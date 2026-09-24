"""数据统计页：关键指标、用量趋势、模型 / 账号 / 项目分布与模型明细。"""

from __future__ import annotations

from collections.abc import Callable
import datetime as dt

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import charts
from md3.components import data_table
from md3.components import feedback
from md3.components import text_fields
from md3.tokens import spacing

from claude_status import analytics
from claude_status import formatting
from claude_status import models
from claude_status import pricing
from claude_status import state as state_module
from claude_status.widgets import common
from claude_status.widgets import dense_charts
from claude_status.widgets import stat_card

RANGES: list[tuple[str, int | None]] = [
    ("7 天", 7),
    ("30 天", 30),
    ("90 天", 90),
    ("1 年", 365),
    ("全部", None),
]
METRICS = [
    analytics.Metric.TOKENS,
    analytics.Metric.COST,
    analytics.Metric.REQUESTS,
]
WEEKLY_THRESHOLD_DAYS = 120
TOP_MODELS = 6
TOP_PROJECTS = 8
# 紧凑数据表的表头、行与页脚高度（与 md3 item_views 保持一致）。
TABLE_HEADER, TABLE_ROW, TABLE_FOOTER = 46, 40, 58

# 横幅：(键, 文字, 图标, [(按钮文字, 目标页面)])。
BannerSpec = tuple[str, str, str, list[tuple[str, str]]]

_FORMATTERS: dict[analytics.Metric, Callable[[float], str]] = {
    analytics.Metric.TOKENS: formatting.tokens,
    analytics.Metric.COST: formatting.money,
    analytics.Metric.REQUESTS: formatting.count,
}


def metric_formatter(metric: analytics.Metric) -> Callable[[float], str]:
    """指标对应的数值格式化函数。"""
    return _FORMATTERS[metric]


def _leave_label_room(
    chart: charts.CartesianChart, values: list[float]
) -> None:
    """横向柱状图的数值标签画在柱子末端，给数值轴留出 20% 余量。"""
    peak = max(values, default=0.0)
    chart.set_y_range(0, peak * 1.2 if peak > 0 else None)


class AccountFilter(text_fields.SelectField):
    """"全部账号 / 某个账号 / 未归属"下拉框，``account_ids`` 给出筛选条件。"""

    def __init__(self, state: state_module.AppState) -> None:
        super().__init__("账号", [], 0)
        self._state = state
        self._keys: list[str | None] = []
        self.setFixedWidth(176)
        self.sync()

    def sync(self) -> None:
        """账号列表变化后重建选项，尽量保留当前选择。"""
        current = self.current_key()
        keys: list[str | None] = ["*"]
        labels = ["全部账号"]
        for account in self._state.accounts:
            keys.append(account.id)
            labels.append(account.display_name)
        if any(r.account_id is None for r in self._state.dataset.records):
            keys.append(None)
            labels.append("未归属")
        self._keys = keys
        self.blockSignals(True)
        self.set_options(labels, keep_selection=False)
        index = keys.index(current) if current in keys else 0
        self.set_selected_index(index)
        self.blockSignals(False)

    def current_key(self) -> str | None:
        """当前选项的键：``"*"`` 为全部，None 为未归属。"""
        index = self.selected_index
        if 0 <= index < len(self._keys):
            return self._keys[index]
        return "*"

    def account_ids(self) -> list[str | None] | None:
        """筛选用的账号 ID 列表；None 表示不筛选。"""
        key = self.current_key()
        return None if key == "*" else [key]


