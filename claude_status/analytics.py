"""用量统计：按日期、模型、账号、项目与时段聚合。

``Dataset`` 在构造时为每条记录计算一次费用，之后的筛选与聚合都复用
这些结果；所有聚合函数都是纯函数，便于测试。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Iterable
from collections.abc import Sequence
import dataclasses
import datetime as dt
import enum

from claude_status import models
from claude_status import pricing


class Metric(enum.Enum):
    """统计指标。"""

    TOKENS = "tokens"
    REQUESTS = "requests"
    COST = "cost"

    @property
    def label(self) -> str:
        """界面显示名称。"""
        return {"tokens": "Token", "requests": "请求", "cost": "费用"}[
            self.value
        ]

    def of(self, totals: Totals) -> float:
        """从合计中取出该指标的值。"""
        if self is Metric.TOKENS:
            return float(totals.total_tokens)
        if self is Metric.REQUESTS:
            return float(totals.requests)
        return totals.cost


@dataclasses.dataclass
class Totals:
    """一组记录的合计。

    Attributes:
        input_tokens: 未命中缓存的输入 token。
        output_tokens: 输出 token。
        cache_write: 缓存写入 token。
        cache_read: 缓存读取 token。
        requests: 请求次数。
        cost: 可计价部分的估算费用（美元）。
        unpriced_tokens: 没有单价的模型产生的 token。
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_write: int = 0
    cache_read: int = 0
    requests: int = 0
    cost: float = 0.0
    unpriced_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """全部 token。"""
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_write
            + self.cache_read
        )

    @property
    def cache_hit_rate(self) -> float:
        """输入侧的缓存命中率（缓存读取 / 全部输入）。"""
        total_input = self.input_tokens + self.cache_write + self.cache_read
        return self.cache_read / total_input if total_input else 0.0

    @property
    def priced(self) -> bool:
        """是否至少有一部分用量可以计价。"""
        return self.total_tokens > self.unpriced_tokens

    def merge(self, other: Totals) -> None:
        """累加另一组合计。"""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_write += other.cache_write
        self.cache_read += other.cache_read
        self.requests += other.requests
        self.cost += other.cost
        self.unpriced_tokens += other.unpriced_tokens

    def add(self, record: models.UsageRecord, cost: float | None) -> None:
        """累加一条记录。"""
        self.input_tokens += record.input_tokens
        self.output_tokens += record.output_tokens
        self.cache_write += record.cache_write
        self.cache_read += record.cache_read
        self.requests += record.requests
        if cost is None:
            self.unpriced_tokens += record.total_tokens
        else:
            self.cost += cost


@dataclasses.dataclass
class DayStat:
    """某一天的合计。"""

    day: dt.date
    totals: Totals


@dataclasses.dataclass
class GroupStat:
    """某个分组（模型 / 项目 / 账号）的合计。"""

    key: str | None
    totals: Totals


def relative_change(current: float, previous: float) -> float | None:
    """相对变化率；上期为 0 时无法计算，返回 None。"""
    if previous == 0:
        return None
    return (current - previous) / previous


@dataclasses.dataclass
class Comparison:
    """当前区间与上一个等长区间的对比。"""

    current: Totals
    previous: Totals
    active_days: int
    previous_active_days: int
    days: int

    def delta(self, metric: Callable[[Totals], float]) -> float | None:
        """某个指标的相对变化率。"""
        return relative_change(metric(self.current), metric(self.previous))

    @property
    def daily_average(self) -> float:
        """区间内日均 token。"""
        return self.current.total_tokens / max(1, self.days)


