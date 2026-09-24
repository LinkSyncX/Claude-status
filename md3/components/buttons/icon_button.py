"""图标按钮（Icon buttons）。

四种变体：standard / filled / tonal / outlined，均支持切换态。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import shape as shape_utils
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens

CONTAINER_SIZE = 40.0
ICON_SIZE = 24.0
OUTLINE_WIDTH = 1.0


class IconButtonVariant(enum.Enum):
    """图标按钮变体。"""

    STANDARD = "standard"
    FILLED = "filled"
    TONAL = "tonal"
    OUTLINED = "outlined"


class IconButton(widget.InteractiveWidget):
    """图标按钮。

    Args:
        icon: 图标名或 ``Icon``。
        variant: 变体。
        checkable: 是否为切换按钮。
        checked: 初始选中状态。
        selected_icon: 选中时显示的图标；默认为同名填充图标。
        tooltip: 提示文字（图标按钮没有可见标签，建议提供）。
        parent: 父控件。
    """

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        icon: icons.IconLike,
        variant: IconButtonVariant = IconButtonVariant.STANDARD,
        checkable: bool = False,
        checked: bool = False,
        selected_icon: icons.IconLike = None,
        tooltip: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon = icons.coerce(icon, ICON_SIZE)
        self._selected_icon = icons.coerce(selected_icon, ICON_SIZE)
        self._variant = variant
        self._checkable = checkable
        self._checked = checked and checkable
        self._tooltip = None
        self._shape_override: shape_tokens.Shape | None = None
        if tooltip:
            self.set_tooltip(tooltip)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_tooltip(self, text: str) -> None:
        """设置 M3 纯文字提示（替代原生 QToolTip）。"""
        # 提示模块依赖按钮模块，延迟导入以避免循环导入。
        from md3.components.tooltips import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            tooltip as tooltip_module,
        )

        if self._tooltip is None:
            self._tooltip = tooltip_module.install_plain(self, text)
        else:
            self._tooltip.set_text(text)
        self.setAccessibleName(text)

    def icon_rect(self) -> QtCore.QRectF:
        """居中于容器的 24dp 图标矩形。"""
        rect = self.container_rect()
        return QtCore.QRectF(
            rect.center().x() - ICON_SIZE / 2,
            rect.center().y() - ICON_SIZE / 2,
            ICON_SIZE,
            ICON_SIZE,
        )

    def badge_anchor_rect(self) -> QtCore.QRectF:
        """徽标挂载时依附的锚点，即图标矩形。"""
        return self.icon_rect()

    # ---- 属性 -------------------------------------------------------------

    @property
    def icon(self) -> icons.AnyIcon | None:
        """未选中时的图标。"""
        return self._icon

    def set_icon(self, icon: icons.IconLike) -> None:
        """设置图标。"""
        self._icon = icons.coerce(icon, ICON_SIZE)
        self.update()

    def set_selected_icon(self, icon: icons.IconLike) -> None:
        """设置选中时的图标。"""
        self._selected_icon = icons.coerce(icon, ICON_SIZE)
        self.update()

    @property
    def variant(self) -> IconButtonVariant:
        """变体。"""
        return self._variant

    def set_variant(self, variant: IconButtonVariant) -> None:
        """切换变体。"""
        self._variant = variant
        self.update()

    @property
    def checkable(self) -> bool:
        """是否为切换按钮。"""
        return self._checkable

    def set_checkable(self, checkable: bool) -> None:
        """设置是否可切换。"""
        self._checkable = checkable
        if not checkable:
            self._checked = False
        self.update()

    @property
    def checked(self) -> bool:
        """当前是否选中。"""
        return self._checked

    def set_checked(self, checked: bool) -> None:
        """设置选中状态，变化时发出 ``toggled``。"""
        checked = bool(checked) and self._checkable
        if checked == self._checked:
            return
        self._checked = checked
        self.toggled.emit(checked)
        accessibility.notify_state_changed(self, checked=True)
        self.update()

    @override
    def activate(self) -> None:
        if self._checkable:
            self.set_checked(not self._checked)
        super().activate()

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        state.checkable = self._checkable
        state.checked = self._checked

    # ---- 尺寸与形状 -------------------------------------------------------

    @override
    def sizeHint(self) -> QtCore.QSize:
        side = round(CONTAINER_SIZE + 2 * self.outer_margin)
        return QtCore.QSize(side, side)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def container_rect(self) -> QtCore.QRectF:
        rect = QtCore.QRectF(self.rect())
        return QtCore.QRectF(
            rect.center().x() - CONTAINER_SIZE / 2,
            rect.center().y() - CONTAINER_SIZE / 2,
            CONTAINER_SIZE,
            CONTAINER_SIZE,
        )

    @override
    def container_shape(self) -> shape_tokens.Shape:
        if self._shape_override is not None:
            return self._shape_override
        return shape_tokens.SHAPE_FULL

    @property
    def shape_override(self) -> shape_tokens.Shape | None:
        """显式指定的容器形状；None 时为圆形。"""
        return self._shape_override

    def set_shape(self, shape: shape_tokens.Shape | None) -> None:
        """覆盖容器形状（按钮组用它控制各边圆角）。"""
        self._shape_override = shape
        self.update()

    # ---- 颜色 -------------------------------------------------------------

    def _icon_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        selected = self._checked
        toggle = self._checkable
        match self._variant:
            case IconButtonVariant.STANDARD:
                if toggle:
                    return self.color(
                        "primary" if selected else "on_surface_variant"
                    )
                return self.color("on_surface_variant")
            case IconButtonVariant.FILLED:
                if toggle and not selected:
                    return self.color("primary")
                return self.color("on_primary")
            case IconButtonVariant.TONAL:
                if toggle and not selected:
                    return self.color("on_surface_variant")
                return self.color("on_secondary_container")
            case _:
                if toggle and selected:
                    return self.color("inverse_on_surface")
                return self.color("on_surface_variant")

    def _container_color(self) -> QtGui.QColor | None:
        selected = self._checked
        toggle = self._checkable
        disabled = not self.isEnabled()
        match self._variant:
            case IconButtonVariant.STANDARD:
                return None
            case IconButtonVariant.FILLED:
                if disabled:
                    return self._disabled_container()
                if toggle and not selected:
                    return self.color("surface_container_highest")
                return self.color("primary")
            case IconButtonVariant.TONAL:
                if disabled:
                    return self._disabled_container()
                if toggle and not selected:
                    return self.color("surface_container_highest")
                return self.color("secondary_container")
            case _:
                if toggle and selected:
                    if disabled:
                        return self._disabled_container()
                    return self.color("inverse_surface")
                return None

    def _outline_color(self) -> QtGui.QColor | None:
        if self._variant is not IconButtonVariant.OUTLINED:
            return None
        if self._checkable and self._checked:
            return None
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        return self.color("outline")

    def _disabled_container(self) -> QtGui.QColor:
        return theme_module.with_alpha(
            self.color("on_surface"), state_tokens.DISABLED_CONTAINER_OPACITY
        )

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self._icon_color()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        shape_utils.fill_shape(
            painter,
            self.container_path(),
            self._container_color(),
            self._outline_color(),
            OUTLINE_WIDTH,
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        icon = self._current_icon()
        if icon is None:
            return
        icon.paint(painter, self.icon_rect(), self._icon_color())

    def _current_icon(self) -> icons.AnyIcon | None:
        if self._checkable and self._checked:
            if self._selected_icon is not None:
                return self._selected_icon
            if self._icon is not None:
                return self._icon.with_fill(True)
        return self._icon
