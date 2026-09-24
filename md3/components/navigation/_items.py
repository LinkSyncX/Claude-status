"""由多个可选项组成的导航容器的公共交互逻辑。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import focus_ring
from md3.core import ripple as ripple_module
from md3.core import state_layer as state_layer_module
from md3.core import widget
from md3.tokens import motion
from md3.tokens import shape as shape_tokens

_KEYBOARD_REASONS = frozenset(
    {
        QtCore.Qt.FocusReason.TabFocusReason,
        QtCore.Qt.FocusReason.BacktabFocusReason,
        QtCore.Qt.FocusReason.ShortcutFocusReason,
    }
)


class SelectableItems(widget.MaterialWidget):
    """管理多个项的悬停、按压、焦点与单选状态。

    子类实现 ``item_count`` / ``item_rect`` / ``item_enabled`` /
    ``item_state_path``，并在绘制时通过 ``progress(index)`` 读取选中
    过渡进度、通过 ``paint_item_overlays`` 叠加状态层与涟漪。
    """

    selection_changed = QtCore.Signal(int)

    def __init__(
        self,
        parent: QtWidgets.QWidget | None = None,
        horizontal_keys: bool = True,
    ) -> None:
        super().__init__(parent)
        self._selected = -1
        self._hovered = -1
        self._pressed = -1
        self._focused = 0
        self._focus_visible = False
        self._horizontal_keys = horizontal_keys
        self._layers: list[state_layer_module.StateLayer] = []
        self._ripples: list[ripple_module.RippleController] = []
        self._progress: list[animation.AnimatedFloat] = []
        self._focus_anim = animation.AnimatedFloat(self, 1.0, self.update)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)

    # ---- 子类接口 -------------------------------------------------------

    def item_count(self) -> int:
        """项数量。"""
        return 0

    def item_rect(self, index: int) -> QtCore.QRectF:
        """第 index 项的矩形。"""
        del index
        return QtCore.QRectF()

    def item_enabled(self, index: int) -> bool:
        """第 index 项是否可用。"""
        del index
        return True

    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        """状态层与涟漪的裁剪路径，默认为项矩形。"""
        path = QtGui.QPainterPath()
        path.addRect(self.item_rect(index))
        return path

    def item_state_color(self, index: int) -> QtGui.QColor:
        """状态层颜色，默认为 ``on_surface``。"""
        del index
        return self.color("on_surface")

    def focus_shape(self) -> shape_tokens.Shape:
        """焦点环形状。"""
        return shape_tokens.SHAPE_FULL

    def item_label(self, index: int) -> str:
        """第 index 项的文字（供无障碍播报），子类可覆写。"""
        del index
        return ""

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.PageTabList

    @override
    def accessible_value(self) -> str:
        return self.item_label(self._selected) if self._selected >= 0 else ""

    # ---- 状态 -------------------------------------------------------------

    def _rebuild_states(self) -> None:
        count = self.item_count()
        self._layers = [
            state_layer_module.StateLayer(self, on_change=self.update)
            for _ in range(count)
        ]
        self._ripples = [
            ripple_module.RippleController(self, on_change=self.update)
            for _ in range(count)
        ]
        self._progress = [
            animation.AnimatedFloat(
                self, 1.0 if index == self._selected else 0.0, self.update
            )
            for index in range(count)
        ]
        self._hovered = -1
        self._pressed = -1
        self._focused = max(0, min(self._focused, count - 1))

    @property
    def selected_index(self) -> int:
        """当前选中下标，-1 表示未选中。"""
        return self._selected

    def set_selected_index(self, index: int, animate: bool = True) -> None:
        """设置选中项，变化时发出 ``selection_changed``。"""
        if index < -1 or index >= self.item_count():
            return
        if index == self._selected:
            return
        previous = self._selected
        self._selected = index
        if index >= 0:
            # 键盘焦点跟随选中项，方向键从当前选中项出发。
            self._set_focused(index)
        for current, value in enumerate(self._progress):
            target = 1.0 if current == index else 0.0
            if animate and current in (index, previous):
                value.animate_to(
                    target, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
                )
            else:
                value.set(target)
        self.selection_changed.emit(index)
        accessibility.notify_value_changed(self, self.accessible_value())
        self.update()

    def progress(self, index: int) -> float:
        """第 index 项的选中过渡进度。"""
        if 0 <= index < len(self._progress):
            return self._progress[index].value
        return 0.0

    def is_hovered(self, index: int) -> bool:
        """第 index 项是否悬停。"""
        return index == self._hovered

    def paint_item_overlays(self, painter: QtGui.QPainter, index: int) -> None:
        """绘制第 index 项的状态层、涟漪与焦点环。"""
        if index < 0 or index >= len(self._layers):
            return
        path = self.item_state_path(index)
        color = self.item_state_color(index)
        self._layers[index].paint(painter, path, color)
        self._ripples[index].paint(painter, path, color)
        if self._focus_visible and index == self._focused:
            focus_ring.paint_focus_ring(
                painter,
                path.boundingRect(),
                self.focus_shape(),
                self.color("secondary"),
                max_extent=2.0,
                progress=self._focus_anim.value,
            )

    def _index_at(self, point: QtCore.QPointF) -> int:
        for index in range(self.item_count()):
            if self.item_rect(index).contains(point):
                return index
        return -1

    def _set_hovered(self, index: int) -> None:
        if index == self._hovered:
            return
        if 0 <= self._hovered < len(self._layers):
            self._layers[self._hovered].set_hovered(False)
        self._hovered = index
        if 0 <= index < len(self._layers) and self.item_enabled(index):
            self._layers[index].set_hovered(True)

    def _set_focused(self, index: int) -> None:
        if 0 <= self._focused < len(self._layers):
            self._layers[self._focused].set_focused(False)
        moved = index != self._focused
        self._focused = index
        if self._focus_visible and 0 <= index < len(self._layers):
            self._layers[index].set_focused(True)
            if moved or not self._focus_anim.is_running():
                self._focus_anim.set(0.0)
                self._focus_anim.animate_to(
                    1.0, focus_ring.ANIMATION_DURATION_MS, motion.STANDARD
                )
        self.update()

    def activate_item(self, index: int) -> None:
        """选中第 index 项（子类可覆写以处理非选择类项）。"""
        if 0 <= index < self.item_count() and self.item_enabled(index):
            self.set_selected_index(index)

    # ---- 事件 -------------------------------------------------------------

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._set_hovered(self._index_at(event.position()))
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._set_hovered(-1)
        super().leaveEvent(event)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() != QtCore.Qt.MouseButton.LeftButton
            or not self.isEnabled()
        ):
            super().mousePressEvent(event)
            return
        index = self._index_at(event.position())
        if index < 0 or not self.item_enabled(index):
            return
        self._pressed = index
        self._set_focused(index)
        self._ripples[index].press(
            event.position(), self.item_state_path(index).boundingRect()
        )
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        pressed = self._pressed
        self._pressed = -1
        if pressed >= 0:
            self._ripples[pressed].release()
            if self._index_at(event.position()) == pressed:
                self.activate_item(pressed)
        event.accept()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        # 水平排列的项在 RTL 下向左才是"前进"。
        right, left = QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Left
        if self._horizontal_keys and self.is_rtl():
            right, left = left, right
        forward = (
            (right, QtCore.Qt.Key.Key_Down)
            if self._horizontal_keys
            else (QtCore.Qt.Key.Key_Down, right)
        )
        backward = (
            (left, QtCore.Qt.Key.Key_Up)
            if self._horizontal_keys
            else (QtCore.Qt.Key.Key_Up, left)
        )
        if key in forward:
            self._move_focus(1)
        elif key in backward:
            self._move_focus(-1)
        elif key in (
            QtCore.Qt.Key.Key_Space,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
        ):
            self.activate_item(self._focused)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _move_focus(self, delta: int) -> None:
        count = self.item_count()
        if count == 0:
            return
        index = self._focused
        for _ in range(count):
            index = (index + delta) % count
            if self.item_enabled(index):
                self._focus_visible = True
                self._set_focused(index)
                return

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusInEvent(event)
        self._focus_visible = event.reason() in _KEYBOARD_REASONS
        if self._focus_visible:
            if self._selected >= 0:
                self._focused = self._selected
            self._set_focused(self._focused)
        self.update()

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(event)
        self._focus_visible = False
        for layer in self._layers:
            layer.set_focused(False)
        self.update()
