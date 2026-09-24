"""悬浮操作按钮（FAB）与扩展 FAB。"""

from __future__ import annotations

import dataclasses
import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens


@dataclasses.dataclass(frozen=True)
class _FabMetrics:
    container: float
    icon: float
    shape: shape_tokens.Shape


class FabSize(enum.Enum):
    """FAB 尺寸：small 40dp、regular 56dp、large 96dp。"""

    SMALL = _FabMetrics(40.0, 24.0, shape_tokens.SHAPE_MEDIUM)
    REGULAR = _FabMetrics(56.0, 24.0, shape_tokens.SHAPE_LARGE)
    LARGE = _FabMetrics(96.0, 36.0, shape_tokens.SHAPE_EXTRA_LARGE)


class FabColor(enum.Enum):
    """FAB 配色：值为 (容器角色, 内容角色)。"""

    PRIMARY = ("primary_container", "on_primary_container")
    SURFACE = ("surface_container_high", "primary")
    SECONDARY = ("secondary_container", "on_secondary_container")
    TERTIARY = ("tertiary_container", "on_tertiary_container")


class FloatingActionButton(widget.InteractiveWidget):
    """悬浮操作按钮。

    Args:
        icon: 图标名或 ``Icon``。
        size: 尺寸。
        color: 配色。
        lowered: 为真时使用较低的海拔（level 1），用于已有较多阴影的界面。
        tooltip: 提示文字。
        parent: 父控件。
    """

    def __init__(
        self,
        icon: icons.IconLike = "add",
        size: FabSize = FabSize.REGULAR,
        color: FabColor = FabColor.PRIMARY,
        lowered: bool = False,
        tooltip: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._fab_color = color
        self._lowered = lowered
        self._icon = icons.coerce(icon, size.value.icon)
        if tooltip:
            self.setToolTip(tooltip)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._update_elevation()

    @property
    def icon(self) -> icons.AnyIcon | None:
        """图标。"""
        return self._icon

    def set_icon(self, icon: icons.IconLike) -> None:
        """设置图标。"""
        self._icon = icons.coerce(icon, self._size.value.icon)
        self.update()

    @property
    def fab_size(self) -> FabSize:
        """尺寸。"""
        return self._size

    @property
    def fab_color(self) -> FabColor:
        """配色。"""
        return self._fab_color

    def set_fab_color(self, color: FabColor) -> None:
        """设置配色。"""
        self._fab_color = color
        self.update()

    @property
    def lowered(self) -> bool:
        """是否使用较低海拔。"""
        return self._lowered

    def set_lowered(self, lowered: bool) -> None:
        """设置是否使用较低海拔。"""
        self._lowered = lowered
        self._update_elevation()

    @override
    def sizeHint(self) -> QtCore.QSize:
        side = round(self._size.value.container + 2 * self.outer_margin)
        return QtCore.QSize(side, side)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return self._size.value.shape

    def _container_color(self) -> QtGui.QColor:
        return self.color(self._fab_color.value[0])

    def _content_color(self) -> QtGui.QColor:
        return self.color(self._fab_color.value[1])

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self._content_color()

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        shape_utils.fill_shape(
            painter, self.container_path(), self._container_color()
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        if self._icon is None:
            return
        rect = self.container_rect()
        size = self._size.value.icon
        icon_rect = QtCore.QRectF(
            rect.center().x() - size / 2,
            rect.center().y() - size / 2,
            size,
            size,
        )
        self._icon.paint(painter, icon_rect, self._content_color())

    def _update_elevation(self) -> None:
        hovered = self.state_layer.has(state_tokens.InteractionState.HOVERED)
        pressed = self.state_layer.has(state_tokens.InteractionState.PRESSED)
        if self._lowered:
            resting = elevation.Level.LEVEL_1
            raised = elevation.Level.LEVEL_2
        else:
            resting = elevation.Level.LEVEL_3
            raised = elevation.Level.LEVEL_4
        self.set_elevation(raised if hovered and not pressed else resting)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._update_elevation()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._update_elevation()

    @override
    def start_press(self, position: QtCore.QPointF | None) -> None:
        super().start_press(position)
        self._update_elevation()

    @override
    def end_press(self, activate: bool) -> None:
        super().end_press(activate)
        self._update_elevation()


class ExtendedFab(FloatingActionButton):
    """带文字标签的扩展 FAB（高 56dp）。

    Args:
        text: 标签文字。
        icon: 可选图标。
        color: 配色。
        lowered: 是否使用较低海拔。
        parent: 父控件。
    """

    CONTAINER_HEIGHT = 56.0
    PADDING = 16.0
    ICON_GAP = 12.0
    ICON_SIZE = 24.0
    MIN_WIDTH = 80.0
    LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        color: FabColor = FabColor.PRIMARY,
        lowered: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._text = text
        super().__init__(icon, FabSize.REGULAR, color, lowered, parent=parent)
        self._icon = icons.coerce(icon, self.ICON_SIZE)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Minimum,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def text(self) -> str:
        """标签文字。"""
        return self._text

    def set_text(self, text: str) -> None:
        """设置标签文字。"""
        self._text = text
        self.updateGeometry()
        self.update()

    @override
    def set_icon(self, icon: icons.IconLike) -> None:
        self._icon = icons.coerce(icon, self.ICON_SIZE)
        self.updateGeometry()
        self.update()

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = 2 * self.PADDING
        if self._icon is not None:
            width += self.ICON_SIZE + self.ICON_GAP
        width += typography.text_width(self._text, self.LABEL_STYLE)
        width = max(width, self.MIN_WIDTH)
        margin = self.outer_margin
        return typography.size_hint(
            width + 2 * margin, self.CONTAINER_HEIGHT + 2 * margin
        )

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_LARGE

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = self.container_rect()
        color = self._content_color()
        left = rect.left() + self.PADDING
        if self._icon is not None:
            icon_rect = QtCore.QRectF(
                left,
                rect.center().y() - self.ICON_SIZE / 2,
                self.ICON_SIZE,
                self.ICON_SIZE,
            )
            self._icon.paint(painter, icon_rect, color)
            left += self.ICON_SIZE + self.ICON_GAP
        label_rect = QtCore.QRectF(
            left,
            rect.top(),
            max(0.0, rect.right() - self.PADDING - left),
            rect.height(),
        )
        typography.paint_text(
            painter,
            label_rect,
            self._text,
            self.LABEL_STYLE,
            color,
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )
