"""加载指示器（Loading indicator，M3 Expressive）。

不确定态在七个 Material 形状之间依次变形：每 650ms 开始一次变形，形状
用带轻微回弹的弹簧过渡，并同时顺时针转 90°；整体另以 4666ms 一圈匀速
旋转。确定态按进度把圆形逐渐变为 soft burst，并逆时针旋转 180°。
``ContainedLoadingIndicator`` 额外绘制 48dp 的 primary-container 圆形
容器。参数取自 Compose Material3 的 ``LoadingIndicator``。
"""

from __future__ import annotations

from collections.abc import Sequence
import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.progress import indicators
from md3.core import animation
from md3.core import polygon
from md3.core import shape as shape_utils
from md3.tokens import motion

CONTAINER_SIZE = 48.0
INDICATOR_SIZE = 38.0
GLOBAL_ROTATION_MS = 4666
MORPH_INTERVAL_MS = 650
# 变形弹簧的静止阈值放宽到 0.1，使其在 650ms 间隔内明显早于下一次变形结束。
MORPH_REST_THRESHOLD = 0.1
QUARTER_TURN = 90.0
DETERMINATE_ROTATION = -180.0


class LoadingIndicator(indicators.ProgressIndicator):
    """形状变形式加载指示器。

    Args:
        value: 进度 0–1；None（默认）表示不确定态。
        size: 容器边长（dp），活动形状按 38/48 的比例缩放。
        contained: 是否绘制 primary-container 圆形容器。
        shapes: 不确定态循环变形的形状序列（至少两个），默认为 M3 的
            七个形状。
        parent: 父控件。
    """

    def __init__(
        self,
        value: float | None = None,
        size: float = CONTAINER_SIZE,
        contained: bool = False,
        shapes: Sequence[polygon.RoundedPolygon] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(value, parent)
        shapes = tuple(shapes or polygon.LOADING_INDICATOR_SHAPES)
        if len(shapes) < 2:
            raise ValueError("shapes 至少需要两个形状")
        self._size = float(size)
        self._contained = contained
        self._radii = [shape.radii() for shape in shapes]
        self._determinate_radii = [
            shape.radii() for shape in polygon.DETERMINATE_LOADING_SHAPES
        ]
        self._morph_index = 0
        self._morph_step = -1
        self._base_rotation = QUARTER_TURN
        # 单次变形进度，弹簧可能短暂超过 1 以表现回弹。
        self._morph = animation.AnimatedFloat(self, 0.0, self.update)
        self._morph.finished.connect(self._advance_morph)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 属性 -------------------------------------------------------------

    @property
    def contained(self) -> bool:
        """是否带容器。"""
        return self._contained

    def set_contained(self, contained: bool) -> None:
        """切换容器。"""
        self._contained = bool(contained)
        self.update()

    @property
    def shape_index(self) -> int:
        """不确定态当前正在离开的形状下标。"""
        return self._morph_index

    @property
    def morph_progress(self) -> float:
        """当前变形进度（0–1，回弹时可能略大于 1）。"""
        return self._morph.value

    @property
    def size_dp(self) -> float:
        """容器边长（dp）。"""
        return self._size

    @override
    def sizeHint(self) -> QtCore.QSize:
        side = math.ceil(self._size)
        return QtCore.QSize(side, side)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def set_indeterminate(self, indeterminate: bool) -> None:
        if bool(indeterminate) != self._indeterminate and indeterminate:
            self._morph_index = 0
            self._morph_step = -1
            self._base_rotation = QUARTER_TURN
            self._morph.set(0.0)
        super().set_indeterminate(indeterminate)

    # ---- 动画 -------------------------------------------------------------

    @override
    def _tick(self) -> None:
        step = self.elapsed_ms() // MORPH_INTERVAL_MS
        if step != self._morph_step:
            self._morph_step = step
            if self._morph.is_running():
                self._advance_morph()
            self._morph.set(0.0)
            self._morph.spring_to(
                1.0, motion.MORPH_SPRING, MORPH_REST_THRESHOLD
            )
        self.update()

    def _advance_morph(self) -> None:
        """一次变形结束：切换到下一形状并累计 90° 旋转。"""
        if not self._indeterminate:
            return
        self._morph_index = (self._morph_index + 1) % len(self._radii)
        self._base_rotation = (self._base_rotation + QUARTER_TURN) % 360.0
        self._morph.set(0.0)

    def current_shape(self) -> tuple[tuple[float, ...], float]:
        """当前绘制的（极坐标半径序列, 顺时针旋转角度）。"""
        if self._indeterminate:
            progress = self._morph.value
            start = self._radii[self._morph_index]
            end = self._radii[(self._morph_index + 1) % len(self._radii)]
            elapsed = self.elapsed_ms() % GLOBAL_ROTATION_MS
            rotation = (
                progress * QUARTER_TURN
                + self._base_rotation
                + elapsed / GLOBAL_ROTATION_MS * 360.0
            )
            return polygon.morph_radii(start, end, progress), rotation
        progress = self.display_value
        radii = polygon.morph_radii(
            self._determinate_radii[0], self._determinate_radii[1], progress
        )
        return radii, DETERMINATE_ROTATION * progress

    # ---- 绘制 -------------------------------------------------------------

    def container_color(self) -> QtGui.QColor:
        """容器颜色。"""
        return self.color("primary_container")

    @override
    def active_color(self) -> QtGui.QColor:
        if self._contained:
            return self.color("on_primary_container")
        return self.color("primary")

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        side = min(rect.width(), rect.height())
        center = rect.center()
        if self._contained:
            shape_utils.fill_shape(
                painter,
                shape_utils.circle_path(center, side / 2),
                self.container_color(),
            )
        radii, rotation = self.current_shape()
        radius = side * INDICATOR_SIZE / CONTAINER_SIZE / 2
        path = polygon.polar_path(radii, center, radius, rotation)
        shape_utils.fill_shape(painter, path, self.active_color())


class ContainedLoadingIndicator(LoadingIndicator):
    """带 primary-container 圆形容器的加载指示器。

    Args:
        value: 进度 0–1；None（默认）表示不确定态。
        size: 容器边长（dp）。
        shapes: 不确定态循环变形的形状序列。
        parent: 父控件。
    """

    def __init__(
        self,
        value: float | None = None,
        size: float = CONTAINER_SIZE,
        shapes: Sequence[polygon.RoundedPolygon] | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(value, size, True, shapes, parent)
