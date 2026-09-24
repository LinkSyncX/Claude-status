"""漏斗图与树图。

- ``FunnelChart``：各阶段按值递减绘制为居中的梯形，阶段名与数值（及相对
  首阶段的转化率）标注在右侧；每个阶段一种系列色，图例可隐藏阶段。
- ``TreemapChart``：按 squarified 算法把矩形区域划分给各项，面积与值成
  正比；矩形内显示名称与数值（放不下时省略），悬停高亮并显示气泡，点击
  发出 ``item_clicked``。
"""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.charts import base
from md3.components.charts import model
from md3.components.charts import palette
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

FUNNEL_GAP = 4.0
FUNNEL_LABEL_WIDTH = 140.0
FUNNEL_MIN_RATIO = 0.12
FUNNEL_LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
FUNNEL_VALUE_STYLE = typography_tokens.TypeRole.BODY_SMALL
TREEMAP_GAP = 3.0
TREEMAP_PADDING = 8.0
TREEMAP_RADIUS = 6.0
TREEMAP_LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
TREEMAP_VALUE_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM


class FunnelChart(base.Chart):
    """漏斗图。

    Args:
        values: 各阶段的值（通常递减）。
        categories: 阶段名称。
        title: 标题。
        show_legend: 是否显示图例。
        animated: 是否播放入场动画。
        parent: 父控件。
    """

    def __init__(
        self,
        values: list[float] | None = None,
        categories: list[str] | None = None,
        title: str = "",
        show_legend: bool = False,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        series = [model.Series("", list(values or []))]
        super().__init__(
            series, categories, title, show_legend, animated, parent
        )

    @property
    def values(self) -> list[float]:
        """各阶段的值。"""
        return list(self._series[0].values) if self._series else []

    def set_values(
        self, values: list[float], categories: list[str] | None = None
    ) -> None:
        """替换数据。"""
        self.set_data(
            categories if categories is not None else self._categories,
            [model.Series("", list(values))],
        )

    def stage_color(self, index: int) -> QtGui.QColor:
        """第 index 个阶段的颜色。"""
        colors = palette.series_colors(self.theme, max(1, len(self.values)))
        return colors[index % len(colors)]

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        return [
            (self.stage_color(index), self.category_label(index))
            for index in range(len(self.values))
        ]

    def stage_rects(self, rect: QtCore.QRectF) -> list[QtGui.QPolygonF]:
        """各阶段梯形（已应用入场动画与隐藏状态）。"""
        values = self.values
        visible = [i for i in range(len(values)) if self.entry_visible(i)]
        if not visible:
            return []
        peak = max((abs(values[i]) for i in visible), default=1.0) or 1.0
        area = QtCore.QRectF(rect)
        area.setRight(area.right() - FUNNEL_LABEL_WIDTH)
        count = len(visible)
        height = (area.height() - FUNNEL_GAP * (count - 1)) / count
        polygons: list[QtGui.QPolygonF] = []
        progress = self.progress
        for position, index in enumerate(visible):
            top = area.top() + position * (height + FUNNEL_GAP)
            ratio = max(
                FUNNEL_MIN_RATIO, abs(self.displayed_value(0, index)) / peak
            )
            next_ratio = ratio
            if position + 1 < count:
                next_index = visible[position + 1]
                next_ratio = max(
                    FUNNEL_MIN_RATIO,
                    abs(self.displayed_value(0, next_index)) / peak,
                )
            top_width = area.width() * ratio * progress
            bottom_width = area.width() * next_ratio * progress
            center = area.center().x()
            polygons.append(
                QtGui.QPolygonF(
                    [
                        QtCore.QPointF(center - top_width / 2, top),
                        QtCore.QPointF(center + top_width / 2, top),
                        QtCore.QPointF(center + bottom_width / 2, top + height),
                        QtCore.QPointF(center - bottom_width / 2, top + height),
                    ]
                )
            )
        return polygons

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        values = self.values
        visible = [i for i in range(len(values)) if self.entry_visible(i)]
        polygons = self.stage_rects(rect)
        first = abs(values[visible[0]]) if visible else 0.0
        label_left = rect.right() - FUNNEL_LABEL_WIDTH + 12
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        for position, (index, polygon) in enumerate(
            zip(visible, polygons, strict=True)
        ):
            color = self.stage_color(index)
            if position == self.hovered_index:
                color = color.lighter(112)
            painter.setBrush(color)
            painter.drawPolygon(polygon)
            bounds = polygon.boundingRect()
            value = values[index]
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    label_left,
                    bounds.top(),
                    FUNNEL_LABEL_WIDTH - 12,
                    bounds.height() / 2,
                ),
                self.category_label(index),
                FUNNEL_LABEL_STYLE,
                self.color("on_surface"),
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignBottom,
            )
            percent = model.format_percent(value / first) if first else ""
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    label_left,
                    bounds.center().y(),
                    FUNNEL_LABEL_WIDTH - 12,
                    bounds.height() / 2,
                ),
                f"{self.format(value)}  {percent}".strip(),
                FUNNEL_VALUE_STYLE,
                self.color("on_surface_variant"),
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignTop,
            )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        rect = self.content_rect()
        values = self.values
        visible = [i for i in range(len(values)) if self.entry_visible(i)]
        for order, (index, polygon) in enumerate(
            zip(visible, self.stage_rects(rect), strict=True)
        ):
            if polygon.boundingRect().contains(position):
                first = abs(values[visible[0]]) or 1.0
                lines = [
                    (
                        self.stage_color(index),
                        self.category_label(index),
                        self.format(values[index]),
                    ),
                ]
                if order > 0:
                    previous = values[visible[order - 1]] or 1.0
                    lines.append(
                        (
                            self.color("on_surface_variant"),
                            "→",
                            model.format_percent(values[index] / previous),
                        )
                    )
                lines.append(
                    (
                        self.color("on_surface_variant"),
                        "%",
                        model.format_percent(values[index] / first),
                    )
                )
                bounds = polygon.boundingRect()
                return order, base.HoverInfo(
                    self.category_label(index),
                    lines,
                    QtCore.QPointF(bounds.center().x(), bounds.top()),
                )
        return None


