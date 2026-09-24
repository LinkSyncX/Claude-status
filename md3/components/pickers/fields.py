"""带弹出选择器的日期 / 时间文本框。

``DateField`` 是 M3 "停靠日期选择器" 的完整形态：轮廓文本框加尾部日历
图标，点击图标在下方弹出月历，也可以直接键入日期；``TimeField`` 以同样
的方式弹出时间选择对话框。
"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.pickers import date_picker
from md3.components.pickers import time_picker
from md3.components.text_fields import text_field

_TIME_FORMATS = ("HH:mm", "H:mm", "HHmm", "h:mm AP", "h:mm ap", "H点m分")


def parse_time(text: str) -> QtCore.QTime | None:
    """解析用户输入的时间（``HH:mm``、``H:mm``、``HHmm`` 或 ``h:mm AM``）。"""
    text = text.strip()
    if not text:
        return None
    for pattern in _TIME_FORMATS:
        time = QtCore.QTime.fromString(text, pattern)
        if time.isValid():
            return time
    return None


def format_time(time: QtCore.QTime | None, is_24_hour: bool = True) -> str:
    """把时间格式化为文本框中的文字。"""
    if time is None or not time.isValid():
        return ""
    return time.toString("HH:mm" if is_24_hour else "h:mm AP")


class DateField(text_field.OutlinedTextField):
    """日期文本框：可键入日期，也可点击尾部图标从停靠月历中选择。

    Args:
        label: 浮动标签。
        date: 初始日期。
        minimum: 最早日期。
        maximum: 最晚日期。
        supporting_text: 辅助文字，默认提示输入格式。
        parent: 父控件。
    """

    date_changed = QtCore.Signal(QtCore.QDate)

    def __init__(
        self,
        label: str | None = None,
        date: QtCore.QDate | None = None,
        minimum: QtCore.QDate | None = None,
        maximum: QtCore.QDate | None = None,
        supporting_text: str = date_picker.DATE_INPUT_HINT,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            i18n.tr("date") if label is None else label,
            date_picker.format_input(date),
            placeholder=date_picker.DATE_INPUT_HINT,
            supporting_text=supporting_text,
            trailing_icon="calendar_today",
            parent=parent,
        )
        self._date = date if date is not None and date.isValid() else None
        self._minimum = minimum
        self._maximum = maximum
        self._picker: date_picker.DockedDatePicker | None = None
        self.trailing_icon_clicked.connect(self.open_picker)
        self.editing_finished.connect(self._commit_text)

    @property
    def date(self) -> QtCore.QDate | None:
        """当前日期；文本无效时为 None。"""
        return self._date

    def set_date(self, date: QtCore.QDate | None) -> None:
        """设置日期并同步文本。"""
        date = date if date is not None and date.isValid() else None
        if date is not None and not self._in_range(date):
            return
        self.set_text(date_picker.format_input(date))
        self.set_error(False)
        self._apply(date)

    def set_range(
        self, minimum: QtCore.QDate | None, maximum: QtCore.QDate | None
    ) -> None:
        """设置可选日期范围。"""
        self._minimum = minimum
        self._maximum = maximum
        if self._picker is not None:
            self._picker.calendar.set_range(minimum, maximum)

    @property
    def picker(self) -> date_picker.DockedDatePicker:
        """停靠月历弹出面板（首次访问时创建）。"""
        if self._picker is None:
            self._picker = date_picker.DockedDatePicker(
                self._date, self._minimum, self._maximum, parent=self
            )
            self._picker.date_selected.connect(self.set_date)
        return self._picker

    def open_picker(self) -> None:
        """在文本框下方弹出月历。"""
        picker = self.picker
        if self._date is not None:
            picker.calendar.set_date(self._date)
        picker.popup_below(self)

    def _in_range(self, date: QtCore.QDate) -> bool:
        if self._minimum is not None and date < self._minimum:
            return False
        return not (self._maximum is not None and date > self._maximum)

    def _apply(self, date: QtCore.QDate | None) -> None:
        if date != self._date:
            self._date = date
            self.date_changed.emit(date if date is not None else QtCore.QDate())

    def _commit_text(self) -> None:
        text = self.text.strip()
        if not text:
            self.set_error(False)
            self._apply(None)
            return
        date = date_picker.parse_date(text)
        if date is None:
            self.set_error(True, i18n.tr("invalid_date"))
            return
        if not self._in_range(date):
            self.set_error(True, i18n.tr("out_of_range"))
            return
        self.set_error(False)
        self.set_text(date_picker.format_input(date))
        self._apply(date)


class TimeField(text_field.OutlinedTextField):
    """时间文本框：可键入时间，也可点击尾部图标打开时间选择对话框。

    Args:
        label: 浮动标签。
        time: 初始时间。
        is_24_hour: 对话框与文本是否使用 24 小时制。
        supporting_text: 辅助文字。
        parent: 父控件。
    """

    time_changed = QtCore.Signal(QtCore.QTime)

    def __init__(
        self,
        label: str | None = None,
        time: QtCore.QTime | None = None,
        is_24_hour: bool = True,
        supporting_text: str = "hh:mm",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        time = time if time is not None and time.isValid() else None
        super().__init__(
            i18n.tr("time") if label is None else label,
            format_time(time, is_24_hour),
            placeholder="hh:mm",
            supporting_text=supporting_text,
            trailing_icon="schedule",
            parent=parent,
        )
        self._time = time
        self._is_24_hour = is_24_hour
        self.trailing_icon_clicked.connect(self.open_picker)
        self.editing_finished.connect(self._commit_text)

    @property
    def time(self) -> QtCore.QTime | None:
        """当前时间；文本无效时为 None。"""
        return self._time

    def set_time(self, time: QtCore.QTime | None) -> None:
        """设置时间并同步文本。"""
        time = time if time is not None and time.isValid() else None
        self.set_text(self._format(time))
        self.set_error(False)
        self._apply(time)

    def _format(self, time: QtCore.QTime | None) -> str:
        return format_time(time, self._is_24_hour)

    def open_picker(self) -> None:
        """打开时间选择对话框。"""
        dialog = time_picker.TimePickerDialog(
            self._time or QtCore.QTime.currentTime(),
            is_24_hour=self._is_24_hour,
            parent=self,
        )
        dialog.time_selected.connect(self.set_time)
        dialog.open()

    def _apply(self, time: QtCore.QTime | None) -> None:
        if time != self._time:
            self._time = time
            self.time_changed.emit(time if time is not None else QtCore.QTime())

    def _commit_text(self) -> None:
        text = self.text.strip()
        if not text:
            self.set_error(False)
            self._apply(None)
            return
        time = parse_time(text)
        if time is None:
            self.set_error(True, i18n.tr("invalid_time"))
            return
        self.set_error(False)
        self.set_text(self._format(time))
        self._apply(time)
