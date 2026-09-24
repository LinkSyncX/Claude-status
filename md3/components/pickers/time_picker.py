"""时间选择器（Time pickers）：表盘与键盘输入两种模式。"""

from __future__ import annotations

import enum
import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import common as buttons
from md3.components.buttons import icon_button
from md3.components.dialogs import dialog as dialog_module
from md3.core import animation
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

DIAL_SIZE = 256.0
DIAL_NUMERAL_RADIUS = 104.0
DIAL_INNER_RADIUS = 68.0
SELECTOR_SIZE = 48.0
CENTER_DOT = 8.0
HAND_WIDTH = 2.0
FIELD_WIDTH = 96.0
FIELD_HEIGHT = 80.0
INPUT_FIELD_HEIGHT = 72.0
PERIOD_WIDTH = 52.0
DISPLAY_STYLE = typography_tokens.TypeRole.DISPLAY_LARGE
NUMERAL_STYLE = typography_tokens.TypeRole.BODY_LARGE
PERIOD_STYLE = typography_tokens.TypeRole.TITLE_MEDIUM
LABEL_STYLE = typography_tokens.TypeRole.BODY_SMALL
SUPPORTING_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
PANEL_WIDTH = 328
SHADOW_MARGIN = 16


class TimePickerMode(enum.Enum):
    """选择器模式。"""

    DIAL = "dial"
    INPUT = "input"


class _Selection(enum.Enum):
    HOUR = "hour"
    MINUTE = "minute"


