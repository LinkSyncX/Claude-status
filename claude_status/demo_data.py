"""演示数据：示例账号与逼真的用量记录。

用量按账号套餐决定强度与模型组合，叠加工作日 / 时段节律、长期增长
趋势与随机波动；同一账号在同一天生成的数据是确定的（以账号 ID 作为
随机种子），因此每次刷新看到的图表一致。
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import math
import random

from claude_status import models
from claude_status import quota

# 每个套餐的日均 token 基线与模型权重。
_PROFILES: dict[models.Plan, tuple[float, dict[str, float]]] = {
    models.Plan.FREE: (
        0.4e6,
        {"claude-sonnet-5": 0.9, "claude-haiku-4-5": 0.1},
    ),
    models.Plan.PRO: (
        6e6,
        {"claude-sonnet-5": 0.6, "claude-opus-5": 0.3, "claude-haiku-4-5": 0.1},
    ),
    models.Plan.MAX_5X: (
        22e6,
        {
            "claude-opus-5": 0.55,
            "claude-sonnet-5": 0.4,
            "claude-haiku-4-5": 0.05,
        },
    ),
    models.Plan.MAX_20X: (
        60e6,
        {
            "claude-opus-5": 0.5,
            "claude-fable-5-1": 0.15,
            "claude-sonnet-5": 0.3,
            "claude-haiku-4-5": 0.05,
        },
    ),
    models.Plan.TEAM: (
        14e6,
        {
            "claude-sonnet-5": 0.55,
            "claude-opus-5": 0.35,
            "claude-haiku-4-5": 0.1,
        },
    ),
    models.Plan.ENTERPRISE: (
        30e6,
        {
            "claude-opus-5": 0.45,
            "claude-sonnet-5": 0.45,
            "claude-haiku-4-5": 0.1,
        },
    ),
    models.Plan.API: (
        9e6,
        {
            "claude-sonnet-5": 0.5,
            "claude-haiku-4-5": 0.35,
            "claude-opus-5": 0.15,
        },
    ),
}

_PROJECTS = (
    "web-console",
    "api-gateway",
    "data-pipeline",
    "mobile-app",
    "docs-site",
    "infra-terraform",
    "ml-research",
    "claude-status",
    "billing-service",
    "design-system",
)

# 一天 24 小时的相对活跃度：上午与下午两个高峰，晚间有少量加班。
_HOURLY = (
    0.05, 0.02, 0.01, 0.01, 0.01, 0.02, 0.05, 0.15,
    0.45, 0.85, 1.00, 0.90, 0.40, 0.65, 0.95, 1.00,
    0.90, 0.70, 0.35, 0.30, 0.45, 0.50, 0.35, 0.15,
)  # fmt: skip
_WEEKDAY = (1.0, 1.05, 1.0, 0.95, 0.85, 0.35, 0.25)

# token 构成：Claude Code 的请求绝大部分是缓存读取。
_SPLIT = {
    "input_tokens": 0.015,
    "output_tokens": 0.03,
    "cache_write_5m": 0.045,
    "cache_write_1h": 0.02,
    "cache_read": 0.89,
}
_TOKENS_PER_REQUEST = 55_000


def _ago(**delta: float) -> str:
    moment = dt.datetime.now().astimezone() - dt.timedelta(**delta)
    return moment.isoformat(timespec="seconds")


def sample_accounts() -> list[models.Account]:
    """一组覆盖各种套餐、认证方式与状态的示例账号（邮箱均为 example.com）。"""
    return [
        models.Account(
            name="工作主力号",
            email="dev.lead@example.com",
            plan=models.Plan.MAX_20X,
            organization="Acme 研发中心",
            tags=["工作", "主力"],
            favorite=True,
            notes="日常开发主要使用，Claude Code 常驻登录。",
            last_used_at=_ago(minutes=4),
        ),
        models.Account(
            name="个人 Pro",
            email="me@example.com",
            plan=models.Plan.PRO,
            tags=["个人"],
            notes="周末写个人项目。",
            last_used_at=_ago(days=2, hours=3),
        ),
        models.Account(
            name="API 生产环境",
            email="ops@example.com",
            plan=models.Plan.API,
            auth_type=models.AuthType.API_KEY,
            api_key="sk-ant-api03-DEMO-0000000000000000000000",
            organization="Acme Inc.",
            monthly_budget=800.0,
            tags=["生产", "API"],
            last_used_at=_ago(hours=5),
        ),
        models.Account(
            name="团队席位",
            email="alice@example.com",
            plan=models.Plan.TEAM,
            organization="Acme Inc.",
            tags=["团队"],
            last_used_at=_ago(days=1, hours=2),
        ),
        models.Account(
            name="中转备用线路",
            plan=models.Plan.API,
            auth_type=models.AuthType.RELAY,
            base_url="https://relay.example.com/v1",
            api_key="relay-DEMO-token-0000000000",
            status=models.AccountStatus.LIMITED,
            monthly_budget=60.0,
            tags=["备用"],
            notes="高峰期偶尔触发限流。",
            last_used_at=_ago(days=6),
        ),
        models.Account(
            name="旧试用号",
            email="trial@example.com",
            plan=models.Plan.FREE,
            status=models.AccountStatus.EXPIRED,
            tags=["试用"],
            last_used_at=_ago(days=74),
        ),
    ]


def _pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), list(weights.values()))[0]


def _active_until(account: models.Account, today: dt.date) -> dt.date:
    """过期 / 停用账号在一段时间之前就不再产生用量。"""
    rng = random.Random(f"end-{account.id}")
    if account.status is models.AccountStatus.EXPIRED:
        return today - dt.timedelta(days=rng.randint(45, 120))
    if account.status is models.AccountStatus.DISABLED:
        return today - dt.timedelta(days=rng.randint(90, 200))
    return today


def generate(
    accounts: list[models.Account],
    days: int = 365,
    today: dt.date | None = None,
    now: dt.datetime | None = None,
) -> list[models.UsageRecord]:
    """为每个账号生成过去 ``days`` 天的按小时聚合的用量记录。

    Args:
        accounts: 账号列表。
        days: 生成的天数。
        today: 最后一天，默认今天。
        now: 当前时刻（今天只生成到该小时），默认系统时间。
    """
    now = now or dt.datetime.now().astimezone()
    today = today or now.date()
    tz = now.tzinfo
    records: list[models.UsageRecord] = []
    for account in accounts:
        baseline, mix = _PROFILES[account.plan]
        rng = random.Random(f"demo-{account.id}")
        projects = rng.sample(_PROJECTS, k=rng.randint(3, 5))
        project_weights = {name: rng.uniform(0.3, 1.0) for name in projects}
        last_day = _active_until(account, today)
        # 账号在第一年里逐渐被更多地使用。
        start_offset = rng.randint(0, days // 8)
        for offset in range(days - start_offset, -1, -1):
            day = today - dt.timedelta(days=offset)
            if day > last_day:
                break
            weekday = day.weekday()
            idle = 0.12 if weekday < 5 else 0.45
            if rng.random() < idle:
                continue
            progress = 1.0 - offset / max(1, days)
            trend = 0.45 + 0.85 * progress
            burst = rng.lognormvariate(0.0, 0.55)
            day_tokens = baseline * _WEEKDAY[weekday] * trend * burst
            limited = account.status is models.AccountStatus.LIMITED
            if limited and rng.random() < 0.1:
                day_tokens *= 2.5
            # 今天只生成到当前小时，并按已过去时段的活跃度比例缩减用量。
            last_hour = now.hour if day == now.date() else 23
            if last_hour < 23:
                elapsed = sum(_HOURLY[: last_hour + 1]) / sum(_HOURLY)
                day_tokens *= elapsed
            records.extend(
                _day_records(
                    rng,
                    account,
                    day,
                    day_tokens,
                    mix,
                    project_weights,
                    tz,
                    last_hour,
                )
            )
    records.sort(key=lambda record: record.timestamp)
    return records


def _day_records(
    rng: random.Random,
    account: models.Account,
    day: dt.date,
    day_tokens: float,
    mix: dict[str, float],
    projects: dict[str, float],
    tz: dt.tzinfo | None,
    last_hour: int = 23,
) -> list[models.UsageRecord]:
    hours = [
        hour
        for hour in range(last_hour + 1)
        if rng.random() < _HOURLY[hour] * 0.9 + 0.02
    ] or [min(last_hour, rng.choice((10, 14, 16)))]
    weights = [_HOURLY[hour] + 0.05 for hour in hours]
    scale = day_tokens / sum(weights)
    result: list[models.UsageRecord] = []
    for hour, weight in zip(hours, weights, strict=True):
        tokens = scale * weight * rng.uniform(0.6, 1.4)
        model = _pick(rng, mix)
        split = {
            key: int(tokens * share * rng.uniform(0.8, 1.2))
            for key, share in _SPLIT.items()
        }
        result.append(
            models.UsageRecord(
                timestamp=dt.datetime(
                    day.year,
                    day.month,
                    day.day,
                    hour,
                    rng.randint(0, 59),
                    tzinfo=tz,
                ),
                model=model,
                account_id=account.id,
                project=_pick(rng, projects),
                session_id=f"demo-{account.id[:6]}-{day.isoformat()}",
                requests=max(1, math.ceil(tokens / _TOKENS_PER_REQUEST)),
                **split,
            )
        )
    return result


def sample_quota(
    account: models.Account, now: dt.datetime | None = None
) -> quota.Quota | None:
    """演示用的额度（订阅账号才有；同一账号的数值稳定）。"""
    if account.auth_type is not models.AuthType.OAUTH:
        return None
    now = now or dt.datetime.now().astimezone()
    rng = random.Random(f"quota-{account.id}")
    if account.status is models.AccountStatus.EXPIRED:
        return None
    heavy = account.status is models.AccountStatus.LIMITED
    five = rng.uniform(70, 99) if heavy else rng.uniform(3, 85)
    week = rng.uniform(40, 95) if heavy else rng.uniform(10, 75)
    five_reset = now + dt.timedelta(minutes=rng.randint(12, 290))
    week_reset = (now + dt.timedelta(days=rng.randint(1, 6))).replace(
        minute=0, second=0, microsecond=0
    )
    return quota.Quota(
        now - dt.timedelta(minutes=rng.randint(1, 20)),
        quota.Source.DEMO,
        quota.Window(round(five), five_reset),
        quota.Window(round(week), week_reset),
    )


def attribute(
    records: list[models.UsageRecord], account_id: str | None
) -> list[models.UsageRecord]:
    """把一组记录归属到指定账号（本机日志使用）。"""
    return [
        dataclasses.replace(record, account_id=account_id)
        for record in records
    ]
