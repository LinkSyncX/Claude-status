"""拆分按钮（Split button，M3 Expressive）。

左侧为主操作按钮，右侧为带下拉箭头的按钮，两段相距 2dp、内侧圆角
4dp。点击箭头弹出菜单时箭头旋转 180°、右段形状变为完整胶囊；菜单关闭
后复原。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import common
from md3.components.buttons import group
from md3.components.menus import menu as menu_module
from md3.core import animation
from md3.core import widget
from md3.theme import icons
from md3.tokens import motion
from md3.tokens import shape as shape_tokens

SPACING = 2.0
INNER_CORNER = shape_tokens.EXTRA_SMALL
TRAILING_WIDTH = 40.0
ARROW_ICON = "keyboard_arrow_down"
ARROW_SIZE = 22.0


class _TrailingButton(common.Button):
    """拆分按钮右段：仅含旋转箭头的按钮。"""

    def __init__(
        self, variant: common.ButtonVariant, parent: QtWidgets.QWidget | None
    ) -> None:
        super().__init__("", None, variant, parent=parent)
        self._arrow = icons.coerce(ARROW_ICON, ARROW_SIZE)
        self._rotation = animation.AnimatedFloat(self, 0.0, self.update)
        self._open = animation.AnimatedFloat(self, 0.0, self.update)
        self._open.finished.connect(self.sync_shadow)

    def set_open(self, opened: bool) -> None:
        """菜单打开 / 关闭：箭头旋转、形状变为胶囊。"""
        target = 1.0 if opened else 0.0
        self._rotation.spring_to(target, motion.EXPRESSIVE_DEFAULT_SPATIAL)
        self._open.spring_to(target, motion.EXPRESSIVE_DEFAULT_SPATIAL)

    @property
    def rotation(self) -> float:
        """箭头当前旋转角度（度）。"""
        return self._rotation.value * 180.0

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ButtonDropDown

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        opened = self._open.value > 0.5
        state.hasPopup = True
        state.expandable = True
        state.expanded = opened
        state.collapsed = not opened

    @override
    def sizeHint(self) -> QtCore.QSize:
        margin = self.outer_margin
        return QtCore.QSize(
            round(TRAILING_WIDTH + 2 * margin),
            round(self.tokens.container_height + 2 * margin),
        )

    @override
    def container_shape(self) -> shape_tokens.Shape:
        rect = self.container_rect()
        closed = shape_tokens.Shape(
            INNER_CORNER, shape_tokens.FULL, shape_tokens.FULL, INNER_CORNER
        )
        return group.lerp_shape(
            closed,
            shape_tokens.SHAPE_FULL,
            self._open.value,
            rect.width(),
            rect.height(),
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        if self._arrow is None:
            return
        rect = self.container_rect()
        painter.save()
        painter.translate(rect.center())
        painter.rotate(self.rotation)
        self._arrow.paint(
            painter,
            QtCore.QRectF(
                -ARROW_SIZE / 2, -ARROW_SIZE / 2, ARROW_SIZE, ARROW_SIZE
            ),
            self._content_color(),
        )
        painter.restore()


class SplitButton(widget.MaterialWidget):
    """拆分按钮。

    Args:
        text: 主操作文字。
        icon: 主操作图标。
        variant: 两段共用的按钮变体。
        menu: 点击箭头弹出的菜单；也可以不给菜单而监听 ``menu_requested``。
        parent: 父控件。
    """

    clicked = QtCore.Signal()
    menu_requested = QtCore.Signal()
    triggered = QtCore.Signal(object)

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        variant: common.ButtonVariant = common.ButtonVariant.FILLED,
        menu: menu_module.Menu | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._leading = common.Button(text, icon, variant, parent=self)
        self._leading.set_shape(
            shape_tokens.Shape(
                shape_tokens.FULL, INNER_CORNER, INNER_CORNER, shape_tokens.FULL
            )
        )
        self._leading.clicked.connect(self.clicked)
        self._trailing = _TrailingButton(variant, self)
        self._trailing.clicked.connect(self._on_trailing)
        self._menu: menu_module.Menu | None = None
        self._open = False
        self.set_menu(menu)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def leading_button(self) -> common.Button:
        """主操作按钮。"""
        return self._leading

    @property
    def trailing_button(self) -> common.Button:
        """箭头按钮。"""
        return self._trailing

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    @property
    def text(self) -> str:
        """主操作文字。"""
        return self._leading.text

    def set_text(self, text: str) -> None:
        """设置主操作文字。"""
        self._leading.set_text(text)
        self.updateGeometry()

    @property
    def menu(self) -> menu_module.Menu | None:
        """关联的菜单。"""
        return self._menu

    def set_menu(self, menu: menu_module.Menu | None) -> None:
        """设置菜单。"""
        if self._menu is not None:
            self._menu.triggered.disconnect(self.triggered)
            self._menu.closed.disconnect(self._on_menu_closed)
        self._menu = menu
        if menu is not None:
            menu.triggered.connect(self.triggered)
            menu.closed.connect(self._on_menu_closed)

    @property
    def menu_open(self) -> bool:
        """菜单是否打开。"""
        return self._open

    def set_variant(self, variant: common.ButtonVariant) -> None:
        """切换两段的变体。"""
        self._leading.set_variant(variant)
        self._trailing.set_variant(variant)

    def _on_trailing(self) -> None:
        self.menu_requested.emit()
        if self._menu is None:
            return
        if self._open:
            self._menu.close_all()
            return
        self._set_open(True)
        self._menu.popup_below(self, gap=4)

    def _on_menu_closed(self) -> None:
        self._set_open(False)

    def _set_open(self, opened: bool) -> None:
        if opened == self._open:
            return
        self._open = opened
        self._trailing.set_open(opened)

    @override
    def sizeHint(self) -> QtCore.QSize:
        leading = self._leading.sizeHint()
        trailing = self._trailing.sizeHint()
        margin = self._leading.outer_margin
        # 两段的外边距在中间重叠，只保留 2dp 间距。
        width = leading.width() + trailing.width() - 2 * margin + SPACING
        return QtCore.QSize(
            round(width), max(leading.height(), trailing.height())
        )

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        leading = self._leading.sizeHint()
        trailing = self._trailing.sizeHint()
        margin = round(self._leading.outer_margin)
        trailing_x = self.width() - trailing.width()
        self._trailing.setGeometry(
            trailing_x, 0, trailing.width(), trailing.height()
        )
        self._leading.setGeometry(
            0,
            0,
            max(leading.width(), trailing_x + margin - round(SPACING) + margin),
            leading.height(),
        )