class TimePicker(widget.MaterialWidget):
    """时间选择器主体（不含对话框外壳）。

    Args:
        time: 初始时间。
        is_24_hour: 是否使用 24 小时制。
        mode: 初始模式。
        minute_step: 分钟步长（1–30，须能整除 60）；表盘与键盘调整都会
            吸附到该步长。
        parent: 父控件。
    """

    time_changed = QtCore.Signal(QtCore.QTime)
    mode_changed = QtCore.Signal(object)

    def __init__(
        self,
        time: QtCore.QTime | None = None,
        is_24_hour: bool = False,
        mode: TimePickerMode = TimePickerMode.DIAL,
        minute_step: int = 1,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._minute_step = self._validate_step(minute_step)
        self._time = self._snap(
            time if time is not None and time.isValid() else QtCore.QTime(12, 0)
        )
        self._is_24_hour = is_24_hour
        self._mode = mode
        self._selection = _Selection.HOUR
        self._dragging = False
        self._hovered_period = ""
        # 表针角度（度）与半径带过渡动画，沿最短路径旋转。
        self._hand_angle = animation.AnimatedFloat(self, 0.0, self.update)
        self._hand_radius = animation.AnimatedFloat(
            self, DIAL_NUMERAL_RADIUS, self.update
        )
        self._sync_hand(animate=False)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._hour_edit = QtWidgets.QLineEdit(self)
        self._minute_edit = QtWidgets.QLineEdit(self)
        for edit in (self._hour_edit, self._minute_edit):
            edit.setFrame(False)
            edit.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            edit.setMaxLength(2)
            edit.setValidator(QtGui.QIntValidator(0, 59, edit))
            edit.editingFinished.connect(self._apply_input)
            edit.installEventFilter(self)
        self._apply_editor_style()
        self._sync_mode_widgets()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 状态 -------------------------------------------------------------

    @property
    def time(self) -> QtCore.QTime:
        """当前时间。"""
        return self._time

    def set_time(self, time: QtCore.QTime) -> None:
        """设置时间（分钟吸附到步长）。"""
        if not time.isValid():
            return
        time = self._snap(time)
        if time == self._time:
            return
        self._time = time
        self._sync_inputs()
        self._sync_hand(animate=not self._dragging)
        self.time_changed.emit(self._time)
        self.update()

    @staticmethod
    def _validate_step(step: int) -> int:
        step = int(step)
        if step < 1 or step > 30 or 60 % step:
            raise ValueError("minute_step 必须在 1–30 之间且能整除 60")
        return step

    @property
    def minute_step(self) -> int:
        """分钟步长。"""
        return self._minute_step

    def set_minute_step(self, step: int) -> None:
        """设置分钟步长，并把当前时间吸附到新的步长。"""
        self._minute_step = self._validate_step(step)
        self.set_time(self._time)
        self.update()

    def _snap(self, time: QtCore.QTime) -> QtCore.QTime:
        """把分钟吸附到最近的步长（进位时小时随之变化）。"""
        step = self._minute_step
        if step == 1:
            return QtCore.QTime(time.hour(), time.minute())
        total = time.hour() * 60 + time.minute()
        snapped = round(total / step) * step
        return QtCore.QTime((snapped // 60) % 24, snapped % 60)

    def _hand_target(self) -> tuple[float, float]:
        """表针的目标角度（度，12 点为 0、顺时针）与半径。"""
        if self.selecting_hour:
            hour = self._time.hour()
            radius = (
                DIAL_INNER_RADIUS
                if self._is_24_hour and hour >= 12
                else DIAL_NUMERAL_RADIUS
            )
            return (hour % 12) * 30.0, radius
        return self._time.minute() * 6.0, DIAL_NUMERAL_RADIUS

    def _sync_hand(self, animate: bool) -> None:
        angle, radius = self._hand_target()
        current = self._hand_angle.value
        delta = ((angle - current + 180.0) % 360.0) - 180.0
        if animate:
            self._hand_angle.animate_to(
                current + delta, motion.MEDIUM2, motion.STANDARD
            )
            self._hand_radius.animate_to(
                radius, motion.MEDIUM2, motion.STANDARD
            )
        else:
            self._hand_angle.set(current + delta)
            self._hand_radius.set(radius)

    @property
    def is_24_hour(self) -> bool:
        """是否为 24 小时制。"""
        return self._is_24_hour

    def set_24_hour(self, enabled: bool) -> None:
        """切换 24 小时制。"""
        self._is_24_hour = enabled
        self._hour_edit.setValidator(
            QtGui.QIntValidator(
                0 if enabled else 1, 23 if enabled else 12, self._hour_edit
            )
        )
        self._sync_hand(animate=True)
        self.updateGeometry()
        self.update()

    @property
    def mode(self) -> TimePickerMode:
        """当前模式。"""
        return self._mode

    def set_mode(self, mode: TimePickerMode) -> None:
        """切换表盘 / 输入模式。"""
        if mode == self._mode:
            return
        self._mode = mode
        self._sync_mode_widgets()
        self.mode_changed.emit(mode)
        self.updateGeometry()
        self.update()

    def toggle_mode(self) -> None:
        """在两种模式间切换。"""
        self.set_mode(
            TimePickerMode.INPUT
            if self._mode is TimePickerMode.DIAL
            else TimePickerMode.DIAL
        )

    @property
    def selecting_hour(self) -> bool:
        """当前是否在选择小时（否则为分钟）。"""
        return self._selection is _Selection.HOUR

    def select_hour(self) -> None:
        """切换到小时选择。"""
        self._selection = _Selection.HOUR
        self._sync_hand(animate=True)
        self.update()

    def select_minute(self) -> None:
        """切换到分钟选择。"""
        self._selection = _Selection.MINUTE
        self._sync_hand(animate=True)
        self.update()

    @property
    def is_pm(self) -> bool:
        """当前是否为下午。"""
        return self._time.hour() >= 12

    def set_pm(self, pm: bool) -> None:
        """设置上午 / 下午（12 小时制）。"""
        hour = self._time.hour() % 12 + (12 if pm else 0)
        self.set_time(QtCore.QTime(hour, self._time.minute()))

    def _display_hour(self) -> int:
        if self._is_24_hour:
            return self._time.hour()
        return self._time.hour() % 12 or 12

    # ---- 输入模式 ---------------------------------------------------------

    def _apply_editor_style(self) -> None:
        theme = self.theme
        font = theme.font(typography_tokens.TypeRole.DISPLAY_MEDIUM)
        for edit in (self._hour_edit, self._minute_edit):
            edit.setFont(font)
            palette = edit.palette()
            palette.setColor(
                QtGui.QPalette.ColorRole.Text, theme.color("on_surface")
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.Base, theme_module.TRANSPARENT
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.Highlight, theme.color("primary")
            )
            palette.setColor(
                QtGui.QPalette.ColorRole.HighlightedText,
                theme.color("on_primary"),
            )
            edit.setPalette(palette)
            edit.setStyleSheet(
                "background: transparent; border: none; padding: 0px;"
            )
        self._sync_inputs()

    @override
    def on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self._apply_editor_style()

    def _sync_inputs(self) -> None:
        self._hour_edit.setText(f"{self._display_hour():02d}")
        self._minute_edit.setText(f"{self._time.minute():02d}")

    def _sync_mode_widgets(self) -> None:
        show = self._mode is TimePickerMode.INPUT
        self._hour_edit.setVisible(show)
        self._minute_edit.setVisible(show)
        self._layout_children()

    def _apply_input(self) -> None:
        try:
            hour = int(self._hour_edit.text() or 0)
            minute = int(self._minute_edit.text() or 0)
        except ValueError:
            self._sync_inputs()
            return
        minute = max(0, min(59, minute))
        if self._is_24_hour:
            hour = max(0, min(23, hour))
        else:
            hour = max(1, min(12, hour)) % 12 + (12 if self.is_pm else 0)
        self.set_time(QtCore.QTime(hour, minute))
        self._sync_inputs()

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if event.type() == QtCore.QEvent.Type.FocusIn:
            if watched is self._hour_edit:
                self.select_hour()
            elif watched is self._minute_edit:
                self.select_minute()
        return super().eventFilter(watched, event)

    # ---- 几何 -------------------------------------------------------------

    def _fields_top(self) -> float:
        return 0.0

    def _field_height(self) -> float:
        return (
            INPUT_FIELD_HEIGHT
            if self._mode is TimePickerMode.INPUT
            else FIELD_HEIGHT
        )

    def _fields_left(self) -> float:
        total = 2 * FIELD_WIDTH + 24
        if not self._is_24_hour:
            total += 12 + PERIOD_WIDTH
        return (self.width() - total) / 2

    def hour_rect(self) -> QtCore.QRectF:
        """小时显示框。"""
        return QtCore.QRectF(
            self._fields_left(),
            self._fields_top(),
            FIELD_WIDTH,
            self._field_height(),
        )

    def minute_rect(self) -> QtCore.QRectF:
        """分钟显示框。"""
        return QtCore.QRectF(
            self._fields_left() + FIELD_WIDTH + 24,
            self._fields_top(),
            FIELD_WIDTH,
            self._field_height(),
        )

    def period_rect(self) -> QtCore.QRectF:
        """上午/下午选择器矩形（24 小时制时为空）。"""
        if self._is_24_hour:
            return QtCore.QRectF()
        left = self._fields_left() + 2 * FIELD_WIDTH + 24 + 12
        return QtCore.QRectF(
            left, self._fields_top(), PERIOD_WIDTH, self._field_height()
        )

    def dial_rect(self) -> QtCore.QRectF:
        """表盘矩形。"""
        return QtCore.QRectF(
            (self.width() - DIAL_SIZE) / 2,
            FIELD_HEIGHT + 36,
            DIAL_SIZE,
            DIAL_SIZE,
        )

    def _layout_children(self) -> None:
        if self._mode is TimePickerMode.INPUT:
            hour = self.hour_rect().adjusted(4, 8, -4, -8)
            minute = self.minute_rect().adjusted(4, 8, -4, -8)
            self._hour_edit.setGeometry(hour.toRect())
            self._minute_edit.setGeometry(minute.toRect())

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    @override
    def sizeHint(self) -> QtCore.QSize:
        if self._mode is TimePickerMode.INPUT:
            return QtCore.QSize(PANEL_WIDTH - 48, int(INPUT_FIELD_HEIGHT + 24))
        return QtCore.QSize(
            PANEL_WIDTH - 48, int(FIELD_HEIGHT + 36 + DIAL_SIZE)
        )

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        self._paint_field(
            painter,
            self.hour_rect(),
            f"{self._display_hour():02d}",
            self.selecting_hour,
        )
        self._paint_field(
            painter,
            self.minute_rect(),
            f"{self._time.minute():02d}",
            not self.selecting_hour,
        )
        typography.paint_text(
            painter,
            QtCore.QRectF(
                self.hour_rect().right(), self._fields_top(), 24, FIELD_HEIGHT
            ),
            ":",
            DISPLAY_STYLE,
            self.color("on_surface"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        if not self._is_24_hour:
            self._paint_period(painter)
        if self._mode is TimePickerMode.INPUT:
            self._paint_input_labels(painter)
        else:
            self._paint_dial(painter)

    def _paint_field(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        text: str,
        active: bool,
    ) -> None:
        path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_SMALL)
        if self._mode is TimePickerMode.INPUT:
            if active:
                shape_utils.fill_shape(
                    painter, path, None, self.color("primary"), 2.0
                )
            else:
                shape_utils.fill_shape(
                    painter, path, None, self.color("outline"), 1.0
                )
            return
        if active:
            shape_utils.fill_shape(
                painter, path, self.color("primary_container")
            )
            color = self.color("on_primary_container")
        else:
            shape_utils.fill_shape(
                painter, path, self.color("surface_container_highest")
            )
            color = self.color("on_surface")
        typography.paint_text(
            painter,
            rect,
            text,
            DISPLAY_STYLE,
            color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    def _paint_input_labels(self, painter: QtGui.QPainter) -> None:
        color = self.color("on_surface_variant")
        for rect, label in (
            (self.hour_rect(), i18n.tr("hour")),
            (self.minute_rect(), i18n.tr("minute")),
        ):
            typography.paint_text(
                painter,
                QtCore.QRectF(rect.left(), rect.bottom() + 8, rect.width(), 16),
                label,
                LABEL_STYLE,
                color,
            )

    def _paint_period(self, painter: QtGui.QPainter) -> None:
        rect = self.period_rect()
        outline = self.color("outline")
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_SMALL),
            None,
            outline,
            1.0,
        )
        half = rect.height() / 2
        am_rect = QtCore.QRectF(rect.left(), rect.top(), rect.width(), half)
        pm_rect = QtCore.QRectF(
            rect.left(), rect.top() + half, rect.width(), half
        )
        painter.fillRect(
            QtCore.QRectF(
                rect.left(), rect.top() + half - 0.5, rect.width(), 1
            ),
            outline,
        )
        for period_rect, label, selected in (
            (am_rect, "AM", not self.is_pm),
            (pm_rect, "PM", self.is_pm),
        ):
            shape = (
                shape_tokens.Shape.top(shape_tokens.SMALL)
                if label == "AM"
                else shape_tokens.Shape.bottom(shape_tokens.SMALL)
            )
            inner = period_rect.adjusted(1, 1, -1, -1)
            if selected:
                shape_utils.fill_shape(
                    painter,
                    shape_utils.rounded_rect_path(inner, shape),
                    self.color("tertiary_container"),
                )
                color = self.color("on_tertiary_container")
            else:
                color = self.color("on_surface_variant")
            if self._hovered_period == label and not selected:
                shape_utils.fill_shape(
                    painter,
                    shape_utils.rounded_rect_path(inner, shape),
                    theme_module.with_alpha(
                        self.color("on_surface"),
                        state_tokens.HOVER_STATE_LAYER_OPACITY,
                    ),
                )
            typography.paint_text(
                painter,
                period_rect,
                label,
                PERIOD_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )

    def _dial_values(self) -> list[tuple[int, float]]:
        """表盘上的刻度值及其半径。"""
        if self.selecting_hour:
            values = [
                (hour, DIAL_NUMERAL_RADIUS) for hour in (12, *range(1, 12))
            ]
            if self._is_24_hour:
                values = [
                    (hour, DIAL_NUMERAL_RADIUS) for hour in (0, *range(1, 12))
                ]
                values += [
                    (hour, DIAL_INNER_RADIUS) for hour in (12, *range(13, 24))
                ]
            return values
        return [(minute, DIAL_NUMERAL_RADIUS) for minute in range(0, 60, 5)]

    def _angle_for(self, value: int) -> float:
        """值对应的角度（弧度，12 点方向为 0，顺时针）。"""
        if self.selecting_hour:
            return (value % 12) / 12 * 2 * math.pi
        return value / 60 * 2 * math.pi

    def _point_on_dial(self, angle: float, radius: float) -> QtCore.QPointF:
        center = self.dial_rect().center()
        return QtCore.QPointF(
            center.x() + radius * math.sin(angle),
            center.y() - radius * math.cos(angle),
        )

    def _paint_dial(self, painter: QtGui.QPainter) -> None:
        dial = self.dial_rect()
        center = dial.center()
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self.color("surface_container_highest"))
        painter.drawEllipse(dial)
        current = (
            self._time.hour() if self.selecting_hour else self._time.minute()
        )
        angle = math.radians(self._hand_angle.value)
        radius = self._hand_radius.value
        tip = self._point_on_dial(angle, radius)
        pen = QtGui.QPen(self.color("primary"), HAND_WIDTH)
        painter.setPen(pen)
        painter.drawLine(center, tip)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self.color("primary"))
        painter.drawEllipse(center, CENTER_DOT / 2, CENTER_DOT / 2)
        painter.drawEllipse(tip, SELECTOR_SIZE / 2, SELECTOR_SIZE / 2)
        if not self.selecting_hour and current % 5 != 0:
            painter.setBrush(self.color("on_primary"))
            painter.drawEllipse(tip, 3, 3)
        for value, value_radius in self._dial_values():
            point = self._point_on_dial(self._angle_for(value), value_radius)
            selected = value == current
            color = (
                self.color("on_primary")
                if selected
                else self.color("on_surface")
            )
            if (
                self.selecting_hour
                and self._is_24_hour
                and value_radius == DIAL_INNER_RADIUS
            ):
                if not selected:
                    color = self.color("on_surface_variant")
            label = (
                f"{value:02d}"
                if (not self.selecting_hour or self._is_24_hour)
                else str(value)
            )
            typography.paint_text(
                painter,
                QtCore.QRectF(point.x() - 24, point.y() - 12, 48, 24),
                label,
                NUMERAL_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        painter.restore()

    # ---- 交互 -------------------------------------------------------------

    def _value_at(self, point: QtCore.QPointF) -> int | None:
        dial = self.dial_rect()
        center = dial.center()
        dx = point.x() - center.x()
        dy = point.y() - center.y()
        distance = math.hypot(dx, dy)
        if distance > DIAL_SIZE / 2 + 8 or distance < 16:
            return None
        angle = math.atan2(dx, -dy)
        if angle < 0:
            angle += 2 * math.pi
        if self.selecting_hour:
            hour = round(angle / (2 * math.pi) * 12) % 12
            if self._is_24_hour:
                inner = distance < (DIAL_NUMERAL_RADIUS + DIAL_INNER_RADIUS) / 2
                return hour + 12 if inner else hour
            return hour
        return round(angle / (2 * math.pi) * 60) % 60

    def _apply_dial_value(self, value: int) -> None:
        if self.selecting_hour:
            if self._is_24_hour:
                hour = value
            else:
                hour = value % 12 + (12 if self.is_pm else 0)
            self.set_time(QtCore.QTime(hour, self._time.minute()))
        else:
            self.set_time(QtCore.QTime(self._time.hour(), value))

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position()
        if self.hour_rect().contains(position):
            self.select_hour()
        elif self.minute_rect().contains(position):
            self.select_minute()
        elif self.period_rect().contains(position):
            self.set_pm(position.y() > self.period_rect().center().y())
        elif self._mode is TimePickerMode.DIAL and self.dial_rect().contains(
            position
        ):
            self._dragging = True
            value = self._value_at(position)
            if value is not None:
                self._apply_dial_value(value)
        event.accept()

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            value = self._value_at(event.position())
            if value is not None:
                self._apply_dial_value(value)
        period = self.period_rect()
        hovered = ""
        if period.contains(event.position()):
            hovered = (
                "PM" if event.position().y() > period.center().y() else "AM"
            )
        if hovered != self._hovered_period:
            self._hovered_period = hovered
            self.update()
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            self._dragging = False
            if self.selecting_hour:
                self.select_minute()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if self.selecting_hour:
            step = 1
        else:
            step = self._minute_step if self._minute_step > 1 else 5
        if key in (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Right):
            self._nudge(step)
        elif key in (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Left):
            self._nudge(-step)
        elif key == QtCore.Qt.Key.Key_Tab:
            if self.selecting_hour:
                self.select_minute()
            else:
                self.select_hour()
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _nudge(self, delta: int) -> None:
        if self.selecting_hour:
            self.set_time(
                QtCore.QTime(
                    (self._time.hour() + delta) % 24, self._time.minute()
                )
            )
        else:
            self.set_time(
                QtCore.QTime(
                    self._time.hour(), (self._time.minute() + delta) % 60
                )
            )


class TimePickerDialog(dialog_module._DialogBase):  # pylint: disable=protected-access
    """模态时间选择对话框。

    Args:
        time: 初始时间。
        title: 头部说明文字。
        is_24_hour: 是否 24 小时制。
        minute_step: 分钟步长。
        parent: 父控件。
    """

    time_selected = QtCore.Signal(QtCore.QTime)

    def __init__(
        self,
        time: QtCore.QTime | None = None,
        title: str | None = None,
        is_24_hour: bool = False,
        minute_step: int = 1,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if title is None:
            title = i18n.tr("select_time")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )
        self._panel = QtWidgets.QWidget(self)
        self._panel.setFixedWidth(PANEL_WIDTH)
        root.addWidget(self._panel)
        layout = QtWidgets.QVBoxLayout(self._panel)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(20)
        layout.addWidget(
            typography.Label(title, SUPPORTING_STYLE, "on_surface_variant")
        )
        self._picker = TimePicker(time, is_24_hour, minute_step=minute_step)
        self._picker.mode_changed.connect(self._on_mode_changed)
        layout.addWidget(self._picker, 0, QtCore.Qt.AlignmentFlag.AlignHCenter)
        footer = QtWidgets.QHBoxLayout()
        footer.setContentsMargins(-12, 0, -12, 0)
        self._mode_button = icon_button.IconButton(
            "keyboard", tooltip=i18n.tr("switch_input_mode")
        )
        self._mode_button.clicked.connect(self._picker.toggle_mode)
        footer.addWidget(self._mode_button)
        footer.addStretch()
        self._cancel = buttons.TextButton(i18n.tr("cancel"))
        self._cancel.clicked.connect(self.reject)
        self._confirm = buttons.TextButton(i18n.tr("confirm"))
        self._confirm.clicked.connect(self._confirm_time)
        footer.addWidget(self._cancel)
        footer.addWidget(self._confirm)
        layout.addLayout(footer)

    @property
    def picker(self) -> TimePicker:
        """内部选择器。"""
        return self._picker

    @property
    def time(self) -> QtCore.QTime:
        """当前时间。"""
        return self._picker.time

    def _on_mode_changed(self, mode: TimePickerMode) -> None:
        self._mode_button.set_icon(
            "schedule" if mode is TimePickerMode.INPUT else "keyboard"
        )
        # 先让布局吸收新的尺寸提示，再收缩对话框。
        self._picker.setFixedSize(self._picker.sizeHint())
        self._panel.layout().activate()
        self._panel.adjustSize()
        self.layout().activate()
        self.adjustSize()
        self._center_on_host()

    def _confirm_time(self) -> None:
        self.time_selected.emit(self._picker.time)
        self.accept()

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
