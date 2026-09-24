"""列表项（List item）：一至三行文字，可带前置 / 后置元素。

列表项支持水平滑动手势：``set_swipe_actions`` 为两侧配置操作后，向右
滑动显露 leading 操作、向左滑动显露 trailing 操作。一侧只有一个
``dismiss=True`` 的操作时为"滑动移除"——滑过阈值后整行滑出并发出
``dismissed``；否则为"滑动显露"——松手后停在操作按钮处，点击按钮发出
``swipe_action_triggered``。
"""

from __future__ import annotations

import dataclasses
from typing import Any
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
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ONE_LINE_HEIGHT = 56.0
TWO_LINE_HEIGHT = 72.0
THREE_LINE_HEIGHT = 88.0
LEADING_PADDING = 16.0
TRAILING_PADDING = 24.0
TRAILING_PADDING_WITH_ELEMENT = 16.0
ELEMENT_GAP = 16.0
ICON_SIZE = 24.0
AVATAR_SIZE = 40.0
IMAGE_SIZE = 56.0
HEADLINE_STYLE = typography_tokens.TypeRole.BODY_LARGE
SUPPORTING_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
OVERLINE_STYLE = typography_tokens.TypeRole.LABEL_SMALL
TRAILING_TEXT_STYLE = typography_tokens.TypeRole.LABEL_SMALL
# 滑动手势：每个显露的操作占 72dp；移动超过阈值才视为滑动；滑动移除需要
# 滑过行宽的 40%。
SWIPE_ACTION_WIDTH = 72.0
SWIPE_THRESHOLD = 8.0
DISMISS_FRACTION = 0.4
SWIPE_LABEL_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM


@dataclasses.dataclass
class SwipeAction:
    """滑动显露的操作。

    Attributes:
        icon: 图标。
        text: 图标下方的说明文字（显露模式下显示）。
        color: 背景色彩角色，例如 ``error`` / ``primary_container``。
        content_color: 图标与文字的色彩角色；默认为 ``on_<color>``。
        dismiss: 为真时该侧为"滑动移除"模式（整行滑出）。
        key: 业务侧标识。
    """

    icon: icons.IconLike = None
    text: str = ""
    color: str = "primary_container"
    content_color: str | None = None
    dismiss: bool = False
    key: Any = None


