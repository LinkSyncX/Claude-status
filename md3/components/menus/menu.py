"""弹出菜单（Menu）。

菜单是独立的顶层弹出窗口：容器 ``surface_container``、4dp 圆角、
海拔 level 2；菜单项高 48dp，支持前置图标、后置文字/图标、勾选态、
分隔线与子菜单。菜单项超出可用高度（屏幕或 ``max_height``）时容器
内部滚动：滚轮、方向键、PageUp / PageDown、Home / End 均可滚动，
右侧显示细滚动条；输入字母可跳转到以之开头的菜单项。
"""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import state_layer as state_layer_module
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ITEM_HEIGHT = 48.0
MIN_WIDTH = 112.0
MAX_WIDTH = 280.0
VERTICAL_PADDING = 8.0
HORIZONTAL_PADDING = 12.0
ICON_SIZE = 24.0
ICON_GAP = 12.0
DIVIDER_HEIGHT = 1.0
DIVIDER_MARGIN = 8.0
SHADOW_MARGIN = 16
LABEL_STYLE = typography_tokens.TypeRole.BODY_LARGE
TRAILING_STYLE = typography_tokens.TypeRole.BODY_LARGE
ELEVATION = elevation.Level.LEVEL_2
# 滚动：滚轮每格滚动一项；滚动条为 4dp 宽的圆角细条，贴容器右缘。
WHEEL_STEP = ITEM_HEIGHT
SCROLLBAR_WIDTH = 4.0
SCROLLBAR_MARGIN = 2.0
SCROLLBAR_MIN_THUMB = 24.0
SCROLLBAR_OPACITY = 0.4
# 连续按键在此间隔内视为同一次首字母搜索。
TYPEAHEAD_TIMEOUT_MS = 1000


@dataclasses.dataclass
class MenuItem:
    """菜单项。

    Attributes:
        text: 标签。
        icon: 前置图标。
        trailing_icon: 后置图标。
        trailing_text: 后置文字（例如快捷键提示）。
        enabled: 是否可用。
        checkable: 是否可勾选。
        checked: 勾选状态。
        submenu: 子菜单。
        separator: 为真时表示一条分隔线。
        key: 业务侧标识。
    """

    text: str = ""
    icon: icons.IconLike = None
    trailing_icon: icons.IconLike = None
    trailing_text: str = ""
    enabled: bool = True
    checkable: bool = False
    checked: bool = False
    submenu: Menu | None = None
    separator: bool = False
    key: Any = None

    @classmethod
    def divider(cls) -> MenuItem:
        """创建分隔线。"""
        return cls(separator=True)


