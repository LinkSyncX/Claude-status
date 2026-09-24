"""雷达图：多个分类沿圆周分布，每个系列绘制为一个多边形。"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.charts import base
from md3.components.charts import model
from md3.core import typography

LEVELS = 4
LINE_WIDTH = 2.0
POINT_RADIUS = 3.5
HOVER_POINT_RADIUS = 5.5
AREA_ALPHA = 0.22
LABEL_GAP = 12.0
LABEL_MAX_WIDTH = 88.0
HOVER_DEGREES = 20.0


class RadarChart(base.Chart):
    """雷达图。

    Args:
        series: 数据系列，每个值对应一个分类轴。
        categories: 分类（轴）名称，至少 3 个。
        levels: 同心网格的层数。
        fill: 是否填充多边形。
        title: 标题。
        show_legend: 是否显示图例。
        animated: 是否播放入场动画（多边形自中心展开）。
        parent: 父控件。
    """

    def __init__(
        self,
        series: list[model.Series] | None = None,
        categories: list[str] | None = None,
        levels: int = LEVELS,
        fill: bool = True,
        title: str = "",
        show_legend: bool = True,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            series, categories, title, show_legend, animated, parent
        )
        self._levels = max(1, levels)
        self._fill = fill
        self._maximum: float | None = None

    def set_fill(self, fill: bool) -> None:
        """设置是否填充多边形。"""
        self._fill = fill
        self.update()

    def set_maximum(self, maximum: float | None) -> None:
        """固定最外圈对应的数值（None 表示按数据自动取整齐上限）。"""
        self._maximum = maximum
        self.update()

    def axis_count(self) -> int:
        """分类轴数量。"""
        return self.category_count()

    def maximum(self) -> float:
        """最外圈对应的数值。"""
        if self._maximum is not None:
            return self._maximum
        values = [
            v
            for i in self.visible_series_indices()
            for v in self._series[i].values
        ]
        peak = max(values, default=0.0)
        if peak <= 0:
            return 1.0
        return model.nice_ticks(0.0, peak, self._levels)[-1]

    # ---- 几何 -------------------------------------------------------------

    def geometry(self, rect: QtCore.QRectF) -> tuple[QtCore.QPointF, float]:
        """返回 (圆心, 半径)，为分类标签预留空间。"""
        line = self.theme.style(base.AXIS_STYLE).line_height
        reserve = LABEL_MAX_WIDTH / 2 + LABEL_GAP
        radius = min(
            rect.width() / 2 - reserve, rect.height() / 2 - line - LABEL_GAP
        )
        return rect.center(), max(8.0, radius)

    def angle_for(self, index: int) -> float:
        """第 index 个轴的角度（弧度，12 点为 0，顺时针）。"""
        return 2 * math.pi * index / max(1, self.axis_count())

    def point_for(
        self, center: QtCore.QPointF, radius: float, index: int, value: float
    ) -> QtCore.QPointF:
        """数值在第 index 个轴上的坐标。"""
        angle = self.angle_for(index)
        distance = radius * max(0.0, value) / self.maximum()
        return QtCore.QPointF(
            center.x() + distance * math.sin(angle),
            center.y() - distance * math.cos(angle),
        )

    def polygon(
        self, s_index: int, center: QtCore.QPointF, radius: float
    ) -> QtGui.QPolygonF:
        """第 s_index 个系列的多边形（已应用入场进度）。"""
        polygon = QtGui.QPolygonF()
        count = self.axis_count()
        for index in range(count):
            value = self.displayed_value(s_index, index) * self.progress
            polygon.append(self.point_for(center, radius, index, value))
        return polygon

    # ---- 绘制 -------------------------------------------------------------

    def _paint_grid(
        self, painter: QtGui.QPainter, center: QtCore.QPointF, radius: float
    ) -> None:
        count = self.axis_count()
        grid = QtGui.QPen(self.color("outline_variant"), base.GRID_WIDTH)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        for level in range(1, self._levels + 1):
            ring = QtGui.QPolygonF()
            for index in range(count):
                ring.append(
                    self.point_for(
                        center,
                        radius,
                        index,
                        self.maximum() * level / self._levels,
                    )
                )
            painter.setPen(grid)
            painter.drawPolygon(ring)
        for index in range(count):
            painter.setPen(grid)
            painter.drawLine(
                center, self.point_for(center, radius, index, self.maximum())
            )
        label_color = self.color("on_surface_variant")
        style = self.theme.style(base.AXIS_STYLE)
        for index in range(count):
            tip = self.point_for(
                center,
                radius + LABEL_GAP + style.line_height / 2,
                index,
                self.maximum(),
            )
            angle = self.angle_for(index)
            horizontal = math.sin(angle)
            if horizontal > 0.2:
                align = QtCore.Qt.AlignmentFlag.AlignLeft
                left = tip.x()
            elif horizontal < -0.2:
                align = QtCore.Qt.AlignmentFlag.AlignRight
                left = tip.x() - LABEL_MAX_WIDTH
            else:
                align = QtCore.Qt.AlignmentFlag.AlignHCenter
                left = tip.x() - LABEL_MAX_WIDTH / 2
            highlight = index == self.hovered_index
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    left,
                    tip.y() - style.line_height / 2,
                    LABEL_MAX_WIDTH,
                    style.line_height,
                ),
                self.category_label(index),
                base.AXIS_STYLE,
                self.color("on_surface") if highlight else label_color,
                align | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        # 刻度值沿第一根轴标注。
        for level in range(1, self._levels + 1):
            value = self.maximum() * level / self._levels
            point = self.point_for(center, radius, 0, value)
            typography.paint_text(
                painter,
                QtCore.QRectF(point.x() + 4, point.y() - 8, 60, 16),
                self.format(value),
                typography.TypeRole.LABEL_SMALL,
                label_color,
                elide=False,
            )

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        if self.axis_count() < 3:
            self._paint_empty(painter, rect)
            return
        center, radius = self.geometry(rect)
        self._paint_grid(painter, center, radius)
        hovered = self.hovered_index
        if hovered >= 0:
            pen = QtGui.QPen(self.color("outline"), 1.5)
            painter.setPen(pen)
            painter.drawLine(
                center, self.point_for(center, radius, hovered, self.maximum())
            )
        for s_index in self.visible_series_indices():
            color = self.color_for(s_index)
            polygon = self.polygon(s_index, center, radius)
            if self._fill:
                fill = QtGui.QColor(color)
                fill.setAlphaF(AREA_ALPHA)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(fill)
                painter.drawPolygon(polygon)
            pen = QtGui.QPen(color, LINE_WIDTH)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPolygon(polygon)
            painter.setPen(QtGui.QPen(self.color("surface"), 1.5))
            painter.setBrush(color)
            for index, point in enumerate(polygon):
                size = HOVER_POINT_RADIUS if index == hovered else POINT_RADIUS
                painter.drawEllipse(point, size, size)

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        count = self.axis_count()
        if count < 3:
            return None
        rect = self.content_rect()
        center, radius = self.geometry(rect)
        dx = position.x() - center.x()
        dy = position.y() - center.y()
        if math.hypot(dx, dy) > radius + LABEL_GAP + LABEL_MAX_WIDTH / 2:
            return None
        degrees = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0
        step = 360.0 / count
        index = round(degrees / step) % count
        offset = abs(((degrees - index * step) + 180.0) % 360.0 - 180.0)
        if offset > min(HOVER_DEGREES, step / 2):
            return None
        lines = []
        tops = []
        for s_index in self.visible_series_indices():
            series = self._series[s_index]
            value = series.values[index] if index < len(series.values) else 0.0
            lines.append(
                (self.color_for(s_index), series.name, self.format(value))
            )
            tops.append(self.point_for(center, radius, index, value))
        if not lines:
            return None
        anchor = max(
            tops,
            key=lambda p: math.hypot(p.x() - center.x(), p.y() - center.y()),
        )
        return index, base.HoverInfo(self.category_label(index), lines, anchor)

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(320, 320)
