"""核心色板：由种子色派生的六组色调板。"""

from __future__ import annotations

import dataclasses

from md3.color import hct as hct_module
from md3.color import tonal_palette
from md3.color import utils
from md3.color import variant as variant_module

_TonalPalette = tonal_palette.TonalPalette

# Expressive / Vibrant 变体的色相分段与旋转量。
_EXPRESSIVE_BREAKPOINTS = (0, 21, 51, 121, 151, 191, 271, 321, 360)
_EXPRESSIVE_SECONDARY_ROTATIONS = (45, 95, 45, 20, 45, 90, 45, 45, 45)
_EXPRESSIVE_TERTIARY_ROTATIONS = (120, 120, 20, 45, 20, 15, 20, 120, 120)
_VIBRANT_BREAKPOINTS = (0, 41, 61, 101, 131, 181, 251, 301, 360)
_VIBRANT_SECONDARY_ROTATIONS = (18, 15, 10, 12, 15, 18, 15, 12, 12)
_VIBRANT_TERTIARY_ROTATIONS = (35, 30, 20, 25, 30, 35, 30, 25, 25)


@dataclasses.dataclass(frozen=True)
class CorePalette:
    """主题的六组色调板。

    Attributes:
        primary: 主色调色板。
        secondary: 次要色调色板。
        tertiary: 第三色调色板。
        neutral: 中性色调色板（表面、背景）。
        neutral_variant: 中性变体调色板（轮廓、表面变体）。
        error: 错误色调色板。
    """

    primary: _TonalPalette
    secondary: _TonalPalette
    tertiary: _TonalPalette
    neutral: _TonalPalette
    neutral_variant: _TonalPalette
    error: _TonalPalette

    @classmethod
    def of(cls, argb: int) -> CorePalette:
        """基线算法：主色色度不低于 48，其余取固定色度。"""
        return cls.from_seed(argb, variant_module.Variant.BASELINE)

    @classmethod
    def content_of(cls, argb: int) -> CorePalette:
        """内容算法：各调色板色度随种子色变化，适合图片主题。"""
        return cls.from_seed(argb, variant_module.Variant.CONTENT)

    @classmethod
    def from_seed(
        cls,
        argb: int,
        variant: variant_module.Variant = variant_module.Variant.BASELINE,
    ) -> CorePalette:
        """按指定变体由种子色生成核心色板。

        Args:
            argb: 种子色。
            variant: 配色变体。
        """
        seed = hct_module.Hct.from_int(argb)
        return cls.from_hct(seed, variant)

    @classmethod
    def from_hct(
        cls,
        seed: hct_module.Hct,
        variant: variant_module.Variant = variant_module.Variant.BASELINE,
    ) -> CorePalette:
        """按指定变体由 HCT 种子色生成核心色板。"""
        hue = seed.hue
        chroma = seed.chroma
        error = _TonalPalette.from_hue_and_chroma(25.0, 84.0)
        palette = _TonalPalette.from_hue_and_chroma
        rotate = utils.sanitize_degrees_double
        match variant:
            case variant_module.Variant.BASELINE:
                return cls(
                    primary=palette(hue, max(48.0, chroma)),
                    secondary=palette(hue, 16.0),
                    tertiary=palette(rotate(hue + 60.0), 24.0),
                    neutral=palette(hue, 4.0),
                    neutral_variant=palette(hue, 8.0),
                    error=error,
                )
            case variant_module.Variant.CONTENT:
                return cls(
                    primary=palette(hue, chroma),
                    secondary=palette(hue, max(chroma - 32.0, chroma * 0.5)),
                    tertiary=palette(rotate(hue + 60.0), chroma / 2),
                    neutral=palette(hue, chroma / 8.0),
                    neutral_variant=palette(hue, chroma / 8.0 + 4.0),
                    error=error,
                )
            case variant_module.Variant.TONAL_SPOT:
                return cls(
                    primary=palette(hue, 36.0),
                    secondary=palette(hue, 16.0),
                    tertiary=palette(rotate(hue + 60.0), 24.0),
                    neutral=palette(hue, 6.0),
                    neutral_variant=palette(hue, 8.0),
                    error=error,
                )
            case variant_module.Variant.VIBRANT:
                return cls(
                    primary=palette(hue, 200.0),
                    secondary=palette(
                        _rotated_hue(
                            hue,
                            _VIBRANT_BREAKPOINTS,
                            _VIBRANT_SECONDARY_ROTATIONS,
                        ),
                        24.0,
                    ),
                    tertiary=palette(
                        _rotated_hue(
                            hue,
                            _VIBRANT_BREAKPOINTS,
                            _VIBRANT_TERTIARY_ROTATIONS,
                        ),
                        32.0,
                    ),
                    neutral=palette(hue, 10.0),
                    neutral_variant=palette(hue, 12.0),
                    error=error,
                )
            case variant_module.Variant.EXPRESSIVE:
                return cls(
                    primary=palette(rotate(hue + 240.0), 40.0),
                    secondary=palette(
                        _rotated_hue(
                            hue,
                            _EXPRESSIVE_BREAKPOINTS,
                            _EXPRESSIVE_SECONDARY_ROTATIONS,
                        ),
                        24.0,
                    ),
                    tertiary=palette(
                        _rotated_hue(
                            hue,
                            _EXPRESSIVE_BREAKPOINTS,
                            _EXPRESSIVE_TERTIARY_ROTATIONS,
                        ),
                        32.0,
                    ),
                    neutral=palette(rotate(hue + 15.0), 8.0),
                    neutral_variant=palette(rotate(hue + 15.0), 12.0),
                    error=error,
                )
            case variant_module.Variant.NEUTRAL:
                return cls(
                    primary=palette(hue, 12.0),
                    secondary=palette(hue, 8.0),
                    tertiary=palette(hue, 16.0),
                    neutral=palette(hue, 2.0),
                    neutral_variant=palette(hue, 2.0),
                    error=error,
                )
            case variant_module.Variant.MONOCHROME:
                return cls(
                    primary=palette(hue, 0.0),
                    secondary=palette(hue, 0.0),
                    tertiary=palette(hue, 0.0),
                    neutral=palette(hue, 0.0),
                    neutral_variant=palette(hue, 0.0),
                    error=error,
                )
            case variant_module.Variant.FRUIT_SALAD:
                return cls(
                    primary=palette(rotate(hue - 50.0), 48.0),
                    secondary=palette(rotate(hue - 50.0), 36.0),
                    tertiary=palette(hue, 36.0),
                    neutral=palette(hue, 10.0),
                    neutral_variant=palette(hue, 16.0),
                    error=error,
                )
            case variant_module.Variant.RAINBOW:
                return cls(
                    primary=palette(hue, 48.0),
                    secondary=palette(hue, 16.0),
                    tertiary=palette(rotate(hue + 60.0), 24.0),
                    neutral=palette(hue, 0.0),
                    neutral_variant=palette(hue, 0.0),
                    error=error,
                )
        raise ValueError(f"不支持的配色变体: {variant!r}")

    @classmethod
    def from_colors(
        cls,
        primary: int,
        secondary: int | None = None,
        tertiary: int | None = None,
        neutral: int | None = None,
        neutral_variant: int | None = None,
        error: int | None = None,
        content: bool = False,
    ) -> CorePalette:
        """由一组关键色分别指定各调色板。

        未指定的调色板由主色按基线（或内容）算法派生。

        Args:
            primary: 主色种子。
            secondary: 次要色种子。
            tertiary: 第三色种子。
            neutral: 中性色种子。
            neutral_variant: 中性变体种子。
            error: 错误色种子。
            content: 为真时使用内容算法。
        """
        variant = (
            variant_module.Variant.CONTENT
            if content
            else variant_module.Variant.BASELINE
        )
        base = cls.from_seed(primary, variant)
        overrides: dict[str, _TonalPalette] = {}
        if secondary is not None:
            overrides["secondary"] = cls.from_seed(secondary, variant).primary
        if tertiary is not None:
            overrides["tertiary"] = cls.from_seed(tertiary, variant).primary
        if error is not None:
            overrides["error"] = cls.from_seed(error, variant).primary
        if neutral is not None:
            overrides["neutral"] = cls.from_seed(neutral, variant).neutral
        if neutral_variant is not None:
            overrides["neutral_variant"] = cls.from_seed(
                neutral_variant, variant
            ).neutral_variant
        return dataclasses.replace(base, **overrides)


def _rotated_hue(
    hue: float,
    breakpoints: tuple[int, ...],
    rotations: tuple[int, ...],
) -> float:
    """按色相所在分段施加旋转量。"""
    size = min(len(breakpoints) - 1, len(rotations))
    for i in range(size):
        if breakpoints[i] <= hue < breakpoints[i + 1]:
            return utils.sanitize_degrees_double(hue + rotations[i])
    return hue
