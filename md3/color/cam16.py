"""CAM16 色貌模型。

CAM16 用色相、色度、明度等感知维度描述颜色，并附带 CAM16-UCS 坐标
（jstar/astar/bstar）用于度量颜色间距离。
"""

from __future__ import annotations

import dataclasses
import math

from md3.color import utils
from md3.color import viewing_conditions as vc_module
from md3.tokens import color as color_tokens


@dataclasses.dataclass(frozen=True)
class Cam16:
    """一个颜色在特定观察条件下的 CAM16 表示。

    Attributes:
        hue: 色相（0–360）。
        chroma: 色度，感知上准确的饱和度。
        j: 明度。
        q: 亮度。
        m: 彩度。
        s: 饱和度。
        jstar: CAM16-UCS 明度坐标。
        astar: CAM16-UCS a 坐标。
        bstar: CAM16-UCS b 坐标。
    """

    hue: float
    chroma: float
    j: float
    q: float
    m: float
    s: float
    jstar: float
    astar: float
    bstar: float

    def distance(self, other: Cam16) -> float:
        """在 CAM16-UCS 空间中的感知距离。"""
        d_j = self.jstar - other.jstar
        d_a = self.astar - other.astar
        d_b = self.bstar - other.bstar
        d_e_prime = math.sqrt(d_j * d_j + d_a * d_a + d_b * d_b)
        return 1.41 * math.pow(d_e_prime, 0.63)

    @classmethod
    def from_int(cls, argb: int) -> Cam16:
        """在默认观察条件下由 ARGB 构造。"""
        return cls.from_int_in_viewing_conditions(argb, vc_module.DEFAULT)

    @classmethod
    def from_int_in_viewing_conditions(
        cls, argb: int, conditions: vc_module.ViewingConditions
    ) -> Cam16:
        """在给定观察条件下由 ARGB 构造。"""
        red_l = utils.linearized(color_tokens.red_of(argb))
        green_l = utils.linearized(color_tokens.green_of(argb))
        blue_l = utils.linearized(color_tokens.blue_of(argb))
        x = 0.41233895 * red_l + 0.35762064 * green_l + 0.18051042 * blue_l
        y = 0.2126 * red_l + 0.7152 * green_l + 0.0722 * blue_l
        z = 0.01932141 * red_l + 0.11916382 * green_l + 0.95034478 * blue_l
        return cls.from_xyz_in_viewing_conditions(x, y, z, conditions)

    @classmethod
    def from_xyz_in_viewing_conditions(
        cls,
        x: float,
        y: float,
        z: float,
        conditions: vc_module.ViewingConditions,
    ) -> Cam16:
        """在给定观察条件下由 XYZ 构造。"""
        r_c = 0.401288 * x + 0.650173 * y - 0.051461 * z
        g_c = -0.250268 * x + 1.204414 * y + 0.045854 * z
        b_c = -0.002079 * x + 0.048952 * y + 0.953127 * z

        r_d = conditions.rgb_d[0] * r_c
        g_d = conditions.rgb_d[1] * g_c
        b_d = conditions.rgb_d[2] * b_c

        r_af = math.pow(conditions.fl * abs(r_d) / 100.0, 0.42)
        g_af = math.pow(conditions.fl * abs(g_d) / 100.0, 0.42)
        b_af = math.pow(conditions.fl * abs(b_d) / 100.0, 0.42)
        r_a = utils.signum(r_d) * 400.0 * r_af / (r_af + 27.13)
        g_a = utils.signum(g_d) * 400.0 * g_af / (g_af + 27.13)
        b_a = utils.signum(b_d) * 400.0 * b_af / (b_af + 27.13)

        a = (11.0 * r_a + -12.0 * g_a + b_a) / 11.0
        b = (r_a + g_a - 2.0 * b_a) / 9.0
        u = (20.0 * r_a + 20.0 * g_a + 21.0 * b_a) / 20.0
        p2 = (40.0 * r_a + 20.0 * g_a + b_a) / 20.0

        hue = utils.sanitize_degrees_double(math.degrees(math.atan2(b, a)))
        hue_radians = math.radians(hue)

        ac = p2 * conditions.nbb
        j = 100.0 * math.pow(ac / conditions.aw, conditions.c * conditions.z)
        q = (
            (4.0 / conditions.c)
            * math.sqrt(j / 100.0)
            * (conditions.aw + 4.0)
            * conditions.fl_root
        )
        hue_prime = hue + 360 if hue < 20.14 else hue
        e_hue = 0.25 * (math.cos(math.radians(hue_prime) + 2.0) + 3.8)
        p1 = (50000.0 / 13.0) * e_hue * conditions.nc * conditions.ncb
        t = p1 * math.sqrt(a * a + b * b) / (u + 0.305)
        alpha = math.pow(t, 0.9) * math.pow(
            1.64 - math.pow(0.29, conditions.n), 0.73
        )
        chroma = alpha * math.sqrt(j / 100.0)
        m = chroma * conditions.fl_root
        s = 50.0 * math.sqrt((alpha * conditions.c) / (conditions.aw + 4.0))
        jstar = ((1.0 + 100.0 * 0.007) * j) / (1.0 + 0.007 * j)
        mstar = (1.0 / 0.0228) * math.log(1.0 + 0.0228 * m)
        return cls(
            hue=hue,
            chroma=chroma,
            j=j,
            q=q,
            m=m,
            s=s,
            jstar=jstar,
            astar=mstar * math.cos(hue_radians),
            bstar=mstar * math.sin(hue_radians),
        )

    @classmethod
    def from_jch(cls, j: float, c: float, h: float) -> Cam16:
        """在默认观察条件下由明度、色度、色相构造。"""
        return cls.from_jch_in_viewing_conditions(j, c, h, vc_module.DEFAULT)

    @classmethod
    def from_jch_in_viewing_conditions(
        cls,
        j: float,
        c: float,
        h: float,
        conditions: vc_module.ViewingConditions,
    ) -> Cam16:
        """在给定观察条件下由明度、色度、色相构造。"""
        q = (
            (4.0 / conditions.c)
            * math.sqrt(j / 100.0)
            * (conditions.aw + 4.0)
            * conditions.fl_root
        )
        m = c * conditions.fl_root
        alpha = c / math.sqrt(j / 100.0)
        s = 50.0 * math.sqrt((alpha * conditions.c) / (conditions.aw + 4.0))
        hue_radians = math.radians(h)
        jstar = ((1.0 + 100.0 * 0.007) * j) / (1.0 + 0.007 * j)
        mstar = (1.0 / 0.0228) * math.log(1.0 + 0.0228 * m)
        return cls(
            hue=h,
            chroma=c,
            j=j,
            q=q,
            m=m,
            s=s,
            jstar=jstar,
            astar=mstar * math.cos(hue_radians),
            bstar=mstar * math.sin(hue_radians),
        )

    @classmethod
    def from_ucs(cls, jstar: float, astar: float, bstar: float) -> Cam16:
        """在默认观察条件下由 CAM16-UCS 坐标构造。"""
        return cls.from_ucs_in_viewing_conditions(
            jstar, astar, bstar, vc_module.DEFAULT
        )

    @classmethod
    def from_ucs_in_viewing_conditions(
        cls,
        jstar: float,
        astar: float,
        bstar: float,
        conditions: vc_module.ViewingConditions,
    ) -> Cam16:
        """在给定观察条件下由 CAM16-UCS 坐标构造。"""
        m = math.sqrt(astar * astar + bstar * bstar)
        big_m = (math.exp(m * 0.0228) - 1.0) / 0.0228
        c = big_m / conditions.fl_root
        h = math.degrees(math.atan2(bstar, astar))
        if h < 0.0:
            h += 360.0
        j = jstar / (1 - (jstar - 100) * 0.007)
        return cls.from_jch_in_viewing_conditions(j, c, h, conditions)

    def to_int(self) -> int:
        """在默认观察条件下转换为 ARGB。"""
        return self.viewed(vc_module.DEFAULT)

    def viewed(self, conditions: vc_module.ViewingConditions) -> int:
        """在给定观察条件下转换为 ARGB。"""
        x, y, z = self.xyz_in_viewing_conditions(conditions)
        return utils.argb_from_xyz(x, y, z)

    def xyz_in_viewing_conditions(
        self, conditions: vc_module.ViewingConditions
    ) -> tuple[float, float, float]:
        """在给定观察条件下的 XYZ 坐标。"""
        if self.chroma == 0.0 or self.j == 0.0:
            alpha = 0.0
        else:
            alpha = self.chroma / math.sqrt(self.j / 100.0)
        t = math.pow(
            alpha / math.pow(1.64 - math.pow(0.29, conditions.n), 0.73),
            1.0 / 0.9,
        )
        h_rad = math.radians(self.hue)
        e_hue = 0.25 * (math.cos(h_rad + 2.0) + 3.8)
        ac = conditions.aw * math.pow(
            self.j / 100.0, 1.0 / conditions.c / conditions.z
        )
        p1 = e_hue * (50000.0 / 13.0) * conditions.nc * conditions.ncb
        p2 = ac / conditions.nbb

        h_sin = math.sin(h_rad)
        h_cos = math.cos(h_rad)
        gamma = (
            23.0
            * (p2 + 0.305)
            * t
            / (23.0 * p1 + 11.0 * t * h_cos + 108.0 * t * h_sin)
        )
        a = gamma * h_cos
        b = gamma * h_sin
        r_a = (460.0 * p2 + 451.0 * a + 288.0 * b) / 1403.0
        g_a = (460.0 * p2 - 891.0 * a - 261.0 * b) / 1403.0
        b_a = (460.0 * p2 - 220.0 * a - 6300.0 * b) / 1403.0

        r_c = _inverse_adaptation(r_a, conditions.fl)
        g_c = _inverse_adaptation(g_a, conditions.fl)
        b_c = _inverse_adaptation(b_a, conditions.fl)
        r_f = r_c / conditions.rgb_d[0]
        g_f = g_c / conditions.rgb_d[1]
        b_f = b_c / conditions.rgb_d[2]

        x = 1.86206786 * r_f - 1.01125463 * g_f + 0.14918677 * b_f
        y = 0.38752654 * r_f + 0.62144744 * g_f - 0.00897398 * b_f
        z = -0.01584150 * r_f - 0.03412294 * g_f + 1.04996444 * b_f
        return x, y, z


def _inverse_adaptation(adapted: float, fl: float) -> float:
    """色适应的逆变换。"""
    base = max(0.0, (27.13 * abs(adapted)) / (400.0 - abs(adapted)))
    return utils.signum(adapted) * (100.0 / fl) * math.pow(base, 1.0 / 0.42)
