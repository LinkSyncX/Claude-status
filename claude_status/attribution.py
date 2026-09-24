"""本机日志用量的归属：按请求来源计入账号。

Claude Code 与 Claude Desktop 的 Code 标签页都把会话记录写在
``~/.claude/projects``，解析时按客户端与服务商把每条记录分为三种来源
（``models.UsageSource``）：Claude Code（官方）、Claude Desktop（官方）与
中转 / 第三方。

日志不记录账号，因此由 ``ClientManager`` 在运行中观察各来源正在使用的身份
（订阅账号 UUID、组织 UUID 或中转配置的指纹），连同时间记成“身份时间线”；
Desktop 的额度采样带有时间与组织，可补上过去一段时间。归属时取记录发生
时刻的身份，再对应到账号：

- 身份还没有对应的账号时，记录显示为“未归属”（关联或保存账号后自动归属）；
- 最早一次观察之前的记录，按最早观察到的身份归属；
- 从未观察到的来源计入默认归属账号。
"""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from collections.abc import Sequence
import dataclasses
import datetime as dt
import hashlib
from typing import Any

from claude_status import code_config
from claude_status import formatting
from claude_status import models

Source = models.UsageSource
# 时间线最多保留的事件数（切换账号时才会新增，正常使用远远达不到）。
MAX_EVENTS = 1000


# ---- 身份 -----------------------------------------------------------------


def fingerprint(base_url: str, secret: str) -> str:
    """端点与密钥的指纹：不可逆，只用于在配置中记录“是哪一套中转配置”。"""
    text = base_url.strip().rstrip("/") + "\n" + secret.strip()
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def account_identity(uuid: str) -> str:
    """订阅账号（UUID）身份。"""
    return f"account:{uuid}"


def org_identity(uuid: str) -> str:
    """组织（UUID）身份：Desktop 的额度采样只记录组织。"""
    return f"org:{uuid}"


def env_identity(env: dict[str, str]) -> str:
    """供应商变量（端点 + 密钥）对应的身份。"""
    secret = (
        env.get(code_config.AUTH_TOKEN_KEY)
        or env.get(code_config.API_KEY_KEY)
        or ""
    )
    base_url = env.get(code_config.BASE_URL_KEY, "")
    return f"env:{fingerprint(base_url, secret)}"


def current_code_identity(
    login: code_config.CodeLogin | None, env: dict[str, str]
) -> tuple[Source, str] | None:
    """Claude Code 当前的 (来源, 身份)；没有可用配置时返回 None。

    配置了中转端点时 Claude Code 的请求属于“中转 / 第三方”来源；只有
    官方 API Key 或订阅登录属于“Claude Code”来源。
    """
    if env.get(code_config.BASE_URL_KEY):
        return Source.THIRD_PARTY, env_identity(env)
    if env.get(code_config.API_KEY_KEY) or env.get(code_config.AUTH_TOKEN_KEY):
        return Source.CODE, env_identity(env)
    if login is not None and login.account_uuid:
        return Source.CODE, account_identity(login.account_uuid)
    return None


class Resolver:
    """把身份对应到账号（按账号当前记录的 UUID、组织与中转配置）。"""

    def __init__(self, accounts: Sequence[models.Account]) -> None:
        self._accounts = list(accounts)
        self._cache: dict[str, str | None] = {}

    def __call__(self, identity: str) -> str | None:
        if identity not in self._cache:
            self._cache[identity] = self._resolve(identity)
        return self._cache[identity]

    def _resolve(self, identity: str) -> str | None:
        kind, _, value = identity.partition(":")
        if not value:
            return None
        if kind == "account":
            matches = [a for a in self._accounts if a.claude_uuid == value]
        elif kind == "org":
            matches = [
                a
                for a in self._accounts
                if a.auth_type is models.AuthType.OAUTH and a.org_uuid == value
            ]
        elif kind == "env":
            matches = [
                a
                for a in self._accounts
                if a.auth_type is not models.AuthType.OAUTH
                and env_identity(code_config.provider_env_for(a)) == identity
            ]
        else:
            matches = []
        # 同一组织下有多个账号（团队）时无法确定是谁，宁可不归属。
        return matches[0].id if len(matches) == 1 else None


