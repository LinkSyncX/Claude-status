"""分段按钮（Segmented buttons）：2–5 个相邻选项，支持单选或多选。"""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import focus_ring
from md3.core import ripple as ripple_module
from md3.core import shape as shape_utils
from md3.core import state_layer as state_layer_module
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

CONTAINER_HEIGHT = 40.0
MIN_SEGMENT_WIDTH = 48.0
ICON_SIZE = 18.0
ICON_GAP = 8.0
PADDING = 12.0
OUTLINE_WIDTH = 1.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE


@dataclasses.dataclass
class Segment:
    """一个分段。

    Attributes:
        text: 标签。
        icon: 图标名或 ``Icon``；选中时若显示勾选图标则替换它。
        enabled: 是否可用。
        key: 业务侧标识，随信号一起返回。
    """

    text: str = ""
    icon: icons.IconLike = None
    enabled: bool = True
    key: Any = None


class SegmentedButton(widget.MaterialWidget):
    """分段按钮。

    Args:
        segments: 分段列表（字符串会被转换为仅含文字的 ``Segment``）。
        multi_select: 是否允许多选。
        selected: 初始选中的下标集合。
        show_check_icon: 选中时是否显示勾选图标。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(list)

    def __init__(
        self,
        segments: list[Segment | str],
        multi_select: bool = False,
        selected: set[int] | list[int] | None = None,
        show_check_icon: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._segments = [
            Segment(text=item) if isinstance(item, str) else item
            for item in segments
        ]
        self._multi_select = multi_select
        self._selected: set[int] = set(selected or ())
        self._show_check_icon = show_check_icon
        self._hovered = -1
        self._pressed = -1
        self._focused = 0
        self._focus_visible = False
        self._outer_margin = widget.DEFAULT_OUTER_MARGIN
        self._layers = [
            state_layer_module.StateLayer(self, on_change=self.update)
            for _ in self._segments
        ]
        self._ripples = [
            ripple_module.RippleController(self, on_change=self.update)
            for _ in self._segments
        ]
        self._focus_anim = animation.AnimatedFloat(self, 1.0, self.update)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 属性 -------------------------------------------------------------

    @property
    def segments(self) -> list[Segment]:
        """分段列表（只读视图，修改后请调用 ``set_segments``）。"""
        return list(self._segments)

    def set_segments(self, segments: list[Segment | str]) -> None:
        """替换全部分段并清空选择。"""
        self._segments = [
            Segment(text=item) if isinstance(item, str) else item
            for item in segments
        ]
        self._selected.clear()
        self._layers = [
            state_layer_module.StateLayer(self, on_change=self.update)
            for _ in self._segments
        ]
        self._ripples = [
            ripple_module.RippleController(self, on_change=self.update)
            for _ in self._segments
        ]
        self._focused = 0
        self.updateGeometry()
        self.update()

    @property
    def selected_indices(self) -> list[int]:
        """已选中的下标，升序。"""
        return sorted(self._selected)

    @property
    def selected_keys(self) -> list[Any]:
        """已选中分段的 key（未设置 key 时为文字）。"""
        return [
            self._segments[i].key
            if self._segments[i].key is not None
            else self._segments[i].text
            for i in self.selected_indices
        ]

    def set_selected(self, indices: set[int] | list[int]) -> None:
        """设置选中集合；单选模式下只保留第一个。"""
        new = {i for i in indices if 0 <= i < len(self._segments)}
        if not self._multi_select and len(new) > 1:
            new = {min(new)}
        if new != self._selected:
            self._selected = new
            self.selection_changed.emit(self.selected_indices)
            accessibility.notify_value_changed(self, self.accessible_value())
            self.update()

    def is_selected(self, index: int) -> bool:
        """某个分段是否选中。"""
        return index in self._selected

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    @override
    def accessible_value(self) -> str:
        # 分段由同一控件绘制，把选中分段的文字作为取值播报。
        return "、".join(self._segments[i].text for i in self.selected_indices)

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        state.multiSelectable = self._multi_select

    def toggle(self, index: int) -> None:
        """切换某个分段；单选模式下不允许取消最后一个选中项。"""
        if index < 0 or index >= len(self._segments):
            return
        if not self._segments[index].enabled:
            return
        if self._multi_select:
            new = set(self._selected)
            if index in new:
                new.remove(index)
            else:
                new.add(index)
        else:
            new = {index}
        self.set_selected(new)

    @property
    def multi_select(self) -> bool:
        """是否多选。"""
        return self._multi_select

    # ---- 几何 -------------------------------------------------------------

    def _segment_width(self, index: int) -> float:
        segment = self._segments[index]
        width = 2 * PADDING
        has_icon = segment.icon is not None or (
            self._show_check_icon and index in self._selected
        )
        if has_icon:
            width += ICON_SIZE + ICON_GAP
        width += typography.text_width(segment.text, LABEL_STYLE)
        return max(MIN_SEGMENT_WIDTH, width)

    def _natural_widths(self) -> list[float]:
        # 各分段等宽：取最宽者，使按钮在切换选中图标时不跳动。
        widest = max(
            (
                self._segment_width(i) + (ICON_SIZE + ICON_GAP)
                if self._show_check_icon
                and self._segments[i].icon is None
                and i not in self._selected
                else self._segment_width(i)
                for i in range(len(self._segments))
            ),
            default=MIN_SEGMENT_WIDTH,
        )
        return [widest] * len(self._segments)

    def container_rect(self) -> QtCore.QRectF:
        """整个分段按钮的容器矩形。"""
        margin = self._outer_margin
        return QtCore.QRectF(self.rect()).adjusted(
            margin, margin, -margin, -margin
        )

    def segment_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个分段的矩形。"""
        rect = self.container_rect()
        count = len(self._segments)
        if count == 0:
            return QtCore.QRectF()
        width = rect.width() / count
        return self.visual_rect(
            QtCore.QRectF(
                rect.left() + index * width, rect.top(), width, rect.height()
            )
        )

    def _segment_shape(self, index: int) -> shape_tokens.Shape:
        count = len(self._segments)
        if count == 1:
            return shape_tokens.SHAPE_FULL
        first, last = index == 0, index == count - 1
        if self.is_rtl():
            # 第一段位于右侧，因此圆角也要交换。
            first, last = last, first
        if first:
            return shape_tokens.Shape.start(shape_tokens.FULL)
        if last:
            return shape_tokens.Shape.end(shape_tokens.FULL)
        return shape_tokens.SHAPE_NONE

    def _segment_path(self, index: int) -> QtGui.QPainterPath:
        return shape_utils.rounded_rect_path(
            self.segment_rect(index), self._segment_shape(index)
        )

    def _index_at(self, point: QtCore.QPointF) -> int:
        for index in range(len(self._segments)):
            if self.segment_rect(index).contains(point):
                return index
        return -1

    @override
    def sizeHint(self) -> QtCore.QSize:
        margin = self._outer_margin
        width = sum(self._natural_widths())
        return typography.size_hint(
            width + 2 * margin, CONTAINER_HEIGHT + 2 * margin
        )

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    # ---- 颜色 -------------------------------------------------------------

    def _content_color(self, index: int) -> QtGui.QColor:
        segment = self._segments[index]
        if not self.isEnabled() or not segment.enabled:
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if index in self._selected:
            return self.color("on_secondary_container")
        return self.color("on_surface")

    def _outline_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        return self.color("outline")

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        if not self._segments:
            return
        outline = self._outline_color()
        container = self.container_rect()
        outer_path = shape_utils.rounded_rect_path(
            container, shape_tokens.SHAPE_FULL
        )
        painter.save()
        painter.setClipPath(outer_path)
        for index in range(len(self._segments)):
            self._paint_segment(painter, index)
        painter.restore()
        # 外框与分隔线。
        shape_utils.fill_shape(
            painter, outer_path, None, outline, OUTLINE_WIDTH
        )
        pen = QtGui.QPen(outline, OUTLINE_WIDTH)
        painter.setPen(pen)
        for index in range(1, len(self._segments)):
            x = self.segment_rect(index).left()
            painter.drawLine(
                QtCore.QPointF(x, container.top()),
                QtCore.QPointF(x, container.bottom()),
            )
        if self._focus_visible and 0 <= self._focused < len(self._segments):
            focus_ring.paint_focus_ring(
                painter,
                self.segment_rect(self._focused),
                self._segment_shape(self._focused),
                self.color("secondary"),
                max_extent=self._outer_margin,
                progress=self._focus_anim.value,
            )

    def _restart_focus_animation(self) -> None:
        self._focus_anim.set(0.0)
        self._focus_anim.animate_to(
            1.0, focus_ring.ANIMATION_DURATION_MS, motion.STANDARD
        )

    def _paint_segment(self, painter: QtGui.QPainter, index: int) -> None:
        segment = self._segments[index]
        rect = self.segment_rect(index)
        path = QtGui.QPainterPath()
        path.addRect(rect)
        selected = index in self._selected
        if selected:
            fill = (
                self.color("secondary_container")
                if self.isEnabled() and segment.enabled
                else theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTAINER_OPACITY,
                )
            )
            painter.fillPath(path, fill)
        color = self._content_color(index)
        icon: icons.AnyIcon | None
        if selected and self._show_check_icon:
            icon = icons.Icon("check", ICON_SIZE)
        else:
            icon = icons.coerce(segment.icon, ICON_SIZE)
        content_width = typography.text_width(segment.text, LABEL_STYLE)
        if icon is not None:
            content_width += ICON_SIZE + (ICON_GAP if segment.text else 0)
        left = rect.center().x() - content_width / 2
        if icon is not None:
            icon_rect = QtCore.QRectF(
                left, rect.center().y() - ICON_SIZE / 2, ICON_SIZE, ICON_SIZE
            )
            icon.paint(painter, icon_rect, color)
            left += ICON_SIZE + (ICON_GAP if segment.text else 0)
        if segment.text:
            label_rect = QtCore.QRectF(
                left, rect.top(), rect.right() - left - 4, rect.height()
            )
            typography.paint_text(
                painter,
                label_rect,
                segment.text,
                LABEL_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        self._layers[index].paint(painter, path, color)
        self._ripples[index].paint(painter, path, color)

    # ---- 事件 -------------------------------------------------------------

    def _set_hovered(self, index: int) -> None:
        if index == self._hovered:
            return
        if 0 <= self._hovered < len(self._layers):
            self._layers[self._hovered].set_hovered(False)
        self._hovered = index
        if 0 <= index < len(self._layers) and self._segments[index].enabled:
            self._layers[index].set_hovered(True)

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
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        index = self._index_at(event.position())
        if (
            index < 0
            or not self._segments[index].enabled
            or not self.isEnabled()
        ):
            return
        self._pressed = index
        self._focused = index
        self._ripples[index].press(event.position(), self.segment_rect(index))
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
                self.toggle(pressed)
        event.accept()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        count = len(self._segments)
        if key in (QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Down) and count:
            self._move_focus(1)
        elif key in (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Up) and count:
            self._move_focus(-1)
        elif key in (
            QtCore.Qt.Key.Key_Space,
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
        ):
            if 0 <= self._focused < count:
                self._ripples[self._focused].press(
                    None, self.segment_rect(self._focused)
                )
                self._ripples[self._focused].release()
                self.toggle(self._focused)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _move_focus(self, delta: int) -> None:
        count = len(self._segments)
        if count == 0:
            return
        if 0 <= self._focused < count:
            self._layers[self._focused].set_focused(False)
        self._focused = (self._focused + delta) % count
        self._focus_visible = True
        self._layers[self._focused].set_focused(True)
        self._restart_focus_animation()
        self.update()

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusInEvent(event)
        self._focus_visible = event.reason() in (
            QtCore.Qt.FocusReason.TabFocusReason,
            QtCore.Qt.FocusReason.BacktabFocusReason,
            QtCore.Qt.FocusReason.ShortcutFocusReason,
        )
        if self._focus_visible and 0 <= self._focused < len(self._layers):
            self._layers[self._focused].set_focused(True)
            self._restart_focus_animation()
        self.update()

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(event)
        self._focus_visible = False
        for layer in self._layers:
            layer.set_focused(False)
        self.update()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            for layer in self._layers:
                layer.set_disabled(not self.isEnabled())
            self.update()
