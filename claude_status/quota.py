"""订阅额度：5 小时窗口与每周额度的解析、联网获取与令牌刷新。

数据来源（按获取时间择新使用）：

- 联网：用保存的 Claude Code 登录令牌请求 ``/api/oauth/usage``，与官方
  客户端使用同一接口；访问令牌过期时用刷新令牌换新（刷新令牌会轮换，
  新令牌必须写回保存处）。
- Claude Desktop 的 ``plan-usage-history.json``：Desktop 运行时约每 15
  分钟按组织记录一次 ``{"fh": 5 小时 %, "sd": 每周 %}``，不含重置时间。
- Claude Code 的 ``~/.claude.json`` 中 ``cachedUsageUtilization`` 缓存。

接口与客户端 ID 取自官方 Claude Code 客户端，属于未公开接口，可能随
版本变化；失败时只影响额度显示。
"""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
import datetime as dt
import enum
import json
import time
from typing import Any
import urllib.error
import urllib.request

import claude_status

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_BETA = "oauth-2025-04-20"
FIVE_HOURS = dt.timedelta(hours=5)
ONE_WEEK = dt.timedelta(days=7)
TIMEOUT = 20.0

Opener = Callable[[urllib.request.Request, float], Any]


class Source(enum.Enum):
    """额度数据来源。"""

    API = "api"
    DESKTOP = "desktop"
    CLAUDE_CODE = "claude_code"
    DEMO = "demo"

    @property
    def label(self) -> str:
        """界面显示名称。"""
        return {
            "api": "联网查询",
            "desktop": "Claude Desktop 采样",
            "claude_code": "Claude Code 缓存",
            "demo": "演示数据",
        }[self.value]


def _parse_time(value: Any) -> dt.datetime | None:
    if isinstance(value, int | float):
        return dt.datetime.fromtimestamp(value / 1000, dt.UTC).astimezone()
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone()


@dataclasses.dataclass(frozen=True)
class Window:
    """一个额度窗口。

    Attributes:
        percent: 已用百分比（0–100，可能超过 100）。
        resets_at: 重置时间，未知时为 None。
        label: 按模型划分的周额度的名称（如 ``Fable``）。
    """

    percent: float
    resets_at: dt.datetime | None = None
    label: str = ""

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        return {
            "percent": self.percent,
            "resets_at": self.resets_at.isoformat() if self.resets_at else None,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Window:
        """反序列化。"""
        return cls(
            float(data.get("percent") or 0.0),
            _parse_time(data.get("resets_at")),
            str(data.get("label") or ""),
        )


@dataclasses.dataclass(frozen=True)
class WindowState:
    """某一时刻窗口的实际状态（考虑重置）。"""

    percent: float
    reset: bool
    resets_at: dt.datetime | None


@dataclasses.dataclass(frozen=True)
class Quota:
    """一个账号的额度快照。

    Attributes:
        fetched_at: 获取（采样）时间。
        source: 数据来源。
        five_hour: 5 小时窗口。
        seven_day: 每周额度。
        scoped: 按模型划分的周额度。
    """

    fetched_at: dt.datetime
    source: Source
    five_hour: Window | None = None
    seven_day: Window | None = None
    scoped: tuple[Window, ...] = ()

    @property
    def empty(self) -> bool:
        """是否没有任何窗口数据。"""
        return self.five_hour is None and self.seven_day is None

    def state(
        self, window: Window | None, span: dt.timedelta, now: dt.datetime
    ) -> WindowState | None:
        """窗口在 ``now`` 时的状态：已过重置时间（或采样已超过一个窗口
        长度且不知道重置时间）时视为已重置、用量归零。"""
        if window is None:
            return None
        if window.resets_at is not None:
            if now >= window.resets_at:
                return WindowState(0.0, True, None)
            return WindowState(window.percent, False, window.resets_at)
        if now - self.fetched_at >= span:
            return WindowState(0.0, True, None)
        return WindowState(window.percent, False, None)

    def to_dict(self) -> dict[str, Any]:
        """序列化。"""
        return {
            "fetched_at": self.fetched_at.isoformat(),
            "source": self.source.value,
            "five_hour": self.five_hour.to_dict() if self.five_hour else None,
            "seven_day": self.seven_day.to_dict() if self.seven_day else None,
            "scoped": [window.to_dict() for window in self.scoped],
        }

    @classmethod
    def from_dict(cls, data: Any) -> Quota | None:
        """反序列化；格式不对时返回 None。"""
        if not isinstance(data, dict):
            return None
        fetched = _parse_time(data.get("fetched_at"))
        try:
            source = Source(data.get("source"))
        except ValueError:
            return None
        if fetched is None:
            return None

        def window(value: Any) -> Window | None:
            return Window.from_dict(value) if isinstance(value, dict) else None

        return cls(
            fetched,
            source,
            window(data.get("five_hour")),
            window(data.get("seven_day")),
            tuple(
                Window.from_dict(item)
                for item in data.get("scoped") or []
                if isinstance(item, dict)
            ),
        )


def newest(*quotas: Quota | None) -> Quota | None:
    """取获取时间最新的非空额度。"""
    candidates = [q for q in quotas if q is not None and not q.empty]
    return max(candidates, key=lambda q: q.fetched_at, default=None)


def _legacy_window(value: Any, label: str = "") -> Window | None:
    if not isinstance(value, dict):
        return None
    percent = value.get("utilization")
    if not isinstance(percent, int | float):
        return None
    return Window(float(percent), _parse_time(value.get("resets_at")), label)


def _scope_label(scope: Any) -> str:
    if isinstance(scope, dict):
        model = scope.get("model")
        if isinstance(model, dict) and model.get("display_name"):
            return str(model["display_name"])
        if scope.get("surface"):
            return str(scope["surface"])
    return "指定模型"


def parse_usage(
    payload: dict[str, Any],
    fetched_at: dt.datetime,
    source: Source = Source.API,
) -> Quota:
    """解析 ``/api/oauth/usage`` 的响应（或 Claude Code 缓存中的同构数据）。

    新版响应带 ``limits`` 列表（``session`` / ``weekly_all`` /
    ``weekly_scoped``），旧版只有 ``five_hour`` / ``seven_day`` 等对象，
    两种格式都支持，优先使用 ``limits``。
    """
    five_hour = seven_day = None
    scoped: list[Window] = []
    for item in payload.get("limits") or []:
        if not isinstance(item, dict):
            continue
        percent = item.get("percent")
        if not isinstance(percent, int | float):
            continue
        window = Window(float(percent), _parse_time(item.get("resets_at")))
        kind = item.get("kind")
        if kind == "session":
            five_hour = window
        elif kind == "weekly_all":
            seven_day = window
        elif kind == "weekly_scoped" and (item.get("is_active") or percent > 0):
            scoped.append(
                dataclasses.replace(window, label=_scope_label(item.get("scope")))
            )
    five_hour = five_hour or _legacy_window(payload.get("five_hour"))
    seven_day = seven_day or _legacy_window(payload.get("seven_day"))
    if not scoped:
        for key, label in (("seven_day_opus", "Opus"), ("seven_day_sonnet", "Sonnet")):
            window = _legacy_window(payload.get(key), label)
            if window is not None and window.percent > 0:
                scoped.append(window)
    return Quota(fetched_at, source, five_hour, seven_day, tuple(scoped))


def from_desktop_sample(usage: dict[str, Any], time_ms: int) -> Quota | None:
    """由 Desktop 的一条采样 ``{"fh": …, "sd": …}`` 构造额度。"""
    fetched = _parse_time(time_ms)
    if fetched is None:
        return None

    def window(key: str) -> Window | None:
        value = usage.get(key)
        return Window(float(value)) if isinstance(value, int | float) else None

    return Quota(fetched, Source.DESKTOP, window("fh"), window("sd"))


def from_claude_code_cache(cache: Any) -> tuple[str, Quota] | None:
    """解析 ``~/.claude.json`` 的 ``cachedUsageUtilization``，返回 (账号 UUID, 额度)。"""
    if not isinstance(cache, dict):
        return None
    account = cache.get("accountUuid")
    utilization = cache.get("utilization")
    fetched = _parse_time(cache.get("fetchedAtMs"))
    if not isinstance(account, str) or not isinstance(utilization, dict):
        return None
    if fetched is None:
        return None
    return account, parse_usage(utilization, fetched, Source.CLAUDE_CODE)


# ---- 联网 ------------------------------------------------------------------


class QuotaError(Exception):
    """获取额度失败。

    Attributes:
        kind: ``auth``（令牌无效）/ ``network`` / ``http`` / ``format``。
    """

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


def make_opener(proxy: str = "") -> Opener:
    """构造请求函数；``proxy`` 为空时使用环境变量与系统代理设置。"""
    handlers = []
    if proxy:
        handlers.append(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
    opener = urllib.request.build_opener(*handlers)
    return lambda request, timeout: opener.open(request, timeout=timeout)


def user_agent() -> str:
    """请求使用的 User-Agent。"""
    return f"claude-status/{claude_status.__version__}"


def request_json(
    opener: Opener, request: urllib.request.Request
) -> dict[str, Any]:
    """发送请求并解析 JSON 对象；错误统一转换为 ``QuotaError``。"""
    try:
        with opener(request, TIMEOUT) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        exc.close()  # 错误响应也持有连接，及时释放
        if exc.code in (401, 403):
            raise QuotaError("auth", "登录已失效，需要重新登录该账号") from exc
        raise QuotaError("http", f"服务器返回 {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise QuotaError(
            "network", f"网络连接失败：{reason}（可在设置中配置代理）"
        ) from exc
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise QuotaError("format", "服务器返回的不是 JSON") from exc
    if not isinstance(data, dict):
        raise QuotaError("format", "服务器返回的数据格式不正确")
    return data


def fetch_usage(
    access_token: str, opener: Opener | None = None
) -> dict[str, Any]:
    """用访问令牌查询当前账号的额度。

    Raises:
        QuotaError: 令牌无效、网络错误或响应格式错误。
    """
    request = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": OAUTH_BETA,
            "Content-Type": "application/json",
            "User-Agent": user_agent(),
        },
    )
    return request_json(opener or make_opener(), request)


