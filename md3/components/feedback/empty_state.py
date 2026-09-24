"""空状态（Empty state）。

列表、搜索结果或页面没有内容时的占位：居中的图标（或插图）、标题、说明
文字与最多两个操作按钮（主操作为填充按钮、次操作为文字按钮）。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import common as buttons
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import spacing
from md3.tokens import typography as typography_tokens

ICON_SIZE = 48.0
MAX_TEXT_WIDTH = 360
HEADLINE_STYLE = typography_tokens.TypeRole.TITLE_LARGE
SUPPORTING_STYLE = typography_tokens.TypeRole.BODY_MEDIUM


class _Illustration(widget.MaterialWidget):
    """图标或图片。"""

    def __init__(
        self,
        icon: icons.IconLike,
        image: QtGui.QPixmap | None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon = icons.coerce(icon, ICON_SIZE)
        self._image = image
        if image is not None:
            size = image.deviceIndependentSize().toSize()
            self.setFixedSize(size)
        else:
            self.setFixedSize(round(ICON_SIZE), round(ICON_SIZE))

    def set_icon(self, icon: icons.IconLike) -> None:
        """更换图标。"""
        self._icon = icons.coerce(icon, ICON_SIZE)
        self._image = None
        self.setFixedSize(round(ICON_SIZE), round(ICON_SIZE))
        self.update()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        if self._image is not None:
            painter.drawPixmap(rect.topLeft(), self._image)
        elif self._icon is not None:
            self._icon.paint(painter, rect, self.color("on_surface_variant"))


class EmptyState(QtWidgets.QWidget):
    """空状态。

    Args:
        headline: 标题。
        supporting_text: 说明文字。
        icon: 图标（默认 ``inbox``）。
        image: 插图；提供时代替图标。
        parent: 父控件。
    """

    def __init__(
        self,
        headline: str,
        supporting_text: str = "",
        icon: icons.IconLike = "inbox",
        image: QtGui.QPixmap | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._actions: list[buttons.Button] = []
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
        )
        layout.setSpacing(round(spacing.SPACE_2))
        layout.addStretch()
        self._illustration = _Illustration(icon, image)
        layout.addWidget(
            self._illustration, 0, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        layout.addSpacing(round(spacing.SPACE_2))
        self._headline = typography.Label(
            headline, HEADLINE_STYLE, "on_surface"
        )
        self._headline.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._headline.setWordWrap(True)
        self._headline.setMaximumWidth(MAX_TEXT_WIDTH)
        layout.addWidget(
            self._headline, 0, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        self._supporting = typography.Label(
            supporting_text, SUPPORTING_STYLE, "on_surface_variant"
        )
        self._supporting.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._supporting.setWordWrap(True)
        self._supporting.setMaximumWidth(MAX_TEXT_WIDTH)
        self._supporting.setVisible(bool(supporting_text))
        layout.addWidget(
            self._supporting, 0, QtCore.Qt.AlignmentFlag.AlignHCenter
        )
        self._actions_layout = QtWidgets.QHBoxLayout()
        self._actions_layout.setContentsMargins(0, round(spacing.SPACE_4), 0, 0)
        self._actions_layout.setSpacing(round(spacing.SPACE_2))
        self._actions_layout.addStretch()
        self._actions_layout.addStretch()
        layout.addLayout(self._actions_layout)
        layout.addStretch()

    @property
    def headline(self) -> str:
        """标题。"""
        return self._headline.text()

    def set_headline(self, headline: str) -> None:
        """设置标题。"""
        self._headline.setText(headline)

    def set_supporting_text(self, text: str) -> None:
        """设置说明文字。"""
        self._supporting.setText(text)
        self._supporting.setVisible(bool(text))

    def set_icon(self, icon: icons.IconLike) -> None:
        """更换图标。"""
        self._illustration.set_icon(icon)

    def add_action(self, text: str, primary: bool = True) -> buttons.Button:
        """追加操作按钮：主操作为填充按钮，次操作为文字按钮。"""
        button: buttons.Button = (
            buttons.FilledButton(text) if primary else buttons.TextButton(text)
        )
        self._actions.append(button)
        # 操作居中：夹在两个弹性空间之间。
        self._actions_layout.insertWidget(
            self._actions_layout.count() - 1, button
        )
        return button

    @property
    def action_buttons(self) -> list[buttons.Button]:
        """操作按钮。"""
        return list(self._actions)
