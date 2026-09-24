"""动效令牌（md.sys.motion）：时长、缓动曲线与弹簧。.

时长单位为毫秒。缓动曲线以三次贝塞尔控制点表示；``EMPHASIZED`` 是由两段
贝塞尔曲线拼接而成的路径，需要动画框架支持多段曲线。弹簧令牌来自
M3 Expressive 的运动方案（motion scheme），以阻尼比与刚度描述，由
``md3.core.animation`` 解析为时长与缓动曲线。
"""

from __future__ import annotations

import dataclasses

# 时长（ms）。
SHORT1 = 50
SHORT2 = 100
SHORT3 = 150
SHORT4 = 200
MEDIUM1 = 250
MEDIUM2 = 300
MEDIUM3 = 350
MEDIUM4 = 400
LONG1 = 450
LONG2 = 500
LONG3 = 550
LONG4 = 600
EXTRA_LONG1 = 700
EXTRA_LONG2 = 800
EXTRA_LONG3 = 900
EXTRA_LONG4 = 1000


@dataclasses.dataclass(frozen=True)
class CubicBezier:
    """单段三次贝塞尔缓动，起点 (0, 0)、终点 (1, 1)。"""

    x1: float
    y1: float
    x2: float
    y2: float


@dataclasses.dataclass(frozen=True)
class BezierSegment:
    """路径缓动中的一段，包含两个控制点与终点。"""

    c1: tuple[float, float]
    c2: tuple[float, float]
    end: tuple[float, float]


@dataclasses.dataclass(frozen=True)
class PathEasing:
    """由多段贝塞尔曲线拼接的缓动路径，起点为 (0, 0)。"""

    segments: tuple[BezierSegment, ...]


Easing = CubicBezier | PathEasing

LINEAR = CubicBezier(0.0, 0.0, 1.0, 1.0)
STANDARD = CubicBezier(0.2, 0.0, 0.0, 1.0)
STANDARD_ACCELERATE = CubicBezier(0.3, 0.0, 1.0, 1.0)
STANDARD_DECELERATE = CubicBezier(0.0, 0.0, 0.0, 1.0)
EMPHASIZED_ACCELERATE = CubicBezier(0.3, 0.0, 0.8, 0.15)
EMPHASIZED_DECELERATE = CubicBezier(0.05, 0.7, 0.1, 1.0)
# 规范中的 emphasized 曲线：
# M 0,0 C 0.05,0 0.133333,0.06 0.166666,0.4 C 0.208333,0.82 0.25,1 1,1
EMPHASIZED = PathEasing(
    segments=(
        BezierSegment(c1=(0.05, 0.0), c2=(0.133333, 0.06), end=(0.166666, 0.4)),
        BezierSegment(c1=(0.208333, 0.82), c2=(0.25, 1.0), end=(1.0, 1.0)),
    )
)

# 常用组合：进入 / 退出 / 状态切换。
ENTER_DURATION = MEDIUM4
ENTER_EASING = EMPHASIZED_DECELERATE
EXIT_DURATION = SHORT4
EXIT_EASING = EMPHASIZED_ACCELERATE
STATE_LAYER_DURATION = SHORT3
STATE_LAYER_EASING = STANDARD
RIPPLE_DURATION = LONG2


@dataclasses.dataclass(frozen=True)
class Spring:
    """弹簧动效参数（单位质量）。

    Attributes:
        damping_ratio: 阻尼比，<1 时有过冲回弹，=1 为临界阻尼。
        stiffness: 刚度，越大越快。
    """

    damping_ratio: float
    stiffness: float

    def __post_init__(self) -> None:
        if self.damping_ratio <= 0:
            raise ValueError("damping_ratio 必须大于 0")
        if self.stiffness <= 0:
            raise ValueError("stiffness 必须大于 0")


# M3 运动方案：spatial 用于位置 / 尺寸 / 形状变化，effects 用于颜色 /
# 不透明度等不改变几何的过渡（因此阻尼比为 1，不会过冲）。
# 标准方案（MotionScheme.standard）。
STANDARD_DEFAULT_SPATIAL = Spring(damping_ratio=0.9, stiffness=700.0)
STANDARD_FAST_SPATIAL = Spring(damping_ratio=0.9, stiffness=1400.0)
STANDARD_SLOW_SPATIAL = Spring(damping_ratio=0.9, stiffness=300.0)
STANDARD_DEFAULT_EFFECTS = Spring(damping_ratio=1.0, stiffness=1600.0)
STANDARD_FAST_EFFECTS = Spring(damping_ratio=1.0, stiffness=3800.0)
STANDARD_SLOW_EFFECTS = Spring(damping_ratio=1.0, stiffness=800.0)
# 表现力方案（MotionScheme.expressive），用于醒目元素与主要交互。
EXPRESSIVE_DEFAULT_SPATIAL = Spring(damping_ratio=0.8, stiffness=380.0)
EXPRESSIVE_FAST_SPATIAL = Spring(damping_ratio=0.6, stiffness=800.0)
EXPRESSIVE_SLOW_SPATIAL = Spring(damping_ratio=0.8, stiffness=200.0)
EXPRESSIVE_DEFAULT_EFFECTS = STANDARD_DEFAULT_EFFECTS
EXPRESSIVE_FAST_EFFECTS = STANDARD_FAST_EFFECTS
EXPRESSIVE_SLOW_EFFECTS = STANDARD_SLOW_EFFECTS
# 进度指示器数值变化：无回弹、极低刚度，让进度平缓追上目标。
PROGRESS_SPRING = Spring(damping_ratio=1.0, stiffness=50.0)
# 加载指示器形状变形：轻微回弹，650ms 内完成一次变形。
MORPH_SPRING = Spring(damping_ratio=0.6, stiffness=200.0)