class Dataset:
    """带费用的用量记录集合。

    Args:
        records: 用量记录。
        book: 价格表。
    """

    def __init__(
        self,
        records: Sequence[models.UsageRecord],
        book: pricing.PriceBook | None = None,
        costs: Sequence[float | None] | None = None,
    ) -> None:
        self.records = list(records)
        if costs is None:
            book = book or pricing.PriceBook()
            costs = [book.cost(record) for record in self.records]
        self.costs = list(costs)

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(zip(self.records, self.costs, strict=True))

    # ---- 筛选 -------------------------------------------------------------

    def filter(
        self,
        start: dt.date | None = None,
        end: dt.date | None = None,
        account_ids: Iterable[str | None] | None = None,
        predicate: Callable[[models.UsageRecord], bool] | None = None,
    ) -> Dataset:
        """按日期闭区间、账号与自定义条件筛选。"""
        accounts = set(account_ids) if account_ids is not None else None
        records: list[models.UsageRecord] = []
        costs: list[float | None] = []
        for record, cost in self:
            day = record.day
            if start is not None and day < start:
                continue
            if end is not None and day > end:
                continue
            if accounts is not None and record.account_id not in accounts:
                continue
            if predicate is not None and not predicate(record):
                continue
            records.append(record)
            costs.append(cost)
        return Dataset(records, costs=costs)

    def date_span(self) -> tuple[dt.date, dt.date] | None:
        """最早与最晚的日期。"""
        if not self.records:
            return None
        days = [record.day for record in self.records]
        return min(days), max(days)

    # ---- 聚合 -------------------------------------------------------------

    def totals(self) -> Totals:
        """全部合计。"""
        totals = Totals()
        for record, cost in self:
            totals.add(record, cost)
        return totals

    def _group(
        self, key: Callable[[models.UsageRecord], str | None]
    ) -> list[GroupStat]:
        groups: dict[str | None, Totals] = {}
        for record, cost in self:
            groups.setdefault(key(record), Totals()).add(record, cost)
        return sorted(
            (GroupStat(name, totals) for name, totals in groups.items()),
            key=lambda group: group.totals.total_tokens,
            reverse=True,
        )

    def by_model(self) -> list[GroupStat]:
        """按模型分组，按 token 降序。"""
        return self._group(lambda record: record.model)

    def by_family(self) -> list[GroupStat]:
        """按模型系列（Opus / Sonnet / …）分组。"""
        return self._group(lambda record: pricing.model_family(record.model))

    def by_project(self) -> list[GroupStat]:
        """按项目分组。"""
        return self._group(lambda record: record.project or "（未知项目）")

    def by_source(self) -> list[GroupStat]:
        """按请求来源分组（key 为 ``UsageSource`` 的值，空字符串为未知）。"""
        return self._group(lambda record: record.source)

    def by_account(self) -> list[GroupStat]:
        """按账号分组（key 为账号 ID，None 表示未归属）。"""
        return self._group(lambda record: record.account_id)

    def daily(self, start: dt.date, end: dt.date) -> list[DayStat]:
        """``start`` 到 ``end``（含）的逐日合计，没有用量的日期补零。"""
        buckets: dict[dt.date, Totals] = {}
        for record, cost in self:
            day = record.day
            if start <= day <= end:
                buckets.setdefault(day, Totals()).add(record, cost)
        span = max(0, (end - start).days + 1)
        days = (start + dt.timedelta(days=i) for i in range(span))
        return [DayStat(day, buckets.get(day, Totals())) for day in days]

    def daily_map(self, metric: Metric) -> dict[dt.date, float]:
        """日期 → 指标值（只包含有用量的日期）。"""
        buckets: dict[dt.date, Totals] = {}
        for record, cost in self:
            buckets.setdefault(record.day, Totals()).add(record, cost)
        return {day: metric.of(totals) for day, totals in buckets.items()}

    def weekday_hour(self, metric: Metric) -> list[list[float]]:
        """7 × 24 矩阵：行为周一至周日，列为 0–23 时。"""
        cells = [[Totals() for _ in range(24)] for _ in range(7)]
        for record, cost in self:
            stamp = record.timestamp
            cells[stamp.weekday()][stamp.hour].add(record, cost)
        return [[metric.of(cell) for cell in row] for row in cells]

    def monthly_by_account(
        self, months: Sequence[tuple[int, int]], metric: Metric
    ) -> dict[str | None, list[float]]:
        """账号 → 每个月的指标值（``months`` 为 (年, 月) 列表）。"""
        index = {month: i for i, month in enumerate(months)}
        grid: dict[str | None, list[Totals]] = {}
        for record, cost in self:
            stamp = record.timestamp
            position = index.get((stamp.year, stamp.month))
            if position is None:
                continue
            row = grid.setdefault(
                record.account_id, [Totals() for _ in months]
            )
            row[position].add(record, cost)
        return {
            account: [metric.of(cell) for cell in row]
            for account, row in grid.items()
        }


