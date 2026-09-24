"""间距与布局常量。

M3 以 4 dp 为基础网格，组件内边距与组件间距均为其整数倍。
"""

import dataclasses

UNIT = 4.0

SPACE_1 = UNIT * 1  # 4
SPACE_2 = UNIT * 2  # 8
SPACE_3 = UNIT * 3  # 12
SPACE_4 = UNIT * 4  # 16
SPACE_5 = UNIT * 5  # 20
SPACE_6 = UNIT * 6  # 24
SPACE_8 = UNIT * 8  # 32
SPACE_10 = UNIT * 10  # 40
SPACE_12 = UNIT * 12  # 48
SPACE_14 = UNIT * 14  # 56
SPACE_16 = UNIT * 16  # 64

# 桌面端常见的布局边距与列间距。
LAYOUT_MARGIN_COMPACT = 16.0
LAYOUT_MARGIN_MEDIUM = 24.0
LAYOUT_GUTTER = 24.0

# 窗口尺寸断点（dp），用于导航组件的自适应切换。
BREAKPOINT_COMPACT = 600
BREAKPOINT_MEDIUM = 840
BREAKPOINT_EXPANDED = 1200
BREAKPOINT_LARGE = 1600


@dataclasses.dataclass(frozen=True)
class Insets:
    """四边内边距（dp），顺序为左、上、右、下。"""

    left: float = 0.0
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0

    @classmethod
    def all(cls, value: float) -> "Insets":
        """四边相同。"""
        return cls(value, value, value, value)

    @classmethod
    def symmetric(cls, horizontal: float, vertical: float) -> "Insets":
        """水平与垂直方向分别指定。"""
        return cls(horizontal, vertical, horizontal, vertical)

    @property
    def horizontal(self) -> float:
        """左右之和。"""
        return self.left + self.right

    @property
    def vertical(self) -> float:
        """上下之和。"""
        return self.top + self.bottom
