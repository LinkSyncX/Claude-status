"""无障碍触控目标（最小 48 dp）。"""

from __future__ import annotations

from PySide6 import QtCore

from md3.tokens import state as state_tokens

MIN_SIZE = int(state_tokens.MIN_TOUCH_TARGET)


def expand(size: QtCore.QSize, minimum: int = MIN_SIZE) -> QtCore.QSize:
    """把尺寸扩展到不小于触控目标。"""
    return QtCore.QSize(max(size.width(), minimum), max(size.height(), minimum))


def centered_rect(
    outer: QtCore.QRectF, width: float, height: float
) -> QtCore.QRectF:
    """在外部矩形内居中放置给定尺寸的矩形（视觉容器）。"""
    return QtCore.QRectF(
        outer.left() + (outer.width() - width) / 2,
        outer.top() + (outer.height() - height) / 2,
        width,
        height,
    )


def contains(
    visual: QtCore.QRectF, point: QtCore.QPointF, minimum: int = MIN_SIZE
) -> bool:
    """判断点是否命中扩展到触控目标后的区域。"""
    grow_w = max(0.0, (minimum - visual.width()) / 2)
    grow_h = max(0.0, (minimum - visual.height()) / 2)
    return visual.adjusted(-grow_w, -grow_h, grow_w, grow_h).contains(point)
