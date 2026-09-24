"""日期选择器（Date pickers）。

``CalendarView`` 是核心的月历控件（含年份选择，支持单日与日期范围两种
选择模式）；``DatePickerDialog`` / ``DateRangePickerDialog`` 为模态对话框
形式（可切换为键盘输入），``DockedDatePicker`` 为停靠在输入框下方的弹出
形式。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import common as buttons
from md3.components.buttons import icon_button
from md3.components.dialogs import dialog as dialog_module
from md3.components.text_fields import text_field
from md3.core import animation
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

CELL_SIZE = 40.0
# 7 × 40 + 6 × 4 + 2 × 12 = 328，与 M3 对话框宽度一致。
CELL_GAP = 4.0
GRID_COLUMNS = 7
GRID_ROWS = 6
NAV_HEIGHT = 56.0
WEEKDAY_HEIGHT = 40.0
HORIZONTAL_PADDING = 12.0
YEAR_CELL_WIDTH = 88.0
YEAR_CELL_HEIGHT = 36.0
YEAR_COLUMNS = 3
YEAR_RANGE = 100
DAY_STYLE = typography_tokens.TypeRole.BODY_LARGE
WEEKDAY_STYLE = typography_tokens.TypeRole.BODY_LARGE
YEAR_STYLE = typography_tokens.TypeRole.BODY_LARGE
HEADLINE_STYLE = typography_tokens.TypeRole.HEADLINE_LARGE
RANGE_HEADLINE_STYLE = typography_tokens.TypeRole.HEADLINE_SMALL
SUPPORTING_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
DIALOG_WIDTH = 328
SHADOW_MARGIN = 16
DATE_INPUT_FORMAT = "yyyy/MM/dd"
DATE_INPUT_HINT = "yyyy/mm/dd"
# 范围预览（只选了起点时随鼠标显示）的不透明度。
RANGE_PREVIEW_OPACITY = 0.5
_INPUT_FORMATS = (
    "yyyy/M/d",
    "yyyy-M-d",
    "yyyy.M.d",
    "yyyyMMdd",
    "yyyy年M月d日",
    "MMM d, yyyy",
    "d MMM yyyy",
)


class SelectionMode(enum.Enum):
    """月历的选择模式。"""

    SINGLE = "single"
    RANGE = "range"


def parse_date(text: str) -> QtCore.QDate | None:
    """解析用户输入的日期（支持 ``/`` ``-`` ``.`` 分隔、紧凑与中文格式）。"""
    text = text.strip()
    if not text:
        return None
    for pattern in _INPUT_FORMATS:
        date = QtCore.QDate.fromString(text, pattern)
        if date.isValid():
            return date
    return None


def format_input(date: QtCore.QDate | None) -> str:
    """把日期格式化为输入框中的文字。"""
    if date is None or not date.isValid():
        return ""
    return date.toString(DATE_INPUT_FORMAT)


class CalendarView(widget.MaterialWidget):
    """月历视图，支持切换月份、年份选择以及单日 / 范围选择。

    Args:
        date: 初始选中日期；None 表示未选择（显示当月）。
        minimum: 可选的最早日期。
        maximum: 可选的最晚日期。
        mode: 选择模式；范围模式下先点起点再点终点。
        parent: 父控件。
    """

    date_changed = QtCore.Signal(QtCore.QDate)
    range_changed = QtCore.Signal(QtCore.QDate, QtCore.QDate)
    month_changed = QtCore.Signal(int, int)

    def __init__(
        self,
        date: QtCore.QDate | None = None,
        minimum: QtCore.QDate | None = None,
        maximum: QtCore.QDate | None = None,
        mode: SelectionMode = SelectionMode.SINGLE,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        today = QtCore.QDate.currentDate()
        self._selected = date if date is not None and date.isValid() else None
        anchor = self._selected or today
        self._year = anchor.year()
        self._month = anchor.month()
        self._minimum = minimum
        self._maximum = maximum
        self._mode = mode
        self._range_start: QtCore.QDate | None = None
        self._range_end: QtCore.QDate | None = None
        self._year_mode = False
        self._hovered = -1
        self._year_scroll = 0.0
        # 翻月时日期网格的水平滑入偏移（px）。
        self._slide = animation.AnimatedFloat(self, 0.0, self.update)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._prev = icon_button.IconButton(
            "chevron_left", tooltip=i18n.tr("previous_month"), parent=self
        )
        self._next = icon_button.IconButton(
            "chevron_right", tooltip=i18n.tr("next_month"), parent=self
        )
        self._prev.clicked.connect(lambda: self.shift_month(-1))
        self._next.clicked.connect(lambda: self.shift_month(1))
        self._month_button = buttons.Button(
            "",
            variant=buttons.ButtonVariant.TEXT,
            trailing_icon="arrow_drop_down",
            parent=self,
        )
        self._month_button.clicked.connect(self.toggle_year_mode)
        self._refresh_month_button()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 状态 -------------------------------------------------------------

    @property
    def date(self) -> QtCore.QDate | None:
        """当前选中日期。"""
        return self._selected

    def set_date(self, date: QtCore.QDate | None) -> None:
        """设置选中日期并跳转到其所在月份。"""
        if date is not None and not date.isValid():
            date = None
        if date is not None and not self._is_selectable(date):
            return
        changed = date != self._selected
        self._selected = date
        if date is not None:
            self.show_month(date.year(), date.month())
        if changed:
            self.date_changed.emit(date if date is not None else QtCore.QDate())
        self.update()

    def set_range(
        self, minimum: QtCore.QDate | None, maximum: QtCore.QDate | None
    ) -> None:
        """设置可选日期范围。"""
        self._minimum = minimum
        self._maximum = maximum
        self.update()

    # ---- 范围选择 ---------------------------------------------------------

    @property
    def mode(self) -> SelectionMode:
        """选择模式。"""
        return self._mode

    def set_mode(self, mode: SelectionMode) -> None:
        """切换单日 / 范围选择模式。"""
        self._mode = mode
        self.update()

    @property
    def selected_range(self) -> tuple[QtCore.QDate | None, QtCore.QDate | None]:
        """范围模式下的 (起点, 终点)。"""
        return self._range_start, self._range_end

    def set_selected_range(
        self, start: QtCore.QDate | None, end: QtCore.QDate | None
    ) -> None:
        """设置日期范围（自动调整先后顺序），并跳转到起点所在月份。"""
        start = start if start is not None and start.isValid() else None
        end = end if end is not None and end.isValid() else None
        if start is not None and end is not None and end < start:
            start, end = end, start
        if start is not None and not self._is_selectable(start):
            return
        if end is not None and not self._is_selectable(end):
            return
        changed = (start, end) != (self._range_start, self._range_end)
        self._range_start, self._range_end = start, end
        if start is not None:
            self.show_month(start.year(), start.month())
        if changed:
            self.range_changed.emit(
                start if start is not None else QtCore.QDate(),
                end if end is not None else QtCore.QDate(),
            )
        self.update()

    def clear_range(self) -> None:
        """清除范围选择。"""
        self.set_selected_range(None, None)

    def _pick_date(self, date: QtCore.QDate) -> None:
        """点击或键盘选中一个日期：单日模式直接选中，范围模式依次取两端。"""
        if self._mode is SelectionMode.SINGLE:
            self.set_date(date)
            return
        if self._range_start is None or self._range_end is not None:
            self.set_selected_range(date, None)
        else:
            self.set_selected_range(self._range_start, date)

    def _range_state(self, date: QtCore.QDate) -> tuple[bool, bool]:
        """返回 (是否为端点, 是否位于范围内部)，含鼠标悬停时的预览。"""
        start, end = self._range_start, self._range_end
        if start is None:
            return False, False
        if end is None:
            hovered = self._hover_date()
            if hovered is None or hovered == start:
                return date == start, False
            end = hovered
            if end < start:
                start, end = end, start
        if date in (start, end):
            return True, False
        return False, start < date < end

    def _hover_date(self) -> QtCore.QDate | None:
        if self._hovered < 0 or self._year_mode:
            return None
        date = self.date_at_cell(self._hovered)
        if date is None or not self._is_selectable(date):
            return None
        return date

    def _previewing(self) -> bool:
        """是否正在预览尚未确定终点的范围。"""
        return (
            self._mode is SelectionMode.RANGE
            and self._range_start is not None
            and self._range_end is None
            and self._hover_date() is not None
        )

    @property
    def visible_month(self) -> tuple[int, int]:
        """当前显示的 (年, 月)。"""
        return self._year, self._month

    def show_month(self, year: int, month: int) -> None:
        """显示指定月份。"""
        if (year, month) != (self._year, self._month):
            self._year = year
            self._month = month
            self.month_changed.emit(year, month)
        self._refresh_month_button()
        self.update()

    def shift_month(self, delta: int) -> None:
        """前后翻页若干个月，日期网格沿翻页方向滑入。"""
        if delta == 0:
            return
        index = self._year * 12 + (self._month - 1) + delta
        self.show_month(index // 12, index % 12 + 1)
        direction = 1 if delta > 0 else -1
        self._slide.set(direction * self.grid_rect().width() * 0.5)
        self._slide.animate_to(
            0.0, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
        )

    @property
    def year_mode(self) -> bool:
        """是否处于年份选择模式。"""
        return self._year_mode

    def toggle_year_mode(self) -> None:
        """切换年份选择模式。"""
        self._year_mode = not self._year_mode
        self._hovered = -1
        self._prev.setVisible(not self._year_mode)
        self._next.setVisible(not self._year_mode)
        if self._year_mode:
            self._year_scroll = self._year_row_offset()
        self._refresh_month_button()
        self.update()

    def _refresh_month_button(self) -> None:
        locale = QtCore.QLocale()
        text = locale.toString(
            QtCore.QDate(self._year, self._month, 1),
            i18n.tr("month_year_format"),
        )
        self._month_button.set_text(text)
        self._month_button.set_trailing_icon(
            "arrow_drop_up" if self._year_mode else "arrow_drop_down"
        )
        self._layout_children()

    def _is_selectable(self, date: QtCore.QDate) -> bool:
        if self._minimum is not None and date < self._minimum:
            return False
        if self._maximum is not None and date > self._maximum:
            return False
        return True

    # ---- 几何 -------------------------------------------------------------

    def grid_rect(self) -> QtCore.QRectF:
        """日期网格区域。"""
        width = GRID_COLUMNS * CELL_SIZE + (GRID_COLUMNS - 1) * CELL_GAP
        return QtCore.QRectF(
            HORIZONTAL_PADDING,
            NAV_HEIGHT + WEEKDAY_HEIGHT,
            width,
            GRID_ROWS * CELL_SIZE + (GRID_ROWS - 1) * 0,
        )

    def cell_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个格子（0–41）的矩形。"""
        grid = self.grid_rect()
        row, column = divmod(index, GRID_COLUMNS)
        return QtCore.QRectF(
            grid.left() + column * (CELL_SIZE + CELL_GAP),
            grid.top() + row * CELL_SIZE,
            CELL_SIZE,
            CELL_SIZE,
        )

    @staticmethod
    def _first_day_of_week() -> int:
        """本地化的一周起始日（1=周一 … 7=周日）。"""
        return int(QtCore.QLocale().firstDayOfWeek().value)

    def _first_cell_offset(self) -> int:
        first = QtCore.QDate(self._year, self._month, 1)
        return (first.dayOfWeek() - self._first_day_of_week()) % 7

    def date_at_cell(self, index: int) -> QtCore.QDate | None:
        """格子对应的日期；不属于本月时返回 None。"""
        day = index - self._first_cell_offset() + 1
        if (
            day < 1
            or day > QtCore.QDate(self._year, self._month, 1).daysInMonth()
        ):
            return None
        return QtCore.QDate(self._year, self._month, day)

    def _cell_at(self, point: QtCore.QPointF) -> int:
        for index in range(GRID_COLUMNS * GRID_ROWS):
            if self.cell_rect(index).contains(point):
                return index
        return -1

    def _years(self) -> list[int]:
        current = QtCore.QDate.currentDate().year()
        return list(
            range(current - YEAR_RANGE // 2, current + YEAR_RANGE // 2 + 1)
        )

    def _year_row_offset(self) -> float:
        years = self._years()
        row = (
            years.index(self._year) // YEAR_COLUMNS
            if self._year in years
            else 0
        )
        visible_rows = int(self._year_area().height() // (YEAR_CELL_HEIGHT + 8))
        return max(0.0, (row - visible_rows // 2) * (YEAR_CELL_HEIGHT + 8))

    def _year_area(self) -> QtCore.QRectF:
        rect = QtCore.QRectF(self.rect())
        return QtCore.QRectF(
            HORIZONTAL_PADDING,
            NAV_HEIGHT,
            rect.width() - 2 * HORIZONTAL_PADDING,
            rect.height() - NAV_HEIGHT,
        )

    def _year_rect(self, index: int) -> QtCore.QRectF:
        area = self._year_area()
        row, column = divmod(index, YEAR_COLUMNS)
        spacing = (area.width() - YEAR_COLUMNS * YEAR_CELL_WIDTH) / (
            YEAR_COLUMNS - 1
        )
        return QtCore.QRectF(
            area.left() + column * (YEAR_CELL_WIDTH + spacing),
            area.top() + 8 + row * (YEAR_CELL_HEIGHT + 8) - self._year_scroll,
            YEAR_CELL_WIDTH,
            YEAR_CELL_HEIGHT,
        )

    def _year_at(self, point: QtCore.QPointF) -> int:
        if not self._year_area().contains(point):
            return -1
        for index in range(len(self._years())):
            if self._year_rect(index).contains(point):
                return index
        return -1

    def _layout_children(self) -> None:
        y = (NAV_HEIGHT - 48) / 2
        self._month_button.setGeometry(
            round(HORIZONTAL_PADDING - 4),
            round(y),
            self._month_button.sizeHint().width(),
            48,
        )
        width = self.width()
        self._next.setGeometry(
            round(width - HORIZONTAL_PADDING - 48 + 4), round(y), 48, 48
        )
        self._prev.setGeometry(
            round(width - HORIZONTAL_PADDING - 96 + 4), round(y), 48, 48
        )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    @override
    def sizeHint(self) -> QtCore.QSize:
        grid = self.grid_rect()
        return typography.size_hint(
            grid.width() + 2 * HORIZONTAL_PADDING, grid.bottom() + 8
        )

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        if self._year_mode:
            self._paint_years(painter)
        else:
            self._paint_weekdays(painter)
            self._paint_days(painter)

    def _paint_weekdays(self, painter: QtGui.QPainter) -> None:
        locale = QtCore.QLocale()
        first = self._first_day_of_week()
        color = self.color("on_surface")
        for column in range(GRID_COLUMNS):
            day = (first - 1 + column) % 7 + 1
            name = locale.dayName(day, QtCore.QLocale.FormatType.NarrowFormat)
            rect = self.cell_rect(column)
            rect.moveTop(NAV_HEIGHT)
            typography.paint_text(
                painter,
                rect,
                name,
                WEEKDAY_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )

    def _paint_days(self, painter: QtGui.QPainter) -> None:
        today = QtCore.QDate.currentDate()
        offset = self._slide.value
        grid = self.grid_rect()
        if abs(offset) > 0.01:
            painter.save()
            painter.setClipRect(grid.adjusted(-8, -8, 8, 8))
            painter.translate(offset, 0)
            painter.setOpacity(
                max(0.0, 1.0 - abs(offset) / max(1.0, grid.width() * 0.5))
            )
            self._paint_day_cells(painter, today)
            painter.restore()
            return
        self._paint_day_cells(painter, today)

    def _paint_range_band(self, painter: QtGui.QPainter) -> None:
        """在范围内的日期后方绘制 primary-container 色带，端点处收于圆心。"""
        band_color = self.color("primary_container")
        if self._previewing():
            band_color = theme_module.with_alpha(
                band_color, RANGE_PREVIEW_OPACITY
            )
        for row in range(GRID_ROWS):
            left = right = None
            for column in range(GRID_COLUMNS):
                index = row * GRID_COLUMNS + column
                date = self.date_at_cell(index)
                if date is None:
                    continue
                endpoint, inside = self._range_state(date)
                if not (endpoint or inside):
                    continue
                cell = self.cell_rect(index)
                # 端点只延伸到圆心，且需要另一端存在才有色带。
                start = (
                    cell.center().x()
                    if endpoint
                    else cell.left() - CELL_GAP / 2
                )
                end = (
                    cell.center().x()
                    if endpoint
                    else cell.right() + CELL_GAP / 2
                )
                left = start if left is None else min(left, start)
                right = end if right is None else max(right, end)
            if left is None or right is None or right - left < 1:
                continue
            row_rect = self.cell_rect(row * GRID_COLUMNS)
            painter.fillRect(
                QtCore.QRectF(left, row_rect.top(), right - left, CELL_SIZE),
                band_color,
            )

    def _paint_day_cells(
        self, painter: QtGui.QPainter, today: QtCore.QDate
    ) -> None:
        if self._mode is SelectionMode.RANGE and self._range_start is not None:
            self._paint_range_band(painter)
        for index in range(GRID_COLUMNS * GRID_ROWS):
            date = self.date_at_cell(index)
            if date is None:
                continue
            rect = self.cell_rect(index)
            circle = rect.adjusted(0, 0, 0, 0)
            selectable = self._is_selectable(date)
            if self._mode is SelectionMode.RANGE:
                selected, inside = self._range_state(date)
            else:
                selected = self._selected is not None and date == self._selected
                inside = False
            path = QtGui.QPainterPath()
            path.addEllipse(circle)
            if selected:
                shape_utils.fill_shape(painter, path, self.color("primary"))
                color = self.color("on_primary")
            elif inside:
                color = self.color("on_primary_container")
            elif date == today:
                pen = QtGui.QPen(self.color("primary"), 1)
                painter.save()
                painter.setPen(pen)
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(circle.adjusted(0.5, 0.5, -0.5, -0.5))
                painter.restore()
                color = self.color("primary")
            else:
                color = self.color("on_surface")
            if not selectable:
                color = theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTENT_OPACITY,
                )
            if index == self._hovered and selectable and not selected:
                layer = theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.HOVER_STATE_LAYER_OPACITY,
                )
                shape_utils.fill_shape(painter, path, layer)
            typography.paint_text(
                painter,
                rect,
                str(date.day()),
                DAY_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )

    def _paint_years(self, painter: QtGui.QPainter) -> None:
        painter.save()
        painter.setClipRect(self._year_area())
        current_year = QtCore.QDate.currentDate().year()
        for index, year in enumerate(self._years()):
            rect = self._year_rect(index)
            if (
                rect.bottom() < self._year_area().top()
                or rect.top() > self._year_area().bottom()
            ):
                continue
            path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL)
            if year == self._year:
                shape_utils.fill_shape(painter, path, self.color("primary"))
                color = self.color("on_primary")
            elif year == current_year:
                shape_utils.fill_shape(
                    painter, path, None, self.color("primary"), 1.0
                )
                color = self.color("primary")
            else:
                color = self.color("on_surface")
            if index == self._hovered and year != self._year:
                shape_utils.fill_shape(
                    painter,
                    path,
                    theme_module.with_alpha(
                        self.color("on_surface"),
                        state_tokens.HOVER_STATE_LAYER_OPACITY,
                    ),
                )
            typography.paint_text(
                painter,
                rect,
                str(year),
                YEAR_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        painter.restore()

    # ---- 事件 -------------------------------------------------------------

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hovered = (
            self._year_at(event.position())
            if self._year_mode
            else self._cell_at(event.position())
        )
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mouseReleaseEvent(event)
            return
        if self._year_mode:
            index = self._year_at(event.position())
            if index >= 0:
                self.show_month(self._years()[index], self._month)
                self.toggle_year_mode()
        else:
            index = self._cell_at(event.position())
            date = self.date_at_cell(index) if index >= 0 else None
            if date is not None and self._is_selectable(date):
                self._pick_date(date)
        event.accept()

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if self._year_mode:
            max_scroll = max(
                0.0,
                (len(self._years()) / YEAR_COLUMNS) * (YEAR_CELL_HEIGHT + 8)
                - self._year_area().height()
                + 16,
            )
            self._year_scroll = max(
                0.0,
                min(max_scroll, self._year_scroll - event.angleDelta().y() / 2),
            )
            self.update()
            event.accept()
            return
        self.shift_month(-1 if event.angleDelta().y() > 0 else 1)
        event.accept()

    def _keyboard_base(self) -> QtCore.QDate:
        """方向键移动的基准日期：单日模式为选中日，范围模式为待定端点。"""
        if self._mode is SelectionMode.RANGE:
            anchor = self._range_end or self._range_start
        else:
            anchor = self._selected
        return anchor or QtCore.QDate(self._year, self._month, 1)

    def _move_selection(self, delta: int) -> None:
        target = self._keyboard_base().addDays(delta)
        if not self._is_selectable(target):
            return
        if self._mode is SelectionMode.RANGE and self._range_start is not None:
            self.set_selected_range(self._range_start, target)
        else:
            self._pick_date(target)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        delta = {
            QtCore.Qt.Key.Key_Left: -1,
            QtCore.Qt.Key.Key_Right: 1,
            QtCore.Qt.Key.Key_Up: -7,
            QtCore.Qt.Key.Key_Down: 7,
        }.get(key)
        if delta is not None:
            self._move_selection(delta)
            event.accept()
            return
        if key == QtCore.Qt.Key.Key_PageUp:
            self.shift_month(-1)
        elif key == QtCore.Qt.Key.Key_PageDown:
            self.shift_month(1)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


def format_headline(date: QtCore.QDate | None) -> str:
    """把日期格式化为对话框头部的标题，例如 ``9月4日 周五``。"""
    if date is None or not date.isValid():
        return i18n.tr("select_date")
    locale = QtCore.QLocale()
    return locale.toString(date, i18n.tr("date_title_format"))


def format_range_headline(
    start: QtCore.QDate | None, end: QtCore.QDate | None
) -> str:
    """把日期范围格式化为标题，例如 ``9月4日 – 9月12日``。"""
    locale = QtCore.QLocale()

    def part(date: QtCore.QDate | None, placeholder: str) -> str:
        if date is None or not date.isValid():
            return placeholder
        return locale.toString(date, i18n.tr("date_short_format"))

    return (
        f"{part(start, i18n.tr('start_date'))} – "
        f"{part(end, i18n.tr('end_date'))}"
    )


class DateInputPanel(QtWidgets.QWidget):
    """对话框键盘输入模式中的日期文本框（一个或两个并排）。

    Args:
        labels: 每个文本框的标签。
        minimum: 最早日期。
        maximum: 最晚日期。
        parent: 父控件。
    """

    date_edited = QtCore.Signal(int, QtCore.QDate)

    def __init__(
        self,
        labels: list[str],
        minimum: QtCore.QDate | None = None,
        maximum: QtCore.QDate | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 8)
        layout.setSpacing(12)
        self._fields: list[text_field.OutlinedTextField] = []
        for index, label in enumerate(labels):
            field = text_field.OutlinedTextField(
                label,
                placeholder=DATE_INPUT_HINT,
                supporting_text=DATE_INPUT_HINT,
            )
            field.editing_finished.connect(lambda i=index: self._commit(i))
            layout.addWidget(field, 1)
            self._fields.append(field)

    @property
    def fields(self) -> list[text_field.OutlinedTextField]:
        """内部文本框。"""
        return list(self._fields)

    def set_date(self, index: int, date: QtCore.QDate | None) -> None:
        """把日期写入第 index 个文本框。"""
        self._fields[index].set_text(format_input(date))
        self._fields[index].set_error(False)

    def dates(self) -> list[QtCore.QDate | None]:
        """各文本框当前解析出的日期（无效为 None）。"""
        return [parse_date(field.text) for field in self._fields]

    def focus_first(self) -> None:
        """聚焦第一个文本框。"""
        if self._fields:
            self._fields[0].setFocus()

    def _in_range(self, date: QtCore.QDate) -> bool:
        if self._minimum is not None and date < self._minimum:
            return False
        return not (self._maximum is not None and date > self._maximum)

    def _commit(self, index: int) -> None:
        field = self._fields[index]
        text = field.text.strip()
        if not text:
            field.set_error(False)
            self.date_edited.emit(index, QtCore.QDate())
            return
        date = parse_date(text)
        if date is None:
            field.set_error(True, i18n.tr("invalid_date"))
            return
        if not self._in_range(date):
            field.set_error(True, i18n.tr("out_of_range"))
            return
        field.set_error(False)
        field.set_text(format_input(date))
        self.date_edited.emit(index, date)


class _PickerDialog(dialog_module._DialogBase):  # pylint: disable=protected-access
    """日期类对话框的公共外壳：说明文字、标题、切换输入方式、操作按钮。

    Args:
        title: 说明文字。
        headline: 初始标题。
        headline_style: 标题排版。
        calendar: 月历控件。
        input_panel: 键盘输入面板（默认隐藏）。
        parent: 父控件。
    """

    def __init__(
        self,
        title: str,
        headline: str,
        headline_style: typography_tokens.TypeRole,
        calendar: CalendarView,
        input_panel: DateInputPanel,
        parent: QtWidgets.QWidget | None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._input_mode = False
        self._calendar = calendar
        self._input = input_panel
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )
        self._panel = QtWidgets.QWidget(self)
        self._panel.setFixedWidth(DIALOG_WIDTH)
        root.addWidget(self._panel)
        layout = QtWidgets.QVBoxLayout(self._panel)
        layout.setContentsMargins(0, 16, 0, 12)
        layout.setSpacing(0)
        self._supporting = typography.Label(
            title, SUPPORTING_STYLE, "on_surface_variant"
        )
        self._supporting.setContentsMargins(24, 0, 24, 0)
        layout.addWidget(self._supporting)
        header = QtWidgets.QHBoxLayout()
        header.setContentsMargins(24, 12, 12, 12)
        self._headline = typography.Label(
            headline, headline_style, "on_surface"
        )
        header.addWidget(self._headline, 1)
        self._edit_button = icon_button.IconButton(
            "edit", tooltip=i18n.tr("keyboard_input")
        )
        self._edit_button.clicked.connect(self.toggle_input_mode)
        header.addWidget(self._edit_button)
        layout.addLayout(header)
        divider = QtWidgets.QFrame()
        divider.setFixedHeight(1)
        divider.setAutoFillBackground(True)
        self._divider = divider
        layout.addWidget(divider)
        layout.addWidget(calendar, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(input_panel)
        input_panel.hide()
        actions = QtWidgets.QHBoxLayout()
        actions.setContentsMargins(12, 0, 12, 0)
        actions.setSpacing(8)
        actions.addStretch()
        self._cancel = buttons.TextButton(i18n.tr("cancel"))
        self._cancel.clicked.connect(self.reject)
        self._confirm = buttons.TextButton(i18n.tr("confirm"))
        self._confirm.clicked.connect(self._confirm_selection)
        actions.addWidget(self._cancel)
        actions.addWidget(self._confirm)
        self._actions = actions
        layout.addLayout(actions)
        self._apply_divider_color()

    @property
    def calendar(self) -> CalendarView:
        """内部月历控件。"""
        return self._calendar

    @property
    def input_panel(self) -> DateInputPanel:
        """键盘输入面板。"""
        return self._input

    @property
    def input_mode(self) -> bool:
        """是否处于键盘输入模式。"""
        return self._input_mode

    def toggle_input_mode(self) -> None:
        """在月历与键盘输入之间切换。"""
        self.set_input_mode(not self._input_mode)

    def set_input_mode(self, enabled: bool) -> None:
        """设置是否使用键盘输入。"""
        if enabled == self._input_mode:
            return
        self._input_mode = enabled
        self._edit_button.set_icon(icon_for_mode(enabled))
        self._edit_button.setToolTip(
            i18n.tr("switch_to_calendar" if enabled else "keyboard_input")
        )
        self._calendar.setVisible(not enabled)
        self._input.setVisible(enabled)
        if enabled:
            self._sync_input_from_calendar()
            self._input.focus_first()
        self._panel.layout().activate()
        self._panel.adjustSize()
        self.layout().activate()
        self.adjustSize()
        self._center_on_host()

    def _sync_input_from_calendar(self) -> None:
        """把月历中的选择写入输入框，由子类实现。"""

    def _confirm_selection(self) -> None:
        """确认按钮的处理，由子类实现。"""

    def _apply_divider_color(self) -> None:
        palette = self._divider.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            theme_module.current().color("outline_variant"),
        )
        self._divider.setPalette(palette)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self._panel.geometry())
        shape = shape_tokens.SHAPE_EXTRA_LARGE
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            elevation.Level.LEVEL_3,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape),
            theme.color("surface_container_high"),
        )
        painter.end()
        self._apply_divider_color()


