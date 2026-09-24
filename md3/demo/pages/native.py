"""Native 页面：原生 Qt 控件在主题样式表下的外观。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.demo.pages import _common


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "原生控件",
        "未被 M3 组件替代的原生 Qt 控件由应用级样式表统一配色："
        "按钮、输入框、下拉框、数字框、复选框、单选框、滑块、进度条、"
        "标签页、分组框与分割条。",
    )
    _build_buttons(page)
    _build_inputs(page)
    _build_choices(page)
    _build_ranges(page)
    _build_containers(page)
    _build_views(page)
    page.finish()
    return page


def _build_buttons(page: _common.Page) -> None:
    section = page.section("按钮")
    default_button = QtWidgets.QPushButton("默认按钮")
    default_button.setDefault(True)
    flat = QtWidgets.QPushButton("文字按钮")
    flat.setFlat(True)
    checkable = QtWidgets.QPushButton("可切换")
    checkable.setCheckable(True)
    checkable.setChecked(True)
    disabled = QtWidgets.QPushButton("禁用")
    disabled.setEnabled(False)
    tool = QtWidgets.QToolButton()
    tool.setText("工具按钮")
    tool.setCheckable(True)
    page.row(
        section,
        [
            QtWidgets.QPushButton("普通按钮"),
            default_button,
            flat,
            checkable,
            disabled,
            tool,
        ],
    )


def _build_inputs(page: _common.Page) -> None:
    section = page.section("输入")
    line = QtWidgets.QLineEdit()
    line.setPlaceholderText("QLineEdit")
    combo = QtWidgets.QComboBox()
    combo.addItems(["选项一", "选项二", "选项三"])
    spin = QtWidgets.QSpinBox()
    spin.setRange(0, 100)
    spin.setValue(42)
    double_spin = QtWidgets.QDoubleSpinBox()
    double_spin.setRange(0, 10)
    double_spin.setValue(3.14)
    date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
    date.setCalendarPopup(False)
    for editor in (line, combo, spin, double_spin, date):
        editor.setMinimumWidth(160)
    page.row(section, [line, combo, spin, double_spin, date])
    text = QtWidgets.QPlainTextEdit()
    text.setPlaceholderText("QPlainTextEdit")
    text.setFixedSize(360, 96)
    section.addWidget(text)


def _build_choices(page: _common.Page) -> None:
    section = page.section("选择")
    checked = QtWidgets.QCheckBox("已选中")
    checked.setChecked(True)
    partial = QtWidgets.QCheckBox("部分选中")
    partial.setTristate(True)
    partial.setCheckState(QtCore.Qt.CheckState.PartiallyChecked)
    disabled_check = QtWidgets.QCheckBox("禁用")
    disabled_check.setChecked(True)
    disabled_check.setEnabled(False)
    radio_on = QtWidgets.QRadioButton("单选 A")
    radio_on.setChecked(True)
    page.row(
        section,
        [
            QtWidgets.QCheckBox("未选中"),
            checked,
            partial,
            disabled_check,
            radio_on,
            QtWidgets.QRadioButton("单选 B"),
        ],
    )


def _build_ranges(page: _common.Page) -> None:
    section = page.section("滑块与进度")
    slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
    slider.setRange(0, 100)
    slider.setValue(40)
    slider.setFixedWidth(240)
    progress = QtWidgets.QProgressBar()
    progress.setRange(0, 100)
    progress.setValue(65)
    progress.setFixedWidth(240)
    slider.valueChanged.connect(progress.setValue)
    vertical = QtWidgets.QSlider(QtCore.Qt.Orientation.Vertical)
    vertical.setRange(0, 100)
    vertical.setValue(70)
    vertical.setFixedHeight(120)
    page.row(section, [slider, progress, vertical], gap=24)


def _build_containers(page: _common.Page) -> None:
    section = page.section("标签页、分组框与分割条")
    tabs = QtWidgets.QTabWidget()
    for name in ("概览", "详情", "设置"):
        content = QtWidgets.QLabel(f"{name}页内容")
        content.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        tabs.addTab(content, name)
    tabs.setFixedSize(360, 160)
    group = QtWidgets.QGroupBox("分组框")
    group.setCheckable(True)
    group_layout = QtWidgets.QVBoxLayout(group)
    group_layout.addWidget(QtWidgets.QCheckBox("选项 1"))
    group_layout.addWidget(QtWidgets.QCheckBox("选项 2"))
    splitter = QtWidgets.QSplitter()
    for name in ("左", "右"):
        pane = QtWidgets.QLabel(name)
        pane.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        splitter.addWidget(pane)
    splitter.setFixedSize(240, 120)
    page.row(section, [tabs, group, splitter], gap=24, align_top=True)


def _build_views(page: _common.Page) -> None:
    section = page.section("原生列表")
    table = QtWidgets.QTableWidget(4, 3)
    table.setHorizontalHeaderLabels(["名称", "数量", "状态"])
    for row in range(4):
        values = (f"项目 {row + 1}", str(row * 7), "正常")
        for column, value in enumerate(values):
            table.setItem(row, column, QtWidgets.QTableWidgetItem(value))
    table.setFixedSize(420, 200)
    section.addWidget(table)