class ListItem(widget.InteractiveWidget):
    """列表项。

    Args:
        headline: 主文字。
        supporting_text: 辅助文字，可为两行。
        overline: 主文字上方的小字。
        leading_icon: 前置图标。
        leading_avatar: 前置头像（40dp 圆形图片或文字首字母）。
        leading_image: 前置图片（56dp 方形）。
        trailing_icon: 后置图标。
        trailing_text: 后置文字（如时间、计数）。
        leading_widget: 前置控件（如 Checkbox）。
        trailing_widget: 后置控件（如 Switch）。
        lines: 行数 1–3；None 时按内容推断。
        parent: 父控件。
    """

    swipe_action_triggered = QtCore.Signal(object)
    dismissed = QtCore.Signal(object)
    swipe_offset_changed = QtCore.Signal(float)

    def __init__(
        self,
        headline: str,
        supporting_text: str = "",
        overline: str = "",
        leading_icon: icons.IconLike = None,
        leading_avatar: QtGui.QPixmap | str | None = None,
        leading_image: QtGui.QPixmap | None = None,
        trailing_icon: icons.IconLike = None,
        trailing_text: str = "",
        leading_widget: QtWidgets.QWidget | None = None,
        trailing_widget: QtWidgets.QWidget | None = None,
        lines: int | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._headline = headline
        self._supporting_text = supporting_text
        self._overline = overline
        self._leading_icon = icons.coerce(leading_icon, ICON_SIZE)
        self._leading_avatar = leading_avatar
        self._leading_image = leading_image
        self._trailing_icon = icons.coerce(trailing_icon, ICON_SIZE)
        self._trailing_text = trailing_text
        self._leading_widget = leading_widget
        self._trailing_widget = trailing_widget
        self._lines = lines
        self._selected = False
        self._show_divider = False
        self._leading_actions: list[SwipeAction] = []
        self._trailing_actions: list[SwipeAction] = []
        self._swipe = animation.AnimatedFloat(self, 0.0, self._on_swipe_moved)
        self._swipe.finished.connect(self._on_swipe_finished)
        self._swipe_press: QtCore.QPointF | None = None
        self._swipe_origin = 0.0
        self._swiping = False
        self._pending_dismiss: SwipeAction | None = None
        for child in (leading_widget, trailing_widget):
            if child is not None:
                child.setParent(self)
        self.set_outer_margin(0.0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 属性 -------------------------------------------------------------

    @property
    def headline(self) -> str:
        """主文字。"""
        return self._headline

    def set_headline(self, text: str) -> None:
        """设置主文字。"""
        self._headline = text
        self.update()

    @property
    def supporting_text(self) -> str:
        """辅助文字。"""
        return self._supporting_text

    def set_supporting_text(self, text: str) -> None:
        """设置辅助文字。"""
        self._supporting_text = text
        self.updateGeometry()
        self.update()

    @property
    def selected(self) -> bool:
        """是否选中。"""
        return self._selected

    def set_selected(self, selected: bool) -> None:
        """设置选中状态。"""
        if selected != self._selected:
            self._selected = selected
            accessibility.notify_state_changed(self, selected=True)
        self.update()

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ListItem

    @override
    def accessible_name(self) -> str:
        return self._headline

    @override
    def accessible_description(self) -> str:
        return self._supporting_text

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        state.selectable = True
        state.selected = self._selected

    def set_show_divider(self, show: bool) -> None:
        """是否在底部绘制分隔线。"""
        self._show_divider = show
        self.update()

    # ---- 滑动操作 ---------------------------------------------------------

    def set_swipe_actions(
        self,
        leading: list[SwipeAction] | None = None,
        trailing: list[SwipeAction] | None = None,
    ) -> None:
        """配置两侧的滑动操作；向右滑显露 leading，向左滑显露 trailing。"""
        self._leading_actions = list(leading or [])
        self._trailing_actions = list(trailing or [])
        self._swipe.set(0.0)
        self.update()

    @property
    def leading_swipe_actions(self) -> list[SwipeAction]:
        """向右滑动显露的操作。"""
        return list(self._leading_actions)

    @property
    def trailing_swipe_actions(self) -> list[SwipeAction]:
        """向左滑动显露的操作。"""
        return list(self._trailing_actions)

    @property
    def has_swipe_actions(self) -> bool:
        """是否配置了滑动操作。"""
        return bool(self._leading_actions or self._trailing_actions)

    @property
    def swipe_offset(self) -> float:
        """内容的水平偏移（向右为正）。"""
        return self._swipe.value

    @property
    def swipe_open(self) -> bool:
        """是否停在显露操作的状态。"""
        return abs(self._swipe.target) > 0.5 and self._pending_dismiss is None

    def _actions_for(self, offset: float) -> list[SwipeAction]:
        """按（视觉）滑动方向返回显露的操作；RTL 下起始侧在右边。"""
        logical = -offset if self.is_rtl() else offset
        if logical > 0:
            return self._leading_actions
        if logical < 0:
            return self._trailing_actions
        return []

    def _is_dismiss_side(self, offset: float) -> bool:
        actions = self._actions_for(offset)
        return len(actions) == 1 and actions[0].dismiss

    def _reveal_width(self, offset: float) -> float:
        actions = self._actions_for(offset)
        if not actions:
            return 0.0
        if self._is_dismiss_side(offset):
            return float(self.width())
        return SWIPE_ACTION_WIDTH * len(actions)

    def open_swipe(self, trailing: bool = True, animate: bool = True) -> None:
        """显露一侧的操作（滑动移除模式的一侧不可显露）。"""
        sign = -1.0 if trailing else 1.0
        if self.is_rtl():
            sign = -sign
        if not self._actions_for(sign) or self._is_dismiss_side(sign):
            return
        self._settle(sign * self._reveal_width(sign), animate)

    def close_swipe(self, animate: bool = True) -> None:
        """收回显露的操作。"""
        self._settle(0.0, animate)

    def cancel_swipe(self) -> None:
        """放弃进行中的滑动手势并收回。"""
        self._swipe_press = None
        self._swiping = False
        self.close_swipe()

    def _settle(self, target: float, animate: bool) -> None:
        if animate:
            self._swipe.animate_to(
                target, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
            )
        else:
            self._swipe.set(target)

    def _on_swipe_moved(self) -> None:
        self._layout_children()
        self.update()
        self.swipe_offset_changed.emit(self._swipe.value)

    def _on_swipe_finished(self) -> None:
        action = self._pending_dismiss
        if action is None:
            return
        self._pending_dismiss = None
        self.swipe_action_triggered.emit(action)
        self.dismissed.emit(action)

    def _dismiss(self, direction: float) -> None:
        action = self._actions_for(direction)[0]
        self._pending_dismiss = action
        self._settle(direction * float(self.width()), animate=True)

    def swipe_action_slots(self) -> list[tuple[SwipeAction, QtCore.QRectF]]:
        """当前显露区域内各操作的矩形（显露模式），按屏幕顺序排列。"""
        offset = self._swipe.value
        actions = self._actions_for(offset)
        if not actions or self._is_dismiss_side(offset):
            return []
        revealed = abs(offset)
        slot = revealed / len(actions)
        rect = QtCore.QRectF(self.rect())
        slots = []
        for index, action in enumerate(actions):
            if offset > 0:
                x = rect.left() + index * slot
            else:
                x = rect.right() - revealed + index * slot
            slots.append(
                (action, QtCore.QRectF(x, rect.top(), slot, rect.height()))
            )
        return slots

    def _action_at(self, point: QtCore.QPointF) -> SwipeAction | None:
        for action, slot in self.swipe_action_slots():
            if slot.contains(point):
                return action
        return None

    def _content_contains(self, point: QtCore.QPointF) -> bool:
        return (
            QtCore.QRectF(self.rect())
            .translated(self._swipe.value, 0.0)
            .contains(point)
        )

    def _clamp_offset(self, offset: float) -> float:
        if offset > 0:
            return min(offset, self._reveal_width(1.0))
        if offset < 0:
            return max(offset, -self._reveal_width(-1.0))
        return 0.0

    def _finish_swipe(self) -> None:
        offset = self._swipe.value
        if abs(offset) < 0.5:
            self._settle(0.0, animate=True)
            return
        if self._is_dismiss_side(offset):
            if abs(offset) >= self.width() * DISMISS_FRACTION:
                self._dismiss(1.0 if offset > 0 else -1.0)
            else:
                self._settle(0.0, animate=True)
            return
        reveal = self._reveal_width(offset)
        if abs(offset) >= reveal / 2:
            self._settle(reveal if offset > 0 else -reveal, animate=True)
        else:
            self._settle(0.0, animate=True)

    @property
    def trailing_widget(self) -> QtWidgets.QWidget | None:
        """后置控件。"""
        return self._trailing_widget

    @property
    def leading_widget(self) -> QtWidgets.QWidget | None:
        """前置控件。"""
        return self._leading_widget

    def line_count(self) -> int:
        """实际行数。"""
        if self._lines is not None:
            return max(1, min(3, self._lines))
        lines = 1
        if self._supporting_text:
            lines += 1
            if "\n" in self._supporting_text or len(self._supporting_text) > 60:
                lines += 1
        if self._overline:
            lines += 1
        return max(1, min(3, lines))

    # ---- 几何 -------------------------------------------------------------

    def _height(self) -> float:
        lines = self.line_count()
        if lines == 1:
            height = ONE_LINE_HEIGHT
        elif lines == 2:
            height = TWO_LINE_HEIGHT
        else:
            height = THREE_LINE_HEIGHT
        if self._leading_image is not None:
            height = max(height, TWO_LINE_HEIGHT)
        return height

    def _leading_width(self) -> float:
        if self._leading_widget is not None:
            return self._leading_widget.sizeHint().width()
        if self._leading_image is not None:
            return IMAGE_SIZE
        if self._leading_avatar is not None:
            return AVATAR_SIZE
        if self._leading_icon is not None:
            return ICON_SIZE
        return 0.0

    def _trailing_width(self) -> float:
        if self._trailing_widget is not None:
            return self._trailing_widget.sizeHint().width()
        if self._trailing_icon is not None:
            return ICON_SIZE
        if self._trailing_text:
            return typography.text_width(
                self._trailing_text, TRAILING_TEXT_STYLE
            )
        return 0.0

    def text_rect(self) -> QtCore.QRectF:
        """文字区域矩形（已按布局方向镜像）。"""
        rect = QtCore.QRectF(self.rect())
        left = rect.left() + LEADING_PADDING
        leading = self._leading_width()
        if leading:
            left += leading + ELEMENT_GAP
        trailing = self._trailing_width()
        right = rect.right() - (
            TRAILING_PADDING_WITH_ELEMENT + trailing + ELEMENT_GAP
            if trailing
            else TRAILING_PADDING
        )
        return self.visual_rect(
            QtCore.QRectF(
                left, rect.top(), max(0.0, right - left), rect.height()
            )
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = LEADING_PADDING + TRAILING_PADDING
        width += self._leading_width() + self._trailing_width()
        width += typography.text_width(self._headline, HEADLINE_STYLE)
        return typography.size_hint(max(width, 200.0), self._height())

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return typography.size_hint(120.0, self._height())

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self) -> None:
        rect = QtCore.QRectF(self.rect())
        offset = self._swipe.value
        if self._leading_widget is not None:
            hint = self._leading_widget.sizeHint()
            logical = QtCore.QRectF(
                rect.left() + LEADING_PADDING,
                rect.center().y() - hint.height() / 2,
                hint.width(),
                hint.height(),
            )
            self._leading_widget.setGeometry(
                self.visual_rect(logical).translated(offset, 0.0).toRect()
            )
        if self._trailing_widget is not None:
            hint = self._trailing_widget.sizeHint()
            logical = QtCore.QRectF(
                rect.right() - TRAILING_PADDING_WITH_ELEMENT - hint.width(),
                rect.center().y() - hint.height() / 2,
                hint.width(),
                hint.height(),
            )
            self._trailing_widget.setGeometry(
                self.visual_rect(logical).translated(offset, 0.0).toRect()
            )

    # ---- 颜色 -------------------------------------------------------------

    def _text_color(self, role: str) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        return self.color(role)

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("on_surface")

    # ---- 事件 -------------------------------------------------------------

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.has_swipe_actions
        ):
            self._swipe_press = event.position()
            self._swipe_origin = self._swipe.value
            self._swiping = False
            if self.swipe_open and not self._content_contains(event.position()):
                # 按在显露的操作上：不开始内容的按压。
                event.accept()
                return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._swipe_press is not None:
            delta = event.position() - self._swipe_press
            if not self._swiping and (
                abs(delta.x()) > SWIPE_THRESHOLD
                and abs(delta.x()) > abs(delta.y())
            ):
                self._swiping = True
                self.cancel_press()
            if self._swiping:
                self._swipe.set(
                    self._clamp_offset(self._swipe_origin + delta.x())
                )
                event.accept()
                return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._swipe_press is None:
            super().mouseReleaseEvent(event)
            return
        self._swipe_press = None
        if self._swiping:
            self._swiping = False
            self._finish_swipe()
            event.accept()
            return
        if self.swipe_open:
            action = self._action_at(event.position())
            self.cancel_press()
            self.close_swipe()
            if action is not None:
                self.swipe_action_triggered.emit(action)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        offset = self._swipe.value
        if abs(offset) < 0.5:
            super().paint(painter)
            return
        self._paint_swipe_background(painter, offset)
        painter.save()
        painter.translate(offset, 0.0)
        super().paint(painter)
        painter.restore()

    def _swipe_colors(
        self, action: SwipeAction
    ) -> tuple[QtGui.QColor, QtGui.QColor]:
        background = self.color(action.color)
        role = action.content_color or f"on_{action.color}"
        try:
            content = self.color(role)
        except KeyError:
            content = self.color("on_surface")
        return background, content

    def _paint_swipe_background(
        self, painter: QtGui.QPainter, offset: float
    ) -> None:
        rect = QtCore.QRectF(self.rect())
        actions = self._actions_for(offset)
        if not actions:
            return
        if self._is_dismiss_side(offset):
            background, content = self._swipe_colors(actions[0])
            painter.fillRect(rect, background)
            icon = icons.coerce(actions[0].icon, ICON_SIZE)
            if icon is not None:
                x = (
                    rect.left() + LEADING_PADDING
                    if offset > 0
                    else rect.right() - LEADING_PADDING - ICON_SIZE
                )
                icon.paint(
                    painter,
                    QtCore.QRectF(
                        x,
                        rect.center().y() - ICON_SIZE / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    ),
                    content,
                )
            return
        label_height = self.theme.style(SWIPE_LABEL_STYLE).line_height
        for action, slot in self.swipe_action_slots():
            background, content = self._swipe_colors(action)
            painter.fillRect(slot, background)
            painter.save()
            painter.setClipRect(slot)
            icon = icons.coerce(action.icon, ICON_SIZE)
            block = ICON_SIZE + (4 + label_height if action.text else 0)
            top = slot.center().y() - block / 2
            center_x = slot.center().x()
            if icon is not None:
                icon.paint(
                    painter,
                    QtCore.QRectF(
                        center_x - ICON_SIZE / 2, top, ICON_SIZE, ICON_SIZE
                    ),
                    content,
                )
            if action.text:
                typography.paint_text(
                    painter,
                    QtCore.QRectF(
                        center_x - SWIPE_ACTION_WIDTH / 2,
                        top + ICON_SIZE + 4,
                        SWIPE_ACTION_WIDTH,
                        label_height,
                    ),
                    action.text,
                    SWIPE_LABEL_STYLE,
                    content,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
            painter.restore()

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        if abs(self._swipe.value) > 0.5:
            # 内容滑开时需要不透明底色，避免显露区透出。
            painter.fillRect(rect, self.color("surface"))
        if self._selected:
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_NONE),
                self.color("secondary_container"),
            )
        if self._show_divider:
            painter.fillRect(
                QtCore.QRectF(rect.left(), rect.bottom() - 1, rect.width(), 1),
                self.color("outline_variant"),
            )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        self._paint_leading(painter, rect)
        self._paint_trailing(painter, rect)
        self._paint_text(painter)

    def _paint_leading(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        left = rect.left() + LEADING_PADDING
        lines = self.line_count()
        top_aligned = lines >= 3
        if self._leading_image is not None:
            image_rect = self.visual_rect(
                QtCore.QRectF(
                    left,
                    rect.top()
                    + (8 if top_aligned else (rect.height() - IMAGE_SIZE) / 2),
                    IMAGE_SIZE,
                    IMAGE_SIZE,
                )
            )
            painter.drawPixmap(image_rect.toRect(), self._leading_image)
        elif self._leading_avatar is not None:
            avatar_rect = self.visual_rect(
                QtCore.QRectF(
                    left,
                    rect.top()
                    + (8 if top_aligned else (rect.height() - AVATAR_SIZE) / 2),
                    AVATAR_SIZE,
                    AVATAR_SIZE,
                )
            )
            path = QtGui.QPainterPath()
            path.addEllipse(avatar_rect)
            if isinstance(self._leading_avatar, QtGui.QPixmap):
                painter.save()
                painter.setClipPath(path)
                painter.drawPixmap(avatar_rect.toRect(), self._leading_avatar)
                painter.restore()
            else:
                shape_utils.fill_shape(
                    painter, path, self.color("primary_container")
                )
                typography.paint_text(
                    painter,
                    avatar_rect,
                    str(self._leading_avatar)[:1],
                    typography_tokens.TypeRole.TITLE_MEDIUM,
                    self.color("on_primary_container"),
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
        elif self._leading_icon is not None:
            icon_rect = self.visual_rect(
                QtCore.QRectF(
                    left,
                    rect.top()
                    + (16 if top_aligned else (rect.height() - ICON_SIZE) / 2),
                    ICON_SIZE,
                    ICON_SIZE,
                )
            )
            self._leading_icon.paint(
                painter, icon_rect, self._text_color("on_surface_variant")
            )

    def _paint_trailing(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        if self._trailing_widget is not None:
            return
        top_aligned = self.line_count() >= 3
        right = rect.right() - TRAILING_PADDING_WITH_ELEMENT
        if self._trailing_icon is not None:
            icon_rect = self.visual_rect(
                QtCore.QRectF(
                    right - ICON_SIZE,
                    rect.top()
                    + (16 if top_aligned else (rect.height() - ICON_SIZE) / 2),
                    ICON_SIZE,
                    ICON_SIZE,
                )
            )
            self._trailing_icon.paint(
                painter, icon_rect, self._text_color("on_surface_variant")
            )
        elif self._trailing_text:
            width = typography.text_width(
                self._trailing_text, TRAILING_TEXT_STYLE
            )
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - width,
                        rect.top() + (16 if top_aligned else 0),
                        width,
                        16 if top_aligned else rect.height(),
                    )
                ),
                self._trailing_text,
                TRAILING_TEXT_STYLE,
                self._text_color("on_surface_variant"),
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )

    def _paint_text(self, painter: QtGui.QPainter) -> None:
        area = self.text_rect()
        theme = self.theme
        headline_height = theme.style(HEADLINE_STYLE).line_height
        supporting_height = theme.style(SUPPORTING_STYLE).line_height
        overline_height = theme.style(OVERLINE_STYLE).line_height
        lines = self.line_count()
        block_height = headline_height
        if self._overline:
            block_height += overline_height
        supporting_lines = 0
        if self._supporting_text:
            supporting_lines = max(1, lines - 1 - (1 if self._overline else 0))
            block_height += supporting_height * supporting_lines
        if lines >= 3:
            y = area.top() + 12
        else:
            y = area.center().y() - block_height / 2
        alignment = self.start_alignment()
        if self._overline:
            typography.paint_text(
                painter,
                QtCore.QRectF(area.left(), y, area.width(), overline_height),
                self._overline,
                OVERLINE_STYLE,
                self._text_color("on_surface_variant"),
                alignment,
            )
            y += overline_height
        typography.paint_text(
            painter,
            QtCore.QRectF(area.left(), y, area.width(), headline_height),
            self._headline,
            HEADLINE_STYLE,
            self._text_color("on_surface"),
            alignment,
        )
        y += headline_height
        if self._supporting_text:
            if supporting_lines > 1:
                typography.paint_multiline(
                    painter,
                    QtCore.QRectF(
                        area.left(),
                        y,
                        area.width(),
                        supporting_height * supporting_lines,
                    ),
                    self._supporting_text,
                    SUPPORTING_STYLE,
                    self._text_color("on_surface_variant"),
                    max_lines=supporting_lines,
                    alignment=alignment,
                )
            else:
                typography.paint_text(
                    painter,
                    QtCore.QRectF(
                        area.left(), y, area.width(), supporting_height
                    ),
                    self._supporting_text,
                    SUPPORTING_STYLE,
                    self._text_color("on_surface_variant"),
                    alignment,
                )
