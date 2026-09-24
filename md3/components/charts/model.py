"""图表数据模型与刻度算法。"""

from __future__ import annotations

import dataclasses
import math

from PySide6 import QtGui


@dataclasses.dataclass
class Series:
    """一个数据系列。

    Attributes:
        name: 系列名称，显示在图例与悬停气泡中。
        values: 数值列表，与图表的分类一一对应。
        color: 颜色，可为 ``QColor``、色彩角色名（如 ``"tertiary"``）或
            None（按系列顺序自动分配）。
    """

    name: str
    values: list[float]
    color: QtGui.QColor | str | None = None

    def total(self) -> float:
        """数值之和。"""
        return float(sum(self.values))


@dataclasses.dataclass
class PointSeries:
    """散点 / 气泡图的一个系列。

    Attributes:
        name: 系列名称。
        points: (x, y) 坐标列表。
        sizes: 与 ``points`` 一一对应的气泡大小；None 时绘制等大的散点。
        color: 颜色，同 ``Series.color``。
    """

    name: str
    points: list[tuple[float, float]]
    sizes: list[float] | None = None
    color: QtGui.QColor | str | None = None

    def size_at(self, index: int) -> float | None:
        """第 index 个点的大小，未提供时返回 None。"""
        if self.sizes is None or index >= len(self.sizes):
            return None
        return self.sizes[index]


def nice_step(span: float, count: int) -> float:
    """按 "nice number" 规则选择刻度步长（1、2、5 的十进制倍数）。"""
    if span <= 0 or count <= 0:
        return 1.0
    raw = span / count
    magnitude = 10 ** math.floor(math.log10(raw))
    residual = raw / magnitude
    if residual <= 1:
        factor = 1
    elif residual <= 2:
        factor = 2
    elif residual <= 5:
        factor = 5
    else:
        factor = 10
    return factor * magnitude


def nice_ticks(minimum: float, maximum: float, count: int = 5) -> list[float]:
    """返回覆盖 ``[minimum, maximum]`` 的整齐刻度列表。

    Args:
        minimum: 数据最小值。
        maximum: 数据最大值。
        count: 期望的刻度数量（实际数量可能略有差异）。
    """
    if maximum <= minimum:
        maximum = minimum + 1.0
    step = nice_step(maximum - minimum, count)
    start = math.floor(minimum / step) * step
    end = math.ceil(maximum / step) * step
    ticks: list[float] = []
    value = start
    while value <= end + step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    return ticks


def format_value(value: float) -> str:
    """把数值格式化为简短标签：整数不带小数，大数使用 k / M 后缀。"""
    magnitude = abs(value)
    if magnitude >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if magnitude >= 10_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "k"
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def format_percent(fraction: float) -> str:
    """把 0–1 的比例格式化为百分数。"""
    percent = fraction * 100
    if percent >= 10 or percent == 0:
        return f"{percent:.0f}%"
    return f"{percent:.1f}%"
