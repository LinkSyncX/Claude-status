"""对比度计算。

对比度由 XYZ 的 Y 计算；Y 线性化后即 HCT 的色调（L*）。以下函数均以
色调为参数。
"""

from __future__ import annotations

from md3.color import utils


def ratio_of_tones(tone_a: float, tone_b: float) -> float:
    """两个色调之间的对比度（1–21）。"""
    tone_a = utils.clamp_double(0.0, 100.0, tone_a)
    tone_b = utils.clamp_double(0.0, 100.0, tone_b)
    return ratio_of_ys(utils.y_from_lstar(tone_a), utils.y_from_lstar(tone_b))


def ratio_of_ys(y1: float, y2: float) -> float:
    """两个相对亮度之间的对比度。"""
    light_y = y1 if y1 > y2 else y2
    dark_y = y1 if light_y == y2 else y2
    return (light_y + 5.0) / (dark_y + 5.0)


def ratio_of_argbs(argb_a: int, argb_b: int) -> float:
    """两个 ARGB 颜色之间的对比度。"""
    return ratio_of_ys(
        utils.xyz_from_argb(argb_a)[1], utils.xyz_from_argb(argb_b)[1]
    )


def lighter(tone: float, ratio: float) -> float:
    """返回比 tone 更亮且满足对比度的色调，无法满足时返回 -1。"""
    if tone < 0.0 or tone > 100.0:
        return -1.0
    dark_y = utils.y_from_lstar(tone)
    light_y = ratio * (dark_y + 5.0) - 5.0
    real_contrast = ratio_of_ys(light_y, dark_y)
    delta = abs(real_contrast - ratio)
    if real_contrast < ratio and delta > 0.04:
        return -1.0
    # 略微提亮，保证色域映射后仍满足对比度。
    value = utils.lstar_from_y(light_y) + 0.4
    if value < 0 or value > 100:
        return -1.0
    return value


def darker(tone: float, ratio: float) -> float:
    """返回比 tone 更暗且满足对比度的色调，无法满足时返回 -1。"""
    if tone < 0.0 or tone > 100.0:
        return -1.0
    light_y = utils.y_from_lstar(tone)
    dark_y = ((light_y + 5.0) / ratio) - 5.0
    real_contrast = ratio_of_ys(light_y, dark_y)
    delta = abs(real_contrast - ratio)
    if real_contrast < ratio and delta > 0.04:
        return -1.0
    value = utils.lstar_from_y(dark_y) - 0.4
    if value < 0 or value > 100:
        return -1.0
    return value


def lighter_unsafe(tone: float, ratio: float) -> float:
    """同 ``lighter``，但无法满足时返回 100。"""
    value = lighter(tone, ratio)
    return 100.0 if value < 0.0 else value


def darker_unsafe(tone: float, ratio: float) -> float:
    """同 ``darker``，但无法满足时返回 0。"""
    value = darker(tone, ratio)
    return 0.0 if value < 0.0 else value
