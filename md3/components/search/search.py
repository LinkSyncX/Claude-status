"""搜索栏（Search bar）与搜索视图（Search view）。

搜索栏是高 56dp 的胶囊输入框；聚焦或输入时可展开停靠在下方的搜索视图，
显示建议列表。搜索视图是宿主窗口内的浮动面板。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import icon_button
from md3.components.lists import list_item
from md3.core import elevation as elevation_utils
from md3.core import overlay
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

BAR_HEIGHT = 56.0
MIN_WIDTH = 360.0
MAX_WIDTH = 720.0
ICON_SIZE = 24.0
ICON_PADDING = 16.0
TEXT_GAP = 16.0
VIEW_MAX_HEIGHT = 480
INPUT_STYLE = typography_tokens.TypeRole.BODY_LARGE


class SearchBar(widget.MaterialWidget):
    """搜索栏。

    Args:
        placeholder: 占位文字。
        leading_icon: 前置图标，通常为 ``search`` 或 ``menu``。
        trailing_icon: 后置图标（如 ``mic`` 或头像），可点击。
        parent: 父控件。
    """

    text_changed = QtCore.Signal(str)
    submitted = QtCore.Signal(str)
    leading_clicked = QtCore.Signal()
    trailing_clicked = QtCore.Signal()
    focus_changed = QtCore.Signal(bool)

    def __init__(
        self,
        placeholder: str | None = None,
        leading_icon: icons.IconLike = "search",
        trailing_icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if placeholder is None:
            placeholder = i18n.tr("search")
        self._placeholder = placeholder
        self._leading = icons.coerce(leading_icon, ICON_SIZE)
        self._trailing = icons.coerce(trailing_icon, ICON_SIZE)
        self._hovered = False
        self._focused = False
        self._pressed_zone = ""
        self._edit = QtWidgets.QLineEdit(self)
        self._edit.setFrame(False)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setAccessibleName(placeholder)
        self._edit.textChanged.connect(self.text_changed)
        self._edit.returnPressed.connect(self._on_return)
        self._edit.installEventFilter(self)
        self.setFocusProxy(self._edit)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._apply_editor_style()

    @property
    def editor(self) -> QtWidgets.QLineEdit:
        """内部输入框。"""
        return self._edit

    @property
    def text(self) -> str:
        """当前文字。"""
        return self._edit.text()

    def set_text(self, text: str) -> None:
        """设置文字。"""
        self._edit.setText(text)

    def set_placeholder(self, placeholder: str) -> None:
        """设置占位文字。"""
        self._placeholder = placeholder
        self._edit.setPlaceholderText(placeholder)
        self._edit.setAccessibleName(placeholder)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    @override
    def accessible_name(self) -> str:
        return self._placeholder

    def set_trailing_icon(self, icon: icons.IconLike) -> None:
        """设置后置图标。"""
        self._trailing = icons.coerce(icon, ICON_SIZE)
        self._layout_editor()
        self.update()

    def _apply_editor_style(self) -> None:
        theme = self.theme
        self._edit.setFont(theme.font(INPUT_STYLE))
        palette = self._edit.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Text, theme.color("on_surface")
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Base, theme_module.TRANSPARENT
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.PlaceholderText,
            theme.color("on_surface_variant"),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Highlight, theme.color("primary")
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.HighlightedText, theme.color("on_primary")
        )
        self._edit.setPalette(palette)
        self._edit.setStyleSheet(
            "background: transparent; border: none; padding: 0px;"
        )

    @override
    def on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self._apply_editor_style()

    def _on_return(self) -> None:
        self.submitted.emit(self._edit.text())

    # ---- 几何 -------------------------------------------------------------

    def container_rect(self) -> QtCore.QRectF:
        """容器矩形。"""
        return QtCore.QRectF(self.rect())

    def leading_rect(self) -> QtCore.QRectF:
        """前置图标可点击区域。"""
        rect = self.container_rect()
        return QtCore.QRectF(
            rect.left(), rect.top(), ICON_PADDING + ICON_SIZE + 8, rect.height()
        )

    def trailing_rect(self) -> QtCore.QRectF:
        """后置图标可点击区域。"""
        if self._trailing is None:
            return QtCore.QRectF()
        rect = self.container_rect()
        width = ICON_PADDING + ICON_SIZE + 8
        return QtCore.QRectF(
            rect.right() - width, rect.top(), width, rect.height()
        )

    def _layout_editor(self) -> None:
        rect = self.container_rect()
        left = (
            rect.left()
            + ICON_PADDING
            + (ICON_SIZE + TEXT_GAP if self._leading else 0)
        )
        right = (
            rect.right()
            - ICON_PADDING
            - (ICON_SIZE + TEXT_GAP if self._trailing else 0)
        )
        height = self.theme.style(INPUT_STYLE).line_height
        self._edit.setGeometry(
            round(left),
            round(rect.center().y() - height / 2),
            max(1, round(right - left)),
            round(height),
        )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_editor()

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(int(MIN_WIDTH), int(BAR_HEIGHT))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(200, int(BAR_HEIGHT))

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL)
        shape_utils.fill_shape(
            painter, path, self.color("surface_container_high")
        )
        if self._hovered and not self._focused:
            layer = theme_module.with_alpha(self.color("on_surface"), 0.08)
            shape_utils.fill_shape(painter, path, layer)
        color = self.color("on_surface_variant")
        if self._leading is not None:
            self._leading.paint(
                painter,
                QtCore.QRectF(
                    rect.left() + ICON_PADDING,
                    rect.center().y() - ICON_SIZE / 2,
                    ICON_SIZE,
                    ICON_SIZE,
                ),
                self.color("on_surface"),
            )
        if self._trailing is not None:
            self._trailing.paint(
                painter,
                QtCore.QRectF(
                    rect.right() - ICON_PADDING - ICON_SIZE,
                    rect.center().y() - ICON_SIZE / 2,
                    ICON_SIZE,
                    ICON_SIZE,
                ),
                color,
            )

    # ---- 事件 -------------------------------------------------------------

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if watched is self._edit:
            if event.type() == QtCore.QEvent.Type.FocusIn:
                self._focused = True
                self.focus_changed.emit(True)
                self.update()
            elif event.type() == QtCore.QEvent.Type.FocusOut:
                self._focused = False
                self.focus_changed.emit(False)
                self.update()
        return super().eventFilter(watched, event)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._hovered = True
        self.update()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._hovered = False
        self.update()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        if self.leading_rect().contains(event.position()):
            self._pressed_zone = "leading"
        elif self.trailing_rect().contains(event.position()):
            self._pressed_zone = "trailing"
        else:
            self._pressed_zone = ""
            self._edit.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        zone = self._pressed_zone
        self._pressed_zone = ""
        if zone == "leading" and self.leading_rect().contains(event.position()):
            self.leading_clicked.emit()
        elif zone == "trailing" and self.trailing_rect().contains(
            event.position()
        ):
            self.trailing_clicked.emit()
        event.accept()


class SearchView(overlay.FloatingPanel):
    """停靠在搜索栏下方的搜索视图，显示建议列表。

    Args:
        host: 宿主窗口。
        search_bar: 关联的搜索栏；视图对齐到其下方。
        auto_open: 为真时搜索栏聚焦即打开视图。
    """

    suggestion_selected = QtCore.Signal(str)

    def __init__(
        self,
        host: QtWidgets.QWidget,
        search_bar: SearchBar,
        auto_open: bool = True,
    ) -> None:
        super().__init__(host, modal=False)
        self._bar = search_bar
        self._suggestions: list[str] = []
        self._items: list[list_item.ListItem] = []
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, int(BAR_HEIGHT) + 1, 0, 8)
        root.setSpacing(0)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._list = QtWidgets.QWidget()
        self._list_layout = QtWidgets.QVBoxLayout(self._list)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(0)
        self._list_layout.addStretch()
        self._scroll.setWidget(self._list)
        root.addWidget(self._scroll)
        self._back = icon_button.IconButton(
            "arrow_back", tooltip=i18n.tr("back"), parent=self
        )
        self._back.clicked.connect(self.close_panel)
        self._clear = icon_button.IconButton(
            "close", tooltip=i18n.tr("clear"), parent=self
        )
        self._clear.clicked.connect(lambda: self._bar.set_text(""))
        if auto_open:
            search_bar.focus_changed.connect(self._on_bar_focus)
        search_bar.text_changed.connect(lambda _t: self.update())

    def _on_bar_focus(self, focused: bool) -> None:
        if focused and not self.is_open:
            self.open_panel()

    # ---- 建议 -------------------------------------------------------------

    @property
    def suggestions(self) -> list[str]:
        """建议列表。"""
        return list(self._suggestions)

    def set_suggestions(self, suggestions: list[str]) -> None:
        """替换建议列表。"""
        for item in self._items:
            self._list_layout.removeWidget(item)
            item.setParent(None)
            item.deleteLater()
        self._items = []
        self._suggestions = list(suggestions)
        for text in self._suggestions:
            item = list_item.ListItem(text, leading_icon="history")
            item.clicked.connect(self._on_item_clicked)
            self._items.append(item)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)

    def _on_item_clicked(self) -> None:
        sender = self.sender()
        for item in self._items:
            if item is sender:
                self._bar.set_text(item.headline)
                self.suggestion_selected.emit(item.headline)
                self.close_panel()
                return

    # ---- 几何 -------------------------------------------------------------

    @override
    def open_geometry(self) -> QtCore.QRect:
        bar_rect = QtCore.QRect(
            self._bar.mapTo(self.host, QtCore.QPoint(0, 0)), self._bar.size()
        )
        height = min(VIEW_MAX_HEIGHT, self.host.height() - bar_rect.top())
        return QtCore.QRect(
            bar_rect.left(), bar_rect.top(), bar_rect.width(), height
        )

    @override
    def closed_geometry(self) -> QtCore.QRect:
        rect = self.open_geometry()
        return QtCore.QRect(
            rect.left(), rect.top(), rect.width(), int(BAR_HEIGHT)
        )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        side = 48
        y = int((BAR_HEIGHT - side) / 2)
        self._back.setGeometry(8, y, side, side)
        self._clear.setGeometry(self.width() - 8 - side, y, side, side)

    @override
    def open_panel(self) -> None:
        super().open_panel()
        self._bar.editor.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect())
        shape = shape_tokens.SHAPE_EXTRA_LARGE
        elevation_utils.paint_shadow(
            painter,
            rect.adjusted(8, 8, -8, -8),
            shape,
            elevation.Level.LEVEL_3,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        path = shape_utils.rounded_rect_path(rect, shape)
        shape_utils.fill_shape(
            painter, path, theme.color("surface_container_high")
        )
        # 头部：返回、当前文字、清除。
        text = self._bar.text
        typography.paint_text(
            painter,
            QtCore.QRectF(64, 0, rect.width() - 128, BAR_HEIGHT),
            text or self._bar._placeholder,  # pylint: disable=protected-access
            INPUT_STYLE,
            theme.color("on_surface" if text else "on_surface_variant"),
        )
        painter.fillRect(
            QtCore.QRectF(rect.left(), BAR_HEIGHT, rect.width(), 1),
            theme.color("outline_variant"),
        )
        painter.end()
