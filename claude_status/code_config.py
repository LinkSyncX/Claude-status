"""Claude Code 的登录凭据与供应商环境变量的读写。

- 订阅登录：``~/.claude/.credentials.json``（OAuth 令牌）与 ``~/.claude.json``
  中的 ``oauthAccount``（邮箱、账号 / 组织 UUID 等）。切换账号时两者一起
  替换；``~/.claude.json`` 的其余内容（项目记录等）保持不变。
- API / 中转：``~/.claude/settings.json`` 的 ``env`` 中以 ``ANTHROPIC_``
  开头的变量（以及子代理模型）。设置了 ``ANTHROPIC_BASE_URL`` 等变量时
  Claude Code 优先使用它们而不是订阅登录。

所有写入都是"读取 → 修改相关键 → 原子替换"，不会改动无关配置。macOS
上的订阅凭据保存在钥匙串中，不在此处理。
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import pathlib
import re
from typing import Any

from claude_status import claude_code
from claude_status import models
from claude_status import storage

OAUTH_KEY = "claudeAiOauth"
# 属于"供应商配置"的非 ANTHROPIC_ 变量：模型映射随中转站而不同。
EXTRA_PROVIDER_KEYS = frozenset({"CLAUDE_CODE_SUBAGENT_MODEL"})
BASE_URL_KEY = "ANTHROPIC_BASE_URL"
AUTH_TOKEN_KEY = "ANTHROPIC_AUTH_TOKEN"
API_KEY_KEY = "ANTHROPIC_API_KEY"
# 端点与密钥：由账号的 Base URL 与 API Key 字段决定，不属于"额外变量"。
IDENTITY_KEYS = (BASE_URL_KEY, AUTH_TOKEN_KEY, API_KEY_KEY)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def credentials_path() -> pathlib.Path:
    """订阅登录凭据文件。"""
    return claude_code.config_dir() / ".credentials.json"


def settings_path() -> pathlib.Path:
    """用户级 ``settings.json``。"""
    return claude_code.config_dir() / "settings.json"


def _read_json(path: pathlib.Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _parse_expiry(value: Any) -> dt.datetime | None:
    if not isinstance(value, int | float):
        return None
    return dt.datetime.fromtimestamp(value / 1000, dt.UTC).astimezone()


@dataclasses.dataclass(frozen=True)
class CodeLogin:
    """一次 Claude Code 订阅登录的完整快照。

    Attributes:
        credentials: ``.credentials.json`` 的全部内容。
        oauth_account: ``~/.claude.json`` 中的 ``oauthAccount``。
    """

    credentials: dict[str, Any]
    oauth_account: dict[str, Any]

    @property
    def oauth(self) -> dict[str, Any]:
        """``claudeAiOauth`` 部分。"""
        value = self.credentials.get(OAUTH_KEY)
        return value if isinstance(value, dict) else {}

    @property
    def email(self) -> str:
        """登录邮箱。"""
        return str(self.oauth_account.get("emailAddress") or "")

    @property
    def account_uuid(self) -> str:
        """账号 UUID（Claude Code 与 Desktop 通用）。"""
        return str(self.oauth_account.get("accountUuid") or "")

    @property
    def org_uuid(self) -> str:
        """组织 UUID。"""
        return str(self.oauth_account.get("organizationUuid") or "")

    @property
    def display_name(self) -> str:
        """显示名。"""
        return str(
            self.oauth_account.get("displayName")
            or self.oauth_account.get("fullName")
            or ""
        )

    @property
    def access_token(self) -> str:
        """访问令牌。"""
        return str(self.oauth.get("accessToken") or "")

    @property
    def refresh_token(self) -> str:
        """刷新令牌。"""
        return str(self.oauth.get("refreshToken") or "")

    @property
    def expires_at(self) -> dt.datetime | None:
        """访问令牌过期时间。"""
        return _parse_expiry(self.oauth.get("expiresAt"))

    @property
    def subscription_type(self) -> str:
        """订阅类型（``pro`` / ``max`` 等）。"""
        return str(self.oauth.get("subscriptionType") or "")

    def expired(
        self, now: dt.datetime | None = None, margin: float = 120.0
    ) -> bool:
        """访问令牌是否已过期（预留 ``margin`` 秒余量）。"""
        expires = self.expires_at
        if expires is None:
            return False
        now = now or dt.datetime.now().astimezone()
        return (expires - now).total_seconds() <= margin

    def with_oauth(self, oauth: dict[str, Any]) -> CodeLogin:
        """返回替换了 ``claudeAiOauth`` 的副本（令牌刷新后使用）。"""
        credentials = dict(self.credentials)
        credentials[OAUTH_KEY] = oauth
        return CodeLogin(credentials, self.oauth_account)

    def same_account(self, other: CodeLogin | None) -> bool:
        """是否为同一个账号（优先比较 UUID）。"""
        if other is None:
            return False
        if self.account_uuid and other.account_uuid:
            return self.account_uuid == other.account_uuid
        return bool(self.email) and self.email.lower() == other.email.lower()

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        return {
            "credentials": self.credentials,
            "oauth_account": self.oauth_account,
        }

    @classmethod
    def from_dict(cls, data: Any) -> CodeLogin | None:
        """反序列化；格式不对时返回 None。"""
        if not isinstance(data, dict):
            return None
        credentials = data.get("credentials")
        account = data.get("oauth_account")
        if not isinstance(credentials, dict):
            return None
        login = cls(credentials, account if isinstance(account, dict) else {})
        return login if login.access_token or login.refresh_token else None


def read_code_login() -> CodeLogin | None:
    """读取当前的订阅登录；没有凭据文件或其中没有令牌时返回 None。"""
    credentials = _read_json(credentials_path())
    if credentials is None:
        return None
    state = _read_json(claude_code.global_state_path()) or {}
    account = state.get("oauthAccount")
    login = CodeLogin(credentials, account if isinstance(account, dict) else {})
    return login if login.access_token or login.refresh_token else None


def write_code_login(login: CodeLogin) -> None:
    """写入订阅登录：替换凭据文件，并更新 ``~/.claude.json`` 的 ``oauthAccount``。"""
    storage.atomic_write_json(credentials_path(), login.credentials)
    set_oauth_account(login.oauth_account or None)


def set_oauth_account(account: dict[str, Any] | None) -> None:
    """设置（None 表示删除）``~/.claude.json`` 的 ``oauthAccount``。"""
    path = claude_code.global_state_path()
    state = _read_json(path)
    if state is None:
        if account is None:
            return
        state = {}
    if account is None:
        state.pop("oauthAccount", None)
    else:
        state["oauthAccount"] = account
    storage.atomic_write_json(path, state)


def read_oauth_account() -> dict[str, Any] | None:
    """当前 ``~/.claude.json`` 中的 ``oauthAccount``。"""
    state = _read_json(claude_code.global_state_path()) or {}
    account = state.get("oauthAccount")
    return account if isinstance(account, dict) else None


def read_usage_cache() -> Any:
    """``~/.claude.json`` 中 Claude Code 缓存的额度（``cachedUsageUtilization``）。"""
    state = _read_json(claude_code.global_state_path()) or {}
    return state.get("cachedUsageUtilization")


def read_credentials() -> dict[str, Any] | None:
    """当前凭据文件的全部内容。"""
    return _read_json(credentials_path())


def write_credentials(credentials: dict[str, Any] | None) -> None:
    """写入凭据文件；None 表示删除。"""
    path = credentials_path()
    if credentials is None:
        path.unlink(missing_ok=True)
        return
    storage.atomic_write_json(path, credentials)


# ---- 供应商环境变量 -------------------------------------------------------


def is_provider_key(key: str) -> bool:
    """是否属于供应商配置（切换 API / 中转账号时整体替换）。"""
    return key.startswith("ANTHROPIC_") or key in EXTRA_PROVIDER_KEYS


def read_settings() -> dict[str, Any]:
    """读取 ``settings.json``（不存在时为空字典）。"""
    return _read_json(settings_path()) or {}


def read_provider_env() -> dict[str, str]:
    """``settings.json`` 中的供应商环境变量。"""
    env = read_settings().get("env")
    if not isinstance(env, dict):
        return {}
    return {
        str(key): str(value)
        for key, value in env.items()
        if is_provider_key(str(key)) and value is not None
    }


def write_provider_env(env: dict[str, str]) -> None:
    """用 ``env`` 整体替换 ``settings.json`` 中的供应商变量，其余设置不变。"""
    path = settings_path()
    settings = read_settings()
    current = settings.get("env")
    merged = {
        key: value
        for key, value in (current if isinstance(current, dict) else {}).items()
        if not is_provider_key(str(key))
    }
    merged.update(env)
    if merged:
        settings["env"] = merged
    else:
        settings.pop("env", None)
    if not settings and not path.exists():
        return
    storage.atomic_write_json(path, settings)


def format_env_lines(env: dict[str, str]) -> str:
    """把变量格式化为每行一个的 ``KEY=VALUE``。"""
    return "\n".join(f"{key}={value}" for key, value in env.items())


def parse_env_lines(text: str) -> dict[str, str]:
    """解析账号的额外变量：每行一个 ``KEY=VALUE``，忽略空行与 ``#`` 注释。

    Raises:
        ValueError: 格式不对或变量不受支持（消息可直接展示给用户）。
    """
    env: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not _ENV_NAME.match(key):
            raise ValueError(f"第 {number} 行应为 KEY=VALUE")
        if key in IDENTITY_KEYS:
            raise ValueError(
                f"第 {number} 行：{key} 请填写在 Base URL / API Key 中"
            )
        if not is_provider_key(key):
            raise ValueError(
                f"第 {number} 行：只支持 ANTHROPIC_* 与 CLAUDE_CODE_SUBAGENT_MODEL"
            )
        env[key] = value.strip()
    return env


def provider_env_for(account: models.Account) -> dict[str, str]:
    """API / 中转账号对应的供应商变量；订阅账号返回空字典。"""
    if account.auth_type is models.AuthType.OAUTH:
        return {}
    env = {
        key: value for key, value in account.env.items() if is_provider_key(key)
    }
    if account.base_url:
        env[BASE_URL_KEY] = account.base_url
    if account.api_key:
        key = (
            API_KEY_KEY
            if account.auth_type is models.AuthType.API_KEY
            else AUTH_TOKEN_KEY
        )
        env.pop(AUTH_TOKEN_KEY if key == API_KEY_KEY else API_KEY_KEY, None)
        env[key] = account.api_key
    return env


def matches_provider_env(
    account: models.Account, env: dict[str, str]
) -> bool:
    """当前供应商变量是否就是该账号的配置（比较端点与密钥）。"""
    if account.auth_type is models.AuthType.OAUTH or not env:
        return False
    expected = provider_env_for(account)
    keys = (BASE_URL_KEY, AUTH_TOKEN_KEY, API_KEY_KEY)
    return all(expected.get(key) == env.get(key) for key in keys)


def account_from_env(env: dict[str, str]) -> models.Account:
    """把当前的供应商变量整理为一个新的 API / 中转账号。"""
    base_url = env.get(BASE_URL_KEY, "")
    token = env.get(AUTH_TOKEN_KEY, "")
    api_key = env.get(API_KEY_KEY, "")
    # 只有 ANTHROPIC_API_KEY 时按 API Key 方式保存，切回时写回同一个变量。
    auth = (
        models.AuthType.API_KEY
        if api_key and not token
        else models.AuthType.RELAY
    )
    extra = {
        key: value
        for key, value in env.items()
        if key not in (BASE_URL_KEY, AUTH_TOKEN_KEY, API_KEY_KEY)
    }
    host = base_url.split("//", 1)[-1].split("/", 1)[0] if base_url else ""
    return models.Account(
        name=f"中转 {host}" if host else "API 配置",
        plan=models.Plan.API,
        auth_type=auth,
        base_url=base_url,
        api_key=token or api_key,
        env=extra,
        tags=["Claude Code"],
        notes="从 Claude Code 的 settings.json 自动导入。",
    )
