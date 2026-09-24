"""仪表盘：在 240° 圆弧上显示单个数值及其所处区间。"""

from __future__ import annotations

import dataclasses
import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.charts import base
from md3.components.charts import palette
from md3.core import animation
from md3.core import typography
from md3.tokens import motion
from md3.tokens import typography as typography_tokens

SWEEP_DEGREES = 240.0
START_DEGREES = -120.0  # 相对 12 点方向，顺时针为正
TRACK_RATIO = 0.16
TRACK_GAP = 4.0
VALUE_STYLE = typography_tokens.TypeRole.DISPLAY_SMALL
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
BOUND_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
TARGET_WIDTH = 3.0


@dataclasses.dataclass
class GaugeBand:
    """仪表盘上的一个颜色区间。

    Attributes:
        start: 区间起点（数值）。
        end: 区间终点（数值）。
        color: 颜色（``QColor``、色彩角色名或十六进制）。
    """

    start: float
    end: float
    color: QtGui.QColor | str


class GaugeChart(base.Chart):
    """仪表盘。

    Args:
        value: 当前值。
        minimum: 最小值。
        maximum: 最大值。
        bands: 背景颜色区间；为空时轨道使用 ``secondary_container``。
        label: 数值下方的说明文字（如单位）。
        target: 可选的目标值，在弧上以短线标出。
        title: 标题。
        animated: 是否播放入场动画（指示弧自起点生长）。
        parent: 父控件。
    """

    value_changed = QtCore.Signal(float)

    def __init__(
        self,
        value: float = 0.0,
        minimum: float = 0.0,
        maximum: float = 100.0,
        bands: list[GaugeBand] | None = None,
        label: str = "",
        target: float | None = None,
        title: str = "",
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(None, None, title, False, animated, parent)
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._value = self._clamp(value)
        self._bands = list(bands or [])
        self._label = label
        self._target = target
        # 显示值以进度弹簧追随目标值。
        self._display = animation.AnimatedFloat(self, self._value, self.update)

    # ---- 数据 -------------------------------------------------------------

    def _clamp(self, value: float) -> float:
        return max(self._minimum, min(self._maximum, float(value)))

    @property
    def value(self) -> float:
        """当前值。"""
        return self._value

    def set_value(self, value: float) -> None:
        """设置数值，指示弧平滑过渡。"""
        value = self._clamp(value)
        if value != self._value:
            self._value = value
            self.value_changed.emit(value)
        if self._animated:
            self._display.spring_to(value, motion.PROGRESS_SPRING)
        else:
            self._display.set(value)
        self.update()

    @property
    def displayed(self) -> float:
        """当前绘制的数值。"""
        return self._display.value

    @property
    def bounds(self) -> tuple[float, float]:
        """(最小值, 最大值)。"""
        return self._minimum, self._maximum

    def set_bounds(self, minimum: float, maximum: float) -> None:
        """设置范围。"""
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")
        self._minimum, self._maximum = float(minimum), float(maximum)
        self._value = self._clamp(self._value)
        self._display.set(self._value)
        self.update()

    def set_bands(self, bands: list[GaugeBand]) -> None:
        """设置颜色区间。"""
        self._bands = list(bands)
        self.update()

    def set_label(self, label: str) -> None:
        """设置说明文字。"""
        self._label = label
        self.update()

    def set_target(self, target: float | None) -> None:
        """设置目标值标记。"""
        self._target = target
        self.update()

    @override
    def has_data(self) -> bool:
        return True

    def fraction(self, value: float) -> float:
        """数值在范围内的比例 0–1。"""
        span = self._maximum - self._minimum
        return (self._clamp(value) - self._minimum) / span

    def band_color(self, value: float) -> QtGui.QColor:
        """数值所在区间的颜色；不在任何区间时为 ``primary``。"""
        for band in self._bands:
            if band.start <= value <= band.end:
                return palette.resolve_color(
                    self.theme, band.color, self.color("primary")
                )
        return self.color("primary")

    # ---- 几何 -------------------------------------------------------------

    def geometry(
        self, rect: QtCore.QRectF
    ) -> tuple[QtCore.QPointF, float, float]:
        """返回 (圆心, 半径, 弧粗细)。弧的开口朝下，因此圆心偏下。"""
        # 240° 弧的纵向占比：顶部为 r，底部为 r·cos(60°) = r/2。
        width_limit = rect.width() / 2
        height_limit = rect.height() / 1.5
        radius = max(16.0, min(width_limit, height_limit))
        thickness = max(6.0, radius * TRACK_RATIO)
        radius -= thickness / 2
        center = QtCore.QPointF(
            rect.center().x(), rect.top() + radius + thickness / 2
        )
        return center, radius, thickness

    @staticmethod
    def _draw_arc(
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        radius: float,
        start: float,
        sweep: float,
    ) -> None:
        """按顺时针度数（0 为 12 点）绘制弧。"""
        rect = QtCore.QRectF(
            center.x() - radius, center.y() - radius, 2 * radius, 2 * radius
        )
        painter.drawArc(rect, round((90.0 - start) * 16), round(-sweep * 16))

    def _point_at(
        self, center: QtCore.QPointF, radius: float, degrees: float
    ) -> QtCore.QPointF:
        angle = math.radians(degrees)
        return QtCore.QPointF(
            center.x() + radius * math.sin(angle),
            center.y() - radius * math.cos(angle),
        )

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        center, radius, thickness = self.geometry(rect)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        pen = QtGui.QPen(self.color("secondary_container"), thickness)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        # 轨道：无区间时为整段，有区间时按区间着色（区间之间留空隙）。
        if not self._bands:
            painter.setPen(pen)
            self._draw_arc(
                painter, center, radius, START_DEGREES, SWEEP_DEGREES
            )
        else:
            pen.setCapStyle(QtCore.Qt.PenCapStyle.FlatCap)
            gap = math.degrees(TRACK_GAP / radius)
            for band in self._bands:
                start = (
                    START_DEGREES + self.fraction(band.start) * SWEEP_DEGREES
                )
                end = START_DEGREES + self.fraction(band.end) * SWEEP_DEGREES
                color = palette.resolve_color(
                    self.theme, band.color, self.color("primary")
                )
                faded = QtGui.QColor(color)
                faded.setAlphaF(0.32)
                pen.setColor(faded)
                painter.setPen(pen)
                self._draw_arc(
                    painter,
                    center,
                    radius,
                    start + gap / 2,
                    max(0.0, end - start - gap),
                )
        # 指示弧。
        shown = self.displayed
        fraction = self.fraction(shown) * self.progress
        sweep = fraction * SWEEP_DEGREES
        if sweep > 0.1:
            active = QtGui.QPen(self.band_color(shown), thickness)
            active.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(active)
            self._draw_arc(painter, center, radius, START_DEGREES, sweep)
        # 目标标记。
        if self._target is not None:
            degrees = (
                START_DEGREES + self.fraction(self._target) * SWEEP_DEGREES
            )
            inner = self._point_at(center, radius - thickness / 2 - 4, degrees)
            outer = self._point_at(center, radius + thickness / 2 + 4, degrees)
            marker = QtGui.QPen(self.color("on_surface"), TARGET_WIDTH)
            marker.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            painter.setPen(marker)
            painter.drawLine(inner, outer)
        self._paint_texts(painter, center, radius, thickness)

    def _paint_texts(
        self,
        painter: QtGui.QPainter,
        center: QtCore.QPointF,
        radius: float,
        thickness: float,
    ) -> None:
        value_style = self.theme.style(VALUE_STYLE)
        label_style = self.theme.style(LABEL_STYLE)
        inner = radius - thickness / 2
        width = inner * 1.6
        block = value_style.line_height + (
            label_style.line_height if self._label else 0
        )
        top = center.y() - block / 2 + 4
        typography.paint_text(
            painter,
            QtCore.QRectF(
                center.x() - width / 2, top, width, value_style.line_height
            ),
            self.format(self.displayed),
            VALUE_STYLE,
            self.color("on_surface"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        if self._label:
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    center.x() - width / 2,
                    top + value_style.line_height,
                    width,
                    label_style.line_height,
                ),
                self._label,
                LABEL_STYLE,
                self.color("on_surface_variant"),
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        # 两端的最小 / 最大值。
        bound_style = self.theme.style(BOUND_STYLE)
        color = self.color("on_surface_variant")
        for degrees, value, align in (
            (START_DEGREES, self._minimum, QtCore.Qt.AlignmentFlag.AlignRight),
            (
                START_DEGREES + SWEEP_DEGREES,
                self._maximum,
                QtCore.Qt.AlignmentFlag.AlignLeft,
            ),
        ):
            point = self._point_at(center, radius, degrees)
            left = (
                point.x() - 60 - thickness / 2 - 8
                if align == QtCore.Qt.AlignmentFlag.AlignRight
                else point.x() + thickness / 2 + 8
            )
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    left,
                    point.y() - bound_style.line_height / 2,
                    60,
                    bound_style.line_height,
                ),
                self.format(value),
                BOUND_STYLE,
                color,
                align | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        center, radius, thickness = self.geometry(rect)
        distance = math.hypot(
            position.x() - center.x(), position.y() - center.y()
        )
        if abs(distance - radius) > thickness:
            return None
        degrees = math.degrees(
            math.atan2(position.x() - center.x(), -(position.y() - center.y()))
        )
        if not START_DEGREES <= degrees <= START_DEGREES + SWEEP_DEGREES:
            return None
        lines = [
            (
                self.band_color(self._value),
                i18n.tr("current_value"),
                self.format(self._value),
            )
        ]
        if self._target is not None:
            lines.append(
                (
                    self.color("on_surface"),
                    i18n.tr("target"),
                    self.format(self._target),
                )
            )
        anchor = self._point_at(center, radius + thickness / 2, degrees)
        return 0, base.HoverInfo(
            self._label or self.title or i18n.tr("current_value"),
            lines,
            anchor,
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(280, 220)
