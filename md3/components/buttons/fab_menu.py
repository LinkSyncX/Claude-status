"""FAB 菜单（FAB menu，M3 Expressive）。

点击 FAB 后它变为 ``primary`` 色的关闭按钮（图标交叉淡入为 ×、圆角变为
完整胶囊），同时在其上方依次弹出若干带图标与文字的胶囊形操作项；点击
操作、点击别处或按 Esc 收起。操作项浮在 FAB 所在窗口之上，因此 FAB 本身
只占据自己的位置。
"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import fab as fab_module
from md3.components.buttons import group
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

ITEM_HEIGHT = 56.0
ITEM_PADDING = 20.0
ITEM_ICON = 24.0
ITEM_ICON_GAP = 12.0
ITEM_GAP = 8.0
MENU_GAP = 12.0
CLOSE_ICON = "close"
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
# 每个操作项依次延迟出现的比例。
STAGGER = 0.12
SLIDE = 24.0


@dataclasses.dataclass
class FabMenuItem:
    """FAB 菜单中的一个操作。

    Attributes:
        text: 标签。
        icon: 图标。
        key: 业务侧标识。
    """

    text: str
    icon: icons.IconLike = None
    key: Any = None


class _MenuFab(fab_module.FloatingActionButton):
    """展开时变为关闭按钮的 FAB。"""

    def __init__(
        self,
        icon: icons.IconLike,
        size: fab_module.FabSize,
        color: fab_module.FabColor,
        parent: QtWidgets.QWidget | None,
    ) -> None:
        super().__init__(icon, size, color, parent=parent)
        self._close_icon = icons.coerce(CLOSE_ICON, size.value.icon)
        self._expand = animation.AnimatedFloat(self, 0.0, self.update)
        self._expand.finished.connect(self.sync_shadow)

    def set_expanded(self, expanded: bool) -> None:
        """切换展开态。"""
        self._expand.spring_to(
            1.0 if expanded else 0.0, motion.EXPRESSIVE_DEFAULT_SPATIAL
        )

    @property
    def expansion(self) -> float:
        """展开过渡进度 0–1。"""
        expand = getattr(self, "_expand", None)
        return expand.value if expand is not None else 0.0

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        expanded = self.expansion > 0.5
        state.expandable = True
        state.expanded = expanded
        state.collapsed = not expanded

    @override
    def container_shape(self) -> shape_tokens.Shape:
        rect = self.container_rect()
        return group.lerp_shape(
            self.fab_size.value.shape,
            shape_tokens.SHAPE_FULL,
            self.expansion,
            rect.width(),
            rect.height(),
        )

    @override
    def _container_color(self) -> QtGui.QColor:
        return _mix(
            super()._container_color(), self.color("primary"), self.expansion
        )

    @override
    def _content_color(self) -> QtGui.QColor:
        return _mix(
            super()._content_color(), self.color("on_primary"), self.expansion
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        progress = self.expansion
        rect = self.container_rect()
        size = self.fab_size.value.icon
        icon_rect = QtCore.QRectF(
            rect.center().x() - size / 2,
            rect.center().y() - size / 2,
            size,
            size,
        )
        color = self._content_color()
        painter.save()
        painter.translate(rect.center())
        # 图标交叉淡入并旋转 90°，× 由 + 的姿态转出。
        painter.rotate(progress * 90.0)
        painter.translate(-rect.center())
        if self.icon is not None and progress < 1.0:
            painter.setOpacity(1.0 - progress)
            self.icon.paint(painter, icon_rect, color)
        if self._close_icon is not None and progress > 0.0:
            painter.setOpacity(progress)
            self._close_icon.paint(painter, icon_rect, color)
        painter.restore()


def _mix(a: QtGui.QColor, b: QtGui.QColor, t: float) -> QtGui.QColor:
    t = max(0.0, min(1.0, t))
    return QtGui.QColor.fromRgbF(
        a.redF() + (b.redF() - a.redF()) * t,
        a.greenF() + (b.greenF() - a.greenF()) * t,
        a.blueF() + (b.blueF() - a.blueF()) * t,
        a.alphaF() + (b.alphaF() - a.alphaF()) * t,
    )


class _MenuItemButton(widget.InteractiveWidget):
    """FAB 菜单中的胶囊形操作项。"""

    def __init__(
        self, item: FabMenuItem, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.item = item
        self.setAccessibleName(item.text)
        self._icon = icons.coerce(item.icon, ITEM_ICON)
        self._reveal = 1.0
        self.set_outer_margin(0.0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self.set_elevation(elevation.Level.LEVEL_1)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.MenuItem

    def set_reveal(self, value: float) -> None:
        """设置出现进度（用作整体不透明度）。"""
        self._reveal = max(0.0, min(1.0, value))
        self.update()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        painter.setOpacity(self._reveal)
        super().paint(painter)

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = 2 * ITEM_PADDING + typography.text_width(
            self.item.text, LABEL_STYLE
        )
        if self._icon is not None:
            width += ITEM_ICON + ITEM_ICON_GAP
        return typography.size_hint(width, ITEM_HEIGHT)

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_FULL

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("on_primary_container")

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        shape_utils.fill_shape(
            painter, self.container_path(), self.color("primary_container")
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        color = self.color("on_primary_container")
        left = rect.left() + ITEM_PADDING
        if self._icon is not None:
            self._icon.paint(
                painter,
                QtCore.QRectF(
                    left,
                    rect.center().y() - ITEM_ICON / 2,
                    ITEM_ICON,
                    ITEM_ICON,
                ),
                color,
            )
            left += ITEM_ICON + ITEM_ICON_GAP
        typography.paint_text(
            painter,
            QtCore.QRectF(
                left,
                rect.top(),
                rect.right() - ITEM_PADDING - left,
                rect.height(),
            ),
            self.item.text,
            LABEL_STYLE,
            color,
        )


class FabMenu(widget.MaterialWidget):
    """FAB 菜单。

    Args:
        items: 操作项。
        icon: 收起时 FAB 的图标。
        size: FAB 尺寸。
        color: FAB 配色。
        parent: 父控件。
    """

    triggered = QtCore.Signal(object)
    expanded_changed = QtCore.Signal(bool)

    def __init__(
        self,
        items: Sequence[FabMenuItem | str] = (),
        icon: icons.IconLike = "add",
        size: fab_module.FabSize = fab_module.FabSize.REGULAR,
        color: fab_module.FabColor = fab_module.FabColor.PRIMARY,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[FabMenuItem] = [
            FabMenuItem(item) if isinstance(item, str) else item
            for item in items
        ]
        self._fab = _MenuFab(icon, size, color, self)
        self._fab.clicked.connect(self.toggle)
        self._expanded = False
        self._buttons: list[_MenuItemButton] = []
        self._progress: list[animation.AnimatedFloat] = []
        self._filtering = False
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        state.expandable = True
        state.expanded = self._expanded
        state.collapsed = not self._expanded

    # ---- 数据 -------------------------------------------------------------

    @property
    def items(self) -> list[FabMenuItem]:
        """操作项。"""
        return list(self._items)

    def set_items(self, items: Sequence[FabMenuItem | str]) -> None:
        """替换操作项（会先收起）。"""
        self.collapse()
        self._items = [
            FabMenuItem(item) if isinstance(item, str) else item
            for item in items
        ]

    @property
    def fab(self) -> fab_module.FloatingActionButton:
        """内部 FAB。"""
        return self._fab

    @property
    def expanded(self) -> bool:
        """是否展开。"""
        return self._expanded

    @property
    def item_buttons(self) -> list[_MenuItemButton]:
        """当前展开的操作项按钮（收起时为空）。"""
        return list(self._buttons)

    @override
    def sizeHint(self) -> QtCore.QSize:
        return self._fab.sizeHint()

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._fab.setGeometry(self.rect())

    # ---- 展开与收起 -------------------------------------------------------

    def toggle(self) -> None:
        """切换展开 / 收起。"""
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self) -> None:
        """展开菜单。"""
        if self._expanded or not self._items:
            return
        host = self.window()
        self._expanded = True
        self._fab.set_expanded(True)
        for index, item in enumerate(self._items):
            button = _MenuItemButton(item, host)
            button.clicked.connect(lambda i=item: self._on_item(i))
            button.show()
            button.raise_()
            self._buttons.append(button)
            progress = animation.AnimatedFloat(self, 0.0, self._layout_items)
            self._progress.append(progress)
            delay = (len(self._items) - 1 - index) * STAGGER
            progress.set(-delay)
            progress.spring_to(1.0, motion.EXPRESSIVE_DEFAULT_SPATIAL)
        self._layout_items()
        self._set_filtering(True)
        self.expanded_changed.emit(True)

    def collapse(self) -> None:
        """收起菜单。"""
        if not self._expanded:
            return
        self._expanded = False
        self._fab.set_expanded(False)
        self._set_filtering(False)
        for button in self._buttons:
            button.hide()
            button.deleteLater()
        self._buttons.clear()
        self._progress.clear()
        self.expanded_changed.emit(False)

    def _on_item(self, item: FabMenuItem) -> None:
        self.triggered.emit(item)
        self.collapse()

    def _layout_items(self) -> None:
        """把操作项右对齐堆叠在 FAB 上方，按各自进度上滑淡入。"""
        if not self._buttons:
            return
        host = self.window()
        origin = self.mapTo(host, QtCore.QPoint(0, 0))
        fab_rect = self._fab.container_rect().translated(origin)
        bottom = fab_rect.top() - MENU_GAP
        for button, progress in zip(
            reversed(self._buttons), reversed(self._progress), strict=True
        ):
            size = button.sizeHint()
            value = max(0.0, min(1.0, progress.value))
            y = bottom - size.height() + SLIDE * (1.0 - value)
            button.setGeometry(
                round(fab_rect.right() - size.width()),
                round(y),
                size.width(),
                size.height(),
            )
            button.setVisible(value > 0.0)
            button.set_reveal(value)
            bottom -= size.height() + ITEM_GAP

    # ---- 外部点击 / Esc ---------------------------------------------------

    def _set_filtering(self, enabled: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None or enabled == self._filtering:
            return
        self._filtering = enabled
        if enabled:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)

    def _owns(self, obj: QtCore.QObject | None) -> bool:
        while obj is not None:
            if obj is self or obj in self._buttons:
                return True
            obj = obj.parent()
        return False

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress and isinstance(
            watched, QtWidgets.QWidget
        ):
            if not self._owns(watched):
                self.collapse()
        elif (
            kind == QtCore.QEvent.Type.KeyPress
            and isinstance(event, QtGui.QKeyEvent)
            and event.key() == QtCore.Qt.Key.Key_Escape
        ):
            self.collapse()
            return True
        elif kind in (QtCore.QEvent.Type.Resize, QtCore.QEvent.Type.Move) and (
            watched is self.window()
        ):
            self._layout_items()
        return super().eventFilter(watched, event)

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self.collapse()
