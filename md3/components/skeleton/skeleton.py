"""骨架屏（Skeleton）。

内容加载前的占位形状：矩形、圆形或文本行，填充 ``surface_container_highest``，
一道柔和的高光沿布局方向缓慢扫过（1.6s 一周）。``SkeletonText`` 生成若干
行文本占位（最后一行较短），``skeleton_list_item`` 组合出"头像 + 两行文
字"的列表项占位。所有动画由 ``FrameClock`` 驱动，隐藏时自动停止。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens

SHIMMER_PERIOD_MS = 1600
SHIMMER_WIDTH_RATIO = 0.6
SHIMMER_OPACITY = 0.55
TEXT_LINE_HEIGHT = 14.0
TEXT_LINE_GAP = 10.0


class SkeletonShape(enum.Enum):
    """占位形状。"""

    RECT = "rect"
    CIRCLE = "circle"
    TEXT = "text"


class Skeleton(widget.MaterialWidget):
    """单个占位形状。

    Args:
        width: 宽度（px）；None 时随布局伸展。
        height: 高度（px）。
        shape: 形状。
        radius: 矩形圆角；文本行固定为 4dp，圆形忽略。
        animated: 是否播放高光扫过动画。
        parent: 父控件。
    """

    def __init__(
        self,
        width: float | None = None,
        height: float = 16.0,
        shape: SkeletonShape = SkeletonShape.RECT,
        radius: float = shape_tokens.SMALL,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._shape = shape
        self._radius = radius
        self._animated = animated
        self._clock = animation.FrameClock(self)
        self._clock.ticked.connect(self.update)
        if shape is SkeletonShape.CIRCLE:
            side = round(width if width is not None else height)
            self.setFixedSize(side, side)
        else:
            self.setFixedHeight(round(height))
            if width is not None:
                self.setFixedWidth(round(width))
            else:
                self.setSizePolicy(
                    QtWidgets.QSizePolicy.Policy.Expanding,
                    QtWidgets.QSizePolicy.Policy.Fixed,
                )

    @property
    def shape(self) -> SkeletonShape:
        """形状。"""
        return self._shape

    @property
    def animated(self) -> bool:
        """是否播放动画。"""
        return self._animated

    def set_animated(self, animated: bool) -> None:
        """开启或关闭高光动画。"""
        self._animated = animated
        self._refresh_clock()

    def _refresh_clock(self) -> None:
        if (
            self._animated
            and self.isVisible()
            and animation.animations_enabled()
        ):
            self._clock.start()
        else:
            self._clock.stop()
        self.update()

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_clock()

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self._clock.stop()

    def shimmer_phase(self) -> float:
        """当前高光位置 0–1（不播放时为 -1）。"""
        if not self._clock.is_active():
            return -1.0
        return (
            self._clock.elapsed_ms() % SHIMMER_PERIOD_MS
        ) / SHIMMER_PERIOD_MS

    def _path(self) -> QtGui.QPainterPath:
        rect = QtCore.QRectF(self.rect())
        if self._shape is SkeletonShape.CIRCLE:
            return shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL)
        radius = (
            shape_tokens.EXTRA_SMALL
            if self._shape is SkeletonShape.TEXT
            else self._radius
        )
        return shape_utils.rounded_rect_path(
            rect, shape_tokens.Shape.all(radius)
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        path = self._path()
        shape_utils.fill_shape(
            painter, path, self.color("surface_container_highest")
        )
        phase = self.shimmer_phase()
        if phase < 0:
            return
        rect = QtCore.QRectF(self.rect())
        band = rect.width() * SHIMMER_WIDTH_RATIO
        travel = rect.width() + band
        start = rect.left() - band + travel * phase
        if self.is_rtl():
            start = rect.right() - (start - rect.left()) - band
        highlight = theme_module.with_alpha(
            self.color("surface_container_lowest"), SHIMMER_OPACITY
        )
        transparent = theme_module.with_alpha(highlight, 0.0)
        gradient = QtGui.QLinearGradient(start, 0.0, start + band, 0.0)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, highlight)
        gradient.setColorAt(1.0, transparent)
        painter.save()
        painter.setClipPath(path)
        painter.fillRect(rect, QtGui.QBrush(gradient))
        painter.restore()


class SkeletonText(QtWidgets.QWidget):
    """若干行文本占位。

    Args:
        lines: 行数。
        line_height: 每行高度。
        last_line_ratio: 最后一行相对宽度（0–1）。
        animated: 是否播放动画。
        parent: 父控件。
    """

    def __init__(
        self,
        lines: int = 3,
        line_height: float = TEXT_LINE_HEIGHT,
        last_line_ratio: float = 0.6,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ratio = max(0.1, min(1.0, last_line_ratio))
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(TEXT_LINE_GAP))
        self._lines: list[Skeleton] = []
        for _ in range(max(1, lines)):
            line = Skeleton(
                None, line_height, SkeletonShape.TEXT, animated=animated
            )
            self._lines.append(line)
            layout.addWidget(line)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def lines(self) -> list[Skeleton]:
        """各行占位。"""
        return list(self._lines)

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if len(self._lines) > 1:
            last = self._lines[-1]
            last.setMaximumWidth(max(24, round(self.width() * self._ratio)))


def skeleton_list_item(
    avatar: bool = True,
    lines: int = 2,
    animated: bool = True,
    parent: QtWidgets.QWidget | None = None,
) -> QtWidgets.QWidget:
    """组合出一个列表项占位：可选的 40dp 圆形头像 + 文本行。"""
    item = QtWidgets.QWidget(parent)
    layout = QtWidgets.QHBoxLayout(item)
    layout.setContentsMargins(16, 8, 16, 8)
    layout.setSpacing(16)
    if avatar:
        layout.addWidget(
            Skeleton(40, 40, SkeletonShape.CIRCLE, animated=animated),
            0,
            QtCore.Qt.AlignmentFlag.AlignTop,
        )
    layout.addWidget(SkeletonText(lines, animated=animated), 1)
    return item
