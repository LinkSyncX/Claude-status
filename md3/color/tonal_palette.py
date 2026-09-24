"""色调板：色相与色度固定、色调可变的一组颜色。"""

from __future__ import annotations

from md3.color import hct as hct_module
from md3.color import utils


class TonalPalette:
    """按色调取色的调色板，结果带缓存。"""

    def __init__(
        self,
        hue: float,
        chroma: float,
        key_color: hct_module.Hct | None = None,
    ) -> None:
        self._hue = hue
        self._chroma = chroma
        self._key_color = key_color
        self._cache: dict[float, int] = {}

    @classmethod
    def from_int(cls, argb: int) -> TonalPalette:
        """使用颜色的色相与色度构造调色板。"""
        return cls.from_hct(hct_module.Hct.from_int(argb))

    @classmethod
    def from_hct(cls, hct: hct_module.Hct) -> TonalPalette:
        """使用 HCT 颜色的色相与色度构造调色板。"""
        return cls(hct.hue, hct.chroma, hct)

    @classmethod
    def from_hue_and_chroma(cls, hue: float, chroma: float) -> TonalPalette:
        """由色相与色度构造调色板。"""
        return cls(hue, chroma)

    @property
    def hue(self) -> float:
        """色相。"""
        return self._hue

    @property
    def chroma(self) -> float:
        """色度。"""
        return self._chroma

    @property
    def key_color(self) -> hct_module.Hct:
        """代表本调色板色相与色度的关键色（从 T50 附近搜索）。"""
        if self._key_color is None:
            self._key_color = _KeyColor(self._hue, self._chroma).create()
        return self._key_color

    def tone(self, tone: float) -> int:
        """返回指定色调（0–100）的 ARGB 颜色。"""
        argb = self._cache.get(tone)
        if argb is None:
            if tone == 99 and hct_module.Hct.is_yellow(self._hue):
                argb = _average_argb(self.tone(98), self.tone(100))
            else:
                argb = hct_module.Hct.from_hct(
                    self._hue, self._chroma, tone
                ).to_int()
            self._cache[tone] = argb
        return argb

    def get_hct(self, tone: float) -> hct_module.Hct:
        """返回指定色调的 HCT 颜色。"""
        return hct_module.Hct.from_int(self.tone(tone))

    def __repr__(self) -> str:
        return f"TonalPalette(hue={self._hue:.1f}, chroma={self._chroma:.1f})"


def _average_argb(argb1: int, argb2: int) -> int:
    red = utils.round_half_up(
        (((argb1 >> 16) & 0xFF) + ((argb2 >> 16) & 0xFF)) / 2
    )
    green = utils.round_half_up(
        (((argb1 >> 8) & 0xFF) + ((argb2 >> 8) & 0xFF)) / 2
    )
    blue = utils.round_half_up(((argb1 & 0xFF) + (argb2 & 0xFF)) / 2)
    return utils.argb_from_rgb(red, green, blue)


class _KeyColor:
    """在色调轴上搜索能达到请求色度、且最接近 T50 的颜色。"""

    _MAX_CHROMA_VALUE = 200.0

    def __init__(self, hue: float, requested_chroma: float) -> None:
        self._hue = hue
        self._requested_chroma = requested_chroma
        self._chroma_cache: dict[int, float] = {}

    def create(self) -> hct_module.Hct:
        """二分搜索满足条件的色调并返回对应颜色。"""
        pivot_tone = 50
        tone_step_size = 1
        epsilon = 0.01
        lower_tone = 0
        upper_tone = 100
        while lower_tone < upper_tone:
            mid_tone = (lower_tone + upper_tone) // 2
            is_ascending = self._max_chroma(mid_tone) < self._max_chroma(
                mid_tone + tone_step_size
            )
            sufficient_chroma = (
                self._max_chroma(mid_tone) >= self._requested_chroma - epsilon
            )
            if sufficient_chroma:
                if abs(lower_tone - pivot_tone) < abs(upper_tone - pivot_tone):
                    upper_tone = mid_tone
                else:
                    if lower_tone == mid_tone:
                        return hct_module.Hct.from_hct(
                            self._hue, self._requested_chroma, lower_tone
                        )
                    lower_tone = mid_tone
            elif is_ascending:
                lower_tone = mid_tone + tone_step_size
            else:
                upper_tone = mid_tone
        return hct_module.Hct.from_hct(
            self._hue, self._requested_chroma, lower_tone
        )

    def _max_chroma(self, tone: int) -> float:
        chroma = self._chroma_cache.get(tone)
        if chroma is None:
            chroma = hct_module.Hct.from_hct(
                self._hue, self._MAX_CHROMA_VALUE, tone
            ).chroma
            self._chroma_cache[tone] = chroma
        return chroma
