"""画廊页面的公共构建工具。"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.core import typography
from md3.tokens import spacing


class Page(QtWidgets.QWidget):
    """一个可滚动的画廊页面：标题、说明与若干分节。"""

    def __init__(
        self,
        title: str,
        description: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
            round(spacing.SPACE_10),
        )
        self._layout.setSpacing(round(spacing.SPACE_4))
        self._layout.addWidget(
            typography.Label(title, "headline-medium", "on_surface")
        )
        if description:
            label = typography.Label(
                description, "body-large", "on_surface_variant"
            )
            label.setWordWrap(True)
            self._layout.addWidget(label)

    @property
    def body(self) -> QtWidgets.QVBoxLayout:
        """页面主布局。"""
        return self._layout

    def section(
        self, title: str, description: str = ""
    ) -> QtWidgets.QVBoxLayout:
        """新增一个分节并返回其布局。"""
        self._layout.addSpacing(round(spacing.SPACE_2))
        self._layout.addWidget(
            typography.Label(title, "title-medium", "on_surface")
        )
        if description:
            label = typography.Label(
                description, "body-medium", "on_surface_variant"
            )
            label.setWordWrap(True)
            self._layout.addWidget(label)
        section = QtWidgets.QVBoxLayout()
        section.setSpacing(round(spacing.SPACE_3))
        self._layout.addLayout(section)
        return section

    def row(
        self,
        target: QtWidgets.QVBoxLayout,
        widgets: Iterable[QtWidgets.QWidget],
        gap: float = spacing.SPACE_2,
        align_top: bool = False,
    ) -> QtWidgets.QHBoxLayout:
        """在分节中添加一行控件。"""
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(round(gap))
        alignment = (
            QtCore.Qt.AlignmentFlag.AlignTop
            if align_top
            else QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        for widget in widgets:
            row.addWidget(widget, 0, alignment)
        row.addStretch()
        target.addLayout(row)
        return row

    def finish(self) -> None:
        """在末尾加入弹性空间。"""
        self._layout.addStretch()


def wrap_scroll(page: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    """把页面放进可滚动区域。"""
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setWidget(page)
    return scroll
