"""应用图标：运行时设为窗口图标，打包时导出为 .ico（Windows）与 .icns（macOS）。

图标用 QPainter 绘制（圆角方形底、额度环与用量柱），不依赖图片文件；
每个尺寸单独绘制，小尺寸去掉细节、加粗线条，保持清晰。
"""

from __future__ import annotations

import pathlib
import struct

from PySide6 import QtCore
from PySide6 import QtGui

TOP_COLOR = "#E48A6B"
BOTTOM_COLOR = "#C45F3D"
TRACK_ALPHA = 90
# 额度环：从左下方顺时针扫过 270°，点亮其中的 70%。
ARC_START = 225
ARC_SPAN = 270
ARC_VALUE = 0.7
# 小于该尺寸时只画额度环与圆点。
DETAIL_SIZE = 40
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
# macOS .icns 中以 PNG 保存的条目：(类型, 像素尺寸)。
ICNS_ENTRIES = (
    (b"icp4", 16),
    (b"icp5", 32),
    (b"ic11", 32),
    (b"ic12", 64),
    (b"ic07", 128),
    (b"ic13", 256),
    (b"ic08", 256),
    (b"ic14", 512),
    (b"ic09", 512),
    (b"ic10", 1024),
)


def render(size: int) -> QtGui.QImage:
    """绘制 ``size`` × ``size`` 像素的图标。"""
    image = QtGui.QImage(
        size, size, QtGui.QImage.Format.Format_ARGB32_Premultiplied
    )
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.scale(size, size)  # 以下坐标都是边长的比例
    detailed = size >= DETAIL_SIZE
    margin = 0.06 if detailed else 0.0
    body = QtCore.QRectF(margin, margin, 1 - 2 * margin, 1 - 2 * margin)
    unit = body.width()
    gradient = QtGui.QLinearGradient(body.topLeft(), body.bottomRight())
    gradient.setColorAt(0, QtGui.QColor(TOP_COLOR))
    gradient.setColorAt(1, QtGui.QColor(BOTTOM_COLOR))
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(body, 0.23 * unit, 0.23 * unit)

    center = body.center()
    radius = (0.29 if detailed else 0.3) * unit
    ring = QtCore.QRectF(
        center.x() - radius, center.y() - radius, 2 * radius, 2 * radius
    )
    pen = QtGui.QPen(QtGui.QColor(255, 255, 255, TRACK_ALPHA))
    pen.setWidthF((0.075 if detailed else 0.12) * unit)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.drawArc(ring, ARC_START * 16, -ARC_SPAN * 16)
    pen.setColor(QtGui.QColor("white"))
    painter.setPen(pen)
    painter.drawArc(ring, ARC_START * 16, -round(ARC_SPAN * ARC_VALUE * 16))

    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor("white"))
    if detailed:
        width, gap = 0.06 * unit, 0.035 * unit
        left = center.x() - (3 * width + 2 * gap) / 2
        bottom = center.y() + 0.1 * unit
        for index, height in enumerate((0.1, 0.15, 0.2)):
            bar = QtCore.QRectF(
                left + index * (width + gap),
                bottom - height * unit,
                width,
                height * unit,
            )
            painter.drawRoundedRect(bar, width / 2, width / 2)
    else:
        dot = 0.1 * unit
        painter.drawEllipse(center, dot, dot)
    painter.end()
    return image


def png_bytes(size: int) -> bytes:
    """图标的 PNG 编码。"""
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
    render(size).save(buffer, "PNG")
    return bytes(buffer.data().data())


def icon() -> QtGui.QIcon:
    """含各常用尺寸的窗口图标。"""
    result = QtGui.QIcon()
    for size in ICON_SIZES:
        result.addPixmap(QtGui.QPixmap.fromImage(render(size)))
    return result


def ico_bytes() -> bytes:
    """Windows .ico：各尺寸以 PNG 保存（Windows Vista 起支持）。"""
    images = [png_bytes(size) for size in ICON_SIZES]
    offset = 6 + 16 * len(images)
    entries = []
    for size, data in zip(ICON_SIZES, images, strict=True):
        side = 0 if size >= 256 else size  # 0 表示 256
        entries.append(
            struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(data), offset)
        )
        offset += len(data)
    header = struct.pack("<HHH", 0, 1, len(images))
    return header + b"".join(entries) + b"".join(images)


def icns_bytes() -> bytes:
    """macOS .icns：各尺寸以 PNG 保存。"""
    cache: dict[int, bytes] = {}
    chunks = []
    for kind, size in ICNS_ENTRIES:
        if size not in cache:
            cache[size] = png_bytes(size)
        data = cache[size]
        chunks.append(kind + struct.pack(">I", 8 + len(data)) + data)
    body = b"".join(chunks)
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def write(path: pathlib.Path) -> pathlib.Path:
    """按扩展名（.ico / .icns / .png）写出图标文件，返回路径。"""
    suffix = path.suffix.lower()
    if suffix == ".ico":
        data = ico_bytes()
    elif suffix == ".icns":
        data = icns_bytes()
    elif suffix == ".png":
        data = png_bytes(512)
    else:
        raise ValueError(f"不支持的图标格式：{path.suffix}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
