"""折线图：可平滑、可填充面积、可堆叠、可显示数据点。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.charts import base
from md3.components.charts import model

LINE_WIDTH = 2.5
POINT_RADIUS = 4.0
HOVER_POINT_RADIUS = 6.0
AREA_ALPHA = 0.28
STACKED_AREA_ALPHA = 0.55
SMOOTH_TENSION = 0.5


class LineChart(base.CartesianChart):
    """折线图。

    Args:
        series: 数据系列。
        categories: 分类标签。
        smooth: 是否用三次贝塞尔曲线平滑连接。
        fill_area: 是否在折线下方填充渐变面积。
        stacked: 为真时各系列按分类累加，形成堆叠面积图。
        show_points: 是否绘制数据点。
        title: 标题。
        show_legend: 是否显示图例。
        animated: 是否播放入场动画（自左向右揭示）。
        parent: 父控件。
    """

    def __init__(
        self,
        series: list[model.Series] | None = None,
        categories: list[str] | None = None,
        smooth: bool = True,
        fill_area: bool = False,
        stacked: bool = False,
        show_points: bool = True,
        title: str = "",
        show_legend: bool = True,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            series, categories, title, show_legend, animated, parent
        )
        self._smooth = smooth
        self._fill_area = fill_area
        self._stacked = stacked
        self._show_points = show_points

    @property
    def smooth(self) -> bool:
        """是否平滑。"""
        return self._smooth

    def set_smooth(self, smooth: bool) -> None:
        """设置是否平滑。"""
        self._smooth = smooth
        self.update()

    @property
    def fill_area(self) -> bool:
        """是否填充面积。"""
        return self._fill_area

    def set_fill_area(self, fill: bool) -> None:
        """设置是否填充面积。"""
        self._fill_area = fill
        self.update()

    @property
    def stacked(self) -> bool:
        """是否堆叠。"""
        return self._stacked

    def set_stacked(self, stacked: bool) -> None:
        """切换堆叠面积 / 普通折线。"""
        self._stacked = stacked
        self.update()

    def set_show_points(self, show: bool) -> None:
        """设置是否绘制数据点。"""
        self._show_points = show
        self.update()

    @override
    def data_extent(self) -> tuple[float, float]:
        if not self._stacked:
            return super().data_extent()
        return self.stacked_extent()

    def stacked_value(self, s_index: int, index: int) -> float:
        """堆叠模式下第 s_index 个系列在分类 index 处的累计值（含自身）。"""
        total = 0.0
        for other in self.visible_series_indices():
            total += self.displayed_value(other, index)
            if other == s_index:
                break
        return total

    def series_points(
        self, s_index: int, plot: QtCore.QRectF, low: float, high: float
    ) -> list[QtCore.QPointF]:
        """第 s_index 个系列的数据点坐标（堆叠时为累计值）。"""
        points = []
        for index in range(self.series_length(s_index)):
            value = (
                self.stacked_value(s_index, index)
                if self._stacked
                else self.displayed_value(s_index, index)
            )
            slot = self.category_slot(index, plot)
            points.append(
                QtCore.QPointF(
                    slot.center().x(), self.value_to_y(value, plot, low, high)
                )
            )
        return points

    def _line_path(self, points: list[QtCore.QPointF]) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        if not self._smooth or len(points) < 3:
            for point in points[1:]:
                path.lineTo(point)
            return path
        # Catmull-Rom 转三次贝塞尔，端点使用自身作为邻点。
        for index in range(len(points) - 1):
            p0 = points[index - 1] if index > 0 else points[index]
            p1 = points[index]
            p2 = points[index + 1]
            p3 = points[index + 2] if index + 2 < len(points) else p2
            c1 = QtCore.QPointF(
                p1.x() + (p2.x() - p0.x()) * SMOOTH_TENSION / 3,
                p1.y() + (p2.y() - p0.y()) * SMOOTH_TENSION / 3,
            )
            c2 = QtCore.QPointF(
                p2.x() - (p3.x() - p1.x()) * SMOOTH_TENSION / 3,
                p2.y() - (p3.y() - p1.y()) * SMOOTH_TENSION / 3,
            )
            path.cubicTo(c1, c2, p2)
        return path

    def _area_path(
        self,
        path: QtGui.QPainterPath,
        points: list[QtCore.QPointF],
        lower: list[QtCore.QPointF] | None,
        baseline: float,
    ) -> QtGui.QPainterPath:
        """折线与下边界（前一系列的折线或基线）之间的面积。"""
        area = QtGui.QPainterPath(path)
        if lower:
            reverse = list(reversed(lower))
            area.lineTo(reverse[0])
            back = self._line_path(reverse)
            area.connectPath(back)
        else:
            area.lineTo(points[-1].x(), baseline)
            area.lineTo(points[0].x(), baseline)
        area.closeSubpath()
        return area

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        low, high, ticks = self.value_range()
        plot = self.plot_rect(rect, ticks)
        self.paint_axes(painter, plot, low, high, ticks)
        hovered = self.hovered_index
        if hovered >= 0:
            slot = self.category_slot(hovered, plot)
            pen = QtGui.QPen(self.color("outline"), 1)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(
                QtCore.QPointF(slot.center().x(), plot.top()),
                QtCore.QPointF(slot.center().x(), plot.bottom()),
            )
        # 入场动画：自左向右揭示。
        reveal = plot.width() * self.progress
        painter.save()
        painter.setClipRect(
            QtCore.QRectF(
                plot.left() - HOVER_POINT_RADIUS,
                plot.top() - HOVER_POINT_RADIUS,
                reveal + 2 * HOVER_POINT_RADIUS,
                plot.height() + 2 * HOVER_POINT_RADIUS,
            )
        )
        baseline = self.value_to_y(0.0, plot, low, high)
        visible = self.visible_series_indices()
        # 堆叠时先画上层系列，使面积互不遮挡；普通模式按顺序绘制。
        order = list(reversed(visible)) if self._stacked else visible
        all_points = {
            s_index: self.series_points(s_index, plot, low, high)
            for s_index in visible
        }
        for s_index in order:
            points = all_points[s_index]
            if not points:
                continue
            color = self.color_for(s_index)
            path = self._line_path(points)
            if (self._fill_area or self._stacked) and len(points) > 1:
                lower = None
                if self._stacked:
                    position = visible.index(s_index)
                    if position > 0:
                        lower = all_points[visible[position - 1]]
                area = self._area_path(path, points, lower, baseline)
                if self._stacked:
                    fill = QtGui.QColor(color)
                    fill.setAlphaF(STACKED_AREA_ALPHA)
                    painter.fillPath(area, fill)
                else:
                    gradient = QtGui.QLinearGradient(
                        QtCore.QPointF(0, plot.top()),
                        QtCore.QPointF(0, baseline),
                    )
                    top = QtGui.QColor(color)
                    top.setAlphaF(AREA_ALPHA)
                    bottom = QtGui.QColor(color)
                    bottom.setAlphaF(0.0)
                    gradient.setColorAt(0.0, top)
                    gradient.setColorAt(1.0, bottom)
                    painter.fillPath(area, gradient)
            pen = QtGui.QPen(color, LINE_WIDTH)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
            if self._show_points or hovered >= 0:
                painter.setPen(QtGui.QPen(self.color("surface"), 2))
                painter.setBrush(color)
                for index, point in enumerate(points):
                    if not self._show_points and index != hovered:
                        continue
                    radius = (
                        HOVER_POINT_RADIUS if index == hovered else POINT_RADIUS
                    )
                    painter.drawEllipse(point, radius, radius)
        painter.restore()

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
        if index < 0:
            return None
        slot = self.category_slot(index, plot)
        ys = []
        lines = []
        for s_index in self.visible_series_indices():
            series = self._series[s_index]
            if index >= self.series_length(s_index):
                continue
            value = self.value_at(s_index, index)
            shown = (
                self.stacked_value(s_index, index) if self._stacked else value
            )
            ys.append(self.value_to_y(shown, plot, low, high))
            lines.append(
                (self.color_for(s_index), series.name, self.format(value))
            )
        if not lines:
            return None
        return index, base.HoverInfo(
            self.category_label(index),
            lines,
            QtCore.QPointF(slot.center().x(), min(ys)),
        )
