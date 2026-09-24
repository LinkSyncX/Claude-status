"""滑块（Slider）与范围滑块（Range slider）。

采用 M3 Expressive 的样式：粗轨道、4dp 宽的竖条把手、把手两侧留 6dp
空隙、轨道末端的停止点，以及拖动时显示的数值指示器。

- ``size`` 选择 XS–XL 五种尺寸（轨道 16 / 24 / 40 / 56 / 96dp）。
- ``orientation`` 为 ``Qt.Orientation.Vertical`` 时轨道竖直，值自下而上
  增大，Up / Down 方向键同样有效。
- ``Slider(centered=True)`` 的活动轨道从范围中点延伸到当前值，适合
  平衡、偏移之类正负对称的取值。
- ``set_track_icons`` 在轨道两端内部放置图标（轨道 ≥ 24dp 时显示）。
"""

from __future__ import annotations

from collections.abc import Callable
import enum
import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import focus_ring
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

TRACK_HEIGHT = 16.0
TRACK_INNER_RADIUS = 2.0
HANDLE_WIDTH = 4.0
HANDLE_PRESSED_WIDTH = 2.0
HANDLE_HEIGHT = 44.0
HANDLE_GAP = 6.0
STOP_SIZE = 4.0
STOP_INSET = 6.0
INDICATOR_HEIGHT = 44.0
INDICATOR_PADDING = 16.0
INDICATOR_GAP = 4.0
INDICATOR_STYLE = typography_tokens.TypeRole.LABEL_LARGE
WIDGET_HEIGHT = HANDLE_HEIGHT
MIN_WIDTH = 120.0
TRACK_ICON_SIZE = 24.0
TRACK_ICON_INSET = 16.0
# 轨道至少这么粗才在内部显示图标。
TRACK_ICON_MIN_TRACK = 24.0

Formatter = Callable[[float], str]


class SliderSize(enum.Enum):
    """滑块尺寸，值为 (轨道粗细, 把手长度)。"""

    EXTRA_SMALL = (16.0, 44.0)
    SMALL = (24.0, 44.0)
    MEDIUM = (40.0, 52.0)
    LARGE = (56.0, 68.0)
    EXTRA_LARGE = (96.0, 108.0)

    @property
    def track(self) -> float:
        """轨道粗细（dp）。"""
        return self.value[0]

    @property
    def handle(self) -> float:
        """把手长度（dp）。"""
        return self.value[1]


