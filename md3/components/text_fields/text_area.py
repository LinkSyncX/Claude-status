"""多行文本区（Text area）：随内容自动增高的多行文本框。"""

from __future__ import annotations

import math

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components.text_fields import text_field


class TextArea(text_field.TextField):
    """多行文本区。

    默认随内容在 ``min_rows`` 与 ``max_rows`` 之间自动增高；超过
    ``max_rows`` 后出现滚动条。

    Args:
        label: 浮动标签。
        text: 初始文字。
        variant: 样式（默认 outlined）。
        min_rows: 最少显示的行数。
        max_rows: 最多增高到的行数，None 表示不限制。
        auto_grow: 是否随内容自动增高。
        **kwargs: 其余参数同 ``TextField``。
    """

    rows_changed = QtCore.Signal(int)

    def __init__(
        self,
        label: str = "",
        text: str = "",
        variant: text_field.TextFieldVariant = (
            text_field.TextFieldVariant.OUTLINED
        ),
        min_rows: int = 3,
        max_rows: int | None = 8,
        auto_grow: bool = True,
        **kwargs,
    ) -> None:
        kwargs.pop("multiline", None)
        kwargs.pop("rows", None)
        self._min_rows = max(1, min_rows)
        self._max_rows = (
            None if max_rows is None else max(self._min_rows, max_rows)
        )
        self._auto_grow = auto_grow
        super().__init__(
            label, text, variant, multiline=True, rows=self._min_rows, **kwargs
        )
        editor = self.editor
        assert isinstance(editor, QtWidgets.QPlainTextEdit)
        editor.setLineWrapMode(
            QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth
        )
        layout = editor.document().documentLayout()
        layout.documentSizeChanged.connect(self._fit_rows)
        self._fit_rows()

    @property
    def rows(self) -> int:
        """当前显示的行数。"""
        return self._rows

    @property
    def min_rows(self) -> int:
        """最少行数。"""
        return self._min_rows

    @property
    def max_rows(self) -> int | None:
        """最多行数。"""
        return self._max_rows

    def set_rows_range(self, min_rows: int, max_rows: int | None) -> None:
        """设置行数范围。"""
        self._min_rows = max(1, min_rows)
        self._max_rows = (
            None if max_rows is None else max(self._min_rows, max_rows)
        )
        self._fit_rows()

    @property
    def auto_grow(self) -> bool:
        """是否自动增高。"""
        return self._auto_grow

    def set_auto_grow(self, auto_grow: bool) -> None:
        """设置是否自动增高。"""
        self._auto_grow = auto_grow
        self._fit_rows()

    def content_lines(self) -> int:
        """当前内容（含自动换行）占据的行数。"""
        editor = self.editor
        assert isinstance(editor, QtWidgets.QPlainTextEdit)
        # QPlainTextDocumentLayout 的文档高度以“行”为单位。
        height = editor.document().documentLayout().documentSize().height()
        return max(1, math.ceil(height - 1e-6))

    def _fit_rows(self, *_args) -> None:
        if self._auto_grow:
            rows = max(self._min_rows, self.content_lines())
            if self._max_rows is not None:
                rows = min(rows, self._max_rows)
        else:
            rows = self._min_rows
        if rows == self._rows:
            return
        self._rows = rows
        self.updateGeometry()
        self._layout_editor()
        self.update()
        self.rows_changed.emit(rows)
