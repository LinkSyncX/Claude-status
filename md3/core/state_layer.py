"""交互状态层：hover / focus / dragged 的半透明覆盖。

按压态默认由涟漪表现；关闭涟漪的组件可启用平铺的按压层。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore
from PySide6 import QtGui

from md3.core import animation
from md3.tokens import motion
from md3.tokens import state as state_tokens

InteractionState = state_tokens.InteractionState


class StateLayer(QtCore.QObject):
    """跟踪交互状态并以动画过渡状态层不透明度。"""

    def __init__(
        self,
        parent: QtCore.QObject | None,
        on_change: Callable[[], None] | None = None,
        pressed_layer: bool = False,
    ) -> None:
        super().__init__(parent)
        self._state = InteractionState.NONE
        self._pressed_layer = pressed_layer
        self._opacity = animation.AnimatedFloat(self, 0.0, on_change)

    @property
    def state(self) -> InteractionState:
        """当前状态组合。"""
        return self._state

    @property
    def opacity(self) -> float:
        """当前（动画中的）状态层不透明度。"""
        return self._opacity.value

    def has(self, flag: InteractionState) -> bool:
        """是否包含某个状态。"""
        return flag in self._state

    def set_flag(self, flag: InteractionState, on: bool) -> None:
        """设置或清除单个状态位，并按需启动过渡动画。"""
        new_state = self._state | flag if on else self._state & ~flag
        if new_state == self._state:
            return
        self._state = new_state
        self._opacity.animate_to(
            self._target_opacity(),
            motion.STATE_LAYER_DURATION,
            motion.STATE_LAYER_EASING,
        )

    def set_hovered(self, on: bool) -> None:
        """设置悬停状态。"""
        self.set_flag(InteractionState.HOVERED, on)

    def set_focused(self, on: bool) -> None:
        """设置（键盘）焦点状态。"""
        self.set_flag(InteractionState.FOCUSED, on)

    def set_pressed(self, on: bool) -> None:
        """设置按压状态。"""
        self.set_flag(InteractionState.PRESSED, on)

    def set_dragged(self, on: bool) -> None:
        """设置拖拽状态。"""
        self.set_flag(InteractionState.DRAGGED, on)

    def set_disabled(self, on: bool) -> None:
        """设置禁用状态（禁用时状态层不显示）。"""
        self.set_flag(InteractionState.DISABLED, on)

    def clear(self) -> None:
        """清除除禁用外的全部状态。"""
        disabled = self.has(InteractionState.DISABLED)
        self._state = InteractionState.NONE
        if disabled:
            self._state |= InteractionState.DISABLED
        self._opacity.animate_to(
            0.0, motion.STATE_LAYER_DURATION, motion.STATE_LAYER_EASING
        )

    def paint(
        self,
        painter: QtGui.QPainter,
        path: QtGui.QPainterPath,
        color: QtGui.QColor,
    ) -> None:
        """以内容色填充路径，作为状态层。"""
        opacity = self._opacity.value
        if opacity <= 0.001:
            return
        layer = QtGui.QColor(color)
        layer.setAlphaF(min(1.0, opacity))
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(layer)
        painter.drawPath(path)
        painter.restore()

    def _target_opacity(self) -> float:
        state = self._state
        if not self._pressed_layer:
            state &= ~InteractionState.PRESSED
        return state_tokens.state_layer_opacity(state)
