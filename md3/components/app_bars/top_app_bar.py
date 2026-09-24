"""顶部应用栏（Top app bar）：center-aligned / small / medium / large。

medium 与 large 变体是"两行"应用栏：标题位于展开区域的左下角，内容
滚动时展开区域先折叠到 64dp（标题交叉淡入到小标题位置），之后内容才
开始滚动；向上滚回顶部时再展开。调用 ``attach_scroll_area`` 即可把这
套嵌套滚动行为接到任意 ``QAbstractScrollArea`` 上，也可以直接用
``set_collapse_fraction`` 手动驱动。

右侧操作最多显示 3 个，其余进入溢出菜单：点击 ``more_vert`` 自动弹出
``Menu``，选中后以操作的绝对下标发出 ``action_triggered``。
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import icon_button
from md3.components.menus import menu as menu_module
from md3.core import animation
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import motion
from md3.tokens import typography as typography_tokens

SMALL_HEIGHT = 64.0
MEDIUM_HEIGHT = 112.0
LARGE_HEIGHT = 152.0
HORIZONTAL_PADDING = 4.0
TITLE_PADDING = 16.0
ICON_BUTTON_SIZE = 48.0
MAX_ACTIONS = 3
# 两行应用栏展开标题距容器底部的间距（dp）。
MEDIUM_TITLE_BOTTOM = 24.0
LARGE_TITLE_BOTTOM = 28.0


class TopAppBarVariant(enum.Enum):
    """顶部应用栏变体，值为 (名称, 高度, 标题排版角色)。

    名称用于区分高度与排版相同的 center-aligned 与 small，避免枚举别名。
    """

    CENTER_ALIGNED = (
        "center_aligned",
        SMALL_HEIGHT,
        typography_tokens.TypeRole.TITLE_LARGE,
    )
    SMALL = ("small", SMALL_HEIGHT, typography_tokens.TypeRole.TITLE_LARGE)
    MEDIUM = (
        "medium",
        MEDIUM_HEIGHT,
        typography_tokens.TypeRole.HEADLINE_SMALL,
    )
    LARGE = ("large", LARGE_HEIGHT, typography_tokens.TypeRole.HEADLINE_MEDIUM)

    @property
    def height(self) -> float:
        """展开时的容器高度（dp）。"""
        return self.value[1]

    @property
    def title_style(self) -> typography_tokens.TypeRole:
        """展开时的标题排版角色。"""
        return self.value[2]

    @property
    def collapsible(self) -> bool:
        """是否为可折叠的两行应用栏。"""
        return self.height > SMALL_HEIGHT


@dataclasses.dataclass
class AppBarAction:
    """应用栏操作。

    Attributes:
        icon: 图标。
        text: 文字，用作按钮提示与溢出菜单项的标签。
        enabled: 是否可用。
        key: 业务侧标识。
    """

    icon: icons.IconLike
    text: str = ""
    enabled: bool = True
    key: Any = None


ActionLike = AppBarAction | icons.IconLike


def coerce_action(action: ActionLike) -> AppBarAction:
    """把图标或 ``AppBarAction`` 统一为 ``AppBarAction``。"""
    if isinstance(action, AppBarAction):
        return action
    text = action if isinstance(action, str) else ""
    return AppBarAction(icon=action, text=text)


class TopAppBar(widget.MaterialWidget):
    """顶部应用栏。

    Args:
        title: 标题。
        variant: 变体。
        navigation_icon: 左侧导航图标（``menu`` / ``arrow_back`` 等），
            None 不显示。
        actions: 右侧操作列表（图标或 ``AppBarAction``；最多显示 3 个，
            多余的放入溢出菜单）。
        parent: 父控件。
    """

    navigation_clicked = QtCore.Signal()
    action_triggered = QtCore.Signal(int)
    overflow_clicked = QtCore.Signal()
    collapse_changed = QtCore.Signal(float)

    def __init__(
        self,
        title: str = "",
        variant: TopAppBarVariant = TopAppBarVariant.SMALL,
        navigation_icon: icons.IconLike = "menu",
        actions: list[ActionLike] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._variant = variant
        self._scrolled = animation.AnimatedFloat(self, 0.0, self.update)
        self._collapse = animation.AnimatedFloat(
            self, 0.0, self._on_collapse_changed
        )
        self._scroll_area: QtWidgets.QAbstractScrollArea | None = None
        self._scroll_bar: QtWidgets.QScrollBar | None = None
        self._handling_wheel = False
        self._auto_overflow_menu = True
        self._overflow_menu: menu_module.Menu | None = None
        self._navigation_button: icon_button.IconButton | None = None
        if navigation_icon is not None:
            self._navigation_button = icon_button.IconButton(
                navigation_icon, parent=self
            )
            self._navigation_button.clicked.connect(self.navigation_clicked)
        self._actions: list[AppBarAction] = []
        self._action_buttons: list[icon_button.IconButton] = []
        self._overflow_button: icon_button.IconButton | None = None
        self.set_actions(actions or [])
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.ToolBar

    @override
    def accessible_name(self) -> str:
        return self._title

    # ---- 属性 -------------------------------------------------------------

    @property
    def title(self) -> str:
        """标题。"""
        return self._title

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self._title = title
        self.update()

    @property
    def variant(self) -> TopAppBarVariant:
        """变体。"""
        return self._variant

    def set_variant(self, variant: TopAppBarVariant) -> None:
        """切换变体。"""
        self._variant = variant
        if not variant.collapsible:
            self._collapse.set(0.0)
        self.updateGeometry()
        self._layout_children()
        self.update()

    @property
    def action_items(self) -> list[AppBarAction]:
        """全部操作（含溢出菜单中的）。"""
        return list(self._actions)

    def set_actions(self, actions: list[ActionLike]) -> None:
        """设置右侧操作；超过 3 个的部分进入溢出菜单。"""
        for button in self._action_buttons:
            button.setParent(None)
            button.deleteLater()
        if self._overflow_button is not None:
            self._overflow_button.setParent(None)
            self._overflow_button.deleteLater()
            self._overflow_button = None
        if self._overflow_menu is not None:
            self._overflow_menu.deleteLater()
            self._overflow_menu = None
        self._actions = [coerce_action(action) for action in actions]
        self._action_buttons = []
        for action in self._actions[:MAX_ACTIONS]:
            button = icon_button.IconButton(
                action.icon, tooltip=action.text, parent=self
            )
            button.setEnabled(action.enabled)
            button.clicked.connect(self._on_action_clicked)
            self._action_buttons.append(button)
        if len(self._actions) > MAX_ACTIONS:
            self._overflow_button = icon_button.IconButton(
                "more_vert", tooltip=i18n.tr("more"), parent=self
            )
            self._overflow_button.clicked.connect(self._on_overflow_clicked)
        self._layout_children()
        self.update()

    @property
    def action_buttons(self) -> list[icon_button.IconButton]:
        """右侧可见的操作按钮。"""
        return list(self._action_buttons)

    @property
    def overflow_button(self) -> icon_button.IconButton | None:
        """溢出按钮（操作不超过 3 个时为 None）。"""
        return self._overflow_button

    @property
    def overflow_actions(self) -> list[AppBarAction]:
        """进入溢出菜单的操作。"""
        return list(self._actions[MAX_ACTIONS:])

    @property
    def auto_overflow_menu(self) -> bool:
        """点击溢出按钮时是否自动弹出菜单。"""
        return self._auto_overflow_menu

    def set_auto_overflow_menu(self, enabled: bool) -> None:
        """关闭后点击溢出按钮只发出 ``overflow_clicked``，由调用方处理。"""
        self._auto_overflow_menu = enabled

    @property
    def navigation_button(self) -> icon_button.IconButton | None:
        """左侧导航按钮。"""
        return self._navigation_button

    def set_scrolled(self, scrolled: bool) -> None:
        """内容滚动时调用，容器色切换为 ``surface_container``。"""
        self._scrolled.animate_to(
            1.0 if scrolled else 0.0, motion.SHORT4, motion.STANDARD
        )

    def _on_action_clicked(self) -> None:
        sender = self.sender()
        for index, button in enumerate(self._action_buttons):
            if button is sender:
                self.action_triggered.emit(index)
                return

    def _on_overflow_clicked(self) -> None:
        self.overflow_clicked.emit()
        if not self._auto_overflow_menu or self._overflow_button is None:
            return
        if self._overflow_menu is None:
            self._overflow_menu = menu_module.Menu(parent=self)
            self._overflow_menu.triggered.connect(self._on_overflow_triggered)
        self._overflow_menu.set_items(
            [
                menu_module.MenuItem(
                    text=action.text or str(action.icon),
                    icon=action.icon,
                    enabled=action.enabled,
                    key=index,
                )
                for index, action in enumerate(self._actions)
                if index >= MAX_ACTIONS
            ]
        )
        anchor = self._overflow_button
        # 菜单右缘与按钮右缘对齐，越界时由 Menu 自行翻转。
        global_pos = anchor.mapToGlobal(
            QtCore.QPoint(anchor.width(), anchor.height())
        )
        menu = self._overflow_menu
        menu.adjustSize()
        menu.popup(
            QtCore.QPoint(
                global_pos.x()
                - menu.sizeHint().width()
                + 2 * menu_module.SHADOW_MARGIN,
                global_pos.y(),
            )
        )

    def _on_overflow_triggered(self, item: menu_module.MenuItem) -> None:
        self.action_triggered.emit(int(item.key))

    # ---- 折叠 -------------------------------------------------------------

    @property
    def collapse_fraction(self) -> float:
        """折叠进度：0 为完全展开，1 为折叠到 64dp。"""
        return self._collapse.value

    def collapsible_range(self) -> float:
        """可折叠的高度（dp），非两行变体为 0。"""
        return max(0.0, self._variant.height - SMALL_HEIGHT)

    def set_collapse_fraction(
        self, fraction: float, animate: bool = False
    ) -> None:
        """设置折叠进度（0–1）。

        Args:
            fraction: 目标进度，超出范围会被截断。
            animate: 为真时以 standard 缓动过渡，否则立即生效（用于
                跟随指针滚动）。
        """
        if not self._variant.collapsible:
            return
        fraction = max(0.0, min(1.0, fraction))
        if animate:
            self._collapse.animate_to(fraction, motion.SHORT4, motion.STANDARD)
        else:
            self._collapse.set(fraction)

    def current_height(self) -> float:
        """当前容器高度（随折叠进度变化）。"""
        return self._variant.height - self.collapsible_range() * (
            self._collapse.value
        )

    def _on_collapse_changed(self) -> None:
        self.updateGeometry()
        self._layout_children()
        self.update()
        self.collapse_changed.emit(self._collapse.value)

    def attach_scroll_area(
        self, area: QtWidgets.QAbstractScrollArea | None
    ) -> None:
        """把应用栏接到滚动区域：滚轮先折叠应用栏再滚动内容。

        两行变体在内容位于顶部时由滚轮驱动折叠 / 展开，进度 1:1 跟随
        指针；通过滚动条拖动等其他方式滚动时，离开顶部即折叠、回到顶部
        即展开（带动画）。所有变体在内容离开顶部时切换到滚动态容器色。
        传入 None 解除绑定。
        """
        if self._scroll_area is not None:
            self._scroll_area.viewport().removeEventFilter(self)
            if self._scroll_bar is not None:
                self._scroll_bar.valueChanged.disconnect(
                    self._on_scroll_value_changed
                )
        self._scroll_area = area
        self._scroll_bar = None
        if area is None:
            return
        self._scroll_bar = area.verticalScrollBar()
        self._scroll_bar.valueChanged.connect(self._on_scroll_value_changed)
        area.viewport().installEventFilter(self)
        self._on_scroll_value_changed(self._scroll_bar.value())

    def _on_scroll_value_changed(self, value: int) -> None:
        self.set_scrolled(value > 0 or self._collapse.value >= 0.999)
        if self._handling_wheel or not self._variant.collapsible:
            return
        # 非滚轮驱动的滚动：离开顶部即折叠，回到顶部即展开。
        self.set_collapse_fraction(1.0 if value > 0 else 0.0, animate=True)

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if (
            self._scroll_area is not None
            and watched is self._scroll_area.viewport()
            and event.type() == QtCore.QEvent.Type.Wheel
            and self._variant.collapsible
        ):
            if self._handle_wheel(event):
                return True
        return super().eventFilter(watched, event)

    def _wheel_pixels(self, event: QtGui.QWheelEvent) -> float:
        """滚轮事件对应的滚动像素，正值表示内容向上（向下滚动）。"""
        angle = event.angleDelta().y()
        if angle:
            bar = self._scroll_bar
            step = bar.singleStep() if bar is not None else 20
            lines = QtWidgets.QApplication.wheelScrollLines()
            return -angle / 120.0 * step * lines
        return -float(event.pixelDelta().y())

    def _handle_wheel(self, event: QtGui.QWheelEvent) -> bool:
        bar = self._scroll_bar
        if bar is None or self.collapsible_range() <= 0:
            return False
        pixels = self._wheel_pixels(event)
        if pixels == 0:
            return False
        offset = self._collapse.value * self.collapsible_range()
        self._handling_wheel = True
        try:
            if pixels > 0:
                # 向下滚动：先折叠应用栏，剩余的再滚动内容。
                consumed = min(self.collapsible_range() - offset, pixels)
                if consumed > 0:
                    self.set_collapse_fraction(
                        (offset + consumed) / self.collapsible_range()
                    )
                remaining = pixels - consumed
                if remaining > 0.5:
                    bar.setValue(bar.value() + round(remaining))
            else:
                # 向上滚动：先把内容滚回顶部，剩余的展开应用栏。
                upward = -pixels
                if bar.value() > 0:
                    consumed = min(float(bar.value()), upward)
                    bar.setValue(bar.value() - round(consumed))
                    upward -= consumed
                if upward > 0.5:
                    self.set_collapse_fraction(
                        (offset - upward) / self.collapsible_range()
                    )
            self.set_scrolled(bar.value() > 0 or self._collapse.value >= 0.999)
        finally:
            self._handling_wheel = False
        event.accept()
        return True

    # ---- 几何 -------------------------------------------------------------

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, round(self.current_height()))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(200, round(self.current_height()))

    def _place(self, button: QtWidgets.QWidget, x: float, y: float) -> None:
        """按布局方向放置一个 48dp 的按钮（x 为从左到右的逻辑坐标）。"""
        rect = QtCore.QRectF(x, y, ICON_BUTTON_SIZE, ICON_BUTTON_SIZE)
        button.setGeometry(self.visual_rect(rect).toRect())

    def _layout_children(self) -> None:
        y = (SMALL_HEIGHT - ICON_BUTTON_SIZE) / 2
        if self._navigation_button is not None:
            self._place(self._navigation_button, HORIZONTAL_PADDING, y)
        right = self.width() - HORIZONTAL_PADDING
        buttons = list(self._action_buttons)
        if self._overflow_button is not None:
            buttons.append(self._overflow_button)
        for button in reversed(buttons):
            right -= ICON_BUTTON_SIZE
            self._place(button, right, y)

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._layout_children()

    def _small_title_rect(self) -> QtCore.QRectF:
        """单行标题矩形：位于 64dp 顶行、导航图标与操作之间。"""
        rect = QtCore.QRectF(self.rect())
        left = rect.left() + TITLE_PADDING
        if self._navigation_button is not None:
            left = rect.left() + HORIZONTAL_PADDING + ICON_BUTTON_SIZE + 4
        actions = len(self._action_buttons) + (
            1 if self._overflow_button else 0
        )
        right = (
            rect.right() - HORIZONTAL_PADDING - actions * ICON_BUTTON_SIZE - 4
        )
        return self.visual_rect(
            QtCore.QRectF(
                left, rect.top(), max(0.0, right - left), SMALL_HEIGHT
            )
        )

    def _expanded_title_rect(self) -> QtCore.QRectF:
        """两行变体展开标题的矩形：贴容器起始侧下角，随折叠上移。"""
        rect = QtCore.QRectF(self.rect())
        style = self.theme.style(self._variant.title_style)
        bottom_gap = (
            MEDIUM_TITLE_BOTTOM
            if self._variant is TopAppBarVariant.MEDIUM
            else LARGE_TITLE_BOTTOM
        )
        return QtCore.QRectF(
            rect.left() + TITLE_PADDING,
            rect.bottom() - bottom_gap - style.line_height,
            rect.width() - 2 * TITLE_PADDING,
            style.line_height,
        )

    def _title_rect(self) -> QtCore.QRectF:
        if self._variant.collapsible:
            return self._expanded_title_rect()
        return self._small_title_rect()

    # ---- 绘制 -------------------------------------------------------------

    def _container_color(self) -> QtGui.QColor:
        base = self.color("surface")
        scrolled = self.color("surface_container")
        t = max(self._scrolled.value, self._collapse.value)
        return QtGui.QColor.fromRgbF(
            base.redF() + (scrolled.redF() - base.redF()) * t,
            base.greenF() + (scrolled.greenF() - base.greenF()) * t,
            base.blueF() + (scrolled.blueF() - base.blueF()) * t,
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        painter.fillRect(rect, self._container_color())
        color = self.color("on_surface")
        if not self._variant.collapsible:
            alignment = (
                QtCore.Qt.AlignmentFlag.AlignCenter
                if self._variant is TopAppBarVariant.CENTER_ALIGNED
                else self.start_alignment()
            )
            typography.paint_text(
                painter,
                self._small_title_rect(),
                self._title,
                self._variant.title_style,
                color,
                alignment,
            )
            return
        # 两行变体：展开标题随折叠淡出并被顶行裁掉，小标题同步淡入。
        fraction = self._collapse.value
        left_aligned = self.start_alignment()
        if fraction < 0.999:
            painter.save()
            painter.setOpacity(1.0 - fraction)
            painter.setClipRect(
                QtCore.QRectF(
                    rect.left(),
                    rect.top() + SMALL_HEIGHT,
                    rect.width(),
                    max(0.0, rect.height() - SMALL_HEIGHT),
                )
            )
            typography.paint_text(
                painter,
                self._expanded_title_rect(),
                self._title,
                self._variant.title_style,
                color,
                left_aligned,
            )
            painter.restore()
        if fraction > 0.001:
            painter.save()
            painter.setOpacity(fraction)
            typography.paint_text(
                painter,
                self._small_title_rect(),
                self._title,
                typography_tokens.TypeRole.TITLE_LARGE,
                color,
                left_aligned,
            )
            painter.restore()