class DatePickerDialog(_PickerDialog):
    """模态日期选择对话框，可切换为键盘输入。

    Args:
        date: 初始日期。
        title: 头部说明文字。
        minimum: 最早日期。
        maximum: 最晚日期。
        parent: 父控件。
    """

    date_selected = QtCore.Signal(QtCore.QDate)

    def __init__(
        self,
        date: QtCore.QDate | None = None,
        title: str | None = None,
        minimum: QtCore.QDate | None = None,
        maximum: QtCore.QDate | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        calendar = CalendarView(date, minimum, maximum)
        panel = DateInputPanel([i18n.tr("date")], minimum, maximum)
        super().__init__(
            i18n.tr("select_date") if title is None else title,
            format_headline(date),
            HEADLINE_STYLE,
            calendar,
            panel,
            parent,
        )
        calendar.date_changed.connect(self._on_date_changed)
        panel.date_edited.connect(self._on_input_edited)

    @property
    def date(self) -> QtCore.QDate | None:
        """当前选中日期。"""
        return self._calendar.date

    def _on_date_changed(self, date: QtCore.QDate) -> None:
        self._headline.setText(
            format_headline(date if date.isValid() else None)
        )

    def _on_input_edited(self, index: int, date: QtCore.QDate) -> None:
        del index
        self._calendar.set_date(date if date.isValid() else None)

    @override
    def _sync_input_from_calendar(self) -> None:
        self._input.set_date(0, self._calendar.date)

    @override
    def _confirm_selection(self) -> None:
        if self._calendar.date is not None:
            self.date_selected.emit(self._calendar.date)
        self.accept()

    def _confirm_date(self) -> None:
        """确认当前日期（等同于点击"确定"）。"""
        self._confirm_selection()


class DateRangePickerDialog(_PickerDialog):
    """模态日期范围选择对话框。

    Args:
        start: 初始起点。
        end: 初始终点。
        title: 头部说明文字。
        minimum: 最早日期。
        maximum: 最晚日期。
        parent: 父控件。
    """

    range_selected = QtCore.Signal(QtCore.QDate, QtCore.QDate)

    def __init__(
        self,
        start: QtCore.QDate | None = None,
        end: QtCore.QDate | None = None,
        title: str | None = None,
        minimum: QtCore.QDate | None = None,
        maximum: QtCore.QDate | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        calendar = CalendarView(
            start, minimum, maximum, mode=SelectionMode.RANGE
        )
        panel = DateInputPanel(
            [i18n.tr("start_date"), i18n.tr("end_date")], minimum, maximum
        )
        super().__init__(
            i18n.tr("select_date_range") if title is None else title,
            format_range_headline(start, end),
            RANGE_HEADLINE_STYLE,
            calendar,
            panel,
            parent,
        )
        calendar.range_changed.connect(self._on_range_changed)
        panel.date_edited.connect(self._on_input_edited)
        calendar.set_selected_range(start, end)

    @property
    def selected_range(
        self,
    ) -> tuple[QtCore.QDate | None, QtCore.QDate | None]:
        """当前选中的 (起点, 终点)。"""
        return self._calendar.selected_range

    def _on_range_changed(self, start: QtCore.QDate, end: QtCore.QDate) -> None:
        self._headline.setText(
            format_range_headline(
                start if start.isValid() else None,
                end if end.isValid() else None,
            )
        )

    def _on_input_edited(self, index: int, date: QtCore.QDate) -> None:
        start, end = self._calendar.selected_range
        value = date if date.isValid() else None
        if index == 0:
            start = value
        else:
            end = value
        self._calendar.set_selected_range(start, end)

    @override
    def _sync_input_from_calendar(self) -> None:
        start, end = self._calendar.selected_range
        self._input.set_date(0, start)
        self._input.set_date(1, end)

    @override
    def _confirm_selection(self) -> None:
        start, end = self._calendar.selected_range
        if start is not None and end is not None:
            self.range_selected.emit(start, end)
        self.accept()


class DockedDatePicker(widget.MaterialWidget):
    """停靠在锚点下方的日期选择弹出面板。

    Args:
        date: 初始日期。
        minimum: 最早日期。
        maximum: 最晚日期。
        parent: 父控件（仅用于对象归属）。
    """

    date_selected = QtCore.Signal(QtCore.QDate)

    def __init__(
        self,
        date: QtCore.QDate | None = None,
        minimum: QtCore.QDate | None = None,
        maximum: QtCore.QDate | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Popup
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )
        layout.setSpacing(0)
        self._calendar = CalendarView(date, minimum, maximum)
        layout.addWidget(self._calendar)
        actions = QtWidgets.QHBoxLayout()
        actions.setContentsMargins(12, 0, 12, 8)
        actions.addStretch()
        self._cancel = buttons.TextButton(i18n.tr("cancel"))
        self._cancel.clicked.connect(self.hide)
        self._confirm = buttons.TextButton(i18n.tr("confirm"))
        self._confirm.clicked.connect(self._confirm_date)
        actions.addWidget(self._cancel)
        actions.addWidget(self._confirm)
        layout.addLayout(actions)

    @property
    def calendar(self) -> CalendarView:
        """内部月历控件。"""
        return self._calendar

    def popup_below(self, anchor: QtWidgets.QWidget, gap: int = 4) -> None:
        """在锚点控件下方弹出。"""
        self.adjustSize()
        position = anchor.mapToGlobal(QtCore.QPoint(0, anchor.height() + gap))
        self.move(position.x() - SHADOW_MARGIN, position.y() - SHADOW_MARGIN)
        self.show()

    def _confirm_date(self) -> None:
        if self._calendar.date is not None:
            self.date_selected.emit(self._calendar.date)
        self.hide()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )
        shape = shape_tokens.SHAPE_LARGE
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            elevation.Level.LEVEL_3,
            self.color("shadow"),
            self.devicePixelRatioF(),
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape),
            self.color("surface_container_high"),
        )


def icon_for_mode(input_mode: bool) -> icons.Icon:
    """输入/日历模式切换图标。"""
    return icons.Icon("calendar_today" if input_mode else "edit", 24)
