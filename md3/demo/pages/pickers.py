"""Pickers 页面：日期、日期范围、时间与颜色选择器。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import pickers
from md3.core import typography
from md3.demo.pages import _common

PRESETS = ["#6750A4", "#0061A4", "#006D3A", "#B3261E", "#7D5700", "#006A6A"]


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "选择器",
        "日期、日期范围、时间与颜色选择器；对话框可切换为键盘输入。",
    )

    inline = page.section(
        "内嵌月历与时间选择器",
        "左侧月历为范围选择模式：先点起点再点终点；时间选择器分钟步长为 5。",
    )
    row = QtWidgets.QHBoxLayout()
    row.setSpacing(32)
    today = QtCore.QDate.currentDate()
    calendar = pickers.CalendarView(today, mode=pickers.SelectionMode.RANGE)
    calendar.set_selected_range(today.addDays(2), today.addDays(9))
    row.addWidget(calendar, 0, QtCore.Qt.AlignmentFlag.AlignTop)
    time_picker = pickers.TimePicker(QtCore.QTime.currentTime(), minute_step=5)
    row.addWidget(time_picker, 0, QtCore.Qt.AlignmentFlag.AlignTop)
    row.addStretch()
    inline.addLayout(row)

    fields_section = page.section(
        "带弹出选择器的文本框",
        "可以直接键入（支持 2026/9/4、2026-09-04 等格式），"
        "也可以点击尾部图标选择。",
    )
    date_field = pickers.DateField("出发日期", today)
    return_field = pickers.DateField(
        "返程日期", today.addDays(3), minimum=today
    )
    time_field = pickers.TimeField("出发时间", QtCore.QTime(9, 30))
    for field in (date_field, return_field, time_field):
        field.setMaximumWidth(280)
    page.row(fields_section, [date_field, return_field, time_field], gap=16)

    dialogs_section = page.section("对话框形式")
    result = typography.Label("", "body-medium", "on_surface_variant")
    date_button = buttons.OutlinedButton("选择日期", icon="calendar_today")
    range_button = buttons.OutlinedButton("选择日期范围", icon="date_range")
    time_button = buttons.OutlinedButton("选择时间", icon="schedule")
    time24_button = buttons.OutlinedButton("24 小时制", icon="schedule")
    docked_button = buttons.OutlinedButton("停靠日期选择", icon="event")

    def pick_date() -> None:
        dialog = pickers.DatePickerDialog(today, parent=page)
        dialog.date_selected.connect(
            lambda d: result.setText(f"日期：{d.toString('yyyy-MM-dd')}")
        )
        dialog.open()

    def pick_range() -> None:
        dialog = pickers.DateRangePickerDialog(
            today, today.addDays(6), parent=page
        )
        dialog.range_selected.connect(
            lambda s, e: result.setText(
                f"范围：{s.toString('MM-dd')} 至 {e.toString('MM-dd')}"
            )
        )
        dialog.open()

    def pick_time(is_24: bool) -> None:
        dialog = pickers.TimePickerDialog(
            QtCore.QTime.currentTime(), is_24_hour=is_24, parent=page
        )
        dialog.time_selected.connect(
            lambda t: result.setText(f"时间：{t.toString('HH:mm')}")
        )
        dialog.open()

    docked = pickers.DockedDatePicker(today, parent=page)
    docked.date_selected.connect(
        lambda d: result.setText(f"日期：{d.toString('yyyy-MM-dd')}")
    )
    date_button.clicked.connect(pick_date)
    range_button.clicked.connect(pick_range)
    time_button.clicked.connect(lambda: pick_time(False))
    time24_button.clicked.connect(lambda: pick_time(True))
    docked_button.clicked.connect(lambda: docked.popup_below(docked_button))
    page.row(
        dialogs_section,
        [date_button, range_button, time_button, time24_button, docked_button],
    )
    dialogs_section.addWidget(result)
    _build_color_section(page)
    page.finish()
    return page


def _build_color_section(page: _common.Page) -> None:
    """颜色选择器分节：内嵌选择器与对话框。"""
    section = page.section(
        "颜色选择器",
        "基于 HCT 色彩空间：同一色调下颜色明暗一致，滑块轨道随其余分量实时"
        "渲染。",
    )
    picker = pickers.ColorPicker("#6750A4", presets=PRESETS)
    picker.setMaximumWidth(480)
    chosen = typography.Label("#6750A4", "label-large", "on_surface_variant")

    def on_color(color: QtGui.QColor) -> None:
        hue, chroma, tone = picker.hct
        chosen.setText(
            f"{color.name().upper()}  H {hue:.0f}° C {chroma:.0f} T {tone:.0f}"
        )

    picker.color_changed.connect(on_color)
    section.addWidget(picker)
    row = QtWidgets.QHBoxLayout()
    color_button = buttons.OutlinedButton("颜色对话框", icon="palette")

    def pick_color() -> None:
        dialog = pickers.ColorPickerDialog(
            picker.selected_color, presets=PRESETS, parent=page
        )
        dialog.color_selected.connect(picker.set_selected_color)
        dialog.open()

    color_button.clicked.connect(pick_color)
    row.addWidget(color_button)
    row.addWidget(chosen)
    row.addStretch()
    section.addLayout(row)
