"""在 HCT 与 CAM16 空间中混合颜色。"""

from __future__ import annotations

from md3.color import cam16
from md3.color import hct as hct_module
from md3.color import utils


def harmonize(design_color: int, source_color: int) -> int:
    """把设计色的色相向主题色轻微偏移（最多 15 度），保持可辨识。

    Args:
        design_color: 任意设计色，例如品牌色或语义色。
        source_color: 主题的主色。
    """
    from_hct = hct_module.Hct.from_int(design_color)
    to_hct = hct_module.Hct.from_int(source_color)
    difference = utils.difference_degrees(from_hct.hue, to_hct.hue)
    rotation = min(difference * 0.5, 15.0)
    output_hue = utils.sanitize_degrees_double(
        from_hct.hue
        + rotation * utils.rotation_direction(from_hct.hue, to_hct.hue)
    )
    return hct_module.Hct.from_hct(
        output_hue, from_hct.chroma, from_hct.tone
    ).to_int()


def hct_hue(from_argb: int, to_argb: int, amount: float) -> int:
    """只混合色相，保持原色的色度与色调。"""
    ucs = cam16_ucs(from_argb, to_argb, amount)
    ucs_cam = cam16.Cam16.from_int(ucs)
    from_cam = cam16.Cam16.from_int(from_argb)
    return hct_module.Hct.from_hct(
        ucs_cam.hue, from_cam.chroma, utils.lstar_from_argb(from_argb)
    ).to_int()


def cam16_ucs(from_argb: int, to_argb: int, amount: float) -> int:
    """在 CAM16-UCS 空间中线性混合，色相、色度、色调都会变化。"""
    from_cam = cam16.Cam16.from_int(from_argb)
    to_cam = cam16.Cam16.from_int(to_argb)
    jstar = from_cam.jstar + (to_cam.jstar - from_cam.jstar) * amount
    astar = from_cam.astar + (to_cam.astar - from_cam.astar) * amount
    bstar = from_cam.bstar + (to_cam.bstar - from_cam.bstar) * amount
    return cam16.Cam16.from_ucs(jstar, astar, bstar).to_int()


def alpha_composite(foreground: int, background: int) -> int:
    """按 alpha 把前景色叠加到不透明背景色上（sRGB 空间）。"""
    alpha = ((foreground >> 24) & 0xFF) / 255.0
    channels = []
    for shift in (16, 8, 0):
        fg = (foreground >> shift) & 0xFF
        bg = (background >> shift) & 0xFF
        channels.append(utils.round_half_up(fg * alpha + bg * (1 - alpha)))
    return utils.argb_from_rgb(channels[0], channels[1], channels[2])