@dataclasses.dataclass
class TreemapItem:
    """树图的一项。

    Attributes:
        label: 名称。
        value: 值（面积权重，非正值不显示）。
        color: 颜色，None 时按顺序自动分配。
        key: 业务侧标识。
    """

    label: str
    value: float
    color: QtGui.QColor | str | None = None
    key: Any = None


def squarify(values: list[float], rect: QtCore.QRectF) -> list[QtCore.QRectF]:
    """squarified treemap 布局：返回与 ``values`` 一一对应的矩形。

    ``values`` 需已按降序排列且均为正数。
    """
    total = sum(values)
    if total <= 0 or rect.isEmpty():
        return [QtCore.QRectF() for _ in values]
    scale = rect.width() * rect.height() / total
    areas = [v * scale for v in values]
    rects: list[QtCore.QRectF] = []
    remaining = QtCore.QRectF(rect)
    index = 0
    while index < len(areas):
        row = [areas[index]]
        index += 1
        while index < len(areas) and _worst(
            row + [areas[index]], remaining
        ) <= _worst(row, remaining):
            row.append(areas[index])
            index += 1
        rects.extend(_layout_row(row, remaining))
    return rects


def _worst(row: list[float], rect: QtCore.QRectF) -> float:
    side = min(rect.width(), rect.height())
    if side <= 0 or not row:
        return float("inf")
    total = sum(row)
    if total <= 0:
        return float("inf")
    biggest, smallest = max(row), min(row)
    return max(
        side * side * biggest / (total * total),
        total * total / (side * side * smallest),
    )


def _layout_row(
    row: list[float], remaining: QtCore.QRectF
) -> list[QtCore.QRectF]:
    total = sum(row)
    rects: list[QtCore.QRectF] = []
    if remaining.width() >= remaining.height():
        # 竖向排一列，占据左侧。
        column_width = total / remaining.height() if remaining.height() else 0.0
        y = remaining.top()
        for area in row:
            height = area / column_width if column_width else 0.0
            rects.append(
                QtCore.QRectF(remaining.left(), y, column_width, height)
            )
            y += height
        remaining.setLeft(remaining.left() + column_width)
    else:
        row_height = total / remaining.width() if remaining.width() else 0.0
        x = remaining.left()
        for area in row:
            width = area / row_height if row_height else 0.0
            rects.append(QtCore.QRectF(x, remaining.top(), width, row_height))
            x += width
        remaining.setTop(remaining.top() + row_height)
    return rects


