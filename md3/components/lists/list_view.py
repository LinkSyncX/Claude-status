"""可滚动的列表容器。

``ListView`` 垂直堆叠 ``ListItem``，提供单选 / 多选、分隔线，并把列表项的
滑动移除接成 ``item_dismissed``（同时从列表中移除该项）。``reorderable``
为真时可以按住列表项上下拖动排序：被拖动的项以带阴影的浮层跟随指针，
其余项即时让位，松手后发出 ``items_reordered(from, to)``。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.lists import list_item
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens

# 竖直移动超过阈值才开始拖动排序；指针靠近视口边缘时自动滚动。
REORDER_THRESHOLD = 8.0
AUTOSCROLL_MARGIN = 32
AUTOSCROLL_STEP = 12
GHOST_ELEVATION = elevation.Level.LEVEL_3
GHOST_MARGIN = 24


class SelectionMode(enum.Enum):
    """列表选择模式。"""

    NONE = "none"
    SINGLE = "single"
    MULTIPLE = "multiple"


class _ReorderGhost(QtWidgets.QWidget):
    """拖动排序时跟随指针的列表项快照，带 level 3 阴影。"""

    def __init__(
        self, pixmap: QtGui.QPixmap, parent: QtWidgets.QWidget
    ) -> None:
        super().__init__(parent)
        self._pixmap = pixmap
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        size = pixmap.deviceIndependentSize().toSize()
        self.resize(
            size.width() + 2 * GHOST_MARGIN, size.height() + 2 * GHOST_MARGIN
        )

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        theme = theme_module.current()
        rect = QtCore.QRectF(self.rect()).adjusted(
            GHOST_MARGIN, GHOST_MARGIN, -GHOST_MARGIN, -GHOST_MARGIN
        )
        shape = shape_tokens.SHAPE_MEDIUM
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            GHOST_ELEVATION,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        path = shape_utils.rounded_rect_path(rect, shape)
        painter.setClipPath(path)
        painter.fillRect(rect, theme.color("surface_container_low"))
        painter.drawPixmap(rect.topLeft(), self._pixmap)
        painter.end()


class ListView(QtWidgets.QScrollArea):
    """垂直排列 ``ListItem`` 的可滚动列表。

    Args:
        selection_mode: 选择模式。
        dividers: 是否在项之间显示分隔线。
        reorderable: 是否允许拖动列表项排序。
        parent: 父控件。
    """

    item_clicked = QtCore.Signal(int)
    selection_changed = QtCore.Signal(list)
    item_dismissed = QtCore.Signal(int, object)
    swipe_action_triggered = QtCore.Signal(int, object)
    items_reordered = QtCore.Signal(int, int)

    def __init__(
        self,
        selection_mode: SelectionMode = SelectionMode.NONE,
        dividers: bool = False,
        reorderable: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._selection_mode = selection_mode
        self._dividers = dividers
        self._reorderable = reorderable
        self._items: list[list_item.ListItem] = []
        self._press_item: list_item.ListItem | None = None
        self._press_pos = QtCore.QPointF()
        self._drag_item: list_item.ListItem | None = None
        self._drag_from = -1
        self._drag_to = -1
        self._grab_offset = 0
        self._placeholder: QtWidgets.QWidget | None = None
        self._ghost: _ReorderGhost | None = None
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 8, 0, 8)
        self._layout.setSpacing(0)
        self._layout.addStretch()
        self.setWidget(self._container)
        self._apply_theme(theme_module.current())
        theme_module.manager().theme_changed.connect(self._apply_theme)

    def _apply_theme(self, theme: theme_module.Theme) -> None:
        palette = self._container.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window, theme.color("surface")
        )
        self._container.setPalette(palette)
        self._container.setAutoFillBackground(True)

    # ---- 项 ---------------------------------------------------------------

    @property
    def items(self) -> list[list_item.ListItem]:
        """全部列表项。"""
        return list(self._items)

    @property
    def reorderable(self) -> bool:
        """是否允许拖动排序。"""
        return self._reorderable

    def set_reorderable(self, reorderable: bool) -> None:
        """设置是否允许拖动排序。"""
        self._reorderable = reorderable

    def add_item(self, item: list_item.ListItem) -> list_item.ListItem:
        """追加列表项并返回它。"""
        return self.insert_item(len(self._items), item)

    def insert_item(
        self, index: int, item: list_item.ListItem
    ) -> list_item.ListItem:
        """在 index 处插入列表项并返回它。"""
        index = max(0, min(index, len(self._items)))
        self._items.insert(index, item)
        item.set_show_divider(self._dividers)
        item.clicked.connect(self._on_sender_clicked)
        item.dismissed.connect(self._on_sender_dismissed)
        item.swipe_action_triggered.connect(self._on_sender_swipe_action)
        item.installEventFilter(self)
        self._layout.insertWidget(index, item)
        return item

    def _index_of_sender(self) -> int:
        sender = self.sender()
        for index, item in enumerate(self._items):
            if item is sender:
                return index
        return -1

    def _on_sender_clicked(self) -> None:
        index = self._index_of_sender()
        if index >= 0:
            self._on_item_clicked(index)

    def _on_sender_swipe_action(self, action: object) -> None:
        index = self._index_of_sender()
        if index >= 0:
            self.swipe_action_triggered.emit(index, action)

    def _on_sender_dismissed(self, action: object) -> None:
        index = self._index_of_sender()
        if index < 0:
            return
        item = self._items[index]
        self.remove_item(item)
        self.item_dismissed.emit(index, action)

    def add(self, headline: str, **kwargs) -> list_item.ListItem:
        """便捷方法：用参数创建并追加列表项。"""
        return self.add_item(list_item.ListItem(headline, **kwargs))

    def remove_item(self, item: list_item.ListItem) -> None:
        """移除并销毁一个列表项。"""
        if item not in self._items:
            return
        self._items.remove(item)
        item.removeEventFilter(self)
        self._layout.removeWidget(item)
        item.setParent(None)
        item.deleteLater()
        if self._selection_mode is not SelectionMode.NONE:
            self.selection_changed.emit(self.selected_indices)

    def move_item(self, from_index: int, to_index: int) -> None:
        """把列表项从 from_index 移到 to_index 并发出 ``items_reordered``。"""
        count = len(self._items)
        if not 0 <= from_index < count or not 0 <= to_index < count:
            return
        if from_index == to_index:
            return
        item = self._items.pop(from_index)
        self._items.insert(to_index, item)
        self._layout.removeWidget(item)
        self._layout.insertWidget(to_index, item)
        self.items_reordered.emit(from_index, to_index)

    def clear(self) -> None:
        """移除全部列表项。"""
        for item in self._items:
            item.removeEventFilter(self)
            self._layout.removeWidget(item)
            item.setParent(None)
            item.deleteLater()
        self._items.clear()

    @property
    def selected_indices(self) -> list[int]:
        """已选中项的下标。"""
        return [i for i, item in enumerate(self._items) if item.selected]

    def set_selected(self, indices: list[int]) -> None:
        """设置选中项。"""
        chosen = set(indices)
        if self._selection_mode is SelectionMode.SINGLE and len(chosen) > 1:
            chosen = {min(chosen)}
        if self._selection_mode is SelectionMode.NONE:
            chosen = set()
        for index, item in enumerate(self._items):
            item.set_selected(index in chosen)
        self.selection_changed.emit(self.selected_indices)

    def _on_item_clicked(self, index: int) -> None:
        self.item_clicked.emit(index)
        if self._selection_mode is SelectionMode.SINGLE:
            self.set_selected([index])
        elif self._selection_mode is SelectionMode.MULTIPLE:
            current = set(self.selected_indices)
            if index in current:
                current.remove(index)
            else:
                current.add(index)
            self.set_selected(sorted(current))

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, 320)

    # ---- 拖动排序 ---------------------------------------------------------

    @property
    def is_reordering(self) -> bool:
        """是否正在拖动排序。"""
        return self._drag_item is not None

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if not self._reorderable or not isinstance(watched, list_item.ListItem):
            return super().eventFilter(watched, event)
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress:
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._press_item = watched
                self._press_pos = event.position()
        elif kind == QtCore.QEvent.Type.MouseMove:
            if self._drag_item is not None:
                self._drag_move(watched, event)
                return True
            if self._press_item is watched and self._should_start(
                watched, event
            ):
                self._begin_drag(watched, event)
                return True
        elif kind == QtCore.QEvent.Type.MouseButtonRelease:
            self._press_item = None
            if self._drag_item is not None:
                self._end_drag()
                return True
        return super().eventFilter(watched, event)

    def _should_start(
        self, item: list_item.ListItem, event: QtGui.QMouseEvent
    ) -> bool:
        delta = event.position() - self._press_pos
        if abs(delta.y()) <= REORDER_THRESHOLD:
            return False
        # 已经在水平滑动显露操作的项不再进入排序。
        return abs(delta.y()) > abs(delta.x()) and abs(item.swipe_offset) < 0.5

    def _begin_drag(
        self, item: list_item.ListItem, event: QtGui.QMouseEvent
    ) -> None:
        item.cancel_press()
        item.cancel_swipe()
        self._drag_item = item
        self._drag_from = self._items.index(item)
        self._drag_to = self._drag_from
        self._grab_offset = round(self._press_pos.y())
        pixmap = item.grab()
        self._ghost = _ReorderGhost(pixmap, self._container)
        self._placeholder = QtWidgets.QWidget(self._container)
        self._placeholder.setFixedHeight(item.height())
        self._layout.replaceWidget(item, self._placeholder)
        item.hide()
        self._ghost.show()
        self._ghost.raise_()
        self._drag_move(item, event)

    def _pointer_y(
        self, item: list_item.ListItem, event: QtGui.QMouseEvent
    ) -> int:
        return self._container.mapFromGlobal(
            item.mapToGlobal(event.position().toPoint())
        ).y()

    def _drag_move(
        self, item: list_item.ListItem, event: QtGui.QMouseEvent
    ) -> None:
        if self._ghost is None or self._placeholder is None:
            return
        pointer_y = self._pointer_y(item, event)
        top = pointer_y - self._grab_offset
        self._ghost.move(-GHOST_MARGIN, top - GHOST_MARGIN)
        center = top + self._placeholder.height() / 2
        target = self._layout_index_for(item, center)
        if target != self._drag_to:
            self._drag_to = target
            self._layout.removeWidget(self._placeholder)
            self._layout.insertWidget(target, self._placeholder)
        self._autoscroll(item, event)

    def _layout_index_for(self, item: list_item.ListItem, center: float) -> int:
        """按浮层中心的 y 坐标决定占位符应处的位置。"""
        others = [other for other in self._items if other is not item]
        for index, other in enumerate(others):
            if center < other.geometry().center().y():
                return index
        return len(others)

    def _autoscroll(
        self, item: list_item.ListItem, event: QtGui.QMouseEvent
    ) -> None:
        viewport_y = (
            self.viewport()
            .mapFromGlobal(item.mapToGlobal(event.position().toPoint()))
            .y()
        )
        bar = self.verticalScrollBar()
        if viewport_y < AUTOSCROLL_MARGIN:
            bar.setValue(bar.value() - AUTOSCROLL_STEP)
        elif viewport_y > self.viewport().height() - AUTOSCROLL_MARGIN:
            bar.setValue(bar.value() + AUTOSCROLL_STEP)

    def _end_drag(self) -> None:
        item = self._drag_item
        if item is None:
            return
        self._drag_item = None
        if self._placeholder is not None:
            self._layout.replaceWidget(self._placeholder, item)
            self._placeholder.setParent(None)
            self._placeholder.deleteLater()
            self._placeholder = None
        if self._ghost is not None:
            self._ghost.hide()
            self._ghost.setParent(None)
            self._ghost.deleteLater()
            self._ghost = None
        item.show()
        if self._drag_to != self._drag_from:
            self._items.remove(item)
            self._items.insert(self._drag_to, item)
            self.items_reordered.emit(self._drag_from, self._drag_to)
        self._drag_from = self._drag_to = -1
