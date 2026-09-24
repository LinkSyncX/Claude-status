"""散点图与气泡图：x、y 均为数值轴。"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.charts import base
from md3.components.charts import model
from md3.components.charts import palette
from md3.core import typography

POINT_RADIUS = 5.0
MIN_BUBBLE_RADIUS = 4.0
MAX_BUBBLE_RADIUS = 28.0
HOVER_DISTANCE = 14.0
BUBBLE_ALPHA = 0.72
STAGGER = 0.5
X_TICK_COUNT = 6


class ScatterChart(base.Chart):
    """散点图 / 气泡图。

    Args:
        series: 点系列；提供 ``sizes`` 的系列绘制为气泡，面积与大小成正比。
        title: 标题。
        x_title: x 轴标题。
        y_title: y 轴标题。
        show_legend: 是否显示图例。
        animated: 是否播放入场动画（点依次弹出）。
        parent: 父控件。
    """

    def __init__(
        self,
        series: list[model.PointSeries] | None = None,
        title: str = "",
        x_title: str = "",
        y_title: str = "",
        show_legend: bool = True,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(None, None, title, show_legend, animated, parent)
        self._points: list[model.PointSeries] = list(series or [])
        self._x_title = x_title
        self._y_title = y_title
        self._show_grid = True
        self._hovered_point: tuple[int, int] | None = None
        self._x_formatter: base.ValueFormatter = model.format_value

    # ---- 数据 -------------------------------------------------------------

    @property
    def point_series(self) -> list[model.PointSeries]:
        """点系列。"""
        return list(self._points)

    def set_point_series(
        self, series: list[model.PointSeries], animate: bool = True
    ) -> None:
        """替换全部点系列并重播入场动画。"""
        self._points = list(series)
        self._hovered_point = None
        self._hidden = {i for i in self._hidden if i < len(self._points)}
        if animate and self._animated:
            self.restart_animation()
        self.update()

    @override
    def has_data(self) -> bool:
        return any(s.points for s in self._points)

    def set_show_grid(self, show: bool) -> None:
        """设置是否绘制网格线。"""
        self._show_grid = show
        self.update()

    def set_axis_titles(self, x_title: str = "", y_title: str = "") -> None:
        """设置轴标题。"""
        self._x_title = x_title
        self._y_title = y_title
        self.update()

    def set_x_formatter(self, formatter: base.ValueFormatter) -> None:
        """设置 x 轴刻度与气泡中 x 值的格式化函数。"""
        self._x_formatter = formatter
        self.update()

    @override
    def color_for(self, index: int) -> QtGui.QColor:
        fallbacks = palette.series_colors(self.theme, max(1, len(self._points)))
        declared = (
            self._points[index].color if index < len(self._points) else None
        )
        return palette.resolve_color(
            self.theme, declared, fallbacks[index % len(fallbacks)]
        )

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        return [(self.color_for(i), s.name) for i, s in enumerate(self._points)]

    def visible_indices(self) -> list[int]:
        """可见的系列下标。"""
        return [i for i in range(len(self._points)) if self.entry_visible(i)]

    @property
    def hovered_point(self) -> tuple[int, int] | None:
        """当前悬停的 (系列下标, 点下标)。"""
        return self._hovered_point

    # ---- 坐标 -------------------------------------------------------------

    def ranges(self) -> tuple[list[float], list[float]]:
        """返回 (x 刻度, y 刻度)。"""
        xs = [
            p[0] for i in self.visible_indices() for p in self._points[i].points
        ]
        ys = [
            p[1] for i in self.visible_indices() for p in self._points[i].points
        ]
        if not xs:
            xs, ys = [0.0, 1.0], [0.0, 1.0]
        x_ticks = model.nice_ticks(min(xs), max(xs), X_TICK_COUNT)
        y_ticks = model.nice_ticks(min(ys), max(ys), base.Y_TICK_COUNT)
        return x_ticks, y_ticks

    def _title_height(self) -> float:
        if not self._x_title:
            return 0.0
        return (
            self.theme.style(base.AXIS_TITLE_STYLE).line_height
            + base.AXIS_TITLE_GAP
        )

    def _title_width(self) -> float:
        if not self._y_title:
            return 0.0
        return (
            self.theme.style(base.AXIS_TITLE_STYLE).line_height
            + base.AXIS_TITLE_GAP
        )

    def plot_rect(
        self, rect: QtCore.QRectF, y_ticks: list[float]
    ) -> QtCore.QRectF:
        """去掉轴标签后的绘图矩形。"""
        label_width = max(
            (
                typography.text_width(self.format(t), base.AXIS_STYLE)
                for t in y_ticks
            ),
            default=0.0,
        )
        left = (
            rect.left()
            + self._title_width()
            + label_width
            + base.AXIS_LABEL_GAP
        )
        margin = MAX_BUBBLE_RADIUS if self._has_sizes() else POINT_RADIUS * 2
        return QtCore.QRectF(
            left + margin,
            rect.top() + margin,
            max(0.0, rect.right() - left - 2 * margin),
            max(
                0.0,
                rect.height()
                - 2 * margin
                - base.X_LABEL_HEIGHT
                - self._title_height(),
            ),
        )

    def _has_sizes(self) -> bool:
        return any(s.sizes for s in self._points)

    @staticmethod
    def _map(
        value: float, ticks: list[float], start: float, length: float
    ) -> float:
        span = ticks[-1] - ticks[0] or 1.0
        return start + (value - ticks[0]) / span * length

    def to_point(
        self,
        x: float,
        y: float,
        plot: QtCore.QRectF,
        x_ticks: list[float],
        y_ticks: list[float],
    ) -> QtCore.QPointF:
        """把数据坐标映射为控件坐标。"""
        return QtCore.QPointF(
            self._map(x, x_ticks, plot.left(), plot.width()),
            plot.bottom() - (self._map(y, y_ticks, 0.0, plot.height())),
        )

    def radius_for(self, s_index: int, index: int) -> float:
        """第 s_index 个系列第 index 个点的半径（气泡面积与大小成正比）。"""
        size = self._points[s_index].size_at(index)
        if size is None:
            return POINT_RADIUS
        largest = max(
            (
                max(self._points[i].sizes)
                for i in self.visible_indices()
                if self._points[i].sizes
            ),
            default=1.0,
        )
        if largest <= 0:
            return MIN_BUBBLE_RADIUS
        ratio = math.sqrt(max(0.0, size) / largest)
        return (
            MIN_BUBBLE_RADIUS + (MAX_BUBBLE_RADIUS - MIN_BUBBLE_RADIUS) * ratio
        )

    def _point_progress(self, s_index: int, index: int, count: int) -> float:
        """逐点错开的入场进度。"""
        offset = (index / max(1, count)) * STAGGER + s_index * 0.05
        raw = (self.progress - offset) / max(0.05, 1.0 - STAGGER - 0.05)
        return max(0.0, min(1.0, raw))

    # ---- 绘制 -------------------------------------------------------------

    def _paint_axes(
        self,
        painter: QtGui.QPainter,
        plot: QtCore.QRectF,
        x_ticks: list[float],
        y_ticks: list[float],
    ) -> None:
        grid_color = self.color("outline_variant")
        label_color = self.color("on_surface_variant")
        style = self.theme.style(base.AXIS_STYLE)
        pen = QtGui.QPen(grid_color, base.GRID_WIDTH)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 4])
        for tick in y_ticks:
            y = self.to_point(x_ticks[0], tick, plot, x_ticks, y_ticks).y()
            if self._show_grid:
                painter.setPen(pen)
                painter.drawLine(
                    QtCore.QPointF(plot.left(), y),
                    QtCore.QPointF(plot.right(), y),
                )
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    plot.left() - base.AXIS_LABEL_GAP - 80,
                    y - style.line_height / 2,
                    80,
                    style.line_height,
                ),
                self.format(tick),
                base.AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )
        for tick in x_ticks:
            x = self.to_point(tick, y_ticks[0], plot, x_ticks, y_ticks).x()
            if self._show_grid:
                painter.setPen(pen)
                painter.drawLine(
                    QtCore.QPointF(x, plot.top()),
                    QtCore.QPointF(x, plot.bottom()),
                )
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    x - 40, plot.bottom() + 8, 80, base.X_LABEL_HEIGHT - 4
                ),
                self._x_formatter(tick),
                base.AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
                elide=False,
            )
        line = self.theme.style(base.AXIS_TITLE_STYLE).line_height
        if self._x_title:
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    plot.left(),
                    plot.bottom() + 8 + base.X_LABEL_HEIGHT,
                    plot.width(),
                    line,
                ),
                self._x_title,
                base.AXIS_TITLE_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        if self._y_title:
            content = self.content_rect()
            painter.save()
            painter.translate(content.left(), plot.center().y())
            painter.rotate(-90)
            typography.paint_text(
                painter,
                QtCore.QRectF(-plot.height() / 2, 0, plot.height(), line),
                self._y_title,
                base.AXIS_TITLE_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
            painter.restore()

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        x_ticks, y_ticks = self.ranges()
        plot = self.plot_rect(rect, y_ticks)
        self._paint_axes(painter, plot, x_ticks, y_ticks)
        painter.save()
        painter.setClipRect(rect)
        hovered = self._hovered_point
        for s_index in self.visible_indices():
            series = self._points[s_index]
            color = self.color_for(s_index)
            fill = QtGui.QColor(color)
            fill.setAlphaF(BUBBLE_ALPHA if series.sizes else 0.9)
            count = len(series.points)
            for index, (x, y) in enumerate(series.points):
                point = self.to_point(x, y, plot, x_ticks, y_ticks)
                scale = self._point_progress(s_index, index, count)
                if scale <= 0:
                    continue
                radius = self.radius_for(s_index, index) * scale
                is_hovered = hovered == (s_index, index)
                dim = hovered is not None and not is_hovered
                painter.setOpacity(0.45 if dim else 1.0)
                painter.setBrush(fill)
                painter.setPen(QtGui.QPen(color, 2 if is_hovered else 1))
                if is_hovered:
                    radius += 2
                painter.drawEllipse(point, radius, radius)
        painter.restore()

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        x_ticks, y_ticks = self.ranges()
        plot = self.plot_rect(rect, y_ticks)
        best_distance = math.inf
        best_hit: tuple[int, int, QtCore.QPointF] | None = None
        for s_index in self.visible_indices():
            for index, (x, y) in enumerate(self._points[s_index].points):
                point = self.to_point(x, y, plot, x_ticks, y_ticks)
                distance = math.hypot(
                    point.x() - position.x(), point.y() - position.y()
                )
                reach = max(HOVER_DISTANCE, self.radius_for(s_index, index))
                if distance <= reach and distance < best_distance:
                    best_distance = distance
                    best_hit = (s_index, index, point)
        if best_hit is None:
            self._hovered_point = None
            return None
        s_index, index, point = best_hit
        self._hovered_point = (s_index, index)
        series = self._points[s_index]
        x, y = series.points[index]
        lines = [
            (self.color_for(s_index), "x", self._x_formatter(x)),
            (self.color_for(s_index), "y", self.format(y)),
        ]
        size = series.size_at(index)
        if size is not None:
            lines.append(
                (self.color_for(s_index), i18n.tr("size"), self.format(size))
            )
        anchor = QtCore.QPointF(
            point.x(), point.y() - self.radius_for(s_index, index)
        )
        return s_index, base.HoverInfo(series.name, lines, anchor)

    @override
    def _set_hover(self, hit: tuple[int, base.HoverInfo] | None) -> None:
        if hit is None:
            self._hovered_point = None
        super()._set_hover(hit)

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, 280)
