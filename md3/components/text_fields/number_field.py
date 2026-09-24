"""数字输入框（Number field）：带范围、步长与步进按钮的文本框。"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import icon_button
from md3.components.text_fields import text_field

STEPPER_SIZE = 40.0
STEPPER_GAP = 0.0
STEPPER_PADDING = 4.0
LARGE_STEP_FACTOR = 10


class NumberField(text_field.TextField):
    """数字输入框。

    输入时只接受数字字符；失焦或回车时解析、按范围钳制并按小数位格式化。
    右侧的减 / 加按钮、方向键上下、PageUp / PageDown（十倍步长）与聚焦时
    的滚轮都可以步进。

    Args:
        label: 浮动标签。
        value: 初始值。
        minimum: 最小值，None 表示不限制。
        maximum: 最大值，None 表示不限制。
        step: 步长。
        decimals: 小数位数。
        variant: 样式（默认 outlined）。
        show_steppers: 是否显示减 / 加按钮。
        wrap: 到达边界后是否回绕到另一端。
        **kwargs: 其余参数同 ``TextField``（如 ``prefix`` / ``suffix``）。
    """

    value_changed = QtCore.Signal(float)

    def __init__(
        self,
        label: str = "",
        value: float = 0.0,
        minimum: float | None = None,
        maximum: float | None = None,
        step: float = 1.0,
        decimals: int = 0,
        variant: text_field.TextFieldVariant = (
            text_field.TextFieldVariant.OUTLINED
        ),
        show_steppers: bool = True,
        wrap: bool = False,
        **kwargs,
    ) -> None:
        kwargs.pop("multiline", None)
        kwargs.pop("password", None)
        self._minimum = minimum
        self._maximum = maximum
        self._step = abs(step) or 1.0
        self._decimals = max(0, decimals)
        self._wrap = wrap
        self._show_steppers = show_steppers
        self._value = self._constrain(value)
        self._syncing = False
        super().__init__(
            label, self.format_value(self._value), variant, **kwargs
        )
        editor = self.editor
        assert isinstance(editor, QtWidgets.QLineEdit)
        editor.setValidator(
            QtGui.QRegularExpressionValidator(
                QtCore.QRegularExpression(self._pattern()), editor
            )
        )
        self.editing_finished.connect(self.commit)
        self.return_pressed.connect(self.commit)
        self._decrement = icon_button.IconButton(
            "remove", tooltip=i18n.tr("decrease"), parent=self
        )
        self._increment = icon_button.IconButton(
            "add", tooltip=i18n.tr("increase"), parent=self
        )
        for button in (self._decrement, self._increment):
            button.set_outer_margin(0.0)
            button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            button.setVisible(show_steppers)
        self._decrement.clicked.connect(lambda: self.step_by(-1))
        self._increment.clicked.connect(lambda: self.step_by(1))
        self._sync_steppers()
        self._layout_editor()

    # ---- 取值 -------------------------------------------------------------

    @property
    def value(self) -> float:
        """当前值。"""
        return self._value

    def set_value(self, value: float) -> None:
        """设置值（按范围钳制、按小数位取整），变化时发出 ``value_changed``。"""
        value = self._constrain(value)
        changed = value != self._value
        self._value = value
        self._sync_text()
        self._sync_steppers()
        if changed:
            self.value_changed.emit(value)

    @property
    def minimum(self) -> float | None:
        """最小值。"""
        return self._minimum

    @property
    def maximum(self) -> float | None:
        """最大值。"""
        return self._maximum

    def set_range(self, minimum: float | None, maximum: float | None) -> None:
        """设置取值范围并重新钳制当前值。"""
        if minimum is not None and maximum is not None and maximum < minimum:
            raise ValueError("maximum 必须不小于 minimum")
        self._minimum = minimum
        self._maximum = maximum
        self.set_value(self._value)

    @property
    def step(self) -> float:
        """步长。"""
        return self._step

    def set_step(self, step: float) -> None:
        """设置步长。"""
        self._step = abs(step) or 1.0

    @property
    def decimals(self) -> int:
        """小数位数。"""
        return self._decimals

    def set_decimals(self, decimals: int) -> None:
        """设置小数位数并重新格式化。"""
        self._decimals = max(0, decimals)
        editor = self.editor
        assert isinstance(editor, QtWidgets.QLineEdit)
        editor.setValidator(
            QtGui.QRegularExpressionValidator(
                QtCore.QRegularExpression(self._pattern()), editor
            )
        )
        self.set_value(self._value)
        self._sync_text(force=True)

    @property
    def show_steppers(self) -> bool:
        """是否显示步进按钮。"""
        return self._show_steppers

    def set_show_steppers(self, show: bool) -> None:
        """设置是否显示步进按钮。"""
        self._show_steppers = show
        self._decrement.setVisible(show)
        self._increment.setVisible(show)
        self._layout_editor()
        self.update()

    def step_by(self, count: int) -> None:
        """按 ``count`` 个步长增减。"""
        if not self.isEnabled() or self.read_only:
            return
        self.commit()
        target = self._value + count * self._step
        if (
            self._wrap
            and self._minimum is not None
            and self._maximum is not None
        ):
            span = self._maximum - self._minimum
            if span > 0:
                target = self._minimum + (target - self._minimum) % (
                    span + self._step
                )
                target = min(target, self._maximum)
        self.set_value(target)

    def commit(self) -> None:
        """解析当前文字为数值；无法解析时恢复为上一个值。"""
        if self._syncing:
            return
        parsed = self.parse(self.text)
        if parsed is None:
            self._sync_text(force=True)
            return
        self.set_value(parsed)
        self._sync_text(force=True)

    def parse(self, text: str) -> float | None:
        """把文字解析为数值，失败返回 None。"""
        cleaned = text.strip().replace(",", ".").replace(" ", "")
        if not cleaned or cleaned in ("-", ".", "-."):
            return None
        try:
            value = float(cleaned)
        except ValueError:
            return None
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    def format_value(self, value: float) -> str:
        """按小数位格式化数值。"""
        return f"{value:.{self._decimals}f}"

    def _pattern(self) -> str:
        allow_negative = self._minimum is None or self._minimum < 0
        sign = "-?" if allow_negative else ""
        if self._decimals > 0:
            return rf"^{sign}\d*([.,]\d{{0,{self._decimals}}})?$"
        return rf"^{sign}\d*$"

    def _constrain(self, value: float) -> float:
        if self._minimum is not None:
            value = max(self._minimum, value)
        if self._maximum is not None:
            value = min(self._maximum, value)
        return round(value, self._decimals)

    def _sync_text(self, force: bool = False) -> None:
        text = self.format_value(self._value)
        if not force and self.parse(self.text) == self._value:
            return
        if text == self.text:
            return
        self._syncing = True
        try:
            self.set_text(text)
        finally:
            self._syncing = False

    def _sync_steppers(self) -> None:
        enabled = self.isEnabled() and not self.read_only
        at_min = self._minimum is not None and self._value <= self._minimum
        at_max = self._maximum is not None and self._value >= self._maximum
        self._decrement.setEnabled(enabled and (self._wrap or not at_min))
        self._increment.setEnabled(enabled and (self._wrap or not at_max))

    # ---- 几何 -------------------------------------------------------------

    @override
    def trailing_reserved_width(self) -> float:
        if not self._show_steppers:
            return 0.0
        return 2 * STEPPER_SIZE + STEPPER_GAP + STEPPER_PADDING

    @override
    def _layout_editor(self) -> None:
        super()._layout_editor()
        buttons = getattr(self, "_increment", None)
        if buttons is None:
            return
        rect = self.container_rect()
        y = rect.top() + (text_field.CONTAINER_HEIGHT - STEPPER_SIZE) / 2
        right = rect.right() - STEPPER_PADDING
        self._increment.setGeometry(
            self.visual_rect(
                QtCore.QRectF(
                    right - STEPPER_SIZE, y, STEPPER_SIZE, STEPPER_SIZE
                )
            ).toRect()
        )
        self._decrement.setGeometry(
            self.visual_rect(
                QtCore.QRectF(
                    right - 2 * STEPPER_SIZE - STEPPER_GAP,
                    y,
                    STEPPER_SIZE,
                    STEPPER_SIZE,
                )
            ).toRect()
        )

    # ---- 事件 -------------------------------------------------------------

    @override
    def editor_key_pressed(self, event: QtGui.QKeyEvent) -> bool:
        steps = {
            QtCore.Qt.Key.Key_Up: 1,
            QtCore.Qt.Key.Key_Down: -1,
            QtCore.Qt.Key.Key_PageUp: LARGE_STEP_FACTOR,
            QtCore.Qt.Key.Key_PageDown: -LARGE_STEP_FACTOR,
        }
        count = steps.get(event.key())
        if count is None:
            return super().editor_key_pressed(event)
        self.step_by(count)
        return True

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self.editor.hasFocus():
            event.ignore()
            return
        delta = event.angleDelta().y()
        if delta:
            self.step_by(1 if delta > 0 else -1)
        event.accept()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._sync_steppers()

    @override
    def set_read_only(self, read_only: bool) -> None:
        super().set_read_only(read_only)
        self._sync_steppers()

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.SpinBox

    @override
    def accessible_value(self) -> str:
        return self.format_value(self._value)
