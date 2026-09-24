"""横幅（Banner）。

页内持久提示：位于内容顶部，容器 ``surface_container_low``、底部一条
分隔线，可带前置图标、一至两行文字与最多两个文字按钮操作；宽度不足时
操作换到文字下方一行。``show_animated`` / ``dismiss`` 以高度动画展开与
收起，操作默认点击后关闭横幅。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import common as buttons
from md3.core import animation
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import motion
from md3.tokens import spacing
from md3.tokens import typography as typography_tokens

ICON_SIZE = 24.0
TEXT_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
# 文字与操作同排时要求的最小宽度，低于此值操作换行。
INLINE_MIN_WIDTH = 560


class _Icon(widget.MaterialWidget):
    def __init__(self, icon: icons.IconLike, color_role: str) -> None:
        super().__init__()
        self._icon = icons.coerce(icon, ICON_SIZE)
        self._color_role = color_role
        self.setFixedSize(round(ICON_SIZE), round(ICON_SIZE))

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        if self._icon is not None:
            self._icon.paint(
                painter,
                QtCore.QRectF(self.rect()),
                self.color(self._color_role),
            )


class Banner(widget.MaterialWidget):
    """横幅。

    Args:
        text: 提示文字。
        icon: 前置图标。
        icon_color: 图标色彩角色（例如 ``error`` 表示警示）。
        dismiss_on_action: 点击操作后是否自动关闭。
        parent: 父控件。
    """

    dismissed = QtCore.Signal()
    action_triggered = QtCore.Signal(int)

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        icon_color: str = "primary",
        dismiss_on_action: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dismiss_on_action = dismiss_on_action
        self._actions: list[buttons.TextButton] = []
        self._reveal = animation.AnimatedFloat(self, 1.0, self._apply_reveal)
        self._reveal.finished.connect(self._on_reveal_finished)
        self._closing = False
        self._body = QtWidgets.QWidget(self)
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._body)
        self._grid = QtWidgets.QGridLayout(self._body)
        self._grid.setContentsMargins(
            round(spacing.SPACE_4),
            round(spacing.SPACE_4),
            round(spacing.SPACE_2),
            round(spacing.SPACE_2),
        )
        self._grid.setHorizontalSpacing(round(spacing.SPACE_4))
        self._grid.setVerticalSpacing(round(spacing.SPACE_2))
        self._icon: _Icon | None = None
        if icon is not None:
            self._icon = _Icon(icon, icon_color)
            self._grid.addWidget(
                self._icon, 0, 0, QtCore.Qt.AlignmentFlag.AlignTop
            )
        self._label = typography.Label(text, TEXT_STYLE, "on_surface")
        self._label.setWordWrap(True)
        self._grid.addWidget(self._label, 0, 1)
        self._actions_widget = QtWidgets.QWidget(self._body)
        self._actions_layout = QtWidgets.QHBoxLayout(self._actions_widget)
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(round(spacing.SPACE_2))
        self._actions_layout.addStretch()
        self._inline = True
        self._place_actions(inline=True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 内容 -------------------------------------------------------------

    @property
    def text(self) -> str:
        """提示文字。"""
        return self._label.text()

    def set_text(self, text: str) -> None:
        """设置提示文字。"""
        self._label.setText(text)

    def add_action(self, text: str) -> buttons.TextButton:
        """追加一个文字按钮操作（最多两个）。"""
        button = buttons.TextButton(text)
        index = len(self._actions)
        button.clicked.connect(lambda: self._on_action(index))
        self._actions.append(button)
        self._actions_layout.addWidget(button)
        return button

    @property
    def action_buttons(self) -> list[buttons.TextButton]:
        """操作按钮。"""
        return list(self._actions)

    def _on_action(self, index: int) -> None:
        self.action_triggered.emit(index)
        if self._dismiss_on_action:
            self.dismiss()

    def _place_actions(self, inline: bool) -> None:
        self._grid.removeWidget(self._actions_widget)
        if inline:
            self._grid.addWidget(
                self._actions_widget,
                0,
                2,
                QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        else:
            self._grid.addWidget(self._actions_widget, 1, 1, 1, 2)
        self._inline = inline

    # ---- 显示与关闭 -------------------------------------------------------

    @property
    def is_dismissed(self) -> bool:
        """是否已关闭（或正在收起）。"""
        return self._closing or (
            not self.isVisible() and self._reveal.value == 0
        )

    def show_animated(self) -> None:
        """展开显示。"""
        self._closing = False
        self.show()
        self._reveal.set(0.0)
        self._reveal.animate_to(
            1.0, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
        )

    def dismiss(self) -> None:
        """收起并隐藏，完成后发出 ``dismissed``。"""
        if self._closing or not self.isVisible():
            return
        self._closing = True
        self._reveal.animate_to(
            0.0, motion.SHORT4, motion.EMPHASIZED_ACCELERATE
        )

    def _apply_reveal(self) -> None:
        progress = self._reveal.value
        full = self._body.sizeHint().height()
        self.setMaximumHeight(
            round(full * progress) if progress < 0.999 else 16777215
        )
        self.updateGeometry()
        self.update()

    def _on_reveal_finished(self) -> None:
        if self._closing and self._reveal.value <= 0.001:
            self._closing = False
            self.hide()
            self.setMaximumHeight(16777215)
            self.dismissed.emit()

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        inline = self.width() >= INLINE_MIN_WIDTH or not self._actions
        if inline != self._inline:
            self._place_actions(inline)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        painter.fillRect(rect, self.color("surface_container_low"))
        painter.fillRect(
            QtCore.QRectF(rect.left(), rect.bottom() - 1, rect.width(), 1),
            self.color("outline_variant"),
        )
