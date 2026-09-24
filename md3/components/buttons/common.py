"""通用按钮（Common buttons）：elevated / filled / tonal / outlined / text。"""

from __future__ import annotations

import dataclasses
import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens


class ButtonVariant(enum.Enum):
    """通用按钮的五种变体，强调程度依次降低。"""

    ELEVATED = "elevated"
    FILLED = "filled"
    TONAL = "tonal"
    OUTLINED = "outlined"
    TEXT = "text"


@dataclasses.dataclass(frozen=True)
class ButtonTokens:
    """通用按钮的组件级令牌（dp）。"""

    container_height: float = 40.0
    icon_size: float = 18.0
    icon_gap: float = 8.0
    leading_padding: float = 24.0
    trailing_padding: float = 24.0
    leading_padding_with_icon: float = 16.0
    trailing_padding_with_icon: float = 16.0
    outline_width: float = 1.0
    label_style: typography_tokens.TypeRole = (
        typography_tokens.TypeRole.LABEL_LARGE
    )
    shape: shape_tokens.Shape = shape_tokens.SHAPE_FULL


DEFAULT_TOKENS = ButtonTokens()
TEXT_BUTTON_TOKENS = ButtonTokens(
    leading_padding=12.0,
    trailing_padding=12.0,
    leading_padding_with_icon=12.0,
    trailing_padding_with_icon=16.0,
)


