"""K 线图、箱线图与瀑布图。

三者都基于直角坐标系：

- ``CandlestickChart``：每个分类一根蜡烛（开 / 高 / 低 / 收），上涨与下跌
  使用不同颜色，影线为 1dp 竖线，实体为圆角矩形。
- ``BoxPlotChart``：每个分类一组五数概括（最小、下四分位、中位、上四分
  位、最大）与离群点，箱体填充 ``primary_container``、中位线为 ``primary``。
- ``WaterfallChart``：值为增量，柱子从上一累计值浮动到新累计值；正值
  ``primary``、负值 ``error``、合计柱 ``secondary``，柱子之间以虚线相连。

三者都支持基类的缩放 / 平移、游标、导出与悬停气泡。
"""

from __future__ import annotations

import dataclasses
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.charts import base
from md3.components.charts import model
from md3.components.charts import palette
from md3.core import shape as shape_utils
from md3.tokens import shape as shape_tokens

BODY_RATIO = 0.6
MIN_BODY_WIDTH = 3.0
WICK_WIDTH = 1.0
BODY_RADIUS = 2.0
BOX_RATIO = 0.56
WHISKER_CAP_RATIO = 0.3
OUTLIER_RADIUS = 3.0
WATERFALL_RATIO = 0.6
CONNECTOR_WIDTH = 1.0


@dataclasses.dataclass
class Candle:
    """一根蜡烛的开 / 高 / 低 / 收。"""

    open: float
    high: float
    low: float
    close: float

    @property
    def rising(self) -> bool:
        """是否上涨（收 ≥ 开）。"""
        return self.close >= self.open


@dataclasses.dataclass
class BoxStats:
    """箱线图的五数概括与离群点。"""

    minimum: float
    q1: float
    median: float
    q3: float
    maximum: float
    outliers: tuple[float, ...] = ()

    @classmethod
    def from_values(cls, values: list[float]) -> BoxStats:
        """由原始样本计算五数概括，1.5 倍四分位距之外的点作为离群点。"""
        data = sorted(float(v) for v in values)
        if not data:
            return cls(0.0, 0.0, 0.0, 0.0, 0.0)

        def percentile(fraction: float) -> float:
            position = (len(data) - 1) * fraction
            lower = int(position)
            upper = min(lower + 1, len(data) - 1)
            weight = position - lower
            return data[lower] * (1 - weight) + data[upper] * weight

        q1, median, q3 = percentile(0.25), percentile(0.5), percentile(0.75)
        spread = q3 - q1
        fence_low, fence_high = q1 - 1.5 * spread, q3 + 1.5 * spread
        inliers = [v for v in data if fence_low <= v <= fence_high]
        outliers = tuple(v for v in data if v < fence_low or v > fence_high)
        return cls(
            min(inliers) if inliers else data[0],
            q1,
            median,
            q3,
            max(inliers) if inliers else data[-1],
            outliers,
        )


