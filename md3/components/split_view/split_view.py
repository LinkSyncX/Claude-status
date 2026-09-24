"""分割视图（Split view）：M3 风格的 ``QSplitter``。

分割条为 8dp 宽的透明区域，中间画一条 1dp 的 ``outline_variant`` 线；
悬停或拖动时线中央出现 4dp × 32dp 的 ``primary`` 胶囊把手，并带 200ms
的过渡。其余行为（折叠、比例、保存状态）与 ``QSplitter`` 相同。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.core import shape as shape_utils
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens

HANDLE_WIDTH = 8
LINE_WIDTH = 1.0
GRIP_LENGTH = 32.0
GRIP_THICKNESS = 4.0


class SplitHandle(QtWidgets.QSplitterHandle):
    """带悬停把手的分割条。"""

    def __init__(
        self, orientation: QtCore.Qt.Orientation, parent: QtWidgets.QSplitter
    ) -> None:
        super().__init__(orientation, parent)
        self._hover = animation.AnimatedFloat(self, 0.0, self.update)
        self._pressed = False
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    @property
    def grip_progress(self) -> float:
        """把手出现的进度（0–1）。"""
        return self._hover.value

    def _set_active(self, active: bool) -> None:
        self._hover.animate_to(
            1.0 if active else 0.0, motion.SHORT4, motion.STANDARD
        )

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._set_active(True)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        if not self._pressed:
            self._set_active(False)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        self._pressed = True
        self._set_active(True)
        super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._pressed = False
        if not self.underMouse():
            self._set_active(False)
        super().mouseReleaseEvent(event)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect())
        horizontal = self.orientation() == QtCore.Qt.Orientation.Horizontal
        if horizontal:
            line = QtCore.QRectF(
                rect.center().x() - LINE_WIDTH / 2,
                rect.top(),
                LINE_WIDTH,
                rect.height(),
            )
        else:
            line = QtCore.QRectF(
                rect.left(),
                rect.center().y() - LINE_WIDTH / 2,
                rect.width(),
                LINE_WIDTH,
            )
        painter.fillRect(line, theme.color("outline_variant"))
        progress = self._hover.value
        if progress > 0.001:
            length = GRIP_LENGTH * progress
            if horizontal:
                grip = QtCore.QRectF(
                    rect.center().x() - GRIP_THICKNESS / 2,
                    rect.center().y() - length / 2,
                    GRIP_THICKNESS,
                    length,
                )
            else:
                grip = QtCore.QRectF(
                    rect.center().x() - length / 2,
                    rect.center().y() - GRIP_THICKNESS / 2,
                    length,
                    GRIP_THICKNESS,
                )
            color = theme.color("primary")
            color.setAlphaF(min(1.0, progress))
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(grip, shape_tokens.SHAPE_FULL),
                color,
            )
        painter.end()


class SplitView(QtWidgets.QSplitter):
    """M3 风格的分割视图。

    Args:
        orientation: 分割方向。
        parent: 父控件。
    """

    def __init__(
        self,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)
        self.setHandleWidth(HANDLE_WIDTH)
        self.setChildrenCollapsible(False)
        self.setOpaqueResize(True)

    @override
    def createHandle(self) -> QtWidgets.QSplitterHandle:
        return SplitHandle(self.orientation(), self)
