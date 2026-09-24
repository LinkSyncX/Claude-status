"""侧面板（Side sheets）：standard / modal，停靠或 detached 浮动。

停靠（docked）的标准侧面板贴窗口右缘、左侧一条分隔线；detached 变体
与窗口边缘保持 16dp 间距、四角 16dp 圆角并带 level 1 阴影。模态侧面板
带遮罩，前缘为圆角。头部可选返回按钮与关闭按钮；``add_action`` 在底部
加入操作按钮区（上方带分隔线）。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import common as buttons
from md3.components.buttons import icon_button
from md3.core import elevation as elevation_utils
from md3.core import overlay
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing
from md3.tokens import typography as typography_tokens

DEFAULT_WIDTH = 320
MIN_WIDTH = 256
MAX_WIDTH = 400
HEADER_HEIGHT = 64
ACTION_AREA_HEIGHT = 72
# detached 变体与窗口边缘的间距，同时为阴影预留空间。
DETACHED_MARGIN = 16
DETACHED_ELEVATION = elevation.Level.LEVEL_1


class SideSheet(overlay.FloatingPanel):
    """从窗口右侧滑入的面板。

    Args:
        host: 宿主窗口。
        title: 标题。
        modal: 为真时显示遮罩并可点击遮罩关闭。
        width: 面板宽度（px），限制在 256–400。
        closable: 是否显示关闭按钮。
        detached: 为真时面板与窗口边缘保持 16dp 间距、四角圆角并投影。
        show_back: 是否显示头部的返回按钮（点击发出 ``back_clicked``）。
    """

    back_clicked = QtCore.Signal()

    def __init__(
        self,
        host: QtWidgets.QWidget,
        title: str = "",
        modal: bool = False,
        width: int = DEFAULT_WIDTH,
        closable: bool = True,
        detached: bool = False,
        show_back: bool = False,
    ) -> None:
        super().__init__(host, modal)
        self._width = max(MIN_WIDTH, min(MAX_WIDTH, width))
        self._detached = detached
        self._actions: list[buttons.Button] = []
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        root = QtWidgets.QVBoxLayout(self)
        margin = DETACHED_MARGIN if detached else 0
        root.setContentsMargins(margin, margin, margin, margin)
        root.setSpacing(0)
        header = QtWidgets.QWidget(self)
        header.setFixedHeight(HEADER_HEIGHT)
        header_layout = QtWidgets.QHBoxLayout(header)
        header_layout.setContentsMargins(
            round(spacing.SPACE_3 if show_back else spacing.SPACE_6),
            0,
            round(spacing.SPACE_3),
            0,
        )
        self._back_button: icon_button.IconButton | None = None
        if show_back:
            self._back_button = icon_button.IconButton(
                "arrow_back", tooltip=i18n.tr("back")
            )
            self._back_button.clicked.connect(self.back_clicked)
            header_layout.addWidget(self._back_button)
        self._title = typography.Label(
            title, typography_tokens.TypeRole.TITLE_LARGE, "on_surface_variant"
        )
        header_layout.addWidget(self._title, 1)
        self._close_button: icon_button.IconButton | None = None
        if closable:
            self._close_button = icon_button.IconButton(
                "close", tooltip=i18n.tr("close")
            )
            self._close_button.clicked.connect(self.close_panel)
            header_layout.addWidget(self._close_button)
        root.addWidget(header)
        self._content_layout = QtWidgets.QVBoxLayout()
        self._content_layout.setContentsMargins(
            round(spacing.SPACE_6),
            0,
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
        )
        self._content_layout.setSpacing(round(spacing.SPACE_4))
        root.addLayout(self._content_layout, 1)
        self._action_area = QtWidgets.QWidget(self)
        self._action_area.setFixedHeight(ACTION_AREA_HEIGHT)
        self._actions_layout = QtWidgets.QHBoxLayout(self._action_area)
        self._actions_layout.setContentsMargins(
            round(spacing.SPACE_6), 0, round(spacing.SPACE_6), 0
        )
        self._actions_layout.setSpacing(round(spacing.SPACE_2))
        self._actions_layout.addStretch()
        self._action_area.hide()
        root.addWidget(self._action_area)

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """内容布局。"""
        return self._content_layout

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """放入内容控件。"""
        self._content_layout.addWidget(content, 1)

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self._title.setText(title)

    @property
    def detached(self) -> bool:
        """是否为 detached 浮动变体。"""
        return self._detached

    @property
    def back_button(self) -> icon_button.IconButton | None:
        """头部返回按钮。"""
        return self._back_button

    @property
    def close_button(self) -> icon_button.IconButton | None:
        """头部关闭按钮。"""
        return self._close_button

    # ---- 操作区 -----------------------------------------------------------

    def add_action(self, text: str, primary: bool = False) -> buttons.Button:
        """在底部操作区追加按钮并返回它。

        Args:
            text: 按钮文字。
            primary: 为真使用填充按钮，否则使用轮廓按钮。
        """
        button: buttons.Button = (
            buttons.FilledButton(text)
            if primary
            else buttons.OutlinedButton(text)
        )
        self._actions.append(button)
        # 操作从左到右排列，弹性空间保持在末尾。
        self._actions_layout.insertWidget(
            self._actions_layout.count() - 1, button
        )
        self._action_area.show()
        return button

    @property
    def action_buttons(self) -> list[buttons.Button]:
        """底部操作按钮。"""
        return list(self._actions)

    # ---- 几何 -------------------------------------------------------------

    def panel_rect(self) -> QtCore.QRectF:
        """面板容器矩形（detached 时向内扣除边距）。"""
        rect = QtCore.QRectF(self.rect())
        if self._detached:
            return rect.adjusted(
                DETACHED_MARGIN,
                DETACHED_MARGIN,
                -DETACHED_MARGIN,
                -DETACHED_MARGIN,
            )
        return rect

    def _rtl(self) -> bool:
        return (
            self.host.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft
        )

    @override
    def open_geometry(self) -> QtCore.QRect:
        host = self.host.rect()
        if self._detached:
            width = min(self._width + 2 * DETACHED_MARGIN, host.width())
        else:
            width = min(self._width, host.width())
        # 侧面板位于布局末尾侧：LTR 在右边，RTL 在左边。
        x = 0 if self._rtl() else host.width() - width
        return QtCore.QRect(x, 0, width, host.height())

    @override
    def closed_geometry(self) -> QtCore.QRect:
        rect = self.open_geometry()
        return rect.translated(
            -rect.width() if self._rtl() else rect.width(), 0
        )

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.panel_rect()
        if self._detached:
            shape = shape_tokens.SHAPE_LARGE
            elevation_utils.paint_shadow(
                painter,
                rect,
                shape,
                DETACHED_ELEVATION,
                theme.color("shadow"),
                self.devicePixelRatioF(),
            )
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(rect, shape),
                theme.color("surface_container_low"),
            )
        elif self.modal:
            if self._rtl():
                path = shape_utils.rounded_rect_path(
                    rect.adjusted(-shape_tokens.LARGE, 0, 0, 0),
                    shape_tokens.Shape.end(shape_tokens.LARGE),
                )
            else:
                path = shape_utils.rounded_rect_path(
                    rect.adjusted(0, 0, shape_tokens.LARGE, 0),
                    shape_tokens.Shape.start(shape_tokens.LARGE),
                )
            shape_utils.fill_shape(
                painter, path, theme.color("surface_container_low")
            )
        else:
            painter.fillRect(rect, theme.color("surface"))
            edge = rect.right() - 1 if self._rtl() else rect.left()
            painter.fillRect(
                QtCore.QRectF(edge, rect.top(), 1, rect.height()),
                theme.color("outline_variant"),
            )
        if self._action_area.isVisible():
            top = self._action_area.geometry().top()
            painter.fillRect(
                QtCore.QRectF(rect.left(), top, rect.width(), 1),
                theme.color("outline_variant"),
            )
        painter.end()
