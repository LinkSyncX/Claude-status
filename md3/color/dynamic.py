"""随对比度等级动态调整色调。

移植 material-color-utilities 的 ``DynamicColor`` 算法（2021 版色彩规范）：
每个色彩角色带有基准色调、所依赖的背景角色与一条对比度曲线
``ContrastCurve(low, normal, medium, high)``。标准对比度下基准色调本就满足
曲线要求，因此结果与静态色调表一致；提高对比度等级时，前景角色会向
更亮或更暗的方向移动直至满足要求，强调色与其容器之间还通过
``ToneDeltaPair`` 保持至少 10 的色调差。
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Literal

from md3.color import contrast

HIGHEST_SURFACE = "highest_surface"
Polarity = Literal["nearer", "farther", "lighter", "darker"]


class ContrastLevel(float, enum.Enum):
    """对比度等级，取值即 material-color-utilities 的 ``contrastLevel``。"""

    STANDARD = 0.0
    MEDIUM = 0.5
    HIGH = 1.0


def coerce_level(level: ContrastLevel | float) -> float:
    """把等级枚举或数值统一为 -1.0～1.0 的浮点数。"""
    value = float(level)
    return max(-1.0, min(1.0, value))


@dataclasses.dataclass(frozen=True)
class ContrastCurve:
    """不同对比度等级下要求的对比度。

    Attributes:
        low: 等级 -1.0（降低对比度）时的要求。
        normal: 等级 0.0（标准）时的要求。
        medium: 等级 0.5 时的要求。
        high: 等级 1.0 时的要求。
    """

    low: float
    normal: float
    medium: float
    high: float

    def get(self, level: float) -> float:
        """按等级线性插值出要求的对比度。"""
        if level <= -1.0:
            return self.low
        if level < 0.0:
            return _lerp(self.low, self.normal, (level + 1.0) / 1.0)
        if level < 0.5:
            return _lerp(self.normal, self.medium, level / 0.5)
        if level < 1.0:
            return _lerp(self.medium, self.high, (level - 0.5) / 0.5)
        return self.high


@dataclasses.dataclass(frozen=True)
class ToneDeltaPair:
    """两个角色之间需要保持的色调差。

    Attributes:
        role_a: 角色 A。
        role_b: 角色 B。
        delta: 至少保持的色调差。
        polarity: 哪个角色更接近背景：``nearer`` / ``farther`` 指 A，
            ``lighter`` / ``darker`` 依明暗模式决定。
        stay_together: 调整时两者是否一起移动。
    """

    role_a: str
    role_b: str
    delta: float
    polarity: Polarity
    stay_together: bool


@dataclasses.dataclass(frozen=True)
class RoleSpec:
    """一个色彩角色的取色规则。

    Attributes:
        palette: 调色板名称。
        light: 亮色基准色调。
        dark: 暗色基准色调。
        background: 背景角色名，``highest_surface`` 表示最亮的表面。
        second_background: 第二背景角色名（fixed 系列的文字）。
        curve: 相对背景的对比度曲线。
        is_background: 是否为背景角色（避开 50–59 的“尴尬区间”）。
        pair: 与另一角色保持的色调差。
        monochrome: 单色变体下的 (亮, 暗) 基准色调。
    """

    palette: str
    light: float
    dark: float
    background: str | None = None
    second_background: str | None = None
    curve: ContrastCurve | None = None
    is_background: bool = False
    pair: ToneDeltaPair | None = None
    monochrome: tuple[float, float] | None = None


ACCENT = ContrastCurve(3, 4.5, 7, 7)
ON_ACCENT = ContrastCurve(4.5, 7, 11, 21)
CONTAINER = ContrastCurve(1, 1, 3, 4.5)
ON_CONTAINER = ContrastCurve(3, 4.5, 7, 11)
_OUTLINE = ContrastCurve(1.5, 3, 4.5, 7)
_ON_BACKGROUND = ContrastCurve(3, 3, 4.5, 7)


def _accent_family(
    name: str,
    monochrome: dict[str, tuple[float, float]],
) -> dict[str, RoleSpec]:
    container = f"{name}_container"
    pair = ToneDeltaPair(container, name, 10, "nearer", False)
    return {
        name: RoleSpec(
            name,
            40,
            80,
            HIGHEST_SURFACE,
            None,
            ACCENT,
            True,
            pair,
            monochrome.get(name),
        ),
        f"on_{name}": RoleSpec(
            name,
            100,
            20,
            name,
            None,
            ON_ACCENT,
            False,
            None,
            monochrome.get(f"on_{name}"),
        ),
        container: RoleSpec(
            name,
            90,
            30,
            HIGHEST_SURFACE,
            None,
            CONTAINER,
            True,
            pair,
            monochrome.get(container),
        ),
        f"on_{container}": RoleSpec(
            name,
            30,
            90,
            container,
            None,
            ON_CONTAINER,
            False,
            None,
            monochrome.get(f"on_{container}"),
        ),
    }


def _fixed_family(
    name: str, monochrome: dict[str, tuple[float, float]]
) -> dict[str, RoleSpec]:
    fixed = f"{name}_fixed"
    dim = f"{name}_fixed_dim"
    pair = ToneDeltaPair(fixed, dim, 10, "lighter", True)
    return {
        fixed: RoleSpec(
            name,
            90,
            90,
            HIGHEST_SURFACE,
            None,
            CONTAINER,
            True,
            pair,
            monochrome.get(fixed),
        ),
        dim: RoleSpec(
            name,
            80,
            80,
            HIGHEST_SURFACE,
            None,
            CONTAINER,
            True,
            pair,
            monochrome.get(dim),
        ),
        f"on_{fixed}": RoleSpec(
            name,
            10,
            10,
            dim,
            fixed,
            ON_ACCENT,
            False,
            None,
            monochrome.get(f"on_{fixed}"),
        ),
        f"on_{fixed}_variant": RoleSpec(
            name,
            30,
            30,
            dim,
            fixed,
            ON_CONTAINER,
            False,
            None,
            monochrome.get(f"on_{fixed}_variant"),
        ),
    }


_MONOCHROME: dict[str, tuple[float, float]] = {
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

SPECS: dict[str, RoleSpec] = {
    "background": RoleSpec("neutral", 98, 6, is_background=True),
    "on_background": RoleSpec(
        "neutral", 10, 90, "background", curve=_ON_BACKGROUND
    ),
    "surface": RoleSpec("neutral", 98, 6, is_background=True),
    "surface_dim": RoleSpec("neutral", 87, 6, is_background=True),
    "surface_bright": RoleSpec("neutral", 98, 24, is_background=True),
    "surface_container_lowest": RoleSpec("neutral", 100, 4, is_background=True),
    "surface_container_low": RoleSpec("neutral", 96, 10, is_background=True),
    "surface_container": RoleSpec("neutral", 94, 12, is_background=True),
    "surface_container_high": RoleSpec("neutral", 92, 17, is_background=True),
    "surface_container_highest": RoleSpec(
        "neutral", 90, 22, is_background=True
    ),
    "on_surface": RoleSpec("neutral", 10, 90, HIGHEST_SURFACE, curve=ON_ACCENT),
    "surface_variant": RoleSpec("neutral_variant", 90, 30, is_background=True),
    "on_surface_variant": RoleSpec(
        "neutral_variant", 30, 80, HIGHEST_SURFACE, curve=ON_CONTAINER
    ),
    "inverse_surface": RoleSpec("neutral", 20, 90),
    "inverse_on_surface": RoleSpec(
        "neutral", 95, 20, "inverse_surface", curve=ON_ACCENT
    ),
    "outline": RoleSpec(
        "neutral_variant", 50, 60, HIGHEST_SURFACE, curve=_OUTLINE
    ),
    "outline_variant": RoleSpec(
        "neutral_variant", 80, 30, HIGHEST_SURFACE, curve=CONTAINER
    ),
    "shadow": RoleSpec("neutral", 0, 0),
    "scrim": RoleSpec("neutral", 0, 0),
    "surface_tint": RoleSpec("primary", 40, 80, is_background=True),
    "inverse_primary": RoleSpec(
        "primary", 80, 40, "inverse_surface", curve=ACCENT
    ),
    **_accent_family("primary", _MONOCHROME),
    **_accent_family("secondary", _MONOCHROME),
    **_accent_family("tertiary", _MONOCHROME),
    **_accent_family("error", _MONOCHROME),
    **_fixed_family("primary", _MONOCHROME),
    **_fixed_family("secondary", _MONOCHROME),
    **_fixed_family("tertiary", _MONOCHROME),
}


def tone_prefers_light_foreground(tone: float) -> bool:
    """色调低于 60 时更适合浅色前景。"""
    return round(tone) < 60


def tone_allows_light_foreground(tone: float) -> bool:
    """色调不超过 49 时浅色前景可达到 4.5 对比度。"""
    return round(tone) <= 49


def foreground_tone(bg_tone: float, ratio: float) -> float:
    """返回相对背景满足对比度的前景色调，优先与背景明暗相反。"""
    lighter_tone = contrast.lighter_unsafe(bg_tone, ratio)
    darker_tone = contrast.darker_unsafe(bg_tone, ratio)
    lighter_ratio = contrast.ratio_of_tones(lighter_tone, bg_tone)
    darker_ratio = contrast.ratio_of_tones(darker_tone, bg_tone)
    if tone_prefers_light_foreground(bg_tone):
        negligible = (
            abs(lighter_ratio - darker_ratio) < 0.1
            and lighter_ratio < ratio
            and darker_ratio < ratio
        )
        if (
            lighter_ratio >= ratio
            or lighter_ratio >= darker_ratio
            or negligible
        ):
            return lighter_tone
        return darker_tone
    if darker_ratio >= ratio or darker_ratio >= lighter_ratio:
        return darker_tone
    return lighter_tone


class ToneResolver:
    """按对比度等级解析全部角色的色调（带缓存）。

    Args:
        is_dark: 是否为暗色方案。
        monochrome: 是否使用单色变体的基准色调。
        level: 对比度等级（-1.0～1.0）。
    """

    def __init__(
        self,
        is_dark: bool,
        monochrome: bool = False,
        level: ContrastLevel | float = ContrastLevel.STANDARD,
    ) -> None:
        self._is_dark = is_dark
        self._monochrome = monochrome
        self._level = coerce_level(level)
        self._cache: dict[str, float] = {}

    @property
    def level(self) -> float:
        """对比度等级。"""
        return self._level

    def base_tone(self, spec: RoleSpec) -> float:
        """未经对比度调整的基准色调。"""
        if self._monochrome and spec.monochrome is not None:
            return spec.monochrome[1 if self._is_dark else 0]
        return spec.dark if self._is_dark else spec.light

    def resolve(self) -> dict[str, float]:
        """解析全部角色。"""
        return {role: self.tone(role) for role in SPECS}

    def tone(self, role: str) -> float:
        """解析单个角色的色调。"""
        if role == HIGHEST_SURFACE:
            role = "surface_bright" if self._is_dark else "surface_dim"
        cached = self._cache.get(role)
        if cached is not None:
            return cached
        spec = SPECS[role]
        if spec.pair is not None:
            value = self._pair_tone(role, spec)
        elif spec.background is None:
            value = self.base_tone(spec)
        else:
            value = self._contrast_tone(spec)
        self._cache[role] = value
        return value

    def _contrast_tone(self, spec: RoleSpec) -> float:
        assert spec.background is not None and spec.curve is not None
        bg_tone = self.tone(spec.background)
        desired = spec.curve.get(self._level)
        answer = self.base_tone(spec)
        if contrast.ratio_of_tones(bg_tone, answer) < desired:
            answer = foreground_tone(bg_tone, desired)
        if self._level < 0:
            answer = foreground_tone(bg_tone, desired)
        if spec.is_background and 50 <= answer < 60:
            answer = (
                49.0
                if contrast.ratio_of_tones(49, bg_tone) >= desired
                else 60.0
            )
        if spec.second_background is None:
            return answer
        return self._dual_background_tone(spec, answer, desired)

    def _dual_background_tone(
        self, spec: RoleSpec, answer: float, desired: float
    ) -> float:
        assert spec.background is not None
        assert spec.second_background is not None
        bg1 = self.tone(spec.background)
        bg2 = self.tone(spec.second_background)
        upper, lower = max(bg1, bg2), min(bg1, bg2)
        if (
            contrast.ratio_of_tones(upper, answer) >= desired
            and contrast.ratio_of_tones(lower, answer) >= desired
        ):
            return answer
        light_option = contrast.lighter(upper, desired)
        dark_option = contrast.darker(lower, desired)
        available = [o for o in (light_option, dark_option) if o >= 0]
        prefers_light = tone_prefers_light_foreground(
            bg1
        ) or tone_prefers_light_foreground(bg2)
        if prefers_light:
            return 100.0 if light_option < 0 else light_option
        if len(available) == 1:
            return available[0]
        return 0.0 if dark_option < 0 else dark_option

    def _pair_tone(self, role: str, spec: RoleSpec) -> float:
        pair = spec.pair
        assert pair is not None and spec.background is not None
        bg_tone = self.tone(spec.background)
        a_is_nearer = (
            pair.polarity == "nearer"
            or (pair.polarity == "lighter" and not self._is_dark)
            or (pair.polarity == "darker" and self._is_dark)
        )
        nearer, farther = (
            (pair.role_a, pair.role_b)
            if a_is_nearer
            else (pair.role_b, pair.role_a)
        )
        n_spec, f_spec = SPECS[nearer], SPECS[farther]
        assert n_spec.curve is not None and f_spec.curve is not None
        expansion = 1.0 if self._is_dark else -1.0
        delta = pair.delta
        n_contrast = n_spec.curve.get(self._level)
        f_contrast = f_spec.curve.get(self._level)
        n_tone = self._satisfying_tone(
            bg_tone, self.base_tone(n_spec), n_contrast
        )
        f_tone = self._satisfying_tone(
            bg_tone, self.base_tone(f_spec), f_contrast
        )
        if self._level < 0:
            n_tone = foreground_tone(bg_tone, n_contrast)
            f_tone = foreground_tone(bg_tone, f_contrast)
        if (f_tone - n_tone) * expansion < delta:
            f_tone = _clamp(n_tone + delta * expansion)
            if (f_tone - n_tone) * expansion < delta:
                n_tone = _clamp(f_tone - delta * expansion)
        if 50 <= n_tone < 60:
            n_tone, f_tone = _leave_awkward_zone(
                n_tone, f_tone, delta, expansion
            )
        elif 50 <= f_tone < 60:
            if pair.stay_together:
                n_tone, f_tone = _leave_awkward_zone(
                    n_tone, f_tone, delta, expansion
                )
            else:
                f_tone = 60.0 if expansion > 0 else 49.0
        return n_tone if role == nearer else f_tone

    @staticmethod
    def _satisfying_tone(bg_tone: float, initial: float, ratio: float) -> float:
        if contrast.ratio_of_tones(bg_tone, initial) >= ratio:
            return initial
        return foreground_tone(bg_tone, ratio)


def _leave_awkward_zone(
    n_tone: float, f_tone: float, delta: float, expansion: float
) -> tuple[float, float]:
    if expansion > 0:
        n_tone = 60.0
        f_tone = max(f_tone, n_tone + delta * expansion)
    else:
        n_tone = 49.0
        f_tone = min(f_tone, n_tone + delta * expansion)
    return n_tone, f_tone


def resolve_tones(
    is_dark: bool,
    monochrome: bool = False,
    level: ContrastLevel | float = ContrastLevel.STANDARD,
) -> dict[str, float]:
    """解析给定模式与对比度等级下全部角色的色调。"""
    return ToneResolver(is_dark, monochrome, level).resolve()


def _lerp(start: float, stop: float, amount: float) -> float:
    return start + (stop - start) * amount


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
