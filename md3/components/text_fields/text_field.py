"""文本框（Text fields）。

编辑能力由内嵌的 ``QLineEdit`` / ``QPlainTextEdit`` 提供（输入法、选择、
剪贴板、撤销），外层负责绘制容器、浮动标签、指示线、前后图标、
辅助文字与字数统计。
"""

from __future__ import annotations

from collections.abc import Callable
import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
import shiboken6

from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

CONTAINER_HEIGHT = 56.0
LABEL_TOP_SPACE = 8.0
HORIZONTAL_PADDING = 16.0
ICON_SIZE = 24.0
ICON_PADDING = 12.0
ICON_GAP = 16.0
SUPPORTING_GAP = 4.0
SUPPORTING_HEIGHT = 16.0
MIN_WIDTH = 210.0
INDICATOR_WIDTH = 1.0
FOCUSED_INDICATOR_WIDTH = 2.0
MULTILINE_ROW_HEIGHT = 24.0
# 多行编辑器没有 QLineEdit 那样的垂直居中留白，首行上方补足 24dp 行高与
# 字体高度之差的一半，使其与单行输入文字的基线位置一致。
MULTILINE_TOP_LEADING = 4.0
CLEAR_ICON = "cancel"
INPUT_STYLE = typography_tokens.TypeRole.BODY_LARGE
LABEL_STYLE = typography_tokens.TypeRole.BODY_LARGE
FLOATING_LABEL_STYLE = typography_tokens.TypeRole.BODY_SMALL
SUPPORTING_STYLE = typography_tokens.TypeRole.BODY_SMALL

Validator = Callable[[str], str | None]


class TextFieldVariant(enum.Enum):
    """文本框样式。"""

    FILLED = "filled"
    OUTLINED = "outlined"


class _EditProxy(QtCore.QObject):
    """把内部编辑器的焦点、悬停与键盘事件转发给文本框。"""

    def __init__(self, field: TextField) -> None:
        super().__init__(field)
        self._field = field

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        # 文本框销毁过程中编辑器仍会收到事件，此时外层对象已不可用（引用
        # 环被垃圾回收清理时属性字典也可能已清空）。
        field = getattr(self, "_field", None)
        if field is None or not shiboken6.isValid(field):
            return False
        kind = event.type()
        if kind == QtCore.QEvent.Type.FocusIn:
            self._field._on_focus_changed(True)  # pylint: disable=protected-access
        elif kind == QtCore.QEvent.Type.FocusOut:
            self._field._on_focus_changed(False)  # pylint: disable=protected-access
        elif kind == QtCore.QEvent.Type.KeyPress:
            assert isinstance(event, QtGui.QKeyEvent)
            if self._field.editor_key_pressed(event):
                return True
        return super().eventFilter(watched, event)


