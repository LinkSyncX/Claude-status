"""带可选文字标签的选择控件基类。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

TOUCH_TARGET = 48.0
STATE_LAYER_SIZE = 40.0
LABEL_GAP = 2.0
LABEL_STYLE = typography_tokens.TypeRole.BODY_LARGE


class SelectionControl(widget.InteractiveWidget):
    """复选框、单选按钮与开关的公共基类。

    控件视觉部分居中放在 48dp 触控目标内，右侧可选文字标签；点击整行都
    会切换状态。子类实现 ``paint_control`` 并通过 ``progress`` 获取
    0–1 的选中过渡值。
    """

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        text: str = "",
        checked: bool = False,
        control_width: float = 20.0,
        control_height: float = 20.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._checked = checked
        self._control_width = control_width
        self._control_height = control_height
        self._progress = animation.AnimatedFloat(
            self, 1.0 if checked else 0.0, self.update
        )
        self.set_outer_margin(0.0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 状态 -------------------------------------------------------------

    @property
    def checked(self) -> bool:
        """是否选中。"""
        return self._checked

    def set_checked(self, checked: bool) -> None:
        """设置选中状态，变化时发出 ``toggled``。"""
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self._progress.animate_to(
            1.0 if checked else 0.0, motion.SHORT4, motion.STANDARD
        )
        self.toggled.emit(checked)
        accessibility.notify_state_changed(self, checked=True)
        self.update()

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.CheckBox

    @property
    def progress(self) -> float:
        """选中过渡进度，0 为未选中、1 为选中。"""
        return self._progress.value

    @property
    def text(self) -> str:
        """标签文字。"""
        return self._text

    def set_text(self, text: str) -> None:
        """设置标签文字。"""
        self._text = text
        self.updateGeometry()
        self.update()

    @override
    def activate(self) -> None:
        self.set_checked(not self._checked)
        super().activate()

    # ---- 几何 -------------------------------------------------------------

    def _logical_target_rect(self) -> QtCore.QRectF:
        rect = QtCore.QRectF(self.rect())
        side = TOUCH_TARGET
        width = max(side, self._control_width + 8)
        return QtCore.QRectF(
            rect.left(), rect.center().y() - side / 2, width, side
        )

    def target_rect(self) -> QtCore.QRectF:
        """48dp 触控目标矩形（布局起始侧，RTL 下在右侧）。"""
        return self.visual_rect(self._logical_target_rect())

    def control_rect(self) -> QtCore.QRectF:
        """控件视觉部分的矩形，居中于触控目标。"""
        target = self.target_rect()
        return QtCore.QRectF(
            target.center().x() - self._control_width / 2,
            target.center().y() - self._control_height / 2,
            self._control_width,
            self._control_height,
        )

    def label_rect(self) -> QtCore.QRectF:
        """文字标签矩形。"""
        target = self._logical_target_rect()
        rect = QtCore.QRectF(self.rect())
        left = target.right() + LABEL_GAP
        return self.visual_rect(
            QtCore.QRectF(left, rect.top(), rect.right() - left, rect.height())
        )

    @override
    def container_rect(self) -> QtCore.QRectF:
        target = self.target_rect()
        size = max(STATE_LAYER_SIZE, self._control_width + 8)
        return QtCore.QRectF(
            target.center().x() - size / 2,
            target.center().y() - STATE_LAYER_SIZE / 2,
            size,
            STATE_LAYER_SIZE,
        )

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_FULL

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = self.target_rect().width()
        if self._text:
            width += LABEL_GAP + typography.text_width(self._text, LABEL_STYLE)
            width += 8.0
        return typography.size_hint(width, TOUCH_TARGET)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    # ---- 颜色 -------------------------------------------------------------

    def label_color(self) -> QtGui.QColor:
        """标签文字颜色。"""
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        return self.color("on_surface")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        if self._checked:
            return self.color("primary")
        return self.color("on_surface")

    # ---- 绘制 -------------------------------------------------------------

    def paint_control(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        """绘制控件本体，由子类实现。"""
        del painter, rect

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        self.paint_control(painter, self.control_rect())
        if self._text:
            typography.paint_text(
                painter,
                self.label_rect(),
                self._text,
                LABEL_STYLE,
                self.label_color(),
                self.start_alignment(),
            )

    @override
    def focus_ring_extent(self) -> float:
        # 40dp 状态层圆位于 48dp 触控目标内，四周各有 4dp 可画焦点环。
        return (TOUCH_TARGET - STATE_LAYER_SIZE) / 2
