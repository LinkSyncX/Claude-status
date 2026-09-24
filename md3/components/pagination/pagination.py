"""分页器（Pagination）。

``Pagination`` 由上一页 / 下一页图标按钮与一条页码带组成：页码以 40dp
的圆形项显示，当前页为 ``primary`` 填充圆；页数多时按"首页 … 当前页
前后 … 末页"的方式折叠，可选显示首页 / 末页按钮。页码带支持悬停状态层、
涟漪、方向键与 Home / End。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import icon_button
from md3.components.navigation import _items
from md3.core import accessibility
from md3.core import shape as shape_utils
from md3.core import typography
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ITEM_SIZE = 40.0
ITEM_GAP = 4.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
ELLIPSIS = -1


def page_window(page_count: int, current: int, max_buttons: int) -> list[int]:
    """计算要显示的页码序列，省略处以 ``ELLIPSIS``（-1）表示。

    首页与末页始终显示，当前页尽量居中；``max_buttons`` 为包含省略号在内的
    最大项数（至少 5）。
    """
    max_buttons = max(5, max_buttons)
    if page_count <= max_buttons:
        return list(range(page_count))
    inner = max_buttons - 2  # 去掉首页与末页
    half = (inner - 1) // 2
    start = max(1, current - half)
    end = min(page_count - 2, start + inner - 1)
    start = max(1, end - inner + 1)
    pages: list[int] = [0]
    if start > 1:
        pages.append(ELLIPSIS)
        start += 1
    if end < page_count - 2:
        end -= 1
    pages.extend(range(start, end + 1))
    if end < page_count - 2:
        pages.append(ELLIPSIS)
    pages.append(page_count - 1)
    return pages


class _PageStrip(_items.SelectableItems):
    """页码带：可点击的页码与不可交互的省略号。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent, horizontal_keys=True)
        self._pages: list[int] = [0]
        self._current = 0
        self._rebuild_states()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_pages(self, pages: list[int], current: int) -> None:
        """替换页码序列并标记当前页。"""
        self._pages = list(pages)
        self._current = current
        self._selected = self._index_of_page(current)
        self._rebuild_states()
        self._focused = max(0, self._selected)
        for index, value in enumerate(self._progress):
            value.set(1.0 if index == self._selected else 0.0)
        self.updateGeometry()
        self.update()

    def _index_of_page(self, page: int) -> int:
        for index, value in enumerate(self._pages):
            if value == page:
                return index
        return -1

    @override
    def item_count(self) -> int:
        return len(self._pages)

    @override
    def item_label(self, index: int) -> str:
        if 0 <= index < len(self._pages) and self._pages[index] != ELLIPSIS:
            return str(self._pages[index] + 1)
        return "…"

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        return self.visual_rect(
            QtCore.QRectF(
                index * (ITEM_SIZE + ITEM_GAP),
                (self.height() - ITEM_SIZE) / 2,
                ITEM_SIZE,
                ITEM_SIZE,
            )
        )

    @override
    def item_enabled(self, index: int) -> bool:
        return (
            self.isEnabled()
            and 0 <= index < len(self._pages)
            and self._pages[index] != ELLIPSIS
        )

    @override
    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        return shape_utils.rounded_rect_path(
            self.item_rect(index), shape_tokens.SHAPE_FULL
        )

    @override
    def item_state_color(self, index: int) -> QtGui.QColor:
        if index == self._selected:
            return self.color("on_primary")
        return self.color("on_surface")

    @override
    def sizeHint(self) -> QtCore.QSize:
        count = len(self._pages)
        width = count * ITEM_SIZE + max(0, count - 1) * ITEM_GAP
        return typography.size_hint(width, ITEM_SIZE + 8)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        for index, page in enumerate(self._pages):
            rect = self.item_rect(index)
            if page == ELLIPSIS:
                typography.paint_text(
                    painter,
                    rect,
                    "…",
                    LABEL_STYLE,
                    self.color("on_surface_variant"),
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
                continue
            progress = self.progress(index)
            if progress > 0.001:
                fill = self.color("primary")
                fill.setAlphaF(min(1.0, progress))
                shape_utils.fill_shape(
                    painter,
                    shape_utils.rounded_rect_path(
                        rect, shape_tokens.SHAPE_FULL
                    ),
                    fill,
                )
            if not self.isEnabled():
                color = QtGui.QColor(self.color("on_surface"))
                color.setAlphaF(state_tokens.DISABLED_CONTENT_OPACITY)
            elif index == self._selected:
                color = self.color("on_primary")
            else:
                color = self.color("on_surface")
            typography.paint_text(
                painter,
                rect,
                str(page + 1),
                LABEL_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
            self.paint_item_overlays(painter, index)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Home and self._pages:
            self.activate_item(0)
            event.accept()
            return
        if event.key() == QtCore.Qt.Key.Key_End and self._pages:
            self.activate_item(len(self._pages) - 1)
            event.accept()
            return
        super().keyPressEvent(event)


class Pagination(QtWidgets.QWidget):
    """分页器。

    Args:
        page_count: 总页数（≥ 1）。
        current_page: 当前页下标（从 0 开始）。
        max_buttons: 页码带最多显示的项数（含省略号）。
        show_first_last: 是否显示首页 / 末页按钮。
        show_numbers: 为假时只显示上一页 / 下一页（数据表页脚常用）。
        parent: 父控件。
    """

    page_changed = QtCore.Signal(int)

    def __init__(
        self,
        page_count: int = 1,
        current_page: int = 0,
        max_buttons: int = 7,
        show_first_last: bool = False,
        show_numbers: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._page_count = max(1, page_count)
        self._current = max(0, min(current_page, self._page_count - 1))
        self._max_buttons = max_buttons
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._first = icon_button.IconButton(
            "first_page", tooltip=i18n.tr("first_page")
        )
        self._first.clicked.connect(lambda: self.set_current_page(0))
        self._previous = icon_button.IconButton(
            "chevron_left", tooltip=i18n.tr("previous_page")
        )
        self._previous.clicked.connect(self.previous_page)
        self._strip = _PageStrip()
        self._strip.selection_changed.connect(self._on_strip_selected)
        self._next = icon_button.IconButton(
            "chevron_right", tooltip=i18n.tr("next_page")
        )
        self._next.clicked.connect(self.next_page)
        self._last = icon_button.IconButton(
            "last_page", tooltip=i18n.tr("last_page")
        )
        self._last.clicked.connect(
            lambda: self.set_current_page(self._page_count - 1)
        )
        for button in (self._first, self._previous):
            layout.addWidget(button)
        layout.addWidget(self._strip)
        for button in (self._next, self._last):
            layout.addWidget(button)
        self._first.setVisible(show_first_last)
        self._last.setVisible(show_first_last)
        self._strip.setVisible(show_numbers)
        self._refresh()

    # ---- 属性 -------------------------------------------------------------

    @property
    def page_count(self) -> int:
        """总页数。"""
        return self._page_count

    def set_page_count(self, page_count: int) -> None:
        """设置总页数（当前页超出时移到最后一页）。"""
        self._page_count = max(1, page_count)
        if self._current >= self._page_count:
            self.set_current_page(self._page_count - 1)
        else:
            self._refresh()

    @property
    def current_page(self) -> int:
        """当前页下标。"""
        return self._current

    def set_current_page(self, page: int) -> None:
        """跳到指定页，变化时发出 ``page_changed``。"""
        page = max(0, min(page, self._page_count - 1))
        if page == self._current:
            self._refresh()
            return
        self._current = page
        self._refresh()
        self.page_changed.emit(page)
        accessibility.notify_value_changed(self._strip, str(page + 1))

    def next_page(self) -> None:
        """下一页。"""
        self.set_current_page(self._current + 1)

    def previous_page(self) -> None:
        """上一页。"""
        self.set_current_page(self._current - 1)

    def set_show_first_last(self, show: bool) -> None:
        """设置是否显示首页 / 末页按钮。"""
        self._first.setVisible(show)
        self._last.setVisible(show)

    def set_show_numbers(self, show: bool) -> None:
        """设置是否显示页码带。"""
        self._strip.setVisible(show)

    @property
    def visible_pages(self) -> list[int]:
        """页码带当前显示的页码（省略号为 -1）。"""
        return page_window(self._page_count, self._current, self._max_buttons)

    @property
    def buttons(
        self,
    ) -> tuple[
        icon_button.IconButton,
        icon_button.IconButton,
        icon_button.IconButton,
        icon_button.IconButton,
    ]:
        """(首页, 上一页, 下一页, 末页) 按钮。"""
        return self._first, self._previous, self._next, self._last

    # ---- 内部 -------------------------------------------------------------

    def _refresh(self) -> None:
        self._strip.set_pages(self.visible_pages, self._current)
        at_start = self._current <= 0
        at_end = self._current >= self._page_count - 1
        self._first.setEnabled(not at_start)
        self._previous.setEnabled(not at_start)
        self._next.setEnabled(not at_end)
        self._last.setEnabled(not at_end)

    def _on_strip_selected(self, index: int) -> None:
        pages = self._strip._pages  # pylint: disable=protected-access
        if 0 <= index < len(pages) and pages[index] != ELLIPSIS:
            self.set_current_page(pages[index])
