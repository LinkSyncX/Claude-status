"""复选框（Checkbox），支持三态与错误态。"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.selection import base
from md3.theme import theme as theme_module
from md3.tokens import state as state_tokens

BOX_SIZE = 18.0
BOX_RADIUS = 2.0
OUTLINE_WIDTH = 2.0
MARK_WIDTH = 2.0


class CheckState(enum.Enum):
    """复选框状态。"""

    UNCHECKED = "unchecked"
    CHECKED = "checked"
    INDETERMINATE = "indeterminate"


class Checkbox(base.SelectionControl):
    """复选框。

    Args:
        text: 右侧标签文字。
        checked: 初始是否选中。
        tristate: 为真时点击在 未选中 → 选中 → 不确定 之间循环。
        error: 是否显示错误态。
        parent: 父控件。
    """

    state_changed = QtCore.Signal(object)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        tristate: bool = False,
        error: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, checked, BOX_SIZE, BOX_SIZE, parent)
        self._tristate = tristate
        self._error = error
        self._indeterminate = False

    # ---- 状态 -------------------------------------------------------------

    @property
    def state(self) -> CheckState:
        """当前三态。"""
        if self._indeterminate:
            return CheckState.INDETERMINATE
        return CheckState.CHECKED if self.checked else CheckState.UNCHECKED

    def set_state(self, state: CheckState) -> None:
        """设置三态。"""
        previous = self.state
        if state is CheckState.INDETERMINATE:
            self._indeterminate = True
            self.set_checked(True)
        else:
            self._indeterminate = False
            self.set_checked(state is CheckState.CHECKED)
        if self.state != previous:
            self.state_changed.emit(self.state)
            self.update()

    @override
    def set_checked(self, checked: bool) -> None:
        was_indeterminate = self._indeterminate
        if not checked:
            self._indeterminate = False
        super().set_checked(checked)
        if was_indeterminate != self._indeterminate:
            self.update()

    @property
    def indeterminate(self) -> bool:
        """是否处于不确定态。"""
        return self._indeterminate

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        state.checkStateMixed = self._indeterminate
        state.invalid = self._error

    @property
    def tristate(self) -> bool:
        """是否为三态复选框。"""
        return self._tristate

    def set_tristate(self, tristate: bool) -> None:
        """设置是否三态。"""
        self._tristate = tristate

    @property
    def error(self) -> bool:
        """是否为错误态。"""
        return self._error

    def set_error(self, error: bool) -> None:
        """设置错误态。"""
        self._error = error
        self.update()

    @override
    def activate(self) -> None:
        previous = self.state
        if self._tristate:
            match previous:
                case CheckState.UNCHECKED:
                    self._indeterminate = False
                    self.set_checked(True)
                case CheckState.CHECKED:
                    self._indeterminate = True
                    self.update()
                case _:
                    self._indeterminate = False
                    self.set_checked(False)
        else:
            self._indeterminate = False
            self.set_checked(not self.checked)
        if self.state != previous:
            self.state_changed.emit(self.state)
        self.clicked.emit()

    # ---- 颜色 -------------------------------------------------------------

    def _outline_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._error:
            return self.color("error")
        return self.color("on_surface_variant")

    def _fill_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._error:
            return self.color("error")
        return self.color("primary")

    def _mark_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return self.color("surface")
        if self._error:
            return self.color("on_error")
        return self.color("on_primary")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        if self._error:
            return self.color("error")
        return super().state_layer_color()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_control(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        progress = self.progress
        painter.save()
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        if progress < 1.0:
            outline = self._outline_color()
            outline.setAlphaF(outline.alphaF() * (1.0 - progress))
            pen = QtGui.QPen(outline, OUTLINE_WIDTH)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            inner = rect.adjusted(
                OUTLINE_WIDTH / 2,
                OUTLINE_WIDTH / 2,
                -OUTLINE_WIDTH / 2,
                -OUTLINE_WIDTH / 2,
            )
            painter.drawRoundedRect(inner, BOX_RADIUS, BOX_RADIUS)
        if progress > 0.0:
            fill = self._fill_color()
            fill.setAlphaF(fill.alphaF() * progress)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, BOX_RADIUS, BOX_RADIUS)
            pen = QtGui.QPen(self._mark_color(), MARK_WIDTH)
            pen.setCapStyle(QtCore.Qt.PenCapStyle.SquareCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.setClipRect(rect)
            if self._indeterminate:
                y = rect.center().y()
                painter.drawLine(
                    QtCore.QPointF(rect.left() + 4, y),
                    QtCore.QPointF(rect.right() - 4, y),
                )
            else:
                self._paint_check(painter, rect, progress)
        painter.restore()

    def _paint_check(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF, progress: float
    ) -> None:
        # 勾选标记的三个顶点（18dp 网格坐标），随进度从左向右展开。
        scale = rect.width() / 18.0
        points = [
            QtCore.QPointF(rect.left() + 4.0 * scale, rect.top() + 9.5 * scale),
            QtCore.QPointF(
                rect.left() + 7.5 * scale, rect.top() + 13.0 * scale
            ),
            QtCore.QPointF(
                rect.left() + 14.5 * scale, rect.top() + 5.5 * scale
            ),
        ]
        path = QtGui.QPainterPath(points[0])
        first_len = 5.0 * scale
        second_len = 10.0 * scale
        total = first_len + second_len
        drawn = total * progress
        if drawn <= first_len:
            t = drawn / first_len
            path.lineTo(_lerp_point(points[0], points[1], t))
        else:
            path.lineTo(points[1])
            t = (drawn - first_len) / second_len
            path.lineTo(_lerp_point(points[1], points[2], t))
        painter.drawPath(path)


def _lerp_point(
    a: QtCore.QPointF, b: QtCore.QPointF, t: float
) -> QtCore.QPointF:
    return QtCore.QPointF(
        a.x() + (b.x() - a.x()) * t, a.y() + (b.y() - a.y()) * t
    )