def refresh_oauth(
    oauth: dict[str, Any], opener: Opener | None = None
) -> dict[str, Any]:
    """用刷新令牌换取新的访问令牌，返回更新后的 ``claudeAiOauth``。

    请求格式与官方客户端一致：JSON 请求体包含 ``grant_type``、
    ``refresh_token``、``client_id`` 与 ``scope``。刷新令牌会轮换，调用方
    必须保存返回的新令牌。

    Raises:
        QuotaError: 没有刷新令牌、令牌已失效或网络错误。
    """
    refresh_token = oauth.get("refreshToken")
    if not refresh_token:
        raise QuotaError("auth", "没有可用的刷新令牌，需要重新登录该账号")
    scopes = oauth.get("scopes") or []
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "scope": " ".join(scopes),
    }
    request = urllib.request.Request(
        TOKEN_URL,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": user_agent(),
        },
    )
    data = request_json(opener or make_opener(), request)
    access = data.get("access_token")
    if not isinstance(access, str) or not access:
        raise QuotaError("format", "令牌刷新响应中没有访问令牌")
    updated = dict(oauth)
    updated["accessToken"] = access
    if data.get("refresh_token"):
        updated["refreshToken"] = data["refresh_token"]
    expires_in = data.get("expires_in")
    if isinstance(expires_in, int | float):
        updated["expiresAt"] = int((time.time() + expires_in) * 1000)
    if isinstance(data.get("scope"), str) and data["scope"]:
        updated["scopes"] = data["scope"].split()
    return updated
