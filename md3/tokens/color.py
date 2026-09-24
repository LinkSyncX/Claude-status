"""系统级色彩角色（md.sys.color）。.

颜色统一使用 32 位 ARGB 整数（``0xAARRGGBB``）表示，与
material-color-utilities 保持一致；需要 Qt 颜色时由主题层转换。
"""

from __future__ import annotations

from collections.abc import Iterator
import dataclasses


@dataclasses.dataclass(frozen=True)
class ColorRoles:
    """一套完整的 M3 色彩角色。.

    字段命名与规范中的令牌一一对应（例如 ``on_primary_container`` 对应
    ``md.sys.color.on-primary-container``）。实例不可变，切换主题时应
    生成新的实例。
    """

    primary: int
    on_primary: int
    primary_container: int
    on_primary_container: int
    secondary: int
    on_secondary: int
    secondary_container: int
    on_secondary_container: int
    tertiary: int
    on_tertiary: int
    tertiary_container: int
    on_tertiary_container: int
    error: int
    on_error: int
    error_container: int
    on_error_container: int
    primary_fixed: int
    primary_fixed_dim: int
    on_primary_fixed: int
    on_primary_fixed_variant: int
    secondary_fixed: int
    secondary_fixed_dim: int
    on_secondary_fixed: int
    on_secondary_fixed_variant: int
    tertiary_fixed: int
    tertiary_fixed_dim: int
    on_tertiary_fixed: int
    on_tertiary_fixed_variant: int
    surface: int
    on_surface: int
    surface_variant: int
    on_surface_variant: int
    surface_dim: int
    surface_bright: int
    surface_container_lowest: int
    surface_container_low: int
    surface_container: int
    surface_container_high: int
    surface_container_highest: int
    surface_tint: int
    inverse_surface: int
    inverse_on_surface: int
    inverse_primary: int
    outline: int
    outline_variant: int
    background: int
    on_background: int
    shadow: int
    scrim: int

    def get(self, role: str) -> int:
        """按角色名读取颜色。.

        Args:
            role: 角色名，支持 ``on_primary`` 或 ``on-primary`` 两种写法。

        Returns:
            ARGB 整数。

        Raises:
            KeyError: 角色名不存在。
        """
        name = role.replace("-", "_")
        if name not in ROLE_NAMES:
            raise KeyError(f"未知的色彩角色: {role!r}")
        return getattr(self, name)

    def items(self) -> Iterator[tuple[str, int]]:
        """按规范顺序迭代 ``(角色名, ARGB)``。."""
        for name in ROLE_NAMES:
            yield name, getattr(self, name)

    def replace(self, **overrides: int) -> ColorRoles:
        """返回覆盖了部分角色的新实例。."""
        return dataclasses.replace(self, **overrides)


ROLE_NAMES: tuple[str, ...] = tuple(
    field.name for field in dataclasses.fields(ColorRoles)
)


def argb_to_hex(argb: int, include_alpha: bool = False) -> str:
    """把 ARGB 整数转换为 ``#RRGGBB`` 或 ``#AARRGGBB`` 字符串。"""
    if include_alpha:
        return f"#{argb & 0xFFFFFFFF:08X}"
    return f"#{argb & 0xFFFFFF:06X}"


def hex_to_argb(text: str) -> int:
    """解析 ``#RGB``、``#RRGGBB`` 或 ``#AARRGGBB`` 字符串为 ARGB 整数。.

    Raises:
        ValueError: 字符串不是合法的颜色表示。
    """
    digits = text.strip().lstrip("#")
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    if len(digits) == 6:
        digits = "FF" + digits
    if len(digits) != 8:
        raise ValueError(f"无法解析颜色: {text!r}")
    try:
        return int(digits, 16)
    except ValueError as exc:
        raise ValueError(f"无法解析颜色: {text!r}") from exc


def alpha_of(argb: int) -> int:
    """返回 0–255 的 alpha 分量。."""
    return (argb >> 24) & 0xFF


def red_of(argb: int) -> int:
    """返回 0–255 的红色分量。"""
    return (argb >> 16) & 0xFF


def green_of(argb: int) -> int:
    """返回 0–255 的绿色分量。"""
    return (argb >> 8) & 0xFF


def blue_of(argb: int) -> int:
    """返回 0–255 的蓝色分量。"""
    return argb & 0xFF


def argb_from_rgb(red: int, green: int, blue: int, alpha: int = 255) -> int:
    """由 0–255 的分量组合出 ARGB 整数。."""
    return (
        ((alpha & 0xFF) << 24)
        | ((red & 0xFF) << 16)
        | ((green & 0xFF) << 8)
        | (blue & 0xFF)
    ) & 0xFFFFFFFF


def with_alpha(argb: int, alpha: float) -> int:
    """返回替换了 alpha（0.0–1.0）的颜色。"""
    clamped = max(0.0, min(1.0, alpha))
    return ((round(clamped * 255) & 0xFF) << 24) | (argb & 0xFFFFFF)
