"""数据表（Data table）。

``DataTable`` 把 M3 数据表规范中的整套行为组装在一个控件里：

- 列由 ``Column`` 描述（键、标题、对齐、宽度、是否可排序、格式化函数）；
  行是字典或序列，``set_rows`` 一次替换。
- 可选的复选列：表头复选框全选 / 取消当前页，``checked_rows`` 返回被选
  中的原始行下标，``selection_changed`` 随之发出。
- 点击表头排序（Material 排序箭头），``set_filter`` 按显示文字过滤。
- 页脚：每页行数选择、"1–10 / 共 100 项"与分页器；``set_dense`` 切换
  52dp / 40dp 密度；没有数据时在表体居中显示空状态文字。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Mapping
from collections.abc import Sequence
import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import common as buttons
from md3.components.item_views import item_views
from md3.components.menus import menu as menu_module
from md3.components.pagination import pagination
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import typography as typography_tokens

Row = Mapping[str, Any] | Sequence[Any]
Formatter = Callable[[Any], str]
DEFAULT_PAGE_SIZES = (10, 25, 50, 100)
CHECK_COLUMN_WIDTH = 56
FOOTER_HEIGHT = 56
FOOTER_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
EMPTY_STYLE = typography_tokens.TypeRole.BODY_MEDIUM


@dataclasses.dataclass(frozen=True)
class Column:
    """数据表的一列。

    Attributes:
        key: 行为字典时取值的键；行为序列时为下标（int）。
        title: 表头文字。
        align: 单元格水平对齐；数值列通常靠右。
        width: 固定列宽（px），None 按内容自适应。
        sortable: 是否可点击排序。
        formatter: 把单元格值格式化为文字的函数，默认 ``str``。
        numeric: 为真时默认靠右对齐并按数值排序。
    """

    key: str | int
    title: str
    align: QtCore.Qt.AlignmentFlag | None = None
    width: int | None = None
    sortable: bool = True
    formatter: Formatter | None = None
    numeric: bool = False

    def alignment(self) -> QtCore.Qt.AlignmentFlag:
        """实际使用的水平对齐。"""
        if self.align is not None:
            return self.align
        return (
            QtCore.Qt.AlignmentFlag.AlignRight
            if self.numeric
            else QtCore.Qt.AlignmentFlag.AlignLeft
        )

    def value_of(self, row: Row) -> Any:
        """取该列在一行中的值。"""
        if isinstance(row, Mapping):
            return row.get(self.key)
        if isinstance(self.key, int):
            return row[self.key] if 0 <= self.key < len(row) else None
        return None

    def text_of(self, row: Row) -> str:
        """该列在一行中的显示文字。"""
        value = self.value_of(row)
        if value is None:
            return ""
        if self.formatter is not None:
            return self.formatter(value)
        return str(value)


class DataTableModel(QtCore.QAbstractTableModel):
    """支持排序、过滤与勾选的表格模型。

    模型行只包含通过过滤的行，``source_row(row)`` 把模型行换回原始下标；
    勾选状态按原始下标保存，排序与过滤都不会丢失。
    """

    check_changed = QtCore.Signal()

    def __init__(
        self,
        columns: Sequence[Column],
        rows: Sequence[Row] = (),
        checkable: bool = False,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._columns = list(columns)
        self._rows: list[Row] = list(rows)
        self._checkable = checkable
        self._checked: set[int] = set()
        self._order: list[int] = list(range(len(self._rows)))
        self._sort_column = -1
        self._sort_order = QtCore.Qt.SortOrder.AscendingOrder
        self._filter = ""

    # ---- 数据 -------------------------------------------------------------

    @property
    def columns(self) -> list[Column]:
        """列定义。"""
        return list(self._columns)

    @property
    def source_rows(self) -> list[Row]:
        """全部原始行。"""
        return list(self._rows)

    @property
    def checkable(self) -> bool:
        """是否带复选列。"""
        return self._checkable

    def set_rows(self, rows: Sequence[Row]) -> None:
        """替换全部行（清空勾选，保留排序与过滤）。"""
        self.beginResetModel()
        self._rows = list(rows)
        self._checked.clear()
        self._rebuild_order()
        self.endResetModel()
        self.check_changed.emit()

    def source_row(self, row: int) -> int:
        """模型行对应的原始行下标。"""
        return self._order[row]

    def model_row(self, source: int) -> int:
        """原始行下标对应的模型行，被过滤掉时为 -1。"""
        try:
            return self._order.index(source)
        except ValueError:
            return -1

    def row_data(self, row: int) -> Row:
        """模型行对应的原始行数据。"""
        return self._rows[self._order[row]]

    # ---- 过滤与排序 -------------------------------------------------------

    @property
    def filter_text(self) -> str:
        """当前过滤文字。"""
        return self._filter

    def set_filter(self, text: str) -> None:
        """按显示文字（忽略大小写、任意列包含）过滤。"""
        self.beginResetModel()
        self._filter = text.strip().lower()
        self._rebuild_order()
        self.endResetModel()

    def _matches(self, row: Row) -> bool:
        if not self._filter:
            return True
        return any(
            self._filter in column.text_of(row).lower()
            for column in self._columns
        )

    def _sort_key(self, column: Column) -> Callable[[int], Any]:
        def key(index: int) -> tuple[int, Any]:
            value = column.value_of(self._rows[index])
            if value is None:
                return (1, 0)
            if column.numeric:
                try:
                    return (0, float(value))
                except (TypeError, ValueError):
                    return (0, str(value))
            if isinstance(value, int | float):
                return (0, value)
            return (0, column.text_of(self._rows[index]).lower())

        return key

    def _rebuild_order(self) -> None:
        order = [
            index for index, row in enumerate(self._rows) if self._matches(row)
        ]
        if 0 <= self._sort_column < len(self._columns):
            column = self._columns[self._sort_column]
            try:
                order.sort(
                    key=self._sort_key(column),
                    reverse=self._sort_order
                    == QtCore.Qt.SortOrder.DescendingOrder,
                )
            except TypeError:
                order.sort(
                    key=lambda index: column.text_of(self._rows[index]).lower(),
                    reverse=self._sort_order
                    == QtCore.Qt.SortOrder.DescendingOrder,
                )
        self._order = order

    @override
    def sort(
        self,
        column: int,
        order: QtCore.Qt.SortOrder = QtCore.Qt.SortOrder.AscendingOrder,
    ) -> None:
        self.layoutAboutToBeChanged.emit()
        self._sort_column = column
        self._sort_order = order
        self._rebuild_order()
        self.layoutChanged.emit()

    @property
    def sort_column(self) -> int:
        """当前排序列，-1 为未排序。"""
        return self._sort_column

    @property
    def sort_order(self) -> QtCore.Qt.SortOrder:
        """当前排序方向。"""
        return self._sort_order

    # ---- 勾选 -------------------------------------------------------------

    @property
    def checked(self) -> list[int]:
        """已勾选的原始行下标（升序）。"""
        return sorted(self._checked)

    def set_checked(self, sources: Sequence[int], checked: bool) -> None:
        """批量设置原始行的勾选状态。"""
        changed = False
        for source in sources:
            if not 0 <= source < len(self._rows):
                continue
            if checked and source not in self._checked:
                self._checked.add(source)
                changed = True
            elif not checked and source in self._checked:
                self._checked.discard(source)
                changed = True
        if changed:
            if self._order:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(self._order) - 1, 0),
                    [QtCore.Qt.ItemDataRole.CheckStateRole],
                )
            self.check_changed.emit()

    def is_checked(self, source: int) -> bool:
        """原始行是否勾选。"""
        return source in self._checked

    # ---- QAbstractTableModel --------------------------------------------

    @override
    def rowCount(self, parent: QtCore.QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._order)

    @override
    def columnCount(self, parent: QtCore.QModelIndex | None = None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self._columns)

    @override
    def data(
        self,
        index: QtCore.QModelIndex,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._order):
            return None
        column = self._columns[index.column()]
        row = self._rows[self._order[index.row()]]
        if role == QtCore.Qt.ItemDataRole.DisplayRole:
            return column.text_of(row)
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            return int(
                column.alignment() | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
        if (
            role == QtCore.Qt.ItemDataRole.CheckStateRole
            and self._checkable
            and index.column() == 0
        ):
            return (
                QtCore.Qt.CheckState.Checked
                if self._order[index.row()] in self._checked
                else QtCore.Qt.CheckState.Unchecked
            )
        if role == QtCore.Qt.ItemDataRole.UserRole:
            return column.value_of(row)
        return None

    @override
    def setData(
        self,
        index: QtCore.QModelIndex,
        value: Any,
        role: int = QtCore.Qt.ItemDataRole.EditRole,
    ) -> bool:
        if (
            role == QtCore.Qt.ItemDataRole.CheckStateRole
            and self._checkable
            and index.isValid()
            and index.column() == 0
        ):
            source = self._order[index.row()]
            checked = (
                QtCore.Qt.CheckState(value) == QtCore.Qt.CheckState.Checked
            )
            self.set_checked([source], checked)
            return True
        return False

    @override
    def flags(self, index: QtCore.QModelIndex) -> QtCore.Qt.ItemFlag:
        flags = (
            QtCore.Qt.ItemFlag.ItemIsEnabled
            | QtCore.Qt.ItemFlag.ItemIsSelectable
        )
        if self._checkable and index.column() == 0:
            flags |= QtCore.Qt.ItemFlag.ItemIsUserCheckable
        return flags

    @override
    def headerData(
        self,
        section: int,
        orientation: QtCore.Qt.Orientation,
        role: int = QtCore.Qt.ItemDataRole.DisplayRole,
    ) -> Any:
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.DisplayRole
            and 0 <= section < len(self._columns)
        ):
            return self._columns[section].title
        if (
            orientation == QtCore.Qt.Orientation.Horizontal
            and role == QtCore.Qt.ItemDataRole.TextAlignmentRole
            and 0 <= section < len(self._columns)
        ):
            return int(self._columns[section].alignment())
        return None


class _DataTableHeader(item_views.MaterialHeaderView):
    """带全选复选框的表头。"""

    select_all_clicked = QtCore.Signal()

    def __init__(
        self, table: DataTable, dense: bool, parent: QtWidgets.QWidget
    ) -> None:
        super().__init__(QtCore.Qt.Orientation.Horizontal, dense, parent)
        self._table = table

    def _check_rect(self, rect: QtCore.QRect) -> QtCore.QRectF:
        return QtCore.QRectF(
            rect.left() + item_views.CELL_PADDING,
            rect.top(),
            item_views.ICON_SIZE,
            rect.height(),
        )

    @override
    def paintSection(
        self, painter: QtGui.QPainter, rect: QtCore.QRect, logical_index: int
    ) -> None:
        if not (self._table.checkable and logical_index == 0):
            super().paintSection(painter, rect, logical_index)
            return
        theme = theme_module.current()
        painter.save()
        painter.fillRect(rect, theme.color("surface"))
        painter.fillRect(
            QtCore.QRectF(
                rect.left(),
                rect.bottom() + 1 - item_views.DIVIDER_WIDTH,
                rect.width(),
                item_views.DIVIDER_WIDTH,
            ),
            theme.color("outline_variant"),
        )
        item_views.paint_checkbox(
            painter,
            self._check_rect(rect),
            self._table.page_check_state(),
            theme,
            self.isEnabled() and self._table.page_row_count() > 0,
        )
        title = self._table.columns[0].title if self._table.columns else ""
        if title:
            typography.paint_text(
                painter,
                QtCore.QRectF(rect).adjusted(
                    item_views.CELL_PADDING
                    + item_views.ICON_SIZE
                    + item_views.ICON_GAP,
                    0,
                    -item_views.CELL_PADDING,
                    0,
                ),
                title,
                item_views.HEADER_STYLE,
                theme.color("on_surface_variant"),
            )
        painter.restore()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        index = self.logicalIndexAt(event.position().toPoint())
        if self._table.checkable and index == 0:
            rect = QtCore.QRect(
                self.sectionViewportPosition(0),
                0,
                self.sectionSize(0),
                self.height(),
            )
            if (
                self._check_rect(rect)
                .adjusted(-8, 0, 8, 0)
                .contains(event.position())
            ):
                self.select_all_clicked.emit()
                event.accept()
                return
        super().mouseReleaseEvent(event)


class DataTable(QtWidgets.QWidget):
    """M3 数据表。

    Args:
        columns: 列定义。
        rows: 初始行。
        checkable: 是否显示复选列。
        page_size: 每页行数；0 表示不分页。
        page_sizes: 页脚可选的每页行数。
        dense: 是否使用紧凑密度。
        sortable: 是否允许点击表头排序。
        show_footer: 是否显示页脚。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(list)
    row_activated = QtCore.Signal(int)
    sort_changed = QtCore.Signal(int, object)
    page_changed = QtCore.Signal(int)

    def __init__(
        self,
        columns: Sequence[Column],
        rows: Sequence[Row] = (),
        checkable: bool = False,
        page_size: int = 10,
        page_sizes: Sequence[int] = DEFAULT_PAGE_SIZES,
        dense: bool = False,
        sortable: bool = True,
        show_footer: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = DataTableModel(columns, rows, checkable, self)
        self._model.check_changed.connect(self._on_check_changed)
        self._page_size = max(0, page_size)
        self._page_sizes = tuple(sorted(set(page_sizes)))
        self._page = 0
        self._sortable = sortable
        self._dense = dense
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._view = item_views.MaterialTableView(dense=dense)
        self._view.setModel(self._model)
        self._view.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.SingleSelection
        )
        self._view.doubleClicked.connect(self._on_double_clicked)
        self._view.clicked.connect(self._on_clicked)
        self._install_header()
        layout.addWidget(self._view, 1)
        self._empty = typography.Label(
            i18n.tr("no_data"), EMPTY_STYLE, "on_surface_variant", self._view
        )
        self._empty.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._footer = QtWidgets.QWidget(self)
        self._footer.setFixedHeight(FOOTER_HEIGHT)
        footer_layout = QtWidgets.QHBoxLayout(self._footer)
        footer_layout.setContentsMargins(16, 0, 8, 0)
        footer_layout.setSpacing(8)
        footer_layout.addStretch()
        self._page_size_label = typography.Label(
            i18n.tr("rows_per_page"), FOOTER_STYLE, "on_surface_variant"
        )
        footer_layout.addWidget(self._page_size_label)
        self._page_size_button = buttons.Button(
            str(self._page_size or "—"),
            variant=buttons.ButtonVariant.TEXT,
            trailing_icon="arrow_drop_down",
        )
        self._page_size_button.clicked.connect(self._open_page_size_menu)
        self._page_size_menu = menu_module.Menu(parent=self)
        self._page_size_menu.triggered.connect(self._on_page_size_chosen)
        footer_layout.addWidget(self._page_size_button)
        footer_layout.addSpacing(16)
        self._range_label = typography.Label(
            "", FOOTER_STYLE, "on_surface_variant"
        )
        footer_layout.addWidget(self._range_label)
        self._pagination = pagination.Pagination(show_numbers=False)
        self._pagination.page_changed.connect(self._on_page_changed)
        footer_layout.addWidget(self._pagination)
        layout.addWidget(self._footer)
        self._footer.setVisible(show_footer)
        self._apply_columns()
        self._refresh_page()

    # ---- 组成部分 ---------------------------------------------------------

    @property
    def view(self) -> item_views.MaterialTableView:
        """内部表格视图。"""
        return self._view

    @property
    def model(self) -> DataTableModel:
        """内部模型。"""
        return self._model

    @property
    def pagination(self) -> pagination.Pagination:
        """页脚分页器。"""
        return self._pagination

    @property
    def columns(self) -> list[Column]:
        """列定义。"""
        return self._model.columns

    @property
    def checkable(self) -> bool:
        """是否带复选列。"""
        return self._model.checkable

    def _install_header(self) -> None:
        header = _DataTableHeader(self, self._dense, self._view)
        header.select_all_clicked.connect(self.toggle_page_checked)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(self._on_header_clicked)
        self._view.setHorizontalHeader(header)
        # 排序由 DataTable 自己处理（分页 + 模型排序），关闭视图内建排序；
        # 该调用会隐藏排序指示器，因此必须在其之后再打开。
        self._view.setSortingEnabled(False)
        header.setSortIndicatorShown(self._sortable)

    def _apply_columns(self) -> None:
        # 指定宽度的列固定，其余列平分剩余宽度；全部固定时最后一列补满。
        header = self._view.horizontalHeader()
        for index, column in enumerate(self.columns):
            if column.width is not None:
                header.setSectionResizeMode(
                    index, QtWidgets.QHeaderView.ResizeMode.Fixed
                )
                header.resizeSection(index, column.width)
            else:
                header.setSectionResizeMode(
                    index, QtWidgets.QHeaderView.ResizeMode.Stretch
                )
        if self.columns and all(c.width is not None for c in self.columns):
            header.setSectionResizeMode(
                len(self.columns) - 1, QtWidgets.QHeaderView.ResizeMode.Stretch
            )

    # ---- 数据 -------------------------------------------------------------

    @property
    def rows(self) -> list[Row]:
        """全部原始行。"""
        return self._model.source_rows

    def set_rows(self, rows: Sequence[Row]) -> None:
        """替换全部行并回到第一页。"""
        self._model.set_rows(rows)
        self._page = 0
        self._refresh_page()

    def row_count(self) -> int:
        """通过过滤的行数。"""
        return self._model.rowCount()

    def set_filter(self, text: str) -> None:
        """按显示文字过滤并回到第一页。"""
        self._model.set_filter(text)
        self._page = 0
        self._refresh_page()

    # ---- 勾选 -------------------------------------------------------------

    @property
    def checked_rows(self) -> list[int]:
        """已勾选的原始行下标。"""
        return self._model.checked

    def set_checked(self, sources: Sequence[int], checked: bool = True) -> None:
        """设置原始行的勾选状态。"""
        self._model.set_checked(sources, checked)

    def clear_checked(self) -> None:
        """取消全部勾选。"""
        self._model.set_checked(self._model.checked, False)

    def page_rows(self) -> range:
        """当前页对应的模型行区间。"""
        total = self._model.rowCount()
        if self._page_size <= 0:
            return range(total)
        start = self._page * self._page_size
        return range(start, min(total, start + self._page_size))

    def page_row_count(self) -> int:
        """当前页的行数。"""
        return len(self.page_rows())

    def page_check_state(self) -> QtCore.Qt.CheckState:
        """表头复选框状态：当前页全部 / 部分 / 没有勾选。"""
        sources = [self._model.source_row(row) for row in self.page_rows()]
        if not sources:
            return QtCore.Qt.CheckState.Unchecked
        checked = sum(1 for source in sources if self._model.is_checked(source))
        if checked == 0:
            return QtCore.Qt.CheckState.Unchecked
        if checked == len(sources):
            return QtCore.Qt.CheckState.Checked
        return QtCore.Qt.CheckState.PartiallyChecked

    def toggle_page_checked(self) -> None:
        """表头复选框：当前页未全选则全选，否则取消。"""
        sources = [self._model.source_row(row) for row in self.page_rows()]
        select = self.page_check_state() != QtCore.Qt.CheckState.Checked
        self._model.set_checked(sources, select)

    def _on_check_changed(self) -> None:
        self._view.horizontalHeader().viewport().update()
        self.selection_changed.emit(self._model.checked)

    def _on_clicked(self, index: QtCore.QModelIndex) -> None:
        if self.checkable and index.column() == 0:
            source = self._model.source_row(index.row())
            self._model.set_checked(
                [source], not self._model.is_checked(source)
            )

    def _on_double_clicked(self, index: QtCore.QModelIndex) -> None:
        if index.isValid():
            self.row_activated.emit(self._model.source_row(index.row()))

    # ---- 排序 -------------------------------------------------------------

    def sort_by(
        self,
        column: int,
        order: QtCore.Qt.SortOrder = QtCore.Qt.SortOrder.AscendingOrder,
    ) -> None:
        """按列排序。"""
        if not 0 <= column < len(self.columns):
            return
        self._model.sort(column, order)
        header = self._view.horizontalHeader()
        header.setSortIndicator(column, order)
        self._refresh_page()
        self.sort_changed.emit(column, order)

    def _on_header_clicked(self, section: int) -> None:
        if not self._sortable or not self.columns[section].sortable:
            return
        if self._model.sort_column == section:
            order = (
                QtCore.Qt.SortOrder.DescendingOrder
                if self._model.sort_order == QtCore.Qt.SortOrder.AscendingOrder
                else QtCore.Qt.SortOrder.AscendingOrder
            )
        else:
            order = QtCore.Qt.SortOrder.AscendingOrder
        self.sort_by(section, order)

    # ---- 分页 -------------------------------------------------------------

    @property
    def page_size(self) -> int:
        """每页行数，0 表示不分页。"""
        return self._page_size

    def set_page_size(self, page_size: int) -> None:
        """设置每页行数并回到第一页。"""
        self._page_size = max(0, page_size)
        self._page = 0
        self._page_size_button.set_text(str(self._page_size or "—"))
        self._refresh_page()

    @property
    def page_count(self) -> int:
        """总页数（至少 1）。"""
        total = self._model.rowCount()
        if self._page_size <= 0 or total == 0:
            return 1
        return (total + self._page_size - 1) // self._page_size

    @property
    def current_page(self) -> int:
        """当前页下标。"""
        return self._page

    def set_current_page(self, page: int) -> None:
        """跳到指定页。"""
        page = max(0, min(page, self.page_count - 1))
        if page != self._page:
            self._page = page
            self._refresh_page()
            self.page_changed.emit(page)
        else:
            self._pagination.set_current_page(page)

    def _on_page_changed(self, page: int) -> None:
        if page != self._page:
            self._page = page
            self._refresh_page()
            self.page_changed.emit(page)

    def _open_page_size_menu(self) -> None:
        self._page_size_menu.set_items(
            [
                menu_module.MenuItem(
                    text=str(size),
                    checkable=True,
                    checked=size == self._page_size,
                    key=size,
                )
                for size in self._page_sizes
            ]
        )
        self._page_size_menu.popup_below(self._page_size_button)

    def _on_page_size_chosen(self, item: menu_module.MenuItem) -> None:
        self.set_page_size(int(item.key))

    def _refresh_page(self) -> None:
        total = self._model.rowCount()
        visible = self.page_rows()
        for row in range(total):
            self._view.setRowHidden(row, row not in visible)
        self._pagination.set_page_count(self.page_count)
        self._pagination.set_current_page(self._page)
        if total == 0:
            self._range_label.setText(
                i18n.tr("page_range").format(start=0, end=0, total=0)
            )
        else:
            self._range_label.setText(
                i18n.tr("page_range").format(
                    start=visible.start + 1, end=visible.stop, total=total
                )
            )
        self._empty.setVisible(total == 0)
        self._position_empty()
        self._view.horizontalHeader().viewport().update()

    def range_text(self) -> str:
        """页脚的行范围文字。"""
        return self._range_label.text()

    # ---- 外观 -------------------------------------------------------------

    @property
    def dense(self) -> bool:
        """是否为紧凑密度。"""
        return self._dense

    def set_dense(self, dense: bool) -> None:
        """切换 52dp / 40dp 行高。"""
        if dense == self._dense:
            return
        self._dense = dense
        self._view.material_delegate = item_views.apply_material_style(
            self._view, dense
        )
        self._install_header()
        self._apply_columns()
        self._view.verticalHeader().setDefaultSectionSize(
            item_views.DENSE_ROW_HEIGHT if dense else item_views.ROW_HEIGHT
        )
        self._refresh_page()

    def set_empty_text(self, text: str) -> None:
        """设置没有数据时显示的文字。"""
        self._empty.setText(text)

    def set_show_footer(self, show: bool) -> None:
        """显示或隐藏页脚。"""
        self._footer.setVisible(show)

    def _position_empty(self) -> None:
        header_height = self._view.horizontalHeader().height()
        self._empty.setGeometry(
            0,
            header_height,
            self._view.width(),
            max(0, self._view.height() - header_height),
        )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._position_empty()
