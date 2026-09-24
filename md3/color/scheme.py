"""配色方案：把核心色板按 M3 规范的色调映射为完整的色彩角色。

色调映射与 material-color-utilities 中 2021 版色彩规范一致，包含 surface
container 五级、fixed 系列与 inverse 系列；``contrast_level`` 大于 0 时由
:mod:`md3.color.dynamic` 按对比度曲线提高前景与背景的对比度。
"""

from __future__ import annotations

from md3.color import core_palette as core_palette_module
from md3.color import dynamic
from md3.color import variant as variant_module
from md3.tokens import color as color_tokens

Variant = variant_module.Variant
CorePalette = core_palette_module.CorePalette
ContrastLevel = dynamic.ContrastLevel

# 标准对比度下每个角色的取值：(调色板名, 亮色色调, 暗色色调)。
_TONES: dict[str, tuple[str, float, float]] = {
    "primary": ("primary", 40, 80),
    "on_primary": ("primary", 100, 20),
    "primary_container": ("primary", 90, 30),
    "on_primary_container": ("primary", 30, 90),
    "secondary": ("secondary", 40, 80),
    "on_secondary": ("secondary", 100, 20),
    "secondary_container": ("secondary", 90, 30),
    "on_secondary_container": ("secondary", 30, 90),
    "tertiary": ("tertiary", 40, 80),
    "on_tertiary": ("tertiary", 100, 20),
    "tertiary_container": ("tertiary", 90, 30),
    "on_tertiary_container": ("tertiary", 30, 90),
    "error": ("error", 40, 80),
    "on_error": ("error", 100, 20),
    "error_container": ("error", 90, 30),
    "on_error_container": ("error", 30, 90),
    "primary_fixed": ("primary", 90, 90),
    "primary_fixed_dim": ("primary", 80, 80),
    "on_primary_fixed": ("primary", 10, 10),
    "on_primary_fixed_variant": ("primary", 30, 30),
    "secondary_fixed": ("secondary", 90, 90),
    "secondary_fixed_dim": ("secondary", 80, 80),
    "on_secondary_fixed": ("secondary", 10, 10),
    "on_secondary_fixed_variant": ("secondary", 30, 30),
    "tertiary_fixed": ("tertiary", 90, 90),
    "tertiary_fixed_dim": ("tertiary", 80, 80),
    "on_tertiary_fixed": ("tertiary", 10, 10),
    "on_tertiary_fixed_variant": ("tertiary", 30, 30),
    "surface": ("neutral", 98, 6),
    "on_surface": ("neutral", 10, 90),
    "surface_variant": ("neutral_variant", 90, 30),
    "on_surface_variant": ("neutral_variant", 30, 80),
    "surface_dim": ("neutral", 87, 6),
    "surface_bright": ("neutral", 98, 24),
    "surface_container_lowest": ("neutral", 100, 4),
    "surface_container_low": ("neutral", 96, 10),
    "surface_container": ("neutral", 94, 12),
    "surface_container_high": ("neutral", 92, 17),
    "surface_container_highest": ("neutral", 90, 22),
    "surface_tint": ("primary", 40, 80),
    "inverse_surface": ("neutral", 20, 90),
    "inverse_on_surface": ("neutral", 95, 20),
    "inverse_primary": ("primary", 80, 40),
    "outline": ("neutral_variant", 50, 60),
    "outline_variant": ("neutral_variant", 80, 30),
    "background": ("neutral", 98, 6),
    "on_background": ("neutral", 10, 90),
    "shadow": ("neutral", 0, 0),
    "scrim": ("neutral", 0, 0),
}

