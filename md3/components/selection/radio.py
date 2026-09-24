"""单选按钮（Radio button）与互斥分组。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.selection import base
from md3.theme import theme as theme_module
from md3.tokens import state as state_tokens

RADIO_SIZE = 20.0
OUTLINE_WIDTH = 2.0
DOT_SIZE = 10.0


class RadioButton(base.SelectionControl):
    """单选按钮。

    单选按钮自身只负责显示与切换为选中；互斥逻辑由 ``RadioGroup`` 管理。
    """

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, checked, RADIO_SIZE, RADIO_SIZE, parent)
        self._group: RadioGroup | None = None

    @property
    def group(self) -> RadioGroup | None:
        """所属分组。"""
        return self._group

    @override
    def activate(self) -> None:
        # 单选按钮点击只能选中，不能取消。
        if not self.checked:
            self.set_checked(True)
        self.clicked.emit()

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.RadioButton

    def _control_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self.checked:
            return self.color("primary")
        return self.color("on_surface_variant")

    @override
    def paint_control(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        color = self._control_color()
        painter.save()
        pen = QtGui.QPen(color, OUTLINE_WIDTH)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        half = OUTLINE_WIDTH / 2
        painter.drawEllipse(rect.adjusted(half, half, -half, -half))
        progress = self.progress
        if progress > 0:
            dot = DOT_SIZE * progress
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(rect.center(), dot / 2, dot / 2)
        painter.restore()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self._group is not None and event.key() in (
            QtCore.Qt.Key.Key_Down,
            QtCore.Qt.Key.Key_Right,
        ):
            self._group.select_relative(self, 1)
            event.accept()
            return
        if self._group is not None and event.key() in (
            QtCore.Qt.Key.Key_Up,
            QtCore.Qt.Key.Key_Left,
        ):
            self._group.select_relative(self, -1)
            event.accept()
            return
        super().keyPressEvent(event)


class RadioGroup(QtCore.QObject):
    """管理一组互斥的单选按钮。

    Args:
        buttons: 初始按钮列表。
        parent: 父对象。
    """

    selection_changed = QtCore.Signal(int)

    def __init__(
        self,
        buttons: list[RadioButton] | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._buttons: list[RadioButton] = []
        self._updating = False
        for button in buttons or ():
            self.add(button)

    @property
    def buttons(self) -> list[RadioButton]:
        """分组中的按钮。"""
        return list(self._buttons)

    def add(self, button: RadioButton) -> None:
        """加入按钮；若其已选中则取消其他按钮。"""
        if button in self._buttons:
            return
        self._buttons.append(button)
        button._group = self  # pylint: disable=protected-access
        button.toggled.connect(self._on_button_toggled)
        if button.checked:
            self._on_toggled(button, True)

    def remove(self, button: RadioButton) -> None:
        """移除按钮。"""
        if button in self._buttons:
            self._buttons.remove(button)
            button._group = None  # pylint: disable=protected-access

    @property
    def checked_index(self) -> int:
        """当前选中按钮的下标，未选中为 -1。"""
        for index, button in enumerate(self._buttons):
            if button.checked:
                return index
        return -1

    @property
    def checked_button(self) -> RadioButton | None:
        """当前选中的按钮。"""
        index = self.checked_index
        return self._buttons[index] if index >= 0 else None

    def set_checked_index(self, index: int) -> None:
        """选中指定下标的按钮。"""
        if 0 <= index < len(self._buttons):
            self._buttons[index].set_checked(True)

    def select_relative(self, current: RadioButton, delta: int) -> None:
        """从 current 起按方向选中下一个可用按钮，并把焦点移到它上面。"""
        if current not in self._buttons or not self._buttons:
            return
        count = len(self._buttons)
        index = self._buttons.index(current)
        for _ in range(count):
            index = (index + delta) % count
            candidate = self._buttons[index]
            if candidate.isEnabled():
                candidate.set_checked(True)
                candidate.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
                return

    def _on_button_toggled(self, checked: bool) -> None:
        # 通过 sender() 识别按钮，避免用闭包持有已销毁的对象。
        button = self.sender()
        if isinstance(button, RadioButton):
            self._on_toggled(button, checked)

    def _on_toggled(self, button: RadioButton, checked: bool) -> None:
        if not checked or self._updating:
            return
        self._updating = True
        try:
            for other in self._buttons:
                if other is not button and other.checked:
                    other.set_checked(False)
        finally:
            self._updating = False
        self.selection_changed.emit(self._buttons.index(button))