class Menu(widget.MaterialWidget):
    """弹出菜单。

    Args:
        items: 初始菜单项。
        max_height: 容器最大高度（px）；None 表示只受屏幕可用高度限制。
            菜单项总高度超出时在容器内滚动。
        parent: 父控件（仅用于对象归属，菜单本身是顶层窗口）。
    """

    triggered = QtCore.Signal(object)
    closed = QtCore.Signal()

    def __init__(
        self,
        items: list[MenuItem | str] | None = None,
        max_height: float | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Popup
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._items: list[MenuItem] = []
        self._layers: list[state_layer_module.StateLayer] = []
        self._hovered = -1
        self._focused = -1
        self._open_submenu: Menu | None = None
        self._parent_menu: Menu | None = None
        self._max_height = max_height
        # 弹出时由所在屏幕的可用高度决定的上限。
        self._screen_limit: float | None = None
        self._scroll = 0.0
        self._typeahead = ""
        self._typeahead_timer = QtCore.QTimer(self)
        self._typeahead_timer.setSingleShot(True)
        self._typeahead_timer.setInterval(TYPEAHEAD_TIMEOUT_MS)
        self._typeahead_timer.timeout.connect(self._clear_typeahead)
        # 弹出时容器自上而下展开并淡入。
        self._reveal = animation.AnimatedFloat(self, 1.0, self.update)
        if items:
            self.set_items(items)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.PopupMenu

    @override
    def accessible_value(self) -> str:
        # 菜单项由同一控件绘制，把当前聚焦项文字作为取值播报。
        if 0 <= self._focused < len(self._items):
            return self._items[self._focused].text
        return ""

    # ---- 菜单项 -----------------------------------------------------------

    @property
    def items(self) -> list[MenuItem]:
        """全部菜单项。"""
        return list(self._items)

    def set_items(self, items: list[MenuItem | str]) -> None:
        """替换全部菜单项。"""
        self._items = [
            MenuItem(text=item) if isinstance(item, str) else item
            for item in items
        ]
        self._layers = [
            state_layer_module.StateLayer(self, on_change=self.update)
            for _ in self._items
        ]
        for item in self._items:
            if item.submenu is not None:
                item.submenu._parent_menu = self  # pylint: disable=protected-access
        self._hovered = -1
        self._focused = -1
        self._scroll = 0.0
        self.adjustSize()
        self.update()

    def add_item(self, item: MenuItem | str) -> MenuItem:
        """追加菜单项并返回它。"""
        entry = MenuItem(text=item) if isinstance(item, str) else item
        self.set_items([*self._items, entry])
        return entry

    def add_divider(self) -> None:
        """追加分隔线。"""
        self.add_item(MenuItem.divider())

    @property
    def max_height(self) -> float | None:
        """容器最大高度，None 表示只受屏幕限制。"""
        return self._max_height

    def set_max_height(self, max_height: float | None) -> None:
        """设置容器最大高度。"""
        self._max_height = max_height
        self.adjustSize()
        self.update()

    # ---- 滚动 -------------------------------------------------------------

    @property
    def scroll_offset(self) -> float:
        """当前滚动偏移（px）。"""
        return self._scroll

    def max_scroll(self) -> float:
        """可滚动的最大偏移，内容未超出容器时为 0。"""
        return max(0.0, self._content_height() - self.container_rect().height())

    def is_scrollable(self) -> bool:
        """菜单项是否超出容器需要滚动。"""
        return self.max_scroll() > 0.5

    def set_scroll_offset(self, offset: float) -> None:
        """设置滚动偏移（自动限制在可滚动范围内）。"""
        offset = max(0.0, min(self.max_scroll(), offset))
        if offset == self._scroll:
            return
        self._scroll = offset
        self._close_submenu()
        self.update()

    def scroll_to_item(self, index: int) -> None:
        """滚动到第 index 项完全可见。"""
        if not 0 <= index < len(self._items) or not self.is_scrollable():
            return
        container = self.container_rect()
        rect = self.item_rect(index)
        top = container.top() + VERTICAL_PADDING
        bottom = container.bottom() - VERTICAL_PADDING
        if rect.top() < top:
            self.set_scroll_offset(self._scroll - (top - rect.top()))
        elif rect.bottom() > bottom:
            self.set_scroll_offset(self._scroll + (rect.bottom() - bottom))

    # ---- 几何 -------------------------------------------------------------

    def _has_icons(self) -> bool:
        return any(
            item.icon is not None or item.checkable for item in self._items
        )

    def _content_width(self) -> float:
        width = MIN_WIDTH
        for item in self._items:
            if item.separator:
                continue
            item_width = 2 * HORIZONTAL_PADDING
            if self._has_icons():
                item_width += ICON_SIZE + ICON_GAP
            item_width += typography.text_width(item.text, LABEL_STYLE)
            if item.trailing_text:
                item_width += ICON_GAP + typography.text_width(
                    item.trailing_text, TRAILING_STYLE
                )
            if item.trailing_icon is not None or item.submenu is not None:
                item_width += ICON_GAP + ICON_SIZE
            width = max(width, item_width)
        return min(MAX_WIDTH, width)

    def _content_height(self) -> float:
        height = 2 * VERTICAL_PADDING
        for item in self._items:
            if item.separator:
                height += DIVIDER_HEIGHT + 2 * DIVIDER_MARGIN
            else:
                height += ITEM_HEIGHT
        return height

    def _viewport_height(self) -> float:
        """容器高度：内容高度受 ``max_height`` 与屏幕可用高度限制。"""
        height = self._content_height()
        for limit in (self._max_height, self._screen_limit):
            if limit is not None:
                height = min(height, limit)
        return max(height, ITEM_HEIGHT + 2 * VERTICAL_PADDING)

    def container_rect(self) -> QtCore.QRectF:
        """菜单容器矩形（阴影边距之内）。"""
        return QtCore.QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )

    def item_rect(self, index: int) -> QtCore.QRectF:
        """第 index 个菜单项的矩形（已计入滚动偏移）。"""
        container = self.container_rect()
        y = container.top() + VERTICAL_PADDING - self._scroll
        for current, item in enumerate(self._items):
            height = (
                DIVIDER_HEIGHT + 2 * DIVIDER_MARGIN
                if item.separator
                else ITEM_HEIGHT
            )
            if current == index:
                return QtCore.QRectF(
                    container.left(), y, container.width(), height
                )
            y += height
        return QtCore.QRectF()

    def _index_at(self, point: QtCore.QPointF) -> int:
        if not self.container_rect().contains(point):
            return -1
        for index, item in enumerate(self._items):
            if not item.separator and self.item_rect(index).contains(point):
                return index
        return -1

    @override
    def sizeHint(self) -> QtCore.QSize:
        return typography.size_hint(
            self._content_width() + 2 * SHADOW_MARGIN,
            self._viewport_height() + 2 * SHADOW_MARGIN,
        )

    # ---- 显示 -------------------------------------------------------------

    def popup(self, global_pos: QtCore.QPoint) -> None:
        """在全局坐标处弹出菜单（容器左上角对齐该点，越界时翻转）。

        菜单高度不会超过所在屏幕的可用区域，超出的菜单项通过滚动查看。
        """
        screen = QtGui.QGuiApplication.screenAt(global_pos)
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        self._screen_limit = float(available.height() - 2 * SHADOW_MARGIN)
        self._scroll = 0.0
        # 顶层窗口的 adjustSize 会把高度压到屏幕的 2/3，这里按自身尺寸提示
        # 直接调整，滚动上限已由屏幕可用高度决定。
        self.resize(self.sizeHint().expandedTo(self.minimumSize()))
        size = self.size()
        x = global_pos.x() - SHADOW_MARGIN
        y = global_pos.y() - SHADOW_MARGIN
        if x + size.width() > available.right():
            x = global_pos.x() - size.width() + SHADOW_MARGIN
        if y + size.height() > available.bottom():
            y = global_pos.y() - size.height() + SHADOW_MARGIN
        x = max(available.left(), x)
        y = max(available.top(), y)
        self.move(x, y)
        self._hovered = -1
        self._focused = -1
        self._clear_typeahead()
        self._reveal.set(0.0)
        self._reveal.animate_to(
            1.0, motion.MEDIUM2, motion.EMPHASIZED_DECELERATE
        )
        self.show()
        self.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

    def popup_below(self, anchor: QtWidgets.QWidget, gap: int = 4) -> None:
        """在锚点控件下方弹出，宽度不小于锚点。"""
        self.setMinimumWidth(anchor.width() + 2 * SHADOW_MARGIN)
        self.popup(anchor.mapToGlobal(QtCore.QPoint(0, anchor.height() + gap)))

    def close_all(self) -> None:
        """关闭本菜单及所有父菜单。"""
        menu: Menu | None = self
        while menu is not None:
            parent = menu._parent_menu  # pylint: disable=protected-access
            menu.hide()
            menu = parent

    def _close_submenu(self) -> None:
        if self._open_submenu is not None:
            self._open_submenu.hide()
            self._open_submenu = None

    def _open_submenu_for(self, index: int) -> None:
        item = self._items[index]
        if item.submenu is None or self._open_submenu is item.submenu:
            return
        self._close_submenu()
        rect = self.item_rect(index)
        submenu = item.submenu
        submenu.setLayoutDirection(self.layoutDirection())
        submenu.adjustSize()
        if self.is_rtl():
            # RTL 下子菜单向左展开，其容器右缘贴本菜单项左缘。
            x = rect.left() - (submenu.sizeHint().width() - 2 * SHADOW_MARGIN)
        else:
            x = rect.right()
        global_pos = self.mapToGlobal(
            QtCore.QPoint(round(x), round(rect.top() - VERTICAL_PADDING))
        )
        submenu._parent_menu = self  # pylint: disable=protected-access
        submenu.popup(global_pos)
        self._open_submenu = submenu

    def _trigger(self, index: int) -> None:
        item = self._items[index]
        if not item.enabled or item.separator:
            return
        if item.submenu is not None:
            self._open_submenu_for(index)
            return
        if item.checkable:
            item.checked = not item.checked
        self.close_all()
        self.triggered.emit(item)

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self._close_submenu()
        self._set_hovered(-1)
        self._typeahead_timer.stop()
        self._clear_typeahead()
        # 复位揭示进度，保证隐藏状态下（例如离屏渲染）完整绘制。
        self._reveal.set(1.0)
        self.closed.emit()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        container = self.container_rect()
        shape = shape_tokens.SHAPE_EXTRA_SMALL
        reveal = self._reveal.value
        if reveal < 0.999:
            painter.setOpacity(min(1.0, reveal * 3))
            revealed_height = (
                SHADOW_MARGIN + container.height() * reveal + SHADOW_MARGIN
            )
            painter.setClipRect(
                QtCore.QRectF(0, 0, self.width(), revealed_height)
            )
        elevation_utils.paint_shadow(
            painter,
            container,
            shape,
            ELEVATION,
            self.color("shadow"),
            self.devicePixelRatioF(),
        )
        path = shape_utils.rounded_rect_path(container, shape)
        shape_utils.fill_shape(painter, path, self.color("surface_container"))
        painter.save()
        painter.setClipPath(path)
        for index, item in enumerate(self._items):
            rect = self.item_rect(index)
            if (
                rect.bottom() < container.top()
                or rect.top() > container.bottom()
            ):
                continue
            if item.separator:
                y = rect.center().y()
                painter.setPen(QtGui.QPen(self.color("outline_variant"), 1))
                painter.drawLine(
                    QtCore.QPointF(rect.left(), y),
                    QtCore.QPointF(rect.right(), y),
                )
                continue
            self._paint_item(painter, index, item, rect)
        self._paint_scrollbar(painter, container)
        painter.restore()

    def _paint_scrollbar(
        self, painter: QtGui.QPainter, container: QtCore.QRectF
    ) -> None:
        max_scroll = self.max_scroll()
        if max_scroll <= 0.5:
            return
        track_top = container.top() + VERTICAL_PADDING
        track_height = container.height() - 2 * VERTICAL_PADDING
        visible = container.height() / self._content_height()
        thumb_height = max(SCROLLBAR_MIN_THUMB, track_height * visible)
        thumb_top = track_top + (track_height - thumb_height) * (
            self._scroll / max_scroll
        )
        thumb = self.visual_rect(
            QtCore.QRectF(
                container.right() - SCROLLBAR_MARGIN - SCROLLBAR_WIDTH,
                thumb_top,
                SCROLLBAR_WIDTH,
                thumb_height,
            )
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(thumb, shape_tokens.SHAPE_FULL),
            theme_module.with_alpha(
                self.color("on_surface_variant"), SCROLLBAR_OPACITY
            ),
        )

    def _paint_item(
        self,
        painter: QtGui.QPainter,
        index: int,
        item: MenuItem,
        rect: QtCore.QRectF,
    ) -> None:
        if not item.enabled:
            color = theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            icon_color = color
            trailing_color = color
        else:
            color = self.color("on_surface")
            icon_color = self.color("on_surface_variant")
            trailing_color = self.color("on_surface_variant")
        left = rect.left() + HORIZONTAL_PADDING
        if self._has_icons():
            icon = None
            if item.checkable and item.checked:
                icon = icons.Icon("check", ICON_SIZE)
            elif item.icon is not None:
                icon = icons.coerce(item.icon, ICON_SIZE)
            if icon is not None:
                icon.paint(
                    painter,
                    self.visual_rect(
                        QtCore.QRectF(
                            left,
                            rect.center().y() - ICON_SIZE / 2,
                            ICON_SIZE,
                            ICON_SIZE,
                        )
                    ),
                    icon_color,
                )
            left += ICON_SIZE + ICON_GAP
        right = rect.right() - HORIZONTAL_PADDING
        trailing_icon = item.trailing_icon
        if item.submenu is not None and trailing_icon is None:
            trailing_icon = "arrow_left" if self.is_rtl() else "arrow_right"
        if trailing_icon is not None:
            icon = icons.coerce(trailing_icon, ICON_SIZE)
            icon.paint(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - ICON_SIZE,
                        rect.center().y() - ICON_SIZE / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    )
                ),
                trailing_color,
            )
            right -= ICON_SIZE + ICON_GAP
        if item.trailing_text:
            width = typography.text_width(item.trailing_text, TRAILING_STYLE)
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - width, rect.top(), width, rect.height()
                    )
                ),
                item.trailing_text,
                TRAILING_STYLE,
                trailing_color,
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )
            right -= width + ICON_GAP
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(
                    left, rect.top(), max(0.0, right - left), rect.height()
                )
            ),
            item.text,
            LABEL_STYLE,
            color,
            self.start_alignment(),
        )
        path = QtGui.QPainterPath()
        path.addRect(rect)
        self._layers[index].paint(painter, path, self.color("on_surface"))

    # ---- 事件 -------------------------------------------------------------

    def _set_hovered(self, index: int) -> None:
        if index == self._hovered:
            return
        if 0 <= self._hovered < len(self._layers):
            self._layers[self._hovered].set_hovered(False)
        self._hovered = index
        if 0 <= index < len(self._layers) and self._items[index].enabled:
            self._layers[index].set_hovered(True)
            self._set_focused(index)
            if self._items[index].submenu is not None:
                self._open_submenu_for(index)

    def _set_focused(self, index: int) -> None:
        if 0 <= self._focused < len(self._layers):
            self._layers[self._focused].set_focused(False)
        self._focused = index
        if 0 <= index < len(self._layers):
            self._layers[index].set_focused(True)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._set_hovered(self._index_at(event.position()))
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._set_hovered(-1)
        super().leaveEvent(event)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if not self.container_rect().contains(event.position()):
            # 点击容器外：Qt 会关闭弹出窗口。
            super().mousePressEvent(event)
            return
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            index = self._index_at(event.position())
            if index >= 0:
                self._trigger(index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self.is_scrollable():
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta:
            step = delta / 120.0 * WHEEL_STEP
        else:
            step = float(event.pixelDelta().y())
        self.set_scroll_offset(self._scroll - step)
        self._set_hovered(self._index_at(event.position()))
        event.accept()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        page = self.container_rect().height() - 2 * VERTICAL_PADDING
        if key == QtCore.Qt.Key.Key_Escape:
            self.hide()
        elif key == QtCore.Qt.Key.Key_Down:
            self._move_focus(1)
        elif key == QtCore.Qt.Key.Key_Up:
            self._move_focus(-1)
        elif key == QtCore.Qt.Key.Key_Home:
            self._focus_edge(first=True)
        elif key == QtCore.Qt.Key.Key_End:
            self._focus_edge(first=False)
        elif key == QtCore.Qt.Key.Key_PageDown:
            self.set_scroll_offset(self._scroll + page)
        elif key == QtCore.Qt.Key.Key_PageUp:
            self.set_scroll_offset(self._scroll - page)
        elif key in (
            QtCore.Qt.Key.Key_Return,
            QtCore.Qt.Key.Key_Enter,
            QtCore.Qt.Key.Key_Space,
        ):
            if self._focused >= 0:
                self._trigger(self._focused)
        elif key == self._submenu_open_key() and self._focused >= 0:
            self._open_submenu_for(self._focused)
        elif key == self._submenu_close_key() and self._parent_menu is not None:
            self.hide()
            self._parent_menu.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)
        elif not self._typeahead_search(event.text()):
            super().keyPressEvent(event)
            return
        event.accept()

    def _submenu_open_key(self) -> QtCore.Qt.Key:
        """展开子菜单的方向键（跟随布局方向）。"""
        return (
            QtCore.Qt.Key.Key_Left if self.is_rtl() else QtCore.Qt.Key.Key_Right
        )

    def _submenu_close_key(self) -> QtCore.Qt.Key:
        """返回父菜单的方向键。"""
        return (
            QtCore.Qt.Key.Key_Right if self.is_rtl() else QtCore.Qt.Key.Key_Left
        )

    def focus_item(self, index: int) -> None:
        """把键盘焦点移到第 index 项并滚动到可见。"""
        if not 0 <= index < len(self._items):
            return
        self._set_focused(index)
        self.scroll_to_item(index)
        self.update()

    def _move_focus(self, delta: int) -> None:
        count = len(self._items)
        if count == 0:
            return
        index = self._focused
        for _ in range(count):
            index = (index + delta) % count
            item = self._items[index]
            if not item.separator and item.enabled:
                self.focus_item(index)
                return

    def _focus_edge(self, first: bool) -> None:
        indices = range(len(self._items))
        for index in indices if first else reversed(indices):
            item = self._items[index]
            if not item.separator and item.enabled:
                self.focus_item(index)
                return

    # ---- 首字母跳转 -------------------------------------------------------

    def _clear_typeahead(self) -> None:
        self._typeahead = ""

    def _typeahead_search(self, text: str) -> bool:
        """把输入字符追加到搜索前缀并聚焦匹配项；无可用字符时返回 False。

        一秒内连续输入视为同一前缀（从当前项开始匹配，保持已匹配的项
        不跳走）；反复按同一个字母则从当前项之后开始查找，在同首字母的
        菜单项之间循环。
        """
        if not text or not text.isprintable() or text.isspace():
            return False
        self._typeahead += text.lower()
        self._typeahead_timer.start()
        count = len(self._items)
        if count == 0:
            return True
        if len(set(self._typeahead)) == 1:
            prefix = self._typeahead[0]
            start = self._focused + 1
        else:
            prefix = self._typeahead
            start = max(self._focused, 0)
        for offset in range(count):
            index = (start + offset) % count
            item = self._items[index]
            if item.separator or not item.enabled:
                continue
            if item.text.lower().startswith(prefix):
                self.focus_item(index)
                return True
        return True
