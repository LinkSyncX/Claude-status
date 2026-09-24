"""进度指示器（Progress indicators）。

线性指示器采用 M3 2023 年更新后的样式：4dp 轨道、活动段与轨道之间
留 4dp 空隙、轨道末端有 4dp 停止点。两种指示器都支持确定与不确定态：

- 确定态数值变化用 ``motion.PROGRESS_SPRING`` 平缓追上目标；
- 线性不确定态为两条相继扫过轨道的活动段（1750ms 周期）；
- 环形不确定态为"后撤"动画：弧长在 10%–87% 之间呼吸，同时整体匀速
  旋转并每 1.5s 额外快转 90°（6s 周期）。

节奏参数取自 Compose Material3 的 ``ProgressIndicator``。
"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import widget
from md3.tokens import motion
from md3.tokens import shape as shape_tokens

TRACK_HEIGHT = 4.0
TRACK_GAP = 4.0
STOP_SIZE = 4.0
CIRCULAR_SIZE = 48.0
CIRCULAR_STROKE = 4.0

# 线性不确定态：四条轨道各自的（起始延迟, 时长），周期 1750ms。
LINEAR_CYCLE_MS = 1750
LINEAR_FIRST_HEAD = (0, 1000)
LINEAR_FIRST_TAIL = (250, 1000)
LINEAR_SECOND_HEAD = (650, 850)
LINEAR_SECOND_TAIL = (900, 850)
LINEAR_INDETERMINATE_EASING = motion.EMPHASIZED_ACCELERATE

# 环形不确定态：6s 内匀速旋转 1080°，每 1500ms 用 300ms 额外转 90°，
# 弧长在前 3s 由 10% 增至 87%、后 3s 退回。
CIRCULAR_CYCLE_MS = 6000
CIRCULAR_ROTATION_DEGREES = 1080.0
CIRCULAR_SPIN_INTERVAL_MS = 1500
CIRCULAR_SPIN_MS = 300
CIRCULAR_SPIN_DEGREES = 90.0
CIRCULAR_MIN_SWEEP = 0.1
CIRCULAR_MAX_SWEEP = 0.87


def linear_indeterminate_segments(
    elapsed_ms: float,
) -> list[tuple[float, float]]:
    """线性不确定态在 ``elapsed_ms`` 时的活动段（起点, 终点）列表。"""
    phase = elapsed_ms % LINEAR_CYCLE_MS
    easing = LINEAR_INDETERMINATE_EASING
    segments: list[tuple[float, float]] = []
    for head_spec, tail_spec in (
        (LINEAR_FIRST_HEAD, LINEAR_FIRST_TAIL),
        (LINEAR_SECOND_HEAD, LINEAR_SECOND_TAIL),
    ):
        head = animation.keyframe(phase, *head_spec, easing)
        tail = animation.keyframe(phase, *tail_spec, easing)
        if head - tail > 1e-4:
            segments.append((tail, head))
    segments.sort()
    return segments


def circular_indeterminate_arc(elapsed_ms: float) -> tuple[float, float]:
    """环形不确定态在 ``elapsed_ms`` 时的（起始角, 弧长比例）。

    起始角为顺时针度数（0 为 12 点方向），弧长比例为整圈的分数。
    """
    phase = elapsed_ms % CIRCULAR_CYCLE_MS
    rotation = phase / CIRCULAR_CYCLE_MS * CIRCULAR_ROTATION_DEGREES
    for index in range(CIRCULAR_CYCLE_MS // CIRCULAR_SPIN_INTERVAL_MS):
        rotation += CIRCULAR_SPIN_DEGREES * animation.keyframe(
            phase,
            index * CIRCULAR_SPIN_INTERVAL_MS,
            CIRCULAR_SPIN_MS,
            motion.EMPHASIZED_DECELERATE,
        )
    half = CIRCULAR_CYCLE_MS / 2
    if phase < half:
        grow = animation.keyframe(phase, 0, half, motion.STANDARD)
    else:
        grow = 1.0 - animation.keyframe(phase, half, half, motion.STANDARD)
    sweep = (
        CIRCULAR_MIN_SWEEP + (CIRCULAR_MAX_SWEEP - CIRCULAR_MIN_SWEEP) * grow
    )
    return rotation % 360.0, sweep


class ProgressIndicator(widget.MaterialWidget):
    """进度指示器公共基类：数值、不确定态与帧时钟。

    帧时钟只在控件可见且 ``needs_clock`` 为真时运行，隐藏后自动停止。

    Args:
        value: 进度 0–1；None 表示不确定态。
        parent: 父控件。
    """

    value_changed = QtCore.Signal(float)

    def __init__(
        self,
        value: float | None,
        parent: QtWidgets.QWidget | None,
    ) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._indeterminate = value is None
        self._clock = animation.FrameClock(self)
        self._clock.ticked.connect(self._tick)
        if value is not None:
            self._value = self._clamp(value)
        # 确定态下实际绘制的进度，向目标值平滑过渡。
        self._display = animation.AnimatedFloat(
            self, self._value, self._display_changed
        )

    # ---- 状态 -------------------------------------------------------------

    @staticmethod
    def _clamp(value: float) -> float:
        return max(0.0, min(1.0, float(value)))

    @property
    def value(self) -> float:
        """当前进度（0–1）。"""
        return self._value

    def set_value(self, value: float) -> None:
        """设置进度并退出不确定态。

        从不确定态切换时活动段自轨道起点生长到目标值。
        """
        value = self._clamp(value)
        if self._indeterminate:
            self.set_indeterminate(False)
            self._display.set(0.0)
        if value != self._value:
            self._value = value
            self.value_changed.emit(value)
            accessibility.notify_value_changed(self, self.accessible_value())
        self._display.spring_to(value, motion.PROGRESS_SPRING)
        self.update()

    @property
    def display_value(self) -> float:
        """当前绘制的进度（过渡中可能与目标值不同）。"""
        return self._display.value

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ProgressBar

    @override
    def accessible_value(self) -> str:
        if self._indeterminate:
            return ""
        return f"{round(self._value * 100)}%"

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        state.busy = self._indeterminate
        state.readOnly = True

    @property
    def indeterminate(self) -> bool:
        """是否为不确定态。"""
        return self._indeterminate

    def set_indeterminate(self, indeterminate: bool) -> None:
        """切换不确定态。"""
        indeterminate = bool(indeterminate)
        if indeterminate == self._indeterminate:
            return
        self._indeterminate = indeterminate
        if indeterminate:
            self._clock.restart()
        self.refresh_clock()
        self.updateGeometry()
        self.update()

    # ---- 动画驱动 ---------------------------------------------------------

    def elapsed_ms(self) -> int:
        """帧时钟已运行的毫秒数。"""
        return self._clock.elapsed_ms()

    def needs_clock(self) -> bool:
        """是否需要逐帧重绘；子类可扩展（例如波浪运动）。"""
        return self._indeterminate

    def refresh_clock(self) -> None:
        """按 ``needs_clock`` 与可见性启动或停止帧时钟。"""
        if self.needs_clock() and self.isVisible():
            self._clock.start()
        else:
            self._clock.stop()

    def _tick(self) -> None:
        """每帧回调，默认仅重绘。"""
        self.update()

    def _display_changed(self) -> None:
        """绘制进度变化时的钩子，默认重绘。"""
        self.update()

    def active_color(self) -> QtGui.QColor:
        """活动指示器颜色。"""
        return self.color("primary")

    def track_color(self) -> QtGui.QColor:
        """轨道颜色。"""
        return self.color("secondary_container")

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self.refresh_clock()

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self._clock.stop()


class LinearProgressIndicator(ProgressIndicator):
    """线性进度指示器。

    Args:
        value: 进度 0–1；None 表示不确定态。
        thickness: 轨道粗细（dp），规范默认 4。
        parent: 父控件。
    """

    def __init__(
        self,
        value: float | None = 0.0,
        thickness: float = TRACK_HEIGHT,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(value, parent)
        self._thickness = max(1.0, float(thickness))
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def thickness(self) -> float:
        """轨道与活动指示器的粗细（dp）。"""
        return self._thickness

    def set_thickness(self, thickness: float) -> None:
        """设置粗细（dp）。"""
        self._thickness = max(1.0, float(thickness))
        self.updateGeometry()
        self.update()

    def container_height(self) -> float:
        """控件高度（dp）；波浪变体会在此基础上加上振幅。"""
        return self._thickness

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(240, math.ceil(self.container_height()))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(48, math.ceil(self.container_height()))

    def segments(self) -> list[tuple[float, float]]:
        """当前活动段（起点, 终点）的轨道比例列表。"""
        if self._indeterminate:
            return linear_indeterminate_segments(self.elapsed_ms())
        shown = self.display_value
        return [(0.0, shown)] if shown > 0 else []

    def track_rect(self) -> QtCore.QRectF:
        """轨道矩形（垂直居中，高度为粗细）。"""
        rect = QtCore.QRectF(self.rect())
        return QtCore.QRectF(
            rect.left(),
            rect.center().y() - self._thickness / 2,
            rect.width(),
            self._thickness,
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        track = self.track_rect()
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        segments = self.segments()
        pixel_segments = [
            self._pixel_extent(track, start, end) for start, end in segments
        ]
        self._paint_track(painter, track, pixel_segments)
        for left, right in pixel_segments:
            self.paint_active_segment(painter, track, left, right)
        if not self._indeterminate:
            self._paint_stop(painter, track, pixel_segments)
        painter.restore()

    def _pixel_extent(
        self, track: QtCore.QRectF, start: float, end: float
    ) -> tuple[float, float]:
        """把比例区间换算为像素区间，并保证至少显示一个圆点。"""
        left = track.left() + start * track.width()
        right = track.left() + end * track.width()
        if right - left < self._thickness:
            right = left + self._thickness
        if right > track.right():
            right = track.right()
            left = max(track.left(), right - self._thickness)
        return left, right

    def _paint_track(
        self,
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        segments: list[tuple[float, float]],
    ) -> None:
        cursor = track.left()
        for left, right in segments:
            self._fill_segment(
                painter, track, cursor, left - TRACK_GAP, self.track_color()
            )
            cursor = right + TRACK_GAP
        end = track.right()
        if not self._indeterminate:
            end -= STOP_SIZE + TRACK_GAP
        self._fill_segment(painter, track, cursor, end, self.track_color())

    def _paint_stop(
        self,
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        segments: list[tuple[float, float]],
    ) -> None:
        """轨道末端的停止点：活动段靠近时逐渐缩小直至消失。"""
        size = min(STOP_SIZE, self._thickness)
        left = track.right() - size
        head = segments[-1][1] if segments else track.left()
        if head > left:
            size -= head - left
            left = head
        if size <= 0.5:
            return
        painter.setBrush(self.active_color())
        painter.drawEllipse(
            QtCore.QPointF(left + size / 2, track.center().y()),
            size / 2,
            size / 2,
        )

    def paint_active_segment(
        self,
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        left: float,
        right: float,
    ) -> None:
        """绘制一段活动指示器（像素区间），默认为圆头矩形。"""
        self._fill_segment(painter, track, left, right, self.active_color())

    @staticmethod
    def _fill_segment(
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        left: float,
        right: float,
        color: QtGui.QColor,
    ) -> None:
        left = max(track.left(), left)
        right = min(track.right(), right)
        if right - left < 0.5:
            return
        segment = QtCore.QRectF(left, track.top(), right - left, track.height())
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawPath(
            shape_utils.rounded_rect_path(segment, shape_tokens.SHAPE_FULL)
        )


class CircularProgressIndicator(ProgressIndicator):
    """环形进度指示器。

    Args:
        value: 进度 0–1；None 表示不确定态。
        size: 直径（dp），默认 48。
        show_track: 确定态是否绘制轨道。
        thickness: 描边粗细（dp），规范默认 4。
        parent: 父控件。
    """

    def __init__(
        self,
        value: float | None = 0.0,
        size: float = CIRCULAR_SIZE,
        show_track: bool = True,
        thickness: float = CIRCULAR_STROKE,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(value, parent)
        self._thickness = max(1.0, float(thickness))
        self._size = size
        self._show_track = show_track
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def thickness(self) -> float:
        """描边粗细（dp）。"""
        return self._thickness

    def set_thickness(self, thickness: float) -> None:
        """设置描边粗细（dp）。"""
        self._thickness = max(1.0, float(thickness))
        self.update()

    @property
    def size_dp(self) -> float:
        """直径（dp）。"""
        return self._size

    @override
    def sizeHint(self) -> QtCore.QSize:
        side = math.ceil(self._size)
        return QtCore.QSize(side, side)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    def arc(self) -> tuple[float, float]:
        """当前活动弧的（起始角, 弧长），顺时针度数，0 为 12 点方向。"""
        if self._indeterminate:
            start, fraction = circular_indeterminate_arc(self.elapsed_ms())
            return start, fraction * 360.0
        return 0.0, self.display_value * 360.0

    def ring_rect(self) -> QtCore.QRectF:
        """描边中心线所在的正方形。"""
        rect = QtCore.QRectF(self.rect())
        side = min(rect.width(), rect.height()) - self._thickness
        return QtCore.QRectF(
            rect.center().x() - side / 2,
            rect.center().y() - side / 2,
            side,
            side,
        )

    def gap_degrees(self) -> float:
        """活动弧与轨道之间空隙对应的角度（含圆头）。"""
        ring = self.ring_rect()
        circumference = math.pi * (ring.width() + self._thickness)
        return (TRACK_GAP + self._thickness) / max(1.0, circumference) * 360.0

    def _pen(self, color: QtGui.QColor) -> QtGui.QPen:
        pen = QtGui.QPen(color, self._thickness)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        return pen

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        ring = self.ring_rect()
        start, sweep = self.arc()
        painter.save()
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        if not self._indeterminate and self._show_track and sweep < 360.0:
            gap = min(sweep, self.gap_degrees()) if sweep > 0 else 0.0
            track_sweep = 360.0 - sweep - 2 * gap
            if track_sweep > 0.5:
                self.paint_track_arc(
                    painter, ring, start + sweep + gap, track_sweep
                )
        if sweep >= 0.5:
            self.paint_active_arc(painter, ring, start, sweep)
        painter.restore()

    def paint_track_arc(
        self,
        painter: QtGui.QPainter,
        ring: QtCore.QRectF,
        start: float,
        sweep: float,
    ) -> None:
        """绘制轨道弧（顺时针度数，0 为 12 点方向）。"""
        painter.setPen(self._pen(self.track_color()))
        self._draw_arc(painter, ring, start, sweep)

    def paint_active_arc(
        self,
        painter: QtGui.QPainter,
        ring: QtCore.QRectF,
        start: float,
        sweep: float,
    ) -> None:
        """绘制活动弧（顺时针度数，0 为 12 点方向）。"""
        painter.setPen(self._pen(self.active_color()))
        self._draw_arc(painter, ring, start, sweep)

    @staticmethod
    def _draw_arc(
        painter: QtGui.QPainter,
        ring: QtCore.QRectF,
        start: float,
        sweep: float,
    ) -> None:
        """把顺时针角度（0 为 12 点）转换为 Qt 的逆时针 1/16 度并绘制。

        圆头会在弧的两端各延伸半个粗细，``gap_degrees`` 已把这部分计入
        轨道空隙。
        """
        painter.drawArc(ring, round((90.0 - start) * 16), round(-sweep * 16))
