"""Theme 页面：色彩角色、排版标度与形状标度一览。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.demo.pages import _common
from md3.theme import theme as theme_module
from md3.tokens import color as color_tokens
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

_SWATCH_GROUPS = [
    ("primary", "on_primary", "primary_container", "on_primary_container"),
    (
        "secondary",
        "on_secondary",
        "secondary_container",
        "on_secondary_container",
    ),
    ("tertiary", "on_tertiary", "tertiary_container", "on_tertiary_container"),
    ("error", "on_error", "error_container", "on_error_container"),
    ("surface_dim", "surface", "surface_bright", "surface_tint"),
    (
        "surface_container_lowest",
        "surface_container_low",
        "surface_container",
        "surface_container_high",
    ),
    (
        "surface_container_highest",
        "on_surface",
        "on_surface_variant",
        "outline",
    ),
    (
        "outline_variant",
        "inverse_surface",
        "inverse_on_surface",
        "inverse_primary",
    ),
]


class ColorSwatch(widget.MaterialWidget):
    """显示一个色彩角色的色块、名称与十六进制值。"""

    def __init__(
        self, role: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._role = role
        self.setFixedSize(168, 64)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        if not self.theme.has_color(self._role):
            return
        argb = self.theme.argb(self._role)
        fill = theme_module.qcolor(argb)
        path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_SMALL)
        shape_utils.fill_shape(
            painter, path, fill, self.color("outline_variant"), 1.0
        )
        text = QtGui.QColor("black" if fill.lightness() > 140 else "white")
        typography.paint_text(
            painter,
            rect.adjusted(8, 6, -8, 0),
            self._role.replace("_", " "),
            "label-medium",
            text,
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignTop,
        )
        typography.paint_text(
            painter,
            rect.adjusted(8, 0, -8, -6),
            color_tokens.argb_to_hex(argb),
            "label-small",
            text,
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignBottom,
        )


class ShapeSample(widget.MaterialWidget):
    """显示一个形状标度的示例。"""

    def __init__(
        self, name: str, radius: float, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._radius = radius
        self.setFixedSize(112, 88)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(8, 0, 96, 56)
        path = shape_utils.rounded_rect_path(rect, self._radius)
        shape_utils.fill_shape(painter, path, self.color("primary_container"))
        typography.paint_text(
            painter,
            QtCore.QRectF(0, 64, self.width(), 20),
            self._name,
            "label-medium",
            self.color("on_surface_variant"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page("主题", "当前主题的色彩角色、排版标度与形状标度。")
    colors = page.section(
        "色彩角色", "由种子色经 HCT 色彩空间生成，明暗模式各一套。"
    )
    for group in _SWATCH_GROUPS:
        page.row(colors, [ColorSwatch(role) for role in group])

    extended_section = page.section(
        "扩展色",
        "success / warning / info 由各自的种子色生成，色相向主色轻微偏移"
        "以保持和谐，并随明暗与对比度一起变化。",
    )
    for name in ("success", "warning", "info"):
        page.row(
            extended_section,
            [
                ColorSwatch(role)
                for role in (
                    name,
                    f"on_{name}",
                    f"{name}_container",
                    f"on_{name}_container",
                )
            ],
        )

    type_section = page.section("排版标度")
    for style in typography_tokens.TYPE_SCALE.values():
        label = typography.Label(
            f"{style.name}  {style.size:g}/{style.line_height:g}",
            style.role,
            "on_surface",
        )
        type_section.addWidget(label)

    shapes = page.section("形状标度")
    page.row(
        shapes,
        [
            ShapeSample("none", shape_tokens.NONE),
            ShapeSample("extra small", shape_tokens.EXTRA_SMALL),
            ShapeSample("small", shape_tokens.SMALL),
            ShapeSample("medium", shape_tokens.MEDIUM),
            ShapeSample("large", shape_tokens.LARGE),
            ShapeSample("extra large", shape_tokens.EXTRA_LARGE),
            ShapeSample("full", shape_tokens.FULL),
        ],
    )
    page.finish()
    return page
