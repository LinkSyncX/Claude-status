"""柱状图：分组或堆叠，纵向或横向。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.charts import base
from md3.components.charts import model
from md3.core import shape as shape_utils
from md3.core import typography
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

BAR_RADIUS = 4.0
GROUP_PADDING_RATIO = 0.25
BAR_GAP = 4.0
MIN_BAR_WIDTH = 4.0
STAGGER = 0.06
VALUE_LABEL_STYLE = typography_tokens.TypeRole.LABEL_SMALL
VALUE_LABEL_GAP = 4.0
# 横向柱状图分类标签的最大宽度。
CATEGORY_LABEL_MAX_WIDTH = 96.0


class BarChart(base.CartesianChart):
    """柱状图。

    Args:
        series: 数据系列。
        categories: 分类标签。
        stacked: 为真时同一分类的各系列堆叠，否则并排分组。
        show_values: 是否在柱子末端标注数值（堆叠时标注每类合计）。
        title: 标题。
        show_legend: 是否显示图例。
        animated: 是否播放入场动画（柱子自基线生长，逐分类错开）。
        parent: 父控件。
    """

    def __init__(
        self,
        series: list[model.Series] | None = None,
        categories: list[str] | None = None,
        stacked: bool = False,
        show_values: bool = False,
        title: str = "",
        show_legend: bool = True,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            series, categories, title, show_legend, animated, parent
        )
        self._stacked = stacked
        self._show_values = show_values

    @property
    def stacked(self) -> bool:
        """是否堆叠。"""
        return self._stacked

    def set_stacked(self, stacked: bool) -> None:
        """切换堆叠 / 分组。"""
        self._stacked = stacked
        self.update()

    @property
    def show_values(self) -> bool:
        """是否标注数值。"""
        return self._show_values

    def set_show_values(self, show: bool) -> None:
        """设置是否标注数值。"""
        self._show_values = show
        self.update()

    @override
    def data_extent(self) -> tuple[float, float]:
        if not self._stacked:
            return super().data_extent()
        return self.stacked_extent()

    def _category_progress(self, index: int) -> float:
        """逐分类错开的入场进度。"""
        raw = (self.progress - index * STAGGER) / (1.0 - STAGGER * 4)
        return max(0.0, min(1.0, raw))

    def bar_spans(
        self, plot: QtCore.QRectF
    ) -> list[list[tuple[float, float, float, float]]]:
        """返回 ``[系列][分类]`` 的 (槽位起点, 槽位宽度, 值起点, 值终点)。

        槽位沿分类轴度量、值沿数值轴度量（均为像素），由纵向 / 横向
        子类转换为矩形。隐藏的系列不占槽位，其条目为空。
        """
        count = self.category_count()
        visible = self.visible_series_indices()
        spans: list[list[tuple[float, float, float, float]]] = [
            [] for _ in self._series
        ]
        for index in range(count):
            slot = self.category_slot(index, plot)
            extent = self._slot_extent(slot)
            padding = extent[1] * GROUP_PADDING_RATIO / 2
            inner_start = extent[0] + padding
            inner_size = extent[1] - 2 * padding
            progress = self._category_progress(index)
            if self._stacked:
                width = max(MIN_BAR_WIDTH, inner_size)
                pos_cursor = neg_cursor = 0.0
                for s_index in visible:
                    value = self.displayed_value(s_index, index)
                    if value >= 0:
                        start, end = pos_cursor, pos_cursor + value
                        pos_cursor = end
                    else:
                        start, end = neg_cursor + value, neg_cursor
                        neg_cursor = start
                    spans[s_index].append(
                        (
                            inner_start + (inner_size - width) / 2,
                            width,
                            start * progress,
                            end * progress,
                        )
                    )
            else:
                n = max(1, len(visible))
                width = max(MIN_BAR_WIDTH, (inner_size - BAR_GAP * (n - 1)) / n)
                for position, s_index in enumerate(visible):
                    value = self.displayed_value(s_index, index) * progress
                    spans[s_index].append(
                        (
                            inner_start + position * (width + BAR_GAP),
                            width,
                            min(0.0, value),
                            max(0.0, value),
                        )
                    )
        return spans

    @staticmethod
    def _slot_extent(slot: QtCore.QRectF) -> tuple[float, float]:
        """槽位沿分类轴的 (起点, 长度)。"""
        return slot.left(), slot.width()

    def bar_rects(self, plot: QtCore.QRectF) -> list[list[QtCore.QRectF]]:
        """返回 ``[系列][分类]`` 的柱子矩形（已应用入场进度）。"""
        low, high, _ = self.value_range()
        rects: list[list[QtCore.QRectF]] = []
        for spans in self.bar_spans(plot):
            row = []
            for start, width, v0, v1 in spans:
                y0 = self.value_to_y(v0, plot, low, high)
                y1 = self.value_to_y(v1, plot, low, high)
                row.append(
                    QtCore.QRectF(start, min(y0, y1), width, abs(y0 - y1))
                )
            rects.append(row)
        return rects

    def _bar_shape(
        self, s_index: int, c_index: int, positive: bool
    ) -> shape_tokens.Shape:
        """柱子末端的圆角：分组时每根都有，堆叠时只有最外层段落有。"""
        if self._stacked:
            for other in self.visible_series_indices():
                if other <= s_index:
                    continue
                value = self.value_at(other, c_index)
                if (value > 0) == positive and value != 0:
                    return shape_tokens.SHAPE_NONE
        return self._end_shape(positive)

    @staticmethod
    def _end_shape(positive: bool) -> shape_tokens.Shape:
        return (
            shape_tokens.Shape.top(BAR_RADIUS)
            if positive
            else shape_tokens.Shape.bottom(BAR_RADIUS)
        )

    def _category_totals(self, index: int) -> tuple[float, float]:
        """第 index 个分类中可见系列的正、负合计。"""
        positive = negative = 0.0
        for s_index in self.visible_series_indices():
            value = self.displayed_value(s_index, index)
            if value >= 0:
                positive += value
            else:
                negative += value
        return positive, negative

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        self.paint_hover_band(painter, plot, self.hovered_index)
        self.paint_axes(painter, plot, low, high, ticks)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        rects = self.bar_rects(plot)
        for s_index, bars in enumerate(rects):
            color = self.color_for(s_index)
            for c_index, bar in enumerate(bars):
                if self._bar_length(bar) < 0.5:
                    continue
                dim = self.hovered_index >= 0 and c_index != self.hovered_index
                painter.setOpacity(0.55 if dim else 1.0)
                positive = self._is_positive(bar, plot, low, high)
                painter.setBrush(color)
                painter.drawPath(
                    shape_utils.rounded_rect_path(
                        bar, self._bar_shape(s_index, c_index, positive)
                    )
                )
        painter.setOpacity(1.0)
        if self._show_values:
            self._paint_values(painter, plot, rects, low, high)

    @staticmethod
    def _bar_length(bar: QtCore.QRectF) -> float:
        return bar.height()

    def _is_positive(
        self,
        bar: QtCore.QRectF,
        plot: QtCore.QRectF,
        low: float,
        high: float,
    ) -> bool:
        baseline = self.value_to_y(0.0, plot, low, high)
        return bar.bottom() >= baseline - 0.5

    def _paint_values(
        self,
        painter: QtGui.QPainter,
        plot: QtCore.QRectF,
        rects: list[list[QtCore.QRectF]],
        low: float,
        high: float,
    ) -> None:
        """在柱子末端标注数值；堆叠时标注每个分类的合计。"""
        color = self.color("on_surface_variant")
        line = self.theme.style(VALUE_LABEL_STYLE).line_height
        if self._stacked:
            for index in range(self.category_count()):
                slot = self.category_slot(index, plot)
                positive, negative = self._category_totals(index)
                total = positive + negative
                y = self.value_to_y(
                    positive if total >= 0 else negative, plot, low, high
                )
                self._paint_value_label(
                    painter,
                    slot.center().x(),
                    y,
                    total >= 0,
                    total,
                    color,
                    line,
                )
            return
        for s_index, bars in enumerate(rects):
            for c_index, bar in enumerate(bars):
                value = self.displayed_value(s_index, c_index)
                positive = value >= 0
                y = bar.top() if positive else bar.bottom()
                self._paint_value_label(
                    painter, bar.center().x(), y, positive, value, color, line
                )

    def _paint_value_label(
        self,
        painter: QtGui.QPainter,
        x: float,
        y: float,
        positive: bool,
        value: float,
        color: QtGui.QColor,
        line: float,
    ) -> None:
        top = y - VALUE_LABEL_GAP - line if positive else y + VALUE_LABEL_GAP
        typography.paint_text(
            painter,
            QtCore.QRectF(x - 40, top, 80, line),
            self.format(value),
            VALUE_LABEL_STYLE,
            color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
            elide=False,
        )

    def hover_lines(self, index: int) -> list[tuple[QtGui.QColor, str, str]]:
        """悬停气泡中可见系列的行。"""
        lines = []
        for s_index in self.visible_series_indices():
            series = self._series[s_index]
            value = self.value_at(s_index, index)
            lines.append(
                (self.color_for(s_index), series.name, self.format(value))
            )
        return lines

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        _, _, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        index = self.category_at(position.x(), plot)
        if (
            index < 0
            or not plot.top()
            <= position.y()
            <= plot.bottom() + base.X_LABEL_HEIGHT
        ):
            return None
        bars = self.bar_rects(plot)
        tops = [rows[index].top() for rows in bars if index < len(rows)]
        anchor_y = min(tops) if tops else plot.top()
        slot = self.category_slot(index, plot)
        return index, base.HoverInfo(
            self.category_label(index),
            self.hover_lines(index),
            QtCore.QPointF(slot.center().x(), anchor_y),
        )


class HorizontalBarChart(BarChart):
    """横向柱状图：分类沿 y 轴排列，数值沿 x 轴延伸。

    参数与 ``BarChart`` 相同；分类标签显示在左侧，适合分类名较长的
    排行类数据。
    """

    def _label_width(self) -> float:
        width = max(
            (
                typography.text_width(self.category_label(i), base.AXIS_STYLE)
                for i in range(self.category_count())
            ),
            default=0.0,
        )
        return min(CATEGORY_LABEL_MAX_WIDTH, width)

    @override
    def plot_rect(
        self, rect: QtCore.QRectF, ticks: list[float]
    ) -> QtCore.QRectF:
        if not self.show_axes:
            return rect.adjusted(4, 4, -4, -4)
        left = (
            rect.left()
            + self._axis_title_width()
            + self._label_width()
            + base.AXIS_LABEL_GAP
        )
        return QtCore.QRectF(
            left,
            rect.top() + 4,
            max(0.0, rect.right() - left - 8),
            max(
                0.0,
                rect.height()
                - 4
                - base.X_LABEL_HEIGHT
                - self._axis_title_height(),
            ),
        )

    def value_to_x(
        self, value: float, plot: QtCore.QRectF, low: float, high: float
    ) -> float:
        """把数值映射为 x 坐标。"""
        span = high - low or 1.0
        return plot.left() + (value - low) / span * plot.width()

    @override
    def category_slot(self, index: int, plot: QtCore.QRectF) -> QtCore.QRectF:
        count = max(1, self.category_count())
        height = plot.height() / count
        return QtCore.QRectF(
            plot.left(), plot.top() + index * height, plot.width(), height
        )

    def category_at_y(self, y: float, plot: QtCore.QRectF) -> int:
        """y 坐标对应的分类下标，越界返回 -1。"""
        count = self.category_count()
        if (
            count == 0
            or plot.height() <= 0
            or not plot.top() <= y <= plot.bottom()
        ):
            return -1
        index = int((y - plot.top()) / plot.height() * count)
        return min(count - 1, max(0, index))

    @staticmethod
    @override
    def _slot_extent(slot: QtCore.QRectF) -> tuple[float, float]:
        return slot.top(), slot.height()

    @override
    def bar_rects(self, plot: QtCore.QRectF) -> list[list[QtCore.QRectF]]:
        low, high, _ = self.value_range()
        rects: list[list[QtCore.QRectF]] = []
        for spans in self.bar_spans(plot):
            row = []
            for start, height, v0, v1 in spans:
                x0 = self.value_to_x(v0, plot, low, high)
                x1 = self.value_to_x(v1, plot, low, high)
                row.append(
                    QtCore.QRectF(min(x0, x1), start, abs(x1 - x0), height)
                )
            rects.append(row)
        return rects

    @staticmethod
    @override
    def _bar_length(bar: QtCore.QRectF) -> float:
        return bar.width()

    @override
    def _is_positive(
        self,
        bar: QtCore.QRectF,
        plot: QtCore.QRectF,
        low: float,
        high: float,
    ) -> bool:
        baseline = self.value_to_x(0.0, plot, low, high)
        return bar.left() >= baseline - 0.5

    @staticmethod
    @override
    def _end_shape(positive: bool) -> shape_tokens.Shape:
        if positive:
            return shape_tokens.Shape(0.0, BAR_RADIUS, BAR_RADIUS, 0.0)
        return shape_tokens.Shape(BAR_RADIUS, 0.0, 0.0, BAR_RADIUS)

    @override
    def paint_axes(
        self,
        painter: QtGui.QPainter,
        plot: QtCore.QRectF,
        low: float,
        high: float,
        ticks: list[float],
    ) -> None:
        if not self.show_axes:
            return
        grid_color = self.color("outline_variant")
        label_color = self.color("on_surface_variant")
        style = self.theme.style(base.AXIS_STYLE)
        for tick in ticks:
            x = self.value_to_x(tick, plot, low, high)
            if self._show_grid or tick == 0:
                pen = QtGui.QPen(grid_color, base.GRID_WIDTH)
                if tick != 0:
                    pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                    pen.setDashPattern([4, 4])
                painter.setPen(pen)
                painter.drawLine(
                    QtCore.QPointF(x, plot.top()),
                    QtCore.QPointF(x, plot.bottom()),
                )
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    x - 40, plot.bottom() + 4, 80, base.X_LABEL_HEIGHT - 4
                ),
                self.format(tick),
                base.AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
                elide=False,
            )
        width = self._label_width()
        for index in range(self.category_count()):
            slot = self.category_slot(index, plot)
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    plot.left() - base.AXIS_LABEL_GAP - width,
                    slot.center().y() - style.line_height / 2,
                    width,
                    style.line_height,
                ),
                self.category_label(index),
                base.AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        self.paint_axis_titles(painter, plot)

    @override
    def _paint_values(
        self,
        painter: QtGui.QPainter,
        plot: QtCore.QRectF,
        rects: list[list[QtCore.QRectF]],
        low: float,
        high: float,
    ) -> None:
        color = self.color("on_surface_variant")
        line = self.theme.style(VALUE_LABEL_STYLE).line_height
        entries: list[tuple[float, float, float]] = []
        if self._stacked:
            for index in range(self.category_count()):
                slot = self.category_slot(index, plot)
                positive, negative = self._category_totals(index)
                total = positive + negative
                x = self.value_to_x(
                    positive if total >= 0 else negative, plot, low, high
                )
                entries.append((x, slot.center().y(), total))
        else:
            for s_index, bars in enumerate(rects):
                for c_index, bar in enumerate(bars):
                    value = self.displayed_value(s_index, c_index)
                    x = bar.right() if value >= 0 else bar.left()
                    entries.append((x, bar.center().y(), value))
        for x, y, value in entries:
            text = self.format(value)
            width = typography.text_width(text, VALUE_LABEL_STYLE) + 4
            left = (
                x + VALUE_LABEL_GAP
                if value >= 0
                else x - VALUE_LABEL_GAP - width
            )
            typography.paint_text(
                painter,
                QtCore.QRectF(left, y - line / 2, width, line),
                text,
                VALUE_LABEL_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter
                if value >= 0
                else QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        _, _, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        index = self.category_at_y(position.y(), plot)
        if index < 0 or not rect.left() <= position.x() <= plot.right():
            return None
        bars = self.bar_rects(plot)
        rights = [rows[index].right() for rows in bars if index < len(rows)]
        slot = self.category_slot(index, plot)
        anchor_x = max(rights) if rights else plot.left()
        return index, base.HoverInfo(
            self.category_label(index),
            self.hover_lines(index),
            QtCore.QPointF(anchor_x, slot.center().y()),
        )
