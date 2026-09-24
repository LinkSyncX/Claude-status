"""评分（Rating）。

一排星形（或任意 Material 图标）表示 0–``max_value`` 的评分：已评分部分为
``primary`` 填充图标，其余为 ``outline`` 色的轮廓图标；支持半星步长、悬停
预览、点击评分、方向键调整与只读模式。RTL 下从右向左计数。
"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens

DEFAULT_SIZE = 28.0
ICON_GAP = 4.0


class Rating(widget.InteractiveWidget):
    """评分。

    Args:
        value: 初始评分。
        max_value: 最高分（图标数量）。
        step: 评分步长，0.5 允许半星。
        read_only: 为真时只显示不可修改。
        icon: 图标名，默认 ``star``。
        size: 图标尺寸（dp）。
        parent: 父控件。
    """

    value_changed = QtCore.Signal(float)
    hover_changed = QtCore.Signal(float)

    def __init__(
        self,
        value: float = 0.0,
        max_value: int = 5,
        step: float = 1.0,
        read_only: bool = False,
        icon: icons.IconLike = "star",
        size: float = DEFAULT_SIZE,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._max = max(1, max_value)
        self._step = 0.5 if step <= 0.5 else 1.0
        self._value = self._snap(value)
        self._read_only = read_only
        self._icon = icons.coerce(icon, size)
        self._size = size
        self._hover: float | None = None
        self.set_outer_margin(0.0)
        self.setMouseTracking(True)
        self.ripple.set_enabled(False)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._apply_read_only()

    # ---- 取值 -------------------------------------------------------------

    def _snap(self, value: float) -> float:
        value = max(0.0, min(float(self._max), float(value)))
        return round(value / self._step) * self._step

    @property
    def value(self) -> float:
        """当前评分。"""
        return self._value

    def set_value(self, value: float) -> None:
        """设置评分，变化时发出 ``value_changed``。"""
        value = self._snap(value)
        if value != self._value:
            self._value = value
            self.value_changed.emit(value)
            accessibility.notify_value_changed(self, self.accessible_value())
            self.update()

    @property
    def max_value(self) -> int:
        """最高分。"""
        return self._max

    @property
    def step(self) -> float:
        """步长。"""
        return self._step

    @property
    def read_only(self) -> bool:
        """是否只读。"""
        return self._read_only

    def set_read_only(self, read_only: bool) -> None:
        """设置只读。"""
        self._read_only = read_only
        self._hover = None
        self._apply_read_only()
        self.update()

    def _apply_read_only(self) -> None:
        self.setFocusPolicy(
            QtCore.Qt.FocusPolicy.NoFocus
            if self._read_only
            else QtCore.Qt.FocusPolicy.StrongFocus
        )
        self.setCursor(
            QtCore.Qt.CursorShape.ArrowCursor
            if self._read_only
            else QtCore.Qt.CursorShape.PointingHandCursor
        )

    @override
    def is_interactive(self) -> bool:
        return self.isEnabled() and not self._read_only

    @property
    def hover_value(self) -> float | None:
        """悬停预览的评分，未悬停为 None。"""
        return self._hover

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Slider

    @override
    def accessible_value(self) -> str:
        return f"{self._value:g}/{self._max}"

    # ---- 几何 -------------------------------------------------------------

    def icon_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个图标的矩形。"""
        logical = QtCore.QRectF(
            index * (self._size + ICON_GAP),
            (self.height() - self._size) / 2,
            self._size,
            self._size,
        )
        return self.visual_rect(logical)

    def value_at(self, point: QtCore.QPointF) -> float:
        """位置对应的评分（按步长向上取整）。"""
        x = self.logical_point(point).x()
        if x <= 0:
            return self._step
        unit = self._size + ICON_GAP
        index = int(x // unit)
        offset = x - index * unit
        fraction = min(1.0, offset / self._size) if self._size else 1.0
        value = index + (
            self._step if fraction <= 0.5 and self._step < 1 else 1.0
        )
        return self._snap(min(float(self._max), max(self._step, value)))

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = self._max * self._size + (self._max - 1) * ICON_GAP
        return QtCore.QSize(math.ceil(width), math.ceil(self._size + 8))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def container_rect(self) -> QtCore.QRectF:
        return QtCore.QRectF(self.rect())

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_SMALL

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        if self._icon is None:
            return
        shown = self._hover if self._hover is not None else self._value
        enabled = self.isEnabled()
        active = self.color("primary")
        inactive = self.color("outline")
        if not enabled:
            active = theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            inactive = active
        filled = self._icon.with_fill(True)
        for index in range(self._max):
            rect = self.icon_rect(index)
            self._icon.paint(painter, rect, inactive)
            portion = max(0.0, min(1.0, shown - index))
            if portion <= 0:
                continue
            painter.save()
            if portion < 1.0:
                if self.is_rtl():
                    clip = QtCore.QRectF(
                        rect.right() - rect.width() * portion,
                        rect.top(),
                        rect.width() * portion,
                        rect.height(),
                    )
                else:
                    clip = QtCore.QRectF(
                        rect.left(),
                        rect.top(),
                        rect.width() * portion,
                        rect.height(),
                    )
                painter.setClipRect(clip)
            filled.paint(painter, rect, active)
            painter.restore()

    @override
    def paint_overlays(self, painter: QtGui.QPainter) -> None:
        # 评分没有整块状态层，只保留键盘焦点环。
        if self.focus_visible:
            super().paint_overlays(painter)

    # ---- 事件 -------------------------------------------------------------

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self.is_interactive():
            hover = self.value_at(event.position())
            if hover != self._hover:
                self._hover = hover
                self.hover_changed.emit(hover)
                self.update()
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        if self._hover is not None:
            self._hover = None
            self.update()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.is_interactive()
            and self.rect().contains(event.position().toPoint())
        ):
            value = self.value_at(event.position())
            # 再次点击当前评分则清零。
            self.set_value(0.0 if value == self._value else value)
        self._hover = None
        super().mouseReleaseEvent(event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if not self.is_interactive():
            super().keyPressEvent(event)
            return
        key = event.key()
        increase = (
            QtCore.Qt.Key.Key_Left if self.is_rtl() else QtCore.Qt.Key.Key_Right
        )
        decrease = (
            QtCore.Qt.Key.Key_Right if self.is_rtl() else QtCore.Qt.Key.Key_Left
        )
        if key in (increase, QtCore.Qt.Key.Key_Up):
            self.set_value(self._value + self._step)
        elif key in (decrease, QtCore.Qt.Key.Key_Down):
            self.set_value(self._value - self._step)
        elif key == QtCore.Qt.Key.Key_Home:
            self.set_value(0.0)
        elif key == QtCore.Qt.Key.Key_End:
            self.set_value(float(self._max))
        else:
            super().keyPressEvent(event)
            return
        event.accept()
