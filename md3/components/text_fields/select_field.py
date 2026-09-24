"""下拉选择文本框（Select field）。

M3 的 exposed dropdown menu 以文本框呈现：filled / outlined 容器、浮动
标签、辅助文字与错误态都与 ``TextField`` 一致，尾部为下拉箭头，点击后
在下方弹出带勾选标记的 ``Menu``（选项多时可滚动、支持首字母跳转）。

``editable=True`` 时文本框可以输入：输入内容实时过滤选项并以建议浮层
显示，回车或点击选择；失焦时若文字与某个选项一致则选中它，否则按
``allow_custom`` 决定保留自定义文字还是恢复到上一个选项。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui

from md3.components.menus import menu as menu_module
from md3.components.text_fields import autocomplete
from md3.components.text_fields import text_field

ARROW_ICON = "arrow_drop_down"
ARROW_OPEN_ICON = "arrow_drop_up"
MENU_GAP = 4


class SelectField(text_field.TextField):
    """下拉选择文本框。

    Args:
        label: 浮动标签。
        options: 选项文字列表。
        selected_index: 初始选中下标，-1 为未选择。
        variant: 样式（默认 outlined）。
        editable: 为真时允许输入并过滤选项。
        allow_custom: 可编辑时是否接受不在选项中的自定义文字。
        max_menu_height: 下拉菜单最大高度（px），None 只受屏幕限制。
        **kwargs: 其余参数同 ``TextField``（``supporting_text`` 等）。
    """

    selection_changed = QtCore.Signal(int)
    opened = QtCore.Signal()
    closed = QtCore.Signal()

    def __init__(
        self,
        label: str = "",
        options: Sequence[str] = (),
        selected_index: int = -1,
        variant: text_field.TextFieldVariant = (
            text_field.TextFieldVariant.OUTLINED
        ),
        editable: bool = False,
        allow_custom: bool = False,
        max_menu_height: float | None = None,
        **kwargs,
    ) -> None:
        kwargs.pop("multiline", None)
        kwargs.pop("password", None)
        kwargs.pop("trailing_icon", None)
        kwargs.pop("read_only", None)
        self._options = list(options)
        self._selected = (
            selected_index if 0 <= selected_index < len(self._options) else -1
        )
        # 可编辑模式下输入自定义文字会暂时清空选择；失焦时若不接受自定义
        # 文字则恢复到这里记录的上一个有效选择。
        self._committed = self._selected
        self._editable = editable
        self._allow_custom = allow_custom
        self._open = False
        self._syncing = False
        initial = self._options[self._selected] if self._selected >= 0 else ""
        super().__init__(
            label,
            initial,
            variant,
            trailing_icon=ARROW_ICON,
            read_only=not editable,
            **kwargs,
        )
        if not editable:
            self.editor.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._menu = menu_module.Menu(max_height=max_menu_height, parent=self)
        self._menu.triggered.connect(self._on_menu_triggered)
        self._menu.closed.connect(self._on_menu_closed)
        self._popup: autocomplete.SuggestionPopup | None = None
        if editable:
            self._popup = autocomplete.SuggestionPopup(self)
            self._popup.selected.connect(self._on_suggestion_selected)
            self.destroyed.connect(self._popup.deleteLater)
            self.text_changed.connect(self._on_editable_text)
        self.trailing_icon_clicked.connect(self.toggle_menu)

    # ---- 选项与选择 -------------------------------------------------------

    @property
    def options(self) -> list[str]:
        """选项列表。"""
        return list(self._options)

    def set_options(
        self, options: Sequence[str], keep_selection: bool = True
    ) -> None:
        """替换选项；``keep_selection`` 为真时按文字保留当前选择。"""
        current = self.selected_text
        self._options = list(options)
        index = (
            self._options.index(current)
            if keep_selection and current in self._options
            else -1
        )
        self._apply_selection(
            index, sync_text=index >= 0 or not self._allow_custom
        )

    def add_option(self, text: str) -> None:
        """追加一个选项。"""
        self._options.append(text)

    @property
    def selected_index(self) -> int:
        """当前选中下标，-1 表示未选择（或为自定义文字）。"""
        return self._selected

    @property
    def selected_text(self) -> str:
        """当前选中的选项文字；未选择时为空字符串。"""
        if 0 <= self._selected < len(self._options):
            return self._options[self._selected]
        return ""

    @property
    def value(self) -> str:
        """当前值：选中的选项，或可编辑模式下的自定义文字。"""
        if self._selected >= 0:
            return self.selected_text
        return self.text if self._editable and self._allow_custom else ""

    def set_selected_index(self, index: int) -> None:
        """设置选中下标（-1 清空），变化时发出 ``selection_changed``。"""
        if index < -1 or index >= len(self._options):
            return
        self._apply_selection(index, sync_text=True)

    def set_selected_text(self, text: str) -> None:
        """按文字选中选项；不在选项中时清空选择。"""
        self.set_selected_index(
            self._options.index(text) if text in self._options else -1
        )

    def _apply_selection(self, index: int, sync_text: bool) -> None:
        changed = index != self._selected
        self._selected = index
        self._committed = index
        if sync_text:
            self._sync_text(self.selected_text)
        self.set_error(False)
        if changed:
            self.selection_changed.emit(index)
        self.update()

    def _sync_text(self, text: str) -> None:
        if text == self.text:
            return
        self._syncing = True
        try:
            self.set_text(text)
        finally:
            self._syncing = False

    @property
    def editable(self) -> bool:
        """是否可输入。"""
        return self._editable

    @property
    def is_open(self) -> bool:
        """下拉菜单或建议浮层是否展开。"""
        return self._open or (
            self._popup is not None and self._popup.isVisible()
        )

    @property
    def menu(self) -> menu_module.Menu:
        """下拉菜单。"""
        return self._menu

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ComboBox

    @override
    def accessible_value(self) -> str:
        return self.value

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        state.hasPopup = True
        state.expandable = True
        state.expanded = self.is_open
        state.collapsed = not self.is_open

    # ---- 菜单 -------------------------------------------------------------

    def open_menu(self) -> None:
        """弹出选项菜单。"""
        if self._open or not self.isEnabled() or not self._options:
            return
        self._menu.set_items(
            [
                menu_module.MenuItem(
                    text=text,
                    checkable=True,
                    checked=index == self._selected,
                    key=index,
                )
                for index, text in enumerate(self._options)
            ]
        )
        self._menu.setLayoutDirection(self.layoutDirection())
        self._menu.setMinimumWidth(self.width() + 2 * menu_module.SHADOW_MARGIN)
        container = self.container_rect()
        anchor = self.mapToGlobal(
            QtCore.QPoint(0, round(container.bottom()) + MENU_GAP)
        )
        self._open = True
        self.set_trailing_icon(ARROW_OPEN_ICON)
        self._menu.popup(anchor)
        if self._selected >= 0:
            self._menu.focus_item(self._selected)
        self.opened.emit()

    def close_menu(self) -> None:
        """收起选项菜单。"""
        if self._open:
            self._menu.hide()

    def toggle_menu(self) -> None:
        """切换选项菜单。"""
        if self._open:
            self.close_menu()
        else:
            self.hide_suggestions()
            self.open_menu()

    def _on_menu_triggered(self, item: menu_module.MenuItem) -> None:
        self.set_selected_index(int(item.key))

    def _on_menu_closed(self) -> None:
        self._open = False
        self.set_trailing_icon(ARROW_ICON)
        self.closed.emit()
        self.update()

    # ---- 可编辑模式 -------------------------------------------------------

    def matches(self, query: str) -> list[str]:
        """按输入过滤后的选项。"""
        return autocomplete.default_filter(query, self._options)

    def _on_editable_text(self, text: str) -> None:
        if self._syncing or self._popup is None:
            return
        if self._selected >= 0 and text != self.selected_text:
            # 用户改动文字后当前选择失效。
            self._selected = -1
            self.selection_changed.emit(-1)
        self.show_suggestions()

    def show_suggestions(self) -> None:
        """按当前文字显示过滤后的选项（可编辑模式）。"""
        if self._popup is None or not self.editor.hasFocus():
            return
        items = self.matches(self.text.strip())
        if not items:
            self.hide_suggestions()
            return
        host = self.window()
        if self._popup.parentWidget() is not host:
            self._popup.setParent(host)
        self._popup.set_items(items, self.text.strip(), self.width())
        origin = self.mapTo(
            host,
            QtCore.QPoint(0, round(self.container_rect().bottom()) + MENU_GAP),
        )
        self._popup.move(
            origin.x() - autocomplete.SHADOW_MARGIN,
            origin.y() - autocomplete.SHADOW_MARGIN,
        )
        if not self._popup.isVisible():
            self._popup.show()
        self._popup.raise_()

    def hide_suggestions(self) -> None:
        """收起建议浮层。"""
        if self._popup is not None and self._popup.isVisible():
            self._popup.hide()

    def _on_suggestion_selected(self, text: str) -> None:
        self.hide_suggestions()
        self.set_selected_text(text)

    def _commit_text(self) -> None:
        """失焦时把输入解析为选择。"""
        text = self.text.strip()
        lowered = text.lower()
        for index, option in enumerate(self._options):
            if option.lower() == lowered:
                self._apply_selection(index, sync_text=True)
                return
        if not text:
            self._apply_selection(-1, sync_text=False)
            return
        if self._allow_custom:
            if self._selected != -1:
                self._selected = -1
                self.selection_changed.emit(-1)
            self._committed = -1
            return
        # 不接受自定义文字：恢复上一个有效选择。
        self._apply_selection(self._committed, sync_text=True)

    # ---- 事件 -------------------------------------------------------------

    @override
    def editor_key_pressed(self, event: QtGui.QKeyEvent) -> bool:
        key = event.key()
        if self._popup is not None and self._popup.isVisible():
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
                return super().editor_key_pressed(event)
            return True
        if key == QtCore.Qt.Key.Key_Down or (
            not self._editable
            and key
            in (
                QtCore.Qt.Key.Key_Space,
                QtCore.Qt.Key.Key_Return,
                QtCore.Qt.Key.Key_Enter,
            )
        ):
            if self._editable and self.text.strip():
                self.show_suggestions()
            else:
                self.open_menu()
            return True
        if not self._editable and key not in (
            QtCore.Qt.Key.Key_Tab,
            QtCore.Qt.Key.Key_Backtab,
            QtCore.Qt.Key.Key_Escape,
        ):
            # 不可编辑：字母键交给菜单的首字母跳转。
            text = event.text()
            if text and text.isprintable() and not text.isspace():
                self.open_menu()
                self._menu.keyPressEvent(event)
            return True
        return super().editor_key_pressed(event)

    @override
    def editor_focus_changed(self, focused: bool) -> None:
        if not focused:
            self.hide_suggestions()
            if self._editable:
                self._commit_text()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            not self._editable
            and event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.isEnabled()
            and self.container_rect().contains(event.position())
        ):
            self.editor.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            self.toggle_menu()
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self.hide_suggestions()
        self.close_menu()
