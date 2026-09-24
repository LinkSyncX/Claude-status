"""导航抽屉（Navigation drawer）：standard 与 modal。"""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.navigation import _items
from md3.core import overlay
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

DRAWER_WIDTH = 360
ITEM_HEIGHT = 56.0
ITEM_PADDING = 12.0
ICON_SIZE = 24.0
ICON_GAP = 12.0
INNER_PADDING = 16.0
HEADLINE_HEIGHT = 56.0
DIVIDER_HEIGHT = 17.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
HEADLINE_STYLE = typography_tokens.TypeRole.TITLE_SMALL
BADGE_STYLE = typography_tokens.TypeRole.LABEL_LARGE


@dataclasses.dataclass
class DrawerItem:
    """抽屉中的一项。

    Attributes:
        label: 标签。
        icon: 图标。
        badge: 右侧的徽标文字（例如未读数）。
        enabled: 是否可用。
        headline: 为真时表示分组标题而非可选项。
        divider: 为真时表示分隔线。
        key: 业务侧标识。
    """

    label: str = ""
    icon: icons.IconLike = None
    badge: str = ""
    enabled: bool = True
    headline: bool = False
    divider: bool = False
    key: Any = None

    @classmethod
    def section(cls, label: str) -> DrawerItem:
        """创建分组标题。"""
        return cls(label=label, headline=True)

    @classmethod
    def separator(cls) -> DrawerItem:
        """创建分隔线。"""
        return cls(divider=True)

    @property
    def selectable(self) -> bool:
        """是否为可选项。"""
        return not (self.headline or self.divider)


class DrawerContent(_items.SelectableItems):
    """抽屉的项列表（可独立嵌入任意容器）。"""

    def __init__(
        self,
        items: list[DrawerItem | str],
        selected_index: int = 0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, horizontal_keys=False)
        self._drawer_items = [
            DrawerItem(label=item) if isinstance(item, str) else item
            for item in items
        ]
        self._selected = (
            selected_index if self._is_valid(selected_index) else -1
        )
        self._rebuild_states()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

    def _is_valid(self, index: int) -> bool:
        return (
            0 <= index < len(self._drawer_items)
            and self._drawer_items[index].selectable
        )

    @property
    def items(self) -> list[DrawerItem]:
        """全部项。"""
        return list(self._drawer_items)

    def set_items(self, items: list[DrawerItem | str]) -> None:
        """替换全部项。"""
        self._drawer_items = [
            DrawerItem(label=item) if isinstance(item, str) else item
            for item in items
        ]
        if not self._is_valid(self._selected):
            self._selected = -1
        self._rebuild_states()
        self.updateGeometry()
        self.update()

    @property
    def selected_item(self) -> DrawerItem | None:
        """当前选中的项。"""
        if self._is_valid(self._selected):
            return self._drawer_items[self._selected]
        return None

    @override
    def item_count(self) -> int:
        return len(self._drawer_items)

    @override
    def item_label(self, index: int) -> str:
        if self._is_valid(index):
            return self._drawer_items[index].label
        return ""

    def _item_height(self, item: DrawerItem) -> float:
        if item.divider:
            return DIVIDER_HEIGHT
        if item.headline:
            return HEADLINE_HEIGHT
        return ITEM_HEIGHT

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        y = 12.0
        for current, item in enumerate(self._drawer_items):
            height = self._item_height(item)
            if current == index:
                return QtCore.QRectF(
                    ITEM_PADDING, y, self.width() - 2 * ITEM_PADDING, height
                )
            y += height
        return QtCore.QRectF()

    @override
    def item_enabled(self, index: int) -> bool:
        item = self._drawer_items[index]
        return item.selectable and item.enabled and self.isEnabled()

    @override
    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        return shape_utils.rounded_rect_path(
            self.item_rect(index), shape_tokens.SHAPE_FULL
        )

    @override
    def activate_item(self, index: int) -> None:
        if self._is_valid(index) and self.item_enabled(index):
            self.set_selected_index(index)

    def total_height(self) -> float:
        """全部项的总高度。"""
        return 24.0 + sum(
            self._item_height(item) for item in self._drawer_items
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(DRAWER_WIDTH, int(self.total_height()))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(200, int(self.total_height()))

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        for index, item in enumerate(self._drawer_items):
            rect = self.item_rect(index)
            if item.divider:
                painter.fillRect(
                    QtCore.QRectF(
                        rect.left() + INNER_PADDING,
                        rect.center().y(),
                        rect.width() - 2 * INNER_PADDING,
                        1,
                    ),
                    self.color("outline_variant"),
                )
                continue
            if item.headline:
                typography.paint_text(
                    painter,
                    rect.adjusted(INNER_PADDING, 0, -INNER_PADDING, 0),
                    item.label,
                    HEADLINE_STYLE,
                    self.color("on_surface_variant"),
                    self.start_alignment(),
                )
                continue
            self._paint_item(painter, index, item, rect)

    def _paint_item(
        self,
        painter: QtGui.QPainter,
        index: int,
        item: DrawerItem,
        rect: QtCore.QRectF,
    ) -> None:
        selected = index == self._selected
        progress = self.progress(index)
        if progress > 0.001:
            color = self.color("secondary_container")
            color.setAlphaF(min(1.0, progress))
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL),
                color,
            )
        if not self.item_enabled(index):
            icon_color = theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            label_color = icon_color
        elif selected:
            icon_color = self.color("on_secondary_container")
            label_color = icon_color
        else:
            icon_color = self.color("on_surface_variant")
            label_color = self.color("on_surface_variant")
        left = rect.left() + INNER_PADDING
        icon = icons.coerce(item.icon, ICON_SIZE)
        if icon is not None:
            if selected:
                icon = icon.with_fill(True)
            icon.paint(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        left,
                        rect.center().y() - ICON_SIZE / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    )
                ),
                icon_color,
            )
            left += ICON_SIZE + ICON_GAP
        right = rect.right() - INNER_PADDING
        if item.badge:
            width = typography.text_width(item.badge, BADGE_STYLE)
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - width, rect.top(), width, rect.height()
                    )
                ),
                item.badge,
                BADGE_STYLE,
                label_color,
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )
            right -= width + ICON_GAP
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(
                    left, rect.top(), max(0.0, right - left), rect.height()
                )
            ),
            item.label,
            LABEL_STYLE,
            label_color,
            self.start_alignment(),
        )
        self.paint_item_overlays(painter, index)


