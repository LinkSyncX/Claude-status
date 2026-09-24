"""键盘焦点指示环。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui

from md3.core import shape as shape_utils
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens

# 出现动画：环宽先在前 25% 时间内从 0 扩展到 8dp，再回缩到 3dp。
GROW_WIDTH = 8.0
GROW_PHASE = 0.25
ANIMATION_DURATION_MS = 600


def focus_ring_margin() -> float:
    """焦点环越出容器的距离，组件需据此预留空间。"""
    return state_tokens.FOCUS_RING_OFFSET + state_tokens.FOCUS_RING_WIDTH


def animated_width(progress: float) -> float:
    """按出现动画进度（0–1）返回环宽。"""
    progress = max(0.0, min(1.0, progress))
    if progress < GROW_PHASE:
        return GROW_WIDTH * progress / GROW_PHASE
    remaining = (progress - GROW_PHASE) / (1.0 - GROW_PHASE)
    return GROW_WIDTH - (GROW_WIDTH - state_tokens.FOCUS_RING_WIDTH) * remaining


def paint_focus_ring(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    shape: shape_tokens.Shape,
    color: QtGui.QColor,
    inward: bool = False,
    max_extent: float | None = None,
    progress: float = 1.0,
) -> None:
    """围绕容器绘制 3dp 焦点环。

    Args:
        painter: 目标画笔。
        rect: 容器矩形。
        shape: 容器形状。
        color: 环颜色，规范为 ``secondary``。
        inward: 为真时环画在容器内侧（用于无法外扩的场景）。
        max_extent: 容器外可用的空间；不足时先压缩偏移再压缩宽度，
            为 0 时改为内侧绘制。
        progress: 出现动画进度，1 为稳定状态。
    """
    width = animated_width(progress)
    if width <= 0.05:
        return
    offset = state_tokens.FOCUS_RING_OFFSET
    if max_extent is not None and not inward:
        if max_extent <= 0.5:
            inward = True
        elif max_extent < offset + width:
            offset = max(0.0, max_extent - width)
            width = min(width, max_extent - offset)
    if inward:
        ring_rect = rect.adjusted(width / 2, width / 2, -width / 2, -width / 2)
        ring_shape = shape_utils.outset_shape(shape, -width / 2)
    else:
        grow = offset + width / 2
        ring_rect = rect.adjusted(-grow, -grow, grow, grow)
        ring_shape = shape_utils.outset_shape(shape, grow)
    path = shape_utils.rounded_rect_path(ring_rect, ring_shape)
    pen = QtGui.QPen(color, width)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.save()
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()
