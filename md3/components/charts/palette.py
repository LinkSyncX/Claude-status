"""数据系列配色。

前若干个系列使用主题的语义色彩角色，保证与界面其余部分协调；系列更多
时按黄金角在 HCT 色相环上旋转生成新颜色，色度与色调保持一致。
"""

from __future__ import annotations

from PySide6 import QtGui

from md3.color import hct
from md3.theme import theme as theme_module

# 只使用在明暗模式下都互不重合的四个角色；更多系列改由色相旋转生成
# （暗色主题中 primary 与 primary_fixed_dim 同为 T80，不能作为独立颜色）。
_ROLE_CYCLE: tuple[str, ...] = ("primary", "tertiary", "secondary", "error")
_GOLDEN_ANGLE = 137.508
_GENERATED_CHROMA = 48.0


def series_colors(theme: theme_module.Theme, count: int) -> list[QtGui.QColor]:
    """返回 count 个彼此可区分且与主题协调的系列颜色。"""
    colors = [theme.color(role) for role in _ROLE_CYCLE[:count]]
    extra = count - len(colors)
    if extra > 0:
        seed = hct.Hct.from_int(theme.seed)
        tone = 80.0 if theme.dark else 40.0
        for index in range(extra):
            hue = (seed.hue + _GOLDEN_ANGLE * (index + 1)) % 360.0
            generated = hct.Hct.from_hct(hue, _GENERATED_CHROMA, tone)
            colors.append(theme_module.qcolor(generated.to_int()))
    return colors


def resolve_color(
    theme: theme_module.Theme,
    color: QtGui.QColor | str | None,
    fallback: QtGui.QColor,
) -> QtGui.QColor:
    """把系列的颜色声明解析为 ``QColor``。"""
    if color is None:
        return fallback
    if isinstance(color, QtGui.QColor):
        return color
    if color.startswith("#"):
        return QtGui.QColor(color)
    return theme.color(color)
