"""图标图库：以网格浏览、搜索并选取图标。

``IconGallery`` 自绘一组图标瓦片（图标 + 名称），支持悬停状态层、点击选中
与键盘方向键移动，可同时展示 Material Symbols 与已注册的 SVG 图标；配合
``icons.search_icons`` 即可做出图标选择器。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

TILE_WIDTH = 96.0
TILE_HEIGHT = 84.0
TILE_GAP = 4.0
ICON_SIZE = 32.0
ICON_TOP = 12.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_SMALL
LABEL_TOP = 56.0
LABEL_PADDING = 6.0


class IconGallery(widget.MaterialWidget):
    """图标网格。

    Args:
        names: 图标名（Material Symbols 名或已注册的 SVG 名）。
        icon_size: 图标尺寸（dp）。
        fill: Material Symbols 是否使用填充样式。
        parent: 父控件。
    """

    icon_clicked = QtCore.Signal(str)
    selection_changed = QtCore.Signal(str)

    def __init__(
        self,
        names: Iterable[str] = (),
        icon_size: float = ICON_SIZE,
        fill: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._names: list[str] = list(names)
        self._icon_size = icon_size
        self._fill = fill
        self._hovered = -1
        self._selected = -1
        self._columns = 1
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.List

    # ---- 数据 -------------------------------------------------------------

    @property
    def names(self) -> list[str]:
        """当前显示的图标名。"""
        return list(self._names)

    def set_icons(self, names: Iterable[str]) -> None:
        """替换显示的图标。"""
        self._names = list(names)
        self._hovered = -1
        self._selected = -1
        self.updateGeometry()
        self.update()

    @property
    def fill(self) -> bool:
        """Material Symbols 是否填充。"""
        return self._fill

    def set_fill(self, fill: bool) -> None:
        """切换 Material Symbols 的填充样式。"""
        self._fill = fill
        self.update()

    def set_icon_size(self, size: float) -> None:
        """设置图标尺寸。"""
        self._icon_size = size
        self.update()

    @property
    def selected_name(self) -> str:
        """选中的图标名，未选中时为空字符串。"""
        if 0 <= self._selected < len(self._names):
            return self._names[self._selected]
        return ""

    def select(self, name: str) -> None:
        """按名称选中（不存在时清除选择）。"""
        index = self._names.index(name) if name in self._names else -1
        self._set_selected(index)

    def _set_selected(self, index: int) -> None:
        if index == self._selected:
            return
        self._selected = index
        self.selection_changed.emit(self.selected_name)
        self.update()

    def icon_at(self, index: int) -> icons.AnyIcon | None:
        """第 index 个瓦片的图标对象。"""
        if not 0 <= index < len(self._names):
            return None
        icon = icons.coerce(self._names[index], self._icon_size)
        if self._fill and isinstance(icon, icons.Icon):
            icon = icon.with_fill(True)
        return icon

    # ---- 几何 -------------------------------------------------------------

    def columns(self) -> int:
        """当前宽度下每行的瓦片数。"""
        available = max(1.0, self.width() - 0.0)
        return max(1, int((available + TILE_GAP) // (TILE_WIDTH + TILE_GAP)))

    def rows(self) -> int:
        """行数。"""
        return (len(self._names) + self.columns() - 1) // self.columns()

    def tile_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个瓦片的矩形。"""
        columns = self.columns()
        row, column = divmod(index, columns)
        return QtCore.QRectF(
            column * (TILE_WIDTH + TILE_GAP),
            row * (TILE_HEIGHT + TILE_GAP),
            TILE_WIDTH,
            TILE_HEIGHT,
        )

    def index_at(self, position: QtCore.QPointF) -> int:
        """位置对应的瓦片下标，无命中返回 -1。"""
        columns = self.columns()
        column = int(position.x() // (TILE_WIDTH + TILE_GAP))
        row = int(position.y() // (TILE_HEIGHT + TILE_GAP))
        if column >= columns or position.x() < 0 or position.y() < 0:
            return -1
        index = row * columns + column
        if index >= len(self._names) or not self.tile_rect(index).contains(
            position
        ):
            return -1
        return index

    @override
    def sizeHint(self) -> QtCore.QSize:
        rows = self.rows()
        height = rows * TILE_HEIGHT + max(0, rows - 1) * TILE_GAP
        return QtCore.QSize(int(4 * (TILE_WIDTH + TILE_GAP)), int(height))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(int(TILE_WIDTH), self.sizeHint().height())

    @override
    def hasHeightForWidth(self) -> bool:
        return True

    @override
    def heightForWidth(self, width: int) -> int:
        columns = max(1, int((width + TILE_GAP) // (TILE_WIDTH + TILE_GAP)))
        rows = (len(self._names) + columns - 1) // columns
        return int(rows * TILE_HEIGHT + max(0, rows - 1) * TILE_GAP)

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self.columns() != self._columns:
            self._columns = self.columns()
            self.updateGeometry()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        visible = QtCore.QRectF(self.rect())
        icon_color = self.color("on_surface_variant")
        label_color = self.color("on_surface_variant")
        for index, name in enumerate(self._names):
            rect = self.tile_rect(index)
            if not rect.intersects(visible):
                continue
            path = shape_utils.rounded_rect_path(
                rect, shape_tokens.SHAPE_MEDIUM
            )
            selected = index == self._selected
            if selected:
                shape_utils.fill_shape(
                    painter, path, self.color("secondary_container")
                )
            if index == self._hovered:
                shape_utils.fill_shape(
                    painter,
                    path,
                    theme_module.with_alpha(
                        self.color("on_surface"),
                        state_tokens.HOVER_STATE_LAYER_OPACITY,
                    ),
                )
            if self.hasFocus() and selected:
                shape_utils.fill_shape(
                    painter, path, None, self.color("secondary"), 2.0
                )
            icon = self.icon_at(index)
            if icon is not None:
                icon_rect = QtCore.QRectF(
                    rect.center().x() - self._icon_size / 2,
                    rect.top() + ICON_TOP + (ICON_SIZE - self._icon_size) / 2,
                    self._icon_size,
                    self._icon_size,
                )
                icon.paint(
                    painter,
                    icon_rect,
                    self.color("on_secondary_container")
                    if selected
                    else icon_color,
                )
            label = name.rsplit("/", 1)[-1]
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    rect.left() + LABEL_PADDING,
                    rect.top() + LABEL_TOP,
                    rect.width() - 2 * LABEL_PADDING,
                    rect.height() - LABEL_TOP - 4,
                ),
                label,
                LABEL_STYLE,
                self.color("on_secondary_container")
                if selected
                else label_color,
                QtCore.Qt.AlignmentFlag.AlignHCenter
                | QtCore.Qt.AlignmentFlag.AlignTop,
            )

    # ---- 事件 -------------------------------------------------------------

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hovered = self.index_at(event.position())
        if hovered != self._hovered:
            self._hovered = hovered
            self.setToolTip(self._names[hovered] if hovered >= 0 else "")
            self.update()
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            index = self.index_at(event.position())
            if index >= 0:
                self._set_selected(index)
                self.icon_clicked.emit(self._names[index])
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if not self._names:
            super().keyPressEvent(event)
            return
        columns = self.columns()
        current = max(0, self._selected)
        key = event.key()
        delta = {
            QtCore.Qt.Key.Key_Left: -1,
            QtCore.Qt.Key.Key_Right: 1,
            QtCore.Qt.Key.Key_Up: -columns,
            QtCore.Qt.Key.Key_Down: columns,
        }.get(key)
        if delta is not None:
            target = current + delta if self._selected >= 0 else 0
            if 0 <= target < len(self._names):
                self._set_selected(target)
            event.accept()
            return
        if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            if self._selected >= 0:
                self.icon_clicked.emit(self._names[self._selected])
            event.accept()
            return
        super().keyPressEvent(event)
