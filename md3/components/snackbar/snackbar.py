"""Snackbar 与队列宿主。

Snackbar 显示在宿主窗口底部（居中或起始侧对齐）：容器 ``inverse_surface``、
4dp 圆角、level 3 阴影、文字 ``inverse_on_surface``，可带一个
``inverse_primary`` 色的文字操作与关闭图标；操作文字较长时另起一行放在
右下角。同一窗口一次只显示一条，其余排队。指针悬停时暂停自动消失的计时，
向下或向侧面拖动可以把它划走。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
import dataclasses
import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import common as buttons
from md3.components.buttons import icon_button
from md3.core import animation
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

MIN_WIDTH = 344
MAX_WIDTH = 672
SINGLE_LINE_HEIGHT = 48
TWO_LINE_HEIGHT = 68
TEXT_TOP_PADDING = 14
ACTION_ROW_HEIGHT = 40
ACTION_ROW_BOTTOM = 8
PADDING_LEFT = 16
PADDING_RIGHT = 8
SIDE_MARGIN = 16
BOTTOM_MARGIN = 16
SHADOW_MARGIN = 12
TEXT_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
SHORT_DURATION_MS = 4000
LONG_DURATION_MS = 10000
INDEFINITE = 0
ELEVATION = elevation.Level.LEVEL_3
SLIDE_DISTANCE = 24
# 拖动超过此距离松手即划走。
SWIPE_THRESHOLD = 48
# 操作文字宽于此值时自动另起一行。
LONG_ACTION_WIDTH = 96


class SnackbarAlignment(enum.Enum):
    """Snackbar 在宿主底部的水平对齐方式。"""

    CENTER = "center"
    START = "start"


class DismissReason(enum.Enum):
    """Snackbar 消失的原因。"""

    TIMEOUT = "timeout"
    ACTION = "action"
    CLOSE = "close"
    SWIPE = "swipe"
    PROGRAMMATIC = "programmatic"


class _ActionButton(buttons.TextButton):
    """Snackbar 内使用 ``inverse_primary`` 着色的文字按钮。"""

    @override
    def _content_color(self) -> QtGui.QColor:
        return self.color("inverse_primary")


class _CloseButton(icon_button.IconButton):
    """Snackbar 内使用 ``inverse_on_surface`` 着色的关闭按钮。"""

    @override
    def _icon_color(self) -> QtGui.QColor:
        return self.color("inverse_on_surface")


@dataclasses.dataclass
class _Request:
    message: str
    action: str
    on_action: Callable[[], None] | None
    duration_ms: int
    closable: bool
    action_on_new_line: bool | None
    on_dismiss: Callable[[DismissReason], None] | None


class Snackbar(QtWidgets.QWidget):
    """单条 Snackbar 控件（通常由 ``SnackbarHost`` 创建）。

    Args:
        host: 宿主窗口。
        message: 文字，最多显示两行。
        action: 操作按钮文字，为空则无操作。
        closable: 是否显示关闭图标。
        action_on_new_line: 操作是否另起一行；None 时按操作文字长度自动决定。
        alignment: 水平对齐方式。
        bottom_margin: 容器底边到宿主底边的距离（dp）。
    """

    action_triggered = QtCore.Signal()
    dismissed = QtCore.Signal(object)
    hover_changed = QtCore.Signal(bool)

    def __init__(
        self,
        host: QtWidgets.QWidget,
        message: str,
        action: str = "",
        closable: bool = False,
        action_on_new_line: bool | None = None,
        alignment: SnackbarAlignment = SnackbarAlignment.CENTER,
        bottom_margin: int = BOTTOM_MARGIN,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._message = message
        self._alignment = alignment
        self._bottom_margin = bottom_margin
        self._opacity = animation.AnimatedFloat(self, 0.0, self.update)
        self._opacity.finished.connect(self._after_fade)
        self._closing = False
        self._reason = DismissReason.PROGRAMMATIC
        self._drag_origin: QtCore.QPointF | None = None
        self._drag_offset = QtCore.QPoint()
        self._action_button: _ActionButton | None = None
        if action:
            self._action_button = _ActionButton(action, parent=self)
            self._action_button.clicked.connect(self._on_action)
        self._close_button: _CloseButton | None = None
        if closable:
            self._close_button = _CloseButton(
                "close", tooltip=i18n.tr("close"), parent=self
            )
            self._close_button.clicked.connect(self._on_close)
        if action_on_new_line is None:
            action_on_new_line = (
                self._action_button is not None
                and self._action_button.sizeHint().width() > LONG_ACTION_WIDTH
            )
        self._action_on_new_line = bool(action_on_new_line) and (
            self._action_button is not None
        )
        self._lines = 1
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        theme_module.manager().theme_changed.connect(self._on_theme_changed)
        host.installEventFilter(self)
        self.hide()

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    # ---- 属性 -------------------------------------------------------------

    @property
    def message(self) -> str:
        """文字。"""
        return self._message

    @property
    def action_on_new_line(self) -> bool:
        """操作是否另起一行。"""
        return self._action_on_new_line

    @property
    def lines(self) -> int:
        """当前布局下文字占用的行数（1 或 2）。"""
        return self._lines

    @property
    def dismiss_reason(self) -> DismissReason:
        """最近一次关闭的原因。"""
        return self._reason

    @property
    def alignment(self) -> SnackbarAlignment:
        """水平对齐方式。"""
        return self._alignment

    # ---- 几何 -------------------------------------------------------------

    def container_rect(self) -> QtCore.QRectF:
        """容器矩形（阴影边距之内）。"""
        return QtCore.QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )

    def _controls_width(self) -> float:
        """操作与关闭按钮占据的宽度（同行布局时）。"""
        width = 0.0
        if self._action_button is not None:
            width += self._action_button.sizeHint().width() + 8
        if self._close_button is not None:
            width += self._close_button.sizeHint().width() + 8
        return width

    def _container_width(self) -> float:
        text_width = typography.text_width(self._message, TEXT_STYLE)
        controls = 0.0 if self._action_on_new_line else self._controls_width()
        wanted = PADDING_LEFT + text_width + PADDING_RIGHT + 8 + controls
        if self._action_on_new_line:
            wanted = max(wanted, PADDING_LEFT + self._controls_width() + 8)
        limit = self._host.width() - 2 * SIDE_MARGIN
        return max(min(MIN_WIDTH, limit), min(MAX_WIDTH, wanted, limit))

    def _text_width_for(self, container_width: float) -> float:
        controls = 0.0 if self._action_on_new_line else self._controls_width()
        return max(
            16.0, container_width - PADDING_LEFT - PADDING_RIGHT - 8 - controls
        )

    def _layout_metrics(self) -> tuple[float, int, float]:
        """返回 (容器宽度, 行数, 容器高度)。"""
        width = self._container_width()
        needs_two = "\n" in self._message or typography.text_width(
            self._message, TEXT_STYLE
        ) > self._text_width_for(width)
        lines = 2 if needs_two else 1
        line_height = typography.resolve_style(TEXT_STYLE).line_height
        if self._action_on_new_line:
            height = (
                TEXT_TOP_PADDING
                + lines * line_height
                + 4
                + ACTION_ROW_HEIGHT
                + ACTION_ROW_BOTTOM
            )
        else:
            height = TWO_LINE_HEIGHT if lines == 2 else SINGLE_LINE_HEIGHT
        return width, lines, height

    def preferred_size(self) -> QtCore.QSize:
        """按内容计算的尺寸（含阴影边距）。"""
        width, lines, height = self._layout_metrics()
        self._lines = lines
        return QtCore.QSize(
            int(width + 2 * SHADOW_MARGIN), int(height + 2 * SHADOW_MARGIN)
        )

    def _target_geometry(self) -> QtCore.QRect:
        size = self.preferred_size()
        host = self._host.rect()
        if self._alignment is SnackbarAlignment.START:
            if self._is_rtl():
                x = host.width() - size.width() - SIDE_MARGIN + SHADOW_MARGIN
            else:
                x = SIDE_MARGIN - SHADOW_MARGIN
        else:
            x = (host.width() - size.width()) // 2
        return QtCore.QRect(
            x,
            host.height() - size.height() - self._bottom_margin + SHADOW_MARGIN,
            size.width(),
            size.height(),
        )

    def _is_rtl(self) -> bool:
        return self.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft

    def _mirror(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        """RTL 下在容器内左右镜像矩形。"""
        if not self._is_rtl():
            return rect
        bounds = self.container_rect()
        return QtCore.QRectF(
            bounds.left() + bounds.right() - rect.right(),
            rect.top(),
            rect.width(),
            rect.height(),
        )

    def _text_alignment(self) -> QtCore.Qt.AlignmentFlag:
        horizontal = (
            QtCore.Qt.AlignmentFlag.AlignRight
            if self._is_rtl()
            else QtCore.Qt.AlignmentFlag.AlignLeft
        )
        return horizontal | QtCore.Qt.AlignmentFlag.AlignVCenter

    def _text_rect(self) -> QtCore.QRectF:
        rect = self.container_rect()
        line_height = typography.resolve_style(TEXT_STYLE).line_height
        if self._action_on_new_line:
            logical = QtCore.QRectF(
                rect.left() + PADDING_LEFT,
                rect.top() + TEXT_TOP_PADDING,
                rect.width() - PADDING_LEFT - PADDING_RIGHT - 8,
                self._lines * line_height,
            )
            return self._mirror(logical)
        right = rect.right() - PADDING_RIGHT - self._controls_width()
        if self._lines == 2:
            logical = QtCore.QRectF(
                rect.left() + PADDING_LEFT,
                rect.top() + TEXT_TOP_PADDING,
                max(0.0, right - rect.left() - PADDING_LEFT),
                2 * line_height,
            )
            return self._mirror(logical)
        return self._mirror(
            QtCore.QRectF(
                rect.left() + PADDING_LEFT,
                rect.top(),
                max(0.0, right - rect.left() - PADDING_LEFT),
                rect.height(),
            )
        )

    def _layout_controls(self) -> None:
        rect = self.container_rect()
        x = rect.right() - PADDING_RIGHT
        if self._action_on_new_line:
            center_y = rect.bottom() - ACTION_ROW_BOTTOM - ACTION_ROW_HEIGHT / 2
        else:
            center_y = rect.center().y()
        for button in (self._close_button, self._action_button):
            if button is None:
                continue
            size = button.sizeHint()
            x -= size.width()
            logical = QtCore.QRectF(
                x, center_y - size.height() / 2, size.width(), size.height()
            )
            button.setGeometry(self._mirror(logical).toRect())
            x -= 8

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_controls()

    # ---- 显示与关闭 -------------------------------------------------------

    def present(self) -> None:
        """从底部上滑并淡入。"""
        target = self._target_geometry()
        self._drag_offset = QtCore.QPoint()
        self.setGeometry(target.translated(0, SLIDE_DISTANCE))
        self.show()
        self.raise_()
        self._closing = False
        animation.run_property_animation(
            self,
            b"pos",
            target.topLeft(),
            motion.MEDIUM4,
            motion.EMPHASIZED_DECELERATE,
        )
        self._opacity.animate_to(
            1.0, motion.MEDIUM2, motion.STANDARD_DECELERATE
        )

    def dismiss(
        self, reason: DismissReason = DismissReason.PROGRAMMATIC
    ) -> None:
        """下滑淡出并发出 ``dismissed(reason)``。"""
        if self._closing:
            return
        self._closing = True
        self._reason = reason
        offset = QtCore.QPoint(0, SLIDE_DISTANCE)
        if (
            reason is DismissReason.SWIPE
            and self._drag_offset != QtCore.QPoint()
        ):
            # 沿拖动方向继续滑出。
            dx, dy = self._drag_offset.x(), self._drag_offset.y()
            scale = SLIDE_DISTANCE * 3 / max(1.0, float(abs(dx) + abs(dy)))
            offset = QtCore.QPoint(round(dx * scale), round(dy * scale))
        animation.run_property_animation(
            self,
            b"pos",
            self.pos() + offset,
            motion.SHORT4,
            motion.EMPHASIZED_ACCELERATE,
        )
        self._opacity.animate_to(0.0, motion.SHORT4, motion.STANDARD_ACCELERATE)

    def _after_fade(self) -> None:
        if self._closing and self._opacity.value <= 0.001:
            self.hide()
            self.dismissed.emit(self._reason)

    def _on_action(self) -> None:
        self.action_triggered.emit()
        self.dismiss(DismissReason.ACTION)

    def _on_close(self) -> None:
        self.dismiss(DismissReason.CLOSE)

    # ---- 事件 -------------------------------------------------------------

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if watched is self._host and event.type() == QtCore.QEvent.Type.Resize:
            if self.isVisible() and not self._closing:
                self.setGeometry(self._target_geometry())
        return super().eventFilter(watched, event)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self.hover_changed.emit(True)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self.hover_changed.emit(False)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and not self._closing
        ):
            self._drag_origin = event.globalPosition()
            self._drag_offset = QtCore.QPoint()
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is None:
            super().mouseMoveEvent(event)
            return
        delta = event.globalPosition() - self._drag_origin
        # 只允许向下或水平拖动，向上被抵消。
        self._drag_offset = QtCore.QPoint(
            round(delta.x()), max(0, round(delta.y()))
        )
        self.move(self._target_geometry().topLeft() + self._drag_offset)
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_origin is None:
            super().mouseReleaseEvent(event)
            return
        self._drag_origin = None
        distance = abs(self._drag_offset.x()) + self._drag_offset.y()
        if distance >= SWIPE_THRESHOLD:
            self.dismiss(DismissReason.SWIPE)
        else:
            self._drag_offset = QtCore.QPoint()
            animation.run_property_animation(
                self,
                b"pos",
                self._target_geometry().topLeft(),
                motion.MEDIUM2,
                motion.EMPHASIZED_DECELERATE,
            )
        event.accept()

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._opacity.value)
        rect = self.container_rect()
        shape = shape_tokens.SHAPE_EXTRA_SMALL
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            ELEVATION,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape),
            theme.color("inverse_surface"),
        )
        text_rect = self._text_rect()
        color = theme.color("inverse_on_surface")
        if self._lines == 2:
            typography.paint_multiline(
                painter,
                text_rect,
                self._message,
                TEXT_STYLE,
                color,
                max_lines=2,
                alignment=self._text_alignment(),
            )
        else:
            typography.paint_text(
                painter,
                text_rect,
                self._message,
                TEXT_STYLE,
                color,
                self._text_alignment(),
            )
        painter.end()


class SnackbarHost(QtCore.QObject):
    """管理某个窗口内 Snackbar 的显示队列。"""

    _hosts: dict[int, SnackbarHost] = {}

    def __init__(self, host: QtWidgets.QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._queue: deque[_Request] = deque()
        self._current: Snackbar | None = None
        self._request: _Request | None = None
        self._alignment = SnackbarAlignment.CENTER
        self._bottom_margin = BOTTOM_MARGIN
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._remaining_ms = 0
        self._elapsed = QtCore.QElapsedTimer()
        self._paused = False

    @classmethod
    def for_widget(cls, widget: QtWidgets.QWidget) -> SnackbarHost:
        """返回控件所属窗口的宿主，首次调用时创建。"""
        window = widget.window()
        key = id(window)
        host = cls._hosts.get(key)
        if host is None:
            host = cls(window)
            cls._hosts[key] = host
            window.destroyed.connect(lambda: cls._hosts.pop(key, None))
        return host

    @property
    def current(self) -> Snackbar | None:
        """当前显示的 Snackbar。"""
        return self._current

    @property
    def pending(self) -> int:
        """排队等待的条数。"""
        return len(self._queue)

    @property
    def alignment(self) -> SnackbarAlignment:
        """水平对齐方式。"""
        return self._alignment

    def set_alignment(self, alignment: SnackbarAlignment) -> None:
        """设置之后显示的 Snackbar 的对齐方式。"""
        self._alignment = alignment

    @property
    def bottom_margin(self) -> int:
        """容器到宿主底边的距离（dp）。"""
        return self._bottom_margin

    def set_bottom_margin(self, margin: int) -> None:
        """设置底部距离，例如为底部导航栏或 FAB 让出空间。"""
        self._bottom_margin = max(0, int(margin))

    @property
    def paused(self) -> bool:
        """自动消失计时是否因悬停而暂停。"""
        return self._paused

    def show(
        self,
        message: str,
        action: str = "",
        on_action: Callable[[], None] | None = None,
        duration_ms: int = SHORT_DURATION_MS,
        closable: bool = False,
        action_on_new_line: bool | None = None,
        on_dismiss: Callable[[DismissReason], None] | None = None,
    ) -> None:
        """排队显示一条 Snackbar。

        Args:
            message: 文字。
            action: 操作按钮文字。
            on_action: 点击操作时的回调。
            duration_ms: 显示时长；``INDEFINITE``（0）表示不自动消失。
            closable: 是否显示关闭图标。
            action_on_new_line: 操作是否另起一行；None 时自动决定。
            on_dismiss: 消失时的回调，参数为 ``DismissReason``。
        """
        self._queue.append(
            _Request(
                message,
                action,
                on_action,
                duration_ms,
                closable,
                action_on_new_line,
                on_dismiss,
            )
        )
        if self._current is None:
            self._show_next()

    def dismiss(self) -> None:
        """关闭当前 Snackbar。"""
        self._dismiss_current(DismissReason.PROGRAMMATIC)

    def clear(self) -> None:
        """清空队列并关闭当前 Snackbar。"""
        self._queue.clear()
        self._dismiss_current(DismissReason.PROGRAMMATIC)

    def _show_next(self) -> None:
        if not self._queue:
            return
        request = self._queue.popleft()
        snackbar = Snackbar(
            self._host,
            request.message,
            request.action,
            request.closable,
            request.action_on_new_line,
            self._alignment,
            self._bottom_margin,
        )
        if request.on_action is not None:
            snackbar.action_triggered.connect(request.on_action)
        snackbar.dismissed.connect(self._on_dismissed)
        snackbar.hover_changed.connect(self._on_hover)
        self._current = snackbar
        self._request = request
        snackbar.present()
        self._paused = False
        self._remaining_ms = request.duration_ms
        if request.duration_ms > 0:
            self._start_timer(request.duration_ms)

    def _start_timer(self, duration_ms: int) -> None:
        self._remaining_ms = duration_ms
        self._elapsed.start()
        self._timer.start(duration_ms)

    def _on_hover(self, hovered: bool) -> None:
        """悬停时暂停计时，离开后以剩余时间继续。"""
        if self._request is None or self._request.duration_ms <= 0:
            return
        if hovered and self._timer.isActive():
            self._timer.stop()
            self._remaining_ms = max(
                motion.LONG2, self._remaining_ms - self._elapsed.elapsed()
            )
            self._paused = True
        elif not hovered and self._paused:
            self._paused = False
            self._start_timer(self._remaining_ms)

    def _on_timeout(self) -> None:
        self._dismiss_current(DismissReason.TIMEOUT)

    def _dismiss_current(self, reason: DismissReason) -> None:
        self._timer.stop()
        self._paused = False
        if self._current is not None:
            self._current.dismiss(reason)

    def _on_dismissed(self, reason: object) -> None:
        request = self._request
        if self._current is not None:
            self._current.deleteLater()
            self._current = None
            self._request = None
        if request is not None and request.on_dismiss is not None:
            request.on_dismiss(
                reason
                if isinstance(reason, DismissReason)
                else DismissReason.PROGRAMMATIC
            )
        QtCore.QTimer.singleShot(motion.SHORT2, self, self._show_next)


def show(
    widget: QtWidgets.QWidget,
    message: str,
    action: str = "",
    on_action: Callable[[], None] | None = None,
    duration_ms: int = SHORT_DURATION_MS,
    closable: bool = False,
    action_on_new_line: bool | None = None,
    on_dismiss: Callable[[DismissReason], None] | None = None,
) -> SnackbarHost:
    """在控件所属窗口中显示 Snackbar 的便捷函数。"""
    host = SnackbarHost.for_widget(widget)
    host.show(
        message,
        action,
        on_action,
        duration_ms,
        closable,
        action_on_new_line,
        on_dismiss,
    )
    return host
