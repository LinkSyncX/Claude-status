"""图表基类：标题、图例、悬停气泡、入场与数据过渡动画、直角坐标系工具。

图例可点击：点击某个条目会隐藏 / 显示对应系列（或扇区），坐标轴范围随
之重新计算。调用 ``set_data`` 时若新旧数据形状一致（系列数与每个系列的
长度相同），图形会从旧值平滑过渡到新值；否则重播入场动画。
"""

from __future__ import annotations

from collections.abc import Callable
import dataclasses
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.charts import model
from md3.components.charts import palette
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

PADDING = 16.0
TITLE_STYLE = typography_tokens.TypeRole.TITLE_MEDIUM
TITLE_GAP = 12.0
AXIS_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
AXIS_TITLE_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
LEGEND_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
LEGEND_DOT = 12.0
LEGEND_GAP = 8.0
LEGEND_ITEM_GAP = 20.0
LEGEND_ROW_HEIGHT = 24.0
LEGEND_TOP_GAP = 12.0
TOOLTIP_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
TOOLTIP_TITLE_STYLE = typography_tokens.TypeRole.LABEL_LARGE
TOOLTIP_PADDING = 12.0
TOOLTIP_LINE_HEIGHT = 20.0
TOOLTIP_GAP = 8.0
EMPTY_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
GRID_WIDTH = 1.0
Y_TICK_COUNT = 5
X_LABEL_HEIGHT = 24.0
AXIS_LABEL_GAP = 8.0
AXIS_TITLE_GAP = 4.0
ENTER_DURATION = motion.LONG2
TRANSITION_DURATION = motion.MEDIUM4

ValueFormatter = Callable[[float], str]


@dataclasses.dataclass
class HoverInfo:
    """悬停气泡内容。

    Attributes:
        title: 标题（通常为分类名）。
        lines: 每行 (颜色, 名称, 数值文字)。
        anchor: 气泡锚点（控件坐标），气泡显示在其上方。
    """

    title: str
    lines: list[tuple[QtGui.QColor, str, str]]
    anchor: QtCore.QPointF