class TreemapChart(base.Chart):
    """树图。

    Args:
        items: 各项。
        title: 标题。
        animated: 是否播放入场动画。
        parent: 父控件。
    """

    item_clicked = QtCore.Signal(int)

    def __init__(
        self,
        items: list[TreemapItem] | None = None,
        title: str = "",
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__([], [], title, False, animated, parent)
        self._items: list[TreemapItem] = list(items or [])
        self._tiles: list[tuple[int, QtCore.QRectF]] = []

    @property
    def items(self) -> list[TreemapItem]:
        """全部项。"""
        return list(self._items)

    def set_items(self, items: list[TreemapItem]) -> None:
        """替换全部项并重播入场动画。"""
        self._items = list(items)
        self._hovered = -1
        self._hover_info = None
        if self._animated:
            self.restart_animation()
        self.update()

    @override
    def has_data(self) -> bool:
        return any(item.value > 0 for item in self._items)

    @override
    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        return []

    def item_color(self, index: int) -> QtGui.QColor:
        """第 index 项的颜色。"""
        colors = palette.series_colors(self.theme, max(1, len(self._items)))
        return palette.resolve_color(
            self.theme, self._items[index].color, colors[index % len(colors)]
        )

    def layout_tiles(
        self, rect: QtCore.QRectF
    ) -> list[tuple[int, QtCore.QRectF]]:
        """计算各项的矩形（按值降序排列后 squarify），返回 (项下标, 矩形)。"""
        order = sorted(
            (i for i, item in enumerate(self._items) if item.value > 0),
            key=lambda i: -self._items[i].value,
        )
        values = [self._items[i].value for i in order]
        rects = squarify(values, rect)
        return list(zip(order, rects, strict=True))

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        self._tiles = self.layout_tiles(rect)
        progress = self.progress
        total = sum(item.value for item in self._items if item.value > 0) or 1.0
        for index, tile in self._tiles:
            inner = tile.adjusted(
                TREEMAP_GAP / 2,
                TREEMAP_GAP / 2,
                -TREEMAP_GAP / 2,
                -TREEMAP_GAP / 2,
            )
            if inner.width() <= 0 or inner.height() <= 0:
                continue
            if progress < 1.0:
                # 入场：从中心放大。
                center = inner.center()
                inner = QtCore.QRectF(
                    center.x() - inner.width() * progress / 2,
                    center.y() - inner.height() * progress / 2,
                    inner.width() * progress,
                    inner.height() * progress,
                )
            color = self.item_color(index)
            if index == self.hovered_index:
                color = color.lighter(112)
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    inner, shape_tokens.Shape.all(TREEMAP_RADIUS)
                ),
                color,
            )
            self._paint_tile_label(
                painter, inner, self._items[index], color, total
            )

    def _paint_tile_label(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        item: TreemapItem,
        color: QtGui.QColor,
        total: float,
    ) -> None:
        label_style = self.theme.style(TREEMAP_LABEL_STYLE)
        value_style = self.theme.style(TREEMAP_VALUE_STYLE)
        if (
            rect.width() < 2 * TREEMAP_PADDING + 24
            or rect.height() < label_style.line_height + 2 * TREEMAP_PADDING
        ):
            return
        text_color = _contrast_text(color)
        content = rect.adjusted(
            TREEMAP_PADDING, TREEMAP_PADDING, -TREEMAP_PADDING, -TREEMAP_PADDING
        )
        typography.paint_text(
            painter,
            QtCore.QRectF(
                content.left(),
                content.top(),
                content.width(),
                label_style.line_height,
            ),
            item.label,
            TREEMAP_LABEL_STYLE,
            text_color,
        )
        if (
            content.height()
            >= label_style.line_height + value_style.line_height
        ):
            share = model.format_percent(item.value / total)
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    content.left(),
                    content.top() + label_style.line_height,
                    content.width(),
                    value_style.line_height,
                ),
                f"{self.format(item.value)} · {share}",
                TREEMAP_VALUE_STYLE,
                theme_module.with_alpha(text_color, 0.8),
            )

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        tiles = self._tiles or self.layout_tiles(self.content_rect())
        total = sum(item.value for item in self._items if item.value > 0) or 1.0
        for index, tile in tiles:
            if tile.contains(position):
                item = self._items[index]
                return index, base.HoverInfo(
                    item.label,
                    [
                        (
                            self.item_color(index),
                            self.format(item.value),
                            model.format_percent(item.value / total),
                        ),
                    ],
                    QtCore.QPointF(tile.center().x(), tile.top()),
                )
        return None

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            hit = self.hit_test(event.position())
            if hit is not None:
                self.item_clicked.emit(hit[0])
        super().mouseReleaseEvent(event)


def _contrast_text(background: QtGui.QColor) -> QtGui.QColor:
    """按背景相对亮度选择深 / 浅文字色。"""
    luminance = (
        0.2126 * background.redF()
        + 0.7152 * background.greenF()
        + 0.0722 * background.blueF()
    )
    return (
        QtGui.QColor("#1D1B20") if luminance > 0.55 else QtGui.QColor("#FFFFFF")
    )
