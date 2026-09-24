"""饼图与环形图。"""

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
from md3.tokens import typography as typography_tokens

GAP_DEGREES = 2.0
HOVER_GROW = 6.0
DONUT_RATIO = 0.62
START_ANGLE = 90.0  # 12 点方向
CENTER_VALUE_STYLE = typography_tokens.TypeRole.HEADLINE_SMALL
CENTER_LABEL_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM


class PieChart(base.Chart):
    """饼图 / 环形图。

    数据取第一个系列：``values`` 为各扇区的值，``categories`` 为扇区名称。

    Args:
        values: 各扇区的值。
        categories: 扇区名称。
        donut: 为真时绘制环形图，中心显示总计或悬停值。
        title: 标题。
        center_label: 环形图中心的说明文字（默认为当前语言的"总计"）。
        show_legend: 是否显示图例（含百分比）。
        animated: 是否播放入场动画（扇区顺时针依次展开）。
        parent: 父控件。
    """

    def __init__(
        self,
        values: list[float] | None = None,
        categories: list[str] | None = None,
        donut: bool = True,
        title: str = "",
        center_label: str | None = None,
        show_legend: bool = True,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        series = [model.Series("", list(values or []))]
        super().__init__(
            series, categories, title, show_legend, animated, parent
        )
        self._donut = donut
        self._center_label = (
            i18n.tr("total") if center_label is None else center_label
        )

    @property
    def values(self) -> list[float]:
        """各扇区的值。"""
        return list(self._series[0].values) if self._series else []

    def displayed_values(self) -> list[float]:
        """过渡动画中实际绘制的各扇区值；隐藏的扇区为 0。"""
        if not self._series:
            return []
        return [
            self.displayed_value(0, index) if self.entry_visible(index) else 0.0
            for index in range(len(self._series[0].values))
        ]

    def set_values(
        self, values: list[float], categories: list[str] | None = None
    ) -> None:
        """替换数据。"""
        self.set_data(
            categories if categories is not None else self._categories,
            [model.Series("", list(values))],
        )

    @property
    def donut(self) -> bool:
        """是否为环形图。"""
        return self._donut

    def set_donut(self, donut: bool) -> None:
        """切换饼图 / 环形图。"""
        self._donut = donut
        self.update()

    def total(self) -> float:
        """可见扇区值之和。"""
        return float(
            sum(
                max(0.0, v)
                for index, v in enumerate(self.values)
                if self.entry_visible(index)
            )
        )

    def displayed_total(self) -> float:
        """过渡动画中实际绘制的总和。"""
        return float(sum(max(0.0, v) for v in self.displayed_values()))

    @override
    def color_for(self, index: int) -> QtGui.QColor:
        colors = palette.series_colors(self.theme, max(1, len(self.values)))
        return colors[index % len(colors)]

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        total = self.total()
        entries = []
        for index, value in enumerate(self.values):
            if self.entry_visible(index) and total > 0:
                share = model.format_percent(value / total)
            else:
                share = "0%"
            entries.append(
                (self.color_for(index), f"{self.category_label(index)} {share}")
            )
        return entries

    # ---- 几何 -------------------------------------------------------------

    def _geometry(
        self, rect: QtCore.QRectF
    ) -> tuple[QtCore.QPointF, float, float]:
        """返回 (圆心, 外半径, 环宽)。"""
        side = min(rect.width(), rect.height()) - 2 * HOVER_GROW
        outer = max(8.0, side / 2)
        ring = outer * (1 - DONUT_RATIO) if self._donut else outer
        return rect.center(), outer, ring

    def slices(self) -> list[tuple[float, float]]:
        """各扇区的 (起始角, 扫过角)，单位为度、顺时针、12 点为 0。

        使用过渡动画中的显示值，隐藏的扇区扫过角为 0。
        """
        values = self.displayed_values()
        total = float(sum(max(0.0, v) for v in values))
        result = []
        angle = 0.0
        for value in values:
            sweep = 360.0 * max(0.0, value) / total if total > 0 else 0.0
            result.append((angle, sweep))
            angle += sweep
        return result

    def _slice_at(self, position: QtCore.QPointF, rect: QtCore.QRectF) -> int:
        center, outer, ring = self._geometry(rect)
        dx = position.x() - center.x()
        dy = position.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance > outer + HOVER_GROW or distance < outer - ring - 2:
            return -1
        angle = (math.degrees(math.atan2(dx, -dy)) + 360.0) % 360.0
        for index, (start, sweep) in enumerate(self.slices()):
            if start <= angle < start + sweep:
                return index
        return -1

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        center, outer, ring = self._geometry(rect)
        total = self.displayed_total()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        shown = 360.0 * self.progress
        for index, (start, sweep) in enumerate(self.slices()):
            if sweep <= 0 or start >= shown:
                continue
            sweep = min(sweep, shown - start)
            grow = HOVER_GROW if index == self.hovered_index else 0.0
            self._paint_slice(
                painter, center, outer + grow, ring + grow, start, sweep, index
            )
        if self._donut:
            self._paint_center(painter, center, outer - ring, total)

    def _paint_slice(
        self,
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        outer: float,
        ring: float,
        start: float,
        sweep: float,
        index: int,
    ) -> None:
        # 扇区之间留 2 度间隙；间隙不足时按比例缩小。
        gap = min(GAP_DEGREES, sweep / 3)
        start += gap / 2
        sweep -= gap
        if sweep <= 0.1:
            return
        # Qt 的角度以 3 点方向为 0、逆时针为正（单位 1/16 度）。
        qt_start = START_ANGLE - start
        path = QtGui.QPainterPath()
        outer_rect = QtCore.QRectF(
            center.x() - outer, center.y() - outer, 2 * outer, 2 * outer
        )
        if self._donut:
            inner = outer - ring
            inner_rect = QtCore.QRectF(
                center.x() - inner, center.y() - inner, 2 * inner, 2 * inner
            )
            path.arcMoveTo(outer_rect, qt_start)
            path.arcTo(outer_rect, qt_start, -sweep)
            path.arcTo(inner_rect, qt_start - sweep, sweep)
            path.closeSubpath()
        else:
            path.moveTo(center)
            path.arcTo(outer_rect, qt_start, -sweep)
            path.closeSubpath()
        painter.setBrush(self.color_for(index))
        painter.drawPath(path)

    def _paint_center(
        self,
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        inner_radius: float,
        total: float,
    ) -> None:
        hovered = self.hovered_index
        if 0 <= hovered < len(self.values):
            value_text = self.format(self.values[hovered])
            label = self.category_label(hovered)
        else:
            value_text = self.format(total)
            label = self._center_label
        value_style = self.theme.style(CENTER_VALUE_STYLE)
        label_style = self.theme.style(CENTER_LABEL_STYLE)
        block = value_style.line_height + label_style.line_height
        width = inner_radius * 2 - 8
        top = center.y() - block / 2
        typography.paint_text(
            painter,
            QtCore.QRectF(
                center.x() - width / 2, top, width, value_style.line_height
            ),
            value_text,
            CENTER_VALUE_STYLE,
            self.color("on_surface"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        typography.paint_text(
            painter,
            QtCore.QRectF(
                center.x() - width / 2,
                top + value_style.line_height,
                width,
                label_style.line_height,
            ),
            label,
            CENTER_LABEL_STYLE,
            self.color("on_surface_variant"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        index = self._slice_at(position, rect)
        if index < 0:
            return None
        center, outer, _ = self._geometry(rect)
        start, sweep = self.slices()[index]
        middle = math.radians(start + sweep / 2)
        anchor = QtCore.QPointF(
            center.x() + math.sin(middle) * (outer + HOVER_GROW),
            center.y() - math.cos(middle) * (outer + HOVER_GROW),
        )
        total = self.total()
        value = self.values[index]
        share = model.format_percent(value / total) if total > 0 else "0%"
        return index, base.HoverInfo(
            self.category_label(index),
            [(self.color_for(index), self.format(value), share)],
            anchor,
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(280, 280)
