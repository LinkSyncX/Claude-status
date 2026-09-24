"""一键切换：把保存的登录写入 Claude Code / Claude Desktop。

安全措施：

- 切换 Claude Code 前先把当前的凭据、``oauthAccount`` 与供应商变量加密
  备份（可撤销），并把当前登录 / 中转配置保存到对应账号——不属于任何
  账号时自动新建账号，保证随时能切回来。
- 当前登录的最新令牌会写回保险箱（Claude Code 使用期间会轮换令牌）。
- Desktop 会话只在 Desktop 已退出时替换；替换前先把当前会话保存到它所
  属的账号，无法归属时另存一份备份。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
import dataclasses
import datetime as dt
import json
import pathlib
from typing import Any

from claude_status import claude_desktop
from claude_status import code_config
from claude_status import models
from claude_status import secure
from claude_status import storage
from claude_status import vault as vault_module

MAX_BACKUPS = 20
_PLAN_BY_SUBSCRIPTION = {
    "pro": models.Plan.PRO,
    "max": models.Plan.MAX_5X,
    "team": models.Plan.TEAM,
    "enterprise": models.Plan.ENTERPRISE,
    "free": models.Plan.FREE,
}


class SwitchError(Exception):
    """无法完成切换（缺少保存的登录、Desktop 仍在运行等）。"""


# ---- 识别当前登录属于哪个账号 ---------------------------------------------


def identify_code_account(
    login: code_config.CodeLogin | None,
    accounts: Sequence[models.Account],
) -> models.Account | None:
    """订阅登录属于哪个账号：先比较账号 UUID，再比较邮箱。"""
    if login is None:
        return None
    oauth = [a for a in accounts if a.auth_type is models.AuthType.OAUTH]
    if login.account_uuid:
        for account in oauth:
            if account.claude_uuid == login.account_uuid:
                return account
    if login.email:
        for account in oauth:
            if account.email.lower() == login.email.lower():
                return account
    return None


def identify_env_account(
    env: dict[str, str], accounts: Sequence[models.Account]
) -> models.Account | None:
    """供应商变量属于哪个 API / 中转账号。"""
    for account in accounts:
        if code_config.matches_provider_env(account, env):
            return account
    return None


def identify_desktop_account(
    account_uuid: str, accounts: Sequence[models.Account]
) -> models.Account | None:
    """Desktop 登录（``lastKnownAccountUuid``）属于哪个账号。"""
    if not account_uuid:
        return None
    return next(
        (a for a in accounts if a.claude_uuid == account_uuid), None
    )


def account_from_code_login(login: code_config.CodeLogin) -> models.Account:
    """由订阅登录新建账号。"""
    plan = _PLAN_BY_SUBSCRIPTION.get(
        login.subscription_type.lower(), models.Plan.PRO
    )
    return models.Account(
        name=login.display_name or login.email.split("@")[0] or "Claude 账号",
        email=login.email,
        plan=plan,
        organization=str(login.oauth_account.get("organizationName") or ""),
        claude_uuid=login.account_uuid,
        org_uuid=login.org_uuid,
        tags=["Claude Code"],
        notes="切换或保存登录时自动创建。",
    )


def learn_identity(
    account: models.Account, login: code_config.CodeLogin
) -> None:
    """用订阅登录补全账号的 UUID 与邮箱（不覆盖已有值）。"""
    account.claude_uuid = account.claude_uuid or login.account_uuid
    account.org_uuid = account.org_uuid or login.org_uuid
    account.email = account.email or login.email


def env_extras(env: dict[str, str]) -> dict[str, str]:
    """供应商变量中除端点与密钥以外的部分（模型映射等）。"""
    return {
        key: value
        for key, value in env.items()
        if key not in code_config.IDENTITY_KEYS
    }


@dataclasses.dataclass
class Preserved:
    """切换前对当前状态的保存结果。

    Attributes:
        created: 为保存当前配置而新建的账号。
        updated: 用当前状态更新过的已有账号。
    """

    created: list[models.Account] = dataclasses.field(default_factory=list)
    updated: list[models.Account] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class CodeSwitchResult:
    """Claude Code 切换结果。"""

    backup: pathlib.Path
    preserved: Preserved


@dataclasses.dataclass
class DesktopSwitchResult:
    """Desktop 切换结果。

    Attributes:
        previous: 切换前 Desktop 登录所属的账号。
        unassigned_backup: 无法归属的旧会话的备份位置。
    """

    previous: models.Account | None = None
    unassigned_backup: pathlib.Path | None = None


class Switcher:
    """执行切换。

    Args:
        vault: 凭据保险箱。
        backup_root: 切换备份目录。
        desktop_running: 判断 Desktop 是否在运行的函数（测试时可替换）。
    """

    def __init__(
        self,
        vault: vault_module.Vault,
        backup_root: pathlib.Path,
        desktop_running: Callable[[], bool] | None = None,
    ) -> None:
        self.vault = vault
        self.backup_root = backup_root
        self._desktop_running = desktop_running or (
            lambda: bool(claude_desktop.running())
        )

    # ---- Claude Code ------------------------------------------------------

    def code_ready(
        self, target: models.Account, accounts: Sequence[models.Account]
    ) -> tuple[bool, str]:
        """能否把 Claude Code 切换到该账号，以及不能时的原因。"""
        if target.auth_type is models.AuthType.OAUTH:
            live = code_config.read_code_login()
            if self.vault.has_code(target.id):
                return True, ""
            if identify_code_account(live, accounts) is target:
                return True, ""
            return False, (
                "该账号还没有保存 Claude Code 登录：请先在 Claude Code 中登录"
                "该账号（claude /login），再在“客户端”页点击“保存当前登录”"
            )
        if not (target.base_url or target.api_key):
            return False, "该账号没有填写 Base URL 或密钥"
        return True, ""

    def backup_code_state(self) -> pathlib.Path:
        """加密备份当前的 Claude Code 登录与供应商变量。"""
        state = {
            "created_at": dt.datetime.now().astimezone().isoformat(),
            "credentials": code_config.read_credentials(),
            "oauth_account": code_config.read_oauth_account(),
            "provider_env": code_config.read_provider_env(),
        }
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = self.backup_root / f"code-{stamp}.bin"
        payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
        storage.atomic_write_bytes(path, secure.protect(payload))
        self._prune()
        return path

    def restore_code_state(self, path: pathlib.Path) -> None:
        """撤销：恢复备份时的凭据、``oauthAccount`` 与供应商变量。"""
        try:
            state: dict[str, Any] = json.loads(
                secure.unprotect(path.read_bytes()).decode("utf-8")
            )
        except (OSError, ValueError, secure.SecureError) as exc:
            raise SwitchError(f"无法读取切换备份：{exc}") from exc
        credentials = state.get("credentials")
        account = state.get("oauth_account")
        env = state.get("provider_env")
        code_config.write_credentials(
            credentials if isinstance(credentials, dict) else None
        )
        code_config.set_oauth_account(
            account if isinstance(account, dict) else None
        )
        code_config.write_provider_env(env if isinstance(env, dict) else {})

    def _prune(self) -> None:
        backups = sorted(self.backup_root.glob("code-*.bin"))
        for old in backups[:-MAX_BACKUPS]:
            old.unlink(missing_ok=True)

    def preserve_current(
        self, accounts: Sequence[models.Account]
    ) -> Preserved:
        """把当前的订阅登录与中转配置保存到所属账号（没有则新建）。"""
        result = Preserved()
        known = list(accounts)
        env = code_config.read_provider_env()
        if env:
            owner = identify_env_account(env, known)
            if owner is None:
                owner = code_config.account_from_env(env)
                result.created.append(owner)
                known.append(owner)
            elif env_extras(env) != owner.env:
                # 用户可能直接改过 settings.json 中的模型映射，以实际配置为准。
                owner.env = env_extras(env)
                result.updated.append(owner)
        login = code_config.read_code_login()
        if login is not None:
            owner = identify_code_account(login, known)
            if owner is None:
                owner = account_from_code_login(login)
                result.created.append(owner)
            else:
                learn_identity(owner, login)
                if owner not in result.updated:
                    result.updated.append(owner)
            self.vault.save_code(owner.id, login)
        return result

    def switch_code(
        self, target: models.Account, accounts: Sequence[models.Account]
    ) -> CodeSwitchResult:
        """把 Claude Code 切换到该账号。

        订阅账号：写入保存的凭据与 ``oauthAccount``，并移除供应商变量；
        API / 中转账号：用该账号的配置替换 ``settings.json`` 中的供应商变量。
        """
        ready, reason = self.code_ready(target, accounts)
        if not ready:
            raise SwitchError(reason)
        backup = self.backup_code_state()
        preserved = self.preserve_current(accounts)
        if target.auth_type is models.AuthType.OAUTH:
            login = self.vault.load_code(target.id)
            if login is None:
                raise SwitchError("无法读取保存的登录（可能来自其他电脑或用户）")
            code_config.write_code_login(login)
            code_config.write_provider_env({})
        else:
            code_config.write_provider_env(code_config.provider_env_for(target))
        return CodeSwitchResult(backup, preserved)

    def capture_code(
        self, accounts: Sequence[models.Account]
    ) -> tuple[models.Account, bool]:
        """把当前的订阅登录保存到所属账号，返回 (账号, 是否新建)。"""
        login = code_config.read_code_login()
        if login is None:
            raise SwitchError("Claude Code 当前没有订阅登录")
        owner = identify_code_account(login, accounts)
        created = owner is None
        if owner is None:
            owner = account_from_code_login(login)
        else:
            learn_identity(owner, login)
        self.vault.save_code(owner.id, login)
        return owner, created

    # ---- Claude Desktop ---------------------------------------------------

    def _require_closed(self) -> None:
        if self._desktop_running():
            raise SwitchError("Claude Desktop 仍在运行，请先退出")

    def _stash_current_desktop(
        self, root: pathlib.Path, accounts: Sequence[models.Account]
    ) -> DesktopSwitchResult:
        """把当前 Desktop 会话保存到所属账号（无法归属时另存备份）。"""
        result = DesktopSwitchResult()
        if not claude_desktop.is_logged_in(root):
            return result
        uuid = claude_desktop.current_account_uuid(root)
        owner = identify_desktop_account(uuid, accounts)
        result.previous = owner
        if owner is not None:
            size = claude_desktop.snapshot_session(
                root, self.vault.desktop_path(owner.id)
            )
            self.vault.write_desktop_meta(owner.id, size, uuid)
        else:
            destination = self.vault.unassigned_path()
            claude_desktop.snapshot_session(root, destination)
            result.unassigned_backup = destination
        return result

    def switch_desktop(
        self,
        target: models.Account,
        accounts: Sequence[models.Account],
        root: pathlib.Path,
    ) -> DesktopSwitchResult:
        """把 Desktop 切换到该账号保存的会话（Desktop 必须已退出）。"""
        if not self.vault.has_desktop(target.id):
            raise SwitchError(
                "该账号还没有保存 Claude Desktop 登录：请先在 Desktop 中登录"
                "该账号，再在“客户端”页点击“保存当前登录”"
            )
        self._require_closed()
        result = self._stash_current_desktop(root, accounts)
        claude_desktop.restore_session(self.vault.desktop_path(target.id), root)
        return result

    def capture_desktop(
        self,
        target: models.Account,
        root: pathlib.Path,
        allow_mismatch: bool = False,
    ) -> int:
        """把 Desktop 当前的登录会话保存到该账号，返回快照大小。

        Raises:
            SwitchError: Desktop 未登录、仍在运行，或登录的账号与该账号
                记录的 UUID 不一致（``allow_mismatch`` 为假时）。
        """
        self._require_closed()
        if not claude_desktop.is_logged_in(root):
            raise SwitchError("Claude Desktop 当前没有登录")
        uuid = claude_desktop.current_account_uuid(root)
        if (
            not allow_mismatch
            and target.claude_uuid
            and uuid
            and target.claude_uuid != uuid
        ):
            raise SwitchError("Desktop 当前登录的不是该账号")
        size = claude_desktop.snapshot_session(
            root, self.vault.desktop_path(target.id)
        )
        self.vault.write_desktop_meta(target.id, size, uuid)
        target.claude_uuid = target.claude_uuid or uuid
        return size

    def new_desktop_login(
        self, accounts: Sequence[models.Account], root: pathlib.Path
    ) -> DesktopSwitchResult:
        """保存当前会话后清空登录，下次启动 Desktop 时显示登录界面。"""
        self._require_closed()
        result = self._stash_current_desktop(root, accounts)
        claude_desktop.clear_session(root)
        return result
