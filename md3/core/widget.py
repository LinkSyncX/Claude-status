"""组件基类。

``MaterialWidget`` 负责订阅主题与抗锯齿绘制；``InteractiveWidget`` 在其
基础上提供状态层、涟漪、键盘焦点环与统一的按压/点击事件处理。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import accessibility
from md3.core import animation
from md3.core import elevation as elevation_module
from md3.core import focus_ring
from md3.core import ripple as ripple_module
from md3.core import shape as shape_utils
from md3.core import state_layer as state_layer_module
from md3.theme import theme as theme_module
from md3.tokens import elevation as elevation_tokens
from md3.tokens import motion
from md3.tokens import shape as shape_tokens

# 交互组件默认在视觉容器外保留的边距（dp）：40dp 的按钮由此获得 48dp 触控目标。
DEFAULT_OUTER_MARGIN = 4.0

_KEYBOARD_FOCUS_REASONS = frozenset(
    {
        QtCore.Qt.FocusReason.TabFocusReason,
        QtCore.Qt.FocusReason.BacktabFocusReason,
        QtCore.Qt.FocusReason.ShortcutFocusReason,
    }
)
_ACTIVATION_KEYS = frozenset(
    {
        QtCore.Qt.Key.Key_Space,
        QtCore.Qt.Key.Key_Return,
        QtCore.Qt.Key.Key_Enter,
        QtCore.Qt.Key.Key_Select,
    }
)


class MaterialWidget(QtWidgets.QWidget):
    """所有 M3 组件的基类。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        accessibility.install()
        self._shadow: elevation_module.ShadowWidget | None = None
        theme_module.manager().theme_changed.connect(self._handle_theme_changed)

    @property
    def theme(self) -> theme_module.Theme:
        """当前主题。"""
        return theme_module.current()

    def color(self, role: str) -> QtGui.QColor:
        """当前主题中的色彩角色。"""
        return theme_module.current().color(role)

    # ---- 布局方向 ---------------------------------------------------------

    def is_rtl(self) -> bool:
        """当前布局方向是否为从右到左。"""
        return self.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft

    def visual_rect(
        self, rect: QtCore.QRectF, bounds: QtCore.QRectF | None = None
    ) -> QtCore.QRectF:
        """把按从左到右计算的矩形映射到当前布局方向。

        LTR 下原样返回；RTL 下在 ``bounds``（默认整个控件）内左右镜像，
        组件据此把"前置"元素画到右侧、"后置"元素画到左侧。
        """
        if not self.is_rtl():
            return rect
        if bounds is None:
            bounds = QtCore.QRectF(self.rect())
        return QtCore.QRectF(
            bounds.left() + bounds.right() - rect.right(),
            rect.top(),
            rect.width(),
            rect.height(),
        )

    def visual_x(self, x: float, bounds: QtCore.QRectF | None = None) -> float:
        """把从左到右的水平坐标映射到当前布局方向。"""
        if not self.is_rtl():
            return x
        if bounds is None:
            bounds = QtCore.QRectF(self.rect())
        return bounds.left() + bounds.right() - x

    def logical_point(self, point: QtCore.QPointF) -> QtCore.QPointF:
        """把事件坐标换算回从左到右的逻辑坐标（用于命中测试）。"""
        if not self.is_rtl():
            return point
        return QtCore.QPointF(self.visual_x(point.x()), point.y())

    def visual_alignment(
        self, alignment: QtCore.Qt.AlignmentFlag
    ) -> QtCore.Qt.AlignmentFlag:
        """RTL 下交换 ``AlignLeft`` 与 ``AlignRight``。"""
        if not self.is_rtl():
            return alignment
        left = QtCore.Qt.AlignmentFlag.AlignLeft
        right = QtCore.Qt.AlignmentFlag.AlignRight
        if alignment & left:
            return (alignment & ~left) | right
        if alignment & right:
            return (alignment & ~right) | left
        return alignment

    def start_alignment(self) -> QtCore.Qt.AlignmentFlag:
        """靠布局起始边并垂直居中的对齐。"""
        return self.visual_alignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )

    # ---- 无障碍 -----------------------------------------------------------

    def accessible_role(self) -> QtGui.QAccessible.Role:
        """无障碍角色，容器类子类通常返回 ``Grouping``。"""
        return QtGui.QAccessible.Role.Client

    def accessible_name(self) -> str:
        """无障碍名称；未设置 ``accessibleName`` 时的回退值。"""
        return self.toolTip()

    def accessible_description(self) -> str:
        """无障碍描述。"""
        return ""

    def accessible_value(self) -> str:
        """无障碍取值（滑块、进度等）。"""
        return ""

    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        """补充无障碍状态位；基类不做处理。"""
        del state

    # ---- 海拔 -------------------------------------------------------------

    def elevation_rect(self) -> QtCore.QRectF:
        """投影容器矩形（组件坐标），默认为整个组件。"""
        return QtCore.QRectF(self.rect())

    def elevation_shape(self) -> shape_tokens.Shape:
        """投影容器形状。"""
        return shape_tokens.SHAPE_NONE

    def elevation(self) -> elevation_tokens.Level:
        """当前海拔等级。"""
        if self._shadow is None:
            return elevation_tokens.Level.LEVEL_0
        return self._shadow.level

    def set_elevation(self, level: elevation_tokens.Level | int) -> None:
        """设置海拔等级；非 0 时在控件下方创建阴影控件。"""
        level = elevation_tokens.Level(level)
        if self._shadow is None:
            if level == elevation_tokens.Level.LEVEL_0:
                return
            self._shadow = elevation_module.ShadowWidget(
                self,
                level,
                shape_provider=self.elevation_shape,
                color_provider=lambda: self.color("shadow"),
                rect_provider=self.elevation_rect,
            )
        else:
            self._shadow.set_level(level)

    def sync_shadow(self) -> None:
        """容器矩形或形状变化后重新同步阴影位置。"""
        if self._shadow is not None:
            self._shadow.sync()

    def on_theme_changed(self, theme: theme_module.Theme) -> None:
        """主题变更钩子，子类可覆写以刷新缓存的字体或尺寸。"""
        del theme  # 默认实现无需使用。

    def paint(self, painter: QtGui.QPainter) -> None:
        """子类在此完成绘制；画笔已开启抗锯齿。"""
        del painter

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        self.paint(painter)
        painter.end()

    def _handle_theme_changed(self, theme: theme_module.Theme) -> None:
        self.on_theme_changed(theme)
        self.updateGeometry()
        self.update()
        if self._shadow is not None:
            self._shadow.update()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.LayoutDirectionChange:
            self.updateGeometry()
            self.update()