class Chart(widget.MaterialWidget):
    """所有图表的基类。

    Args:
        series: 数据系列。
        categories: 分类标签（x 轴或饼图各块的名称）。
        title: 标题。
        show_legend: 是否显示图例。
        animated: 是否播放入场动画。
        parent: 父控件。
    """

    hovered_changed = QtCore.Signal(int)
    visibility_changed = QtCore.Signal(int, bool)

    def __init__(
        self,
        series: list[model.Series] | None = None,
        categories: list[str] | None = None,
        title: str = "",
        show_legend: bool = True,
        animated: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._series: list[model.Series] = list(series or [])
        self._categories: list[str] = list(categories or [])
        self._title = title
        self._show_legend = show_legend
        self._legend_interactive = True
        self._animated = animated
        self._formatter: ValueFormatter = model.format_value
        self._empty_text = i18n.tr("no_data")
        self._hovered = -1
        self._hover_info: HoverInfo | None = None
        self._hidden: set[int] = set()
        self._legend_hits: list[tuple[QtCore.QRectF, int]] = []
        self._progress = animation.AnimatedFloat(self, 1.0, self.update)
        # 数据过渡：从 _previous_values 插值到当前值。
        self._transition = animation.AnimatedFloat(self, 1.0, self.update)
        self._previous_values: list[list[float]] | None = None
        self._entered = False
        # 可见分类窗口（缩放 / 平移），None 表示显示全部。
        self._view_start = 0
        self._view_count: int | None = None
        # ``append`` 自动编号用的序号，替换数据后重新同步。
        self._append_serial: int | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Chart

    @override
    def accessible_name(self) -> str:
        return self._title or self.toolTip()

    # ---- 数据 -------------------------------------------------------------

    @property
    def series(self) -> list[model.Series]:
        """数据系列。"""
        return list(self._series)

    @property
    def categories(self) -> list[str]:
        """分类标签。"""
        return list(self._categories)

    def set_data(
        self,
        categories: list[str] | None,
        series: list[model.Series],
        animate: bool = True,
    ) -> None:
        """替换全部数据。

        新旧数据形状一致时平滑过渡到新值，否则重新播放入场动画。
        """
        previous = [list(s.values) for s in self._series]
        self._categories = list(categories or [])
        self._series = list(series)
        self._append_serial = None
        self._hovered = -1
        self._hover_info = None
        self._hidden = {
            i for i in self._hidden if i < len(self.legend_entries())
        }
        if animate and self._animated:
            if self._same_shape(previous, self._series):
                self.start_transition(previous)
            else:
                self.restart_animation()
        else:
            self._previous_values = None
            self._transition.set(1.0)
        self.update()

    @staticmethod
    def _same_shape(
        previous: list[list[float]], series: list[model.Series]
    ) -> bool:
        return (
            bool(previous)
            and len(previous) == len(series)
            and all(
                len(old) == len(new.values)
                for old, new in zip(previous, series, strict=True)
            )
        )

    def set_series(
        self, series: list[model.Series], animate: bool = True
    ) -> None:
        """替换数据系列。"""
        self.set_data(self._categories, series, animate)

    def set_categories(self, categories: list[str]) -> None:
        """替换分类标签。"""
        self._categories = list(categories)
        self.update()

    def value_at(self, series_index: int, index: int) -> float:
        """第 series_index 个系列在（可见窗口内）第 index 个分类的原始值。"""
        series = self._series[series_index]
        source = index + self._view_start
        return (
            series.values[source] if 0 <= source < len(series.values) else 0.0
        )

    def series_length(self, series_index: int) -> int:
        """第 series_index 个系列在可见窗口内的值数量。"""
        total = len(self._series[series_index].values)
        return max(0, min(self.category_count(), total - self._view_start))

    def displayed_value(self, series_index: int, index: int) -> float:
        """第 series_index 个系列第 index 个值在当前过渡进度下的显示值。"""
        value = self.value_at(series_index, index)
        if self._previous_values is None:
            return value
        progress = self._transition.value
        if progress >= 1.0:
            return value
        old_series = self._previous_values[series_index]
        source = index + self._view_start
        old = old_series[source] if 0 <= source < len(old_series) else 0.0
        return old + (value - old) * progress

    def append(
        self,
        values: list[float],
        category: str | None = None,
        max_points: int | None = None,
    ) -> None:
        """向每个系列末尾追加一个值（流式数据），可限制保留的点数。

        Args:
            values: 每个系列一个新值，缺少的系列补 0。
            category: 新分类的标签，None 时按序号命名。
            max_points: 超过该数量时丢弃最早的点，None 不限制。
        """
        for index, series in enumerate(self._series):
            series.values.append(
                float(values[index]) if index < len(values) else 0.0
            )
        # 自动编号在丢弃旧点后仍继续递增，而不是重复使用当前长度。
        if self._append_serial is None:
            self._append_serial = self.total_category_count() - 1
        self._append_serial += 1
        label = category if category is not None else str(self._append_serial)
        self._categories.append(label)
        if max_points is not None and max_points > 0:
            for series in self._series:
                del series.values[:-max_points]
            del self._categories[:-max_points]
        self._previous_values = None
        self._transition.set(1.0)
        self._hovered = -1
        self._hover_info = None
        self.update()

    @property
    def title(self) -> str:
        """标题。"""
        return self._title

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self._title = title
        self.update()

    def set_value_formatter(self, formatter: ValueFormatter) -> None:
        """设置数值格式化函数（用于轴刻度与气泡）。"""
        self._formatter = formatter
        self.update()

    def format(self, value: float) -> str:
        """按当前格式化函数格式化数值。"""
        return self._formatter(value)

    def set_show_legend(self, show: bool) -> None:
        """设置是否显示图例。"""
        self._show_legend = show
        self.update()

    def set_legend_interactive(self, interactive: bool) -> None:
        """设置点击图例是否切换系列可见性。"""
        self._legend_interactive = interactive

    def set_empty_text(self, text: str) -> None:
        """设置无数据时显示的提示文字。"""
        self._empty_text = text
        self.update()

    def has_data(self) -> bool:
        """是否有可绘制的数据。"""
        return any(s.values for s in self._series)

    def total_category_count(self) -> int:
        """全部分类数量（取分类标签与最长系列中的较大者）。"""
        longest = max((len(s.values) for s in self._series), default=0)
        return max(len(self._categories), longest)

    def category_count(self) -> int:
        """可见窗口内的分类数量（未缩放时即全部分类）。"""
        total = self.total_category_count()
        remaining = max(0, total - self._view_start)
        if self._view_count is None:
            return remaining
        return min(self._view_count, remaining)

    def category_label(self, index: int) -> str:
        """可见窗口内第 index 个分类的标签，缺失时返回序号。"""
        source = index + self._view_start
        if 0 <= source < len(self._categories):
            return self._categories[source]
        return str(source + 1)

    def color_for(self, index: int) -> QtGui.QColor:
        """第 index 个系列的颜色。"""
        fallbacks = palette.series_colors(self.theme, max(1, len(self._series)))
        declared = (
            self._series[index].color if index < len(self._series) else None
        )
        return palette.resolve_color(
            self.theme, declared, fallbacks[index % len(fallbacks)]
        )

    # ---- 可见性 -----------------------------------------------------------

    def entry_visible(self, index: int) -> bool:
        """第 index 个图例条目（系列 / 扇区）是否可见。"""
        return index not in self._hidden

    def set_entry_visible(self, index: int, visible: bool) -> None:
        """显示或隐藏第 index 个图例条目。"""
        if visible == self.entry_visible(index):
            return
        if visible:
            self._hidden.discard(index)
        else:
            self._hidden.add(index)
        self._hovered = -1
        self._hover_info = None
        self.visibility_changed.emit(index, visible)
        self.update()

    def toggle_entry(self, index: int) -> None:
        """切换第 index 个图例条目的可见性。"""
        self.set_entry_visible(index, not self.entry_visible(index))

    def visible_series_indices(self) -> list[int]:
        """当前可见的系列下标。"""
        return [i for i in range(len(self._series)) if self.entry_visible(i)]

    # ---- 动画 -------------------------------------------------------------

    @property
    def progress(self) -> float:
        """入场动画进度 0–1。"""
        return self._progress.value

    @property
    def transition_progress(self) -> float:
        """数据过渡进度 0–1（无过渡时为 1）。"""
        return self._transition.value

    def restart_animation(self) -> None:
        """重新播放入场动画。"""
        self._previous_values = None
        self._transition.set(1.0)
        self._progress.set(0.0)
        self._progress.animate_to(
            1.0, ENTER_DURATION, motion.EMPHASIZED_DECELERATE
        )

    def start_transition(self, previous: list[list[float]]) -> None:
        """从给定的旧值过渡到当前值。"""
        self._previous_values = previous
        self._progress.set(1.0)
        self._transition.set(0.0)
        self._transition.animate_to(1.0, TRANSITION_DURATION, motion.EMPHASIZED)

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._animated and not self._entered:
            self._entered = True
            self.restart_animation()

    # ---- 布局 -------------------------------------------------------------

    def legend_entries(self) -> list[tuple[QtGui.QColor, str]]:
        """图例条目 (颜色, 名称)，默认每个系列一条。"""
        return [(self.color_for(i), s.name) for i, s in enumerate(self._series)]

    def _legend_rows(
        self, width: float
    ) -> list[list[tuple[int, QtGui.QColor, str]]]:
        rows: list[list[tuple[int, QtGui.QColor, str]]] = []
        current: list[tuple[int, QtGui.QColor, str]] = []
        used = 0.0
        for index, (color, name) in enumerate(self.legend_entries()):
            item_width = (
                LEGEND_DOT
                + LEGEND_GAP
                + typography.text_width(name, LEGEND_STYLE)
            )
            if current and used + LEGEND_ITEM_GAP + item_width > width:
                rows.append(current)
                current = []
                used = 0.0
            current.append((index, color, name))
            used += item_width + (LEGEND_ITEM_GAP if len(current) > 1 else 0)
        if current:
            rows.append(current)
        return rows

    def legend_height(self, width: float) -> float:
        """图例占用高度。"""
        if not self._show_legend or not self.legend_entries():
            return 0.0
        rows = self._legend_rows(width)
        return LEGEND_TOP_GAP + len(rows) * LEGEND_ROW_HEIGHT

    def title_height(self) -> float:
        """标题占用高度。"""
        if not self._title:
            return 0.0
        return self.theme.style(TITLE_STYLE).line_height + TITLE_GAP

    def content_rect(self) -> QtCore.QRectF:
        """去掉边距、标题与图例后的绘图区域。"""
        rect = QtCore.QRectF(self.rect()).adjusted(
            PADDING, PADDING, -PADDING, -PADDING
        )
        rect.setTop(rect.top() + self.title_height())
        rect.setBottom(rect.bottom() - self.legend_height(rect.width()))
        return rect

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, 240)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(160, 120)

    # ---- 导出 -------------------------------------------------------------

    def to_image(
        self, size: QtCore.QSize | None = None, scale: float = 2.0
    ) -> QtGui.QImage:
        """把图表渲染为位图（默认 2 倍分辩率），不含悬停气泡。"""
        target = size or self.size()
        if not target.isValid() or target.isEmpty():
            target = self.sizeHint()
        image = QtGui.QImage(
            round(target.width() * scale),
            round(target.height() * scale),
            QtGui.QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.setDevicePixelRatio(scale)
        image.fill(self.color("surface"))
        self._render_to(image, target)
        return image

    def export_image(
        self,
        path: str,
        size: QtCore.QSize | None = None,
        scale: float = 2.0,
    ) -> bool:
        """导出为 PNG / JPG 等位图文件，返回是否成功。"""
        return self.to_image(size, scale).save(path)

    def export_svg(self, path: str, size: QtCore.QSize | None = None) -> bool:
        """导出为 SVG 文件，返回是否成功。"""
        # QtSvg 只在导出时需要，延迟导入避免为所有图表加载该模块。
        from PySide6 import (  # noqa: PLC0415  # pylint: disable=import-outside-toplevel
            QtSvg,
        )

        target = size or self.size()
        if not target.isValid() or target.isEmpty():
            target = self.sizeHint()
        generator = QtSvg.QSvgGenerator()
        generator.setFileName(path)
        generator.setSize(target)
        generator.setViewBox(QtCore.QRect(QtCore.QPoint(0, 0), target))
        generator.setTitle(self._title)
        self._render_to(generator, target)
        return QtCore.QFile.exists(path)

    def _render_to(
        self, device: QtGui.QPaintDevice, target: QtCore.QSize
    ) -> None:
        hover = self._hover_info
        hovered = self._hovered
        self._hover_info = None
        self._hovered = -1
        original = self.size()
        if original != target:
            self.resize(target)
        try:
            painter = QtGui.QPainter(device)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
            painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
            painter.setRenderHint(
                QtGui.QPainter.RenderHint.SmoothPixmapTransform
            )
            self.paint(painter)
            painter.end()
        finally:
            if original != target:
                self.resize(original)
            self._hover_info = hover
            self._hovered = hovered

    # ---- 绘制 -------------------------------------------------------------

    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        """在绘图区域内绘制图表本体，由子类实现。"""
        del painter, rect

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        outer = QtCore.QRectF(self.rect()).adjusted(
            PADDING, PADDING, -PADDING, -PADDING
        )
        if self._title:
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    outer.left(),
                    outer.top(),
                    outer.width(),
                    self.theme.style(TITLE_STYLE).line_height,
                ),
                self._title,
                TITLE_STYLE,
                self.color("on_surface"),
            )
        content = self.content_rect()
        if content.width() > 8 and content.height() > 8:
            painter.save()
            if self.has_data():
                self.paint_chart(painter, content)
            else:
                self._paint_empty(painter, content)
            painter.restore()
        self._paint_legend(painter, outer)
        if self._hover_info is not None:
            self._paint_tooltip(painter, self._hover_info)

    def _paint_empty(
        self, painter: QtGui.QPainter, rect: QtCore.QRectF
    ) -> None:
        if not self._empty_text:
            return
        typography.paint_text(
            painter,
            rect,
            self._empty_text,
            EMPTY_STYLE,
            self.color("on_surface_variant"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    def _paint_legend(
        self, painter: QtGui.QPainter, outer: QtCore.QRectF
    ) -> None:
        self._legend_hits = []
        if not self._show_legend:
            return
        rows = self._legend_rows(outer.width())
        if not rows:
            return
        y = outer.bottom() - len(rows) * LEGEND_ROW_HEIGHT
        label_color = self.color("on_surface_variant")
        hidden_color = theme_module.with_alpha(
            label_color, state_tokens.DISABLED_CONTENT_OPACITY
        )
        for row in rows:
            widths = [
                LEGEND_DOT
                + LEGEND_GAP
                + typography.text_width(name, LEGEND_STYLE)
                for _, _, name in row
            ]
            total = sum(widths) + LEGEND_ITEM_GAP * (len(row) - 1)
            x = outer.center().x() - total / 2
            for (index, color, name), width in zip(row, widths, strict=True):
                visible = self.entry_visible(index)
                dot = QtCore.QRectF(
                    x,
                    y + (LEGEND_ROW_HEIGHT - LEGEND_DOT) / 2,
                    LEGEND_DOT,
                    LEGEND_DOT,
                )
                painter.save()
                if visible:
                    painter.setPen(QtCore.Qt.PenStyle.NoPen)
                    painter.setBrush(color)
                    painter.drawEllipse(dot)
                else:
                    # 隐藏的条目画成空心圆点。
                    painter.setPen(QtGui.QPen(color, 1.5))
                    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(dot.adjusted(1, 1, -1, -1))
                painter.restore()
                typography.paint_text(
                    painter,
                    QtCore.QRectF(
                        x + LEGEND_DOT + LEGEND_GAP, y, width, LEGEND_ROW_HEIGHT
                    ),
                    name,
                    LEGEND_STYLE,
                    label_color if visible else hidden_color,
                    elide=False,
                )
                self._legend_hits.append(
                    (QtCore.QRectF(x, y, width, LEGEND_ROW_HEIGHT), index)
                )
                x += width + LEGEND_ITEM_GAP
            y += LEGEND_ROW_HEIGHT

    def legend_index_at(self, position: QtCore.QPointF) -> int:
        """鼠标位置对应的图例条目下标，无命中返回 -1。"""
        for rect, index in self._legend_hits:
            if rect.contains(position):
                return index
        return -1

    def _paint_tooltip(self, painter: QtGui.QPainter, info: HoverInfo) -> None:
        theme = self.theme
        title_style = theme.style(TOOLTIP_TITLE_STYLE)
        width = typography.text_width(info.title, TOOLTIP_TITLE_STYLE)
        for _, name, value in info.lines:
            line_width = (
                LEGEND_DOT
                + LEGEND_GAP
                + typography.text_width(name, TOOLTIP_STYLE)
                + 16
                + typography.text_width(value, TOOLTIP_STYLE)
            )
            width = max(width, line_width)
        width += 2 * TOOLTIP_PADDING
        height = 2 * TOOLTIP_PADDING + title_style.line_height
        if info.lines:
            height += TOOLTIP_GAP + len(info.lines) * TOOLTIP_LINE_HEIGHT
        bounds = QtCore.QRectF(self.rect())
        x = info.anchor.x() - width / 2
        y = info.anchor.y() - height - 12
        if y < bounds.top():
            y = info.anchor.y() + 12
        x = max(bounds.left(), min(x, bounds.right() - width))
        y = max(bounds.top(), min(y, bounds.bottom() - height))
        rect = QtCore.QRectF(x, y, width, height)
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_SMALL),
            theme.color("inverse_surface"),
        )
        text_color = theme.color("inverse_on_surface")
        cursor_y = rect.top() + TOOLTIP_PADDING
        typography.paint_text(
            painter,
            QtCore.QRectF(
                rect.left() + TOOLTIP_PADDING,
                cursor_y,
                width - 2 * TOOLTIP_PADDING,
                title_style.line_height,
            ),
            info.title,
            TOOLTIP_TITLE_STYLE,
            text_color,
        )
        cursor_y += title_style.line_height + TOOLTIP_GAP
        for color, name, value in info.lines:
            dot = QtCore.QRectF(
                rect.left() + TOOLTIP_PADDING,
                cursor_y + (TOOLTIP_LINE_HEIGHT - LEGEND_DOT) / 2,
                LEGEND_DOT,
                LEGEND_DOT,
            )
            painter.save()
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(dot)
            painter.restore()
            line_rect = QtCore.QRectF(
                rect.left() + TOOLTIP_PADDING + LEGEND_DOT + LEGEND_GAP,
                cursor_y,
                width - 2 * TOOLTIP_PADDING - LEGEND_DOT - LEGEND_GAP,
                TOOLTIP_LINE_HEIGHT,
            )
            typography.paint_text(
                painter, line_rect, name, TOOLTIP_STYLE, text_color
            )
            typography.paint_text(
                painter,
                line_rect,
                value,
                TOOLTIP_STYLE,
                text_color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )
            cursor_y += TOOLTIP_LINE_HEIGHT

    # ---- 悬停与点击 -------------------------------------------------------

    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, HoverInfo] | None:
        """返回鼠标位置对应的 (下标, 气泡内容)，无命中返回 None。"""
        del position  # 基类不含数据几何，由子类实现命中测试。

    @property
    def hovered_index(self) -> int:
        """当前悬停的分类 / 扇区下标，-1 表示无。"""
        return self._hovered

    def _set_hover(self, hit: tuple[int, HoverInfo] | None) -> None:
        index = hit[0] if hit is not None else -1
        self._hover_info = hit[1] if hit is not None else None
        if index != self._hovered:
            self._hovered = index
            self.hovered_changed.emit(index)
        self.update()

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._set_hover(
            self.hit_test(event.position()) if self.has_data() else None
        )
        over_legend = self.legend_index_at(event.position()) >= 0
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if over_legend and self._legend_interactive
            else QtCore.Qt.CursorShape.ArrowCursor
        )
        super().mouseMoveEvent(event)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self._legend_interactive
        ):
            index = self.legend_index_at(event.position())
            if index >= 0:
                self.toggle_entry(index)
                event.accept()
                return
        super().mousePressEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._set_hover(None)
        super().leaveEvent(event)