# ---- 时间线 ---------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Event:
    """某个来源从 ``since`` 起使用 ``identity``。"""

    source: Source
    identity: str
    since: dt.datetime

    def to_dict(self) -> dict[str, str]:
        """序列化（保存在设置中）。"""
        return {
            "source": self.source.value,
            "identity": self.identity,
            "since": self.since.isoformat(timespec="seconds"),
        }

    @classmethod
    def from_dict(cls, data: Any) -> Event | None:
        """反序列化；格式不对时返回 None。"""
        if not isinstance(data, dict):
            return None
        try:
            source = Source(data.get("source"))
        except ValueError:
            return None
        identity = data.get("identity")
        since = formatting.parse_iso(data.get("since"))
        if not isinstance(identity, str) or since is None:
            return None
        return cls(source, identity, since)


def load_events(raw: Iterable[Any]) -> list[Event]:
    """从设置中读取时间线（按时间升序）。"""
    events = [event for item in raw if (event := Event.from_dict(item))]
    events.sort(key=lambda event: event.since)
    return events


def record_event(
    raw: list[dict[str, str]],
    source: Source,
    identity: str,
    since: dt.datetime,
) -> bool:
    """在时间线中记录一次观察，返回是否有变化。

    与该来源在该时刻之前最近一次同种身份（账号 / 组织 / 中转配置）相同时
    不记录；可以插入过去的时刻（额度采样），时间线始终按时间排序。
    """
    events = load_events(raw)
    kind = identity.partition(":")[0]
    same = [
        event
        for event in events
        if event.source is source and event.identity.partition(":")[0] == kind
    ]
    index = bisect.bisect_right([event.since for event in same], since)
    if index and same[index - 1].identity == identity:
        return False
    events.append(Event(source, identity, since))
    events.sort(key=lambda event: event.since)
    raw[:] = [event.to_dict() for event in events[-MAX_EVENTS:]]
    return True


class Attributor:
    """按时间线给记录找归属账号。

    Args:
        events: 身份时间线。
        accounts: 账号列表。
        default_account_id: 从未观察到的来源计入的账号。
        fallback: 各来源没有观察记录时使用的身份（例如 Claude Code
            最近一次登录的账号）。
    """

    def __init__(
        self,
        events: Sequence[Event],
        accounts: Sequence[models.Account],
        default_account_id: str | None = None,
        fallback: dict[str, str] | None = None,
    ) -> None:
        self._resolve = Resolver(accounts)
        self._default = default_account_id
        self._fallback = fallback or {}
        self._times: dict[str, list[dt.datetime]] = {}
        self._identities: dict[str, list[str]] = {}
        for event in sorted(events, key=lambda e: e.since):
            self._times.setdefault(event.source, []).append(event.since)
            self._identities.setdefault(event.source, []).append(
                event.identity
            )

    def identity_at(self, source: str, moment: dt.datetime) -> str | None:
        """某来源在某时刻使用的身份；从未观察到时返回 None。"""
        times = self._times.get(source)
        if not times:
            return self._fallback.get(source)
        index = bisect.bisect_right(times, moment)
        return self._identities[source][max(0, index - 1)]

    def account_for(self, source: str, moment: dt.datetime) -> str | None:
        """记录应归属的账号 ID；None 表示未归属。"""
        identity = self.identity_at(source, moment)
        if identity is None:
            return self._default
        return self._resolve(identity)

    def assign(
        self, records: Iterable[models.UsageRecord]
    ) -> list[models.UsageRecord]:
        """返回带有归属账号的记录副本。"""
        return [
            dataclasses.replace(
                record,
                account_id=self.account_for(record.source, record.timestamp),
            )
            for record in records
        ]
