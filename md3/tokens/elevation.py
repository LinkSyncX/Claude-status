"""海拔（md.sys.elevation）与阴影参数。

M3 使用 0–5 六个海拔等级，每级由两层阴影叠加而成：一层较锐利的 key
shadow 与一层柔和的 ambient shadow。阴影参数取自 material-web 的实现，
暗色主题下另叠加 surface tint 以体现层级。
"""

from __future__ import annotations

import dataclasses
import enum


class Level(enum.IntEnum):
    """海拔等级，值为对应的 dp。"""

    LEVEL_0 = 0
    LEVEL_1 = 1
    LEVEL_2 = 3
    LEVEL_3 = 6
    LEVEL_4 = 8
    LEVEL_5 = 12


@dataclasses.dataclass(frozen=True)
class ShadowLayer:
    """单层阴影。

    Attributes:
        offset_y: 垂直偏移（dp）。
        blur: 模糊半径（dp）。
        spread: 扩展量（dp），阴影形状比容器向外扩大的距离。
        opacity: 阴影颜色的不透明度。
    """

    offset_y: float
    blur: float
    spread: float
    opacity: float


@dataclasses.dataclass(frozen=True)
class Shadow:
    """一个海拔等级对应的完整阴影定义。"""

    key: ShadowLayer | None
    ambient: ShadowLayer | None

    @property
    def layers(self) -> tuple[ShadowLayer, ...]:
        """按绘制顺序（先 ambient 后 key）返回非空图层。"""
        return tuple(
            layer for layer in (self.ambient, self.key) if layer is not None
        )

    @property
    def extent(self) -> float:
        """阴影可能越出容器边界的最大距离（dp），用于预留外边距。"""
        return max(
            (
                layer.offset_y + layer.blur + layer.spread
                for layer in self.layers
            ),
            default=0.0,
        )


_NO_SHADOW = Shadow(key=None, ambient=None)

SHADOWS: dict[Level, Shadow] = {
    Level.LEVEL_0: _NO_SHADOW,
    Level.LEVEL_1: Shadow(
        key=ShadowLayer(1, 2, 0, 0.30),
        ambient=ShadowLayer(1, 3, 1, 0.15),
    ),
    Level.LEVEL_2: Shadow(
        key=ShadowLayer(1, 2, 0, 0.30),
        ambient=ShadowLayer(2, 6, 2, 0.15),
    ),
    Level.LEVEL_3: Shadow(
        key=ShadowLayer(1, 3, 0, 0.30),
        ambient=ShadowLayer(4, 8, 3, 0.15),
    ),
    Level.LEVEL_4: Shadow(
        key=ShadowLayer(2, 3, 0, 0.30),
        ambient=ShadowLayer(6, 10, 4, 0.15),
    ),
    Level.LEVEL_5: Shadow(
        key=ShadowLayer(4, 4, 0, 0.30),
        ambient=ShadowLayer(8, 12, 6, 0.15),
    ),
}

# 暗色主题下各海拔等级叠加在表面上的 surface tint 不透明度。
SURFACE_TINT_OPACITY: dict[Level, float] = {
    Level.LEVEL_0: 0.0,
    Level.LEVEL_1: 0.05,
    Level.LEVEL_2: 0.08,
    Level.LEVEL_3: 0.11,
    Level.LEVEL_4: 0.12,
    Level.LEVEL_5: 0.14,
}


def shadow_for(level: Level | int) -> Shadow:
    """返回海拔等级对应的阴影定义。

    Args:
        level: ``Level`` 成员或其 dp 值。

    Raises:
        ValueError: dp 值不是合法的海拔等级。
    """
    try:
        return SHADOWS[Level(level)]
    except ValueError as exc:
        raise ValueError(f"非法的海拔等级: {level!r}") from exc
