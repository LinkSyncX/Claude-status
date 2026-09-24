"""面包屑（Breadcrumb）。

以 ``chevron_right`` 分隔的一串路径项：前面的项可点击（悬停状态层与涟漪），
最后一项为当前位置。项数超过 ``max_items`` 时中间的项折叠为 "…"，点击
弹出包含被折叠项的菜单。RTL 下分隔箭头与排列方向自动镜像。
"""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.menus import menu as menu_module
from md3.components.navigation import _items
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ITEM_HEIGHT = 32.0
ITEM_PADDING = 8.0
ICON_SIZE = 18.0
ICON_GAP = 4.0
SEPARATOR_SIZE = 18.0
SEPARATOR_GAP = 4.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
COLLAPSED = -1


@dataclasses.dataclass
class BreadcrumbItem:
    """一个路径项。

    Attributes:
        text: 文字。
        icon: 前置图标。
        key: 业务侧标识。
    """

    text: str
    icon: icons.IconLike = None
    key: Any = None


class Breadcrumb(_items.SelectableItems):
    """面包屑。

    Args:
        items: 路径项（字符串会转换为只有文字的项）。
        max_items: 最多显示的项数（含首尾），超过时折叠中间项。
        parent: 父控件。
    """

    item_clicked = QtCore.Signal(int)

    def __init__(
        self,
        items: list[BreadcrumbItem | str] | None = None,
        max_items: int = 4,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, horizontal_keys=True)
        self._items: list[BreadcrumbItem] = []
        self._max_items = max(3, max_items)
        self._menu: menu_module.Menu | None = None
        self.set_items(items or [])
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 项 ---------------------------------------------------------------

    @property
    def items(self) -> list[BreadcrumbItem]:
        """全部路径项。"""
        return list(self._items)

    def set_items(self, items: list[BreadcrumbItem | str]) -> None:
        """替换路径项。"""
        self._items = [
            BreadcrumbItem(text=item) if isinstance(item, str) else item
            for item in items
        ]
        self._selected = -1
        self._rebuild_states()
        self.updateGeometry()
        self.update()

    def push(self, item: BreadcrumbItem | str) -> None:
        """追加一项（进入下一级）。"""
        self.set_items([*self._items, item])

    def pop(self) -> BreadcrumbItem | None:
        """移除并返回最后一项（返回上一级）。"""
        if not self._items:
            return None
        last = self._items[-1]
        self.set_items(self._items[:-1])
        return last

    def visible_indices(self) -> list[int]:
        """实际显示的项下标序列，折叠处以 ``COLLAPSED``（-1）表示。"""
        count = len(self._items)
        if count <= self._max_items:
            return list(range(count))
        tail = self._max_items - 2
        return [0, COLLAPSED, *range(count - tail, count)]

    def collapsed_indices(self) -> list[int]:
        """被折叠进 "…" 的项下标。"""
        count = len(self._items)
        if count <= self._max_items:
            return []
        return list(range(1, count - (self._max_items - 2)))

    # ---- 项接口 -----------------------------------------------------------

    @override
    def item_count(self) -> int:
        return len(self.visible_indices())

    @override
    def item_label(self, index: int) -> str:
        visible = self.visible_indices()
        if 0 <= index < len(visible):
            source = visible[index]
            return "…" if source == COLLAPSED else self._items[source].text
        return ""

    def _item_width(self, position: int) -> float:
        source = self.visible_indices()[position]
        if source == COLLAPSED:
            return ITEM_HEIGHT
        item = self._items[source]
        width = 2 * ITEM_PADDING + typography.text_width(item.text, LABEL_STYLE)
        if item.icon is not None:
            width += ICON_SIZE + ICON_GAP
        return width

    def _logical_item_rect(self, position: int) -> QtCore.QRectF:
        x = 0.0
        for current in range(position):
            x += self._item_width(current) + 2 * SEPARATOR_GAP + SEPARATOR_SIZE
        return QtCore.QRectF(
            x,
            (self.height() - ITEM_HEIGHT) / 2,
            self._item_width(position),
            ITEM_HEIGHT,
        )

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        if not 0 <= index < self.item_count():
            return QtCore.QRectF()
        return self.visual_rect(self._logical_item_rect(index))

    def _is_current(self, position: int) -> bool:
        return position == self.item_count() - 1

    @override
    def item_enabled(self, index: int) -> bool:
        return self.isEnabled() and not self._is_current(index)

    @override
    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        return shape_utils.rounded_rect_path(
            self.item_rect(index), shape_tokens.SHAPE_SMALL
        )

    @override
    def focus_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_SMALL

    @override
    def activate_item(self, index: int) -> None:
        visible = self.visible_indices()
        if not 0 <= index < len(visible) or self._is_current(index):
            return
        source = visible[index]
        if source == COLLAPSED:
            self._open_collapsed_menu(index)
            return
        self.item_clicked.emit(source)

    def _open_collapsed_menu(self, position: int) -> None:
        if self._menu is None:
            self._menu = menu_module.Menu(parent=self)
            self._menu.triggered.connect(
                lambda item: self.item_clicked.emit(int(item.key))
            )
        self._menu.set_items(
            [
                menu_module.MenuItem(
                    text=self._items[source].text,
                    icon=self._items[source].icon,
                    key=source,
                )
                for source in self.collapsed_indices()
            ]
        )
        rect = self.item_rect(position)
        self._menu.popup(
            self.mapToGlobal(
                QtCore.QPoint(round(rect.left()), round(rect.bottom()) + 4)
            )
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        count = self.item_count()
        width = sum(self._item_width(i) for i in range(count))
        width += max(0, count - 1) * (2 * SEPARATOR_GAP + SEPARATOR_SIZE)
        return typography.size_hint(max(width, 24.0), ITEM_HEIGHT + 8)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        visible = self.visible_indices()
        separator = icons.coerce(
            "chevron_left" if self.is_rtl() else "chevron_right", SEPARATOR_SIZE
        )
        for position, source in enumerate(visible):
            rect = self.item_rect(position)
            current = self._is_current(position)
            if not self.isEnabled():
                color = theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTENT_OPACITY,
                )
            else:
                color = self.color(
                    "on_surface" if current else "on_surface_variant"
                )
            if source == COLLAPSED:
                typography.paint_text(
                    painter,
                    rect,
                    "…",
                    LABEL_STYLE,
                    color,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
            else:
                item = self._items[source]
                logical = self._logical_item_rect(position)
                left = logical.left() + ITEM_PADDING
                icon = icons.coerce(item.icon, ICON_SIZE)
                if icon is not None:
                    icon.paint(
                        painter,
                        self.visual_rect(
                            QtCore.QRectF(
                                left,
                                logical.center().y() - ICON_SIZE / 2,
                                ICON_SIZE,
                                ICON_SIZE,
                            )
                        ),
                        color,
                    )
                    left += ICON_SIZE + ICON_GAP
                typography.paint_text(
                    painter,
                    self.visual_rect(
                        QtCore.QRectF(
                            left,
                            logical.top(),
                            logical.right() - ITEM_PADDING - left,
                            logical.height(),
                        )
                    ),
                    item.text,
                    LABEL_STYLE,
                    color,
                    self.start_alignment(),
                )
            if not current:
                self.paint_item_overlays(painter, position)
            if position < len(visible) - 1 and separator is not None:
                logical = self._logical_item_rect(position)
                separator.paint(
                    painter,
                    self.visual_rect(
                        QtCore.QRectF(
                            logical.right() + SEPARATOR_GAP,
                            logical.center().y() - SEPARATOR_SIZE / 2,
                            SEPARATOR_SIZE,
                            SEPARATOR_SIZE,
                        )
                    ),
                    self.color("on_surface_variant"),
                )
