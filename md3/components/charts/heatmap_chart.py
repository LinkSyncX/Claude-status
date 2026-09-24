"""热力图：行 × 列的数值矩阵，用颜色深浅表示大小。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.color import hct
from md3.components.charts import base
from md3.components.charts import palette
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

CELL_GAP = 2.0
CELL_RADIUS = 4.0
ROW_LABEL_MAX_WIDTH = 96.0
COLUMN_LABEL_HEIGHT = 24.0
SCALE_HEIGHT = 12.0
SCALE_GAP = 12.0
SCALE_LABEL_WIDTH = 48.0
VALUE_STYLE = typography_tokens.TypeRole.LABEL_SMALL
STAGGER = 0.5


def mix_hct(
    low: QtGui.QColor, high: QtGui.QColor, fraction: float
) -> QtGui.QColor:
    """在 HCT 空间按比例混合两种颜色，色调与色度都线性变化。"""
    fraction = max(0.0, min(1.0, fraction))
    start = hct.Hct.from_int(theme_module.argb(low))
    end = hct.Hct.from_int(theme_module.argb(high))
    delta = ((end.hue - start.hue + 180.0) % 360.0) - 180.0
    hue = (start.hue + delta * fraction) % 360.0
    chroma = start.chroma + (end.chroma - start.chroma) * fraction
    tone = start.tone + (end.tone - start.tone) * fraction
    return theme_module.qcolor(hct.Hct.from_hct(hue, chroma, tone).to_int())


class HeatmapChart(base.Chart):
    """热力图。

    Args:
        rows: 行标签。
        columns: 列标签。
        values: ``values[行][列]`` 的数值矩阵。
        show_values: 是否在格子内显示数值。
        low_color: 最小值对应的颜色，默认 ``surface_container_highest``。
        high_color: 最大值对应的颜色，默认 ``primary``。
        title: 标题。
        animated: 是否播放入场动画（格子沿对角线依次显现）。
        parent: 父控件。
    """

    def __init__(
        self,
        rows: list[str] | None = None,
        columns: list[str] | None = None,
        values: list[list[float]] | None = None,
        show_values: bool = False,
        low_color: QtGui.QColor | str | None = None,
        high_color: QtGui.QColor | str | None = None,
        title: str = "",
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            None, list(columns or []), title, False, animated, parent
        )
        self._rows: list[str] = list(rows or [])
        self._values: list[list[float]] = [list(row) for row in values or []]
        self._show_values = show_values
        self._low_color = low_color
        self._high_color = high_color
        self._range: tuple[float, float] | None = None
        self._hovered_cell: tuple[int, int] | None = None
        self._show_scale = True

    # ---- 数据 -------------------------------------------------------------

    @property
    def rows(self) -> list[str]:
        """行标签。"""
        return list(self._rows)

    @property
    def columns(self) -> list[str]:
        """列标签。"""
        return list(self._categories)

    @property
    def values(self) -> list[list[float]]:
        """数值矩阵。"""
        return [list(row) for row in self._values]

    def set_matrix(
        self,
        rows: list[str],
        columns: list[str],
        values: list[list[float]],
        animate: bool = True,
    ) -> None:
        """替换全部数据。"""
        self._rows = list(rows)
        self._categories = list(columns)
        self._values = [list(row) for row in values]
        self._hovered_cell = None
        if animate and self._animated:
            self.restart_animation()
        self.update()

    def set_show_values(self, show: bool) -> None:
        """设置是否显示数值。"""
        self._show_values = show
        self.update()

    def set_show_scale(self, show: bool) -> None:
        """设置是否显示底部的色阶条。"""
        self._show_scale = show
        self.update()

    def set_range(self, minimum: float | None, maximum: float | None) -> None:
        """固定色阶范围（None 表示按数据自动计算）。"""
        if minimum is None or maximum is None:
            self._range = None
        else:
            self._range = (float(minimum), float(maximum))
        self.update()

    @override
    def has_data(self) -> bool:
        return any(row for row in self._values)

    @override
    def value_at(  # pylint: disable=arguments-renamed
        self, row: int, column: int
    ) -> float | None:
        """指定格子的值，缺失时返回 None（热力图以矩阵而非系列存储）。"""
        if 0 <= row < len(self._values) and 0 <= column < len(
            self._values[row]
        ):
            return self._values[row][column]
        return None

    def value_range(self) -> tuple[float, float]:
        """色阶对应的 (最小值, 最大值)。"""
        if self._range is not None:
            return self._range
        flat = [v for row in self._values for v in row]
        if not flat:
            return 0.0, 1.0
        low, high = min(flat), max(flat)
        if high <= low:
            high = low + 1.0
        return low, high

    def color_at(self, value: float) -> QtGui.QColor:
        """数值对应的格子颜色。"""
        low, high = self.value_range()
        fraction = (value - low) / (high - low)
        return mix_hct(self._resolve_low(), self._resolve_high(), fraction)

    def _resolve_low(self) -> QtGui.QColor:
        return palette.resolve_color(
            self.theme, self._low_color, self.color("surface_container_highest")
        )

    def _resolve_high(self) -> QtGui.QColor:
        return palette.resolve_color(
            self.theme, self._high_color, self.color("primary")
        )

    @property
    def hovered_cell(self) -> tuple[int, int] | None:
        """当前悬停的 (行, 列)。"""
        return self._hovered_cell

    # ---- 几何 -------------------------------------------------------------

    def _row_label_width(self) -> float:
        width = max(
            (typography.text_width(r, base.AXIS_STYLE) for r in self._rows),
            default=0.0,
        )
        return min(ROW_LABEL_MAX_WIDTH, width)

    def _scale_height(self) -> float:
        if not self._show_scale:
            return 0.0
        return (
            SCALE_GAP
            + SCALE_HEIGHT
            + self.theme.style(base.AXIS_STYLE).line_height
        )

    def grid_rect(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        """格子区域（去掉行列标签与色阶条）。"""
        left = rect.left() + self._row_label_width() + base.AXIS_LABEL_GAP
        top = rect.top() + COLUMN_LABEL_HEIGHT
        return QtCore.QRectF(
            left,
            top,
            max(0.0, rect.right() - left),
            max(0.0, rect.bottom() - self._scale_height() - top),
        )

    def cell_rect(
        self, grid: QtCore.QRectF, row: int, column: int
    ) -> QtCore.QRectF:
        """指定格子的矩形。"""
        rows = max(1, len(self._rows))
        columns = max(1, len(self._categories))
        width = (grid.width() - CELL_GAP * (columns - 1)) / columns
        height = (grid.height() - CELL_GAP * (rows - 1)) / rows
        return QtCore.QRectF(
            grid.left() + column * (width + CELL_GAP),
            grid.top() + row * (height + CELL_GAP),
            max(0.0, width),
            max(0.0, height),
        )

    def cell_at(
        self, grid: QtCore.QRectF, position: QtCore.QPointF
    ) -> tuple[int, int] | None:
        """鼠标位置对应的 (行, 列)。"""
        if (
            not grid.contains(position)
            or not self._rows
            or not self._categories
        ):
            return None
        rows, columns = len(self._rows), len(self._categories)
        row = int((position.y() - grid.top()) / grid.height() * rows)
        column = int((position.x() - grid.left()) / grid.width() * columns)
        return min(rows - 1, row), min(columns - 1, column)

    def _cell_progress(self, row: int, column: int) -> float:
        rows, columns = max(1, len(self._rows)), max(1, len(self._categories))
        offset = (row / rows + column / columns) / 2 * STAGGER
        raw = (self.progress - offset) / max(0.05, 1.0 - STAGGER)
        return max(0.0, min(1.0, raw))

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        grid = self.grid_rect(rect)
        label_color = self.color("on_surface_variant")
        style = self.theme.style(base.AXIS_STYLE)
        label_width = self._row_label_width()
        for row, name in enumerate(self._rows):
            cell = self.cell_rect(grid, row, 0)
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    grid.left() - base.AXIS_LABEL_GAP - label_width,
                    cell.center().y() - style.line_height / 2,
                    label_width,
                    style.line_height,
                ),
                name,
                base.AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
        for column, name in enumerate(self._categories):
            cell = self.cell_rect(grid, 0, column)
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    cell.left(),
                    rect.top(),
                    cell.width(),
                    COLUMN_LABEL_HEIGHT - 4,
                ),
                name,
                base.AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for row in range(len(self._rows)):
            for column in range(len(self._categories)):
                value = self.value_at(row, column)
                cell = self.cell_rect(grid, row, column)
                progress = self._cell_progress(row, column)
                if value is None or progress <= 0:
                    continue
                color = self.color_at(value)
                painter.setOpacity(progress)
                path = shape_utils.rounded_rect_path(cell, CELL_RADIUS)
                shape_utils.fill_shape(painter, path, color)
                if self._hovered_cell == (row, column):
                    shape_utils.fill_shape(
                        painter, path, None, self.color("on_surface"), 2.0
                    )
                if self._show_values and cell.width() > 24:
                    typography.paint_text(
                        painter,
                        cell,
                        self.format(value),
                        VALUE_STYLE,
                        self._text_color_for(color),
                        QtCore.Qt.AlignmentFlag.AlignCenter,
                    )
        painter.setOpacity(1.0)
        if self._show_scale:
            self._paint_scale(painter, grid)

    def _text_color_for(self, background: QtGui.QColor) -> QtGui.QColor:
        tone = hct.Hct.from_int(theme_module.argb(background)).tone
        return self.color("on_surface") if tone > 60 else QtGui.QColor("white")

    def _paint_scale(
        self, painter: QtGui.QPainter, grid: QtCore.QRectF
    ) -> None:
        low, high = self.value_range()
        style = self.theme.style(base.AXIS_STYLE)
        top = grid.bottom() + SCALE_GAP
        bar = QtCore.QRectF(
            grid.left() + SCALE_LABEL_WIDTH,
            top,
            max(0.0, grid.width() - 2 * SCALE_LABEL_WIDTH),
            SCALE_HEIGHT,
        )
        gradient = QtGui.QLinearGradient(bar.topLeft(), bar.topRight())
        for step in range(9):
            fraction = step / 8
            gradient.setColorAt(
                fraction,
                mix_hct(self._resolve_low(), self._resolve_high(), fraction),
            )
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(
            shape_utils.rounded_rect_path(bar, shape_tokens.SHAPE_FULL)
        )
        color = self.color("on_surface_variant")
        for value, left, align in (
            (low, grid.left(), QtCore.Qt.AlignmentFlag.AlignRight),
            (high, bar.right() + 8, QtCore.Qt.AlignmentFlag.AlignLeft),
        ):
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    left,
                    top + SCALE_HEIGHT / 2 - style.line_height / 2,
                    SCALE_LABEL_WIDTH - 8,
                    style.line_height,
                ),
                self.format(value),
                base.AXIS_STYLE,
                color,
                align | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        grid = self.grid_rect(self.content_rect())
        cell = self.cell_at(grid, position)
        if cell is None:
            self._hovered_cell = None
            return None
        row, column = cell
        value = self.value_at(row, column)
        if value is None:
            self._hovered_cell = None
            return None
        self._hovered_cell = cell
        rect = self.cell_rect(grid, row, column)
        return row * max(1, len(self._categories)) + column, base.HoverInfo(
            f"{self._rows[row]} · {self._categories[column]}",
            [(self.color_at(value), i18n.tr("value"), self.format(value))],
            QtCore.QPointF(rect.center().x(), rect.top()),
        )

    @override
    def _set_hover(self, hit: tuple[int, base.HoverInfo] | None) -> None:
        if hit is None:
            self._hovered_cell = None
        super()._set_hover(hit)

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, 280)