class CandlestickChart(base.CartesianChart):
    """K 线图。

    Args:
        candles: 蜡烛列表。
        categories: 分类标签（通常为日期）。
        title: 标题。
        up_color: 上涨颜色（色彩角色名 / 十六进制 / ``QColor``）。
        down_color: 下跌颜色。
        animated: 是否播放入场动画。
        parent: 父控件。
    """

    def __init__(
        self,
        candles: list[Candle] | None = None,
        categories: list[str] | None = None,
        title: str = "",
        up_color: QtGui.QColor | str = "tertiary",
        down_color: QtGui.QColor | str = "error",
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__([], categories, title, False, animated, parent)
        self._candles: list[Candle] = list(candles or [])
        self._up_color = up_color
        self._down_color = down_color

    @property
    def candles(self) -> list[Candle]:
        """蜡烛列表。"""
        return list(self._candles)

    def set_candles(
        self, candles: list[Candle], categories: list[str] | None = None
    ) -> None:
        """替换全部蜡烛并重播入场动画。"""
        self._candles = list(candles)
        if categories is not None:
            self._categories = list(categories)
        self._hovered = -1
        self._hover_info = None
        if self._animated:
            self.restart_animation()
        self.update()

    def append_candle(
        self,
        candle: Candle,
        category: str | None = None,
        max_points: int | None = None,
    ) -> None:
        """追加一根蜡烛（流式行情）。"""
        self._candles.append(candle)
        self._categories.append(
            category if category is not None else str(len(self._categories) + 1)
        )
        if max_points is not None and max_points > 0:
            del self._candles[:-max_points]
            del self._categories[:-max_points]
        self.update()

    def candle_at(self, index: int) -> Candle | None:
        """可见窗口内第 index 根蜡烛。"""
        source = index + self._view_start
        if 0 <= source < len(self._candles):
            return self._candles[source]
        return None

    def candle_color(self, candle: Candle) -> QtGui.QColor:
        """蜡烛颜色。"""
        declared = self._up_color if candle.rising else self._down_color
        fallback = self.color("tertiary" if candle.rising else "error")
        return palette.resolve_color(self.theme, declared, fallback)

    @override
    def has_data(self) -> bool:
        return bool(self._candles)

    @override
    def total_category_count(self) -> int:
        return len(self._candles)

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        return []

    @override
    def data_extent(self) -> tuple[float, float]:
        if not self._candles:
            return 0.0, 1.0
        return (
            min(c.low for c in self._candles),
            max(c.high for c in self._candles),
        )

    @override
    def value_range(self) -> tuple[float, float, list[float]]:
        low, high = self.data_extent()
        if self._y_min is not None:
            low = self._y_min
        if self._y_max is not None:
            high = self._y_max
        ticks = model.nice_ticks(low, high, base.Y_TICK_COUNT)
        return ticks[0], ticks[-1], ticks

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        self.paint_hover_band(painter, plot, self.hovered_index)
        self.paint_axes(painter, plot, low, high, ticks)
        progress = self.progress
        for index in range(self.category_count()):
            candle = self.candle_at(index)
            if candle is None:
                continue
            slot = self.category_slot(index, plot)
            color = self.candle_color(candle)
            center_x = slot.center().x()
            body_width = max(MIN_BODY_WIDTH, slot.width() * BODY_RATIO)
            # 入场：从中价向两端展开。
            mid = (candle.high + candle.low) / 2
            high_v = mid + (candle.high - mid) * progress
            low_v = mid + (candle.low - mid) * progress
            open_v = mid + (candle.open - mid) * progress
            close_v = mid + (candle.close - mid) * progress
            painter.setPen(QtGui.QPen(color, WICK_WIDTH))
            painter.drawLine(
                QtCore.QPointF(
                    center_x, self.value_to_y(high_v, plot, low, high)
                ),
                QtCore.QPointF(
                    center_x, self.value_to_y(low_v, plot, low, high)
                ),
            )
            top = self.value_to_y(max(open_v, close_v), plot, low, high)
            bottom = self.value_to_y(min(open_v, close_v), plot, low, high)
            body = QtCore.QRectF(
                center_x - body_width / 2,
                top,
                body_width,
                max(1.0, bottom - top),
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    body, shape_tokens.Shape.all(BODY_RADIUS)
                ),
                color,
            )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        if not plot.contains(position):
            return None
        index = self.category_at(position.x(), plot)
        candle = self.candle_at(index)
        if candle is None:
            return None
        color = self.candle_color(candle)
        slot = self.category_slot(index, plot)
        lines = [
            (color, "O", self.format(candle.open)),
            (color, "H", self.format(candle.high)),
            (color, "L", self.format(candle.low)),
            (color, "C", self.format(candle.close)),
        ]
        return index, base.HoverInfo(
            self.category_label(index),
            lines,
            QtCore.QPointF(
                slot.center().x(), self.value_to_y(candle.high, plot, low, high)
            ),
        )


