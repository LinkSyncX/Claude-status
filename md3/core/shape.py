"""把形状令牌转换为 ``QPainterPath``。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui

from md3.tokens import shape as shape_tokens


def rounded_rect_path(
    rect: QtCore.QRectF | QtCore.QRect,
    shape: shape_tokens.Shape | float,
) -> QtGui.QPainterPath:
    """生成圆角矩形路径，支持四角不同半径与 ``FULL`` 胶囊形。

    Args:
        rect: 目标矩形。
        shape: ``Shape`` 或统一半径。
    """
    rect = QtCore.QRectF(rect)
    if not isinstance(shape, shape_tokens.Shape):
        shape = shape_tokens.Shape.all(shape)
    resolved = shape.resolved(rect.width(), rect.height())
    path = QtGui.QPainterPath()
    if resolved.is_uniform:
        radius = resolved.top_left
        if radius <= 0:
            path.addRect(rect)
        else:
            path.addRoundedRect(rect, radius, radius)
        return path

    left, top = rect.left(), rect.top()
    right, bottom = rect.right(), rect.bottom()
    tl, tr = resolved.top_left, resolved.top_right
    br, bl = resolved.bottom_right, resolved.bottom_left

    path.moveTo(left + tl, top)
    path.lineTo(right - tr, top)
    if tr > 0:
        path.arcTo(right - 2 * tr, top, 2 * tr, 2 * tr, 90, -90)
    path.lineTo(right, bottom - br)
    if br > 0:
        path.arcTo(right - 2 * br, bottom - 2 * br, 2 * br, 2 * br, 0, -90)
    path.lineTo(left + bl, bottom)
    if bl > 0:
        path.arcTo(left, bottom - 2 * bl, 2 * bl, 2 * bl, 270, -90)
    path.lineTo(left, top + tl)
    if tl > 0:
        path.arcTo(left, top, 2 * tl, 2 * tl, 180, -90)
    path.closeSubpath()
    return path


def fill_shape(
    painter: QtGui.QPainter,
    path: QtGui.QPainterPath,
    fill: QtGui.QColor | QtGui.QBrush | None,
    outline: QtGui.QColor | None = None,
    outline_width: float = 1.0,
) -> None:
    """填充并按需描边一个路径；描边画在路径内侧以免越界。"""
    painter.save()
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    if fill is not None:
        painter.setBrush(fill)
        painter.drawPath(path)
    if outline is not None and outline.alpha() > 0 and outline_width > 0:
        # 裁剪到路径内后只保留描边的内侧一半，因此画笔宽度取两倍。
        pen = QtGui.QPen(outline, outline_width * 2)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setClipPath(path, QtCore.Qt.ClipOperation.IntersectClip)
        painter.drawPath(path)
    painter.restore()


def circle_path(center: QtCore.QPointF, radius: float) -> QtGui.QPainterPath:
    """以圆心与半径生成圆形路径。"""
    path = QtGui.QPainterPath()
    path.addEllipse(center, radius, radius)
    return path


def inset(rect: QtCore.QRectF, amount: float) -> QtCore.QRectF:
    """向内收缩矩形（负值为外扩）。"""
    return rect.adjusted(amount, amount, -amount, -amount)


def outset_shape(
    shape: shape_tokens.Shape, amount: float
) -> shape_tokens.Shape:
    """把形状的每个非零半径外扩指定距离，用于描边或焦点环。"""

    def grow(radius: float) -> float:
        if radius <= 0:
            return 0.0
        return radius + amount

    return shape_tokens.Shape(
        grow(shape.top_left),
        grow(shape.top_right),
        grow(shape.bottom_right),
        grow(shape.bottom_left),
    )
