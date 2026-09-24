"""开关（Switch）。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.selection import base
from md3.core import animation
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import state as state_tokens

TRACK_WIDTH = 52.0
TRACK_HEIGHT = 32.0
TRACK_OUTLINE = 2.0
HANDLE_UNSELECTED = 16.0
HANDLE_WITH_ICON = 24.0
HANDLE_SELECTED = 24.0
HANDLE_PRESSED = 28.0
ICON_SIZE = 16.0


class Switch(base.SelectionControl):
    """开关。

    Args:
        text: 右侧标签文字。
        checked: 初始状态。
        show_icons: 为真时在把手内显示勾选/关闭图标。
        parent: 父控件。
    """

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        show_icons: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, checked, TRACK_WIDTH, TRACK_HEIGHT, parent)
        self._show_icons = show_icons
        self._check_icon = icons.Icon("check", ICON_SIZE, weight=600)
        self._close_icon = icons.Icon("close", ICON_SIZE, weight=600)
        # 按压时把手放大到 28dp 的过渡进度。
        self._press = animation.AnimatedFloat(self, 0.0, self.update)

    @property
    def show_icons(self) -> bool:
        """是否显示把手图标。"""
        return self._show_icons

    def set_show_icons(self, show: bool) -> None:
        """设置是否显示把手图标。"""
        self._show_icons = show
        self.update()

    # ---- 颜色 -------------------------------------------------------------

    def _track_color(self, selected: bool) -> QtGui.QColor:
        if not self.isEnabled():
            if selected:
                return theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTAINER_OPACITY,
                )
            return theme_module.with_alpha(
                self.color("surface_container_highest"),
                state_tokens.DISABLED_CONTAINER_OPACITY,
            )
        if selected:
            return self.color("primary")
        return self.color("surface_container_highest")

    def _outline_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        return self.color("outline")

    def _handle_color(self, selected: bool) -> QtGui.QColor:
        if not self.isEnabled():
            if selected:
                return self.color("surface")
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if selected:
            return self.color("on_primary")
        return self.color("outline")

    def _icon_color(self, selected: bool) -> QtGui.QColor:
        if not self.isEnabled():
            if selected:
                return theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTENT_OPACITY,
                )
            return theme_module.with_alpha(
                self.color("surface_container_highest"),
                state_tokens.DISABLED_CONTENT_OPACITY,
            )
        if selected:
            return self.color("on_primary_container")
        return self.color("surface_container_highest")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("primary" if self.checked else "on_surface")

    # ---- 几何 -------------------------------------------------------------

    def _handle_size(self) -> float:
        unselected = HANDLE_WITH_ICON if self._show_icons else HANDLE_UNSELECTED
        resting = unselected + (HANDLE_SELECTED - unselected) * self.progress
        return resting + (HANDLE_PRESSED - resting) * self._press.value

    def _handle_center(self, rect: QtCore.QRectF) -> QtCore.QPointF:
        start = rect.left() + TRACK_HEIGHT / 2
        end = rect.right() - TRACK_HEIGHT / 2
        if self.is_rtl():
            # RTL 下把手从右向左移动到选中位置。
            start, end = end, start
        return QtCore.QPointF(
            start + (end - start) * self.progress, rect.center().y()
        )

    @override
    def container_rect(self) -> QtCore.QRectF:
        # 状态层跟随把手移动。
        center = self._handle_center(self.control_rect())
        size = base.STATE_LAYER_SIZE
        return QtCore.QRectF(
            center.x() - size / 2, center.y() - size / 2, size, size
        )

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_control(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        progress = self.progress
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        radius = TRACK_HEIGHT / 2
        # 轨道：未选中色与选中色按进度混合。
        off = self._track_color(False)
        on = self._track_color(True)
        painter.setBrush(_mix(off, on, progress))
        painter.drawRoundedRect(rect, radius, radius)
        if progress < 1.0:
            outline = self._outline_color()
            outline.setAlphaF(outline.alphaF() * (1.0 - progress))
            pen = QtGui.QPen(outline, TRACK_OUTLINE)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            half = TRACK_OUTLINE / 2
            painter.drawRoundedRect(
                rect.adjusted(half, half, -half, -half),
                radius - half,
                radius - half,
            )
        # 把手。
        handle_size = self._handle_size()
        center = self._handle_center(rect)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(
            _mix(self._handle_color(False), self._handle_color(True), progress)
        )
        painter.drawEllipse(center, handle_size / 2, handle_size / 2)
        if self._show_icons:
            icon = self._check_icon if progress >= 0.5 else self._close_icon
            icon_rect = QtCore.QRectF(
                center.x() - ICON_SIZE / 2,
                center.y() - ICON_SIZE / 2,
                ICON_SIZE,
                ICON_SIZE,
            )
            icon.paint(painter, icon_rect, self._icon_color(progress >= 0.5))
        painter.restore()

    @override
    def start_press(self, position: QtCore.QPointF | None) -> None:
        super().start_press(position)
        if self.isEnabled():
            self._press.animate_to(1.0, motion.SHORT3, motion.STANDARD)

    @override
    def end_press(self, activate: bool) -> None:
        super().end_press(activate)
        self._press.animate_to(0.0, motion.SHORT3, motion.STANDARD)


def _mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
    t = max(0.0, min(1.0, t))
    return QtGui.QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )
