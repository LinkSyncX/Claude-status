"""提示（Tooltips）。

``PlainTooltip`` 是悬停 500ms 后出现在锚点旁的小标签，指针离开锚点即淡出；
``RichTooltip`` 包含可选副标题、说明文字与操作按钮，指针移入提示本身时
保持显示，带操作的富提示会一直停留直到点击操作、点击别处或按下 Esc。
两者都是独立的顶层 ToolTip 窗口，可通过 ``Placement`` 指定出现方位，空间
不足时自动翻到对侧。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import common as buttons
from md3.core import animation
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

SHOW_DELAY_MS = 500
# 指针离开锚点后的宽限，用于判断是否移入了提示本身。
LEAVE_GRACE_MS = 120
ANCHOR_GAP = 4
PLAIN_PADDING_H = 8
PLAIN_PADDING_V = 4
PLAIN_MIN_HEIGHT = 24
PLAIN_MAX_WIDTH = 200
RICH_PADDING = 12
RICH_PADDING_H = 16
RICH_MAX_WIDTH = 320
RICH_MIN_WIDTH = 160
SHADOW_MARGIN = 12
SLIDE_DISTANCE = 4
PLAIN_STYLE = typography_tokens.TypeRole.BODY_SMALL
SUBHEAD_STYLE = typography_tokens.TypeRole.TITLE_SMALL
SUPPORTING_STYLE = typography_tokens.TypeRole.BODY_MEDIUM


class Placement(enum.Enum):
    """提示相对锚点的方位。"""

    TOP = "top"
    BOTTOM = "bottom"
    START = "start"
    END = "end"


_OPPOSITE = {
    Placement.TOP: Placement.BOTTOM,
    Placement.BOTTOM: Placement.TOP,
    Placement.START: Placement.END,
    Placement.END: Placement.START,
}


def position_for(
    anchor: QtCore.QRect,
    size: QtCore.QSize,
    placement: Placement,
    available: QtCore.QRect,
    margin: int = SHADOW_MARGIN,
    gap: int = ANCHOR_GAP,
) -> tuple[QtCore.QPoint, Placement]:
    """计算提示窗口左上角的位置，空间不足时翻到对侧。

    Args:
        anchor: 锚点矩形（全局坐标）。
        size: 提示窗口尺寸（含阴影边距）。
        placement: 期望方位。
        available: 可用屏幕区域。
        margin: 窗口四周的阴影边距。
        gap: 提示容器与锚点之间的距离。

    Returns:
        (位置, 实际采用的方位)。
    """

    def compute(where: Placement) -> QtCore.QPoint:
        if where is Placement.TOP:
            return QtCore.QPoint(
                anchor.center().x() - size.width() // 2,
                anchor.top() - size.height() - gap + margin,
            )
        if where is Placement.BOTTOM:
            return QtCore.QPoint(
                anchor.center().x() - size.width() // 2,
                anchor.bottom() + 1 + gap - margin,
            )
        if where is Placement.START:
            return QtCore.QPoint(
                anchor.left() - size.width() - gap + margin,
                anchor.center().y() - size.height() // 2,
            )
        return QtCore.QPoint(
            anchor.right() + 1 + gap - margin,
            anchor.center().y() - size.height() // 2,
        )

    def fits(point: QtCore.QPoint) -> bool:
        rect = QtCore.QRect(point, size).adjusted(
            margin, margin, -margin, -margin
        )
        return available.contains(rect)

    point = compute(placement)
    used = placement
    if not fits(point):
        flipped = compute(_OPPOSITE[placement])
        if fits(flipped):
            point, used = flipped, _OPPOSITE[placement]
    x = max(
        available.left() - margin,
        min(point.x(), available.right() - size.width() + margin),
    )
    y = max(
        available.top() - margin,
        min(point.y(), available.bottom() - size.height() + margin),
    )
    return QtCore.QPoint(x, y), used


class _TooltipWindow(QtWidgets.QWidget):
    """无边框、透明背景的顶层提示窗口。

    传入 ``parent`` 时仍是独立窗口，但生命周期交给 Qt 随父控件销毁，
    避免由 Python 引用计数决定销毁时机的顶层窗口在析构链中被嵌套删除。
    """

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            parent,
            QtCore.Qt.WindowType.ToolTip
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self._fade = animation.AnimatedFloat(self, 0.0, self._apply_opacity)
        self._fade.finished.connect(self._after_fade)
        self._closing = False
        self._placement = Placement.TOP
        self._shown_placement = Placement.TOP
        self._anchor_rect = QtCore.QRect()
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    def _apply_opacity(self) -> None:
        self.setWindowOpacity(self._fade.value)

    def _after_fade(self) -> None:
        if self._closing and self._fade.value <= 0.01:
            self.hide()

    @property
    def placement(self) -> Placement:
        """期望的方位。"""
        return self._placement

    def set_placement(self, placement: Placement) -> None:
        """设置期望的方位。"""
        self._placement = placement

    @property
    def shown_placement(self) -> Placement:
        """最近一次显示实际采用的方位（可能因空间不足而翻转）。"""
        return self._shown_placement

    def show_at(
        self, anchor: QtCore.QRect, placement: Placement | None = None
    ) -> None:
        """在锚点（全局坐标）旁显示并淡入，空间不足时翻到对侧。"""
        if placement is not None:
            self._placement = placement
        self._anchor_rect = QtCore.QRect(anchor)
        self.adjustSize()
        size = self.size()
        screen = QtGui.QGuiApplication.screenAt(anchor.center())
        if screen is None:
            screen = QtGui.QGuiApplication.primaryScreen()
        available = screen.availableGeometry()
        target, used = position_for(anchor, size, self._placement, available)
        self._shown_placement = used
        self._closing = False
        if not self.isVisible():
            self._fade.set(0.0)
            # 从锚点方向滑出 4dp。
            offset = {
                Placement.TOP: QtCore.QPoint(0, SLIDE_DISTANCE),
                Placement.BOTTOM: QtCore.QPoint(0, -SLIDE_DISTANCE),
                Placement.START: QtCore.QPoint(SLIDE_DISTANCE, 0),
                Placement.END: QtCore.QPoint(-SLIDE_DISTANCE, 0),
            }[used]
            self.move(target + offset)
            self.show()
            animation.run_property_animation(
                self,
                b"pos",
                target,
                motion.SHORT4,
                motion.EMPHASIZED_DECELERATE,
            )
        else:
            self.move(target)
        self._fade.animate_to(1.0, motion.SHORT3, motion.STANDARD_DECELERATE)

    def fade_out(self) -> None:
        """淡出后隐藏。"""
        if not self.isVisible():
            return
        self._closing = True
        self._fade.animate_to(0.0, motion.SHORT3, motion.STANDARD_ACCELERATE)

    def contains_global(self, point: QtCore.QPoint) -> bool:
        """全局坐标点是否落在提示容器（不含阴影边距）内。"""
        rect = self.geometry().adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )
        return self.isVisible() and rect.contains(point)


class PlainTooltip(_TooltipWindow):
    """纯文字提示。

    Args:
        text: 提示文字。
        placement: 方位，默认在锚点上方。
        parent: 拥有提示窗口的控件（通常是锚点），None 时由 Python 持有。
    """

    def __init__(
        self,
        text: str,
        placement: Placement = Placement.TOP,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._placement = placement
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

    @property
    def text(self) -> str:
        """提示文字。"""
        return self._text

    def set_text(self, text: str) -> None:
        """设置提示文字。"""
        self._text = text
        self.adjustSize()
        self.update()

    @override
    def sizeHint(self) -> QtCore.QSize:
        size = typography.text_size(self._text, PLAIN_STYLE, PLAIN_MAX_WIDTH)
        width = size.width() + 2 * PLAIN_PADDING_H
        height = max(PLAIN_MIN_HEIGHT, size.height() + 2 * PLAIN_PADDING_V)
        return typography.size_hint(
            width + 2 * SHADOW_MARGIN, height + 2 * SHADOW_MARGIN
        )

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_EXTRA_SMALL),
            theme.color("inverse_surface"),
        )
        typography.paint_multiline(
            painter,
            rect.adjusted(
                PLAIN_PADDING_H,
                PLAIN_PADDING_V,
                -PLAIN_PADDING_H,
                -PLAIN_PADDING_V,
            ),
            self._text,
            PLAIN_STYLE,
            theme.color("inverse_on_surface"),
        )
        painter.end()


class RichTooltip(_TooltipWindow):
    """富提示：副标题、说明文字与可选操作。

    带操作的富提示是持久的：显示后保持，直到点击操作、点击提示外部或按下
    Esc。不带操作的富提示在指针离开锚点与提示后淡出。

    Args:
        text: 说明文字。
        subhead: 副标题。
        actions: 操作按钮文字列表；点击任一操作都会关闭提示并发出
            ``action_triggered(text)``。
        placement: 方位，默认在锚点上方。
        parent: 拥有提示窗口的控件（通常是锚点），None 时由 Python 持有。
    """

    action_triggered = QtCore.Signal(str)
    dismissed = QtCore.Signal()

    def __init__(
        self,
        text: str,
        subhead: str = "",
        actions: list[str] | None = None,
        placement: Placement = Placement.TOP,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._subhead = subhead
        self._placement = placement
        self._buttons: list[buttons.TextButton] = []
        self._hovered = False
        self._filtering = False
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(
            SHADOW_MARGIN + RICH_PADDING_H,
            SHADOW_MARGIN + RICH_PADDING,
            SHADOW_MARGIN + RICH_PADDING_H,
            SHADOW_MARGIN + RICH_PADDING,
        )
        layout.setSpacing(4)
        self._subhead_label: typography.Label | None = None
        if subhead:
            self._subhead_label = typography.Label(
                subhead, SUBHEAD_STYLE, "on_surface_variant"
            )
            layout.addWidget(self._subhead_label)
        self._body = typography.Label(
            text, SUPPORTING_STYLE, "on_surface_variant"
        )
        self._body.setWordWrap(True)
        self._body.setMaximumWidth(RICH_MAX_WIDTH - 2 * RICH_PADDING_H)
        layout.addWidget(self._body)
        if actions:
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(-8, 4, 0, 0)
            row.setSpacing(8)
            for action in actions:
                button = buttons.TextButton(action)
                button.clicked.connect(self._on_action)
                self._buttons.append(button)
                row.addWidget(button)
            row.addStretch()
            layout.addLayout(row)
        self.setMinimumWidth(RICH_MIN_WIDTH + 2 * SHADOW_MARGIN)
        self.setMaximumWidth(RICH_MAX_WIDTH + 2 * SHADOW_MARGIN)

    @property
    def text(self) -> str:
        """说明文字。"""
        return self._text

    def set_text(self, text: str) -> None:
        """设置说明文字。"""
        self._text = text
        self._body.setText(text)
        self.adjustSize()

    @property
    def persistent(self) -> bool:
        """是否带操作（带操作的提示保持显示直到用户交互）。"""
        return bool(self._buttons)

    @property
    def hovered(self) -> bool:
        """指针是否位于提示上。"""
        return self._hovered

    @property
    def action_buttons(self) -> list[buttons.TextButton]:
        """操作按钮。"""
        return list(self._buttons)

    def _on_action(self) -> None:
        sender = self.sender()
        for button in self._buttons:
            if button is sender:
                self.action_triggered.emit(button.text)
                break
        self.dismiss()

    def dismiss(self) -> None:
        """关闭提示并发出 ``dismissed``。"""
        if not self.isVisible():
            return
        self.hide()
        self.dismissed.emit()

    # ---- 持久提示的外部点击 / Esc ------------------------------------------

    def _set_filtering(self, enabled: bool) -> None:
        app = QtWidgets.QApplication.instance()
        if app is None or enabled == self._filtering:
            return
        self._filtering = enabled
        if enabled:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self.persistent:
            self._set_filtering(True)

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self._hovered = False
        self._set_filtering(False)

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        kind = event.type()
        if kind == QtCore.QEvent.Type.MouseButtonPress and isinstance(
            event, QtGui.QMouseEvent
        ):
            point = event.globalPosition().toPoint()
            # 点击锚点由安装器处理（切换显示），点击提示本身不关闭。
            if not self.contains_global(
                point
            ) and not self._anchor_rect.contains(point):
                self.dismiss()
        elif (
            kind == QtCore.QEvent.Type.KeyPress
            and isinstance(event, QtGui.QKeyEvent)
            and event.key() == QtCore.Qt.Key.Key_Escape
        ):
            self.dismiss()
            return True
        return super().eventFilter(watched, event)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._hovered = True

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._hovered = False
        if not self.persistent:
            self.fade_out()

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(
            SHADOW_MARGIN, SHADOW_MARGIN, -SHADOW_MARGIN, -SHADOW_MARGIN
        )
        shape = shape_tokens.SHAPE_MEDIUM
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            elevation.Level.LEVEL_2,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape),
            theme.color("surface_container"),
        )
        painter.end()


class _TooltipInstaller(QtCore.QObject):
    """监听锚点控件的悬停 / 焦点事件，按延迟显示或隐藏提示。"""

    def __init__(
        self, anchor: QtWidgets.QWidget, tooltip: _TooltipWindow
    ) -> None:
        super().__init__(anchor)
        self._anchor = anchor
        self._tooltip = tooltip
        self._show_timer = QtCore.QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(SHOW_DELAY_MS)
        self._show_timer.timeout.connect(self._show)
        self._leave_timer = QtCore.QTimer(self)
        self._leave_timer.setSingleShot(True)
        self._leave_timer.setInterval(LEAVE_GRACE_MS)
        self._leave_timer.timeout.connect(self._after_leave)
        anchor.installEventFilter(self)
        if tooltip.parent() is None:
            # 交给锚点持有：随锚点一起由 Qt 销毁。
            tooltip.setParent(anchor, tooltip.windowFlags())

    @property
    def tooltip(self) -> _TooltipWindow:
        """关联的提示窗口。"""
        return self._tooltip

    def anchor_rect(self) -> QtCore.QRect:
        """锚点的全局矩形。"""
        return QtCore.QRect(
            self._anchor.mapToGlobal(QtCore.QPoint(0, 0)), self._anchor.size()
        )

    def _show(self) -> None:
        if not self._anchor.isVisible():
            return
        self._leave_timer.stop()
        self._tooltip.show_at(self.anchor_rect())

    def _is_persistent(self) -> bool:
        return (
            isinstance(self._tooltip, RichTooltip) and self._tooltip.persistent
        )

    def _after_leave(self) -> None:
        """指针离开锚点一小段时间后：移入了提示则保留，否则淡出。"""
        if self._is_persistent():
            return
        if isinstance(self._tooltip, RichTooltip) and (
            self._tooltip.hovered
            or self._tooltip.contains_global(QtGui.QCursor.pos())
        ):
            return
        self._tooltip.fade_out()

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        kind = event.type()
        if kind in (QtCore.QEvent.Type.Enter, QtCore.QEvent.Type.FocusIn):
            self._leave_timer.stop()
            if self._tooltip.isVisible():
                # 正在淡出时重新淡入（指针从提示回到锚点）。
                self._tooltip.show_at(self.anchor_rect())
            else:
                self._show_timer.start()
        elif kind == QtCore.QEvent.Type.Leave:
            self._show_timer.stop()
            if self._tooltip.isVisible() and not self._is_persistent():
                self._leave_timer.start()
        elif kind in (
            QtCore.QEvent.Type.FocusOut,
            QtCore.QEvent.Type.MouseButtonPress,
            QtCore.QEvent.Type.Hide,
        ):
            self._show_timer.stop()
            self._leave_timer.stop()
            if kind == QtCore.QEvent.Type.Hide:
                self._tooltip.hide()
            elif kind == QtCore.QEvent.Type.MouseButtonPress and (
                self._is_persistent()
            ):
                # 点击锚点切换持久提示的显示。
                if self._tooltip.isVisible():
                    self._tooltip.hide()
                else:
                    self._show()
            elif not self._is_persistent():
                self._tooltip.fade_out()
        return super().eventFilter(watched, event)


def install_plain(
    anchor: QtWidgets.QWidget, text: str, placement: Placement = Placement.TOP
) -> PlainTooltip:
    """为控件安装纯文字提示并返回提示窗口。"""
    tooltip = PlainTooltip(text, placement, parent=anchor)
    _TooltipInstaller(anchor, tooltip)
    return tooltip


def install_rich(
    anchor: QtWidgets.QWidget,
    text: str,
    subhead: str = "",
    actions: list[str] | None = None,
    placement: Placement = Placement.TOP,
) -> RichTooltip:
    """为控件安装富提示并返回提示窗口。"""
    tooltip = RichTooltip(text, subhead, actions, placement, parent=anchor)
    _TooltipInstaller(anchor, tooltip)
    return tooltip
