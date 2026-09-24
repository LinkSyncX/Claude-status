"""形状标度（md.sys.shape）。

圆角半径单位为 dp。``FULL`` 表示胶囊形：半径取容器短边的一半。
"""

from __future__ import annotations

import dataclasses
import math

NONE = 0.0
EXTRA_SMALL = 4.0
SMALL = 8.0
MEDIUM = 12.0
LARGE = 16.0
LARGE_INCREASED = 20.0
EXTRA_LARGE = 28.0
EXTRA_LARGE_INCREASED = 32.0
EXTRA_EXTRA_LARGE = 48.0
FULL = math.inf


def resolve_radius(radius: float, width: float, height: float) -> float:
    """把标度值换算为给定尺寸下的实际半径。

    ``FULL`` 会换算为短边的一半；其他值会被限制为不超过短边的一半，
    以免圆角相互重叠导致绘制异常。
    """
    limit = max(0.0, min(width, height) / 2)
    if math.isinf(radius):
        return limit
    return max(0.0, min(radius, limit))


@dataclasses.dataclass(frozen=True)
class Shape:
    """四个角各自的半径，顺序为左上、右上、右下、左下。

    支持非对称形状，例如分段按钮的两端、底部面板只圆化顶部。
    """

    top_left: float = NONE
    top_right: float = NONE
    bottom_right: float = NONE
    bottom_left: float = NONE

    @classmethod
    def all(cls, radius: float) -> Shape:
        """四角相同半径。"""
        return cls(radius, radius, radius, radius)

    @classmethod
    def top(cls, radius: float) -> Shape:
        """仅顶部两角圆化（底部面板、顶部应用栏等）。"""
        return cls(radius, radius, NONE, NONE)

    @classmethod
    def bottom(cls, radius: float) -> Shape:
        """仅底部两角圆化。"""
        return cls(NONE, NONE, radius, radius)

    @classmethod
    def start(cls, radius: float) -> Shape:
        """仅左侧两角圆化（从左到右布局中的起始端）。"""
        return cls(radius, NONE, NONE, radius)

    @classmethod
    def end(cls, radius: float) -> Shape:
        """仅右侧两角圆化。"""
        return cls(NONE, radius, radius, NONE)

    @property
    def is_uniform(self) -> bool:
        """四角半径是否一致。"""
        return (
            self.top_left
            == self.top_right
            == self.bottom_right
            == self.bottom_left
        )

    def resolved(self, width: float, height: float) -> Shape:
        """返回把 ``FULL`` 等标度值换算为实际半径后的形状。"""
        return Shape(
            resolve_radius(self.top_left, width, height),
            resolve_radius(self.top_right, width, height),
            resolve_radius(self.bottom_right, width, height),
            resolve_radius(self.bottom_left, width, height),
        )


SHAPE_NONE = Shape.all(NONE)
SHAPE_EXTRA_SMALL = Shape.all(EXTRA_SMALL)
SHAPE_SMALL = Shape.all(SMALL)
SHAPE_MEDIUM = Shape.all(MEDIUM)
SHAPE_LARGE = Shape.all(LARGE)
SHAPE_EXTRA_LARGE = Shape.all(EXTRA_LARGE)
SHAPE_FULL = Shape.all(FULL)