class NavigationDrawer(QtWidgets.QWidget):
    """标准（常驻）导航抽屉：宽 360dp，可嵌入布局左侧。

    Args:
        items: 抽屉项。
        selected_index: 初始选中下标。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(int)

    def __init__(
        self,
        items: list[DrawerItem | str],
        selected_index: int = 0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedWidth(DRAWER_WIDTH)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._content = DrawerContent(items, selected_index)
        self._content.selection_changed.connect(self.selection_changed)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    @property
    def content(self) -> DrawerContent:
        """项列表控件。"""
        return self._content

    @property
    def selected_index(self) -> int:
        """当前选中下标。"""
        return self._content.selected_index

    def set_selected_index(self, index: int) -> None:
        """设置选中项。"""
        self._content.set_selected_index(index)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), theme_module.current().color("surface"))
        painter.end()


class ModalNavigationDrawer(overlay.FloatingPanel):
    """模态导航抽屉：从窗口左侧滑入，带遮罩。

    Args:
        host: 宿主窗口。
        items: 抽屉项。
        selected_index: 初始选中下标。
    """

    selection_changed = QtCore.Signal(int)

    def __init__(
        self,
        host: QtWidgets.QWidget,
        items: list[DrawerItem | str],
        selected_index: int = 0,
    ) -> None:
        super().__init__(host, modal=True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._content = DrawerContent(items, selected_index)
        self._content.selection_changed.connect(self._on_selected)
        self._scroll.setWidget(self._content)
        layout.addWidget(self._scroll)

    @property
    def content(self) -> DrawerContent:
        """项列表控件。"""
        return self._content

    def _on_selected(self, index: int) -> None:
        self.selection_changed.emit(index)
        self.close_panel()

    def _rtl(self) -> bool:
        return (
            self.host.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft
        )

    @override
    def open_geometry(self) -> QtCore.QRect:
        host = self.host.rect()
        width = min(DRAWER_WIDTH, host.width() - 56)
        x = host.width() - width if self._rtl() else 0
        return QtCore.QRect(x, 0, width, host.height())

    @override
    def closed_geometry(self) -> QtCore.QRect:
        rect = self.open_geometry()
        # 从布局起始侧滑入：LTR 从左边，RTL 从右边。
        return rect.translated(
            rect.width() if self._rtl() else -rect.width(), 0
        )

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if self._rtl():
            rect = QtCore.QRectF(self.rect()).adjusted(
                0, 0, shape_tokens.LARGE, 0
            )
            shape = shape_tokens.Shape.start(shape_tokens.LARGE)
        else:
            rect = QtCore.QRectF(self.rect()).adjusted(
                -shape_tokens.LARGE, 0, 0, 0
            )
            shape = shape_tokens.Shape.end(shape_tokens.LARGE)
        path = shape_utils.rounded_rect_path(rect, shape)
        shape_utils.fill_shape(
            painter, path, theme.color("surface_container_low")
        )
        painter.end()