# 单色变体下需要覆盖的色调：(亮色色调, 暗色色调)。
_MONOCHROME_TONES: dict[str, tuple[float, float]] = {
    "primary": (0, 100),
    "on_primary": (90, 10),
    "primary_container": (25, 85),
    "on_primary_container": (100, 0),
    "on_secondary": (100, 10),
    "secondary_container": (85, 30),
    "on_secondary_container": (10, 90),
    "tertiary": (25, 90),
    "on_tertiary": (90, 10),
    "tertiary_container": (49, 60),
    "on_tertiary_container": (100, 0),
    "on_error_container": (10, 90),
    "primary_fixed": (40, 40),
    "primary_fixed_dim": (30, 30),
    "on_primary_fixed": (100, 100),
    "on_primary_fixed_variant": (90, 90),
    "secondary_fixed": (80, 80),
    "secondary_fixed_dim": (70, 70),
    "on_secondary_fixed_variant": (25, 25),
    "tertiary_fixed": (40, 40),
    "tertiary_fixed_dim": (30, 30),
    "on_tertiary_fixed": (100, 100),
    "on_tertiary_fixed_variant": (90, 90),
}


def standard_tones(is_dark: bool, monochrome: bool = False) -> dict[str, float]:
    """标准对比度下的静态色调表（供校验动态算法使用）。"""
    index = 1 if is_dark else 0
    tones: dict[str, float] = {}
    for role, (_palette, light_tone, dark_tone) in _TONES.items():
        tone = (light_tone, dark_tone)[index]
        if monochrome and role in _MONOCHROME_TONES:
            tone = _MONOCHROME_TONES[role][index]
        tones[role] = tone
    return tones


def from_palette(
    palette: CorePalette,
    is_dark: bool = False,
    monochrome: bool = False,
    contrast_level: ContrastLevel | float = ContrastLevel.STANDARD,
) -> color_tokens.ColorRoles:
    """由核心色板生成完整色彩角色。

    Args:
        palette: 核心色板。
        is_dark: 是否生成暗色方案。
        monochrome: 是否使用单色变体的特殊色调映射。
        contrast_level: 对比度等级；0 为标准，0.5 为中，1.0 为高。
    """
    level = dynamic.coerce_level(contrast_level)
    if level == 0.0:
        tones = standard_tones(is_dark, monochrome)
    else:
        tones = dynamic.resolve_tones(is_dark, monochrome, level)
    roles: dict[str, int] = {}
    for role, (palette_name, _light, _dark) in _TONES.items():
        tonal = getattr(palette, palette_name)
        roles[role] = tonal.tone(tones[role])
    return color_tokens.ColorRoles(**roles)


def from_seed(
    seed: int,
    is_dark: bool = False,
    variant: Variant = Variant.BASELINE,
    contrast_level: ContrastLevel | float = ContrastLevel.STANDARD,
) -> color_tokens.ColorRoles:
    """由种子色生成完整色彩角色。

    Args:
        seed: 种子色（ARGB）。
        is_dark: 是否生成暗色方案。
        variant: 配色变体。
        contrast_level: 对比度等级。
    """
    palette = CorePalette.from_seed(seed, variant)
    return from_palette(
        palette,
        is_dark=is_dark,
        monochrome=variant is Variant.MONOCHROME,
        contrast_level=contrast_level,
    )


def light(
    seed: int,
    variant: Variant = Variant.BASELINE,
    contrast_level: ContrastLevel | float = ContrastLevel.STANDARD,
) -> color_tokens.ColorRoles:
    """由种子色生成亮色方案。"""
    return from_seed(
        seed, is_dark=False, variant=variant, contrast_level=contrast_level
    )


def dark(
    seed: int,
    variant: Variant = Variant.BASELINE,
    contrast_level: ContrastLevel | float = ContrastLevel.STANDARD,
) -> color_tokens.ColorRoles:
    """由种子色生成暗色方案。"""
    return from_seed(
        seed, is_dark=True, variant=variant, contrast_level=contrast_level
    )


def from_colors(
    primary: int,
    secondary: int | None = None,
    tertiary: int | None = None,
    neutral: int | None = None,
    neutral_variant: int | None = None,
    error: int | None = None,
    is_dark: bool = False,
    contrast_level: ContrastLevel | float = ContrastLevel.STANDARD,
) -> color_tokens.ColorRoles:
    """由一组关键色生成配色方案，未指定的角色由主色派生。"""
    palette = CorePalette.from_colors(
        primary,
        secondary=secondary,
        tertiary=tertiary,
        neutral=neutral,
        neutral_variant=neutral_variant,
        error=error,
    )
    return from_palette(palette, is_dark=is_dark, contrast_level=contrast_level)
