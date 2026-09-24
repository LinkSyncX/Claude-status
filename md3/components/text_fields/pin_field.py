"""验证码输入框（PIN field）：一组等宽字符格。

常用于短信验证码 / 一次性密码：每格一个字符，输入后自动前进，退格
回退，支持粘贴整段代码、方向键移动与输入法提交。控件自身处理键盘
事件，不内嵌 ``QLineEdit``。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

BOX_WIDTH = 44.0
BOX_HEIGHT = 56.0
BOX_GAP = 8.0
GROUP_GAP = 16.0
OUTLINE_WIDTH = 1.0
FOCUSED_OUTLINE_WIDTH = 2.0
CARET_WIDTH = 2.0
CARET_HEIGHT = 24.0
MASK_CHAR = "●"
DIGIT_STYLE = typography_tokens.TypeRole.HEADLINE_SMALL


class PinField(widget.MaterialWidget):
    """验证码输入框。

    Args:
        length: 字符格数量。
        masked: 是否以圆点遮盖已输入字符。
        digits_only: 是否只接受数字。
        group_size: 每隔多少格插入一个较大的分组间隔，0 表示不分组。
        parent: 父控件。
    """

    code_changed = QtCore.Signal(str)
    completed = QtCore.Signal(str)

    def __init__(
        self,
        length: int = 6,
        masked: bool = False,
        digits_only: bool = True,
        group_size: int = 0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._length = max(1, length)
        self._masked = masked
        self._digits_only = digits_only
        self._group_size = max(0, group_size)
        self._code = ""
        self._cursor = 0
        self._error = False
        self._has_focus = False
        self._hovered = -1
        # 新输入字符的放大出现动画。
        self._pop = animation.AnimatedFloat(self, 1.0, self.update)
        self._pop_index = -1
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_InputMethodEnabled, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setCursor(QtCore.Qt.CursorShape.IBeamCursor)
        self.setMouseTracking(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 属性 -------------------------------------------------------------

    @property
    def code(self) -> str:
        """当前输入的代码。"""
        return self._code

    def set_code(self, code: str) -> None:
        """设置代码（超长部分截断，非法字符忽略）。"""
        filtered = "".join(c for c in code if self._accepts(c))[: self._length]
        if filtered == self._code:
            return
        self._code = filtered
        self._cursor = min(len(filtered), self._length - 1)
        self._after_change()

    def clear(self) -> None:
        """清空。"""
        self.set_code("")

    @property
    def length(self) -> int:
        """字符格数量。"""
        return self._length

    @property
    def complete(self) -> bool:
        """是否已填满。"""
        return len(self._code) == self._length

    @property
    def masked(self) -> bool:
        """是否遮盖。"""
        return self._masked

    def set_masked(self, masked: bool) -> None:
        """设置是否遮盖。"""
        self._masked = masked
        self.update()

    @property
    def error(self) -> bool:
        """是否为错误态。"""
        return self._error

    def set_error(self, error: bool) -> None:
        """设置错误态。"""
        self._error = error
        self.update()

    @property
    def cursor_index(self) -> int:
        """当前光标所在的格。"""
        return self._cursor

    def _accepts(self, char: str) -> bool:
        if not char or char.isspace() or not char.isprintable():
            return False
        return char.isdigit() if self._digits_only else True

    def _after_change(self) -> None:
        self.code_changed.emit(self._code)
        accessibility.notify_value_changed(self, self.accessible_value())
        self.update()
        if self.complete:
            self.completed.emit(self._code)

    def insert(self, text: str) -> None:
        """在光标处插入文字（覆盖已有字符），自动前进。"""
        chars = [c for c in text if self._accepts(c)]
        if not chars:
            return
        code = list(self._code)
        for char in chars:
            if self._cursor >= self._length:
                break
            if self._cursor < len(code):
                code[self._cursor] = char
            else:
                code.append(char)
            self._pop_index = self._cursor
            self._cursor += 1
        self._code = "".join(code)
        # 填满后光标停在最后一格，再次输入会覆盖它。
        self._cursor = min(self._cursor, self._length - 1)
        self._pop.set(0.0)
        self._pop.animate_to(1.0, motion.SHORT4, motion.EMPHASIZED_DECELERATE)
        self._after_change()

    def backspace(self) -> None:
        """退格：填满时清除最后一格，否则删除光标前一个字符并回退。"""
        code = list(self._code)
        if self.complete and self._cursor == self._length - 1:
            del code[self._cursor]
        elif self._cursor > 0:
            if self._cursor <= len(code):
                del code[self._cursor - 1]
            self._cursor -= 1
        else:
            return
        self._code = "".join(code)
        self._after_change()

    # ---- 几何 -------------------------------------------------------------

    def box_rect(self, index: int) -> QtCore.QRectF:
        """第 index 格的矩形。"""
        x = 0.0
        for current in range(index):
            x += BOX_WIDTH + BOX_GAP
            if self._group_size and (current + 1) % self._group_size == 0:
                x += GROUP_GAP - BOX_GAP
        return QtCore.QRectF(x, 0.0, BOX_WIDTH, BOX_HEIGHT)

    def index_at(self, position: QtCore.QPointF) -> int:
        """位置所在的格，不在任何格上时返回 -1。"""
        for index in range(self._length):
            if self.box_rect(index).contains(position):
                return index
        return -1

    @override
    def sizeHint(self) -> QtCore.QSize:
        last = self.box_rect(self._length - 1)
        return QtCore.QSize(round(last.right()), round(BOX_HEIGHT))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    # ---- 绘制 -------------------------------------------------------------

    def _outline_color(self, index: int, active: bool) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        if self._error:
            return self.color("error")
        if active:
            return self.color("primary")
        if index == self._hovered:
            return self.color("on_surface")
        return self.color("outline")

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        theme = self.theme
        text_color = self.color("on_surface")
        if not self.isEnabled():
            text_color = theme_module.with_alpha(
                text_color, state_tokens.DISABLED_CONTENT_OPACITY
            )
        for index in range(self._length):
            rect = self.box_rect(index)
            active = self._has_focus and index == self._cursor
            width = FOCUSED_OUTLINE_WIDTH if active else OUTLINE_WIDTH
            half = width / 2
            path = shape_utils.rounded_rect_path(
                rect.adjusted(half, half, -half, -half),
                shape_utils.outset_shape(shape_tokens.SHAPE_EXTRA_SMALL, -half),
            )
            fill = (
                self.color("surface_container_highest")
                if index < len(self._code)
                else self.color("surface")
            )
            shape_utils.fill_shape(
                painter, path, fill, self._outline_color(index, active), width
            )
            if index < len(self._code):
                char = MASK_CHAR if self._masked else self._code[index]
                scale = 1.0
                if index == self._pop_index:
                    scale = 0.6 + 0.4 * self._pop.value
                painter.save()
                painter.translate(rect.center())
                painter.scale(scale, scale)
                painter.translate(-rect.center())
                typography.paint_text(
                    painter,
                    rect,
                    char,
                    DIGIT_STYLE,
                    text_color,
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
                painter.restore()
            elif active:
                caret = QtCore.QRectF(
                    rect.center().x() - CARET_WIDTH / 2,
                    rect.center().y() - CARET_HEIGHT / 2,
                    CARET_WIDTH,
                    CARET_HEIGHT,
                )
                painter.fillRect(caret, theme.color("primary"))

    # ---- 事件 -------------------------------------------------------------

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        if event.matches(QtGui.QKeySequence.StandardKey.Paste):
            self.insert(QtGui.QGuiApplication.clipboard().text())
        elif key == QtCore.Qt.Key.Key_Backspace:
            self.backspace()
        elif key == QtCore.Qt.Key.Key_Delete:
            if self._cursor < len(self._code):
                code = list(self._code)
                del code[self._cursor]
                self._code = "".join(code)
                self._after_change()
        elif key == QtCore.Qt.Key.Key_Left:
            self._move_cursor(self._cursor - 1)
        elif key == QtCore.Qt.Key.Key_Right:
            self._move_cursor(self._cursor + 1)
        elif key == QtCore.Qt.Key.Key_Home:
            self._move_cursor(0)
        elif key == QtCore.Qt.Key.Key_End:
            self._move_cursor(len(self._code))
        elif event.text() and self._accepts(event.text()[0]):
            self.insert(event.text())
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def _move_cursor(self, index: int) -> None:
        self._cursor = max(0, min(len(self._code), index, self._length - 1))
        if len(self._code) == self._length and index >= self._length:
            self._cursor = self._length - 1
        self.update()

    @override
    def inputMethodEvent(self, event: QtGui.QInputMethodEvent) -> None:
        if event.commitString():
            self.insert(event.commitString())
        event.accept()

    @override
    def inputMethodQuery(self, query: QtCore.Qt.InputMethodQuery) -> object:
        if query == QtCore.Qt.InputMethodQuery.ImHints:
            hints = QtCore.Qt.InputMethodHint.ImhNoPredictiveText
            if self._digits_only:
                hints |= QtCore.Qt.InputMethodHint.ImhDigitsOnly
            if self._masked:
                hints |= QtCore.Qt.InputMethodHint.ImhHiddenText
            return hints
        if query == QtCore.Qt.InputMethodQuery.ImCursorRectangle:
            index = min(self._cursor, self._length - 1)
            return self.box_rect(index).toRect()
        return super().inputMethodQuery(query)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            index = self.index_at(event.position())
            if index >= 0:
                self._cursor = min(index, len(self._code), self._length - 1)
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hovered = self.index_at(event.position())
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
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusInEvent(event)
        self._has_focus = True
        if self.complete:
            self._cursor = self._length - 1
        self.update()

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(event)
        self._has_focus = False
        self.update()

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.EditableText

    @override
    def accessible_value(self) -> str:
        if self._masked:
            return MASK_CHAR * len(self._code)
        return self._code

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        state.editable = True
        state.passwordEdit = self._masked
        state.invalid = self._error
