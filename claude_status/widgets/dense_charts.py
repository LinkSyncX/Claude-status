"""分类很多时自动抽稀 x 轴标签的折线图与柱状图。

md3 的直角坐标图表把每个分类标签画在各自的槽位里，分类一多（例如
90 天的逐日数据）标签就会全部被省略号截断。这里在绘制坐标轴时先隐藏
全部分类标签，再按标签宽度每隔 N 个分类绘制一个完整标签；悬停气泡
仍然显示对应分类的完整标签。
"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui

from md3.components import charts
from md3.components.charts import base
from md3.core import typography

LABEL_GAP = 12.0
TOTAL_STAGGER = 0.35


class _SparseAxisChart(charts.CartesianChart):
    """覆写 ``paint_axes``：隐藏逐个分类的标签，改为按间隔绘制。

    作为折线图 / 柱状图的第一个基类使用，``super()`` 会沿 MRO 调用到
    ``CartesianChart`` 的实现。
    """

    _hide_categories = False

    @override
    def category_label(self, index: int) -> str:
        if self._hide_categories:
            return ""
        return super().category_label(index)

    @override
    def paint_axes(
        self,
        painter: QtGui.QPainter,
        plot: QtCore.QRectF,
        low: float,
        high: float,
        ticks: list[float],
    ) -> None:
        self._hide_categories = True
        try:
            super().paint_axes(painter, plot, low, high, ticks)
        finally:
            self._hide_categories = False
        if self.show_axes:
            self._paint_sparse_labels(painter, plot)

    def _paint_sparse_labels(
        self, painter: QtGui.QPainter, plot: QtCore.QRectF
    ) -> None:
        count = self.category_count()
        if count <= 0:
            return
        labels = [self.category_label(i) for i in range(count)]
        widest = max(
            (typography.text_width(text, base.AXIS_STYLE) for text in labels),
            default=0.0,
        )
        slot = plot.width() / count
        step = max(1, math.ceil((widest + LABEL_GAP) / max(1.0, slot)))
        color = self.color("on_surface_variant")
        bounds = QtCore.QRectF(self.rect())
        width = widest + 4
        # 从最后一个分类往前取，保证最近的日期总有标签。
        for index in range(count - 1, -1, -step):
            center = self.category_slot(index, plot).center().x()
            left = min(center - width / 2, bounds.right() - width)
            left = max(bounds.left(), left)
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    left, plot.bottom() + 4, width, base.X_LABEL_HEIGHT - 4
                ),
                labels[index],
                base.AXIS_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
                elide=False,
            )


class DenseLineChart(_SparseAxisChart, charts.LineChart):
    """x 轴标签自动抽稀的折线图。"""

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(640, 300)


class DenseBarChart(_SparseAxisChart, charts.BarChart):
    """x 轴标签自动抽稀、入场错开量按分类数归一化的柱状图。"""

    def _category_progress(self, index: int) -> float:
        # md3 的 BarChart 按下标线性累加错开量（每个分类 0.06），分类超过
        # 16 个时后面的柱子在动画结束后仍然是 0 高度；这里改为按分类总数
        # 归一化，总错开量固定为 TOTAL_STAGGER。
        count = max(1, self.category_count())
        offset = index / count * TOTAL_STAGGER
        raw = (self.progress - offset) / (1.0 - TOTAL_STAGGER)
        return max(0.0, min(1.0, raw))

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(640, 300)
