"""工具栏（Toolbar，M3 Expressive）。

``Toolbar`` 把一组图标按钮（或任意控件）放进 64dp 高的容器：

- 浮动工具栏：胶囊形、level 3 阴影，通常悬浮在内容上方或底部居中；
- 停靠工具栏：贴边、不带阴影、直角，横跨窗口底部。

配色分标准（``surface_container``）与鲜明（``primary_container``）两种，
也支持竖向排列。
"""

from __future__ import annotations

from collections.abc import Sequence
import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import icon_button
from md3.core import shape as shape_utils
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens

HEIGHT = 64.0
PADDING = 8.0
SPACING = 4.0
FLOATING_ELEVATION = elevation.Level.LEVEL_3


class ToolbarColor(enum.Enum):
    """工具栏配色：值为 (容器角色, 内容角色)。"""

    STANDARD = ("surface_container", "on_surface_variant")
    VIBRANT = ("primary_container", "on_primary_container")


class _ToolbarIconButton(icon_button.IconButton):
    """按工具栏配色着色的图标按钮。"""

    def __init__(
        self,
        icon: icons.IconLike,
        toolbar: Toolbar,
        tooltip: str,
        checkable: bool,
    ) -> None:
        super().__init__(
            icon, checkable=checkable, tooltip=tooltip, parent=toolbar
        )
        self._toolbar = toolbar

    @override
    def _icon_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self.checkable and self.checked:
            return self.color("primary")
        return self.color(self._toolbar.toolbar_color.value[1])


class Toolbar(widget.MaterialWidget):
    """工具栏。

    Args:
        actions: 初始操作，可为图标名 / ``Icon`` / ``SvgIcon``（生成图标按钮）
            或任意控件。
        floating: 为真时为浮动胶囊形，否则为停靠条。
        color: 配色。
        vertical: 是否竖向排列。
        parent: 父控件。
    """

    action_triggered = QtCore.Signal(int)

    def __init__(
        self,
        actions: Sequence[icons.IconLike | QtWidgets.QWidget] = (),
        floating: bool = True,
        color: ToolbarColor = ToolbarColor.STANDARD,
        vertical: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._floating = floating
        self._color = color
        self._vertical = vertical
        self._actions: list[icon_button.IconButton] = []
        direction = (
            QtWidgets.QBoxLayout.Direction.TopToBottom
            if vertical
            else QtWidgets.QBoxLayout.Direction.LeftToRight
        )
        self._layout = QtWidgets.QBoxLayout(direction, self)
        self._layout.setContentsMargins(
            round(PADDING), round(PADDING), round(PADDING), round(PADDING)
        )
        self._layout.setSpacing(round(SPACING))
        for action in actions:
            if isinstance(action, QtWidgets.QWidget):
                self.add_widget(action)
            else:
                self.add_action(action)
        self._apply_mode()

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ToolBar

    # ---- 内容 -------------------------------------------------------------

    def add_action(
        self, icon: icons.IconLike, tooltip: str = "", checkable: bool = False
    ) -> icon_button.IconButton:
        """追加一个图标按钮并返回它。"""
        index = len(self._actions)
        button = _ToolbarIconButton(icon, self, tooltip, checkable)
        button.clicked.connect(lambda: self.action_triggered.emit(index))
        self._actions.append(button)
        self._layout.addWidget(button)
        return button

    def add_widget(self, child: QtWidgets.QWidget, stretch: int = 0) -> None:
        """追加任意控件。"""
        self._layout.addWidget(child, stretch)

    def add_stretch(self) -> None:
        """追加弹性空间（停靠工具栏常用于把操作分成两组）。"""
        self._layout.addStretch()

    @property
    def action_buttons(self) -> list[icon_button.IconButton]:
        """全部图标按钮。"""
        return list(self._actions)

    # ---- 样式 -------------------------------------------------------------

    @property
    def floating(self) -> bool:
        """是否为浮动工具栏。"""
        return self._floating

    def set_floating(self, floating: bool) -> None:
        """切换浮动 / 停靠。"""
        self._floating = floating
        self._apply_mode()

    @property
    def toolbar_color(self) -> ToolbarColor:
        """配色。"""
        return self._color

    def set_color(self, color: ToolbarColor) -> None:
        """设置配色。"""
        self._color = color
        self.update()

    @property
    def vertical(self) -> bool:
        """是否竖向。"""
        return self._vertical

    def _apply_mode(self) -> None:
        if self._floating:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed
                if not self._vertical
                else QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
            self.set_elevation(FLOATING_ELEVATION)
        else:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding
                if not self._vertical
                else QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Fixed
                if not self._vertical
                else QtWidgets.QSizePolicy.Policy.Expanding,
            )
            self.set_elevation(elevation.Level.LEVEL_0)
        self.updateGeometry()
        self.update()

    @override
    def elevation_shape(self) -> shape_tokens.Shape:
        return self.container_shape()

    def container_shape(self) -> shape_tokens.Shape:
        """容器形状：浮动为胶囊，停靠为直角。"""
        return (
            shape_tokens.SHAPE_FULL
            if self._floating
            else shape_tokens.SHAPE_NONE
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        hint = self._layout.sizeHint()
        if self._vertical:
            return QtCore.QSize(
                round(HEIGHT), max(hint.height(), round(HEIGHT))
            )
        return QtCore.QSize(max(hint.width(), round(HEIGHT)), round(HEIGHT))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(
                QtCore.QRectF(self.rect()), self.container_shape()
            ),
            self.color(self._color.value[0]),
        )
