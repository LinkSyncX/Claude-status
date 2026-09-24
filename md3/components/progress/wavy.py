"""波浪形进度指示器（M3 Expressive）。

活动指示器以正弦波绘制，并以每秒一个波长的速度向起点方向流动；轨道
保持平直。确定态在进度 ≤10% 或 ≥95% 时振幅平滑归零，其余区间为满
振幅（增大用 standard 缓动、减小用 emphasized-accelerate，各 500ms）；
不确定态始终满振幅。尺寸取自 Compose Material3 的
``WavyProgressIndicatorDefaults``：线性波高 10dp（振幅 3dp）、确定态波长
40dp、不确定态波长 20dp；环形直径 48dp、振幅 1.6dp、波长 15dp。
"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.progress import indicators
from md3.core import animation
from md3.tokens import motion

LINEAR_AMPLITUDE = 3.0
LINEAR_WAVELENGTH = 40.0
LINEAR_INDETERMINATE_WAVELENGTH = 20.0
CIRCULAR_AMPLITUDE = 1.6
CIRCULAR_WAVELENGTH = 15.0
MIN_CIRCULAR_WAVES = 5
# 确定态振幅归零的进度区间端点。
AMPLITUDE_LOW = 0.1
AMPLITUDE_HIGH = 0.95
AMPLITUDE_DURATION = motion.LONG2
# 波每秒前进的波长数。
WAVE_SPEED = 1.0
# 采样步长（px），越小曲线越平滑。
_SAMPLE_STEP = 1.0
_MIN_VISIBLE_AMPLITUDE = 0.05


def amplitude_for_progress(progress: float) -> float:
    """确定态下进度对应的振幅系数：两端为 0，中间为 1。"""
    if progress <= AMPLITUDE_LOW or progress >= AMPLITUDE_HIGH:
        return 0.0
    return 1.0


class Wave:
    """振幅过渡与相位计算，供线性与环形波浪指示器共用。

    Args:
        owner: 拥有动画对象的控件；振幅变化时重绘并重新评估帧时钟。
        amplitude: 满振幅（dp，波峰到中线）。
    """

    def __init__(
        self, owner: indicators.ProgressIndicator, amplitude: float
    ) -> None:
        self._owner = owner
        self.amplitude_dp = max(0.0, float(amplitude))
        self.level = animation.AnimatedFloat(owner, 0.0, self._changed)

    def _changed(self) -> None:
        self._owner.refresh_clock()
        self._owner.update()

    def sync(self, target: float) -> None:
        """把振幅系数向目标值过渡（增大与减小使用不同缓动）。"""
        if target == self.level.target:
            return
        easing = (
            motion.STANDARD
            if target > self.level.value
            else motion.EMPHASIZED_ACCELERATE
        )
        self.level.animate_to(target, AMPLITUDE_DURATION, easing)
        self._owner.refresh_clock()

    def amplitude(self) -> float:
        """当前振幅（dp）。"""
        return self.amplitude_dp * self.level.value

    def is_active(self) -> bool:
        """波是否可见或正在过渡，此时需要逐帧重绘。"""
        return self.level.value > 0 or self.level.target > 0

    @staticmethod
    def phase(elapsed_ms: float) -> float:
        """0–1 的波相位，每秒推进 ``WAVE_SPEED`` 个波长。"""
        return (elapsed_ms / 1000.0 * WAVE_SPEED) % 1.0


class LinearWavyProgressIndicator(indicators.LinearProgressIndicator):
    """线性波浪进度指示器。

    Args:
        value: 进度 0–1；None 表示不确定态。
        amplitude: 满振幅（dp），控件高度为 ``thickness + 2 * amplitude``。
        wavelength: 波长（dp）；None 时确定态 40、不确定态 20。
        thickness: 轨道粗细（dp）。
        parent: 父控件。
    """

    def __init__(
        self,
        value: float | None = 0.0,
        amplitude: float = LINEAR_AMPLITUDE,
        wavelength: float | None = None,
        thickness: float = indicators.TRACK_HEIGHT,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(value, thickness, parent)
        self._wave = Wave(self, amplitude)
        self._wavelength = wavelength
        self._sync_amplitude()
        self._wave.level.set(self._wave.level.target)

    @property
    def amplitude(self) -> float:
        """满振幅（dp）。"""
        return self._wave.amplitude_dp

    @property
    def wave_level(self) -> float:
        """当前振幅系数（0–1）。"""
        return self._wave.level.value

    def wavelength(self) -> float:
        """当前波长（dp）。"""
        if self._wavelength is not None:
            return self._wavelength
        if self._indeterminate:
            return LINEAR_INDETERMINATE_WAVELENGTH
        return LINEAR_WAVELENGTH

    @override
    def container_height(self) -> float:
        return self._thickness + 2 * self._wave.amplitude_dp

    @override
    def needs_clock(self) -> bool:
        return super().needs_clock() or self._wave.is_active()

    def _sync_amplitude(self) -> None:
        if self._indeterminate:
            self._wave.sync(1.0)
        else:
            self._wave.sync(amplitude_for_progress(self.display_value))

    @override
    def _display_changed(self) -> None:
        self._sync_amplitude()
        super()._display_changed()

    @override
    def set_indeterminate(self, indeterminate: bool) -> None:
        super().set_indeterminate(indeterminate)
        self._sync_amplitude()

    @override
    def paint_active_segment(
        self,
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        left: float,
        right: float,
    ) -> None:
        amplitude = self._wave.amplitude()
        half = self._thickness / 2
        start, end = left + half, right - half
        if amplitude < _MIN_VISIBLE_AMPLITUDE or end - start < _SAMPLE_STEP:
            super().paint_active_segment(painter, track, left, right)
            return
        wavelength = max(1.0, self.wavelength())
        phase = self._wave.phase(self.elapsed_ms())
        center_y = track.center().y()

        def y_at(x: float) -> float:
            return center_y + amplitude * math.sin(
                2 * math.pi * (x / wavelength + phase)
            )

        path = QtGui.QPainterPath(QtCore.QPointF(start, y_at(start)))
        x = start + _SAMPLE_STEP
        while x < end:
            path.lineTo(x, y_at(x))
            x += _SAMPLE_STEP
        path.lineTo(end, y_at(end))
        pen = QtGui.QPen(self.active_color(), self._thickness)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)


class CircularWavyProgressIndicator(indicators.CircularProgressIndicator):
    """环形波浪进度指示器。

    波峰位于平直轨道所在的圆上，波谷向内凹陷 ``2 * amplitude``；波数取
    ``2πr / wavelength`` 的整数以保证首尾连续。

    Args:
        value: 进度 0–1；None 表示不确定态。
        size: 直径（dp），默认 48。
        show_track: 确定态是否绘制轨道。
        amplitude: 满振幅（dp）。
        wavelength: 期望波长（dp）。
        thickness: 描边粗细（dp）。
        parent: 父控件。
    """

    def __init__(
        self,
        value: float | None = 0.0,
        size: float = indicators.CIRCULAR_SIZE,
        show_track: bool = True,
        amplitude: float = CIRCULAR_AMPLITUDE,
        wavelength: float = CIRCULAR_WAVELENGTH,
        thickness: float = indicators.CIRCULAR_STROKE,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(value, size, show_track, thickness, parent)
        self._wave = Wave(self, amplitude)
        self._wavelength = max(1.0, float(wavelength))
        self._sync_amplitude()
        self._wave.level.set(self._wave.level.target)

    @property
    def amplitude(self) -> float:
        """满振幅（dp）。"""
        return self._wave.amplitude_dp

    @property
    def wave_level(self) -> float:
        """当前振幅系数（0–1）。"""
        return self._wave.level.value

    def wave_count(self) -> int:
        """沿整圈分布的波数。"""
        radius = self.ring_rect().width() / 2
        return max(
            MIN_CIRCULAR_WAVES, round(2 * math.pi * radius / self._wavelength)
        )

    @override
    def needs_clock(self) -> bool:
        return super().needs_clock() or self._wave.is_active()

    def _sync_amplitude(self) -> None:
        if self._indeterminate:
            self._wave.sync(1.0)
        else:
            self._wave.sync(amplitude_for_progress(self.display_value))

    @override
    def _display_changed(self) -> None:
        self._sync_amplitude()
        super()._display_changed()

    @override
    def set_indeterminate(self, indeterminate: bool) -> None:
        super().set_indeterminate(indeterminate)
        self._sync_amplitude()

    @override
    def paint_active_arc(
        self,
        painter: QtGui.QPainter,
        ring: QtCore.QRectF,
        start: float,
        sweep: float,
    ) -> None:
        amplitude = self._wave.amplitude()
        radius = ring.width() / 2
        if radius <= 0:
            return
        # 圆头在两端各占半个粗细的弧长，波形只画中间部分。
        cap = math.degrees(self._thickness / 2 / radius)
        first, last = start + cap, start + sweep - cap
        if amplitude < _MIN_VISIBLE_AMPLITUDE or last <= first:
            super().paint_active_arc(painter, ring, start, sweep)
            return
        waves = self.wave_count()
        phase = 2 * math.pi * self._wave.phase(self.elapsed_ms())
        center = ring.center()

        def point_at(degrees: float) -> QtCore.QPointF:
            theta = math.radians(degrees)
            r = radius - amplitude + amplitude * math.cos(waves * theta + phase)
            return QtCore.QPointF(
                center.x() + r * math.sin(theta),
                center.y() - r * math.cos(theta),
            )

        step = math.degrees(_SAMPLE_STEP / radius)
        path = QtGui.QPainterPath(point_at(first))
        degrees = first + step
        while degrees < last:
            path.lineTo(point_at(degrees))
            degrees += step
        path.lineTo(point_at(last))
        pen = QtGui.QPen(self.active_color(), self._thickness)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.strokePath(path, pen)
