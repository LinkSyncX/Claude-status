"""扩展色（Extended / custom colors）。

M3 只定义了 primary / secondary / tertiary / error 四组强调色；业务应用
通常还需要 success / warning / info 之类的语义色。本模块移植
material-color-utilities 的 ``customColor``：给定一个种子色，可选地把它
的色相向主题主色轻微偏移（harmonize，最多 15°）以保持和谐，再按与
primary 相同的色调规则生成 ``<name>`` / ``on_<name>`` /
``<name>_container`` / ``on_<name>_container`` 四个角色，并随明暗模式与
对比度等级变化。
"""

from __future__ import annotations

import dataclasses
import re

from md3.color import blend
from md3.color import dynamic
from md3.color import tonal_palette

_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclasses.dataclass(frozen=True)
class ExtendedColor:
    """一个扩展色的定义。

    Attributes:
        name: 角色名前缀（小写字母、数字与下划线，例如 ``success``）。
        value: 种子色（ARGB 整数）。
        blend: 是否把色相向主题主色偏移以保持和谐。
    """

    name: str
    value: int
    blend: bool = True

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.match(self.name):
            raise ValueError(f"扩展色名称不合法: {self.name!r}")


@dataclasses.dataclass(frozen=True)
class ExtendedColorGroup:
    """由扩展色生成的四个色彩角色。

    Attributes:
        name: 角色名前缀。
        seed: 实际用于生成色调板的颜色（和谐化之后）。
        color: 强调色。
        on_color: 强调色上的内容色。
        color_container: 容器色。
        on_color_container: 容器上的内容色。
    """

    name: str
    seed: int
    color: int
    on_color: int
    color_container: int
    on_color_container: int

    def roles(self) -> dict[str, int]:
        """以角色名为键返回四个颜色。"""
        return {
            self.name: self.color,
            f"on_{self.name}": self.on_color,
            f"{self.name}_container": self.color_container,
            f"on_{self.name}_container": self.on_color_container,
        }


def role_names(name: str) -> tuple[str, str, str, str]:
    """扩展色 ``name`` 派生出的四个角色名。"""
    return (name, f"on_{name}", f"{name}_container", f"on_{name}_container")


def resolve(
    color: ExtendedColor,
    source: int,
    is_dark: bool,
    contrast_level: dynamic.ContrastLevel | float = (
        dynamic.ContrastLevel.STANDARD
    ),
) -> ExtendedColorGroup:
    """按主题参数生成扩展色的四个角色。

    Args:
        color: 扩展色定义。
        source: 主题的种子色（用于和谐化）。
        is_dark: 是否为暗色方案。
        contrast_level: 对比度等级；色调调整规则与 primary 家族一致。
    """
    seed = blend.harmonize(color.value, source) if color.blend else color.value
    palette = tonal_palette.TonalPalette.from_int(seed)
    resolver = dynamic.ToneResolver(is_dark, False, contrast_level)
    return ExtendedColorGroup(
        name=color.name,
        seed=seed,
        color=palette.tone(resolver.tone("primary")),
        on_color=palette.tone(resolver.tone("on_primary")),
        color_container=palette.tone(resolver.tone("primary_container")),
        on_color_container=palette.tone(resolver.tone("on_primary_container")),
    )


def resolve_all(
    colors: tuple[ExtendedColor, ...] | list[ExtendedColor],
    source: int,
    is_dark: bool,
    contrast_level: dynamic.ContrastLevel | float = (
        dynamic.ContrastLevel.STANDARD
    ),
) -> dict[str, int]:
    """生成多个扩展色并合并为 ``{角色名: ARGB}``。"""
    roles: dict[str, int] = {}
    for color in colors:
        roles.update(resolve(color, source, is_dark, contrast_level).roles())
    return roles
