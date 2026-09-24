"""底部应用栏（Bottom app bar）：最多 4 个图标操作与一个 FAB。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import fab as fab_module
from md3.components.buttons import icon_button
from md3.core import widget
from md3.theme import icons
from md3.tokens import elevation

BAR_HEIGHT = 80.0
START_PADDING = 4.0
END_PADDING = 16.0
ICON_BUTTON_SIZE = 48.0
MAX_ACTIONS = 4


class BottomAppBar(widget.MaterialWidget):
    """底部应用栏。

    Args:
        actions: 左侧图标操作列表（最多 4 个）。
        fab: 右侧 FAB；放入底部应用栏后 FAB 不再投影。
        parent: 父控件。
    """

    action_triggered = QtCore.Signal(int)

    def __init__(
        self,
        actions: list[icons.IconLike] | None = None,
        fab: fab_module.FloatingActionButton | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._action_buttons: list[icon_button.IconButton] = []
        self._fab: fab_module.FloatingActionButton | None = None
        self.set_actions(actions or [])
        self.set_fab(fab)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_actions(self, actions: list[icons.IconLike]) -> None:
        """设置图标操作。"""
        for button in self._action_buttons:
            button.setParent(None)
            button.deleteLater()
        self._action_buttons = []
        for icon in actions[:MAX_ACTIONS]:
            button = icon_button.IconButton(icon, parent=self)
            button.clicked.connect(self._on_action_clicked)
            self._action_buttons.append(button)
        self._layout_children()

    @property
    def action_buttons(self) -> list[icon_button.IconButton]:
        """图标操作按钮。"""
        return list(self._action_buttons)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ToolBar

    @property
    def fab(self) -> fab_module.FloatingActionButton | None:
        """右侧 FAB。"""
        return self._fab

    def set_fab(self, fab: fab_module.FloatingActionButton | None) -> None:
        """设置右侧 FAB（会取消其阴影）。"""
        if self._fab is not None:
            self._fab.setParent(None)
        self._fab = fab
        if fab is not None:
            fab.setParent(self)
            fab.set_lowered(True)
            fab.set_elevation(elevation.Level.LEVEL_0)
            fab.show()
        self._layout_children()

    def _on_action_clicked(self) -> None:
        sender = self.sender()
        for index, button in enumerate(self._action_buttons):
            if button is sender:
                self.action_triggered.emit(index)
                return

    def _layout_children(self) -> None:
        y = (BAR_HEIGHT - ICON_BUTTON_SIZE) / 2
        x = START_PADDING
        for button in self._action_buttons:
            button.setGeometry(
                self.visual_rect(
                    QtCore.QRectF(x, y, ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
                ).toRect()
            )
            x += ICON_BUTTON_SIZE
        if self._fab is not None:
            hint = self._fab.sizeHint()
            logical = QtCore.QRectF(
                self.width()
                - END_PADDING
                - hint.width()
                + self._fab.outer_margin,
                (BAR_HEIGHT - hint.height()) / 2,
                hint.width(),
                hint.height(),
            )
            self._fab.setGeometry(self.visual_rect(logical).toRect())

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, int(BAR_HEIGHT))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(200, int(BAR_HEIGHT))

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        painter.fillRect(self.rect(), self.color("surface_container"))
