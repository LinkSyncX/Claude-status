"""无边框窗口（Material window）与自绘标题栏。

``MaterialWindow`` 去掉系统边框，用 ``TitleBar`` 绘制 40dp 的标题栏：应用
图标、标题、可自定义的中间区域（放菜单、标签页等）以及最小化 / 最大化
（还原）/ 关闭按钮。拖动标题栏移动窗口、双击切换最大化，窗口边缘 6px
内可拖动改变大小；移动与缩放都通过 ``QWindow.startSystemMove`` /
``startSystemResize`` 交给系统完成，因此保留了各平台的吸附与动画。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import icon_button
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import typography as typography_tokens

TITLE_BAR_HEIGHT = 40
RESIZE_MARGIN = 6
ICON_SIZE = 20.0
TITLE_STYLE = typography_tokens.TypeRole.TITLE_SMALL


class TitleBar(widget.MaterialWidget):
    """自绘标题栏。

    Args:
        window: 所属窗口。
        title: 标题文字。
        icon: 应用图标。
    """

    def __init__(
        self,
        window: MaterialWindow,
        title: str = "",
        icon: icons.IconLike = None,
    ) -> None:
        super().__init__(window)
        self._window = window
        self._title = title
        self._icon = icons.coerce(icon, ICON_SIZE)
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(4)
        # 左侧留给图标与标题（自绘），中间为可插入控件的区域。
        self._title_width = self._measure_title()
        layout.addSpacing(round(self._title_width))
        self._extras = QtWidgets.QHBoxLayout()
        self._extras.setContentsMargins(0, 0, 0, 0)
        self._extras.setSpacing(4)
        layout.addLayout(self._extras, 1)
        self._minimize = icon_button.IconButton(
            "remove", tooltip=i18n.tr("minimize")
        )
        self._minimize.clicked.connect(window.showMinimized)
        self._maximize = icon_button.IconButton(
            "crop_square", tooltip=i18n.tr("maximize")
        )
        self._maximize.clicked.connect(window.toggle_maximized)
        self._close = icon_button.IconButton("close", tooltip=i18n.tr("close"))
        self._close.clicked.connect(window.close)
        for button in (self._minimize, self._maximize, self._close):
            button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
            layout.addWidget(button)

    @property
    def title(self) -> str:
        """标题。"""
        return self._title

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self._title = title
        self._title_width = self._measure_title()
        item = self.layout().itemAt(0)
        if item is not None and item.spacerItem() is not None:
            item.spacerItem().changeSize(round(self._title_width), 0)
        self.layout().invalidate()
        self.update()

    def _measure_title(self) -> float:
        width = typography.text_width(self._title, TITLE_STYLE)
        if self._icon is not None:
            width += ICON_SIZE + 8
        return width + 8

    def add_widget(self, child: QtWidgets.QWidget, stretch: int = 0) -> None:
        """在标题与窗口按钮之间放入控件。"""
        self._extras.addWidget(child, stretch)

    @property
    def buttons(
        self,
    ) -> tuple[
        icon_button.IconButton, icon_button.IconButton, icon_button.IconButton
    ]:
        """(最小化, 最大化, 关闭) 按钮。"""
        return self._minimize, self._maximize, self._close

    def set_maximized(self, maximized: bool) -> None:
        """同步最大化按钮的图标与提示。"""
        self._maximize.set_icon("filter_none" if maximized else "crop_square")
        self._maximize.set_tooltip(
            i18n.tr("restore" if maximized else "maximize")
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        painter.fillRect(rect, self.color("surface"))
        left = rect.left() + 12.0
        if self._icon is not None:
            self._icon.paint(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        left,
                        rect.center().y() - ICON_SIZE / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    )
                ),
                self.color("primary"),
            )
            left += ICON_SIZE + 8
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(
                    left, rect.top(), self._title_width, rect.height()
                )
            ),
            self._title,
            TITLE_STYLE,
            self.color("on_surface"),
            self.start_alignment(),
        )

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and not self._window.isMaximized():
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._window.toggle_maximized()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MaterialWindow(QtWidgets.QWidget):
    """无边框窗口。

    Args:
        title: 标题。
        icon: 应用图标。
        resizable: 是否允许从边缘拖动改变大小。
        parent: 父控件。
    """

    maximized_changed = QtCore.Signal(bool)

    def __init__(
        self,
        title: str = "",
        icon: icons.IconLike = None,
        resizable: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._resizable = resizable
        self.setWindowFlags(
            QtCore.Qt.WindowType.Window
            | QtCore.Qt.WindowType.FramelessWindowHint
        )
        self.setWindowTitle(title)
        self.setMouseTracking(True)
        self._root = QtWidgets.QVBoxLayout(self)
        self._root.setSpacing(0)
        self._title_bar = TitleBar(self, title, icon)
        self._root.addWidget(self._title_bar)
        self._content = QtWidgets.QWidget(self)
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._root.addWidget(self._content, 1)
        self._apply_margins()
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    @property
    def title_bar(self) -> TitleBar:
        """标题栏。"""
        return self._title_bar

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """内容区布局。"""
        return self._content_layout

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """放入内容控件。"""
        self._content_layout.addWidget(content, 1)

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self.setWindowTitle(title)
        self._title_bar.set_title(title)

    def toggle_maximized(self) -> None:
        """在最大化与正常之间切换。"""
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _apply_margins(self) -> None:
        margin = (
            0 if self.isMaximized() or not self._resizable else RESIZE_MARGIN
        )
        self._root.setContentsMargins(margin, margin, margin, margin)

    def _edges_at(self, position: QtCore.QPointF) -> QtCore.Qt.Edge:
        edges = QtCore.Qt.Edge(0)
        if not self._resizable or self.isMaximized():
            return edges
        rect = self.rect()
        if position.x() <= RESIZE_MARGIN:
            edges |= QtCore.Qt.Edge.LeftEdge
        elif position.x() >= rect.width() - RESIZE_MARGIN:
            edges |= QtCore.Qt.Edge.RightEdge
        if position.y() <= RESIZE_MARGIN:
            edges |= QtCore.Qt.Edge.TopEdge
        elif position.y() >= rect.height() - RESIZE_MARGIN:
            edges |= QtCore.Qt.Edge.BottomEdge
        return edges

    @staticmethod
    def _cursor_for(edges: QtCore.Qt.Edge) -> QtCore.Qt.CursorShape:
        left = bool(edges & QtCore.Qt.Edge.LeftEdge)
        right = bool(edges & QtCore.Qt.Edge.RightEdge)
        top = bool(edges & QtCore.Qt.Edge.TopEdge)
        bottom = bool(edges & QtCore.Qt.Edge.BottomEdge)
        if (top and left) or (bottom and right):
            return QtCore.Qt.CursorShape.SizeFDiagCursor
        if (top and right) or (bottom and left):
            return QtCore.Qt.CursorShape.SizeBDiagCursor
        if left or right:
            return QtCore.Qt.CursorShape.SizeHorCursor
        if top or bottom:
            return QtCore.Qt.CursorShape.SizeVerCursor
        return QtCore.Qt.CursorShape.ArrowCursor

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self.setCursor(self._cursor_for(self._edges_at(event.position())))
        super().mouseMoveEvent(event)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        edges = self._edges_at(event.position())
        if edges and event.button() == QtCore.Qt.MouseButton.LeftButton:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemResize(edges)
                event.accept()
                return
        super().mousePressEvent(event)

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.WindowStateChange:
            maximized = self.isMaximized()
            self._title_bar.set_maximized(maximized)
            self._apply_margins()
            self.maximized_changed.emit(maximized)
            self.update()

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), theme.color("surface"))
        if not self.isMaximized():
            painter.setPen(QtGui.QPen(theme.color("outline_variant"), 1))
            painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()
