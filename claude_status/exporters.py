"""把账号导出为其他工具的导入格式：sub2api 与 CPA（CLIProxyAPI）。

- **sub2api**（Wei-Shaw/sub2api）：管理后台“导入数据”使用的 ``sub2api-data``
  JSON，顶层为 ``type`` / ``version`` / ``exported_at`` / ``proxies`` /
  ``accounts``。订阅账号导出为 ``platform: anthropic``、``type: oauth``，凭据为
  ``access_token`` / ``refresh_token`` / ``expires_at``（Unix 秒）等，组织与账号
  标识放在 ``extra``；API / 中转账号导出为 ``type: apikey``，凭据为
  ``api_key`` / ``base_url``。
- **CPA**（router-for-me/CLIProxyAPI）：认证目录（默认 ``~/.cli-proxy-api``）中
  每个订阅账号一个 ``claude-<哈希>-<邮箱>.json``（哈希为组织或账号 UUID 的
  SHA-256 前 8 位），``type`` 为 ``claude``，时间为 RFC 3339；API / 中转账号
  写成 ``config.yaml`` 中 ``claude-api-key`` 的条目。

订阅账号的令牌来自保存的 Claude Code 登录（或 Claude Code 当前的登录），两种
工具都使用与 Claude Code 相同的 OAuth 客户端，令牌可以直接使用。Claude Desktop
的登录令牌由 Desktop 加密且属于另一个 OAuth 客户端，无法导出。
"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
import datetime as dt
import hashlib
import json
import pathlib
import re
from typing import Any

from claude_status import code_config
from claude_status import models
from claude_status import storage
from claude_status import vault as vault_module

SUB2API = "sub2api"
CPA = "cpa"
SUB2API_TYPE = "sub2api-data"
SUB2API_VERSION = 1
# 与常见的 CPA → sub2api 转换工具一致的默认值，导入后可在 sub2api 中调整。
SUB2API_CONCURRENCY = 10
SUB2API_PRIORITY = 1
CPA_AUTH_DIR = pathlib.Path.home() / ".cli-proxy-api"
CPA_API_KEYS_NAME = "claude-api-key.yaml"
_UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
NO_LOGIN_REASON = (
    "没有 Claude Code 登录：在终端运行 claude /login 登录该账号，再到“客户端”页"
    "保存后即可导出（Claude Desktop 的登录无法导出）"
)


@dataclasses.dataclass(frozen=True)
class ExportItem:
    """一个账号的导出准备情况。

    Attributes:
        account: 账号。
        login: 订阅账号要导出的 Claude Code 登录；API / 中转账号为 None。
        reason: 不能导出的原因，为空表示可以导出。
        live: 导出的登录就是 Claude Code 当前正在使用的那一份。
    """

    account: models.Account
    login: code_config.CodeLogin | None = None
    reason: str = ""
    live: bool = False

    @property
    def exportable(self) -> bool:
        """是否可以导出。"""
        return not self.reason


def collect(
    accounts: Sequence[models.Account],
    vault: vault_module.Vault,
    live_login: code_config.CodeLogin | None = None,
    live_owner: models.Account | None = None,
) -> list[ExportItem]:
    """整理各账号能否导出、用哪一份登录。"""
    items = []
    for account in accounts:
        if account.auth_type is not models.AuthType.OAUTH:
            reason = "" if account.api_key else "没有填写 API Key / 令牌"
            items.append(ExportItem(account, reason=reason))
            continue
        login = vault.load_code(account.id)
        if login is None and live_owner is account:
            login = live_login
        if login is None:
            items.append(ExportItem(account, reason=NO_LOGIN_REASON))
            continue
        live = bool(
            live_login is not None
            and login.refresh_token
            and login.refresh_token == live_login.refresh_token
        )
        items.append(ExportItem(account, login=login, live=live))
    return items


def _rfc3339(moment: dt.datetime) -> str:
    """Go 的 ``time.RFC3339`` 格式（UTC，以 Z 结尾）。"""
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value not in ("", None)}


def _email(item: ExportItem) -> str:
    login = item.login
    return (login.email if login else "") or item.account.email


def _scope(login: code_config.CodeLogin) -> str:
    scopes = login.oauth.get("scopes")
    return " ".join(str(s) for s in scopes) if isinstance(scopes, list) else ""


# ---- sub2api --------------------------------------------------------------


def _sub2api_account(item: ExportItem) -> dict[str, Any]:
    account = item.account
    data: dict[str, Any] = {"name": account.display_name, "platform": "anthropic"}
    login = item.login
    if login is not None:
        email = _email(item)
        expires = login.expires_at
        data["type"] = "oauth"
        data["credentials"] = _compact(
            {
                "access_token": login.access_token,
                "refresh_token": login.refresh_token,
                "expires_at": str(int(expires.timestamp())) if expires else "",
                "token_type": "Bearer",
                "scope": _scope(login),
                "email_address": email,
            }
        )
        data["extra"] = _compact(
            {
                "org_uuid": login.org_uuid,
                "account_uuid": login.account_uuid,
                "email_address": email,
            }
        )
    else:
        data["type"] = "apikey"
        data["credentials"] = _compact(
            {"api_key": account.api_key, "base_url": account.base_url}
        )
    data["concurrency"] = SUB2API_CONCURRENCY
    data["priority"] = SUB2API_PRIORITY
    return data


def to_sub2api(
    items: Sequence[ExportItem], now: dt.datetime | None = None
) -> dict[str, Any]:
    """sub2api 管理后台可导入的 ``sub2api-data`` 数据。"""
    now = now or dt.datetime.now(dt.UTC)
    return {
        "type": SUB2API_TYPE,
        "version": SUB2API_VERSION,
        "exported_at": _rfc3339(now),
        "proxies": [],
        "accounts": [_sub2api_account(item) for item in items if item.exportable],
    }


# ---- CPA（CLIProxyAPI） ---------------------------------------------------


def cpa_file_name(email: str, org_uuid: str = "", account_uuid: str = "") -> str:
    """与 CLIProxyAPI 相同的 Claude 认证文件名。"""
    email = email.strip()
    identity = org_uuid.strip() or account_uuid.strip()
    if identity:
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:8]
        name = f"claude-{digest}-{email}.json"
    else:
        name = f"claude-{email}.json"
    return _UNSAFE_FILE_CHARS.sub("_", name)


def _cpa_document(item: ExportItem, now: dt.datetime) -> dict[str, Any]:
    login = item.login
    assert login is not None
    expires = login.expires_at
    organization = str(login.oauth_account.get("organizationName") or "")
    document: dict[str, Any] = {
        "id_token": "",
        "access_token": login.access_token,
        "refresh_token": login.refresh_token,
        "last_refresh": _rfc3339(now),
        "email": _email(item),
    }
    # 与 CLIProxyAPI 的 omitempty 一致：没有值的标识字段不写。
    document.update(
        _compact(
            {
                "account_uuid": login.account_uuid,
                "organization_uuid": login.org_uuid,
                "organization_name": organization,
            }
        )
    )
    document["type"] = "claude"
    document["expired"] = _rfc3339(expires) if expires else ""
    return document


def cpa_api_keys_yaml(items: Sequence[ExportItem]) -> str:
    """API / 中转账号对应的 ``config.yaml`` 片段（``claude-api-key``）。"""
    lines = [
        "# 由 Claude Status 导出：把下面的条目合并到 CLIProxyAPI 的 config.yaml",
        "claude-api-key:",
    ]
    for item in items:
        account = item.account
        lines.append(f"  # {account.display_name}")
        # JSON 字符串同时是合法的 YAML 双引号字符串。
        api_key = json.dumps(account.api_key, ensure_ascii=False)
        lines.append(f"  - api-key: {api_key}")
        if account.base_url:
            base_url = json.dumps(account.base_url, ensure_ascii=False)
            lines.append(f"    base-url: {base_url}")
    return "\n".join(lines) + "\n"


def to_cpa(
    items: Sequence[ExportItem], now: dt.datetime | None = None
) -> tuple[dict[str, dict[str, Any]], str]:
    """CPA 的认证文件 {文件名: 内容} 与 API Key 配置片段（没有时为空字符串）。"""
    now = now or dt.datetime.now(dt.UTC)
    files = {}
    keys = []
    for item in items:
        if not item.exportable:
            continue
        if item.login is None:
            keys.append(item)
            continue
        login = item.login
        name = cpa_file_name(_email(item), login.org_uuid, login.account_uuid)
        files[name] = _cpa_document(item, now)
    return files, cpa_api_keys_yaml(keys) if keys else ""


# ---- 写入 -----------------------------------------------------------------


def write_sub2api(path: pathlib.Path, items: Sequence[ExportItem]) -> int:
    """写入 sub2api 导入文件，返回导出的账号数。"""
    payload = to_sub2api(items)
    storage.atomic_write_json(path, payload)
    return len(payload["accounts"])


def cpa_targets(items: Sequence[ExportItem]) -> list[str]:
    """导出到 CPA 目录时会写入的文件名（用于确认覆盖）。"""
    files, keys = to_cpa(items)
    return [*files, *([CPA_API_KEYS_NAME] if keys else [])]


def write_cpa(directory: pathlib.Path, items: Sequence[ExportItem]) -> list[str]:
    """把认证文件（与 API Key 配置片段）写入目录，返回写入的文件名。"""
    files, keys = to_cpa(items)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, document in files.items():
        # CLIProxyAPI 以紧凑 JSON 保存认证文件，这里保持一致。
        text = json.dumps(document, ensure_ascii=False) + "\n"
        storage.atomic_write_bytes(directory / name, text.encode("utf-8"))
        written.append(name)
    if keys:
        storage.atomic_write_bytes(
            directory / CPA_API_KEYS_NAME, keys.encode("utf-8")
        )
        written.append(CPA_API_KEYS_NAME)
    return written
