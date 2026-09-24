"""导航轨（Navigation rail）：宽 80dp 的侧边导航，可展开为抽屉式列表。

M3 Expressive 把导航轨与抽屉合并：``expandable=True`` 时菜单按钮在折叠态
（80dp，图标上、标签下）与展开态（默认 220dp，图标左、标签右、指示器
为整行胶囊，徽标文字靠右）之间切换，宽度、指示器、图标位置与标签透明度
一起做动画。也可以直接调用 ``set_expanded``。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.badges import badge as badge_module
from md3.components.buttons import icon_button
from md3.components.navigation import _items
from md3.components.navigation import destination as destination_module
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

RAIL_WIDTH = 80.0
ITEM_HEIGHT = 56.0
ITEM_GAP = 12.0
TOP_PADDING = 44.0
HEADER_GAP = 8.0
MENU_BUTTON_HEIGHT = 48.0
# 展开态：默认宽度、整行胶囊指示器的水平内边距与内部间距。
EXPANDED_WIDTH = 220.0
EXPANDED_ITEM_PADDING = 12.0
EXPANDED_INNER_PADDING = 16.0
EXPANDED_ICON_GAP = 12.0
EXPANDED_LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE


class RailAlignment(enum.Enum):
    """目的地在导航轨中的垂直对齐。"""

    TOP = "top"
    CENTER = "center"
    BOTTOM = "bottom"


def _lerp(start: float, end: float, t: float) -> float:
    return start + (end - start) * t


def _lerp_rect(
    start: QtCore.QRectF, end: QtCore.QRectF, t: float
) -> QtCore.QRectF:
    return QtCore.QRectF(
        _lerp(start.left(), end.left(), t),
        _lerp(start.top(), end.top(), t),
        _lerp(start.width(), end.width(), t),
        _lerp(start.height(), end.height(), t),
    )


class NavigationRail(_items.SelectableItems):
    """导航轨。

    Args:
        destinations: 目的地列表。
        selected_index: 初始选中下标。
        show_labels: 折叠态是否显示标签（展开态总是显示）。
        alignment: 目的地对齐方式。
        menu_button: 是否在顶部显示菜单按钮。
        header: 放在顶部（菜单按钮下方）的控件，通常是 FAB。
        expandable: 为真时菜单按钮切换展开 / 折叠，图标随之变为
            ``menu_open``。
        expanded: 初始是否展开。
        expanded_width: 展开态宽度（规范 220–360dp）。
        parent: 父控件。
    """

    menu_clicked = QtCore.Signal()
    expanded_changed = QtCore.Signal(bool)

    def __init__(
        self,
        destinations: list[destination_module.Destination | str],
        selected_index: int = 0,
        show_labels: bool = True,
        alignment: RailAlignment = RailAlignment.TOP,
        menu_button: bool = False,
        header: QtWidgets.QWidget | None = None,
        expandable: bool = False,
        expanded: bool = False,
        expanded_width: float = EXPANDED_WIDTH,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, horizontal_keys=False)
        self._destinations = destination_module.coerce_destinations(
            destinations
        )
        self._show_labels = show_labels
        self._alignment = alignment
        self._expandable = expandable
        self._expanded = expanded
        self._expanded_width = max(RAIL_WIDTH, expanded_width)
        self._expand = animation.AnimatedFloat(
            self, 1.0 if expanded else 0.0, self._on_expand_changed
        )
        self._selected = (
            selected_index
            if 0 <= selected_index < len(self._destinations)
            else -1
        )
        self._menu_button: icon_button.IconButton | None = None
        if menu_button:
            self._menu_button = icon_button.IconButton(
                "menu_open" if expanded else "menu",
                tooltip=i18n.tr("menu"),
                parent=self,
            )
            self._menu_button.clicked.connect(self._on_menu_clicked)
        self._header = header
        if header is not None:
            header.setParent(self)
        self._rebuild_states()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

    @property
    def destinations(self) -> list[destination_module.Destination]:
        """目的地列表。"""
        return list(self._destinations)

    def set_destinations(
        self, destinations: list[destination_module.Destination | str]
    ) -> None:
        """替换目的地。"""
        self._destinations = destination_module.coerce_destinations(
            destinations
        )
        self._selected = min(self._selected, len(self._destinations) - 1)
        self._rebuild_states()
        self.update()

    def set_badge(self, index: int, badge: int | str | None) -> None:
        """设置某个目的地的徽标。"""
        if 0 <= index < len(self._destinations):
            self._destinations[index].badge = badge
            self.update()

    def set_header(self, header: QtWidgets.QWidget | None) -> None:
        """设置顶部控件（通常是 FAB）。"""
        if self._header is not None:
            self._header.setParent(None)
        self._header = header
        if header is not None:
            header.setParent(self)
            header.show()
        self._layout_children()
        self.update()

    @property
    def menu_button(self) -> icon_button.IconButton | None:
        """顶部菜单按钮。"""
        return self._menu_button

    # ---- 展开 -------------------------------------------------------------

    @property
    def expanded(self) -> bool:
        """是否处于展开态。"""
        return self._expanded

    @property
    def expand_progress(self) -> float:
        """展开过渡进度：0 折叠、1 展开。"""
        return self._expand.value

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        """展开或折叠导航轨。"""
        if expanded == self._expanded:
            return
        self._expanded = expanded
        if self._menu_button is not None and self._expandable:
            self._menu_button.set_icon("menu_open" if expanded else "menu")
        target = 1.0 if expanded else 0.0
        if animate:
            self._expand.animate_to(
                target, motion.MEDIUM4, motion.EMPHASIZED_DECELERATE
            )
        else:
            self._expand.set(target)
        self.expanded_changed.emit(expanded)

    def toggle_expanded(self) -> None:
        """切换展开 / 折叠。"""
        self.set_expanded(not self._expanded)

    def _on_menu_clicked(self) -> None:
        self.menu_clicked.emit()
        if self._expandable:
            self.toggle_expanded()

    def _on_expand_changed(self) -> None:
        self.updateGeometry()
        self._layout_children()
        self.update()

    def current_width(self) -> float:
        """当前宽度（随展开进度变化）。"""
        return _lerp(RAIL_WIDTH, self._expanded_width, self._expand.value)

    # ---- 几何 -------------------------------------------------------------

    def _collapsed_item_height(self) -> float:
        if self._show_labels:
            return ITEM_HEIGHT
        return destination_module.INDICATOR_HEIGHT + 24.0

    def _item_height(self) -> float:
        return _lerp(
            self._collapsed_item_height(), ITEM_HEIGHT, self._expand.value
        )

    def _items_top(self) -> float:
        top = 0.0
        if self._menu_button is not None:
            top += MENU_BUTTON_HEIGHT + HEADER_GAP
        if self._header is not None:
            top += self._header.sizeHint().height() + HEADER_GAP
        top = max(
            top,
            TOP_PADDING
            if (self._menu_button is None and self._header is None)
            else top,
        )
        return top

    def _items_total_height(self) -> float:
        count = len(self._destinations)
        if count == 0:
            return 0.0
        return count * self._item_height() + (count - 1) * ITEM_GAP

    def _items_origin(self) -> float:
        rect = QtCore.QRectF(self.rect())
        top = self._items_top()
        total = self._items_total_height()
        match self._alignment:
            case RailAlignment.TOP:
                return top + 8.0
            case RailAlignment.CENTER:
                return max(top, rect.center().y() - total / 2)
            case _:
                return max(top, rect.bottom() - 56.0 - total)

    @override
    def item_count(self) -> int:
        return len(self._destinations)

    @override
    def item_label(self, index: int) -> str:
        if 0 <= index < len(self._destinations):
            return self._destinations[index].label
        return ""

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        height = self._item_height()
        top = self._items_origin() + index * (height + ITEM_GAP)
        return QtCore.QRectF(0, top, self.width(), height)

    @override
    def item_enabled(self, index: int) -> bool:
        return self._destinations[index].enabled and self.isEnabled()

    def _collapsed_indicator(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        """折叠态指示器：56×32，位于图标 + 标签块的顶部，水平居中于 80dp。"""
        label_height = (
            self.theme.style(destination_module.LABEL_STYLE).line_height
            if self._show_labels
            else 0.0
        )
        block = destination_module.INDICATOR_HEIGHT + (
            destination_module.LABEL_GAP + label_height
            if self._show_labels
            else 0
        )
        return QtCore.QRectF(
            (RAIL_WIDTH - destination_module.RAIL_INDICATOR_WIDTH) / 2,
            rect.center().y() - block / 2,
            destination_module.RAIL_INDICATOR_WIDTH,
            destination_module.INDICATOR_HEIGHT,
        )

    def _expanded_indicator(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        """展开态指示器：整行胶囊。"""
        return rect.adjusted(
            EXPANDED_ITEM_PADDING, 0, -EXPANDED_ITEM_PADDING, 0
        )

    def _logical_indicator_rect(self, index: int) -> QtCore.QRectF:
        rect = self.item_rect(index)
        return _lerp_rect(
            self._collapsed_indicator(rect),
            self._expanded_indicator(rect),
            self._expand.value,
        )

    def indicator_rect(self, index: int) -> QtCore.QRectF:
        """第 index 项当前（可能处于过渡中）的指示器矩形（已按方向镜像）。"""
        return self.visual_rect(self._logical_indicator_rect(index))

    @override
    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        return shape_utils.rounded_rect_path(
            self.indicator_rect(index), shape_tokens.SHAPE_FULL
        )

    def _layout_children(self) -> None:
        y = 8.0
        if self._menu_button is not None:
            hint = self._menu_button.sizeHint()
            self._menu_button.setGeometry(
                self.visual_rect(
                    QtCore.QRectF(
                        (RAIL_WIDTH - hint.width()) / 2,
                        y,
                        hint.width(),
                        hint.height(),
                    )
                ).toRect()
            )
            y += MENU_BUTTON_HEIGHT + HEADER_GAP
        if self._header is not None:
            hint = self._header.sizeHint()
            self._header.setGeometry(
                self.visual_rect(
                    QtCore.QRectF(
                        (RAIL_WIDTH - hint.width()) / 2,
                        y,
                        hint.width(),
                        hint.height(),
                    )
                ).toRect()
            )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(round(self.current_width()), 480)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            round(self.current_width()),
            int(self._items_top() + self._items_total_height()),
        )

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        painter.fillRect(self.rect(), self.color("surface"))
        for index, destination in enumerate(self._destinations):
            if self._expand.value <= 0.001:
                destination_module.paint_destination(
                    painter,
                    self.item_rect(index),
                    destination,
                    index == self._selected,
                    self.progress(index),
                    self._show_labels,
                    indicator_width=destination_module.RAIL_INDICATOR_WIDTH,
                    enabled=self.isEnabled(),
                    theme=self.theme,
                    rtl=self.is_rtl(),
                )
            else:
                self._paint_transitional_item(painter, index, destination)
            self.paint_item_overlays(painter, index)

    def _paint_transitional_item(
        self,
        painter: QtGui.QPainter,
        index: int,
        destination: destination_module.Destination,
    ) -> None:
        """按展开进度在折叠与展开两种布局之间插值绘制目的地。"""
        t = self._expand.value
        rect = self.item_rect(index)
        selected = index == self._selected
        collapsed = self._collapsed_indicator(rect)
        indicator = self._logical_indicator_rect(index)
        progress = self.progress(index)
        if progress > 0.001:
            color = self.color("secondary_container")
            color.setAlphaF(min(1.0, progress * 1.5))
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    self.visual_rect(indicator), shape_tokens.SHAPE_FULL
                ),
                color,
            )
        if not self.item_enabled(index):
            icon_color = theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            label_color = icon_color
        elif selected:
            icon_color = self.color("on_secondary_container")
            label_color = self.color("on_surface")
        else:
            icon_color = self.color("on_surface_variant")
            label_color = self.color("on_surface_variant")
        icon_size = destination_module.ICON_SIZE
        collapsed_icon = QtCore.QPointF(
            collapsed.center().x(), collapsed.center().y()
        )
        expanded_icon = QtCore.QPointF(
            indicator.left() + EXPANDED_INNER_PADDING + icon_size / 2,
            rect.center().y(),
        )
        center = QtCore.QPointF(
            _lerp(collapsed_icon.x(), expanded_icon.x(), t),
            _lerp(collapsed_icon.y(), expanded_icon.y(), t),
        )
        icon_rect = self.visual_rect(
            QtCore.QRectF(
                center.x() - icon_size / 2,
                center.y() - icon_size / 2,
                icon_size,
                icon_size,
            )
        )
        icon = destination.current_icon(selected)
        if icon is not None:
            icon.paint(painter, icon_rect, icon_color)
        badge_text = destination.badge_text()
        label_height = self.theme.style(
            destination_module.LABEL_STYLE
        ).line_height
        # 折叠态元素淡出。
        if t < 0.999:
            painter.save()
            painter.setOpacity(1.0 - t)
            if badge_text is not None:
                badge_module.paint_badge(
                    painter, icon_rect, badge_text, self.theme, self.is_rtl()
                )
            if self._show_labels:
                typography.paint_text(
                    painter,
                    self.visual_rect(
                        QtCore.QRectF(
                            0.0,
                            collapsed.bottom() + destination_module.LABEL_GAP,
                            RAIL_WIDTH,
                            label_height,
                        )
                    ),
                    destination.label,
                    destination_module.LABEL_STYLE,
                    label_color,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
            painter.restore()
        # 展开态元素淡入：右侧标签与徽标文字。
        painter.save()
        painter.setOpacity(t)
        expanded_indicator = self._expanded_indicator(rect)
        left = (
            expanded_indicator.left()
            + EXPANDED_INNER_PADDING
            + icon_size
            + EXPANDED_ICON_GAP
        )
        right = expanded_indicator.right() - EXPANDED_INNER_PADDING
        if badge_text:
            width = typography.text_width(badge_text, EXPANDED_LABEL_STYLE)
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - width, rect.top(), width, rect.height()
                    )
                ),
                badge_text,
                EXPANDED_LABEL_STYLE,
                label_color,
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )
            right -= width + EXPANDED_ICON_GAP
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(
                    left, rect.top(), max(0.0, right - left), rect.height()
                )
            ),
            destination.label,
            EXPANDED_LABEL_STYLE,
            label_color,
            self.start_alignment(),
        )
        painter.restore()
