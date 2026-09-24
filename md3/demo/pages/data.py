"""Data 页面：Material 风格的表格、树与列表视图。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import data_table
from md3.components import item_views
from md3.components import pagination
from md3.components import selection
from md3.components import text_fields
from md3.core import typography
from md3.demo.pages import _common

_ROWS = (
    ("季度报表.xlsx", "表格", "2.4 MB", "李娜", "今天 09:12"),
    ("产品路线图.pdf", "文档", "860 KB", "王芳", "昨天"),
    ("品牌规范.fig", "设计", "18.2 MB", "张伟", "3 天前"),
    ("发布说明.md", "文档", "12 KB", "刘洋", "上周"),
    ("演示视频.mp4", "视频", "210 MB", "陈静", "上周"),
    ("图标集.zip", "压缩包", "4.1 MB", "李娜", "两周前"),
    ("用户访谈.docx", "文档", "1.1 MB", "赵敏", "上月"),
    ("数据字典.csv", "表格", "330 KB", "王芳", "上月"),
)
_ICONS = {
    "表格": "table_chart",
    "文档": "description",
    "设计": "palette",
    "视频": "movie",
    "压缩包": "folder_zip",
}


def _table_model(parent: QtCore.QObject) -> QtGui.QStandardItemModel:
    model = QtGui.QStandardItemModel(0, 5, parent)
    model.setHorizontalHeaderLabels(
        ["名称", "类型", "大小", "所有者", "修改时间"]
    )
    for index, (name, kind, size, owner, modified) in enumerate(_ROWS):
        first = QtGui.QStandardItem(name)
        first.setCheckable(True)
        first.setCheckState(
            QtCore.Qt.CheckState.Checked
            if index % 3 == 0
            else QtCore.Qt.CheckState.Unchecked
        )
        first.setData(_ICONS[kind], QtCore.Qt.ItemDataRole.DecorationRole)
        size_item = QtGui.QStandardItem(size)
        size_item.setData(
            int(
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            ),
            QtCore.Qt.ItemDataRole.TextAlignmentRole,
        )
        model.appendRow(
            [
                first,
                QtGui.QStandardItem(kind),
                size_item,
                QtGui.QStandardItem(owner),
                QtGui.QStandardItem(modified),
            ]
        )
    return model


def _tree_model(parent: QtCore.QObject) -> QtGui.QStandardItemModel:
    model = QtGui.QStandardItemModel(parent)
    model.setHorizontalHeaderLabels(["项目", "状态"])
    structure = {
        "设计系统": {
            "色彩": ["配色方案", "对比度"],
            "排版": ["字体", "字号标度"],
            "形状": [],
        },
        "组件": {"按钮": ["通用按钮", "图标按钮", "FAB"], "输入": ["文本框"]},
        "文档": {},
    }
    icon_for = {"设计系统": "palette", "组件": "widgets", "文档": "menu_book"}
    for top, children in structure.items():
        root = QtGui.QStandardItem(top)
        root.setData(icon_for[top], QtCore.Qt.ItemDataRole.DecorationRole)
        model.appendRow([root, QtGui.QStandardItem("进行中")])
        for name, leaves in children.items():
            node = QtGui.QStandardItem(name)
            root.appendRow([node, QtGui.QStandardItem(f"{len(leaves)} 项")])
            for leaf in leaves:
                node.appendRow(
                    [QtGui.QStandardItem(leaf), QtGui.QStandardItem("已完成")]
                )
    return model


_CITIES = (
    ("上海", "华东", 24.87, 6340, 2.1),
    ("北京", "华北", 21.86, 16410, 1.4),
    ("广州", "华南", 18.74, 7434, 3.6),
    ("深圳", "华南", 17.68, 1997, 4.2),
    ("成都", "西南", 21.19, 14335, 3.0),
    ("重庆", "西南", 32.05, 82402, 1.8),
    ("杭州", "华东", 12.20, 16850, 2.9),
    ("武汉", "华中", 13.65, 8569, 2.4),
    ("西安", "西北", 12.99, 10108, 2.6),
    ("南京", "华东", 9.42, 6587, 1.9),
    ("天津", "华北", 13.73, 11966, 0.8),
    ("苏州", "华东", 12.75, 8657, 2.2),
    ("郑州", "华中", 12.74, 7567, 3.1),
    ("长沙", "华中", 10.24, 11819, 3.4),
    ("青岛", "华北", 10.25, 11293, 1.6),
    ("沈阳", "东北", 9.11, 12860, 0.4),
    ("宁波", "华东", 9.61, 9816, 2.0),
    ("昆明", "西南", 8.50, 21013, 1.7),
    ("合肥", "华东", 9.63, 11445, 2.8),
    ("厦门", "华南", 5.28, 1701, 3.3),
)


def _city_rows() -> list[dict[str, object]]:
    return [
        {
            "city": city,
            "region": region,
            "population": population,
            "area": area,
            "growth": growth,
        }
        for city, region, population, area, growth in _CITIES
    ]


def _build_data_table(page: _common.Page) -> None:
    section = page.section(
        "数据表",
        "DataTable 在 MaterialTableView 之上组合了复选列、排序、过滤、"
        "分页页脚与空状态；勾选表头复选框全选当前页。",
    )
    columns = [
        data_table.Column("city", "城市", width=160),
        data_table.Column("region", "区域", width=120),
        data_table.Column(
            "population",
            "人口（百万）",
            numeric=True,
            formatter=lambda value: f"{value:.2f}",
        ),
        data_table.Column(
            "area",
            "面积（km²）",
            numeric=True,
            formatter=lambda value: f"{value:,}",
        ),
        data_table.Column(
            "growth",
            "增长率",
            numeric=True,
            formatter=lambda value: f"{value:.1f}%",
        ),
    ]
    table = data_table.DataTable(
        columns,
        _city_rows(),
        checkable=True,
        page_size=5,
        page_sizes=(5, 10, 20),
    )
    table.sort_by(2, QtCore.Qt.SortOrder.DescendingOrder)
    table.setMinimumHeight(56 + 52 * 5 + 64)
    search = text_fields.OutlinedTextField(
        "筛选城市或区域", leading_icon="search"
    )
    search.text_changed.connect(table.set_filter)
    status = typography.Label("未选择", "body-medium", "on_surface_variant")

    def on_selection(rows: list[int]) -> None:
        names = [str(table.rows[row]["city"]) for row in rows]
        status.setText(
            f"已选 {len(rows)} 项：{'、'.join(names)}" if rows else "未选择"
        )

    table.selection_changed.connect(on_selection)
    dense = selection.Switch("紧凑密度")
    dense.toggled.connect(table.set_dense)
    page.row(section, [search, dense, status], gap=16)
    section.addWidget(table)


def _build_pagination(page: _common.Page) -> None:
    section = page.section(
        "分页器", "Pagination 独立使用：数字页码、省略号折叠与首末页按钮。"
    )
    pager = pagination.Pagination(
        page_count=24, current_page=6, show_first_last=True
    )
    status = typography.Label(
        "第 7 / 24 页", "body-medium", "on_surface_variant"
    )
    pager.page_changed.connect(
        lambda index: status.setText(f"第 {index + 1} / 24 页")
    )
    page.row(section, [pager, status], gap=16)
    compact = pagination.Pagination(page_count=3, show_numbers=False)
    page.row(section, [compact])


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "数据",
        "为 QTableView / QTreeView / QListView 套用 M3 数据表样式：52dp 行高、"
        "分隔线、悬停与选中态、可排序表头、勾选列与 Material 图标。",
    )
    _build_data_table(page)
    _build_pagination(page)

    table_section = page.section(
        "原生表格", "点击表头排序；勾选列使用 M3 复选框；切换紧凑密度。"
    )
    table = item_views.MaterialTableView()
    proxy = QtCore.QSortFilterProxyModel(table)
    proxy.setSourceModel(_table_model(table))
    table.setModel(proxy)
    table.setSortingEnabled(True)
    table.sortByColumn(0, QtCore.Qt.SortOrder.AscendingOrder)
    table.setColumnWidth(0, 260)
    table.setFixedHeight(56 + 52 * len(_ROWS) + 4)
    table.setSelectionMode(
        QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
    )
    table.selectRow(1)
    dense_switch = selection.Switch("紧凑密度")

    def toggle_dense(checked: bool) -> None:
        item_views.apply_material_style(table, dense=checked)
        row = 40 if checked else 52
        header = 44 if checked else 56
        table.setFixedHeight(header + row * len(_ROWS) + 4)

    dense_switch.toggled.connect(toggle_dense)
    table_section.addWidget(dense_switch)
    table_section.addWidget(table)

    tree_list = page.section("树与列表")
    row = QtWidgets.QHBoxLayout()
    row.setSpacing(24)
    tree = item_views.MaterialTreeView()
    tree.setModel(_tree_model(tree))
    tree.expandAll()
    tree.setColumnWidth(0, 240)
    tree.setFixedHeight(56 + 52 * 8)
    row.addWidget(tree, 3)
    listing = item_views.MaterialListView(dense=True)
    list_model = QtGui.QStandardItemModel(listing)
    for name, icon in (
        ("收件箱", "inbox"),
        ("已加星", "star"),
        ("已发送", "send"),
        ("草稿", "drafts"),
        ("垃圾邮件", "report"),
        ("已删除", "delete"),
    ):
        item = QtGui.QStandardItem(name)
        item.setData(icon, QtCore.Qt.ItemDataRole.DecorationRole)
        list_model.appendRow(item)
    listing.setModel(list_model)
    listing.setCurrentIndex(list_model.index(0, 0))
    listing.setFixedHeight(40 * 6 + 4)
    row.addWidget(listing, 1)
    tree_list.addLayout(row)
    page.finish()
    return page