def compare(
    dataset: Dataset, start: dt.date, end: dt.date
) -> Comparison:
    """统计 [start, end] 并与之前等长的区间对比。"""
    days = (end - start).days + 1
    previous_end = start - dt.timedelta(days=1)
    previous_start = previous_end - dt.timedelta(days=days - 1)
    current = dataset.filter(start, end)
    previous = dataset.filter(previous_start, previous_end)
    return Comparison(
        current=current.totals(),
        previous=previous.totals(),
        active_days=len({record.day for record in current.records}),
        previous_active_days=len({record.day for record in previous.records}),
        days=days,
    )


@dataclasses.dataclass
class Activity:
    """活跃度摘要（热力图旁的统计）。

    Attributes:
        active_days: 有用量的天数。
        total_days: 区间天数。
        current_streak: 截至最后一天的连续活跃天数（最后一天尚无用量时
            从前一天开始计算）。
        longest_streak: 最长连续活跃天数。
        longest_start: 最长连续区间的开始日期。
        busiest_day: 指标最高的一天。
        busiest_value: 最高一天的指标值。
    """

    active_days: int = 0
    total_days: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    longest_start: dt.date | None = None
    busiest_day: dt.date | None = None
    busiest_value: float = 0.0


def activity(
    values: dict[dt.date, float], start: dt.date, end: dt.date
) -> Activity:
    """由逐日指标计算连续活跃天数等摘要。"""
    result = Activity(total_days=max(0, (end - start).days + 1))
    run = 0
    run_start: dt.date | None = None
    day = start
    while day <= end:
        value = values.get(day, 0.0)
        if value > 0:
            result.active_days += 1
            if run == 0:
                run_start = day
            run += 1
            if run > result.longest_streak:
                result.longest_streak = run
                result.longest_start = run_start
            if value > result.busiest_value:
                result.busiest_value = value
                result.busiest_day = day
        else:
            run = 0
        day += dt.timedelta(days=1)
    streak = 0
    cursor = end
    if values.get(cursor, 0.0) <= 0:
        cursor -= dt.timedelta(days=1)
    while cursor >= start and values.get(cursor, 0.0) > 0:
        streak += 1
        cursor -= dt.timedelta(days=1)
    result.current_streak = streak
    return result


def level_thresholds(values: Iterable[float], levels: int = 4) -> list[float]:
    """把非零值按分位数分成 ``levels`` 档，返回每档的下限（升序）。

    与 GitHub 贡献图一致：0 为单独一档，其余按分位数分档，避免个别峰值
    让其他日期都挤在最浅的颜色里。
    """
    positive = sorted(value for value in values if value > 0)
    if not positive:
        return []
    thresholds = []
    for level in range(levels):
        index = int(len(positive) * level / levels)
        thresholds.append(positive[min(index, len(positive) - 1)])
    return thresholds


def level_of(value: float, thresholds: Sequence[float]) -> int:
    """数值所在的档位：0 表示无用量，1…len(thresholds) 依次加深。"""
    if value <= 0 or not thresholds:
        return 0
    level = 1
    for index, threshold in enumerate(thresholds):
        if value >= threshold:
            level = index + 1
    return level


def bucket_weekly(days: Sequence[DayStat]) -> list[DayStat]:
    """把逐日合计按周（周一开始）汇总，``day`` 为该周周一。"""
    weeks: dict[dt.date, Totals] = {}
    for stat in days:
        monday = stat.day - dt.timedelta(days=stat.day.weekday())
        weeks.setdefault(monday, Totals()).merge(stat.totals)
    return [DayStat(day, totals) for day, totals in sorted(weeks.items())]


def month_sequence(end: dt.date, count: int) -> list[tuple[int, int]]:
    """截至 ``end`` 所在月份的最近 ``count`` 个 (年, 月)，按时间升序。"""
    year, month = end.year, end.month
    months = []
    for _ in range(count):
        months.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(months))


def month_start(day: dt.date) -> dt.date:
    """所在月份的第一天。"""
    return day.replace(day=1)
