"""文件路径输入框（File field）：后置按钮打开文件 / 目录选择对话框。"""

from __future__ import annotations

from collections.abc import Callable
import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.text_fields import text_field

Picker = Callable[["FileField"], str | None]


class FileMode(enum.Enum):
    """选择模式。"""

    OPEN_FILE = "open_file"
    SAVE_FILE = "save_file"
    DIRECTORY = "directory"


_ICONS = {
    FileMode.OPEN_FILE: "folder_open",
    FileMode.SAVE_FILE: "save",
    FileMode.DIRECTORY: "folder",
}
_CAPTION_KEYS = {
    FileMode.OPEN_FILE: "choose_file",
    FileMode.SAVE_FILE: "save_to",
    FileMode.DIRECTORY: "choose_folder",
}


def default_caption(mode: FileMode) -> str:
    """当前语言下某个模式的对话框标题。"""
    return i18n.tr(_CAPTION_KEYS[mode])


class FileField(text_field.TextField):
    """文件路径输入框。

    Args:
        label: 浮动标签。
        path: 初始路径。
        mode: 选择模式（打开文件 / 保存文件 / 目录）。
        name_filter: 文件名过滤，如 ``"图片 (*.png *.jpg)"``。
        caption: 对话框标题，默认按模式给出。
        directory: 对话框初始目录，默认取当前路径所在目录。
        variant: 样式（默认 outlined）。
        picker: 自定义选择函数 ``field -> 路径 | None``，替代系统对话框
            （便于测试或嵌入自定义浏览器）。
        **kwargs: 其余参数同 ``TextField``。
    """

    path_changed = QtCore.Signal(str)
    picked = QtCore.Signal(str)

    def __init__(
        self,
        label: str | None = None,
        path: str = "",
        mode: FileMode = FileMode.OPEN_FILE,
        name_filter: str = "",
        caption: str = "",
        directory: str = "",
        variant: text_field.TextFieldVariant = (
            text_field.TextFieldVariant.OUTLINED
        ),
        picker: Picker | None = None,
        **kwargs,
    ) -> None:
        kwargs.pop("multiline", None)
        kwargs.pop("password", None)
        kwargs.setdefault("trailing_icon", _ICONS[mode])
        if label is None:
            label = i18n.tr("file")
        self._mode = mode
        self._name_filter = name_filter
        self._caption = caption
        self._directory = directory
        self._picker = picker
        super().__init__(label, path, variant, **kwargs)
        self.trailing_icon_clicked.connect(self.browse)
        self.text_changed.connect(self.path_changed)

    @property
    def path(self) -> str:
        """当前路径。"""
        return self.text

    def set_path(self, path: str) -> None:
        """设置路径。"""
        self.set_text(path)

    @property
    def mode(self) -> FileMode:
        """选择模式。"""
        return self._mode

    def set_mode(self, mode: FileMode) -> None:
        """设置选择模式并更换后置图标。"""
        self._mode = mode
        self.set_trailing_icon(_ICONS[mode])

    @property
    def name_filter(self) -> str:
        """文件名过滤。"""
        return self._name_filter

    def set_name_filter(self, name_filter: str) -> None:
        """设置文件名过滤。"""
        self._name_filter = name_filter

    def browse(self) -> str | None:
        """打开选择对话框；选定后写入路径并发出 ``picked``。"""
        if not self.isEnabled():
            return None
        result = (
            self._picker(self) if self._picker is not None else self._dialog()
        )
        if result:
            self.set_path(result)
            self.picked.emit(result)
            self.editor.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
        return result or None

    def _start_directory(self) -> str:
        if self._directory:
            return self._directory
        if self.path:
            return QtCore.QFileInfo(self.path).absolutePath()
        return ""

    def _dialog(self) -> str:
        caption = self._caption or default_caption(self._mode)
        parent = self.window()
        start = self._start_directory()
        if self._mode is FileMode.DIRECTORY:
            return QtWidgets.QFileDialog.getExistingDirectory(
                parent, caption, start
            )
        if self._mode is FileMode.SAVE_FILE:
            path, _selected = QtWidgets.QFileDialog.getSaveFileName(
                parent, caption, start or self.path, self._name_filter
            )
            return path
        path, _selected = QtWidgets.QFileDialog.getOpenFileName(
            parent, caption, start, self._name_filter
        )
        return path

    @override
    def accessible_description(self) -> str:
        return super().accessible_description() or default_caption(self._mode)
