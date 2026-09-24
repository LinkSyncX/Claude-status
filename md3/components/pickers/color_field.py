"""颜色文本框（Color field）。

轮廓文本框显示 ``#RRGGBB``，前置位置以当前颜色画一个实心圆作为色块，
尾部的调色板图标打开 ``ColorPickerDialog``；也可以直接键入十六进制值，
失焦或回车时解析并发出 ``color_changed``。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.pickers import color_picker
from md3.components.text_fields import text_field
from md3.theme import theme as theme_module

_HEX_PATTERN = QtCore.QRegularExpression("#?[0-9A-Fa-f]{0,6}")


def parse_hex(text: str) -> QtGui.QColor | None:
    """解析 ``#RGB`` / ``#RRGGBB``（可不带 #），无效返回 None。"""
    digits = text.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(char * 2 for char in digits)
    if len(digits) != 6:
        return None
    color = QtGui.QColor(f"#{digits}")
    return color if color.isValid() else None


class ColorField(text_field.OutlinedTextField):
    """颜色文本框。

    Args:
        label: 浮动标签。
        color: 初始颜色。
        presets: 传给颜色对话框的预设颜色。
        parent: 父控件。
    """

    color_changed = QtCore.Signal(QtGui.QColor)

    def __init__(
        self,
        label: str | None = None,
        color: QtGui.QColor | str | int = "#6750A4",
        presets: list[QtGui.QColor | str | int] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._color = theme_module.qcolor(theme_module.parse_seed(color))
        self._presets = presets
        super().__init__(
            i18n.tr("pick_color") if label is None else label,
            self._color.name().upper(),
            leading_icon="circle",
            trailing_icon="palette",
            parent=parent,
        )
        # 色块用填充版的 circle 图标绘制。
        if self._leading_icon is not None:
            self._leading_icon = self._leading_icon.with_fill(True)
        self.editor.setValidator(
            QtGui.QRegularExpressionValidator(_HEX_PATTERN, self.editor)
        )
        self.trailing_icon_clicked.connect(self.open_dialog)
        self.editing_finished.connect(self._commit_text)
        self.return_pressed.connect(self._commit_text)

    @property
    def selected_color(self) -> QtGui.QColor:
        """当前颜色（``color()`` 保留给基类按色彩角色取色）。"""
        return QtGui.QColor(self._color)

    def set_selected_color(self, color: QtGui.QColor | str | int) -> None:
        """设置颜色并同步文字，变化时发出 ``color_changed``。"""
        new = theme_module.qcolor(theme_module.parse_seed(color))
        changed = new.rgb() != self._color.rgb()
        self._color = new
        self.set_text(new.name().upper())
        self.set_error(False)
        if changed:
            self.color_changed.emit(QtGui.QColor(new))
        self.update()

    def open_dialog(self) -> None:
        """打开颜色选择对话框。"""
        dialog = color_picker.ColorPickerDialog(
            self._color, presets=self._presets, parent=self
        )
        dialog.color_selected.connect(self.set_selected_color)
        dialog.open()

    def _commit_text(self) -> None:
        parsed = parse_hex(self.text)
        if parsed is None:
            self.set_error(True, i18n.tr("invalid_hex"))
            return
        self.set_selected_color(parsed)

    @override
    def _icon_color(self, trailing: bool) -> QtGui.QColor:
        if trailing:
            return super()._icon_color(trailing)
        # 前置图标是实心圆，用当前颜色填充作为色块。
        return QtGui.QColor(self._color)