class TextField(widget.MaterialWidget):
    """文本框。

    Args:
        label: 浮动标签。
        text: 初始文字。
        variant: 样式（filled / outlined）。
        placeholder: 标签浮起后显示的占位文字。
        supporting_text: 容器下方的辅助文字。
        leading_icon: 前置图标。
        trailing_icon: 后置图标（可点击）。
        prefix: 输入前的前缀文字（如货币符号）。
        suffix: 输入后的后缀文字（如单位）。
        max_length: 最大字数；设置后显示字数统计。
        password: 是否为密码输入（提供可见性切换）。
        multiline: 是否多行输入。
        rows: 多行输入的可见行数。
        clearable: 有文字时显示清除按钮。
        validator: 校验函数 ``text -> 错误信息 | None``，输入时实时校验并
            切换错误态。
        read_only: 是否只读（可选中复制，不可编辑）。
        parent: 父控件。
    """

    text_changed = QtCore.Signal(str)
    editing_finished = QtCore.Signal()
    return_pressed = QtCore.Signal()
    trailing_icon_clicked = QtCore.Signal()
    cleared = QtCore.Signal()
    validity_changed = QtCore.Signal(bool)
    backspace_on_empty = QtCore.Signal()

    def __init__(
        self,
        label: str = "",
        text: str = "",
        variant: TextFieldVariant = TextFieldVariant.FILLED,
        placeholder: str = "",
        supporting_text: str = "",
        leading_icon: icons.IconLike = None,
        trailing_icon: icons.IconLike = None,
        prefix: str = "",
        suffix: str = "",
        max_length: int | None = None,
        password: bool = False,
        multiline: bool = False,
        rows: int = 3,
        clearable: bool = False,
        validator: Validator | None = None,
        read_only: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._label = label
        self._variant = variant
        self._placeholder = placeholder
        self._supporting_text = supporting_text
        self._error_text = ""
        self._error = False
        self._leading_icon = icons.coerce(leading_icon, ICON_SIZE)
        self._trailing_icon = icons.coerce(trailing_icon, ICON_SIZE)
        self._clear_icon = icons.coerce(CLEAR_ICON, ICON_SIZE)
        self._prefix = prefix
        self._suffix = suffix
        self._max_length = max_length
        self._password = password
        self._password_visible = False
        self._multiline = multiline
        self._rows = max(1, rows)
        self._clearable = clearable
        self._validator = validator
        self._valid = True
        self._read_only = read_only
        self._hovered = False
        self._has_focus = False
        self._trailing_pressed = False
        self._float = animation.AnimatedFloat(self, 0.0, self.update)
        # 聚焦时 2dp 的活动指示线从中心向两侧生长。
        self._active = animation.AnimatedFloat(self, 0.0, self.update)

        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._edit = self._create_editor()
        self._edit.installEventFilter(_EditProxy(self))
        self._edit.setReadOnly(read_only)
        self.setFocusProxy(self._edit)
        self._apply_editor_style()
        self._sync_editor_accessibility()
        if text:
            self.set_text(text)
        if max_length is not None and not multiline:
            self._edit.setMaxLength(max_length)
        self._sync_float(animate=False)
        self._layout_editor()

    # ---- 编辑器 -----------------------------------------------------------

    def _create_editor(self) -> QtWidgets.QLineEdit | QtWidgets.QPlainTextEdit:
        if self._multiline:
            edit: QtWidgets.QPlainTextEdit = QtWidgets.QPlainTextEdit(self)
            edit.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
            edit.setVerticalScrollBarPolicy(
                QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
            edit.textChanged.connect(self._on_text_changed)
            return edit
        line = QtWidgets.QLineEdit(self)
        line.setFrame(False)
        line.textChanged.connect(self._on_text_changed)
        line.editingFinished.connect(self.editing_finished)
        line.returnPressed.connect(self.return_pressed)
        if self._password:
            line.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        return line

    @property
    def editor(self) -> QtWidgets.QLineEdit | QtWidgets.QPlainTextEdit:
        """内部编辑器，可用于设置校验器、补全器等高级功能。"""
        return self._edit

    def _apply_editor_style(self) -> None:
        theme = self.theme
        font = theme.font(INPUT_STYLE)
        self._edit.setFont(font)
        self._edit.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True
        )
        palette = self._edit.palette()
        text_color = self._text_color()
        palette.setColor(QtGui.QPalette.ColorRole.Text, text_color)
        palette.setColor(
            QtGui.QPalette.ColorRole.Base, theme_module.TRANSPARENT
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.PlaceholderText,
            self.color("on_surface_variant"),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Highlight, self.color("primary")
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.HighlightedText, self.color("on_primary")
        )
        self._edit.setPalette(palette)
        self._edit.setStyleSheet(
            "background: transparent; border: none; padding: 0px; margin: 0px;"
        )
        if isinstance(self._edit, QtWidgets.QPlainTextEdit):
            self._edit.viewport().setAutoFillBackground(False)
            self._edit.document().setDocumentMargin(0)
        self._update_placeholder()

    def _update_placeholder(self) -> None:
        show = bool(self._placeholder) and (self._floating() or not self._label)
        self._edit.setPlaceholderText(self._placeholder if show else "")

    @override
    def on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self._apply_editor_style()

    # ---- 文本与属性 -------------------------------------------------------

    @property
    def text(self) -> str:
        """当前文字。"""
        if isinstance(self._edit, QtWidgets.QPlainTextEdit):
            return self._edit.toPlainText()
        return self._edit.text()

    def set_text(self, text: str) -> None:
        """设置文字。"""
        if isinstance(self._edit, QtWidgets.QPlainTextEdit):
            self._edit.setPlainText(text)
        else:
            self._edit.setText(text)

    @property
    def label(self) -> str:
        """浮动标签。"""
        return self._label

    def set_label(self, label: str) -> None:
        """设置浮动标签。"""
        self._label = label
        self._sync_float(animate=False)
        self._sync_editor_accessibility()
        self.updateGeometry()
        self.update()

    # ---- 无障碍 -----------------------------------------------------------

    def _sync_editor_accessibility(self) -> None:
        # 浮动标签与辅助文字是自绘的，把它们交给内部编辑器播报。
        self._edit.setAccessibleName(self._label or self._placeholder)
        self._edit.setAccessibleDescription(
            self._error_text or self._supporting_text
        )

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    @override
    def accessible_name(self) -> str:
        return self._label

    @override
    def accessible_description(self) -> str:
        return self._error_text or self._supporting_text

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        state.invalid = self._error

    @property
    def variant(self) -> TextFieldVariant:
        """样式。"""
        return self._variant

    @property
    def supporting_text(self) -> str:
        """辅助文字。"""
        return self._supporting_text

    def set_supporting_text(self, text: str) -> None:
        """设置辅助文字。"""
        self._supporting_text = text
        self._sync_editor_accessibility()
        self.updateGeometry()
        self.update()

    @property
    def error(self) -> bool:
        """是否为错误态。"""
        return self._error

    def set_error(self, error: bool, error_text: str = "") -> None:
        """设置错误态，可同时给出替代辅助文字的错误说明。"""
        self._error = error
        self._error_text = error_text if error else ""
        self._apply_editor_style()
        self._sync_editor_accessibility()
        self.updateGeometry()
        self.update()

    def set_leading_icon(self, icon: icons.IconLike) -> None:
        """设置前置图标。"""
        self._leading_icon = icons.coerce(icon, ICON_SIZE)
        self._layout_editor()
        self.update()

    def set_trailing_icon(self, icon: icons.IconLike) -> None:
        """设置后置图标。"""
        self._trailing_icon = icons.coerce(icon, ICON_SIZE)
        self._layout_editor()
        self.update()

    def set_placeholder(self, placeholder: str) -> None:
        """设置占位文字。"""
        self._placeholder = placeholder
        self._update_placeholder()

    @property
    def max_length(self) -> int | None:
        """最大字数。"""
        return self._max_length

    def set_max_length(self, max_length: int | None) -> None:
        """设置最大字数（None 取消限制与统计）。"""
        self._max_length = max_length
        if isinstance(self._edit, QtWidgets.QLineEdit):
            self._edit.setMaxLength(max_length if max_length else 32767)
        self.updateGeometry()
        self.update()

    @property
    def read_only(self) -> bool:
        """是否只读。"""
        return self._read_only

    def set_read_only(self, read_only: bool) -> None:
        """设置只读。"""
        self._read_only = read_only
        self._edit.setReadOnly(read_only)
        self.update()

    @property
    def clearable(self) -> bool:
        """有文字时是否显示清除按钮。"""
        return self._clearable

    def set_clearable(self, clearable: bool) -> None:
        """设置是否显示清除按钮。"""
        self._clearable = clearable
        self._layout_editor()
        self.update()

    def clear(self) -> None:
        """清空文字并发出 ``cleared``。"""
        if not self.text:
            return
        self.set_text("")
        self.cleared.emit()

    @property
    def validator(self) -> Validator | None:
        """校验函数。"""
        return self._validator

    def set_validator(self, validator: Validator | None) -> None:
        """设置校验函数并立即校验一次。"""
        self._validator = validator
        self.validate()

    @property
    def valid(self) -> bool:
        """最近一次校验是否通过（没有校验函数时恒为真）。"""
        return self._valid

    def validate(self) -> bool:
        """运行校验函数，按结果切换错误态，返回是否通过。"""
        message = self._validator(self.text) if self._validator else None
        valid = message is None
        if not valid:
            self.set_error(True, message or "")
        elif self._validator is not None and self._error:
            self.set_error(False)
        if valid != self._valid:
            self._valid = valid
            self.validity_changed.emit(valid)
        return valid

    @property
    def password_visible(self) -> bool:
        """密码是否可见。"""
        return self._password_visible

    def set_password_visible(self, visible: bool) -> None:
        """切换密码可见性。"""
        if not self._password or not isinstance(
            self._edit, QtWidgets.QLineEdit
        ):
            return
        self._password_visible = visible
        self._edit.setEchoMode(
            QtWidgets.QLineEdit.EchoMode.Normal
            if visible
            else QtWidgets.QLineEdit.EchoMode.Password
        )
        self.update()

    # ---- 状态 -------------------------------------------------------------

    def _focused(self) -> bool:
        return self._has_focus

    def _floating(self) -> bool:
        return self._focused() or bool(self.text) or bool(self._placeholder)

    def _sync_float(self, animate: bool = True) -> None:
        target = 1.0 if (self._floating() and self._label) else 0.0
        if animate:
            self._float.animate_to(target, motion.SHORT4, motion.STANDARD)
        else:
            self._float.set(target)
        self._update_placeholder()

    def _on_text_changed(self, *_args) -> None:
        text = self.text
        if (
            self._multiline
            and self._max_length is not None
            and len(text) > self._max_length
        ):
            edit = self._edit
            assert isinstance(edit, QtWidgets.QPlainTextEdit)
            cursor = edit.textCursor()
            edit.blockSignals(True)
            edit.setPlainText(text[: self._max_length])
            edit.blockSignals(False)
            cursor.setPosition(min(cursor.position(), self._max_length))
            edit.setTextCursor(cursor)
            text = self.text
        self._sync_float()
        if self._clearable:
            self._layout_editor()
        self.text_changed.emit(text)
        if self._validator is not None:
            self.validate()
        self.update()

    def _on_focus_changed(self, focused: bool) -> None:
        self._has_focus = focused
        self._sync_float()
        self._active.animate_to(
            1.0 if focused else 0.0, motion.SHORT4, motion.STANDARD
        )
        self.update()
        self.editor_focus_changed(focused)

    # ---- 子类钩子 ---------------------------------------------------------

    def editor_focus_changed(self, focused: bool) -> None:
        """编辑器获得 / 失去焦点后的钩子。"""
        del focused

    def editor_key_pressed(self, event: QtGui.QKeyEvent) -> bool:
        """编辑器按键钩子，返回 True 表示已处理、不再交给编辑器。

        子类不要直接把自身安装为编辑器的事件过滤器：控件销毁时编辑器仍会
        派发事件，而此时外层对象已经析构。基类实现只在文字为空时按退格
        发出 ``backspace_on_empty``。
        """
        if event.key() == QtCore.Qt.Key.Key_Backspace and not self.text:
            self.backspace_on_empty.emit()
        return False

    def _show_clear(self) -> bool:
        return (
            self._clearable
            and bool(self.text)
            and not self._read_only
            and not self._disabled()
        )

    @property
    def trailing_icon(self) -> icons.AnyIcon | None:
        """当前显示的后置图标（密码框为可见性切换图标，可清除时为清除图标）。"""
        if self._show_clear():
            return self._clear_icon
        if self._password:
            return icons.Icon(
                "visibility_off" if self._password_visible else "visibility",
                ICON_SIZE,
            )
        return self._trailing_icon

    # ---- 几何 -------------------------------------------------------------

    def _top_space(self) -> float:
        if self._variant is TextFieldVariant.OUTLINED and self._label:
            return LABEL_TOP_SPACE
        return 0.0

    def _container_height(self) -> float:
        if self._multiline:
            return max(
                CONTAINER_HEIGHT,
                24.0 + self._rows * MULTILINE_ROW_HEIGHT + 16.0,
            )
        return CONTAINER_HEIGHT

    def _has_supporting(self) -> bool:
        return bool(
            self._supporting_text or self._error_text or self._max_length
        )

    def container_rect(self) -> QtCore.QRectF:
        """容器矩形。"""
        rect = QtCore.QRectF(self.rect())
        return QtCore.QRectF(
            rect.left(),
            rect.top() + self._top_space(),
            rect.width(),
            self._container_height(),
        )

    def trailing_reserved_width(self) -> float:
        """后置图标之外、子类放置额外控件（如步进按钮）所需的宽度。"""
        return 0.0

    def extra_bottom_height(self) -> float:
        """容器与辅助文字之间子类额外绘制内容（如强度条）的高度。"""
        return 0.0

    def _input_left(self) -> float:
        rect = self.container_rect()
        if self._leading_icon is not None:
            return rect.left() + ICON_PADDING + ICON_SIZE + ICON_GAP
        return rect.left() + HORIZONTAL_PADDING

    def _input_right(self) -> float:
        rect = self.container_rect()
        right = rect.right() - self.trailing_reserved_width()
        if self.trailing_icon is not None:
            return right - ICON_PADDING - ICON_SIZE - ICON_GAP
        return right - HORIZONTAL_PADDING

    def trailing_rect(self) -> QtCore.QRectF:
        """后置图标的可点击区域（已按布局方向镜像）。"""
        if self.trailing_icon is None:
            return QtCore.QRectF()
        rect = self.container_rect()
        right = rect.right() - self.trailing_reserved_width()
        return self.visual_rect(
            QtCore.QRectF(
                right - ICON_PADDING - ICON_SIZE - 12,
                rect.top(),
                ICON_SIZE + ICON_PADDING + 12,
                rect.height(),
            )
        )

    def supporting_message(self) -> str:
        """辅助行实际显示的文字：错误态优先显示错误说明。"""
        if self._error and self._error_text:
            return self._error_text
        return self._supporting_text

    def supporting_top(self) -> float:
        """辅助文字行的顶边。"""
        return (
            self.container_rect().bottom()
            + self.extra_bottom_height()
            + SUPPORTING_GAP
        )

    def _editor_rect(self) -> QtCore.QRect:
        rect = self.container_rect()
        left = self._input_left()
        right = self._input_right()
        if self._prefix:
            left += typography.text_width(self._prefix, INPUT_STYLE) + 2
        if self._suffix:
            right -= typography.text_width(self._suffix, INPUT_STYLE) + 2
        style = self.theme.style(INPUT_STYLE)
        if self._multiline:
            top = rect.top() + (24.0 if self._label else 16.0)
            top += MULTILINE_TOP_LEADING
            bottom = rect.bottom() - 8.0
        elif self._label and self._variant is TextFieldVariant.FILLED:
            top = rect.top() + 24.0
            bottom = rect.bottom() - 8.0
        else:
            top = rect.center().y() - style.line_height / 2
            bottom = rect.center().y() + style.line_height / 2
        logical = QtCore.QRectF(
            left, top, max(1.0, right - left), max(1.0, bottom - top)
        )
        return self.visual_rect(logical).toRect()

    def _layout_editor(self) -> None:
        self._edit.setGeometry(self._editor_rect())

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_editor()

    @override
    def sizeHint(self) -> QtCore.QSize:
        height = (
            self._top_space()
            + self._container_height()
            + self.extra_bottom_height()
        )
        if self._has_supporting():
            height += SUPPORTING_GAP + SUPPORTING_HEIGHT
        return typography.size_hint(MIN_WIDTH, height)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        hint = self.sizeHint()
        return QtCore.QSize(120, hint.height())

    # ---- 颜色 -------------------------------------------------------------

    def _disabled(self) -> bool:
        return not self.isEnabled()

    def _text_color(self) -> QtGui.QColor:
        if self._disabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        return self.color("on_surface")

    def _label_color(self) -> QtGui.QColor:
        if self._disabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._error:
            return self.color("error")
        if self._focused():
            return self.color("primary")
        if self._hovered:
            return self.color("on_surface")
        return self.color("on_surface_variant")

    def _resting_indicator_color(self) -> QtGui.QColor:
        """未聚焦时的指示线 / 轮廓颜色。"""
        if self._disabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        if self._error:
            return self.color("error")
        if self._hovered:
            return self.color("on_surface")
        if self._variant is TextFieldVariant.OUTLINED:
            return self.color("outline")
        return self.color("on_surface_variant")

    def _active_indicator_color(self) -> QtGui.QColor:
        """聚焦时的 2dp 指示线 / 轮廓颜色。"""
        return self.color("error" if self._error else "primary")

    def _active_progress(self) -> float:
        return 0.0 if self._disabled() else self._active.value

    def _icon_color(self, trailing: bool) -> QtGui.QColor:
        if self._disabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if trailing and self._error:
            return self.color("error")
        return self.color("on_surface_variant")

    def _supporting_color(self) -> QtGui.QColor:
        if self._disabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        if self._error:
            return self.color("error")
        return self.color("on_surface_variant")

    # ---- 绘制 -------------------------------------------------------------

    def _container_shape(self) -> shape_tokens.Shape:
        if self._variant is TextFieldVariant.OUTLINED:
            return shape_tokens.SHAPE_EXTRA_SMALL
        return shape_tokens.Shape.top(shape_tokens.EXTRA_SMALL)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        path = shape_utils.rounded_rect_path(rect, self._container_shape())
        if self._variant is TextFieldVariant.FILLED:
            fill = (
                theme_module.with_alpha(self.color("on_surface"), 0.04)
                if self._disabled()
                else self.color("surface_container_highest")
            )
            shape_utils.fill_shape(painter, path, fill)
            if self._hovered and not self._focused() and not self._disabled():
                layer = theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.HOVER_STATE_LAYER_OPACITY,
                )
                shape_utils.fill_shape(painter, path, layer)
            painter.fillRect(
                QtCore.QRectF(
                    rect.left(),
                    rect.bottom() - INDICATOR_WIDTH,
                    rect.width(),
                    INDICATOR_WIDTH,
                ),
                self._resting_indicator_color(),
            )
            active = self._active_progress()
            if active > 0.001:
                active_width = rect.width() * active
                painter.fillRect(
                    QtCore.QRectF(
                        rect.center().x() - active_width / 2,
                        rect.bottom() - FOCUSED_INDICATOR_WIDTH,
                        active_width,
                        FOCUSED_INDICATOR_WIDTH,
                    ),
                    self._active_indicator_color(),
                )
        else:
            self._paint_outline(painter, rect)
        self._paint_icons(painter, rect)
        self._paint_affixes(painter)
        self._paint_label(painter, rect)
        self._paint_supporting(painter, rect)

    def _label_metrics(self) -> tuple[QtCore.QRectF, float, float]:
        """返回浮动标签的矩形、字号插值以及进度。"""
        progress = self._float.value
        rect = self.container_rect()
        resting_style = self.theme.style(LABEL_STYLE)
        floating_style = self.theme.style(FLOATING_LABEL_STYLE)
        size = (
            resting_style.size
            + (floating_style.size - resting_style.size) * progress
        )
        left = self._input_left()
        if self._variant is TextFieldVariant.OUTLINED:
            floating_left = rect.left() + HORIZONTAL_PADDING - 4
            floating_top = rect.top() - 8
        else:
            floating_left = left
            floating_top = rect.top() + 8
        if self._multiline:
            resting_top = rect.top() + 16
        else:
            resting_top = rect.center().y() - resting_style.line_height / 2
        top = resting_top + (floating_top - resting_top) * progress
        x = left + (floating_left - left) * progress
        height = (
            resting_style.line_height
            + (floating_style.line_height - resting_style.line_height)
            * progress
        )
        width = rect.right() - HORIZONTAL_PADDING - x
        return QtCore.QRectF(x, top, max(0.0, width), height), size, progress

    def _paint_label(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        del rect
        if not self._label:
            return
        label_rect, size, progress = self._label_metrics()
        interpolated = self._label_style(size, label_rect.height(), progress)
        color = self._label_color()
        if self._variant is TextFieldVariant.OUTLINED and progress > 0:
            # 标签文字向缺口内侧退 4dp，两侧各留 4dp 空隙。
            label_rect = QtCore.QRectF(
                label_rect.left() + 4,
                label_rect.top(),
                label_rect.width(),
                label_rect.height(),
            )
        typography.paint_text(
            painter,
            self.visual_rect(label_rect),
            self._label,
            interpolated,
            color,
            self.start_alignment(),
        )

    def _label_style(
        self, size: float, line_height: float, progress: float
    ) -> typography_tokens.TypeStyle:
        style = self.theme.style(LABEL_STYLE)
        return typography_tokens.TypeStyle(
            style.role,
            style.family,
            size,
            line_height,
            style.weight,
            style.tracking + (0.4 - style.tracking) * progress,
        )

    def notch_rect(self) -> QtCore.QRectF | None:
        """outlined 样式下浮动标签在边框上开出的缺口，未浮起时为 None。"""
        if self._variant is not TextFieldVariant.OUTLINED or not self._label:
            return None
        label_rect, size, progress = self._label_metrics()
        if progress <= 0.0:
            return None
        interpolated = self._label_style(size, label_rect.height(), progress)
        width = typography.text_width(self._label, interpolated) + 8
        return self.visual_rect(
            QtCore.QRectF(
                label_rect.left(),
                label_rect.top(),
                width * progress,
                label_rect.height(),
            )
        )

    def _paint_outline(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        painter.save()
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        notch = self.notch_rect()
        if notch is not None:
            # 不依赖背景色填充：直接把缺口从描边的绘制区域裁掉，任何背景
            # （包括透明背景）下标签处的边框都不会显示。
            clip = QtGui.QRegion(self.rect()).subtracted(
                QtGui.QRegion(notch.toAlignedRect())
            )
            painter.setClipRegion(clip)
        self._stroke_outline(
            painter, rect, INDICATOR_WIDTH, self._resting_indicator_color()
        )
        active = self._active_progress()
        if active > 0.001:
            painter.setOpacity(active)
            self._stroke_outline(
                painter,
                rect,
                FOCUSED_INDICATOR_WIDTH,
                self._active_indicator_color(),
            )
        painter.restore()

    def _stroke_outline(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        width: float,
        color: QtGui.QColor,
    ) -> None:
        half = width / 2
        path = shape_utils.rounded_rect_path(
            rect.adjusted(half, half, -half, -half),
            shape_utils.outset_shape(self._container_shape(), -half),
        )
        painter.setPen(QtGui.QPen(color, width))
        painter.drawPath(path)

    def _paint_icons(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        if self._leading_icon is not None:
            self._leading_icon.paint(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        rect.left() + ICON_PADDING,
                        rect.top() + (CONTAINER_HEIGHT - ICON_SIZE) / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    )
                ),
                self._icon_color(False),
            )
        trailing = self.trailing_icon
        if trailing is not None:
            right = rect.right() - self.trailing_reserved_width()
            trailing.paint(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - ICON_PADDING - ICON_SIZE,
                        rect.top() + (CONTAINER_HEIGHT - ICON_SIZE) / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    )
                ),
                self._icon_color(True),
            )

    def _paint_affixes(self, painter: QtGui.QPainter) -> None:
        if not self._prefix and not self._suffix:
            return
        if not self._floating() and self._label:
            return
        # 编辑器矩形已镜像，先换回逻辑坐标再放置前后缀。
        editor = self.visual_rect(QtCore.QRectF(self._editor_rect()))
        color = (
            self._supporting_color()
            if not self._disabled()
            else self._text_color()
        )
        if self._prefix:
            width = typography.text_width(self._prefix, INPUT_STYLE)
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        editor.left() - width - 2,
                        editor.top(),
                        width,
                        editor.height(),
                    )
                ),
                self._prefix,
                INPUT_STYLE,
                color,
                self.start_alignment(),
            )
        if self._suffix:
            width = typography.text_width(self._suffix, INPUT_STYLE)
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        editor.right() + 2, editor.top(), width, editor.height()
                    )
                ),
                self._suffix,
                INPUT_STYLE,
                color,
                self.start_alignment(),
            )

    def _paint_supporting(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        if not self._has_supporting():
            return
        top = self.supporting_top()
        color = self._supporting_color()
        counter = ""
        if self._max_length is not None:
            counter = f"{len(self.text)}/{self._max_length}"
        counter_width = (
            typography.text_width(counter, SUPPORTING_STYLE) + 16
            if counter
            else 0.0
        )
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(
                    rect.left() + HORIZONTAL_PADDING,
                    top,
                    rect.width() - 2 * HORIZONTAL_PADDING - counter_width,
                    SUPPORTING_HEIGHT,
                )
            ),
            self.supporting_message(),
            SUPPORTING_STYLE,
            color,
            self.start_alignment(),
        )
        if counter:
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        rect.right() - HORIZONTAL_PADDING - counter_width + 16,
                        top,
                        counter_width - 16,
                        SUPPORTING_HEIGHT,
                    )
                ),
                counter,
                SUPPORTING_STYLE,
                color,
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )

    # ---- 事件 -------------------------------------------------------------

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._hovered = True
        self.update()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._hovered = False
        self.update()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() != QtCore.Qt.MouseButton.LeftButton
            or self._disabled()
        ):
            super().mousePressEvent(event)
            return
        if self.trailing_icon is not None and self.trailing_rect().contains(
            event.position()
        ):
            self._trailing_pressed = True
        elif self.container_rect().contains(event.position()):
            self._edit.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._trailing_pressed:
            self._trailing_pressed = False
            if self.trailing_rect().contains(event.position()):
                if self._show_clear():
                    self.clear()
                    self._edit.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
                elif self._password:
                    self.set_password_visible(not self._password_visible)
                    self.trailing_icon_clicked.emit()
                else:
                    self.trailing_icon_clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._apply_editor_style()
            self.update()


class FilledTextField(TextField):
    """filled 样式文本框。"""

    def __init__(self, label: str = "", text: str = "", **kwargs) -> None:
        kwargs.pop("variant", None)
        super().__init__(label, text, TextFieldVariant.FILLED, **kwargs)


class OutlinedTextField(TextField):
    """outlined 样式文本框。"""

    def __init__(self, label: str = "", text: str = "", **kwargs) -> None:
        kwargs.pop("variant", None)
        super().__init__(label, text, TextFieldVariant.OUTLINED, **kwargs)
