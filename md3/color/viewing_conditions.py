"""CAM16 观察条件。

颜色的外观不仅取决于其 sRGB 值，还取决于观察环境（环境亮度、背景明度、
周围光照等）。本模块缓存仅依赖观察条件的中间量以加速 CAM16 转换。
"""

from __future__ import annotations

import dataclasses
import math

from md3.color import utils


@dataclasses.dataclass(frozen=True)
class ViewingConditions:
    """一组观察条件及其派生的 CAM16 中间量。

    字段名沿用 CAM16 规范中的缩写，具体含义可参考 Fairchild 的
    《Color Appearance Models》。
    """

    n: float
    aw: float
    nbb: float
    ncb: float
    c: float
    nc: float
    rgb_d: tuple[float, float, float]
    fl: float
    fl_root: float
    z: float

    @classmethod
    def make(
        cls,
        white_point: tuple[float, float, float] | None = None,
        adapting_luminance: float | None = None,
        background_lstar: float = 50.0,
        surround: float = 2.0,
        discounting_illuminant: bool = False,
    ) -> ViewingConditions:
        """由物理意义明确的参数构造观察条件。

        Args:
            white_point: XYZ 空间中的白点，默认 D65。
            adapting_luminance: 适应场亮度（cd/m²），默认约 200 lux。
            background_lstar: 颜色周围区域的 L*，默认 50。
            surround: 周围光照，0 为全暗、1 为昏暗、2 为与色块一致。
            discounting_illuminant: 视觉系统是否忽略环境光的色偏。
        """
        if white_point is None:
            white_point = utils.white_point_d65()
        if adapting_luminance is None:
            adapting_luminance = (
                (200.0 / math.pi) * utils.y_from_lstar(50.0) / 100.0
            )
        xyz = white_point
        r_w = xyz[0] * 0.401288 + xyz[1] * 0.650173 + xyz[2] * -0.051461
        g_w = xyz[0] * -0.250268 + xyz[1] * 1.204414 + xyz[2] * 0.045854
        b_w = xyz[0] * -0.002079 + xyz[1] * 0.048952 + xyz[2] * 0.953127
        f = 0.8 + surround / 10.0
        if f >= 0.9:
            c = utils.lerp(0.59, 0.69, (f - 0.9) * 10.0)
        else:
            c = utils.lerp(0.525, 0.59, (f - 0.8) * 10.0)
        if discounting_illuminant:
            d = 1.0
        else:
            d = f * (
                1.0
                - (1.0 / 3.6) * math.exp((-adapting_luminance - 42.0) / 92.0)
            )
        d = utils.clamp_double(0.0, 1.0, d)
        nc = f
        rgb_d = (
            d * (100.0 / r_w) + 1.0 - d,
            d * (100.0 / g_w) + 1.0 - d,
            d * (100.0 / b_w) + 1.0 - d,
        )
        k = 1.0 / (5.0 * adapting_luminance + 1.0)
        k4 = k * k * k * k
        k4f = 1.0 - k4
        fl = k4 * adapting_luminance + 0.1 * k4f * k4f * math.cbrt(
            5.0 * adapting_luminance
        )
        n = utils.y_from_lstar(background_lstar) / white_point[1]
        z = 1.48 + math.sqrt(n)
        nbb = 0.725 / math.pow(n, 0.2)
        ncb = nbb
        rgb_a_factors = (
            math.pow((fl * rgb_d[0] * r_w) / 100.0, 0.42),
            math.pow((fl * rgb_d[1] * g_w) / 100.0, 0.42),
            math.pow((fl * rgb_d[2] * b_w) / 100.0, 0.42),
        )
        rgb_a = tuple(
            (400.0 * factor) / (factor + 27.13) for factor in rgb_a_factors
        )
        aw = (2.0 * rgb_a[0] + rgb_a[1] + 0.05 * rgb_a[2]) * nbb
        return cls(
            n=n,
            aw=aw,
            nbb=nbb,
            ncb=ncb,
            c=c,
            nc=nc,
            rgb_d=rgb_d,
            fl=fl,
            fl_root=math.pow(fl, 0.25),
            z=z,
        )


# 与 sRGB 标准接近的默认观察条件。
DEFAULT = ViewingConditions.make()
