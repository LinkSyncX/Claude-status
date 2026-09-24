"""数据模型：账号、用量记录与应用设置。

账号与设置会被序列化为 JSON 保存；用量记录只在内存中存在，由数据源
（本机 Claude Code 日志或演示数据）在每次刷新时重新生成。
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
from typing import Any
import uuid


class Plan(enum.Enum):
    """账号套餐。"""

    FREE = "free"
    PRO = "pro"
    MAX_5X = "max_5x"
    MAX_20X = "max_20x"
    TEAM = "team"
    ENTERPRISE = "enterprise"
    API = "api"

    @property
    def label(self) -> str:
        """界面显示名称。"""
        return _PLAN_LABELS[self]


_PLAN_LABELS = {
    Plan.FREE: "Free",
    Plan.PRO: "Pro",
    Plan.MAX_5X: "Max 5x",
    Plan.MAX_20X: "Max 20x",
    Plan.TEAM: "Team",
    Plan.ENTERPRISE: "Enterprise",
    Plan.API: "API 按量",
}


class AuthType(enum.Enum):
    """认证方式。"""

    OAUTH = "oauth"
    API_KEY = "api_key"
    RELAY = "relay"

    @property
    def label(self) -> str:
        """界面显示名称。"""
        return _AUTH_LABELS[self][0]

    @property
    def icon(self) -> str:
        """对应的 Material Symbols 图标名。"""
        return _AUTH_LABELS[self][1]

    @property
    def uses_key(self) -> bool:
        """是否需要保存密钥。"""
        return self is not AuthType.OAUTH


_AUTH_LABELS = {
    AuthType.OAUTH: ("订阅登录", "account_circle"),
    AuthType.API_KEY: ("API Key", "key"),
    AuthType.RELAY: ("中转 / 自定义端点", "hub"),
}


class AccountStatus(enum.Enum):
    """账号状态。"""

    ACTIVE = "active"
    LIMITED = "limited"
    EXPIRED = "expired"
    DISABLED = "disabled"

    @property
    def label(self) -> str:
        """界面显示名称。"""
        return _STATUS_STYLES[self][0]

    @property
    def icon(self) -> str:
        """状态图标。"""
        return _STATUS_STYLES[self][1]

    @property
    def color_role(self) -> str:
        """状态色的角色前缀（``success`` → ``success_container`` 等）。"""
        return _STATUS_STYLES[self][2]


_STATUS_STYLES = {
    AccountStatus.ACTIVE: ("正常", "check_circle", "success"),
    AccountStatus.LIMITED: ("受限", "speed", "warning"),
    AccountStatus.EXPIRED: ("已过期", "error", "error"),
    AccountStatus.DISABLED: ("已停用", "block", "surface"),
}


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _coerce_enum(kind: type[enum.Enum], value: Any, default: enum.Enum):
    try:
        return kind(value)
    except ValueError:
        return default


SECRET_ENV_WORDS = ("TOKEN", "KEY", "SECRET", "HEADER")


def is_secret_env_key(key: str) -> bool:
    """环境变量名是否像是密钥（加密保存、导出时默认不含）。"""
    upper = key.upper()
    return any(word in upper for word in SECRET_ENV_WORDS)


def mask_secret(value: str) -> str:
    """掩码后的密钥，例如 ``sk-ant-…a1b2``；过短时全部掩码。"""
    value = value.strip()
    if not value:
        return ""
    if len(value) <= 10:
        return "•" * len(value)
    return f"{value[:7]}…{value[-4:]}"


@dataclasses.dataclass
class Account:
    """一个 Claude 账号。

    Attributes:
        id: 唯一标识。
        name: 显示名称。
        email: 登录邮箱。
        plan: 套餐。
        auth_type: 认证方式。
        status: 状态。
        api_key: API Key 或中转令牌（仅保存在本机）。
        base_url: 自定义 API 端点（中转账号使用）。
        organization: 所属组织。
        tags: 标签。
        notes: 备注。
        monthly_budget: 月度预算（美元），0 表示不限。
        favorite: 是否收藏（排序靠前）。
        link_local: 是否把本机 Claude Code 日志中的用量归属到该账号。
        created_at: 创建时间（ISO 8601）。
        updated_at: 最近修改时间（ISO 8601）。
        last_used_at: 最近被设为当前账号的时间（ISO 8601）。
        claude_uuid: Claude 账号 UUID（Claude Code 与 Desktop 通用），用于
            识别客户端当前登录的是哪个账号。
        org_uuid: 组织 UUID，用于匹配 Desktop 的额度采样。
        env: API / 中转账号切换时额外写入的环境变量（如模型映射）。
        quota: 最近一次获取的额度快照（``quota.Quota.to_dict()``）。
    """

    id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    email: str = ""
    plan: Plan = Plan.PRO
    auth_type: AuthType = AuthType.OAUTH
    status: AccountStatus = AccountStatus.ACTIVE
    api_key: str = ""
    base_url: str = ""
    organization: str = ""
    tags: list[str] = dataclasses.field(default_factory=list)
    notes: str = ""
    monthly_budget: float = 0.0
    favorite: bool = False
    link_local: bool = False
    created_at: str = dataclasses.field(default_factory=_now_iso)
    updated_at: str = dataclasses.field(default_factory=_now_iso)
    last_used_at: str | None = None
    claude_uuid: str = ""
    org_uuid: str = ""
    env: dict[str, str] = dataclasses.field(default_factory=dict)
    quota: dict[str, Any] | None = None

    @property
    def display_name(self) -> str:
        """名称为空时回退到邮箱。"""
        return self.name or self.email or "未命名账号"

    def masked_key(self) -> str:
        """掩码后的密钥，例如 ``sk-ant-…a1b2``。"""
        return mask_secret(self.api_key)

    def to_dict(self, include_secret: bool = True) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        data = dataclasses.asdict(self)
        data["plan"] = self.plan.value
        data["auth_type"] = self.auth_type.value
        data["status"] = self.status.value
        if not include_secret:
            data["api_key"] = ""
            data["env"] = {
                key: value
                for key, value in self.env.items()
                if not is_secret_env_key(key)
            }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Account:
        """从字典恢复；未知字段忽略，缺失字段取默认值。"""
        names = {field.name for field in dataclasses.fields(cls)}
        values = {key: data[key] for key in names if key in data}
        values["plan"] = _coerce_enum(Plan, values.get("plan"), Plan.PRO)
        values["auth_type"] = _coerce_enum(
            AuthType, values.get("auth_type"), AuthType.OAUTH
        )
        values["status"] = _coerce_enum(
            AccountStatus, values.get("status"), AccountStatus.ACTIVE
        )
        values["tags"] = [str(tag) for tag in values.get("tags") or []]
        values["monthly_budget"] = float(values.get("monthly_budget") or 0.0)
        env = values.get("env")
        values["env"] = (
            {str(k): str(v) for k, v in env.items()}
            if isinstance(env, dict)
            else {}
        )
        if not isinstance(values.get("quota"), dict):
            values["quota"] = None
        for key in ("claude_uuid", "org_uuid"):
            values[key] = str(values.get(key) or "")
        if not values.get("id"):
            values["id"] = uuid.uuid4().hex
        return cls(**values)

    def touch(self) -> None:
        """刷新修改时间。"""
        self.updated_at = _now_iso()


@dataclasses.dataclass(frozen=True, slots=True)
class UsageRecord:
    """一条（或一组聚合的）API 请求用量。

    Attributes:
        timestamp: 请求时间（带时区的本地时间）。
        model: 模型 ID。
        input_tokens: 未命中缓存的输入 token。
        output_tokens: 输出 token。
        cache_write_5m: 写入 5 分钟缓存的 token。
        cache_write_1h: 写入 1 小时缓存的 token。
        cache_read: 命中缓存读取的 token。
        account_id: 归属账号，None 表示未归属。
        project: 项目名称（工作目录名）。
        session_id: 会话标识。
        requests: 该记录代表的请求次数（演示数据按小时聚合）。
    """

    timestamp: dt.datetime
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0
    cache_read: int = 0
    account_id: str | None = None
    project: str = ""
    session_id: str = ""
    requests: int = 1

    @property
    def cache_write(self) -> int:
        """缓存写入 token 合计。"""
        return self.cache_write_5m + self.cache_write_1h

    @property
    def total_input(self) -> int:
        """输入侧 token 合计（含缓存写入与读取）。"""
        return self.input_tokens + self.cache_write + self.cache_read

    @property
    def total_tokens(self) -> int:
        """全部 token。"""
        return self.total_input + self.output_tokens

    @property
    def day(self) -> dt.date:
        """所在的本地日期。"""
        return self.timestamp.date()

    def with_account(self, account_id: str | None) -> UsageRecord:
        """返回归属到指定账号的副本。"""
        return dataclasses.replace(self, account_id=account_id)


class DataSource(enum.Enum):
    """用量数据来源。"""

    LOCAL = "local"
    DEMO = "demo"

    @property
    def label(self) -> str:
        """界面显示名称。"""
        return "本机 Claude Code 日志" if self is DataSource.LOCAL else "演示数据"


@dataclasses.dataclass
class CustomPrice:
    """用户自定义的模型单价（美元 / 百万 token）。"""

    input: float
    output: float
    cache_read: float | None = None

    def to_list(self) -> list[float | None]:
        """序列化为列表。"""
        return [self.input, self.output, self.cache_read]


@dataclasses.dataclass
class Settings:
    """应用设置。

    Attributes:
        data_source: 用量数据来源。
        projects_dir: 自定义 Claude Code 日志目录，空字符串使用默认位置。
        dark: 是否使用暗色主题。
        seed: 主题种子色。
        active_account_id: 当前使用中的账号。
        custom_prices: 用户覆盖的模型单价。
        first_run: 是否尚未完成首次启动引导。
        quota_online: 是否允许用保存的登录令牌联网查询额度。
        proxy: 联网查询使用的代理（空字符串表示系统代理）。
        switch_desktop: 一键切换时是否同时切换 Claude Desktop。
        relaunch_desktop: 切换 Desktop 后是否自动重新启动它。
        desktop_account_id: Claude Desktop 当前会话所属的账号。
    """

    data_source: DataSource = DataSource.LOCAL
    projects_dir: str = ""
    dark: bool = False
    seed: str = "#D97757"
    active_account_id: str | None = None
    custom_prices: dict[str, CustomPrice] = dataclasses.field(
        default_factory=dict
    )
    first_run: bool = True
    quota_online: bool = True
    proxy: str = ""
    switch_desktop: bool = True
    relaunch_desktop: bool = True
    desktop_account_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "data_source": self.data_source.value,
            "projects_dir": self.projects_dir,
            "dark": self.dark,
            "seed": self.seed,
            "active_account_id": self.active_account_id,
            "custom_prices": {
                model: price.to_list()
                for model, price in sorted(self.custom_prices.items())
            },
            "first_run": self.first_run,
            "quota_online": self.quota_online,
            "proxy": self.proxy,
            "switch_desktop": self.switch_desktop,
            "relaunch_desktop": self.relaunch_desktop,
            "desktop_account_id": self.desktop_account_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        """从字典恢复，忽略格式错误的字段。"""
        settings = cls()
        settings.data_source = _coerce_enum(
            DataSource, data.get("data_source"), DataSource.LOCAL
        )
        settings.projects_dir = str(data.get("projects_dir") or "")
        settings.dark = bool(data.get("dark", False))
        seed = data.get("seed")
        if isinstance(seed, str) and seed.startswith("#"):
            settings.seed = seed
        active = data.get("active_account_id")
        settings.active_account_id = active if isinstance(active, str) else None
        prices = data.get("custom_prices") or {}
        if isinstance(prices, dict):
            for model, values in prices.items():
                price = _parse_price(values)
                if price is not None:
                    settings.custom_prices[str(model)] = price
        settings.first_run = bool(data.get("first_run", False))
        for key in ("quota_online", "switch_desktop", "relaunch_desktop"):
            setattr(settings, key, bool(data.get(key, True)))
        settings.proxy = str(data.get("proxy") or "")
        desktop = data.get("desktop_account_id")
        settings.desktop_account_id = (
            desktop if isinstance(desktop, str) else None
        )
        return settings


def _parse_price(values: Any) -> CustomPrice | None:
    if not isinstance(values, list | tuple) or len(values) < 2:
        return None
    try:
        cache_read = (
            float(values[2])
            if len(values) > 2 and values[2] is not None
            else None
        )
        return CustomPrice(float(values[0]), float(values[1]), cache_read)
    except (TypeError, ValueError):
        return None