class Button(widget.InteractiveWidget):
    """通用按钮。

    Args:
        text: 标签文字。
        icon: 前置图标名或 ``Icon``。
        variant: 按钮变体。
        trailing_icon: 后置图标（规范中不常用，但允许）。
        parent: 父控件。
    """

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        variant: ButtonVariant = ButtonVariant.FILLED,
        trailing_icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._variant = variant
        self._tokens = self._tokens_for(variant)
        self._icon = icons.coerce(icon, self._tokens.icon_size)
        self._trailing_icon = icons.coerce(
            trailing_icon, self._tokens.icon_size
        )
        self._shape_override: shape_tokens.Shape | None = None
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._update_elevation()

    # ---- 形状 -------------------------------------------------------------

    @property
    def shape_override(self) -> shape_tokens.Shape | None:
        """显式指定的容器形状；None 时使用变体默认的胶囊形。"""
        return self._shape_override

    def set_shape(self, shape: shape_tokens.Shape | None) -> None:
        """覆盖容器形状（按钮组、拆分按钮用它控制各边圆角）。"""
        self._shape_override = shape
        self.sync_shadow()
        self.update()

    # ---- 属性 -------------------------------------------------------------

    @property
    def text(self) -> str:
        """标签文字。"""
        return self._text

    def set_text(self, text: str) -> None:
        """设置标签文字。"""
        if text != self._text:
            self._text = text
            self.updateGeometry()
            self.update()

    @property
    def icon(self) -> icons.AnyIcon | None:
        """前置图标。"""
        return self._icon

    def set_icon(self, icon: icons.IconLike) -> None:
        """设置前置图标。"""
        self._icon = icons.coerce(icon, self._tokens.icon_size)
        self.updateGeometry()
        self.update()

    @property
    def trailing_icon(self) -> icons.AnyIcon | None:
        """后置图标。"""
        return self._trailing_icon

    def set_trailing_icon(self, icon: icons.IconLike) -> None:
        """设置后置图标。"""
        self._trailing_icon = icons.coerce(icon, self._tokens.icon_size)
        self.updateGeometry()
        self.update()

    @property
    def variant(self) -> ButtonVariant:
        """按钮变体。"""
        return self._variant

    def set_variant(self, variant: ButtonVariant) -> None:
        """切换按钮变体。"""
        self._variant = variant
        self._tokens = self._tokens_for(variant)
        self._update_elevation()
        self.updateGeometry()
        self.update()

    @property
    def tokens(self) -> ButtonTokens:
        """当前生效的组件令牌。"""
        return self._tokens

    # ---- 尺寸 -------------------------------------------------------------

    @override
    def sizeHint(self) -> QtCore.QSize:
        tokens = self._tokens
        margin = self.outer_margin
        has_icon = self._icon is not None
        has_trailing = self._trailing_icon is not None
        width = (
            tokens.leading_padding_with_icon
            if has_icon
            else tokens.leading_padding
        )
        if has_icon:
            width += tokens.icon_size + tokens.icon_gap
        width += typography.text_width(self._text, tokens.label_style)
        if has_trailing:
            width += tokens.icon_gap + tokens.icon_size
            width += tokens.trailing_padding_with_icon
        else:
            width += tokens.trailing_padding
        width = max(width, 48.0)
        return typography.size_hint(
            width + 2 * margin, tokens.container_height + 2 * margin
        )

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    # ---- 颜色 -------------------------------------------------------------

    def _content_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        match self._variant:
            case ButtonVariant.FILLED:
                return self.color("on_primary")
            case ButtonVariant.TONAL:
                return self.color("on_secondary_container")
            case _:
                return self.color("primary")

    def _container_color(self) -> QtGui.QColor | None:
        if self._variant in (ButtonVariant.OUTLINED, ButtonVariant.TEXT):
            return None
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"),
                state_tokens.DISABLED_CONTAINER_OPACITY,
            )
        match self._variant:
            case ButtonVariant.ELEVATED:
                return self.color("surface_container_low")
            case ButtonVariant.FILLED:
                return self.color("primary")
            case _:
                return self.color("secondary_container")

    def _outline_color(self) -> QtGui.QColor | None:
        if self._variant is not ButtonVariant.OUTLINED:
            return None
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        if self.focus_visible:
            return self.color("primary")
        return self.color("outline")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self._content_color()

    @override
    def container_shape(self) -> shape_tokens.Shape:
        if self._shape_override is not None:
            return self._shape_override
        return self._tokens.shape

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        shape_utils.fill_shape(
            painter,
            self.container_path(),
            self._container_color(),
            self._outline_color(),
            self._tokens.outline_width,
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        tokens = self._tokens
        rect = self.container_rect()
        color = self._content_color()
        has_icon = self._icon is not None
        left = rect.left() + (
            tokens.leading_padding_with_icon
            if has_icon
            else tokens.leading_padding
        )
        right = rect.right() - (
            tokens.trailing_padding_with_icon
            if self._trailing_icon is not None
            else tokens.trailing_padding
        )
        if self._icon is not None:
            icon_rect = QtCore.QRectF(
                left,
                rect.center().y() - tokens.icon_size / 2,
                tokens.icon_size,
                tokens.icon_size,
            )
            self._icon.paint(painter, self.visual_rect(icon_rect), color)
            left += tokens.icon_size + tokens.icon_gap
        if self._trailing_icon is not None:
            icon_rect = QtCore.QRectF(
                right - tokens.icon_size,
                rect.center().y() - tokens.icon_size / 2,
                tokens.icon_size,
                tokens.icon_size,
            )
            self._trailing_icon.paint(
                painter, self.visual_rect(icon_rect), color
            )
            right -= tokens.icon_size + tokens.icon_gap
        label_rect = QtCore.QRectF(
            left, rect.top(), max(0.0, right - left), rect.height()
        )
        typography.paint_text(
            painter,
            self.visual_rect(label_rect),
            self._text,
            tokens.label_style,
            color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    # ---- 海拔 -------------------------------------------------------------

    def _update_elevation(self) -> None:
        if not self.isEnabled():
            self.set_elevation(elevation.Level.LEVEL_0)
            return
        hovered = self.state_layer.has(state_tokens.InteractionState.HOVERED)
        pressed = self.state_layer.has(state_tokens.InteractionState.PRESSED)
        match self._variant:
            case ButtonVariant.ELEVATED:
                level = elevation.Level.LEVEL_1
                if hovered and not pressed:
                    level = elevation.Level.LEVEL_2
            case ButtonVariant.FILLED | ButtonVariant.TONAL:
                level = elevation.Level.LEVEL_0
                if hovered and not pressed:
                    level = elevation.Level.LEVEL_1
            case _:
                level = elevation.Level.LEVEL_0
        self.set_elevation(level)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._update_elevation()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._update_elevation()

    @override
    def start_press(self, position: QtCore.QPointF | None) -> None:
        super().start_press(position)
        self._update_elevation()

    @override
    def end_press(self, activate: bool) -> None:
        super().end_press(activate)
        self._update_elevation()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._update_elevation()

    @staticmethod
    def _tokens_for(variant: ButtonVariant) -> ButtonTokens:
        if variant is ButtonVariant.TEXT:
            return TEXT_BUTTON_TOKENS
        return DEFAULT_TOKENS


class ElevatedButton(Button):
    """带阴影的按钮，用于需要从背景中分离的场景。"""

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, icon, ButtonVariant.ELEVATED, parent=parent)


class FilledButton(Button):
    """高强调的主要操作按钮。"""

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, icon, ButtonVariant.FILLED, parent=parent)


class FilledTonalButton(Button):
    """中等强调的按钮，介于 filled 与 outlined 之间。"""

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, icon, ButtonVariant.TONAL, parent=parent)


class OutlinedButton(Button):
    """中等强调、带描边的次要操作按钮。"""

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, icon, ButtonVariant.OUTLINED, parent=parent)


class TextButton(Button):
    """低强调的文字按钮，常用于对话框与卡片中的次要操作。"""

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, icon, ButtonVariant.TEXT, parent=parent)