class CartesianChart(Chart):
    """带 x 分类轴与 y 数值轴的图表基类。

    支持沿 x 轴缩放与平移（``set_zoomable``：滚轮缩放、拖动平移）以及
    悬停十字游标（``set_crosshair``）。
    """

    visible_range_changed = QtCore.Signal(int, int)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._show_grid = True
        self._show_axes = True
        self._x_title = ""
        self._y_title = ""
        self._y_min: float | None = None
        self._y_max: float | None = None
        self._zoomable = False
        self._crosshair = False
        self._min_visible = 2
        self._pan_origin: QtCore.QPointF | None = None
        self._pan_start_index = 0
        self._cursor_pos: QtCore.QPointF | None = None
        self._last_plot: QtCore.QRectF | None = None
        self._last_range: tuple[float, float] | None = None

    # ---- 缩放与平移 -------------------------------------------------------

    @property
    def zoomable(self) -> bool:
        """是否允许滚轮缩放与拖动平移。"""
        return self._zoomable

    def set_zoomable(self, zoomable: bool, min_visible: int = 2) -> None:
        """开启或关闭沿 x 轴的缩放 / 平移。"""
        self._zoomable = zoomable
        self._min_visible = max(1, min_visible)
        if not zoomable:
            self.reset_zoom()

    @property
    def visible_range(self) -> tuple[int, int]:
        """当前可见的 (起始分类下标, 分类数量)。"""
        return self._view_start, self.category_count()

    @property
    def zoomed(self) -> bool:
        """是否处于缩放状态。"""
        return self._view_count is not None

    def set_visible_range(self, start: int, count: int | None) -> None:
        """设置可见窗口；``count`` 为 None 表示显示全部。"""
        total = self.total_category_count()
        if count is None or count >= total:
            start, count = 0, None
        else:
            count = max(1, count)
            start = max(0, min(start, total - count))
        if (start, count) == (self._view_start, self._view_count):
            return
        self._view_start = start
        self._view_count = count
        self._hovered = -1
        self._hover_info = None
        self.visible_range_changed.emit(*self.visible_range)
        self.update()

    def reset_zoom(self) -> None:
        """恢复显示全部分类。"""
        self.set_visible_range(0, None)

    def zoom(self, factor: float, anchor_index: int | None = None) -> None:
        """按倍数缩放可见窗口（>1 放大即显示更少分类），围绕锚点分类。"""
        total = self.total_category_count()
        if total <= self._min_visible:
            return
        current = self.category_count()
        new_count = max(self._min_visible, min(total, round(current / factor)))
        if anchor_index is None:
            anchor_index = current // 2
        absolute = self._view_start + anchor_index
        ratio = anchor_index / max(1, current)
        start = round(absolute - ratio * new_count)
        self.set_visible_range(start, new_count if new_count < total else None)

    def pan(self, delta: int) -> None:
        """把可见窗口向右（正）或向左（负）移动若干分类。"""
        if self._view_count is None:
            return
        self.set_visible_range(self._view_start + delta, self._view_count)

    # ---- 游标 -------------------------------------------------------------

    @property
    def crosshair(self) -> bool:
        """是否显示十字游标。"""
        return self._crosshair

    def set_crosshair(self, enabled: bool) -> None:
        """开启或关闭悬停十字游标。"""
        self._crosshair = enabled
        self.update()

    def _remember_plot(
        self, plot: QtCore.QRectF, low: float, high: float
    ) -> None:
        self._last_plot = QtCore.QRectF(plot)
        self._last_range = (low, high)

    def _paint_crosshair(self, painter: QtGui.QPainter) -> None:
        if (
            not self._crosshair
            or self._cursor_pos is None
            or self._last_plot is None
            or self._last_range is None
            or not self._last_plot.contains(self._cursor_pos)
        ):
            return
        plot = self._last_plot
        low, high = self._last_range
        pos = self._cursor_pos
        color = self.color("on_surface_variant")
        pen = QtGui.QPen(color, 1.0)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        pen.setDashPattern([3, 3])
        painter.save()
        painter.setPen(pen)
        index = self.category_at(pos.x(), plot)
        x = (
            self.category_slot(index, plot).center().x()
            if index >= 0
            else pos.x()
        )
        painter.drawLine(
            QtCore.QPointF(x, plot.top()), QtCore.QPointF(x, plot.bottom())
        )
        painter.drawLine(
            QtCore.QPointF(plot.left(), pos.y()),
            QtCore.QPointF(plot.right(), pos.y()),
        )
        painter.restore()
        # y 轴处的数值标签。
        span = high - low or 1.0
        value = low + (plot.bottom() - pos.y()) / plot.height() * span
        text = self.format(value)
        style = self.theme.style(AXIS_STYLE)
        width = typography.text_width(text, AXIS_STYLE) + 8
        label = QtCore.QRectF(
            plot.left() - width - 2,
            pos.y() - style.line_height / 2 - 2,
            width,
            style.line_height + 4,
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(
                label, shape_tokens.SHAPE_EXTRA_SMALL
            ),
            self.color("inverse_surface"),
        )
        typography.paint_text(
            painter,
            label,
            text,
            AXIS_STYLE,
            self.color("inverse_on_surface"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            elide=False,
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        super().paint(painter)
        if self.has_data():
            self._paint_crosshair(painter)

    # ---- 事件 -------------------------------------------------------------

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        self._cursor_pos = event.position()
        if self._pan_origin is not None and self._last_plot is not None:
            count = max(1, self.category_count())
            slot_width = self._last_plot.width() / count
            delta = (event.position().x() - self._pan_origin.x()) / slot_width
            direction = 1 if self.is_rtl() else -1
            self.set_visible_range(
                self._pan_start_index + direction * round(delta),
                self._view_count,
            )
            event.accept()
            return
        super().mouseMoveEvent(event)
        if self._crosshair:
            self.update()

    def _can_start_pan(self, pos: QtCore.QPointF) -> bool:
        """是否可以从该位置开始拖动平移（已缩放且落在绘图区内）。"""
        if not (self._zoomable and self.zoomed) or self._last_plot is None:
            return False
        return self._last_plot.contains(pos) and self.legend_index_at(pos) < 0

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and self._can_start_pan(event.position())
        ):
            self._pan_origin = event.position()
            self._pan_start_index = self._view_start
            self.setCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._pan_origin is not None:
            self._pan_origin = None
            self.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._zoomable and self.zoomed:
            self.reset_zoom()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        if not self._zoomable or self._last_plot is None:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if not delta:
            super().wheelEvent(event)
            return
        anchor = self.category_at(event.position().x(), self._last_plot)
        self.zoom(1.25 if delta > 0 else 0.8, anchor if anchor >= 0 else None)
        event.accept()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._cursor_pos = None
        super().leaveEvent(event)

    def set_show_grid(self, show: bool) -> None:
        """设置是否绘制水平网格线。"""
        self._show_grid = show
        self.update()

    def set_show_axes(self, show: bool) -> None:
        """设置是否绘制坐标轴（关闭后成为无轴的迷你图）。"""
        self._show_axes = show
        self.update()

    @property
    def show_axes(self) -> bool:
        """是否绘制坐标轴。"""
        return self._show_axes

    def set_axis_titles(self, x_title: str = "", y_title: str = "") -> None:
        """设置 x / y 轴标题（y 轴标题竖排在左侧）。"""
        self._x_title = x_title
        self._y_title = y_title
        self.update()

    def set_y_range(self, minimum: float | None, maximum: float | None) -> None:
        """固定 y 轴范围（None 表示按数据自动计算）。"""
        self._y_min = minimum
        self._y_max = maximum
        self.update()

    def data_extent(self) -> tuple[float, float]:
        """可见数据的最小值与最大值，子类可覆写（例如堆叠求和）。"""
        values = [
            v
            for i in self.visible_series_indices()
            for v in self._series[i].values
        ]
        if not values:
            return 0.0, 1.0
        return min(values), max(values)

    def stacked_extent(self) -> tuple[float, float]:
        """按分类把可见系列的正负值分别累加后的范围。"""
        count = self.category_count()
        visible = self.visible_series_indices()
        if count == 0 or not visible:
            return 0.0, 1.0
        positives = [0.0] * count
        negatives = [0.0] * count
        for s_index in visible:
            for index, value in enumerate(self._series[s_index].values[:count]):
                if value >= 0:
                    positives[index] += value
                else:
                    negatives[index] += value
        return min(negatives), max(positives)

    def value_range(self) -> tuple[float, float, list[float]]:
        """返回 y 轴 (下限, 上限, 刻度)。"""
        low, high = self.data_extent()
        if low > 0:
            low = 0.0
        if high < 0:
            high = 0.0
        if self._y_min is not None:
            low = self._y_min
        if self._y_max is not None:
            high = self._y_max
        ticks = model.nice_ticks(low, high, Y_TICK_COUNT)
        return ticks[0], ticks[-1], ticks

    def _axis_title_height(self) -> float:
        if not self._x_title:
            return 0.0
        return self.theme.style(AXIS_TITLE_STYLE).line_height + AXIS_TITLE_GAP

    def _axis_title_width(self) -> float:
        if not self._y_title:
            return 0.0
        return self.theme.style(AXIS_TITLE_STYLE).line_height + AXIS_TITLE_GAP

    def plot_rect(
        self, rect: QtCore.QRectF, ticks: list[float]
    ) -> QtCore.QRectF:
        """去掉轴标签与轴标题后的绘图矩形。"""
        if not self._show_axes:
            return rect.adjusted(4, 4, -4, -4)
        label_width = max(
            (typography.text_width(self.format(t), AXIS_STYLE) for t in ticks),
            default=0.0,
        )
        left = (
            rect.left()
            + self._axis_title_width()
            + label_width
            + AXIS_LABEL_GAP
        )
        return QtCore.QRectF(
            left,
            rect.top() + 4,
            max(0.0, rect.right() - left),
            max(
                0.0,
                rect.height() - 4 - X_LABEL_HEIGHT - self._axis_title_height(),
            ),
        )

    @staticmethod
    def value_to_y(
        value: float, plot: QtCore.QRectF, low: float, high: float
    ) -> float:
        """把数值映射为 y 坐标。"""
        span = high - low or 1.0
        return plot.bottom() - (value - low) / span * plot.height()

    def category_slot(self, index: int, plot: QtCore.QRectF) -> QtCore.QRectF:
        """第 index 个分类占据的竖向槽位。"""
        count = max(1, self.category_count())
        width = plot.width() / count
        return QtCore.QRectF(
            plot.left() + index * width, plot.top(), width, plot.height()
        )

    def category_at(self, x: float, plot: QtCore.QRectF) -> int:
        """x 坐标对应的分类下标，越界返回 -1。"""
        count = self.category_count()
        if (
            count == 0
            or plot.width() <= 0
            or not plot.left() <= x <= plot.right()
        ):
            return -1
        index = int((x - plot.left()) / plot.width() * count)
        return min(count - 1, max(0, index))

    def paint_axes(
        self,
        painter: QtGui.QPainter,
        plot: QtCore.QRectF,
        low: float,
        high: float,
        ticks: list[float],
    ) -> None:
        """绘制网格线、y 轴刻度标签、x 轴分类标签与轴标题。"""
        self._remember_plot(plot, low, high)
        if not self._show_axes:
            return
        grid_color = self.color("outline_variant")
        label_color = self.color("on_surface_variant")
        style = self.theme.style(AXIS_STYLE)
        for tick in ticks:
            y = self.value_to_y(tick, plot, low, high)
            if self._show_grid or tick == 0:
                pen = QtGui.QPen(grid_color, GRID_WIDTH)
                if tick != 0:
                    pen.setStyle(QtCore.Qt.PenStyle.DashLine)
                    pen.setDashPattern([4, 4])
                painter.setPen(pen)
                painter.drawLine(
                    QtCore.QPointF(plot.left(), y),
                    QtCore.QPointF(plot.right(), y),
                )
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    plot.left() - AXIS_LABEL_GAP - 80,
                    y - style.line_height / 2,
                    80,
                    style.line_height,
                ),
                self.format(tick),
                AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )
        for index in range(self.category_count()):
            slot = self.category_slot(index, plot)
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    slot.left(),
                    plot.bottom() + 4,
                    slot.width(),
                    X_LABEL_HEIGHT - 4,
                ),
                self.category_label(index),
                AXIS_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        self.paint_axis_titles(painter, plot)

    def paint_axis_titles(
        self, painter: QtGui.QPainter, plot: QtCore.QRectF
    ) -> None:
        """绘制 x 轴（下方居中）与 y 轴（左侧竖排）标题。"""
        color = self.color("on_surface_variant")
        line = self.theme.style(AXIS_TITLE_STYLE).line_height
        if self._x_title:
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    plot.left(),
                    plot.bottom() + X_LABEL_HEIGHT + AXIS_TITLE_GAP,
                    plot.width(),
                    line,
                ),
                self._x_title,
                AXIS_TITLE_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        if self._y_title:
            content = self.content_rect()
            painter.save()
            painter.translate(content.left(), plot.center().y())
            painter.rotate(-90)
            typography.paint_text(
                painter,
                QtCore.QRectF(-plot.height() / 2, 0, plot.height(), line),
                self._y_title,
                AXIS_TITLE_STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
            painter.restore()

    def paint_hover_band(
        self, painter: QtGui.QPainter, plot: QtCore.QRectF, index: int
    ) -> None:
        """在悬停分类的槽位后方绘制 8% 的状态层。"""
        if index < 0:
            return
        slot = self.category_slot(index, plot)
        layer = theme_module.with_alpha(self.color("on_surface"), 0.08)
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(slot, shape_tokens.SHAPE_SMALL),
            layer,
        )
