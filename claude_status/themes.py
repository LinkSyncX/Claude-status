"""界面主题：Material 动态配色与极简白。

- **Material**：由主题色（种子色）生成 M3 动态配色，表面带有主题色调。
- **极简白**：纯白背景、黑白灰的中性配色，按钮与选中状态为近黑色；只保留
  一个克制的蓝色作为第二强调色（图表靠它区分数据系列）。错误、成功与警告
  等状态色保持彩色，含义不变。深色模式下是对应的中性深色（极简黑）。

极简白以 md3 的单色（MONOCHROME）配色为基础，再覆盖表面、容器与强调色
等角色，因此没有覆盖的角色（错误色等）仍由 md3 生成。
"""

from __future__ import annotations

import dataclasses

from md3.color import variant as variant_module
from md3.theme import theme as theme_module

from claude_status import models

MATERIAL = "material"
MINIMAL = "minimal"
STYLES = (MATERIAL, MINIMAL)
LABELS = {MATERIAL: "Material", MINIMAL: "极简白"}
ICONS = {MATERIAL: "palette", MINIMAL: "contrast"}
# 极简白的强调色：扩展色（成功 / 警告）的协调与图表额外系列的色相都以它为准。
MINIMAL_SEED = "#3B6FE0"

_MINIMAL_LIGHT = {
    "primary": 0xFF1A1A1A,
    "on_primary": 0xFFFFFFFF,
    "primary_container": 0xFFE4E4E4,
    "on_primary_container": 0xFF1A1A1A,
    "secondary": 0xFF5C5C5C,
    "on_secondary": 0xFFFFFFFF,
    "secondary_container": 0xFFE6E6E6,
    "on_secondary_container": 0xFF262626,
    "tertiary": 0xFF3B6FE0,
    "on_tertiary": 0xFFFFFFFF,
    "tertiary_container": 0xFFE7EEFC,
    "on_tertiary_container": 0xFF123A8C,
    "primary_fixed": 0xFFEFEFEF,
    "primary_fixed_dim": 0xFFD4D4D4,
    "on_primary_fixed": 0xFF1A1A1A,
    "on_primary_fixed_variant": 0xFF404040,
    "secondary_fixed": 0xFFEFEFEF,
    "secondary_fixed_dim": 0xFFD4D4D4,
    "on_secondary_fixed": 0xFF262626,
    "on_secondary_fixed_variant": 0xFF4A4A4A,
    "tertiary_fixed": 0xFFE7EEFC,
    "tertiary_fixed_dim": 0xFFBBCDF6,
    "on_tertiary_fixed": 0xFF0B2B6B,
    "on_tertiary_fixed_variant": 0xFF2A56B8,
    "surface": 0xFFFFFFFF,
    "on_surface": 0xFF1A1A1A,
    "surface_variant": 0xFFF0F0F0,
    "on_surface_variant": 0xFF666666,
    "surface_dim": 0xFFEDEDED,
    "surface_bright": 0xFFFFFFFF,
    "surface_container_lowest": 0xFFFFFFFF,
    "surface_container_low": 0xFFFAFAFA,
    "surface_container": 0xFFF6F6F6,
    "surface_container_high": 0xFFF3F3F3,
    "surface_container_highest": 0xFFF0F0F0,
    "surface_tint": 0xFFFFFFFF,
    "inverse_surface": 0xFF262626,
    "inverse_on_surface": 0xFFF5F5F5,
    "inverse_primary": 0xFFCFCFCF,
    "outline": 0xFFBDBDBD,
    "outline_variant": 0xFFE5E5E5,
    "background": 0xFFFFFFFF,
    "on_background": 0xFF1A1A1A,
    "shadow": 0xFF000000,
    "scrim": 0xFF000000,
}

_MINIMAL_DARK = {
    "primary": 0xFFF2F2F2,
    "on_primary": 0xFF141414,
    "primary_container": 0xFF2B2B2B,
    "on_primary_container": 0xFFF2F2F2,
    "secondary": 0xFFB3B3B3,
    "on_secondary": 0xFF1A1A1A,
    "secondary_container": 0xFF2B2B2B,
    "on_secondary_container": 0xFFE6E6E6,
    "tertiary": 0xFF8FB3FF,
    "on_tertiary": 0xFF0B2B6B,
    "tertiary_container": 0xFF1F2E4D,
    "on_tertiary_container": 0xFFD8E3FF,
    "primary_fixed": 0xFFEFEFEF,
    "primary_fixed_dim": 0xFFD4D4D4,
    "on_primary_fixed": 0xFF1A1A1A,
    "on_primary_fixed_variant": 0xFF404040,
    "secondary_fixed": 0xFFEFEFEF,
    "secondary_fixed_dim": 0xFFD4D4D4,
    "on_secondary_fixed": 0xFF262626,
    "on_secondary_fixed_variant": 0xFF4A4A4A,
    "tertiary_fixed": 0xFFE7EEFC,
    "tertiary_fixed_dim": 0xFFBBCDF6,
    "on_tertiary_fixed": 0xFF0B2B6B,
    "on_tertiary_fixed_variant": 0xFF2A56B8,
    "surface": 0xFF141414,
    "on_surface": 0xFFEDEDED,
    "surface_variant": 0xFF2B2B2B,
    "on_surface_variant": 0xFFA6A6A6,
    "surface_dim": 0xFF141414,
    "surface_bright": 0xFF383838,
    "surface_container_lowest": 0xFF0F0F0F,
    "surface_container_low": 0xFF1A1A1A,
    "surface_container": 0xFF1E1E1E,
    "surface_container_high": 0xFF252525,
    "surface_container_highest": 0xFF2E2E2E,
    "surface_tint": 0xFFFFFFFF,
    "inverse_surface": 0xFFEDEDED,
    "inverse_on_surface": 0xFF1E1E1E,
    "inverse_primary": 0xFF404040,
    "outline": 0xFF5C5C5C,
    "outline_variant": 0xFF333333,
    "background": 0xFF141414,
    "on_background": 0xFFEDEDED,
    "shadow": 0xFF000000,
    "scrim": 0xFF000000,
}


def minimal_theme(
    dark: bool,
    font_family: str | None = None,
    extended: theme_module.ExtendedSpec = None,
) -> theme_module.Theme:
    """极简白（深色模式下为极简黑）主题。"""
    base = theme_module.Theme.from_seed(
        MINIMAL_SEED,
        dark=dark,
        variant=variant_module.Variant.MONOCHROME,
        font_family=font_family,
        extended=extended,
    )
    overrides = _MINIMAL_DARK if dark else _MINIMAL_LIGHT
    return dataclasses.replace(
        base, colors=dataclasses.replace(base.colors, **overrides)
    )


def build(
    settings: models.Settings, current: theme_module.Theme
) -> theme_module.Theme:
    """按设置生成主题；字体、对比度与扩展色沿用当前主题。"""
    if settings.theme_style == MINIMAL:
        return minimal_theme(settings.dark, current.font_family, current.extended)
    return theme_module.Theme.from_seed(
        settings.seed,
        dark=settings.dark,
        font_family=current.font_family,
        contrast=current.contrast,
        extended=current.extended,
    )
