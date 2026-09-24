"""纸片（Chips）。

四种类型共用同一实现：assist（辅助操作）、filter（可选过滤）、
input（可移除的输入项）、suggestion（建议）。支持 elevated 变体。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

CONTAINER_HEIGHT = 32.0
ICON_SIZE = 18.0
AVATAR_SIZE = 24.0
PADDING = 16.0
ICON_PADDING = 8.0
ICON_GAP = 8.0
OUTLINE_WIDTH = 1.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE


class ChipKind(enum.Enum):
    """纸片类型。"""

    ASSIST = "assist"
    FILTER = "filter"
    INPUT = "input"
    SUGGESTION = "suggestion"


class Chip(widget.InteractiveWidget):
    """纸片。

    Args:
        text: 标签。
        kind: 类型。
        icon: 前置图标。
        trailing_icon: 后置图标；input 类型默认为 ``close``。
        elevated: 是否使用带阴影的 elevated 样式。
        selected: 初始选中（filter / input）。
        avatar: input 类型的头像图片，替代前置图标。
        parent: 父控件。
    """

    toggled = QtCore.Signal(bool)
    removed = QtCore.Signal()
    trailing_clicked = QtCore.Signal()

    def __init__(
        self,
        text: str,
        kind: ChipKind = ChipKind.ASSIST,
        icon: icons.IconLike = None,
        trailing_icon: icons.IconLike = None,
        elevated: bool = False,
        selected: bool = False,
        avatar: QtGui.QPixmap | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._kind = kind
        self._icon = icons.coerce(icon, ICON_SIZE)
        if trailing_icon is None and kind is ChipKind.INPUT:
            trailing_icon = "close"
        self._trailing_icon = icons.coerce(trailing_icon, ICON_SIZE)
        self._elevated = elevated
        self._selected = selected and kind in (ChipKind.FILTER, ChipKind.INPUT)
        self._avatar = avatar
        self._trailing_pressed = False
        # 选中态过渡：容器色与勾选图标淡入。
        self._select = animation.AnimatedFloat(
            self, 1.0 if self._selected else 0.0, self.update
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._update_elevation()

    # ---- 属性 -------------------------------------------------------------

    @property
    def text(self) -> str:
        """标签。"""
        return self._text

    def set_text(self, text: str) -> None:
        """设置标签。"""
        self._text = text
        self.updateGeometry()
        self.update()

    @property
    def kind(self) -> ChipKind:
        """类型。"""
        return self._kind

    @property
    def selected(self) -> bool:
        """是否选中。"""
        return self._selected

    def set_selected(self, selected: bool) -> None:
        """设置选中状态（filter / input 有效）。"""
        if self._kind not in (ChipKind.FILTER, ChipKind.INPUT):
            return
        selected = bool(selected)
        if selected == self._selected:
            return
        self._selected = selected
        self._select.animate_to(
            1.0 if selected else 0.0, motion.SHORT4, motion.STANDARD
        )
        self.toggled.emit(selected)
        accessibility.notify_state_changed(self, checked=True)
        self._update_elevation()
        self.updateGeometry()
        self.update()

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        if self._kind is ChipKind.FILTER:
            return QtGui.QAccessible.Role.CheckBox
        return QtGui.QAccessible.Role.Button

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        if self._kind in (ChipKind.FILTER, ChipKind.INPUT):
            state.checkable = True
            state.checked = self._selected

    @property
    def elevated(self) -> bool:
        """是否为 elevated 样式。"""
        return self._elevated

    def set_elevated(self, elevated: bool) -> None:
        """设置是否为 elevated 样式。"""
        self._elevated = elevated
        self._update_elevation()
        self.update()

    def set_icon(self, icon: icons.IconLike) -> None:
        """设置前置图标。"""
        self._icon = icons.coerce(icon, ICON_SIZE)
        self.updateGeometry()
        self.update()

    def set_trailing_icon(self, icon: icons.IconLike) -> None:
        """设置后置图标。"""
        self._trailing_icon = icons.coerce(icon, ICON_SIZE)
        self.updateGeometry()
        self.update()

    @override
    def activate(self) -> None:
        if self._kind is ChipKind.FILTER:
            self.set_selected(not self._selected)
        super().activate()

    # ---- 几何 -------------------------------------------------------------

    def _leading_icon(self) -> icons.AnyIcon | None:
        if self._kind is ChipKind.FILTER and self._selected:
            return icons.Icon("check", ICON_SIZE)
        return self._icon

    def _has_leading(self) -> bool:
        return self._avatar is not None or self._leading_icon() is not None

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = 0.0
        if self._avatar is not None:
            width += 4.0 + AVATAR_SIZE + ICON_GAP
        elif self._leading_icon() is not None:
            width += ICON_PADDING + ICON_SIZE + ICON_GAP
        else:
            width += PADDING
        width += typography.text_width(self._text, LABEL_STYLE)
        if self._trailing_icon is not None:
            width += ICON_GAP + ICON_SIZE + ICON_PADDING
        else:
            width += PADDING
        margin = self.outer_margin
        return typography.size_hint(
            width + 2 * margin, CONTAINER_HEIGHT + 2 * margin
        )

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_SMALL

    def trailing_rect(self) -> QtCore.QRectF:
        """后置图标的矩形（含 8dp 内边距），用于命中测试。"""
        if self._trailing_icon is None:
            return QtCore.QRectF()
        rect = self.container_rect()
        return self.visual_rect(
            QtCore.QRectF(
                rect.right() - ICON_PADDING - ICON_SIZE - 4,
                rect.top(),
                ICON_SIZE + ICON_PADDING + 4,
                rect.height(),
            )
        )

    # ---- 颜色 -------------------------------------------------------------

    def _label_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._selected:
            return self.color("on_secondary_container")
        if self._kind is ChipKind.SUGGESTION:
            return self.color("on_surface_variant")
        return self.color("on_surface")

    def _icon_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._selected:
            return self.color("on_secondary_container")
        if self._kind in (
            ChipKind.ASSIST,
            ChipKind.FILTER,
            ChipKind.SUGGESTION,
        ):
            return self.color("primary")
        return self.color("on_surface_variant")

    def _trailing_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._selected:
            return self.color("on_secondary_container")
        return self.color("on_surface_variant")

    def _container_color(
        self, selected: bool | None = None
    ) -> QtGui.QColor | None:
        selected = self._selected if selected is None else selected
        if selected:
            if not self.isEnabled():
                return theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTAINER_OPACITY,
                )
            return self.color("secondary_container")
        if self._elevated:
            if not self.isEnabled():
                return theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTAINER_OPACITY,
                )
            return self.color("surface_container_low")
        return None

    def _outline_color(
        self, selected: bool | None = None
    ) -> QtGui.QColor | None:
        selected = self._selected if selected is None else selected
        if selected or self._elevated:
            return None
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        return self.color("outline_variant")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self._label_color()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        path = self.container_path()
        progress = self._select.value
        if progress <= 0.001 or progress >= 0.999:
            shape_utils.fill_shape(
                painter,
                path,
                self._container_color(),
                self._outline_color(),
                OUTLINE_WIDTH,
            )
            return
        # 过渡中：未选中外观淡出，选中容器淡入。
        painter.save()
        painter.setOpacity(1.0 - progress)
        shape_utils.fill_shape(
            painter,
            path,
            self._container_color(False),
            self._outline_color(False),
            OUTLINE_WIDTH,
        )
        painter.setOpacity(progress)
        shape_utils.fill_shape(painter, path, self._container_color(True))
        painter.restore()

    def _paint_leading_icon(
        self, painter: QtGui.QPainter, icon_rect: QtCore.QRectF
    ) -> None:
        """绘制前置图标；filter 纸片在选中过渡中交叉淡入勾选图标。"""
        color = self._icon_color()
        if self._kind is not ChipKind.FILTER:
            icon = self._leading_icon()
            if icon is not None:
                icon.paint(painter, icon_rect, color)
            return
        progress = self._select.value
        base = self._icon
        if base is not None and progress < 0.999:
            painter.save()
            painter.setOpacity(1.0 - progress)
            base.paint(painter, icon_rect, color)
            painter.restore()
        if progress > 0.001:
            scale = 0.6 + 0.4 * progress
            size = ICON_SIZE * scale
            scaled = QtCore.QRectF(
                icon_rect.center().x() - size / 2,
                icon_rect.center().y() - size / 2,
                size,
                size,
            )
            painter.save()
            painter.setOpacity(progress)
            icons.Icon("check", size).paint(painter, scaled, color)
            painter.restore()

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        left = rect.left()
        if self._avatar is not None:
            avatar_rect = self.visual_rect(
                QtCore.QRectF(
                    left + 4.0,
                    rect.center().y() - AVATAR_SIZE / 2,
                    AVATAR_SIZE,
                    AVATAR_SIZE,
                )
            )
            painter.save()
            path = QtGui.QPainterPath()
            path.addEllipse(avatar_rect)
            painter.setClipPath(path)
            painter.drawPixmap(avatar_rect.toRect(), self._avatar)
            painter.restore()
            left += 4.0 + AVATAR_SIZE + ICON_GAP
        else:
            if self._leading_icon() is not None:
                icon_rect = QtCore.QRectF(
                    left + ICON_PADDING,
                    rect.center().y() - ICON_SIZE / 2,
                    ICON_SIZE,
                    ICON_SIZE,
                )
                self._paint_leading_icon(painter, self.visual_rect(icon_rect))
                left += ICON_PADDING + ICON_SIZE + ICON_GAP
            else:
                left += PADDING
        right = rect.right()
        if self._trailing_icon is not None:
            icon_rect = QtCore.QRectF(
                right - ICON_PADDING - ICON_SIZE,
                rect.center().y() - ICON_SIZE / 2,
                ICON_SIZE,
                ICON_SIZE,
            )
            self._trailing_icon.paint(
                painter, self.visual_rect(icon_rect), self._trailing_color()
            )
            right -= ICON_PADDING + ICON_SIZE + ICON_GAP
        else:
            right -= PADDING
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(
                    left, rect.top(), max(0.0, right - left), rect.height()
                )
            ),
            self._text,
            LABEL_STYLE,
            self._label_color(),
            self.start_alignment(),
        )

    # ---- 海拔与事件 -------------------------------------------------------

    def _update_elevation(self) -> None:
        if not self._elevated or not self.isEnabled():
            self.set_elevation(elevation.Level.LEVEL_0)
            return
        hovered = self.state_layer.has(state_tokens.InteractionState.HOVERED)
        self.set_elevation(
            elevation.Level.LEVEL_2 if hovered else elevation.Level.LEVEL_1
        )

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._update_elevation()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._update_elevation()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._update_elevation()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.is_interactive()
            and self._trailing_icon is not None
            and self.trailing_rect().contains(event.position())
        ):
            self._trailing_pressed = True
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._trailing_pressed:
            self._trailing_pressed = False
            if self.trailing_rect().contains(event.position()):
                self.trailing_clicked.emit()
                if self._kind is ChipKind.INPUT:
                    self.removed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if self._kind is ChipKind.INPUT and event.key() in (
            QtCore.Qt.Key.Key_Delete,
            QtCore.Qt.Key.Key_Backspace,
        ):
            self.removed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class AssistChip(Chip):
    """辅助纸片：代表与内容相关的智能操作。"""

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        elevated: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            text, ChipKind.ASSIST, icon, elevated=elevated, parent=parent
        )


class FilterChip(Chip):
    """过滤纸片：可切换选中，用于筛选内容。"""

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        selected: bool = False,
        elevated: bool = False,
        trailing_icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            text,
            ChipKind.FILTER,
            icon,
            trailing_icon=trailing_icon,
            elevated=elevated,
            selected=selected,
            parent=parent,
        )


class InputChip(Chip):
    """输入纸片：表示用户输入的信息，可移除。"""

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        avatar: QtGui.QPixmap | None = None,
        selected: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            text,
            ChipKind.INPUT,
            icon,
            selected=selected,
            avatar=avatar,
            parent=parent,
        )


class SuggestionChip(Chip):
    """建议纸片：帮助用户缩小意图或提供动态建议。"""

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        elevated: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            text, ChipKind.SUGGESTION, icon, elevated=elevated, parent=parent
        )
