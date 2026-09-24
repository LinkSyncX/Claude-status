"""切换按钮与按钮组（M3 Expressive）。

``ToggleButton`` 是可选中的通用按钮：未选中为胶囊形，选中后换用强调配色
并把圆角收成方角，形状变化用弹簧过渡。``ButtonGroup`` 把一排按钮组织在
一起：按下某个按钮时它横向扩张、相邻按钮相应收缩；``connected`` 模式下
按钮彼此相接，外侧圆角饱满、内侧 8dp，选中的切换按钮则变为完整胶囊。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.buttons import common
from md3.core import accessibility
from md3.core import animation
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens

DEFAULT_SPACING = 8.0
CONNECTED_SPACING = 2.0
INNER_CORNER = shape_tokens.SMALL
CHECKED_CORNER = shape_tokens.MEDIUM
DEFAULT_EXPAND_RATIO = 0.15


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def lerp_shape(
    start: shape_tokens.Shape,
    end: shape_tokens.Shape,
    progress: float,
    width: float,
    height: float,
) -> shape_tokens.Shape:
    """在两个形状之间按进度插值（``FULL`` 先换算为实际半径）。"""
    progress = max(0.0, min(1.0, progress))
    a = start.resolved(width, height)
    b = end.resolved(width, height)
    return shape_tokens.Shape(
        _lerp(a.top_left, b.top_left, progress),
        _lerp(a.top_right, b.top_right, progress),
        _lerp(a.bottom_right, b.bottom_right, progress),
        _lerp(a.bottom_left, b.bottom_left, progress),
    )


class ToggleButton(common.Button):
    """可切换的通用按钮。

    Args:
        text: 标签文字。
        icon: 前置图标。
        variant: 变体，决定未选中 / 选中两态的配色。
        checked: 初始选中状态。
        parent: 父控件。
    """

    toggled = QtCore.Signal(bool)

    def __init__(
        self,
        text: str = "",
        icon: icons.IconLike = None,
        variant: common.ButtonVariant = common.ButtonVariant.FILLED,
        checked: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._checked = checked
        super().__init__(text, icon, variant, parent=parent)
        # 0 未选中 → 1 选中，驱动形状与配色过渡。
        self._morph = animation.AnimatedFloat(
            self, 1.0 if checked else 0.0, self.update
        )
        self._morph.finished.connect(self.sync_shadow)

    @property
    def checked(self) -> bool:
        """是否选中。"""
        return self._checked

    def set_checked(self, checked: bool) -> None:
        """设置选中状态，变化时发出 ``toggled``。"""
        checked = bool(checked)
        if checked == self._checked:
            return
        self._checked = checked
        self._morph.spring_to(
            1.0 if checked else 0.0, motion.EXPRESSIVE_DEFAULT_SPATIAL
        )
        self.toggled.emit(checked)
        accessibility.notify_state_changed(self, checked=True)
        self._update_elevation()
        self.update()

    @property
    def morph_progress(self) -> float:
        """选中过渡进度 0–1。"""
        # 基类构造期间动画对象尚未创建，此时直接按初始状态返回。
        morph = getattr(self, "_morph", None)
        if morph is None:
            return 1.0 if self._checked else 0.0
        return morph.value

    @override
    def activate(self) -> None:
        self.set_checked(not self._checked)
        super().activate()

    @override
    def container_shape(self) -> shape_tokens.Shape:
        rect = self.container_rect()
        resting = (
            self._shape_override
            if self._shape_override is not None
            else shape_tokens.SHAPE_FULL
        )
        # 组内（有覆盖形状）选中后变为完整胶囊；独立时选中后收成方角。
        checked = (
            shape_tokens.SHAPE_FULL
            if self._shape_override is not None
            else shape_tokens.Shape.all(CHECKED_CORNER)
        )
        return lerp_shape(
            resting, checked, self.morph_progress, rect.width(), rect.height()
        )

    def _colors(self) -> tuple[QtGui.QColor | None, QtGui.QColor]:
        """按变体返回 (容器色, 内容色)，已按过渡进度混合。"""
        variant = self._variant
        match variant:
            case common.ButtonVariant.TONAL:
                off = (
                    self.color("secondary_container"),
                    self.color("on_secondary_container"),
                )
                on = (self.color("secondary"), self.color("on_secondary"))
            case common.ButtonVariant.OUTLINED:
                off = (None, self.color("on_surface_variant"))
                on = (
                    self.color("inverse_surface"),
                    self.color("inverse_on_surface"),
                )
            case common.ButtonVariant.ELEVATED:
                off = (
                    self.color("surface_container_low"),
                    self.color("primary"),
                )
                on = (self.color("primary"), self.color("on_primary"))
            case _:
                off = (
                    self.color("surface_container"),
                    self.color("on_surface_variant"),
                )
                on = (self.color("primary"), self.color("on_primary"))
        progress = self.morph_progress
        container = _blend(off[0], on[0], progress)
        content = _blend(off[1], on[1], progress)
        return container, content

    @override
    def _content_color(self) -> QtGui.QColor:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        return self._colors()[1]

    @override
    def _container_color(self) -> QtGui.QColor | None:
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("on_surface"),
                state_tokens.DISABLED_CONTAINER_OPACITY,
            )
        return self._colors()[0]

    @override
    def _outline_color(self) -> QtGui.QColor | None:
        if self._variant is not common.ButtonVariant.OUTLINED:
            return None
        if self.morph_progress > 0.5:
            return None
        return super()._outline_color()


def _blend(
    start: QtGui.QColor | None, end: QtGui.QColor | None, progress: float
) -> QtGui.QColor | None:
    if start is None and end is None:
        return None
    a = QtGui.QColor(start) if start is not None else QtGui.QColor(end)
    b = QtGui.QColor(end) if end is not None else QtGui.QColor(start)
    if start is None:
        a.setAlphaF(0.0)
    if end is None:
        b.setAlphaF(0.0)
    return QtGui.QColor.fromRgbF(
        _lerp(a.redF(), b.redF(), progress),
        _lerp(a.greenF(), b.greenF(), progress),
        _lerp(a.blueF(), b.blueF(), progress),
        _lerp(a.alphaF(), b.alphaF(), progress),
    )


class ButtonGroup(widget.MaterialWidget):
    """按钮组。

    Args:
        buttons: 成员按钮（``Button`` / ``ToggleButton`` / ``IconButton`` 等）。
        connected: 为真时按钮相接，使用外圆内方的连接形状。
        expand_ratio: 按下时该按钮的扩张比例，0 关闭扩张动效。
        single_selection: 为真时组内的 ``ToggleButton`` 互斥（单选）。
        spacing: 按钮间距（dp）；None 时普通组 8、连接组 2。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(list)

    def __init__(
        self,
        buttons: Sequence[QtWidgets.QWidget] = (),
        connected: bool = False,
        expand_ratio: float = DEFAULT_EXPAND_RATIO,
        single_selection: bool = False,
        spacing: float | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._buttons: list[QtWidgets.QWidget] = []
        self._expand: list[animation.AnimatedFloat] = []
        self._connected = connected
        self._expand_ratio = max(0.0, expand_ratio)
        self._single = single_selection
        self._spacing = spacing
        self._syncing = False
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        for button in buttons:
            self.add_button(button)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    # ---- 成员 -------------------------------------------------------------

    @property
    def buttons(self) -> list[QtWidgets.QWidget]:
        """成员按钮。"""
        return list(self._buttons)

    def add_button(self, button: QtWidgets.QWidget) -> None:
        """追加一个按钮。"""
        index = len(self._buttons)
        button.setParent(self)
        button.show()
        self._buttons.append(button)
        progress = animation.AnimatedFloat(self, 0.0, self._relayout)
        self._expand.append(progress)
        pressed = getattr(button, "pressed", None)
        released = getattr(button, "released", None)
        if pressed is not None and released is not None:
            pressed.connect(lambda i=index: self._set_expanded(i, True))
            released.connect(lambda i=index: self._set_expanded(i, False))
        toggled = getattr(button, "toggled", None)
        if toggled is not None and isinstance(button, ToggleButton):
            toggled.connect(
                lambda checked, i=index: self._on_toggled(i, checked)
            )
        self._apply_shapes()
        self.updateGeometry()
        self._relayout()

    @property
    def connected(self) -> bool:
        """是否为连接组。"""
        return self._connected

    def set_connected(self, connected: bool) -> None:
        """切换连接模式。"""
        self._connected = connected
        self._apply_shapes()
        self.updateGeometry()
        self._relayout()

    @property
    def spacing(self) -> float:
        """实际使用的按钮间距。"""
        if self._spacing is not None:
            return self._spacing
        return CONNECTED_SPACING if self._connected else DEFAULT_SPACING

    @property
    def checked_indices(self) -> list[int]:
        """已选中的切换按钮下标。"""
        return [
            i
            for i, button in enumerate(self._buttons)
            if isinstance(button, ToggleButton) and button.checked
        ]

    def set_checked(self, index: int, checked: bool = True) -> None:
        """设置第 index 个切换按钮的选中状态。"""
        button = self._buttons[index]
        if isinstance(button, ToggleButton):
            button.set_checked(checked)

    # ---- 形状 -------------------------------------------------------------

    def connected_shape(self, index: int) -> shape_tokens.Shape:
        """连接模式下第 index 个按钮的形状。"""
        count = len(self._buttons)
        if count <= 1:
            return shape_tokens.SHAPE_FULL
        if index == 0:
            return shape_tokens.Shape(
                shape_tokens.FULL, INNER_CORNER, INNER_CORNER, shape_tokens.FULL
            )
        if index == count - 1:
            return shape_tokens.Shape(
                INNER_CORNER, shape_tokens.FULL, shape_tokens.FULL, INNER_CORNER
            )
        return shape_tokens.Shape.all(INNER_CORNER)

    def _apply_shapes(self) -> None:
        for index, button in enumerate(self._buttons):
            set_shape = getattr(button, "set_shape", None)
            set_margin = getattr(button, "set_outer_margin", None)
            if self._connected:
                if set_shape is not None:
                    set_shape(self.connected_shape(index))
                if set_margin is not None:
                    set_margin(0.0)
            else:
                if set_shape is not None:
                    set_shape(None)
                if set_margin is not None:
                    set_margin(widget.DEFAULT_OUTER_MARGIN)

    # ---- 选择 -------------------------------------------------------------

    def _on_toggled(self, index: int, checked: bool) -> None:
        if self._syncing:
            return
        if self._single and checked:
            self._syncing = True
            try:
                for other, button in enumerate(self._buttons):
                    if other != index and isinstance(button, ToggleButton):
                        button.set_checked(False)
            finally:
                self._syncing = False
        self.selection_changed.emit(self.checked_indices)

    # ---- 布局 -------------------------------------------------------------

    def _set_expanded(self, index: int, expanded: bool) -> None:
        if self._expand_ratio <= 0 or index >= len(self._expand):
            return
        if expanded:
            self._expand[index].spring_to(1.0, motion.EXPRESSIVE_FAST_SPATIAL)
        else:
            self._expand[index].spring_to(
                0.0, motion.EXPRESSIVE_DEFAULT_SPATIAL
            )

    def expansion(self, index: int) -> float:
        """第 index 个按钮当前的扩张进度 0–1。"""
        return self._expand[index].value

    def _base_widths(self) -> list[float]:
        return [float(button.sizeHint().width()) for button in self._buttons]

    def widths(self) -> list[float]:
        """应用扩张动效后的各按钮宽度（总宽不变）。"""
        base = self._base_widths()
        if not base:
            return []
        extra = [
            width * self._expand_ratio * self._expand[i].value
            for i, width in enumerate(base)
        ]
        total_extra = sum(extra)
        if total_extra <= 0:
            return base
        # 扩张的宽度由其余按钮按各自宽度比例吸收。
        others = [width for i, width in enumerate(base) if extra[i] <= 0]
        pool = sum(others) or 1.0
        result = []
        for i, width in enumerate(base):
            if extra[i] > 0:
                result.append(width + extra[i])
            else:
                result.append(max(0.0, width - total_extra * width / pool))
        return result

    def _relayout(self) -> None:
        widths = self.widths()
        x = 0.0
        height = self.height()
        for button, width in zip(self._buttons, widths, strict=True):
            hint = button.sizeHint().height()
            y = (height - hint) / 2
            button.setGeometry(round(x), round(y), round(width), hint)
            x += width + self.spacing
        self.update()

    @override
    def sizeHint(self) -> QtCore.QSize:
        widths = self._base_widths()
        if not widths:
            return QtCore.QSize(0, 40)
        width = sum(widths) + self.spacing * (len(widths) - 1)
        height = max(button.sizeHint().height() for button in self._buttons)
        return QtCore.QSize(round(width), height)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()