class InteractiveWidget(MaterialWidget):
    """可交互组件基类：状态层、涟漪、焦点环与点击事件。

    子类通过覆写 ``container_rect`` / ``container_shape`` /
    ``state_layer_color`` 描述容器，通过 ``paint_container`` 与
    ``paint_content`` 绘制，通过 ``activate`` 响应点击。
    """

    pressed = QtCore.Signal()
    released = QtCore.Signal()
    clicked = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self._state_layer = state_layer_module.StateLayer(
            self, on_change=self.update
        )
        self._ripple = ripple_module.RippleController(
            self, on_change=self.update
        )
        self._focus_visible = False
        self._pressed_inside = False
        self._outer_margin = DEFAULT_OUTER_MARGIN
        self._focus_anim = animation.AnimatedFloat(self, 1.0, self.update)

    # ---- 子类接口 -------------------------------------------------------

    @property
    def state_layer(self) -> state_layer_module.StateLayer:
        """状态层控制器。"""
        return self._state_layer

    @property
    def ripple(self) -> ripple_module.RippleController:
        """涟漪控制器。"""
        return self._ripple

    @property
    def outer_margin(self) -> float:
        """视觉容器与控件边界之间的边距，用于触控目标与焦点环。"""
        return self._outer_margin

    def set_outer_margin(self, margin: float) -> None:
        """设置外边距并刷新布局。"""
        self._outer_margin = max(0.0, margin)
        self.updateGeometry()
        self.update()

    def container_rect(self) -> QtCore.QRectF:
        """容器矩形，默认为控件矩形向内收缩外边距。"""
        margin = self._outer_margin
        return QtCore.QRectF(self.rect()).adjusted(
            margin, margin, -margin, -margin
        )

    def container_shape(self) -> shape_tokens.Shape:
        """容器形状，默认无圆角。"""
        return shape_tokens.SHAPE_NONE

    @override
    def elevation_rect(self) -> QtCore.QRectF:
        return self.container_rect()

    @override
    def elevation_shape(self) -> shape_tokens.Shape:
        return self.container_shape()

    def container_path(self) -> QtGui.QPainterPath:
        """容器路径，用于状态层与涟漪裁剪。"""
        return shape_utils.rounded_rect_path(
            self.container_rect(), self.container_shape()
        )

    def state_layer_color(self) -> QtGui.QColor:
        """状态层与涟漪颜色，默认为 ``on_surface``。"""
        return self.color("on_surface")

    def focus_ring_color(self) -> QtGui.QColor:
        """焦点环颜色，规范为 ``secondary``。"""
        return self.color("secondary")

    def focus_ring_extent(self) -> float:
        """容器外可供焦点环使用的空间，默认等于外边距。"""
        return self._outer_margin

    def is_interactive(self) -> bool:
        """当前是否响应交互。"""
        return self.isEnabled()

    def activate(self) -> None:
        """由点击或键盘触发的默认动作，默认发出 ``clicked``。"""
        self.clicked.emit()

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Button

    @override
    def accessible_name(self) -> str:
        text = getattr(self, "text", None)
        if isinstance(text, str) and text:
            return text
        return self.toolTip()

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        state.pressed = self._pressed_inside
        state.hotTracked = self._state_layer.has(
            state_layer_module.InteractionState.HOVERED
        )
        checked = getattr(self, "checked", None)
        if isinstance(checked, bool):
            state.checkable = True
            state.checked = checked

    def paint_container(self, painter: QtGui.QPainter) -> None:
        """绘制容器（背景、描边、阴影）。"""
        del painter

    def paint_content(self, painter: QtGui.QPainter) -> None:
        """绘制内容（图标、文字）。"""
        del painter

    def paint_overlays(self, painter: QtGui.QPainter) -> None:
        """绘制状态层、涟漪与焦点环。"""
        path = self.container_path()
        color = self.state_layer_color()
        self._state_layer.paint(painter, path, color)
        self._ripple.paint(painter, path, color)
        if self._focus_visible:
            focus_ring.paint_focus_ring(
                painter,
                self.container_rect(),
                self.container_shape(),
                self.focus_ring_color(),
                max_extent=self.focus_ring_extent(),
                progress=self._focus_anim.value,
            )

    def _start_focus_animation(self) -> None:
        self._focus_anim.set(0.0)
        self._focus_anim.animate_to(
            1.0, focus_ring.ANIMATION_DURATION_MS, motion.STANDARD
        )

    @property
    def focus_visible(self) -> bool:
        """是否应显示键盘焦点环（仅键盘获得焦点时为真）。"""
        return self._focus_visible

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        self.paint_container(painter)
        self.paint_content(painter)
        self.paint_overlays(painter)

    # ---- 事件 -------------------------------------------------------------

    def start_press(self, position: QtCore.QPointF | None) -> None:
        """开始一次按压（供子类在自定义命中测试后调用）。"""
        self._pressed_inside = True
        self._state_layer.set_pressed(True)
        self._ripple.press(position, self.container_rect())
        self.pressed.emit()

    def end_press(self, activate: bool) -> None:
        """结束按压，可选触发 ``activate``。"""
        was_pressed = self._pressed_inside
        self._pressed_inside = False
        self._state_layer.set_pressed(False)
        self._ripple.release()
        if was_pressed:
            self.released.emit()
            if activate and self.is_interactive():
                self.activate()

    def cancel_press(self) -> None:
        """放弃进行中的按压（手势转为滑动 / 拖拽时调用），不触发点击。"""
        if not self._pressed_inside:
            return
        self._pressed_inside = False
        self._state_layer.set_pressed(False)
        self._ripple.cancel()

    @property
    def is_pressed(self) -> bool:
        """是否处于按压中。"""
        return self._pressed_inside

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        if self.is_interactive():
            self._state_layer.set_hovered(True)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._state_layer.set_hovered(False)
        if self._pressed_inside:
            self._pressed_inside = False
            self._state_layer.set_pressed(False)
            self._ripple.cancel()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self.is_interactive()
        ):
            self.start_press(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            inside = self.rect().contains(event.position().toPoint())
            self.end_press(activate=inside)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in _ACTIVATION_KEYS and self.is_interactive():
            if not event.isAutoRepeat() and not self._pressed_inside:
                self.start_press(None)
            event.accept()
            return
        super().keyPressEvent(event)

    @override
    def keyReleaseEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() in _ACTIVATION_KEYS and self._pressed_inside:
            if not event.isAutoRepeat():
                self.end_press(activate=True)
            event.accept()
            return
        super().keyReleaseEvent(event)

    @override
    def focusInEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusInEvent(event)
        self._focus_visible = event.reason() in _KEYBOARD_FOCUS_REASONS
        self._state_layer.set_focused(self._focus_visible)
        if self._focus_visible:
            self._start_focus_animation()
        self.update()

    @override
    def focusOutEvent(self, event: QtGui.QFocusEvent) -> None:
        super().focusOutEvent(event)
        self._focus_visible = False
        self._state_layer.set_focused(False)
        if self._pressed_inside:
            self._pressed_inside = False
            self._state_layer.set_pressed(False)
            self._ripple.cancel()
        self.update()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            enabled = self.isEnabled()
            self._state_layer.set_disabled(not enabled)
            if not enabled:
                self._state_layer.set_hovered(False)
                self._ripple.cancel()
            self.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
                if enabled
                else QtCore.Qt.CursorShape.ArrowCursor
            )
            self.update()
