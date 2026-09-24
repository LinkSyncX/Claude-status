"""热力图页：活跃日历、当日明细、一周时段分布与账号 × 月份矩阵。"""

from __future__ import annotations

import datetime as dt

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import charts
from md3.components import dividers
from md3.tokens import spacing

from claude_status import analytics
from claude_status import formatting
from claude_status import pricing
from claude_status import state as state_module
from claude_status.pages import dashboard
from claude_status.widgets import calendar_heatmap
from claude_status.widgets import common
from claude_status.widgets import dense_charts

METRICS = [
    analytics.Metric.TOKENS,
    analytics.Metric.REQUESTS,
    analytics.Metric.COST,
]
MAX_YEARS = 4
MONTHS = 12
HOURS = [str(hour) for hour in range(24)]


class MiniStat(QtWidgets.QWidget):
    """数值 + 说明的小型统计块。"""

    def __init__(
        self, caption: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self._value = common.label("—", "title-large")
        self._caption = common.label(
            caption, "body-small", "on_surface_variant"
        )
        layout.addWidget(self._value)
        layout.addWidget(self._caption)

    def set_value(self, value: str, caption: str | None = None) -> None:
        """更新数值与说明。"""
        self._value.setText(value)
        if caption is not None:
            self._caption.setText(caption)


class HeatmapPage(common.Page):
    """热力图页。

    Args:
        state: 应用状态。
        parent: 父控件。
    """

    def __init__(
        self,
        state: state_module.AppState,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._periods: list[tuple[str, dt.date, dt.date]] = []
        self._scope = analytics.Dataset([])
        self._day_cache: dict[dt.date, analytics.Dataset] = {}
        self._build_controls()
        self._build_calendar()
        self._build_day_details()
        self._build_matrices()
        state.records_changed.connect(self._on_data_changed)
        state.accounts_changed.connect(self._on_data_changed)
        self._on_data_changed()

    # ---- 构建 -------------------------------------------------------------

    def _build_controls(self) -> None:
        self._period_slot = QtWidgets.QHBoxLayout()
        self._period_slot.setContentsMargins(0, 0, 0, 0)
        self._period: buttons.SegmentedButton | None = None
        self._metric = buttons.SegmentedButton(
            [
                buttons.Segment("Token", "token"),
                buttons.Segment("请求", "bolt"),
                buttons.Segment("费用", "payments"),
            ],
            selected=[0],
            show_check_icon=False,
        )
        self._metric.selection_changed.connect(lambda _i: self.refresh())
        self._accounts = dashboard.AccountFilter(self._state)
        self._accounts.selection_changed.connect(lambda _i: self.refresh())
        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(round(spacing.SPACE_3))
        controls.addLayout(self._period_slot)
        controls.addWidget(self._metric)
        controls.addStretch(1)
        controls.addWidget(self._accounts)
        self.body.addLayout(controls)

    def _build_calendar(self) -> None:
        self._calendar_card = common.SectionCard("活跃日历")
        self._calendar = calendar_heatmap.CalendarHeatmap()
        self._calendar.set_tooltip_provider(self._describe_day)
        self._calendar.day_clicked.connect(self._on_day_clicked)
        self._calendar_card.add_widget(self._calendar)
        self._calendar_card.add_widget(dividers.Divider())
        stats = QtWidgets.QHBoxLayout()
        stats.setSpacing(round(spacing.SPACE_8))
        self._stat_current = MiniStat("当前连续活跃")
        self._stat_longest = MiniStat("最长连续活跃")
        self._stat_active = MiniStat("活跃天数")
        self._stat_peak = MiniStat("单日峰值")
        self._stat_total = MiniStat("区间合计")
        for stat in (
            self._stat_current,
            self._stat_longest,
            self._stat_active,
            self._stat_peak,
            self._stat_total,
        ):
            stats.addWidget(stat)
        stats.addStretch(1)
        self._calendar_card.content_layout.addLayout(stats)
        self.body.addWidget(self._calendar_card)

    def _build_day_details(self) -> None:
        self._day_card = common.SectionCard(
            "当日明细", "点击日历中的任意一天查看"
        )
        body = QtWidgets.QHBoxLayout()
        body.setSpacing(round(spacing.SPACE_6))
        left = QtWidgets.QVBoxLayout()
        left.setSpacing(round(spacing.SPACE_3))
        figures = QtWidgets.QHBoxLayout()
        figures.setSpacing(round(spacing.SPACE_6))
        self._day_tokens = MiniStat("Token")
        self._day_requests = MiniStat("请求")
        self._day_cost = MiniStat("估算费用")
        for stat in (self._day_tokens, self._day_requests, self._day_cost):
            figures.addWidget(stat)
        figures.addStretch(1)
        left.addLayout(figures)
        self._day_models = common.label(
            "", "body-medium", "on_surface_variant", wrap=True
        )
        self._day_models.setTextFormat(QtCore.Qt.TextFormat.PlainText)
        left.addWidget(self._day_models)
        left.addStretch(1)
        body.addLayout(left, 2)
        self._day_hours = dense_charts.DenseBarChart(show_legend=False)
        self._day_hours.setMinimumHeight(200)
        body.addWidget(self._day_hours, 3)
        self._day_card.content_layout.addLayout(body)
        self.body.addWidget(self._day_card)

    def _build_matrices(self) -> None:
        self._week_card = common.SectionCard(
            "一周时段分布", "按星期几与小时汇总，找出你最常使用 Claude 的时间"
        )
        self._week = charts.HeatmapChart()
        self._week.setMinimumHeight(300)
        self._week_card.add_widget(self._week)
        self.body.addWidget(self._week_card)
        self._months_card = common.SectionCard(
            "账号 × 月份", "最近 12 个月每个账号的用量"
        )
        self._months = charts.HeatmapChart(show_values=True)
        self._months.set_empty_text("最近 12 个月没有用量")
        self._months_card.add_widget(self._months)
        self.body.addWidget(self._months_card)

    # ---- 数据 -------------------------------------------------------------

    def current_metric(self) -> analytics.Metric:
        """当前指标。"""
        indices = self._metric.selected_indices
        return METRICS[indices[0]] if indices else analytics.Metric.TOKENS

    def _rebuild_periods(self) -> None:
        today = dt.date.today()
        periods = [("近一年", today - dt.timedelta(days=364), today)]
        years = sorted(
            {record.timestamp.year for record in self._state.dataset.records},
            reverse=True,
        )
        for year in years[:MAX_YEARS]:
            end = min(dt.date(year, 12, 31), today)
            periods.append((f"{year} 年", dt.date(year, 1, 1), end))
        labels = [label for label, _, _ in periods]
        if self._period is not None and labels == [p[0] for p in self._periods]:
            return
        previous = self._period.selected_indices if self._period else [0]
        self._periods = periods
        if self._period is not None:
            self._period_slot.removeWidget(self._period)
            self._period.deleteLater()
        self._period = buttons.SegmentedButton(
            labels,
            selected=[min(previous[0] if previous else 0, len(labels) - 1)],
            show_check_icon=False,
        )
        self._period.selection_changed.connect(lambda _i: self.refresh())
        self._period_slot.addWidget(self._period)

    def current_period(self) -> tuple[str, dt.date, dt.date]:
        """当前时间段 (名称, 开始, 结束)。"""
        indices = self._period.selected_indices if self._period else []
        return self._periods[indices[0] if indices else 0]

    def _on_data_changed(self) -> None:
        self._accounts.sync()
        self._rebuild_periods()
        # 后台刷新（例如每分钟增量扫描日志）时原地更新，不重播入场动画。
        self.refresh(animate=False)

    def refresh(self, animate: bool = True) -> None:
        """重算全部热力图；``animate`` 为假时不重播入场动画。"""
        metric = self.current_metric()
        label, start, end = self.current_period()
        self._scope = self._state.dataset.filter(
            account_ids=self._accounts.account_ids()
        )
        period = self._scope.filter(start, end)
        self._day_cache = {}
        for record, cost in period:
            day = self._day_cache.setdefault(record.day, analytics.Dataset([]))
            day.records.append(record)
            day.costs.append(cost)
        values = period.daily_map(metric)
        self._calendar.set_values(values, start, end, animate)
        fmt = dashboard.metric_formatter(metric)
        summary = analytics.activity(values, start, end)
        totals = period.totals()
        self._calendar_card.set_subtitle(
            f"{label}（{formatting.date_short(start)} – "
            f"{formatting.date_short(end)}）按{metric.label}着色，"
            "颜色越深用量越大"
        )
        self._stat_current.set_value(f"{summary.current_streak} 天")
        longest = f"{summary.longest_streak} 天"
        since = (
            f"最长连续活跃 · 始于 {formatting.date_short(summary.longest_start)}"
            if summary.longest_start
            else "最长连续活跃"
        )
        self._stat_longest.set_value(longest, since)
        ratio = summary.active_days / max(1, summary.total_days)
        self._stat_active.set_value(
            f"{summary.active_days} / {summary.total_days}",
            f"活跃天数 · {formatting.percent(ratio, 0)}",
        )
        if summary.busiest_day is not None:
            self._stat_peak.set_value(
                fmt(summary.busiest_value),
                f"单日峰值 · {formatting.date_short(summary.busiest_day)}",
            )
        else:
            self._stat_peak.set_value("—", "单日峰值")
        self._stat_total.set_value(
            fmt(metric.of(totals)), f"区间合计 · {metric.label}"
        )
        selected = self._calendar.selected_day
        if selected is None and self._day_cache:
            selected = max(self._day_cache)
        self._show_day(selected)
        self._update_week(period, metric, animate)
        self._update_months(metric, animate)

    def _day(self, day: dt.date) -> analytics.Dataset:
        return self._day_cache.get(day) or analytics.Dataset([])

    def _describe_day(
        self, day: dt.date, _value: float
    ) -> list[tuple[str, str]]:
        subset = self._day(day)
        totals = subset.totals()
        if totals.requests == 0:
            return [("无用量", "")]
        cost = formatting.money(totals.cost) if totals.priced else "未计价"
        lines = [
            ("Token", formatting.tokens(totals.total_tokens)),
            ("请求", formatting.count(totals.requests)),
            ("费用", cost),
        ]
        top = subset.by_model()
        if top:
            lines.append(("主要模型", pricing.display_name(top[0].key or "")))
        return lines

    def _on_day_clicked(self, day: dt.date | None) -> None:
        self._show_day(day)

    def _show_day(self, day: dt.date | None) -> None:
        if day is None:
            self._day_card.title_label.setText("当日明细")
            self._day_card.set_subtitle("点击日历中的任意一天查看")
            for stat in (self._day_tokens, self._day_requests, self._day_cost):
                stat.set_value("—")
            self._day_models.setText("")
            self._day_hours.set_data(HOURS, [])
            return
        subset = self._day(day)
        totals = subset.totals()
        self._day_card.title_label.setText(
            f"当日明细 · {formatting.date_full(day)}"
        )
        clicked = self._calendar.selected_day == day
        self._day_card.set_subtitle(
            "已选中的日期（再次点击取消）"
            if clicked
            else "默认显示最近有用量的一天"
        )
        self._day_tokens.set_value(formatting.tokens(totals.total_tokens))
        self._day_requests.set_value(formatting.count(totals.requests))
        self._day_cost.set_value(
            formatting.money(totals.cost) if totals.priced else "未计价"
        )
        lines = []
        for group in subset.by_model()[:5]:
            share = group.totals.total_tokens / max(1, totals.total_tokens)
            lines.append(
                f"{pricing.display_name(group.key or '')}："
                f"{formatting.tokens(group.totals.total_tokens)}"
                f"（{formatting.percent(share, 0)}）"
            )
        projects = [g.key or "—" for g in subset.by_project()[:4]]
        if projects:
            lines.append("项目：" + "、".join(projects))
        self._day_models.setText("\n".join(lines) or "这一天没有用量")
        hours = [0.0] * 24
        for record in subset.records:
            hours[record.timestamp.hour] += record.total_tokens
        self._day_hours.set_value_formatter(formatting.tokens)
        self._day_hours.set_data(HOURS, [charts.Series("Token", hours)])

    def _update_week(
        self,
        period: analytics.Dataset,
        metric: analytics.Metric,
        animate: bool,
    ) -> None:
        matrix = period.weekday_hour(metric)
        self._week.set_value_formatter(dashboard.metric_formatter(metric))
        self._week.set_matrix(
            list(formatting.WEEKDAYS), HOURS, matrix, animate
        )
        peak = max(
            (
                (value, row, column)
                for row, cells in enumerate(matrix)
                for column, value in enumerate(cells)
            ),
            default=(0.0, 0, 0),
        )
        value, row, hour = peak
        if value > 0:
            text = dashboard.metric_formatter(metric)(value)
            self._week_card.set_subtitle(
                f"最活跃时段：{formatting.WEEKDAYS[row]} "
                f"{hour}:00–{hour + 1}:00（{text}）"
            )
        else:
            self._week_card.set_subtitle("按星期几与小时汇总")

    def _update_months(self, metric: analytics.Metric, animate: bool) -> None:
        months = analytics.month_sequence(dt.date.today(), MONTHS)
        grid = self._scope.monthly_by_account(months, metric)
        rows = sorted(
            ((key, values) for key, values in grid.items() if any(values)),
            key=lambda item: -sum(item[1]),
        )
        self._months.set_value_formatter(dashboard.metric_formatter(metric))
        self._months.set_matrix(
            [self._state.account_name(key) for key, _ in rows],
            [f"{month}月" for _year, month in months],
            [values for _, values in rows],
            animate,
        )
        self._months.setMinimumHeight(110 + 44 * max(1, len(rows)))
