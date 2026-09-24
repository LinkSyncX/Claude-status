"""客户端状态：Claude Code / Claude Desktop 的实时登录、各账号额度与切换。

``ClientManager`` 挂在 ``AppState.clients`` 上：

- ``refresh()`` 读取两个客户端当前登录的账号（只读、很快），并从本机
  来源（Desktop 采样、Claude Code 缓存）更新额度；
- ``refresh_quotas()`` 在后台用保存的登录令牌联网查询额度。当前在
  Claude Code 中使用的登录只读取、不刷新令牌，避免令牌轮换导致正在运行
  的 Claude Code 掉线；
- 切换与保存登录都经由 ``switcher.Switcher`` 完成。
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from typing import TYPE_CHECKING

from PySide6 import QtCore

from claude_status import attribution
from claude_status import claude_desktop
from claude_status import code_config
from claude_status import demo_data
from claude_status import models
from claude_status import quota as quota_module
from claude_status import switcher as switcher_module
from claude_status import tasks
from claude_status import vault as vault_module

if TYPE_CHECKING:
    from claude_status import state as state_module

ONLINE_REFRESH_MS = 10 * 60_000
# Desktop 最新采样在这个时间内，才认为它属于当前登录的账号。
SAMPLE_FRESHNESS = dt.timedelta(minutes=20)


@dataclasses.dataclass(frozen=True)
class ClientInfo:
    """一个账号在两个客户端中的状态（界面展示用）。

    Attributes:
        code_saved: 保存了 Claude Code 订阅登录。
        desktop_saved: 保存了 Claude Desktop 会话。
        code_current: 正在 Claude Code 中使用。
        desktop_current: 正在 Claude Desktop 中登录。
        code_ready: Claude Code 可以切换到该账号。
        quota: 额度（可能已过期或已重置，展示时用 ``Quota.state``）。
        quota_error: 最近一次联网查询额度的错误。
    """

    code_saved: bool = False
    desktop_saved: bool = False
    code_current: bool = False
    desktop_current: bool = False
    code_ready: bool = False
    quota: quota_module.Quota | None = None
    quota_error: str = ""

    def switch_targets(self, include_desktop: bool) -> tuple[bool, bool]:
        """一键切换时需要切换的 (Claude Code, Claude Desktop)。"""
        code = self.code_ready and not self.code_current
        desktop = (
            include_desktop and self.desktop_saved and not self.desktop_current
        )
        return code, desktop


@dataclasses.dataclass
class _QuotaJob:
    account_id: str
    login: code_config.CodeLogin
    allow_refresh: bool


@dataclasses.dataclass
class _QuotaResult:
    account_id: str
    quota: quota_module.Quota | None = None
    error: str = ""
    refreshed: code_config.CodeLogin | None = None


def _run_quota_jobs(jobs: list[_QuotaJob], proxy: str) -> list[_QuotaResult]:
    """（工作线程）逐个账号查询额度，必要时刷新访问令牌。"""
    opener = quota_module.make_opener(proxy)
    results = []
    for job in jobs:
        result = _QuotaResult(job.account_id)
        login = job.login
        try:
            if login.expired():
                if not job.allow_refresh:
                    raise quota_module.QuotaError(
                        "auth",
                        "访问令牌已过期（在 Claude Code 中使用一次后会自动续期）",
                    )
                login = login.with_oauth(
                    quota_module.refresh_oauth(login.oauth, opener)
                )
                result.refreshed = login
            try:
                payload = quota_module.fetch_usage(login.access_token, opener)
            except quota_module.QuotaError as exc:
                if exc.kind != "auth" or not job.allow_refresh or result.refreshed:
                    raise
                login = login.with_oauth(
                    quota_module.refresh_oauth(login.oauth, opener)
                )
                result.refreshed = login
                payload = quota_module.fetch_usage(login.access_token, opener)
            result.quota = quota_module.parse_usage(
                payload, dt.datetime.now().astimezone()
            )
        except quota_module.QuotaError as exc:
            result.error = str(exc)
        results.append(result)
    return results


class ClientManager(QtCore.QObject):
    """客户端状态与操作。

    Args:
        app_state: 应用状态。
        offline: 为真时不联网查询额度。
    """

    changed = QtCore.Signal()
    quota_loading_changed = QtCore.Signal(bool)

    def __init__(
        self, app_state: state_module.AppState, offline: bool = False
    ) -> None:
        super().__init__(app_state)
        self._state = app_state
        root = app_state.store.directory
        self.vault = vault_module.Vault(root / "vault")
        self.switcher = switcher_module.Switcher(self.vault, root / "backups")
        self.offline = offline
        self.code_login: code_config.CodeLogin | None = None
        self.oauth_account: dict = {}
        self.provider_env: dict[str, str] = {}
        self.desktop: claude_desktop.DesktopState | None = None
        self.quota_errors: dict[str, str] = {}
        self.last_online_refresh: dt.datetime | None = None
        self._quota_task: tasks.Task | None = None
        self._signature: tuple | None = None
        try:
            self.vault.purge_trash()
        except OSError:
            pass
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(ONLINE_REFRESH_MS)
        self._timer.timeout.connect(lambda: self.refresh_quotas(manual=False))
        self._timer.start()

    @property
    def accounts(self) -> list[models.Account]:
        """账号列表（来自应用状态）。"""
        return self._state.accounts

    # ---- 读取实时状态 -----------------------------------------------------

    def refresh(self) -> None:
        """重新读取两个客户端的登录状态，并用本机来源更新额度。"""
        self.code_login = code_config.read_code_login()
        self.oauth_account = code_config.read_oauth_account() or {}
        self.provider_env = code_config.read_provider_env()
        try:
            self.desktop = claude_desktop.read_state()
        except OSError:
            self.desktop = None
        learned = self._learn_identity()
        quotas = self._apply_local_quotas()
        observed = self._observe_sources()
        changed_accounts = learned or quotas or observed
        current = self.current_code_account()
        settings = self._state.settings
        if current is not None and settings.active_account_id != current.id:
            settings.active_account_id = current.id
            changed_accounts = True
        desktop_current = self.current_desktop_account()
        desktop_id = desktop_current.id if desktop_current else None
        if desktop_id and settings.desktop_account_id != desktop_id:
            settings.desktop_account_id = desktop_id
            changed_accounts = True
        if changed_accounts:
            self._state.save()
        if learned or quotas or observed:
            # 账号身份或时间线有变化：重新归属本机用量。
            self._state.reattribute()
        signature = self._make_signature()
        if signature != self._signature or changed_accounts:
            self._signature = signature
            self.changed.emit()

    def _make_signature(self) -> tuple:
        desktop = self.desktop
        return (
            self.code_login.account_uuid if self.code_login else None,
            self.code_login.access_token[-8:] if self.code_login else None,
            tuple(sorted(self.provider_env.items())),
            desktop.running if desktop else None,
            desktop.account_uuid if desktop else None,
            desktop.logged_in if desktop else None,
            len(desktop.samples) if desktop else 0,
            tuple(sorted(self.quota_errors.items())),
        )

    def current_code_account(self) -> models.Account | None:
        """正在 Claude Code 中使用的账号（中转配置优先于订阅登录）。"""
        if self.provider_env:
            return switcher_module.identify_env_account(
                self.provider_env, self.accounts
            )
        return switcher_module.identify_code_account(
            self.code_login, self.accounts
        )

    def current_desktop_account(self) -> models.Account | None:
        """正在 Claude Desktop 中登录的账号。"""
        desktop = self.desktop
        if desktop is None or not desktop.logged_in:
            return None
        return switcher_module.identify_desktop_account(
            desktop.account_uuid, self.accounts
        )

    def code_owner(self) -> models.Account | None:
        """当前订阅登录（不论是否被中转配置覆盖）所属的账号。"""
        return switcher_module.identify_code_account(
            self.code_login, self.accounts
        )

    def env_owner(self) -> models.Account | None:
        """当前中转 / API 配置所属的账号。"""
        if not self.provider_env:
            return None
        return switcher_module.identify_env_account(
            self.provider_env, self.accounts
        )

    def info(self, account: models.Account) -> ClientInfo:
        """账号在两个客户端中的状态。"""
        oauth = account.auth_type is models.AuthType.OAUTH
        code_saved = oauth and self.vault.has_code(account.id)
        code_current = self.current_code_account() is account
        if oauth:
            code_ready = code_saved or self.code_owner() is account
        else:
            code_ready = bool(account.base_url or account.api_key)
        return ClientInfo(
            code_saved=code_saved,
            desktop_saved=self.vault.has_desktop(account.id),
            code_current=code_current,
            desktop_current=self.current_desktop_account() is account,
            code_ready=code_ready,
            quota=self.quota(account),
            quota_error=self.quota_errors.get(account.id, ""),
        )

    def quota(self, account: models.Account) -> quota_module.Quota | None:
        """账号的额度；以 --demo 启动时，没有真实额度的账号使用演示额度。"""
        stored = quota_module.Quota.from_dict(account.quota)
        if stored is None and self._state.demo_forced:
            return demo_data.sample_quota(account)
        return stored

    def samples_for(
        self, account: models.Account
    ) -> list[claude_desktop.Sample]:
        """账号所在组织的 Desktop 额度采样（用于额度走势）。"""
        if self.desktop is None or not account.org_uuid:
            return []
        return [s for s in self.desktop.samples if s.org == account.org_uuid]

    def _learn_identity(self) -> bool:
        """账号还没有 UUID 时，用 ``~/.claude.json`` 中同邮箱的登录信息补全。

        没有保存登录的账号（例如由本机登录信息自动创建的）因此也能被
        Desktop 识别，并对应上 Desktop 的额度采样。返回账号是否有变化。
        """
        oauth_account = self.oauth_account
        uuid = str(oauth_account.get("accountUuid") or "")
        email = str(oauth_account.get("emailAddress") or "").lower()
        if not uuid or not email:
            return False
        if any(account.claude_uuid == uuid for account in self.accounts):
            return False
        for account in self.accounts:
            if (
                account.auth_type is models.AuthType.OAUTH
                and not account.claude_uuid
                and account.email.lower() == email
            ):
                account.claude_uuid = uuid
                account.org_uuid = account.org_uuid or str(
                    oauth_account.get("organizationUuid") or ""
                )
                return True
        return False

    def _observe_sources(self) -> bool:
        """把各用量来源当前使用的身份记入时间线，返回是否有变化。"""
        raw = self._state.settings.usage_sources
        now = dt.datetime.now().astimezone()
        changed = False
        code = attribution.current_code_identity(
            self.code_login, self.provider_env
        )
        if code is not None:
            changed |= attribution.record_event(raw, code[0], code[1], now)
        desktop = self.desktop
        if desktop is not None:
            desktop_source = models.UsageSource.DESKTOP
            # 额度采样记录了过去各时刻登录的组织，可补上本工具没运行的时段。
            previous = ""
            for sample in desktop.samples:
                if sample.org and sample.org != previous:
                    changed |= attribution.record_event(
                        raw,
                        desktop_source,
                        attribution.org_identity(sample.org),
                        sample.time,
                    )
                previous = sample.org
            if desktop.logged_in and desktop.account_uuid:
                changed |= attribution.record_event(
                    raw,
                    desktop_source,
                    attribution.account_identity(desktop.account_uuid),
                    now,
                )
        return changed

    def attributor(self) -> attribution.Attributor:
        """按当前的账号与时间线归属本机用量。"""
        fallback = {}
        uuid = str(self.oauth_account.get("accountUuid") or "")
        if uuid:
            # 没观察到过 Claude Code 官方来源时，归给它最近登录的账号。
            fallback[models.UsageSource.CODE] = attribution.account_identity(
                uuid
            )
        linked = self._state.linked_account()
        return attribution.Attributor(
            attribution.load_events(self._state.settings.usage_sources),
            self.accounts,
            linked.id if linked else None,
            fallback,
        )

    def source_owner(
        self, source: models.UsageSource
    ) -> tuple[bool, models.Account | None]:
        """某来源当前的 (是否识别到身份, 对应的账号)。"""
        now = dt.datetime.now().astimezone()
        attributor = self.attributor()
        identity = attributor.identity_at(source, now)
        account_id = attributor.account_for(source, now)
        return identity is not None, self._state.account(account_id)

    def fresh_desktop_org(self) -> str:
        """Desktop 正在运行且刚采样过时，当前登录账号所在的组织。"""
        desktop = self.desktop
        if desktop is None or not desktop.samples or not desktop.running:
            return ""
        latest = desktop.samples[-1]
        now = dt.datetime.now().astimezone()
        return latest.org if now - latest.time < SAMPLE_FRESHNESS else ""

    def _apply_local_quotas(self) -> bool:
        """用 Desktop 采样与 Claude Code 缓存更新额度，返回账号是否有变化。"""
        changed = False
        now = dt.datetime.now().astimezone()
        desktop = self.desktop
        candidates: list[tuple[models.Account, quota_module.Quota]] = []
        if desktop is not None and desktop.samples:
            current = self.current_desktop_account()
            org = self.fresh_desktop_org()
            if current is not None and not current.org_uuid and org:
                current.org_uuid = org
                changed = True
            by_org = {sample.org: sample for sample in desktop.samples}
            for account in self.accounts:
                sample = by_org.get(account.org_uuid)
                if sample is None:
                    continue
                parsed = quota_module.from_desktop_sample(
                    sample.usage, int(sample.time.timestamp() * 1000)
                )
                if parsed is not None:
                    candidates.append((account, parsed))
        cached = quota_module.from_claude_code_cache(
            code_config.read_usage_cache()
        )
        if cached is not None:
            uuid, parsed = cached
            for account in self.accounts:
                if account.claude_uuid and account.claude_uuid == uuid:
                    candidates.append((account, parsed))
        for account, candidate in candidates:
            if self._store_quota(account, candidate):
                changed = True
        return changed

    @staticmethod
    def _store_quota(
        account: models.Account, candidate: quota_module.Quota
    ) -> bool:
        existing = quota_module.Quota.from_dict(account.quota)
        if quota_module.newest(existing, candidate) is candidate and (
            existing is None or candidate != existing
        ):
            account.quota = candidate.to_dict()
            return True
        return False

    # ---- 联网额度 ---------------------------------------------------------

    @property
    def quota_loading(self) -> bool:
        """是否正在联网查询额度。"""
        return self._quota_task is not None

    def online_enabled(self) -> bool:
        """当前是否允许联网查询额度。"""
        return not self.offline and self._state.settings.quota_online

    def refresh_quotas(self, manual: bool = True) -> bool:
        """后台联网查询所有已保存登录的账号的额度，返回是否已开始。"""
        if self._quota_task is not None or not self.online_enabled():
            return False
        live = self.code_login
        live_owner = self.code_owner()
        jobs = []
        for account in self.accounts:
            if account.auth_type is not models.AuthType.OAUTH:
                continue
            if live is not None and account is live_owner:
                # 正在使用的登录：只读取令牌，不刷新（避免 Claude Code 掉线）。
                jobs.append(_QuotaJob(account.id, live, allow_refresh=False))
                continue
            saved = self.vault.load_code(account.id)
            if saved is None:
                continue
            shares_grant = (
                live is not None and saved.refresh_token == live.refresh_token
            )
            jobs.append(_QuotaJob(account.id, saved, not shares_grant))
        if not jobs:
            if manual:
                self._state.notify.emit(
                    "没有可查询额度的账号：请先保存 Claude Code 登录"
                )
            return False
        proxy = self._state.settings.proxy
        self._quota_task = tasks.run(
            lambda: _run_quota_jobs(jobs, proxy),
            self._on_quotas,
            self._on_quota_failure,
            self,
        )
        self.quota_loading_changed.emit(True)
        return True

    def _on_quotas(self, results: list[_QuotaResult]) -> None:
        self._quota_task = None
        self.last_online_refresh = dt.datetime.now().astimezone()
        errors = 0
        for result in results:
            account = self._state.account(result.account_id)
            if account is None:
                continue
            if result.refreshed is not None and self.vault.has_code(account.id):
                self.vault.save_code(account.id, result.refreshed)
            if result.quota is not None:
                self._store_quota(account, result.quota)
                self.quota_errors.pop(account.id, None)
            else:
                self.quota_errors[account.id] = result.error
                errors += 1
        self._state.save()
        self.quota_loading_changed.emit(False)
        self._signature = None
        self.changed.emit()
        if errors:
            self._state.notify.emit(
                f"{len(results) - errors} 个账号额度已更新，{errors} 个失败"
            )

    def _on_quota_failure(self, error: BaseException) -> None:
        self._quota_task = None
        self.quota_loading_changed.emit(False)
        self._state.notify.emit(f"查询额度失败：{error}")

    # ---- 操作 -------------------------------------------------------------

    def _adopt(self, accounts: list[models.Account]) -> None:
        for account in accounts:
            if self._state.account(account.id) is None:
                self._state.accounts.append(account)

    def capture_code(self) -> tuple[models.Account, bool]:
        """保存当前的 Claude Code 订阅登录，返回 (账号, 是否新建)。"""
        account, created = self.switcher.capture_code(self.accounts)
        if created:
            # 还没有账号接收本机日志用量时，由新账号接收。
            if not any(a.link_local for a in self.accounts):
                account.link_local = True
            self._adopt([account])
        self._state.accounts_modified()
        self.refresh()
        return account, created

    def add_login(
        self,
        login: code_config.CodeLogin,
        target: models.Account | None = None,
    ) -> tuple[models.Account, bool]:
        """保存在本工具中完成的登录，返回 (账号, 是否新建)。

        未指定账号时按 UUID / 邮箱找到对应账号，找不到则新建。这是一份独立的
        登录（与 Claude Code 当前的登录互不影响），切换时写入 Claude Code。

        Raises:
            switcher.SwitchError: 指定的账号记录的是另一个 Claude 账号。
        """
        account = target or switcher_module.identify_code_account(
            login, self.accounts
        )
        created = account is None
        if account is None:
            account = switcher_module.account_from_code_login(login)
        elif (
            account.claude_uuid
            and login.account_uuid
            and account.claude_uuid != login.account_uuid
        ):
            raise switcher_module.SwitchError(
                f"登录的是 {login.email or '另一个账号'}，与「{account.display_name}」"
                "记录的 Claude 账号不同"
            )
        switcher_module.learn_identity(account, login)
        plan = switcher_module.plan_for_login(login)
        if plan is not None:
            account.plan = plan
        account.organization = account.organization or str(
            login.oauth_account.get("organizationName") or ""
        )
        if account.status is models.AccountStatus.EXPIRED:
            account.status = models.AccountStatus.ACTIVE
        self.vault.save_code(account.id, login)
        self.quota_errors.pop(account.id, None)
        if created:
            if not any(a.link_local for a in self.accounts):
                account.link_local = True
            self._adopt([account])
        self._state.accounts_modified()
        self.refresh()
        return account, created

    def import_provider_env(self) -> models.Account | None:
        """把当前的中转 / API 配置保存为账号（已存在时返回该账号）。"""
        if not self.provider_env:
            return None
        existing = self.env_owner()
        if existing is not None:
            return existing
        account = code_config.account_from_env(self.provider_env)
        self._adopt([account])
        self._state.accounts_modified()
        self.refresh()
        return account

    def switch_code(
        self, account: models.Account
    ) -> switcher_module.CodeSwitchResult:
        """把 Claude Code 切换到该账号。"""
        result = self.switcher.switch_code(account, self.accounts)
        self._adopt(result.preserved.created)
        account.last_used_at = dt.datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        self._state.settings.active_account_id = account.id
        self._state.accounts_modified()
        self.refresh()
        return result

    def undo_code(self, backup) -> None:
        """撤销上一次 Claude Code 切换。"""
        self.switcher.restore_code_state(backup)
        self.refresh()

    def link_desktop(self, account: models.Account) -> None:
        """把 Desktop 当前登录的账号关联到该账号（不需要退出 Desktop）。

        关联后即可识别 Desktop 的登录、对应额度采样并归属 Code 标签页的
        用量；要一键切换回该账号，还需要保存会话（``capture_desktop``）。

        Raises:
            switcher.SwitchError: Desktop 没有登录，或该账号记录的是另一个
                Claude 账号。
        """
        desktop = self.desktop
        if desktop is None or not desktop.logged_in or not desktop.account_uuid:
            raise switcher_module.SwitchError("Claude Desktop 当前没有登录")
        uuid = desktop.account_uuid
        if account.claude_uuid and account.claude_uuid != uuid:
            raise switcher_module.SwitchError(
                f"「{account.display_name}」记录的是另一个 Claude 账号，"
                "请选择其他账号或新建账号"
            )
        owner = switcher_module.identify_desktop_account(uuid, self.accounts)
        if owner is not None and owner is not account:
            raise switcher_module.SwitchError(
                f"Desktop 当前登录的账号已关联到「{owner.display_name}」"
            )
        account.claude_uuid = uuid
        account.org_uuid = account.org_uuid or self.fresh_desktop_org()
        self._state.settings.desktop_account_id = account.id
        self._state.accounts_modified()
        self.refresh()

    def capture_desktop(
        self, account: models.Account, allow_mismatch: bool = False
    ) -> int:
        """（Desktop 已退出）把当前 Desktop 会话保存到该账号。"""
        size = self.switcher.capture_desktop(
            account, claude_desktop.data_dir(), allow_mismatch
        )
        self._state.settings.desktop_account_id = account.id
        self._state.accounts_modified()
        self.refresh()
        return size

    def switch_desktop(
        self, account: models.Account
    ) -> switcher_module.DesktopSwitchResult:
        """（Desktop 已退出）把 Desktop 切换到该账号保存的会话。"""
        result = self.switcher.switch_desktop(
            account, self.accounts, claude_desktop.data_dir()
        )
        self._state.settings.desktop_account_id = account.id
        account.last_used_at = dt.datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        self._state.accounts_modified()
        self.refresh()
        return result

    def new_desktop_login(self) -> switcher_module.DesktopSwitchResult:
        """（Desktop 已退出）保存当前会话后清空登录。"""
        result = self.switcher.new_desktop_login(
            self.accounts, claude_desktop.data_dir()
        )
        self._state.settings.desktop_account_id = None
        self._state.accounts_modified()
        self.refresh()
        return result

    def forget_code(self, account: models.Account) -> None:
        """删除账号保存的 Claude Code 登录。"""
        self.vault.delete_code(account.id)
        self.refresh()
        self.changed.emit()

    def forget_desktop(self, account: models.Account) -> None:
        """删除账号保存的 Desktop 会话。"""
        self.vault.delete_desktop(account.id)
        self.refresh()
        self.changed.emit()

    def sync_edited_account(
        self, before: models.Account | None, account: models.Account
    ) -> bool:
        """编辑的正是 Claude Code 当前使用的中转 / API 账号时，把新配置
        同步到 ``settings.json``，返回是否同步。"""
        if before is None or before.id != account.id:
            return False
        if account.auth_type is models.AuthType.OAUTH:
            return False
        env = code_config.provider_env_for(account)
        if env == self.provider_env:
            return False
        self.switcher.backup_code_state()
        code_config.write_provider_env(env)
        self.refresh()
        return True

    def shutdown(self) -> None:
        """停止定时器。"""
        self._timer.stop()