class DashboardPage(common.Page):
    """数据统计页。

    Args:
        state: 应用状态。
        parent: 父控件。
    """

    navigate_requested = QtCore.Signal(str)

    def __init__(
        self,
        state: state_module.AppState,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._banner_slot = QtWidgets.QVBoxLayout()
        self._banner_slot.setContentsMargins(0, 0, 0, 0)
        self.body.addLayout(self._banner_slot)
        self._banner: feedback.Banner | None = None
        self._banner_key: str | None = None
        self._build_controls()
        self._build_kpis()
        self._build_charts()
        self._build_table()
        state.records_changed.connect(self._on_data_changed)
        state.accounts_changed.connect(self._on_data_changed)
        state.settings_changed.connect(self._update_banner)
        self._on_data_changed()

    # ---- 构建 -------------------------------------------------------------

    def _build_controls(self) -> None:
        self._range = buttons.SegmentedButton(
            [label for label, _ in RANGES], selected=[1], show_check_icon=False
        )
        self._range.selection_changed.connect(lambda _i: self.refresh())
        self._metric = buttons.SegmentedButton(
            [
                buttons.Segment("Token", "token"),
                buttons.Segment("费用", "payments"),
                buttons.Segment("请求", "bolt"),
            ],
            selected=[0],
            show_check_icon=False,
        )
        self._metric.selection_changed.connect(lambda _i: self.refresh())
        self._accounts = AccountFilter(self._state)
        self._accounts.selection_changed.connect(lambda _i: self.refresh())
        self._span_label = common.ElidedLabel(
            "", "body-small", "on_surface_variant"
        )
        self.body.addLayout(
            common.row(
                self._range,
                self._metric,
                None,
                self._span_label,
                self._accounts,
                spacing_px=round(spacing.SPACE_3),
            )
        )

    def _build_kpis(self) -> None:
        self._kpi_tokens = stat_card.StatCard("总 Token", "token", "primary")
        self._kpi_cost = stat_card.StatCard(
            "估算费用", "payments", "tertiary", increase_is_good=False
        )
        self._kpi_requests = stat_card.StatCard("请求次数", "bolt", "secondary")
        self._kpi_cache = stat_card.StatCard("缓存命中率", "cached", "success")
        self._kpi_days = stat_card.StatCard(
            "活跃天数", "calendar_today", "primary"
        )
        self._kpi_average = stat_card.StatCard(
            "日均 Token", "trending_up", "tertiary"
        )
        grid = common.ResponsiveGrid(
            min_column_width=200, max_columns=6, balanced=True
        )
        grid.set_widgets(
            [
                self._kpi_tokens,
                self._kpi_cost,
                self._kpi_requests,
                self._kpi_cache,
                self._kpi_days,
                self._kpi_average,
            ]
        )
        self.body.addWidget(grid)

    def _chart_card(
        self, title: str, chart: QtWidgets.QWidget, height: int = 300
    ) -> common.SectionCard:
        card = common.SectionCard(title)
        chart.setMinimumHeight(height)
        card.add_widget(chart, 1)
        return card

    def _build_charts(self) -> None:
        self._trend = dense_charts.DenseBarChart(stacked=True)
        self._trend_card = self._chart_card("用量趋势", self._trend, 320)
        self.body.addWidget(self._trend_card)

        self._models = charts.PieChart(title="", center_label="合计")
        self._models_card = self._chart_card("模型分布", self._models)
        self._account_bars = charts.HorizontalBarChart(show_values=True)
        self._account_bars.set_show_legend(False)
        self._accounts_card = self._chart_card("用量分布", self._account_bars)
        self._group_by = buttons.SegmentedButton(
            ["按账号", "按来源"], selected=[0], show_check_icon=False
        )
        self._group_by.selection_changed.connect(lambda _i: self.refresh())
        self._accounts_card.add_header_widget(self._group_by)
        grid = common.ResponsiveGrid(min_column_width=420, max_columns=2)
        grid.set_widgets([self._models_card, self._accounts_card])
        self.body.addWidget(grid)

        self._projects = charts.HorizontalBarChart(show_values=True)
        self._projects.set_show_legend(False)
        self._projects_card = self._chart_card("项目排行", self._projects)
        self._composition = charts.PieChart(center_label="Token")
        self._composition.set_value_formatter(formatting.tokens)
        self._composition_card = self._chart_card(
            "Token 构成", self._composition
        )
        self._gauge = charts.GaugeChart(
            0,
            bands=[
                charts.GaugeBand(0, 40, "error"),
                charts.GaugeBand(40, 75, "tertiary"),
                charts.GaugeBand(75, 100, "primary"),
            ],
            label="缓存命中率 %",
        )
        self._gauge_card = self._chart_card("缓存效率", self._gauge)
        grid = common.ResponsiveGrid(min_column_width=320, max_columns=3)
        grid.set_widgets(
            [self._projects_card, self._composition_card, self._gauge_card]
        )
        self.body.addWidget(grid)

    def _build_table(self) -> None:
        card = common.SectionCard(
            "模型明细",
            "单价按 Anthropic 官方 API 价格估算；未知模型可在设置中自定义单价。",
        )
        numeric = [
            ("requests", "请求", formatting.count),
            ("input", "输入", formatting.tokens),
            ("output", "输出", formatting.tokens),
            ("write", "缓存写入", formatting.tokens),
            ("read", "缓存读取", formatting.tokens),
            ("total", "合计", formatting.tokens),
            ("cost", "估算费用", formatting.money),
            ("share", "占比", formatting.percent),
        ]
        self._table = data_table.DataTable(
            [data_table.Column("model", "模型", width=220)]
            + [
                data_table.Column(key, title, numeric=True, formatter=fmt)
                for key, title, fmt in numeric
            ],
            page_size=10,
            dense=True,
        )
        card.add_widget(self._table)
        self.body.addWidget(card)

    # ---- 数据 -------------------------------------------------------------

    def current_metric(self) -> analytics.Metric:
        """当前选中的指标。"""
        indices = self._metric.selected_indices
        return METRICS[indices[0]] if indices else analytics.Metric.TOKENS

    def current_span(self) -> tuple[dt.date, dt.date]:
        """当前时间范围（含首尾）。"""
        today = dt.date.today()
        indices = self._range.selected_indices
        days = RANGES[indices[0]][1] if indices else 30
        if days is not None:
            return today - dt.timedelta(days=days - 1), today
        span = self._state.dataset.date_span()
        start = span[0] if span else today - dt.timedelta(days=29)
        return min(start, today), today

    def _on_data_changed(self) -> None:
        self._accounts.sync()
        self._update_banner()
        self.refresh()

    def refresh(self) -> None:
        """按当前筛选条件重算全部指标与图表。"""
        start, end = self.current_span()
        account_ids = self._accounts.account_ids()
        scope = self._state.dataset.filter(account_ids=account_ids)
        current = scope.filter(start, end)
        comparison = analytics.compare(scope, start, end)
        metric = self.current_metric()
        self._span_label.setText(
            f"{formatting.date_short(start)} – {formatting.date_short(end)}"
            f" · {comparison.days} 天"
        )
        self._update_kpis(comparison)
        self._update_trend(current, start, end, metric)
        self._update_models(current, metric)
        self._update_accounts(current, metric)
        self._update_projects(current, metric)
        self._update_composition(comparison.current)
        self._update_table(current)

    def _update_kpis(self, comparison: analytics.Comparison) -> None:
        now, before = comparison.current, comparison.previous
        self._kpi_tokens.set_value(
            formatting.tokens(now.total_tokens),
            comparison.delta(lambda t: t.total_tokens),
            f"输出 {formatting.tokens(now.output_tokens)}",
        )
        unpriced = (
            f"另有 {formatting.tokens(now.unpriced_tokens)} 未计价"
            if now.unpriced_tokens
            else "按 API 价格估算"
        )
        self._kpi_cost.set_value(
            formatting.money(now.cost) if now.priced else "—",
            comparison.delta(lambda t: t.cost) if now.priced else "",
            unpriced,
        )
        self._kpi_requests.set_value(
            formatting.count(now.requests),
            comparison.delta(lambda t: t.requests),
        )
        previous_rate = before.cache_hit_rate if before.total_tokens else None
        change: float | None | str = ""
        if previous_rate:
            change = (now.cache_hit_rate - previous_rate) / previous_rate
        self._kpi_cache.set_value(
            formatting.percent(now.cache_hit_rate) if now.total_tokens else "—",
            change,
            f"读取 {formatting.tokens(now.cache_read)}",
        )
        self._kpi_days.set_value(
            f"{comparison.active_days}",
            analytics.relative_change(
                comparison.active_days, comparison.previous_active_days
            ),
            f"共 {comparison.days} 天",
        )
        self._kpi_average.set_value(
            formatting.tokens(comparison.daily_average),
            comparison.delta(lambda t: t.total_tokens),
            "活跃日均 "
            + formatting.tokens(
                now.total_tokens / max(1, comparison.active_days)
            ),
        )

    def _update_trend(
        self,
        current: analytics.Dataset,
        start: dt.date,
        end: dt.date,
        metric: analytics.Metric,
    ) -> None:
        weekly = (end - start).days + 1 > WEEKLY_THRESHOLD_DAYS
        families = [group.key for group in current.by_family()][:5]
        series = []
        categories: list[str] = []
        for family in families:
            subset = current.filter(
                predicate=lambda r, f=family: pricing.model_family(r.model) == f
            )
            days = subset.daily(start, end)
            if weekly:
                days = analytics.bucket_weekly(days)
            categories = [formatting.date_axis(d.day) for d in days]
            series.append(
                charts.Series(
                    family or "其他", [metric.of(d.totals) for d in days]
                )
            )
        if not series:
            days = current.daily(start, end)
            if weekly:
                days = analytics.bucket_weekly(days)
            categories = [formatting.date_axis(d.day) for d in days]
        self._trend.set_value_formatter(metric_formatter(metric))
        self._trend.set_data(categories, series)
        unit = "按周汇总" if weekly else "按日"
        self._trend_card.set_subtitle(
            f"{metric.label} · {unit} · 按模型系列堆叠"
        )

    def _update_models(
        self, current: analytics.Dataset, metric: analytics.Metric
    ) -> None:
        groups = current.by_model()
        groups.sort(key=lambda g: metric.of(g.totals), reverse=True)
        values = [metric.of(g.totals) for g in groups[:TOP_MODELS]]
        labels = [
            pricing.display_name(g.key or "") for g in groups[:TOP_MODELS]
        ]
        rest = sum(metric.of(g.totals) for g in groups[TOP_MODELS:])
        if rest > 0:
            values.append(rest)
            labels.append("其他模型")
        self._models.set_value_formatter(metric_formatter(metric))
        self._models.set_data(labels, [charts.Series(metric.label, values)])
        self._models_card.set_subtitle(
            formatting.join_cjk("按", metric.label, f"，共 {len(groups)} 个模型")
        )

    def _update_accounts(
        self, current: analytics.Dataset, metric: analytics.Metric
    ) -> None:
        by_source = self._group_by.selected_indices == [1]
        if by_source:
            groups = current.by_source()
            name = self._source_name
            role = "secondary"
        else:
            groups = current.by_account()
            name = self._state.account_name
            role = "primary"
        groups.sort(key=lambda g: metric.of(g.totals), reverse=True)
        labels = [name(g.key) for g in groups[:8]]
        values = [metric.of(g.totals) for g in groups[:8]]
        self._account_bars.set_value_formatter(metric_formatter(metric))
        self._account_bars.set_data(
            labels, [charts.Series(metric.label, values, role)]
        )
        _leave_label_room(self._account_bars, values)
        what = "请求来源" if by_source else "账号"
        self._accounts_card.set_subtitle(
            formatting.join_cjk(f"各{what}的", metric.label)
        )

    @staticmethod
    def _source_name(key: str | None) -> str:
        try:
            return models.UsageSource(key).label
        except ValueError:
            return "未知来源"

    def _update_projects(
        self, current: analytics.Dataset, metric: analytics.Metric
    ) -> None:
        groups = current.by_project()
        groups.sort(key=lambda g: metric.of(g.totals), reverse=True)
        top = groups[:TOP_PROJECTS]
        values = [metric.of(g.totals) for g in top]
        self._projects.set_value_formatter(metric_formatter(metric))
        self._projects.set_data(
            [g.key or "—" for g in top],
            [charts.Series(metric.label, values, "tertiary")],
        )
        _leave_label_room(self._projects, values)
        self._projects_card.set_subtitle(
            f"前 {len(top)} / {len(groups)} 个项目（工作目录）"
        )

    def _update_composition(self, totals: analytics.Totals) -> None:
        self._composition.set_data(
            ["缓存读取", "缓存写入", "输出", "输入"],
            [
                charts.Series(
                    "Token",
                    [
                        float(totals.cache_read),
                        float(totals.cache_write),
                        float(totals.output_tokens),
                        float(totals.input_tokens),
                    ],
                )
            ],
        )
        self._gauge.set_value(round(totals.cache_hit_rate * 100, 1))
        self._gauge_card.set_subtitle(
            "缓存读取占全部输入的比例，越高越省钱"
        )

    def _update_table(self, current: analytics.Dataset) -> None:
        groups = current.by_model()
        total = sum(g.totals.total_tokens for g in groups) or 1
        rows = []
        for group in groups:
            t = group.totals
            rows.append(
                {
                    "model": group.key,
                    "requests": t.requests,
                    "input": t.input_tokens,
                    "output": t.output_tokens,
                    "write": t.cache_write,
                    "read": t.cache_read,
                    "total": t.total_tokens,
                    "cost": t.cost if t.priced else None,
                    "share": t.total_tokens / total,
                }
            )
        self._table.set_rows(rows)
        visible = max(3, min(len(rows), self._table.page_size))
        self._table.setFixedHeight(
            TABLE_HEADER + TABLE_ROW * visible + TABLE_FOOTER
        )

    # ---- 提示横幅 ---------------------------------------------------------

    def _banner_spec(self) -> BannerSpec | None:
        """(键, 文字, 图标, [(按钮, 目标页)])；无需提示时返回 None。"""
        state = self._state
        if state.data_source is models.DataSource.DEMO:
            return (
                "demo",
                "当前显示的是演示数据：根据你的账号列表模拟生成，仅用于预览图表效果。",
                "science",
                [("切换数据源", "settings")],
            )
        scan = state.scan
        if scan is not None and not scan.exists:
            return (
                "missing",
                f"没有找到 Claude Code 日志目录：{scan.directory}",
                "folder_off",
                [("前往设置", "settings")],
            )
        unassigned = [r for r in state.dataset.records if r.account_id is None]
        if unassigned:
            counts: dict[str, int] = {}
            for record in unassigned:
                name = self._source_name(record.source)
                counts[name] = counts.get(name, 0) + record.requests
            detail = "、".join(
                f"{name} {formatting.count(value)} 次"
                for name, value in sorted(counts.items(), key=lambda i: -i[1])
            )
            return (
                f"unassigned:{sorted(counts)}",
                f"有请求还没有归属到账号（{detail}）：关联 Claude Desktop 的"
                "账号或把中转配置保存为账号后，会自动计入对应账号。",
                "person_search",
                [("前往客户端", "clients")],
            )
        return None

    def _update_banner(self) -> None:
        spec = self._banner_spec()
        key = spec[0] if spec else None
        if key == self._banner_key:
            return
        self._banner_key = key
        if self._banner is not None:
            self._banner_slot.removeWidget(self._banner)
            self._banner.deleteLater()
            self._banner = None
        if spec is None:
            return
        _key, text, icon, actions = spec
        banner = common.InfoBanner(text, icon=icon)
        for label, target in actions:
            banner.add_action(label).clicked.connect(
                lambda _checked=False, t=target: self.navigate_requested.emit(t)
            )
        banner.add_action("知道了")
        self._banner = banner
        self._banner_slot.addWidget(banner)
