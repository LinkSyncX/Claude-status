"""标签页（Tabs）：primary 与 secondary，带动画指示条。

``scrollable=True`` 时标签按内容宽度排列并以 52dp 的起始内边距开始；
超出可视范围的部分可以用滚轮、拖拽或两侧的箭头按钮滚动，选中或键盘
聚焦的标签会自动滚入视野。
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.badges import badge as badge_module
from md3.components.buttons import icon_button
from md3.components.navigation import _items
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

TAB_HEIGHT = 48.0
TAB_HEIGHT_WITH_ICON = 64.0
MIN_TAB_WIDTH = 90.0
TAB_PADDING = 16.0
ICON_SIZE = 24.0
PRIMARY_INDICATOR_HEIGHT = 3.0
SECONDARY_INDICATOR_HEIGHT = 2.0
LABEL_STYLE = typography_tokens.TypeRole.TITLE_SMALL
# 可滚动标签页的起始内边距（规范：标签自前缘偏移 52dp）。
SCROLLABLE_START_PADDING = 52.0
# 两侧滚动箭头按钮的宽度；拖拽超过阈值才视为滚动而非点击。
ARROW_WIDTH = 48.0
DRAG_THRESHOLD = 8.0
WHEEL_STEP = 96.0


class TabsVariant(enum.Enum):
    """标签页变体。"""

    PRIMARY = "primary"
    SECONDARY = "secondary"


@dataclasses.dataclass
class Tab:
    """单个标签。

    Attributes:
        label: 文字。
        icon: 图标（primary 标签可在文字上方显示图标）。
        badge: 徽标数字或文字。
        enabled: 是否可用。
        key: 业务侧标识。
    """

    label: str
    icon: icons.IconLike = None
    badge: int | str | None = None
    enabled: bool = True
    key: Any = None


class Tabs(_items.SelectableItems):
    """标签页。

    Args:
        tabs: 标签列表。
        selected_index: 初始选中下标。
        variant: primary（指示条与内容同宽）或 secondary（指示条与标签同宽）。
        scrollable: 为真时标签按内容宽度排列，超出可视范围时可滚动，
            否则等分宽度。
        show_arrows: 可滚动且内容溢出时是否在两侧显示滚动箭头。
        parent: 父控件。
    """

    scroll_changed = QtCore.Signal(float)

    def __init__(
        self,
        tabs: list[Tab | str],
        selected_index: int = 0,
        variant: TabsVariant = TabsVariant.PRIMARY,
        scrollable: bool = False,
        show_arrows: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, horizontal_keys=True)
        self._tabs = [
            Tab(label=tab) if isinstance(tab, str) else tab for tab in tabs
        ]
        self._variant = variant
        self._scrollable = scrollable
        self._show_arrows = show_arrows
        self._selected = (
            selected_index if 0 <= selected_index < len(self._tabs) else -1
        )
        # 指示条位置以内容坐标记录，绘制时再减去滚动偏移。
        self._indicator_x = animation.AnimatedFloat(self, 0.0, self.update)
        self._indicator_w = animation.AnimatedFloat(self, 0.0, self.update)
        self._indicator_ready = False
        self._scroll = animation.AnimatedFloat(self, 0.0, self._on_scrolled)
        self._drag_start: QtCore.QPointF | None = None
        self._drag_origin = 0.0
        self._dragging = False
        self._left_arrow: icon_button.IconButton | None = None
        self._right_arrow: icon_button.IconButton | None = None
        if scrollable and show_arrows:
            self._left_arrow = icon_button.IconButton(
                "chevron_left", tooltip=i18n.tr("scroll_left"), parent=self
            )
            # 箭头按视觉方向滚动：RTL 下向左即朝内容末尾。
            self._left_arrow.clicked.connect(
                lambda: self.scroll_by(1 if self.is_rtl() else -1)
            )
            self._right_arrow = icon_button.IconButton(
                "chevron_right", tooltip=i18n.tr("scroll_right"), parent=self
            )
            self._right_arrow.clicked.connect(
                lambda: self.scroll_by(-1 if self.is_rtl() else 1)
            )
            for arrow in (self._left_arrow, self._right_arrow):
                arrow.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
                arrow.hide()
        self._rebuild_states()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def tabs(self) -> list[Tab]:
        """标签列表。"""
        return list(self._tabs)

    def set_tabs(self, tabs: list[Tab | str]) -> None:
        """替换标签。"""
        self._tabs = [
            Tab(label=tab) if isinstance(tab, str) else tab for tab in tabs
        ]
        self._selected = min(self._selected, len(self._tabs) - 1)
        self._indicator_ready = False
        self._rebuild_states()
        self._scroll.set(min(self._scroll.value, self.max_scroll()))
        self._update_arrows()
        self.updateGeometry()
        self.update()

    @property
    def variant(self) -> TabsVariant:
        """变体。"""
        return self._variant

    @property
    def scrollable(self) -> bool:
        """是否为可滚动标签页。"""
        return self._scrollable

    def _has_icons(self) -> bool:
        return self._variant is TabsVariant.PRIMARY and any(
            tab.icon is not None for tab in self._tabs
        )

    def _height(self) -> float:
        return TAB_HEIGHT_WITH_ICON if self._has_icons() else TAB_HEIGHT

    def _natural_width(self, tab: Tab) -> float:
        width = typography.text_width(tab.label, LABEL_STYLE) + 2 * TAB_PADDING
        if self._variant is TabsVariant.SECONDARY and tab.icon is not None:
            width += ICON_SIZE + 8
        return max(MIN_TAB_WIDTH, width)

    # ---- 滚动 -------------------------------------------------------------

    def _arrows_visible(self) -> bool:
        return (
            self._scrollable
            and self._left_arrow is not None
            and self.content_width() > self.width()
        )

    def strip_rect(self) -> QtCore.QRectF:
        """标签条可视区域（箭头显示时扣除两侧箭头）。"""
        rect = QtCore.QRectF(self.rect())
        if self._arrows_visible():
            return rect.adjusted(ARROW_WIDTH, 0, -ARROW_WIDTH, 0)
        return rect

    def content_width(self) -> float:
        """全部标签占用的内容宽度（可滚动模式含起始内边距）。"""
        if not self._scrollable:
            return float(self.width())
        return SCROLLABLE_START_PADDING + sum(
            self._natural_width(tab) for tab in self._tabs
        )

    def max_scroll(self) -> float:
        """最大滚动偏移。"""
        if not self._scrollable:
            return 0.0
        return max(0.0, self.content_width() - self.strip_rect().width())

    @property
    def scroll_offset(self) -> float:
        """当前滚动偏移。"""
        return self._scroll.value

    def set_scroll_offset(self, offset: float, animate: bool = False) -> None:
        """设置滚动偏移（自动限制范围）。"""
        offset = max(0.0, min(self.max_scroll(), offset))
        if animate:
            self._scroll.animate_to(
                offset, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
            )
        else:
            self._scroll.set(offset)

    def scroll_by(self, direction: int) -> None:
        """按箭头方向滚动约一个可视区宽度。"""
        step = max(WHEEL_STEP, self.strip_rect().width() - MIN_TAB_WIDTH)
        self.set_scroll_offset(
            self._scroll.target + direction * step, animate=True
        )

    def scroll_to_tab(self, index: int, animate: bool = True) -> None:
        """滚动到第 index 个标签完全可见。"""
        if not self._scrollable or not 0 <= index < len(self._tabs):
            return
        rect = self._content_rect(index)
        strip = self.strip_rect()
        target = self._scroll.target
        if rect.left() - target < 0:
            target = rect.left()
        elif rect.right() - target > strip.width():
            target = rect.right() - strip.width()
        self.set_scroll_offset(target, animate)

    def _on_scrolled(self) -> None:
        self._update_arrows()
        self.update()
        self.scroll_changed.emit(self._scroll.value)

    def _update_arrows(self) -> None:
        if self._left_arrow is None or self._right_arrow is None:
            return
        visible = self._arrows_visible()
        y = round((self.height() - ARROW_WIDTH) / 2)
        self._left_arrow.setGeometry(0, y, int(ARROW_WIDTH), int(ARROW_WIDTH))
        self._right_arrow.setGeometry(
            round(self.width() - ARROW_WIDTH),
            y,
            int(ARROW_WIDTH),
            int(ARROW_WIDTH),
        )
        self._left_arrow.setVisible(visible)
        self._right_arrow.setVisible(visible)
        if visible:
            can_go_back = self._scroll.value > 0.5
            can_go_forward = self._scroll.value < self.max_scroll() - 0.5
            if self.is_rtl():
                can_go_back, can_go_forward = can_go_forward, can_go_back
            self._left_arrow.setEnabled(can_go_back)
            self._right_arrow.setEnabled(can_go_forward)

    # ---- 项接口 -----------------------------------------------------------

    @override
    def item_count(self) -> int:
        return len(self._tabs)

    @override
    def item_label(self, index: int) -> str:
        if 0 <= index < len(self._tabs):
            return self._tabs[index].label
        return ""

    def _content_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个标签在内容坐标中的矩形（未计滚动与箭头内缩）。"""
        if not self._tabs or not 0 <= index < len(self._tabs):
            return QtCore.QRectF()
        height = float(self.height())
        if self._scrollable:
            x = SCROLLABLE_START_PADDING
            for current, tab in enumerate(self._tabs):
                width = self._natural_width(tab)
                if current == index:
                    return QtCore.QRectF(x, 0.0, width, height)
                x += width
            return QtCore.QRectF()
        width = self.width() / len(self._tabs)
        return QtCore.QRectF(index * width, 0.0, width, height)

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        rect = self._content_rect(index)
        if rect.isNull():
            return rect
        return self.visual_rect(
            rect.translated(self.strip_rect().left() - self._scroll.value, 0.0)
        )

    @override
    def item_enabled(self, index: int) -> bool:
        return self._tabs[index].enabled and self.isEnabled()

    @override
    def item_state_color(self, index: int) -> QtGui.QColor:
        if index == self._selected:
            return self.color("primary")
        return self.color("on_surface")

    @override
    def focus_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_EXTRA_SMALL

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = sum(self._natural_width(tab) for tab in self._tabs)
        if self._scrollable:
            width += SCROLLABLE_START_PADDING
        return typography.size_hint(max(width, 200.0), self._height())

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        if self._scrollable:
            arrows = 2 * ARROW_WIDTH if self._left_arrow is not None else 0.0
            return typography.size_hint(MIN_TAB_WIDTH + arrows, self._height())
        return typography.size_hint(
            MIN_TAB_WIDTH * len(self._tabs), self._height()
        )

    # ---- 指示条 -----------------------------------------------------------

    def _indicator_target(self) -> tuple[float, float]:
        if self._selected < 0:
            return 0.0, 0.0
        rect = self._content_rect(self._selected)
        tab = self._tabs[self._selected]
        if self._variant is TabsVariant.PRIMARY:
            width = typography.text_width(tab.label, LABEL_STYLE)
            if tab.icon is not None and not tab.label:
                width = ICON_SIZE
            width = max(width, 24.0)
            return rect.center().x() - width / 2, width
        return rect.left(), rect.width()

    def _sync_indicator(self, animate: bool) -> None:
        x, width = self._indicator_target()
        if animate and self._indicator_ready:
            self._indicator_x.animate_to(
                x, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
            )
            self._indicator_w.animate_to(
                width, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
            )
        else:
            self._indicator_x.set(x)
            self._indicator_w.set(width)
        self._indicator_ready = True

    @override
    def set_selected_index(self, index: int, animate: bool = True) -> None:
        super().set_selected_index(index, animate)
        self._sync_indicator(animate)
        self.scroll_to_tab(index, animate)

    @override
    def _set_focused(self, index: int) -> None:
        super()._set_focused(index)
        if self._focus_visible:
            self.scroll_to_tab(index)

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._scroll.set(min(self._scroll.value, self.max_scroll()))
        self._update_arrows()
        self._sync_indicator(animate=False)

    # ---- 事件 -------------------------------------------------------------

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self.max_scroll() <= 0:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().x() or event.angleDelta().y()
        if delta:
            step = -delta / 120.0 * WHEEL_STEP
        else:
            pixel = event.pixelDelta()
            step = -float(pixel.x() or pixel.y())
        self.set_scroll_offset(self._scroll.target + step, animate=True)
        event.accept()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.max_scroll() > 0
        ):
            self._drag_start = event.position()
            self._drag_origin = self._scroll.value
            self._dragging = False
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_start is not None:
            dx = event.position().x() - self._drag_start.x()
            if not self._dragging and abs(dx) > DRAG_THRESHOLD:
                self._dragging = True
                if self._pressed >= 0:
                    self._ripples[self._pressed].cancel()
                    self._pressed = -1
            if self._dragging:
                # RTL 下内容起点在右侧，拖动方向与偏移的关系相反。
                delta = -dx if self.is_rtl() else dx
                self.set_scroll_offset(self._drag_origin - delta)
                event.accept()
                return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        was_dragging = self._dragging
        self._drag_start = None
        self._dragging = False
        if was_dragging:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        painter.fillRect(rect, self.color("surface"))
        painter.fillRect(
            QtCore.QRectF(rect.left(), rect.bottom() - 1, rect.width(), 1),
            self.color("surface_variant"),
        )
        if not self._indicator_ready:
            self._sync_indicator(animate=False)
        strip = self.strip_rect()
        painter.save()
        painter.setClipRect(strip)
        for index, tab in enumerate(self._tabs):
            item = self.item_rect(index)
            if item.right() < strip.left() or item.left() > strip.right():
                continue
            self._paint_tab(painter, index, tab)
        if self._selected >= 0:
            self._paint_indicator(painter, rect)
        painter.restore()

    def _paint_tab(self, painter: QtGui.QPainter, index: int, tab: Tab) -> None:
        rect = self.item_rect(index)
        selected = index == self._selected
        if not self.item_enabled(index):
            color = theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        elif selected:
            color = self.color(
                "primary"
                if self._variant is TabsVariant.PRIMARY
                else "on_surface"
            )
        else:
            color = self.color("on_surface_variant")
        icon = icons.coerce(tab.icon, ICON_SIZE)
        if self._variant is TabsVariant.PRIMARY and self._has_icons():
            icon_rect = QtCore.QRectF(
                rect.center().x() - ICON_SIZE / 2,
                rect.top() + 12,
                ICON_SIZE,
                ICON_SIZE,
            )
            if icon is not None:
                icon.paint(painter, icon_rect, color)
            label_rect = QtCore.QRectF(
                rect.left(), rect.top() + 38, rect.width(), 20
            )
            typography.paint_text(
                painter,
                label_rect,
                tab.label,
                LABEL_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        else:
            content_width = typography.text_width(tab.label, LABEL_STYLE)
            if icon is not None:
                content_width += ICON_SIZE + 8
            left = rect.center().x() - content_width / 2
            if icon is not None:
                icon_rect = QtCore.QRectF(
                    left,
                    rect.center().y() - ICON_SIZE / 2,
                    ICON_SIZE,
                    ICON_SIZE,
                )
                icon.paint(painter, icon_rect, color)
                left += ICON_SIZE + 8
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    left, rect.top(), rect.right() - left, rect.height()
                ),
                tab.label,
                LABEL_STYLE,
                color,
            )
        if tab.badge is not None:
            text = (
                badge_module.badge_text(tab.badge)
                if isinstance(tab.badge, int)
                else tab.badge
            )
            anchor = QtCore.QRectF(
                rect.center().x()
                + content_anchor_offset(rect, tab, self._has_icons()),
                rect.top() + 12,
                ICON_SIZE,
                ICON_SIZE,
            )
            badge_module.paint_badge(
                painter, anchor, text, self.theme, self.is_rtl()
            )
        self.paint_item_overlays(painter, index)

    def _paint_indicator(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        height = (
            PRIMARY_INDICATOR_HEIGHT
            if self._variant is TabsVariant.PRIMARY
            else SECONDARY_INDICATOR_HEIGHT
        )
        indicator = self.visual_rect(
            QtCore.QRectF(
                self._indicator_x.value
                + self.strip_rect().left()
                - self._scroll.value,
                rect.bottom() - height,
                self._indicator_w.value,
                height,
            )
        )
        if self._variant is TabsVariant.PRIMARY:
            shape = shape_tokens.Shape(height, height, 0, 0)
        else:
            shape = shape_tokens.SHAPE_NONE
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(indicator, shape),
            self.color("primary"),
        )


def content_anchor_offset(
    rect: QtCore.QRectF, tab: Tab, icon_row: bool
) -> float:
    """徽标锚点相对标签中心的水平偏移。"""
    del rect
    if icon_row:
        return -ICON_SIZE / 2
    width = typography.text_width(tab.label, LABEL_STYLE)
    return width / 2 - 8
