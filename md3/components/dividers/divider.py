"""分隔线（Divider）：1dp 的 ``outline_variant`` 细线。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import widget

THICKNESS = 1.0
INSET = 16.0


class Divider(widget.MaterialWidget):
    """分隔线。

    Args:
        vertical: 为真时为垂直分隔线。
        inset: 起始端缩进（dp），M3 的 inset 分隔线为 16dp。
        inset_end: 结束端缩进（dp）。
        parent: 父控件。
    """

    def __init__(
        self,
        vertical: bool = False,
        inset: float = 0.0,
        inset_end: float = 0.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._vertical = vertical
        self._inset = inset
        self._inset_end = inset_end
        if vertical:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Fixed,
                QtWidgets.QSizePolicy.Policy.Expanding,
            )
        else:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

    @classmethod
    def inset(cls, parent: QtWidgets.QWidget | None = None) -> Divider:
        """起始端缩进 16dp 的分隔线。"""
        return cls(inset=INSET, parent=parent)

    @classmethod
    def middle_inset(cls, parent: QtWidgets.QWidget | None = None) -> Divider:
        """两端各缩进 16dp 的分隔线。"""
        return cls(inset=INSET, inset_end=INSET, parent=parent)

    @property
    def vertical(self) -> bool:
        """是否垂直。"""
        return self._vertical

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Separator

    def set_insets(self, inset: float, inset_end: float = 0.0) -> None:
        """设置两端缩进。"""
        self._inset = inset
        self._inset_end = inset_end
        self.update()

    @override
    def sizeHint(self) -> QtCore.QSize:
        if self._vertical:
            return QtCore.QSize(int(THICKNESS), 24)
        return QtCore.QSize(24, int(THICKNESS))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(int(THICKNESS), int(THICKNESS))

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        color = self.color("outline_variant")
        if self._vertical:
            line = QtCore.QRectF(
                rect.center().x() - THICKNESS / 2,
                rect.top() + self._inset,
                THICKNESS,
                rect.height() - self._inset - self._inset_end,
            )
        else:
            line = QtCore.QRectF(
                rect.left() + self._inset,
                rect.center().y() - THICKNESS / 2,
                rect.width() - self._inset - self._inset_end,
                THICKNESS,
            )
        painter.fillRect(line, color)