def _default_formatter(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


class _ValueIndicator(QtWidgets.QWidget):
    """拖动时悬浮在把手上方的数值气泡（独立顶层窗口）。"""

    def __init__(self, owner: QtWidgets.QWidget) -> None:
        super().__init__(
            None,
            QtCore.Qt.WindowType.ToolTip
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint,
        )
        self._owner = owner
        self._text = ""
        self._closing = False
        self._fade = animation.AnimatedFloat(self, 0.0, self._apply_opacity)
        self._fade.finished.connect(self._after_fade)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

    def _apply_opacity(self) -> None:
        self.setWindowOpacity(self._fade.value)

    def _after_fade(self) -> None:
        if self._closing and self._fade.value <= 0.01:
            self.hide()

    def show_value(
        self,
        text: str,
        anchor_global: QtCore.QPoint,
        beside: bool = False,
    ) -> None:
        """显示文字并对齐到锚点，首次出现时淡入。

        Args:
            text: 显示的文字。
            anchor_global: 锚点（全局坐标）。
            beside: 为真时气泡放在锚点左侧并垂直居中（竖直滑块），否则
                气泡底部中心对齐锚点。
        """
        self._text = text
        width = (
            typography.text_width(text, INDICATOR_STYLE) + 2 * INDICATOR_PADDING
        )
        width = max(width, 28.0)
        size = typography.size_hint(width, INDICATOR_HEIGHT)
        self.resize(size)
        if beside:
            self.move(
                anchor_global.x() - size.width(),
                anchor_global.y() - size.height() // 2,
            )
        else:
            self.move(
                anchor_global.x() - size.width() // 2,
                anchor_global.y() - size.height(),
            )
        self._closing = False
        if not self.isVisible():
            self._fade.set(0.0)
            self.show()
            self._fade.animate_to(
                1.0, motion.SHORT3, motion.STANDARD_DECELERATE
            )
        self.update()

    def fade_out(self) -> None:
        """淡出后隐藏。"""
        if not self.isVisible():
            return
        self._closing = True
        self._fade.animate_to(0.0, motion.SHORT3, motion.STANDARD_ACCELERATE)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect())
        path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL)
        shape_utils.fill_shape(painter, path, theme.color("inverse_surface"))
        typography.paint_text(
            painter,
            rect,
            self._text,
            INDICATOR_STYLE,
            theme.color("inverse_on_surface"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        painter.end()


class _SliderBase(widget.InteractiveWidget):
    """单值与范围滑块的公共实现，把手数量由子类决定。

    所有几何都以"主轴位置"（水平滑块为 x，竖直滑块为 y）描述，竖直
    滑块的值自下而上增大。
    """

    def __init__(
        self,
        minimum: float,
        maximum: float,
        values: list[float],
        step: float | None,
        show_value_label: bool,
        parent: QtWidgets.QWidget | None,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        size: SliderSize = SliderSize.EXTRA_SMALL,
    ) -> None:
        super().__init__(parent)
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._step = float(step) if step else None
        self._values = [self._snap(v) for v in values]
        self._show_value_label = show_value_label
        self._formatter: Formatter = _default_formatter
        self._orientation = orientation
        self._size = size
        self._start_icon: icons.AnyIcon | None = None
        self._end_icon: icons.AnyIcon | None = None
        self._active = -1
        self._dragging = False
        self._indicator: _ValueIndicator | None = None
        # 拖动时把手由 4dp 收窄到 2dp 的过渡进度。
        self._press = animation.AnimatedFloat(self, 0.0, self.update)
        self.set_outer_margin(0.0)
        self.setMouseTracking(True)
        self._apply_size_policy()
        self.ripple.set_enabled(False)

    def _apply_size_policy(self) -> None:
        if self.horizontal:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        else:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )

    # ---- 方向与尺寸 -------------------------------------------------------

    @property
    def orientation(self) -> QtCore.Qt.Orientation:
        """方向。"""
        return self._orientation

    @property
    def horizontal(self) -> bool:
        """是否为水平滑块。"""
        return self._orientation == QtCore.Qt.Orientation.Horizontal

    def set_orientation(self, orientation: QtCore.Qt.Orientation) -> None:
        """切换方向。"""
        if orientation == self._orientation:
            return
        self._orientation = orientation
        self._apply_size_policy()
        self.updateGeometry()
        self.update()

    @property
    def size_variant(self) -> SliderSize:
        """尺寸。"""
        return self._size

    def set_size_variant(self, size: SliderSize) -> None:
        """设置尺寸。"""
        self._size = size
        self.updateGeometry()
        self.update()

    def track_thickness(self) -> float:
        """轨道粗细（dp）。"""
        return self._size.track

    def handle_length(self) -> float:
        """把手长度（dp）。"""
        return self._size.handle

    def set_track_icons(
        self, start: icons.IconLike = None, end: icons.IconLike = None
    ) -> None:
        """设置轨道两端内部的图标（轨道 ≥ 24dp 时显示）。"""
        self._start_icon = icons.coerce(start, TRACK_ICON_SIZE)
        self._end_icon = icons.coerce(end, TRACK_ICON_SIZE)
        self.update()

    # ---- 范围与步长 -------------------------------------------------------

    @property
    def minimum(self) -> float:
        """最小值。"""
        return self._minimum

    @property
    def maximum(self) -> float:
        """最大值。"""
        return self._maximum

    def set_range(self, minimum: float, maximum: float) -> None:
        """设置取值范围。"""
        if maximum <= minimum:
            raise ValueError("maximum 必须大于 minimum")
        self._minimum = float(minimum)
        self._maximum = float(maximum)
        self._set_values([self._snap(v) for v in self._values])
        self.update()

    @property
    def step(self) -> float | None:
        """离散步长，None 为连续。"""
        return self._step

    def set_step(self, step: float | None) -> None:
        """设置步长；非 None 时显示刻度点。"""
        self._step = float(step) if step else None
        self._set_values([self._snap(v) for v in self._values])
        self.update()

    def set_formatter(self, formatter: Formatter) -> None:
        """设置数值指示器的格式化函数。"""
        self._formatter = formatter

    @property
    def show_value_label(self) -> bool:
        """拖动时是否显示数值指示器。"""
        return self._show_value_label

    def set_show_value_label(self, show: bool) -> None:
        """设置是否显示数值指示器。"""
        self._show_value_label = show

    # ---- 值 ---------------------------------------------------------------

    def _snap(self, value: float) -> float:
        value = max(self._minimum, min(self._maximum, float(value)))
        if self._step:
            steps = round((value - self._minimum) / self._step)
            value = min(self._maximum, self._minimum + steps * self._step)
        return value

    def _set_values(self, values: list[float]) -> None:
        if values != self._values:
            self._values = values
            self._values_changed()
            accessibility.notify_value_changed(self, self.accessible_value())
            self.update()

    def _values_changed(self) -> None:
        """子类在此发出信号。"""

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Slider

    @override
    def accessible_value(self) -> str:
        return " – ".join(self._formatter(value) for value in self._values)

    def _keyboard_step(self, large: bool) -> float:
        span = self._maximum - self._minimum
        if self._step:
            return self._step * (10 if large else 1)
        return span * (0.1 if large else 0.01)

    # ---- 几何 -------------------------------------------------------------

    def track_rect(self) -> QtCore.QRectF:
        """整条轨道的矩形。"""
        rect = QtCore.QRectF(self.rect())
        inset = HANDLE_WIDTH / 2 + HANDLE_GAP
        thickness = self.track_thickness()
        if self.horizontal:
            return QtCore.QRectF(
                rect.left() + inset,
                rect.center().y() - thickness / 2,
                rect.width() - 2 * inset,
                thickness,
            )
        return QtCore.QRectF(
            rect.center().x() - thickness / 2,
            rect.top() + inset,
            thickness,
            rect.height() - 2 * inset,
        )

    def _track_start(self, track: QtCore.QRectF) -> float:
        """主轴上对应最小值的位置（水平 RTL 时在右端）。"""
        if self.horizontal:
            return track.right() if self.is_rtl() else track.left()
        return track.bottom()

    def _track_length(self, track: QtCore.QRectF) -> float:
        return track.width() if self.horizontal else track.height()

    def _axis(self, point: QtCore.QPointF) -> float:
        """取点在主轴上的坐标。"""
        return point.x() if self.horizontal else point.y()

    def _value_to_pos(self, value: float) -> float:
        track = self.track_rect()
        fraction = (value - self._minimum) / (self._maximum - self._minimum)
        length = self._track_length(track)
        if self.horizontal:
            if self.is_rtl():
                return track.right() - fraction * length
            return track.left() + fraction * length
        return track.bottom() - fraction * length

    def _pos_to_value(self, pos: float) -> float:
        track = self.track_rect()
        length = self._track_length(track)
        if length <= 0:
            return self._minimum
        if self.horizontal:
            if self.is_rtl():
                fraction = (track.right() - pos) / length
            else:
                fraction = (pos - track.left()) / length
        else:
            fraction = (track.bottom() - pos) / length
        fraction = max(0.0, min(1.0, fraction))
        return self._snap(
            self._minimum + fraction * (self._maximum - self._minimum)
        )

    def _value_to_x(self, value: float) -> float:
        """水平滑块中值对应的 x（保留给子类与测试）。"""
        return self._value_to_pos(value)

    def _x_to_value(self, x: float) -> float:
        return self._pos_to_value(x)

    def handle_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个把手的矩形。"""
        pos = self._value_to_pos(self._values[index])
        width = HANDLE_WIDTH
        if index == self._active:
            width += (HANDLE_PRESSED_WIDTH - HANDLE_WIDTH) * self._press.value
        length = self.handle_length()
        center = QtCore.QRectF(self.rect()).center()
        if self.horizontal:
            return QtCore.QRectF(
                pos - width / 2, center.y() - length / 2, width, length
            )
        return QtCore.QRectF(
            center.x() - length / 2, pos - width / 2, length, width
        )

    def _nearest_handle(self, pos: float) -> int:
        best = 0
        best_distance = math.inf
        for index, value in enumerate(self._values):
            distance = abs(self._value_to_pos(value) - pos)
            if distance < best_distance:
                best = index
                best_distance = distance
        return best

    @override
    def sizeHint(self) -> QtCore.QSize:
        if self.horizontal:
            return typography.size_hint(MIN_WIDTH, self.handle_length())
        return typography.size_hint(self.handle_length(), MIN_WIDTH)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        if self.horizontal:
            return typography.size_hint(48.0, self.handle_length())
        return typography.size_hint(self.handle_length(), 48.0)

    @override
    def container_rect(self) -> QtCore.QRectF:
        index = self._active if self._active >= 0 else 0
        if not self._values:
            return QtCore.QRectF()
        if self.horizontal:
            return self.handle_rect(index).adjusted(-8, -2, 8, 2)
        return self.handle_rect(index).adjusted(-2, -8, 2, 8)

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_FULL

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    # ---- 颜色 -------------------------------------------------------------

    def _active_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        return self.color("primary")

    def _inactive_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"),
                state_tokens.DISABLED_CONTAINER_OPACITY,
            )
        return self.color("secondary_container")

    def _active_stop_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("inverse_on_surface"), 0.66
            )
        return self.color("on_primary")

    def _inactive_stop_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        return self.color("on_secondary_container")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("primary")

    # ---- 绘制 -------------------------------------------------------------

    def _active_span(self) -> tuple[float, float]:
        """活动轨道覆盖的取值区间，由子类定义。"""
        return self._minimum, self._values[0]

    def _segment_rect(
        self, track: QtCore.QRectF, start: float, end: float
    ) -> QtCore.QRectF:
        """主轴上 [start, end] 区间对应的轨道段矩形。"""
        low, high = min(start, end), max(start, end)
        if self.horizontal:
            return QtCore.QRectF(low, track.top(), high - low, track.height())
        return QtCore.QRectF(track.left(), low, track.width(), high - low)

    def _segment_shape(self, first: bool, last: bool) -> shape_tokens.Shape:
        """轨道段形状：贴轨道两端的角为半圆，靠近把手的角为 2dp。"""
        outer = self.track_thickness() / 2
        inner = TRACK_INNER_RADIUS
        if self.horizontal:
            # first 在左端，last 在右端。
            return shape_tokens.Shape(
                outer if first else inner,
                outer if last else inner,
                outer if last else inner,
                outer if first else inner,
            )
        # 竖直：first 在顶端（最大值一侧），last 在底端。
        return shape_tokens.Shape(
            outer if first else inner,
            outer if first else inner,
            outer if last else inner,
            outer if last else inner,
        )

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        track = self.track_rect()
        if self._track_length(track) <= 0:
            return
        low, high = self._active_span()
        handle_positions = sorted(self._value_to_pos(v) for v in self._values)
        segments = self._segments(track, handle_positions)
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for start, end, first, last in segments:
            if end - start <= 0.5:
                continue
            value_at_mid = self._pos_to_value_raw((start + end) / 2, track)
            active = low <= value_at_mid <= high
            color = self._active_color() if active else self._inactive_color()
            rect = self._segment_rect(track, start, end)
            painter.setBrush(color)
            painter.drawPath(
                shape_utils.rounded_rect_path(
                    rect, self._segment_shape(first, last)
                )
            )
        self._paint_stops(painter, track, low, high)
        self._paint_track_icons(painter, track, low, high)
        painter.restore()

    def _pos_to_value_raw(self, pos: float, track: QtCore.QRectF) -> float:
        """不吸附步长的位置 → 值换算。"""
        length = self._track_length(track)
        if self.horizontal:
            if self.is_rtl():
                fraction = (track.right() - pos) / length
            else:
                fraction = (pos - track.left()) / length
        else:
            fraction = (track.bottom() - pos) / length
        return self._minimum + fraction * (self._maximum - self._minimum)

    def _segments(
        self, track: QtCore.QRectF, handle_positions: list[float]
    ) -> list[tuple[float, float, bool, bool]]:
        """按把手位置把轨道切成若干段：(start, end, 是否首段, 是否末段)。

        位置沿主轴递增（水平自左向右，竖直自上向下）。
        """
        start = track.left() if self.horizontal else track.top()
        end = track.right() if self.horizontal else track.bottom()
        bounds = [start]
        for pos in handle_positions:
            bounds.append(pos - HANDLE_WIDTH / 2 - HANDLE_GAP)
            bounds.append(pos + HANDLE_WIDTH / 2 + HANDLE_GAP)
        bounds.append(end)
        segments = []
        count = len(bounds) // 2
        for index in range(count):
            segments.append(
                (
                    bounds[2 * index],
                    bounds[2 * index + 1],
                    index == 0,
                    index == count - 1,
                )
            )
        return segments

    def _paint_stops(
        self,
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        low: float,
        high: float,
    ) -> None:
        radius = STOP_SIZE / 2
        if self._step:
            count = int(round((self._maximum - self._minimum) / self._step))
            positions = [
                self._minimum + i * self._step for i in range(count + 1)
            ]
        else:
            positions = [self._minimum, self._maximum]
        handle_positions = [self._value_to_pos(v) for v in self._values]
        start = self._track_start(track)
        far = track.right() if self.horizontal else track.top()
        lower, upper = min(start, far), max(start, far)
        for value in positions:
            pos = self._value_to_pos(value)
            if any(
                abs(pos - hp) < HANDLE_GAP + HANDLE_WIDTH
                for hp in handle_positions
            ):
                continue
            pos = min(max(pos, lower + STOP_INSET), upper - STOP_INSET)
            active = low <= value <= high
            painter.setBrush(
                self._active_stop_color()
                if active
                else self._inactive_stop_color()
            )
            center = (
                QtCore.QPointF(pos, track.center().y())
                if self.horizontal
                else QtCore.QPointF(track.center().x(), pos)
            )
            painter.drawEllipse(center, radius, radius)

    def _paint_track_icons(
        self,
        painter: QtGui.QPainter,
        track: QtCore.QRectF,
        low: float,
        high: float,
    ) -> None:
        if self.track_thickness() < TRACK_ICON_MIN_TRACK:
            return
        for icon, at_start in (
            (self._start_icon, True),
            (self._end_icon, False),
        ):
            if icon is None:
                continue
            value = self._minimum if at_start else self._maximum
            active = low <= value <= high
            color = (
                self._active_stop_color()
                if active
                else self._inactive_stop_color()
            )
            if self.horizontal:
                on_left = at_start != self.is_rtl()
                x = (
                    track.left() + TRACK_ICON_INSET
                    if on_left
                    else track.right() - TRACK_ICON_INSET - TRACK_ICON_SIZE
                )
                rect = QtCore.QRectF(
                    x,
                    track.center().y() - TRACK_ICON_SIZE / 2,
                    TRACK_ICON_SIZE,
                    TRACK_ICON_SIZE,
                )
            else:
                y = (
                    track.bottom() - TRACK_ICON_INSET - TRACK_ICON_SIZE
                    if at_start
                    else track.top() + TRACK_ICON_INSET
                )
                rect = QtCore.QRectF(
                    track.center().x() - TRACK_ICON_SIZE / 2,
                    y,
                    TRACK_ICON_SIZE,
                    TRACK_ICON_SIZE,
                )
            handle_positions = [self._value_to_pos(v) for v in self._values]
            icon_pos = self._axis(rect.center())
            if any(
                abs(icon_pos - hp) < TRACK_ICON_SIZE for hp in handle_positions
            ):
                continue
            icon.paint(painter, rect, color)

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self._active_color())
        for index in range(len(self._values)):
            rect = self.handle_rect(index)
            painter.drawPath(
                shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL)
            )
        painter.restore()

    @override
    def paint_overlays(self, painter: QtGui.QPainter) -> None:
        # 新版滑块没有把手状态层，仅保留键盘焦点环。
        if self.focus_visible and self._values:
            index = self._active if self._active >= 0 else 0
            rect = self.handle_rect(index).adjusted(-2, -2, 2, 2)
            focus_ring.paint_focus_ring(
                painter,
                rect,
                shape_tokens.SHAPE_FULL,
                self.focus_ring_color(),
                max_extent=0.0,
            )

    # ---- 交互 -------------------------------------------------------------

    def _indicator_widget(self) -> _ValueIndicator:
        if self._indicator is None:
            self._indicator = _ValueIndicator(self)
        return self._indicator

    def _show_indicator(self, index: int) -> None:
        if not self._show_value_label or index < 0:
            return
        rect = self.handle_rect(index)
        if self.horizontal:
            anchor = self.mapToGlobal(
                QtCore.QPoint(
                    round(rect.center().x()), round(rect.top() - INDICATOR_GAP)
                )
            )
        else:
            anchor = self.mapToGlobal(
                QtCore.QPoint(
                    round(rect.left() - INDICATOR_GAP), round(rect.center().y())
                )
            )
        self._indicator_widget().show_value(
            self._formatter(self._values[index]),
            anchor,
            beside=not self.horizontal,
        )

    def _hide_indicator(self) -> None:
        if self._indicator is not None:
            self._indicator.fade_out()

    def _move_active_to(self, pos: float) -> None:
        if self._active < 0:
            return
        values = list(self._values)
        values[self._active] = self._pos_to_value(pos)
        self._set_values(self._constrain(values, self._active))
        self._show_indicator(self._active)

    def _constrain(self, values: list[float], moved: int) -> list[float]:
        """子类可覆写以保持把手顺序。"""
        del moved
        return values

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() != QtCore.Qt.MouseButton.LeftButton
            or not self.is_interactive()
        ):
            super().mousePressEvent(event)
            return
        pos = self._axis(event.position())
        self._active = self._nearest_handle(pos)
        self._dragging = True
        self.state_layer.set_dragged(True)
        self._press.animate_to(1.0, motion.SHORT3, motion.STANDARD)
        self._move_active_to(pos)
        self.pressed.emit()
        event.accept()

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._dragging:
            self._move_active_to(self._axis(event.position()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self._dragging
        ):
            self._dragging = False
            self.state_layer.set_dragged(False)
            self._press.animate_to(0.0, motion.SHORT3, motion.STANDARD)
            self._hide_indicator()
            self.released.emit()
            self._released()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self.is_interactive() or not self._values:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y() or event.angleDelta().x()
        if not delta:
            super().wheelEvent(event)
            return
        self._active = max(self._active, 0)
        step = self._keyboard_step(False) * (1 if delta > 0 else -1)
        values = list(self._values)
        values[self._active] = self._snap(values[self._active] + step)
        self._set_values(self._constrain(values, self._active))
        self._released()
        event.accept()

    def _released(self) -> None:
        """子类在此发出释放信号。"""

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if not self._values:
            super().keyPressEvent(event)
            return
        self._active = max(self._active, 0)
        key = event.key()
        large = bool(
            event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
        )
        value = self._values[self._active]
        # 水平 RTL 滑块中向右是减小的方向。
        mirrored = self.horizontal and self.is_rtl()
        increase = (
            QtCore.Qt.Key.Key_Left if mirrored else QtCore.Qt.Key.Key_Right
        )
        decrease = (
            QtCore.Qt.Key.Key_Right if mirrored else QtCore.Qt.Key.Key_Left
        )
        if key in (increase, QtCore.Qt.Key.Key_Up):
            value += self._keyboard_step(large)
        elif key in (decrease, QtCore.Qt.Key.Key_Down):
            value -= self._keyboard_step(large)
        elif key == QtCore.Qt.Key.Key_PageUp:
            value += self._keyboard_step(True)
        elif key == QtCore.Qt.Key.Key_PageDown:
            value -= self._keyboard_step(True)
        elif key == QtCore.Qt.Key.Key_Home:
            value = self._minimum
        elif key == QtCore.Qt.Key.Key_End:
            value = self._maximum
        else:
            super().keyPressEvent(event)
            return
        values = list(self._values)
        values[self._active] = self._snap(value)
        self._set_values(self._constrain(values, self._active))
        self._released()
        event.accept()

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(event)
        self._hide_indicator()

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self._hide_indicator()


class Slider(_SliderBase):
    """单值滑块。

    Args:
        minimum: 最小值。
        maximum: 最大值。
        value: 初始值。
        step: 步长；None 为连续滑块。
        show_value_label: 拖动时是否显示数值指示器。
        orientation: 水平或竖直。
        size: 尺寸（轨道粗细与把手长度）。
        centered: 为真时活动轨道从范围中点延伸到当前值。
        parent: 父控件。
    """

    value_changed = QtCore.Signal(float)
    slider_released = QtCore.Signal(float)

    def __init__(
        self,
        minimum: float = 0.0,
        maximum: float = 100.0,
        value: float = 0.0,
        step: float | None = None,
        show_value_label: bool = True,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        size: SliderSize = SliderSize.EXTRA_SMALL,
        centered: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            minimum,
            maximum,
            [value],
            step,
            show_value_label,
            parent,
            orientation,
            size,
        )
        self._centered = centered

    @property
    def value(self) -> float:
        """当前值。"""
        return self._values[0]

    def set_value(self, value: float) -> None:
        """设置当前值（自动吸附到步长并限制范围）。"""
        self._set_values([self._snap(value)])

    @property
    def centered(self) -> bool:
        """活动轨道是否从范围中点开始。"""
        return self._centered

    def set_centered(self, centered: bool) -> None:
        """设置是否为居中滑块。"""
        self._centered = centered
        self.update()

    def handle_x(self) -> float:
        """把手中心在主轴上的位置。"""
        return self._value_to_pos(self._values[0])

    @override
    def _active_span(self) -> tuple[float, float]:
        if self._centered:
            middle = (self._minimum + self._maximum) / 2
            value = self._values[0]
            return min(middle, value), max(middle, value)
        return self._minimum, self._values[0]

    @override
    def _values_changed(self) -> None:
        self.value_changed.emit(self._values[0])

    @override
    def _released(self) -> None:
        self.slider_released.emit(self._values[0])


class RangeSlider(_SliderBase):
    """双把手范围滑块。

    Args:
        minimum: 最小值。
        maximum: 最大值。
        low: 起始值。
        high: 结束值。
        step: 步长；None 为连续。
        show_value_label: 拖动时是否显示数值指示器。
        orientation: 水平或竖直。
        size: 尺寸。
        parent: 父控件。
    """

    range_changed = QtCore.Signal(float, float)
    slider_released = QtCore.Signal(float, float)

    def __init__(
        self,
        minimum: float = 0.0,
        maximum: float = 100.0,
        low: float = 20.0,
        high: float = 80.0,
        step: float | None = None,
        show_value_label: bool = True,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        size: SliderSize = SliderSize.EXTRA_SMALL,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            minimum,
            maximum,
            [min(low, high), max(low, high)],
            step,
            show_value_label,
            parent,
            orientation,
            size,
        )

    @property
    def low(self) -> float:
        """起始值。"""
        return self._values[0]

    @property
    def high(self) -> float:
        """结束值。"""
        return self._values[1]

    def set_values(self, low: float, high: float) -> None:
        """设置区间。"""
        low, high = self._snap(low), self._snap(high)
        self._set_values([min(low, high), max(low, high)])

    @override
    def _active_span(self) -> tuple[float, float]:
        return self._values[0], self._values[1]

    @override
    def _constrain(self, values: list[float], moved: int) -> list[float]:
        if moved == 0:
            values[0] = min(values[0], values[1])
        else:
            values[1] = max(values[1], values[0])
        return values

    @override
    def _values_changed(self) -> None:
        self.range_changed.emit(self._values[0], self._values[1])

    @override
    def _released(self) -> None:
        self.slider_released.emit(self._values[0], self._values[1])

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        # Tab 在两个把手之间切换焦点。
        if event.key() == QtCore.Qt.Key.Key_Tab and self._active == 0:
            self._active = 1
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)