class BoxPlotChart(base.CartesianChart):
    """箱线图。

    Args:
        boxes: 每个分类的五数概括。
        categories: 分类标签。
        title: 标题。
        color: 箱体颜色（默认 ``primary``）。
        animated: 是否播放入场动画。
        parent: 父控件。
    """

    def __init__(
        self,
        boxes: list[BoxStats] | None = None,
        categories: list[str] | None = None,
        title: str = "",
        color: QtGui.QColor | str = "primary",
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__([], categories, title, False, animated, parent)
        self._boxes: list[BoxStats] = list(boxes or [])
        self._color = color

    @property
    def boxes(self) -> list[BoxStats]:
        """全部箱体。"""
        return list(self._boxes)

    def set_boxes(
        self, boxes: list[BoxStats], categories: list[str] | None = None
    ) -> None:
        """替换全部数据。"""
        self._boxes = list(boxes)
        if categories is not None:
            self._categories = list(categories)
        self._hovered = -1
        self._hover_info = None
        if self._animated:
            self.restart_animation()
        self.update()

    def box_at(self, index: int) -> BoxStats | None:
        """可见窗口内第 index 个箱体。"""
        source = index + self._view_start
        if 0 <= source < len(self._boxes):
            return self._boxes[source]
        return None

    def box_color(self) -> QtGui.QColor:
        """箱体强调色。"""
        return palette.resolve_color(
            self.theme, self._color, self.color("primary")
        )

    @override
    def has_data(self) -> bool:
        return bool(self._boxes)

    @override
    def total_category_count(self) -> int:
        return len(self._boxes)

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        return []

    @override
    def data_extent(self) -> tuple[float, float]:
        if not self._boxes:
            return 0.0, 1.0
        lows = [min((box.minimum, *box.outliers)) for box in self._boxes]
        highs = [max((box.maximum, *box.outliers)) for box in self._boxes]
        return min(lows), max(highs)

    @override
    def value_range(self) -> tuple[float, float, list[float]]:
        low, high = self.data_extent()
        if self._y_min is not None:
            low = self._y_min
        if self._y_max is not None:
            high = self._y_max
        ticks = model.nice_ticks(low, high, base.Y_TICK_COUNT)
        return ticks[0], ticks[-1], ticks

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        self.paint_hover_band(painter, plot, self.hovered_index)
        self.paint_axes(painter, plot, low, high, ticks)
        accent = self.box_color()
        fill = QtGui.QColor(accent)
        fill.setAlphaF(0.24)
        progress = self.progress
        for index in range(self.category_count()):
            box = self.box_at(index)
            if box is None:
                continue
            slot = self.category_slot(index, plot)
            center_x = slot.center().x()
            box_width = max(MIN_BODY_WIDTH, slot.width() * BOX_RATIO)
            cap = box_width * WHISKER_CAP_RATIO

            def y_of(value: float, median: float = box.median) -> float:
                # 入场动画：各统计量从中位数向外展开。
                scaled = median + (value - median) * progress
                return self.value_to_y(scaled, plot, low, high)

            pen = QtGui.QPen(accent, WICK_WIDTH)
            painter.setPen(pen)
            painter.drawLine(
                QtCore.QPointF(center_x, y_of(box.maximum)),
                QtCore.QPointF(center_x, y_of(box.q3)),
            )
            painter.drawLine(
                QtCore.QPointF(center_x, y_of(box.q1)),
                QtCore.QPointF(center_x, y_of(box.minimum)),
            )
            for value in (box.maximum, box.minimum):
                y = y_of(value)
                painter.drawLine(
                    QtCore.QPointF(center_x - cap, y),
                    QtCore.QPointF(center_x + cap, y),
                )
            body = QtCore.QRectF(
                center_x - box_width / 2,
                y_of(box.q3),
                box_width,
                max(1.0, y_of(box.q1) - y_of(box.q3)),
            )
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    body, shape_tokens.Shape.all(BODY_RADIUS)
                ),
                fill,
                accent,
                WICK_WIDTH,
            )
            painter.setPen(QtGui.QPen(accent, 2.0))
            median_y = y_of(box.median)
            painter.drawLine(
                QtCore.QPointF(body.left(), median_y),
                QtCore.QPointF(body.right(), median_y),
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(accent)
            for outlier in box.outliers:
                painter.drawEllipse(
                    QtCore.QPointF(center_x, y_of(outlier)),
                    OUTLIER_RADIUS,
                    OUTLIER_RADIUS,
                )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        if not plot.contains(position):
            return None
        index = self.category_at(position.x(), plot)
        box = self.box_at(index)
        if box is None:
            return None
        color = self.box_color()
        slot = self.category_slot(index, plot)
        lines = [
            (color, "max", self.format(box.maximum)),
            (color, "Q3", self.format(box.q3)),
            (color, "median", self.format(box.median)),
            (color, "Q1", self.format(box.q1)),
            (color, "min", self.format(box.minimum)),
        ]
        return index, base.HoverInfo(
            self.category_label(index),
            lines,
            QtCore.QPointF(
                slot.center().x(), self.value_to_y(box.maximum, plot, low, high)
            ),
        )


class WaterfallChart(base.CartesianChart):
    """瀑布图。

    Args:
        values: 每个分类的增量；``totals`` 中的下标表示合计柱（显示累计值）。
        categories: 分类标签。
        title: 标题。
        totals: 合计柱的下标集合。
        animated: 是否播放入场动画。
        parent: 父控件。
    """

    def __init__(
        self,
        values: list[float] | None = None,
        categories: list[str] | None = None,
        title: str = "",
        totals: set[int] | None = None,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        series = [model.Series("", list(values or []))]
        super().__init__(series, categories, title, False, animated, parent)
        self._totals: set[int] = set(totals or ())

    @property
    def values(self) -> list[float]:
        """全部增量。"""
        return list(self._series[0].values) if self._series else []

    def set_values(
        self,
        values: list[float],
        categories: list[str] | None = None,
        totals: set[int] | None = None,
    ) -> None:
        """替换数据。"""
        if totals is not None:
            self._totals = set(totals)
        self.set_data(
            categories if categories is not None else self._categories,
            [model.Series("", list(values))],
        )

    @property
    def totals(self) -> set[int]:
        """合计柱下标。"""
        return set(self._totals)

    def running_totals(self) -> list[tuple[float, float]]:
        """每个（全部）分类柱子的 (起点, 终点) 累计值。"""
        spans: list[tuple[float, float]] = []
        cursor = 0.0
        for index, value in enumerate(self.values):
            if index in self._totals:
                spans.append((0.0, cursor))
                continue
            spans.append((cursor, cursor + value))
            cursor += value
        return spans

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        return []

    @override
    def data_extent(self) -> tuple[float, float]:
        spans = self.running_totals()
        if not spans:
            return 0.0, 1.0
        values = [v for span in spans for v in span]
        return min(values), max(values)

    def bar_color(self, index: int) -> QtGui.QColor:
        """可见窗口内第 index 根柱子的颜色。"""
        source = index + self._view_start
        if source in self._totals:
            return self.color("secondary")
        value = self.value_at(0, index)
        return self.color("primary" if value >= 0 else "error")

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        self.paint_hover_band(painter, plot, self.hovered_index)
        self.paint_axes(painter, plot, low, high, ticks)
        spans = self.running_totals()
        progress = self.progress
        previous_end: tuple[float, float] | None = None
        connector = QtGui.QPen(self.color("outline"), CONNECTOR_WIDTH)
        connector.setStyle(QtCore.Qt.PenStyle.DashLine)
        connector.setDashPattern([3, 3])
        for index in range(self.category_count()):
            source = index + self._view_start
            if source >= len(spans):
                break
            start, end = spans[source]
            start *= progress
            end *= progress
            slot = self.category_slot(index, plot)
            width = max(MIN_BODY_WIDTH, slot.width() * WATERFALL_RATIO)
            y0 = self.value_to_y(start, plot, low, high)
            y1 = self.value_to_y(end, plot, low, high)
            bar = QtCore.QRectF(
                slot.center().x() - width / 2,
                min(y0, y1),
                width,
                max(1.0, abs(y0 - y1)),
            )
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    bar, shape_tokens.Shape.all(BODY_RADIUS)
                ),
                self.bar_color(index),
            )
            if previous_end is not None:
                painter.setPen(connector)
                painter.drawLine(
                    QtCore.QPointF(previous_end[0], previous_end[1]),
                    QtCore.QPointF(bar.left(), previous_end[1]),
                )
            # 合计柱之后的连线从其顶端出发；普通柱从终点出发。
            previous_end = (bar.right(), y1)

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        if not plot.contains(position):
            return None
        index = self.category_at(position.x(), plot)
        spans = self.running_totals()
        source = index + self._view_start
        if index < 0 or source >= len(spans):
            return None
        start, end = spans[source]
        slot = self.category_slot(index, plot)
        color = self.bar_color(index)
        if source in self._totals:
            lines = [(color, "Σ", self.format(end))]
        else:
            delta = self.value_at(0, index)
            lines = [
                (
                    color,
                    "Δ",
                    f"{'+' if delta >= 0 else ''}{self.format(delta)}",
                ),
                (color, "Σ", self.format(end)),
            ]
        return index, base.HoverInfo(
            self.category_label(index),
            lines,
            QtCore.QPointF(
                slot.center().x(),
                self.value_to_y(max(start, end), plot, low, high),
            ),
        )
