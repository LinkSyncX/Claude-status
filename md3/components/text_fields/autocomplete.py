"""带自动补全的文本框与标签输入框。

``AutocompleteTextField`` 在输入时按子串过滤候选，并在文本框下方以不
夺取焦点的浮层列出建议：方向键高亮、回车或点击选择、Esc 收起。
``TagField`` 在其基础上把确认的输入变为纸片组中的输入纸片，回车或逗号
确认、空文本时退格删除最后一个标签。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.chips import chip as chip_module
from md3.components.chips import group as chip_group
from md3.components.text_fields import text_field
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ROW_HEIGHT = 48.0
ROW_PADDING = 16.0
VERTICAL_PADDING = 8.0
SHADOW_MARGIN = 12
MAX_SUGGESTIONS = 8
ROW_STYLE = typography_tokens.TypeRole.BODY_LARGE
ELEVATION = elevation.Level.LEVEL_2

Filter = Callable[[str, Sequence[str]], list[str]]


def default_filter(query: str, candidates: Sequence[str]) -> list[str]:
    """默认过滤：忽略大小写，前缀匹配优先于包含匹配。"""
    query = query.strip().lower()
    if not query:
        return list(candidates)
    starts = [c for c in candidates if c.lower().startswith(query)]
    contains = [
        c
        for c in candidates
        if query in c.lower() and not c.lower().startswith(query)
    ]
    return starts + contains


class SuggestionPopup(widget.MaterialWidget):
    """不夺取焦点的建议列表浮层（作为文本框所在窗口的子控件浮在最上层）。"""

    selected = QtCore.Signal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.setMouseTracking(True)
        self.hide()
        self._items: list[str] = []
        self._query = ""
        self._highlight = -1
        self._hovered = -1
        self._width = 240

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.List

    @override
    def accessible_value(self) -> str:
        if 0 <= self._highlight < len(self._items):
            return self._items[self._highlight]
        return ""

    @property
    def items(self) -> list[str]:
        """当前显示的建议。"""
        return list(self._items)

    @property
    def highlighted(self) -> int:
        """键盘高亮的行，-1 表示无。"""
        return self._highlight

    def set_items(self, items: Sequence[str], query: str, width: int) -> None:
        """替换建议并按宽度重算尺寸。"""
        self._items = list(items)
        self._query = query
        self._highlight = 0 if self._items else -1
        self._hovered = -1
        self._width = max(160, width)
        self.resize(self.sizeHint())
        self.update()

    def move_highlight(self, delta: int) -> None:
        """上下移动高亮行（循环）。"""
        if not self._items:
            return
        self._highlight = (self._highlight + delta) % len(self._items)
        self.update()

    def accept_highlighted(self) -> bool:
        """选择高亮行，返回是否有选择。"""
        if 0 <= self._highlight < len(self._items):
            self.selected.emit(self._items[self._highlight])
            return True
        return False

    def container_rect(self) -> QtCore.QRectF:
        """容器矩形（阴影边距之内）。"""
        return QtCore.QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )

    def row_rect(self, index: int) -> QtCore.QRectF:
        """第 index 行的矩形。"""
        container = self.container_rect()
        return QtCore.QRectF(
            container.left(),
            container.top() + VERTICAL_PADDING + index * ROW_HEIGHT,
            container.width(),
            ROW_HEIGHT,
        )

    def row_at(self, position: QtCore.QPointF) -> int:
        """位置对应的行下标。"""
        for index in range(len(self._items)):
            if self.row_rect(index).contains(position):
                return index
        return -1

    @override
    def sizeHint(self) -> QtCore.QSize:
        height = 2 * VERTICAL_PADDING + ROW_HEIGHT * max(1, len(self._items))
        return QtCore.QSize(
            self._width + 2 * SHADOW_MARGIN, round(height) + 2 * SHADOW_MARGIN
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        container = self.container_rect()
        shape = shape_tokens.SHAPE_EXTRA_SMALL
        elevation_utils.paint_shadow(
            painter,
            container,
            shape,
            ELEVATION,
            self.color("shadow"),
            self.devicePixelRatioF(),
        )
        path = shape_utils.rounded_rect_path(container, shape)
        shape_utils.fill_shape(painter, path, self.color("surface_container"))
        painter.save()
        painter.setClipPath(path)
        query = self._query.lower()
        for index, item in enumerate(self._items):
            rect = self.row_rect(index)
            if index == self._highlight:
                painter.fillRect(
                    rect,
                    theme_module.with_alpha(
                        self.color("on_surface"),
                        state_tokens.FOCUS_STATE_LAYER_OPACITY,
                    ),
                )
            elif index == self._hovered:
                painter.fillRect(
                    rect,
                    theme_module.with_alpha(
                        self.color("on_surface"),
                        state_tokens.HOVER_STATE_LAYER_OPACITY,
                    ),
                )
            text_rect = rect.adjusted(ROW_PADDING, 0, -ROW_PADDING, 0)
            start = item.lower().find(query) if query else -1
            if start < 0:
                typography.paint_text(
                    painter,
                    text_rect,
                    item,
                    ROW_STYLE,
                    self.color("on_surface"),
                )
                continue
            # 匹配片段用 primary 色高亮。
            before, match, after = (
                item[:start],
                item[start : start + len(query)],
                item[start + len(query) :],
            )
            x = text_rect.left()
            for fragment, color in (
                (before, self.color("on_surface")),
                (match, self.color("primary")),
                (after, self.color("on_surface")),
            ):
                if not fragment:
                    continue
                width = typography.text_width(fragment, ROW_STYLE)
                typography.paint_text(
                    painter,
                    QtCore.QRectF(x, rect.top(), width + 2, rect.height()),
                    fragment,
                    ROW_STYLE,
                    color,
                    elide=False,
                )
                x += width
        painter.restore()

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hovered = self.row_at(event.position())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        index = self.row_at(event.position())
        if index >= 0:
            self.selected.emit(self._items[index])
        event.accept()


class AutocompleteTextField(text_field.TextField):
    """带自动补全的文本框。

    Args:
        label: 浮动标签。
        suggestions: 候选列表。
        variant: 样式（默认 outlined）。
        min_chars: 至少输入多少字符后才显示建议。
        max_suggestions: 最多显示的建议数。
        matcher: 自定义过滤函数 ``(query, candidates) -> matches``，默认
            为 :func:`default_filter`。
        **kwargs: 其余参数同 ``TextField``。
    """

    suggestion_selected = QtCore.Signal(str)

    def __init__(
        self,
        label: str = "",
        suggestions: Sequence[str] = (),
        variant: text_field.TextFieldVariant = (
            text_field.TextFieldVariant.OUTLINED
        ),
        min_chars: int = 1,
        max_suggestions: int = MAX_SUGGESTIONS,
        matcher: Filter | None = None,
        **kwargs,
    ) -> None:
        super().__init__(label, variant=variant, **kwargs)
        self._suggestions = list(suggestions)
        self._min_chars = max(0, min_chars)
        self._max_suggestions = max(1, max_suggestions)
        self._filter: Filter = matcher or default_filter
        # 先由文本框持有；显示时再挂到所在窗口下浮在最上层。
        self._popup = SuggestionPopup(self)
        self._popup.selected.connect(self._accept)
        self.destroyed.connect(self._popup.deleteLater)
        self._suppress = False
        self.text_changed.connect(self._refresh_suggestions)

    @property
    def suggestions(self) -> list[str]:
        """候选列表。"""
        return list(self._suggestions)

    def set_suggestions(self, suggestions: Sequence[str]) -> None:
        """替换候选列表。"""
        self._suggestions = list(suggestions)
        self._refresh_suggestions(self.text)

    @property
    def popup(self) -> SuggestionPopup:
        """建议浮层。"""
        return self._popup

    def matches(self, query: str) -> list[str]:
        """按当前过滤函数返回 query 的建议。"""
        return self._filter(query, self._suggestions)[: self._max_suggestions]

    def _refresh_suggestions(self, text: str) -> None:
        if self._suppress:
            return
        query = text.strip()
        if len(query) < self._min_chars or not self.editor.hasFocus():
            self.hide_suggestions()
            return
        items = [item for item in self.matches(query) if item != query]
        if not items:
            self.hide_suggestions()
            return
        host = self.window()
        if self._popup.parentWidget() is not host:
            self._popup.setParent(host)
        self._popup.set_items(items, query, self.width())
        self._position_popup()
        if not self._popup.isVisible():
            self._popup.show()
        self._popup.raise_()

    def _position_popup(self) -> None:
        host = self.window()
        origin = self.mapTo(host, QtCore.QPoint(0, self.height()))
        size = self._popup.size()
        x = origin.x() - SHADOW_MARGIN
        y = origin.y() - SHADOW_MARGIN + 4
        # 下方空间不足且上方够用时翻到文本框上方；水平方向夹在窗口内。
        overflow = y + size.height() > host.height()
        if overflow and origin.y() - self.height() > size.height():
            y = origin.y() - self.height() - size.height() + SHADOW_MARGIN - 4
        x = max(
            -SHADOW_MARGIN, min(x, host.width() - size.width() + SHADOW_MARGIN)
        )
        self._popup.move(x, y)

    def hide_suggestions(self) -> None:
        """收起建议。"""
        if self._popup.isVisible():
            self._popup.hide()

    def show_suggestions(self) -> None:
        """按当前文字显示建议（用于程序触发）。"""
        self._refresh_suggestions(self.text)

    def _accept(self, value: str) -> None:
        self._suppress = True
        try:
            self.set_text(value)
        finally:
            self._suppress = False
        self.hide_suggestions()
        self.suggestion_selected.emit(value)

    @override
    def editor_key_pressed(self, event: QtGui.QKeyEvent) -> bool:
        if self._handle_key(event):
            return True
        return super().editor_key_pressed(event)

    @override
    def editor_focus_changed(self, focused: bool) -> None:
        if not focused:
            self.hide_suggestions()
        elif self.text.strip():
            QtCore.QTimer.singleShot(0, self.show_suggestions)

    def _handle_key(self, event: QtGui.QKeyEvent) -> bool:
        key = event.key()
        if not self._popup.isVisible():
            if key == QtCore.Qt.Key.Key_Down and self.text.strip():
                self.show_suggestions()
                return True
            return False
        if key == QtCore.Qt.Key.Key_Down:
            self._popup.move_highlight(1)
        elif key == QtCore.Qt.Key.Key_Up:
            self._popup.move_highlight(-1)
        elif key in (
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
            QtCore.Qt.Key.Key_Tab,
        ):
            if not self._popup.accept_highlighted():
                return False
        elif key == QtCore.Qt.Key.Key_Escape:
            self.hide_suggestions()
        else:
            return False
        return True

    @override
    def moveEvent(self, event: QtGui.QMoveEvent) -> None:
        super().moveEvent(event)
        if self._popup.isVisible():
            self._position_popup()

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self.hide_suggestions()


class TagField(QtWidgets.QWidget):
    """标签输入框：文本框 + 输入纸片组。

    Args:
        label: 文本框标签。
        tags: 初始标签。
        suggestions: 自动补全候选。
        max_tags: 标签上限，None 不限。
        allow_duplicates: 是否允许重复标签。
        parent: 父控件。
    """

    tags_changed = QtCore.Signal(list)

    def __init__(
        self,
        label: str | None = None,
        tags: Sequence[str] = (),
        suggestions: Sequence[str] = (),
        max_tags: int | None = None,
        allow_duplicates: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._max_tags = max_tags
        self._allow_duplicates = allow_duplicates
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._field = AutocompleteTextField(
            i18n.tr("tags") if label is None else label,
            suggestions,
            placeholder=i18n.tr("tag_placeholder"),
        )
        self._field.suggestion_selected.connect(self._add_from_field)
        self._field.return_pressed.connect(self._add_from_field)
        self._field.text_changed.connect(self._on_field_text)
        self._field.backspace_on_empty.connect(self._remove_last)
        layout.addWidget(self._field)
        self._group = chip_group.ChipGroup(kind=chip_module.ChipKind.INPUT)
        self._group.chip_removed.connect(lambda _text: self._emit())
        layout.addWidget(self._group)
        for tag in tags:
            self.add_tag(tag)

    @property
    def field(self) -> AutocompleteTextField:
        """内部文本框。"""
        return self._field

    @property
    def chip_group(self) -> chip_group.ChipGroup:
        """内部纸片组。"""
        return self._group

    @property
    def tags(self) -> list[str]:
        """当前标签。"""
        return self._group.texts

    def add_tag(self, text: str) -> bool:
        """添加标签，返回是否成功（空、重复或超出上限时失败）。"""
        text = text.strip().strip(",，")
        if not text:
            return False
        if not self._allow_duplicates and text in self.tags:
            return False
        if self._max_tags is not None and len(self.tags) >= self._max_tags:
            return False
        chip = chip_module.InputChip(text)
        self._group.add_chip(chip)
        self._emit()
        return True

    def remove_tag(self, text: str) -> None:
        """移除标签。"""
        self._group.remove_chip(text)

    def set_tags(self, tags: Sequence[str]) -> None:
        """替换全部标签。"""
        self._group.clear()
        for tag in tags:
            self.add_tag(tag)
        self._emit()

    def _emit(self) -> None:
        self.tags_changed.emit(self.tags)
        self._field.set_error(False)

    def _add_from_field(self, value: str | None = None) -> None:
        text = value if isinstance(value, str) else self._field.text
        if self.add_tag(text):
            self._field.set_text("")
            self._field.hide_suggestions()
        elif text.strip():
            self._field.set_error(True, i18n.tr("tag_rejected"))

    def _on_field_text(self, text: str) -> None:
        if text.endswith((",", "，")):
            self._add_from_field(text[:-1])

    def _remove_last(self) -> None:
        if self.tags:
            self._group.remove_chip(len(self.tags) - 1)
