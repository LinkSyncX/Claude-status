"""HCT 色彩空间：色相（Hue）、色度（Chroma）、色调（Tone）。

色相与色度来自 CAM16，色调即 L*a*b* 中的 L*。色调差 40 保证对比度
>= 3.0，色调差 50 保证对比度 >= 4.5，因此可以直接用色调推导无障碍配色。
"""

from __future__ import annotations

from md3.color import cam16
from md3.color import hct_solver
from md3.color import utils
from md3.color import viewing_conditions as vc_module


class Hct:
    """一个 HCT 颜色。

    实例不可变；``with_hue`` 等方法返回调整后的新实例。由于每个色相与
    色调下可达的最大色度不同，实际色度可能低于请求值。
    """

    __slots__ = ("_argb", "_chroma", "_hue", "_tone")

    def __init__(self, argb: int) -> None:
        cam = cam16.Cam16.from_int(argb)
        self._argb = argb & 0xFFFFFFFF
        self._hue = cam.hue
        self._chroma = cam.chroma
        self._tone = utils.lstar_from_argb(argb)

    @classmethod
    def from_hct(cls, hue: float, chroma: float, tone: float) -> Hct:
        """由色相、色度、色调构造，越界值会被修正。"""
        return cls(hct_solver.solve_to_int(hue, chroma, tone))

    @classmethod
    def from_int(cls, argb: int) -> Hct:
        """由 ARGB 构造。"""
        return cls(argb)

    @property
    def hue(self) -> float:
        """色相，0 <= hue < 360。"""
        return self._hue

    @property
    def chroma(self) -> float:
        """色度。"""
        return self._chroma

    @property
    def tone(self) -> float:
        """色调（L*），0–100。"""
        return self._tone

    @property
    def argb(self) -> int:
        """ARGB 整数表示。"""
        return self._argb

    def to_int(self) -> int:
        """ARGB 整数表示。"""
        return self._argb

    def with_hue(self, hue: float) -> Hct:
        """返回替换色相后的新颜色。"""
        return Hct.from_hct(hue, self._chroma, self._tone)

    def with_chroma(self, chroma: float) -> Hct:
        """返回替换色度后的新颜色。"""
        return Hct.from_hct(self._hue, chroma, self._tone)

    def with_tone(self, tone: float) -> Hct:
        """返回替换色调后的新颜色。"""
        return Hct.from_hct(self._hue, self._chroma, tone)

    def in_viewing_conditions(
        self, conditions: vc_module.ViewingConditions
    ) -> Hct:
        """把颜色换算到另一组观察条件下的外观。"""
        cam = cam16.Cam16.from_int(self._argb)
        viewed_xyz = cam.xyz_in_viewing_conditions(conditions)
        recast = cam16.Cam16.from_xyz_in_viewing_conditions(
            viewed_xyz[0], viewed_xyz[1], viewed_xyz[2], vc_module.DEFAULT
        )
        return Hct.from_hct(
            recast.hue, recast.chroma, utils.lstar_from_y(viewed_xyz[1])
        )

    @staticmethod
    def is_blue(hue: float) -> bool:
        """色相是否属于蓝色区间。"""
        return 250 <= hue < 270

    @staticmethod
    def is_yellow(hue: float) -> bool:
        """色相是否属于黄色区间。"""
        return 105 <= hue < 125

    @staticmethod
    def is_cyan(hue: float) -> bool:
        """色相是否属于青色区间。"""
        return 170 <= hue < 207

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Hct):
            return NotImplemented
        return self._argb == other._argb

    def __hash__(self) -> int:
        return hash(self._argb)

    def __repr__(self) -> str:
        return (
            f"Hct(hue={self._hue:.1f}, chroma={self._chroma:.1f}, "
            f"tone={self._tone:.1f}, argb=0x{self._argb:08X})"
        )
