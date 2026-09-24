"""涟漪（按压反馈）动画。

行为参考 material-web 的 ripple：按压时从触点向外扩散、边缘柔化；
释放后至少显示最短按压时长，再淡出。多次快速点击会叠加多个涟漪。
"""

from __future__ import annotations

from collections.abc import Callable
import math
import time

from PySide6 import QtCore
from PySide6 import QtGui

from md3.core import animation
from md3.tokens import motion
from md3.tokens import state as state_tokens

PRESS_GROW_MS = 450
MINIMUM_PRESS_MS = 225
FADE_OUT_MS = 375
INITIAL_RADIUS_RATIO = 0.2
SOFT_EDGE_PADDING = 10.0


class _Ripple:
    """单个涟漪的几何与动画状态。"""

    def __init__(
        self,
        parent: QtCore.QObject,
        center: QtCore.QPointF,
        start_radius: float,
        end_radius: float,
        on_change: Callable[[], None] | None,
    ) -> None:
        self.center = center
        self.start_radius = start_radius
        self.end_radius = end_radius
        self.growth = animation.AnimatedFloat(parent, 0.0, on_change)
        self.opacity = animation.AnimatedFloat(
            parent, state_tokens.PRESSED_STATE_LAYER_OPACITY, on_change
        )
        self.started_at = time.monotonic()
        self.released = False
        self.fade_scheduled = False
        self.finished = False
        self.growth.animate_to(1.0, PRESS_GROW_MS, motion.STANDARD)

    @property
    def radius(self) -> float:
        """当前半径。"""
        return (
            self.start_radius
            + (self.end_radius - self.start_radius) * self.growth.value
        )

    def fade_out(self, finished: Callable[[], None]) -> None:
        """开始淡出，结束后调用 finished。"""
        if self.released:
            return
        self.released = True

        def done() -> None:
            self.finished = True
            finished()

        self.opacity.finished.connect(done)
        self.opacity.animate_to(0.0, FADE_OUT_MS, motion.LINEAR)


class RippleController(QtCore.QObject):
    """管理一个组件上的全部涟漪。"""

    def __init__(
        self,
        parent: QtCore.QObject | None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._ripples: list[_Ripple] = []
        self._enabled = True
        self._color_opacity = state_tokens.PRESSED_STATE_LAYER_OPACITY

    @property
    def enabled(self) -> bool:
        """是否启用涟漪。"""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """启用或关闭涟漪；关闭时清除现有涟漪。"""
        self._enabled = enabled
        if not enabled:
            self._ripples.clear()
            self._notify()

    def is_active(self) -> bool:
        """是否有涟漪正在显示。"""
        return bool(self._ripples)

    def press(
        self,
        position: QtCore.QPointF | None,
        bounds: QtCore.QRectF,
    ) -> None:
        """在给定位置开始一个涟漪。

        Args:
            position: 触点（组件坐标）；为 None 时从容器中心开始。
            bounds: 涟漪需要覆盖的区域。
        """
        if not self._enabled or bounds.isEmpty():
            return
        center = QtCore.QPointF(position) if position else bounds.center()
        farthest = max(
            math.hypot(center.x() - corner.x(), center.y() - corner.y())
            for corner in (
                bounds.topLeft(),
                bounds.topRight(),
                bounds.bottomLeft(),
                bounds.bottomRight(),
            )
        )
        end_radius = farthest + SOFT_EDGE_PADDING
        start_radius = max(
            8.0, min(bounds.width(), bounds.height()) * INITIAL_RADIUS_RATIO
        )
        if not animation.animations_enabled():
            return
        ripple = _Ripple(self, center, start_radius, end_radius, self._notify)
        self._ripples.append(ripple)
        self._notify()

    def release(self) -> None:
        """释放最近一次按压，满足最短按压时长后淡出。"""
        for ripple in self._ripples:
            if not ripple.fade_scheduled:
                self._schedule_fade(ripple)

    def cancel(self) -> None:
        """取消全部涟漪（例如指针离开或组件被禁用）。"""
        self.release()

    def paint(
        self,
        painter: QtGui.QPainter,
        clip: QtGui.QPainterPath,
        color: QtGui.QColor,
    ) -> None:
        """在裁剪路径内绘制全部涟漪。"""
        if not self._ripples:
            return
        painter.save()
        painter.setClipPath(clip, QtCore.Qt.ClipOperation.IntersectClip)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for ripple in self._ripples:
            alpha = ripple.opacity.value
            if alpha <= 0.001:
                continue
            gradient = QtGui.QRadialGradient(ripple.center, ripple.radius)
            solid = QtGui.QColor(color)
            solid.setAlphaF(min(1.0, alpha))
            transparent = QtGui.QColor(color)
            transparent.setAlphaF(0.0)
            gradient.setColorAt(0.0, solid)
            gradient.setColorAt(0.65, solid)
            gradient.setColorAt(1.0, transparent)
            painter.setBrush(gradient)
            painter.drawEllipse(ripple.center, ripple.radius, ripple.radius)
        painter.restore()

    def _schedule_fade(self, ripple: _Ripple) -> None:
        ripple.fade_scheduled = True
        elapsed_ms = (time.monotonic() - ripple.started_at) * 1000
        remaining = MINIMUM_PRESS_MS - elapsed_ms

        def start_fade() -> None:
            ripple.fade_out(self._prune)

        if remaining <= 0:
            start_fade()
        else:
            QtCore.QTimer.singleShot(int(remaining), self, start_fade)

    def _prune(self) -> None:
        self._ripples = [r for r in self._ripples if not r.finished]
        self._notify()

    def _notify(self) -> None:
        if self._on_change is not None:
            self._on_change()
