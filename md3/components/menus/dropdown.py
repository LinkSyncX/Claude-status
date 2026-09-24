"""下拉选择（Exposed dropdown menu）。

外观与文本框一致（filled / outlined），点击后在下方弹出选项菜单。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.menus import menu as menu_module
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

CONTAINER_HEIGHT = 56.0
# outlined 样式的浮动标签骑在上边框上，控件顶部为此预留的空间。
LABEL_TOP_SPACE = 8.0
MIN_WIDTH = 160.0
PADDING = 16.0
ICON_SIZE = 24.0
LABEL_STYLE = typography_tokens.TypeRole.BODY_LARGE
FLOATING_LABEL_STYLE = typography_tokens.TypeRole.BODY_SMALL
OUTLINE_WIDTH = 1.0
FOCUSED_OUTLINE_WIDTH = 2.0


class DropdownMenu(widget.InteractiveWidget):
    """下拉选择框。

    Args:
        options: 选项文字列表。
        label: 浮动标签。
        selected_index: 初始选中下标，-1 为未选择。
        outlined: 为真使用 outlined 样式，否则为 filled。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(int)

    def __init__(
        self,
        options: list[str],
        label: str = "",
        selected_index: int = -1,
        outlined: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._options = list(options)
        self._label = label
        self._selected = (
            selected_index if 0 <= selected_index < len(options) else -1
        )
        self._outlined = outlined
        self._menu = menu_module.Menu(parent=self)
        self._menu.triggered.connect(self._on_triggered)
        self._menu.closed.connect(self._on_menu_closed)
        self._arrow = animation.AnimatedFloat(self, 0.0, self.update)
        self._open = False
        self.set_outer_margin(0.0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 属性 -------------------------------------------------------------

    @property
    def options(self) -> list[str]:
        """选项列表。"""
        return list(self._options)

    def set_options(self, options: list[str]) -> None:
        """替换选项并清空选择。"""
        self._options = list(options)
        self._selected = -1
        self.updateGeometry()
        self.update()

    @property
    def selected_index(self) -> int:
        """当前选中下标。"""
        return self._selected

    @property
    def selected_text(self) -> str:
        """当前选中文字，未选择时为空字符串。"""
        if 0 <= self._selected < len(self._options):
            return self._options[self._selected]
        return ""

    def set_selected_index(self, index: int) -> None:
        """设置选中下标，变化时发出 ``selection_changed``。"""
        if index < -1 or index >= len(self._options):
            return
        if index != self._selected:
            self._selected = index
            self.selection_changed.emit(index)
            self.update()

    @property
    def label(self) -> str:
        """浮动标签。"""
        return self._label

    def set_label(self, label: str) -> None:
        """设置浮动标签。"""
        self._label = label
        self.update()

    @property
    def is_open(self) -> bool:
        """菜单是否展开。"""
        return self._open

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ComboBox

    @override
    def accessible_name(self) -> str:
        return self._label or self.toolTip()

    @override
    def accessible_value(self) -> str:
        return self.selected_text

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        state.hasPopup = True
        state.expandable = True
        state.expanded = self._open
        state.collapsed = not self._open

    # ---- 尺寸 -------------------------------------------------------------

    @override
    def sizeHint(self) -> QtCore.QSize:
        widest = max(
            (
                typography.text_width(text, LABEL_STYLE)
                for text in self._options
            ),
            default=0.0,
        )
        widest = max(widest, typography.text_width(self._label, LABEL_STYLE))
        width = max(MIN_WIDTH, widest + 2 * PADDING + ICON_SIZE + 8)
        return typography.size_hint(width, CONTAINER_HEIGHT + self._top_space())

    def _top_space(self) -> float:
        return LABEL_TOP_SPACE if self._outlined and self._label else 0.0

    @override
    def container_rect(self) -> QtCore.QRectF:
        return QtCore.QRectF(self.rect()).adjusted(0, self._top_space(), 0, 0)

    @override
    def container_shape(self) -> shape_tokens.Shape:
        if self._outlined:
            return shape_tokens.SHAPE_EXTRA_SMALL
        return shape_tokens.Shape.top(shape_tokens.EXTRA_SMALL)

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    # ---- 行为 -------------------------------------------------------------

    @override
    def activate(self) -> None:
        if self._open:
            self._menu.hide()
        else:
            self._open_menu()
        super().activate()

    def _open_menu(self) -> None:
        items = []
        for index, text in enumerate(self._options):
            items.append(menu_module.MenuItem(text=text, key=index))
        self._menu.set_items(items)
        self._open = True
        self._arrow.animate_to(1.0, motion.SHORT4, motion.STANDARD)
        self._menu.popup_below(self)
        if self._selected >= 0:
            # 选项较多时把当前选中项滚动到可见并作为键盘起点。
            self._menu.focus_item(self._selected)

    def _on_triggered(self, item: menu_module.MenuItem) -> None:
        self.set_selected_index(int(item.key))

    def _on_menu_closed(self) -> None:
        self._open = False
        self._arrow.animate_to(0.0, motion.SHORT4, motion.STANDARD)
        self.update()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Down and not self._open:
            self._open_menu()
            event.accept()
            return
        super().keyPressEvent(event)

    # ---- 绘制 -------------------------------------------------------------

    def _is_active(self) -> bool:
        return self._open or self.focus_visible

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("on_surface")

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        path = self.container_path()
        disabled = not self.isEnabled()
        if self._outlined:
            if disabled:
                outline = theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_OUTLINE_OPACITY,
                )
                width = OUTLINE_WIDTH
            elif self._is_active():
                outline = self.color("primary")
                width = FOCUSED_OUTLINE_WIDTH
            else:
                outline = self.color("outline")
                width = OUTLINE_WIDTH
            notch = self.notch_rect()
            painter.save()
            if notch is not None:
                # 浮动标签处把描边裁掉，不依赖背景色遮挡。
                painter.setClipRegion(
                    QtGui.QRegion(self.rect()).subtracted(
                        QtGui.QRegion(notch.toAlignedRect())
                    )
                )
            shape_utils.fill_shape(painter, path, None, outline, width)
            painter.restore()
        else:
            fill = (
                theme_module.with_alpha(self.color("on_surface"), 0.04)
                if disabled
                else self.color("surface_container_highest")
            )
            shape_utils.fill_shape(painter, path, fill)
            indicator = (
                self.color("primary")
                if self._is_active()
                else self.color("on_surface_variant")
            )
            if disabled:
                indicator = theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTENT_OPACITY,
                )
            height = (
                FOCUSED_OUTLINE_WIDTH if self._is_active() else OUTLINE_WIDTH
            )
            painter.fillRect(
                QtCore.QRectF(
                    rect.left(), rect.bottom() - height, rect.width(), height
                ),
                indicator,
            )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        disabled = not self.isEnabled()
        text_color = (
            theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            if disabled
            else self.color("on_surface")
        )
        label_color = (
            text_color
            if disabled
            else self.color(
                "primary" if self._is_active() else "on_surface_variant"
            )
        )
        value = self.selected_text
        left = rect.left() + PADDING
        right = rect.right() - PADDING - ICON_SIZE - 8
        alignment = self.start_alignment()
        if value:
            if self._label:
                label_height = 16.0
                label_rect = QtCore.QRectF(
                    left, rect.top() + 8, right - left, label_height
                )
                if self._outlined:
                    self._paint_notched_label(painter, label_rect, label_color)
                else:
                    typography.paint_text(
                        painter,
                        self.visual_rect(label_rect),
                        self._label,
                        FLOATING_LABEL_STYLE,
                        label_color,
                        alignment,
                    )
                value_rect = QtCore.QRectF(
                    left, rect.top() + 24, right - left, rect.height() - 32
                )
            else:
                value_rect = QtCore.QRectF(
                    left, rect.top(), right - left, rect.height()
                )
            typography.paint_text(
                painter,
                self.visual_rect(value_rect),
                value,
                LABEL_STYLE,
                text_color,
                alignment,
            )
        else:
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(left, rect.top(), right - left, rect.height())
                ),
                self._label,
                LABEL_STYLE,
                label_color,
                alignment,
            )
        # 下拉箭头随展开旋转 180 度。
        icon = icons.Icon("arrow_drop_down", ICON_SIZE)
        center = QtCore.QPointF(
            self.visual_x(rect.right() - PADDING - ICON_SIZE / 2),
            rect.center().y(),
        )
        painter.save()
        painter.translate(center)
        painter.rotate(180.0 * self._arrow.value)
        icon.paint(
            painter,
            QtCore.QRectF(-ICON_SIZE / 2, -ICON_SIZE / 2, ICON_SIZE, ICON_SIZE),
            self.color("on_surface_variant") if not disabled else text_color,
        )
        painter.restore()

    def notch_rect(self) -> QtCore.QRectF | None:
        """outlined 样式下浮动标签在上边框开出的缺口；未浮起时为 None。"""
        if not self._outlined or not self._label or not self.selected_text:
            return None
        container = self.container_rect()
        width = typography.text_width(self._label, FLOATING_LABEL_STYLE)
        return self.visual_rect(
            QtCore.QRectF(
                container.left() + PADDING - 4,
                container.top() - 8,
                width + 8,
                16,
            )
        )

    def _paint_notched_label(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF, color: QtGui.QColor
    ) -> None:
        """outlined 样式的浮动标签：位于上边框的缺口内。"""
        del rect
        notch = self.notch_rect()
        if notch is None:
            return
        typography.paint_text(
            painter,
            notch,
            self._label,
            FLOATING_LABEL_STYLE,
            color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
