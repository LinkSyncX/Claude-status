"""从图片中提取适合作为主题种子的颜色。

量化使用 Pillow（可选依赖），排序使用 material-color-utilities 的
``Score`` 算法：按出现比例与色度打分，过滤灰色与占比过低的色相，并保证
所选颜色之间的色相差足够大。
"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
import os
from typing import Any

from md3.color import hct as hct_module
from md3.color import utils

GOOGLE_BLUE = 0xFF4285F4

_TARGET_CHROMA = 48.0
_WEIGHT_PROPORTION = 0.7
_WEIGHT_CHROMA_ABOVE = 0.3
_WEIGHT_CHROMA_BELOW = 0.1
_CUTOFF_CHROMA = 5.0
_CUTOFF_EXCITED_PROPORTION = 0.01


@dataclasses.dataclass(order=True)
class _Scored:
    score: float
    hct: hct_module.Hct = dataclasses.field(compare=False)


def score(
    colors_to_population: Mapping[int, int],
    desired: int = 4,
    fallback: int = GOOGLE_BLUE,
    filter_unsuitable: bool = True,
) -> list[int]:
    """按适合作为主题色的程度对颜色排序。

    Args:
        colors_to_population: 颜色（ARGB）到出现次数的映射。
        desired: 最多返回的颜色数量。
        fallback: 所有颜色都不合适时返回的兜底色。
        filter_unsuitable: 是否过滤色度过低或占比过低的颜色。

    Returns:
        按适合度降序排列的颜色列表，至少包含一个颜色。
    """
    colors_hct: list[hct_module.Hct] = []
    hue_population = [0.0] * 360
    population_sum = 0.0
    for argb, population in colors_to_population.items():
        hct = hct_module.Hct.from_int(argb)
        colors_hct.append(hct)
        hue_population[int(hct.hue) % 360] += population
        population_sum += population

    hue_excited_proportions = [0.0] * 360
    if population_sum > 0:
        for hue in range(360):
            proportion = hue_population[hue] / population_sum
            for i in range(hue - 14, hue + 16):
                hue_excited_proportions[utils.sanitize_degrees_int(i)] += (
                    proportion
                )

    scored: list[_Scored] = []
    for hct in colors_hct:
        hue = utils.sanitize_degrees_int(utils.round_half_up(hct.hue))
        proportion = hue_excited_proportions[hue]
        if filter_unsuitable and (
            hct.chroma < _CUTOFF_CHROMA
            or proportion <= _CUTOFF_EXCITED_PROPORTION
        ):
            continue
        proportion_score = proportion * 100.0 * _WEIGHT_PROPORTION
        chroma_weight = (
            _WEIGHT_CHROMA_BELOW
            if hct.chroma < _TARGET_CHROMA
            else _WEIGHT_CHROMA_ABOVE
        )
        chroma_score = (hct.chroma - _TARGET_CHROMA) * chroma_weight
        scored.append(_Scored(proportion_score + chroma_score, hct))
    scored.sort(reverse=True)

    chosen: list[hct_module.Hct] = []
    for difference_degrees in range(90, 14, -1):
        chosen = []
        for item in scored:
            duplicate = any(
                utils.difference_degrees(item.hct.hue, other.hue)
                < difference_degrees
                for other in chosen
            )
            if not duplicate:
                chosen.append(item.hct)
            if len(chosen) >= desired:
                break
        if len(chosen) >= desired:
            break

    if not chosen:
        return [fallback]
    return [hct.to_int() for hct in chosen]


def quantize(
    image: Any, max_colors: int = 128, size: int = 112
) -> dict[int, int]:
    """把图片缩小并量化，返回颜色到像素数的映射。

    Args:
        image: ``PIL.Image.Image`` 实例，或图片文件路径。
        max_colors: 量化后的最大颜色数。
        size: 缩放后的最长边像素数，越小越快。

    Raises:
        ImportError: 未安装 Pillow。
    """
    try:
        from PIL import Image  # pylint: disable=import-outside-toplevel
    except ImportError as exc:
        raise ImportError(
            "从图片取色需要安装 Pillow: pip install Pillow"
        ) from exc

    if isinstance(image, str | os.PathLike):
        with Image.open(image) as opened:
            return quantize(opened, max_colors=max_colors, size=size)

    rgb = image.convert("RGB")
    rgb.thumbnail((size, size))
    quantized = rgb.quantize(colors=max_colors, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    result: dict[int, int] = {}
    for count, index in quantized.getcolors(maxcolors=max_colors * 4) or ():
        red, green, blue = palette[index * 3 : index * 3 + 3]
        argb = utils.argb_from_rgb(red, green, blue)
        result[argb] = result.get(argb, 0) + count
    return result


def seed_colors_from_image(
    image: Any, desired: int = 4, fallback: int = GOOGLE_BLUE
) -> list[int]:
    """从图片中提取按适合度排序的候选种子色。"""
    return score(quantize(image), desired=desired, fallback=fallback)


def seed_from_image(image: Any, fallback: int = GOOGLE_BLUE) -> int:
    """从图片中提取最合适的一个种子色。"""
    return seed_colors_from_image(image, desired=1, fallback=fallback)[0]
