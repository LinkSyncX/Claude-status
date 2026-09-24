"""日历热力图：GitHub 贡献图风格，每列一周、每行一个星期几。

颜色按分位数分为 5 档（无用量 + 4 档深浅），在 HCT 空间从
``surface_container_highest`` 过渡到 ``primary``，明暗主题下都保持对比。
悬停显示当天明细气泡，点击发出 ``day_clicked``；入场时格子按周依次
淡入。
"""

from __future__ import annotations

from collections.abc import Callable
import datetime as dt
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import charts
from md3.components.charts import base
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import theme as theme_module
from md3.tokens import typography as typography_tokens

from claude_status import analytics
from claude_status import formatting

LABEL_STYLE = typography_tokens.TypeRole.LABEL_SMALL
MONTH_HEIGHT = 20.0
LEGEND_HEIGHT = 32.0
WEEKDAY_WIDTH = 32.0
MAX_PITCH = 18.0
MIN_PITCH = 6.0
GAP_RATIO = 0.2
LEVEL_FRACTIONS = (0.28, 0.5, 0.75, 1.0)
STAGGER = 0.6

TooltipProvider = Callable[[dt.date, float], list[tuple[str, str]]]


def _monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


class CalendarHeatmap(base.Chart):
    """日历热力图。

    Args:
        title: 标题。
        parent: 父控件。
    """

    day_clicked = QtCore.Signal(object)

    def __init__(
        self, title: str = "", parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(None, [], title, False, True, parent)
        today = dt.date.today()
        self._start = today - dt.timedelta(days=364)
        self._end = today
        self._values: dict[dt.date, float] = {}
        self._thresholds: list[float] = []
        self._provider: TooltipProvider | None = None
        self._hover_day: dt.date | None = None
        self._selected: dt.date | None = None
        self._high_color: str = "primary"
        self.set_empty_text("所选区间内没有用量记录")
        policy = QtWidgets.QSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    # ---- 数据 -------------------------------------------------------------

    def set_values(
        self,
        values: dict[dt.date, float],
        start: dt.date,
        end: dt.date,
        animate: bool = True,
    ) -> None:
        """设置 ``start`` 至 ``end``（含）的逐日数值。"""
        self._start, self._end = min(start, end), max(start, end)
        self._values = {
            day: value
            for day, value in values.items()
            if self._start <= day <= self._end
        }
        self._thresholds = analytics.level_thresholds(self._values.values())
        self._hover_day = None
        self._hover_info = None
        if self._selected is not None and not (
            self._start <= self._selected <= self._end
        ):
            self._selected = None
        if animate and self._animated:
            self.restart_animation()
        self._sync_minimum_height()
        self.updateGeometry()
        self.update()

    def _sync_minimum_height(self) -> None:
        # 放在 widgetResizable 的滚动区域里时，内容会被压到最小尺寸；把
        # 最小高度设为当前宽度下完整显示 7 行与图例所需的高度。
        height = self.heightForWidth(max(1, self.width()))
        if self.minimumHeight() != height:
            self.setMinimumHeight(height)

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._sync_minimum_height()

    def set_tooltip_provider(self, provider: TooltipProvider | None) -> None:
        """设置悬停气泡的明细行：``(日期, 数值) -> [(名称, 文字), …]``。"""
        self._provider = provider

    def set_high_color(self, role: str) -> None:
        """最深一档使用的色彩角色。"""
        self._high_color = role
        self.update()

    def set_selected_day(self, day: dt.date | None) -> None:
        """高亮某一天（None 取消）。"""
        self._selected = day
        self.update()

    @property
    def selected_day(self) -> dt.date | None:
        """当前高亮的日期。"""
        return self._selected

    @property
    def thresholds(self) -> list[float]:
        """各档位的下限。"""
        return list(self._thresholds)

    @override
    def has_data(self) -> bool:
        return any(value > 0 for value in self._values.values())

    def level_color(self, level: int) -> QtGui.QColor:
        """档位对应的颜色（0 为无用量）。"""
        low = self.color("surface_container_highest")
        if level <= 0:
            return low
        fraction = LEVEL_FRACTIONS[min(level, len(LEVEL_FRACTIONS)) - 1]
        return charts.mix_hct(low, self.color(self._high_color), fraction)

    # ---- 几何 -------------------------------------------------------------

    def week_count(self) -> int:
        """区间覆盖的周数（列数）。"""
        return (_monday(self._end) - _monday(self._start)).days // 7 + 1

    def _pitch(self, width: float) -> float:
        available = width - 2 * base.PADDING - WEEKDAY_WIDTH
        pitch = available / max(1, self.week_count())
        return max(MIN_PITCH, min(MAX_PITCH, pitch))

    def grid_rect(self, rect: QtCore.QRectF) -> QtCore.QRectF:
        """格子区域（不含月份与星期标签、图例）。"""
        pitch = self._pitch(self.width())
        width = pitch * self.week_count()
        left = rect.left() + WEEKDAY_WIDTH
        # 空间富余时整体居中。
        spare = rect.right() - left - width
        if spare > 0:
            left += spare / 2
        return QtCore.QRectF(left, rect.top() + MONTH_HEIGHT, width, pitch * 7)

    def cell_rect(self, grid: QtCore.QRectF, day: dt.date) -> QtCore.QRectF:
        """某一天的格子。"""
        pitch = grid.height() / 7
        gap = max(1.5, pitch * GAP_RATIO)
        column = (_monday(day) - _monday(self._start)).days // 7
        return QtCore.QRectF(
            grid.left() + column * pitch + gap / 2,
            grid.top() + day.weekday() * pitch + gap / 2,
            pitch - gap,
            pitch - gap,
        )

    def day_at(self, position: QtCore.QPointF) -> dt.date | None:
        """鼠标位置对应的日期（区间外返回 None）。"""
        grid = self.grid_rect(self.content_rect())
        if not grid.contains(position):
            return None
        pitch = grid.height() / 7
        column = int((position.x() - grid.left()) // pitch)
        row = int((position.y() - grid.top()) // pitch)
        day = _monday(self._start) + dt.timedelta(days=column * 7 + row)
        if not self._start <= day <= self._end:
            return None
        return day

    @override
    def hasHeightForWidth(self) -> bool:
        return True

    @override
    def heightForWidth(self, width: int) -> int:
        pitch = self._pitch(width)
        return round(
            2 * base.PADDING
            + self.title_height()
            + MONTH_HEIGHT
            + pitch * 7
            + LEGEND_HEIGHT
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = round(
            2 * base.PADDING + WEEKDAY_WIDTH + MAX_PITCH * self.week_count()
        )
        return QtCore.QSize(width, self.heightForWidth(width))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        width = round(
            2 * base.PADDING + WEEKDAY_WIDTH + MIN_PITCH * self.week_count()
        )
        return QtCore.QSize(width, self.heightForWidth(width))

    # ---- 绘制 -------------------------------------------------------------

    def _month_labels(self) -> list[tuple[int, dt.date]]:
        """(列, 日期)：每月第一个周一所在的列标注该月。

        第一列标注起始日期所在的月份，但若下个月的标签离得太近（不足 3
        列）则省略，避免只露出几天的月份挤占标签位置。
        """
        origin = _monday(self._start)
        labels = [
            (column, monday)
            for column in range(1, self.week_count())
            if (monday := origin + dt.timedelta(days=column * 7)).day <= 7
        ]
        if not labels or labels[0][0] >= 3:
            labels.insert(0, (0, self._start))
        return labels

    def _column_progress(self, column: int) -> float:
        offset = column / max(1, self.week_count()) * STAGGER
        raw = (self.progress - offset) / max(0.05, 1.0 - STAGGER)
        return max(0.0, min(1.0, raw))

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        # 无数据时也画出空格子，让用户看到日历结构；基类只在有数据时调用
        # paint_chart，这里直接绘制。
        outer = QtCore.QRectF(self.rect()).adjusted(
            base.PADDING, base.PADDING, -base.PADDING, -base.PADDING
        )
        if self._title:
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    outer.left(),
                    outer.top(),
                    outer.width(),
                    self.theme.style(base.TITLE_STYLE).line_height,
                ),
                self._title,
                base.TITLE_STYLE,
                self.color("on_surface"),
            )
        content = self.content_rect()
        painter.save()
        self.paint_chart(painter, content)
        painter.restore()
        if self._hover_info is not None:
            self._paint_tooltip(painter, self._hover_info)

    @override
    def paint_chart(self, painter: QtGui.QPainter, rect: QtCore.QRectF) -> None:
        grid = self.grid_rect(rect)
        pitch = grid.height() / 7
        label_color = self.color("on_surface_variant")
        style = self.theme.style(LABEL_STYLE)
        origin = _monday(self._start)
        last_label_right = -1e9
        for column, day in self._month_labels():
            text = f"{day.year}年1月" if day.month == 1 else f"{day.month}月"
            left = grid.left() + column * pitch
            width = typography.text_width(text, LABEL_STYLE) + 6
            if left < last_label_right:
                continue
            typography.paint_text(
                painter,
                QtCore.QRectF(left, rect.top(), width, MONTH_HEIGHT - 4),
                text,
                LABEL_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignBottom,
                elide=False,
            )
            last_label_right = left + width
        # 星期标签：只标一、三、五，避免拥挤。
        for row in (0, 2, 4):
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    grid.left() - WEEKDAY_WIDTH,
                    grid.top() + (row + 0.5) * pitch - style.line_height / 2,
                    WEEKDAY_WIDTH - 6,
                    style.line_height,
                ),
                formatting.WEEKDAYS[row],
                LABEL_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )
        radius = max(2.0, pitch * 0.2)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        today = dt.date.today()
        day = self._start
        while day <= self._end:
            column = (_monday(day) - origin).days // 7
            progress = self._column_progress(column)
            if progress > 0:
                cell = self.cell_rect(grid, day)
                value = self._values.get(day, 0.0)
                level = analytics.level_of(value, self._thresholds)
                painter.setOpacity(progress)
                path = shape_utils.rounded_rect_path(cell, radius)
                shape_utils.fill_shape(painter, path, self.level_color(level))
                if day == self._selected:
                    shape_utils.fill_shape(
                        painter,
                        shape_utils.rounded_rect_path(
                            cell.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1
                        ),
                        None,
                        self.color("on_surface"),
                        2.0,
                    )
                elif day == self._hover_day:
                    shape_utils.fill_shape(
                        painter, path, None, self.color("on_surface"), 1.5
                    )
                elif day == today:
                    shape_utils.fill_shape(
                        painter, path, None, self.color("outline"), 1.0
                    )
            day += dt.timedelta(days=1)
        painter.setOpacity(1.0)
        self._paint_legend_scale(painter, rect, grid)
        if not self.has_data():
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    grid.left(), grid.bottom() + 6, grid.width() / 2, 24
                ),
                self._empty_text,
                base.EMPTY_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
            )

    def _paint_legend_scale(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRectF,
        grid: QtCore.QRectF,
    ) -> None:
        swatch = 12.0
        gap = 3.0
        color = self.color("on_surface_variant")
        less, more = "少", "多"
        more_width = typography.text_width(more, LABEL_STYLE)
        less_width = typography.text_width(less, LABEL_STYLE)
        total = less_width + 6 + 5 * (swatch + gap) - gap + 6 + more_width
        right = min(grid.right(), rect.right())
        x = right - total
        y = grid.bottom() + (LEGEND_HEIGHT - swatch) / 2
        typography.paint_text(
            painter,
            QtCore.QRectF(x, y - 4, less_width, swatch + 8),
            less,
            LABEL_STYLE,
            color,
            elide=False,
        )
        x += less_width + 6
        for level in range(5):
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    QtCore.QRectF(x, y, swatch, swatch), 3.0
                ),
                self.level_color(level),
            )
            x += swatch + gap
        typography.paint_text(
            painter,
            QtCore.QRectF(x - gap + 6, y - 4, more_width, swatch + 8),
            more,
            LABEL_STYLE,
            color,
            elide=False,
        )

    # ---- 交互 -------------------------------------------------------------

    @override
    def hit_test(
        self, position: QtCore.QPointF
    ) -> tuple[int, base.HoverInfo] | None:
        day = self.day_at(position)
        self._hover_day = day
        if day is None:
            return None
        value = self._values.get(day, 0.0)
        cell = self.cell_rect(self.grid_rect(self.content_rect()), day)
        level_color = self.level_color(
            analytics.level_of(value, self._thresholds)
        )
        lines = (
            self._provider(day, value)
            if self._provider is not None
            else [("数值", charts.format_value(value))]
        )
        colored = [
            (level_color if i == 0 else theme_module.TRANSPARENT, name, text)
            for i, (name, text) in enumerate(lines)
        ]
        return (day - self._start).days, base.HoverInfo(
            formatting.date_full(day),
            colored,
            QtCore.QPointF(cell.center().x(), cell.top()),
        )

    @override
    def _set_hover(self, hit: tuple[int, base.HoverInfo] | None) -> None:
        if hit is None:
            self._hover_day = None
        super()._set_hover(hit)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        super().mouseMoveEvent(event)
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if self._hover_day is not None
            else QtCore.Qt.CursorShape.ArrowCursor
        )

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            day = self.day_at(event.position())
            if day is not None:
                self._selected = None if day == self._selected else day
                self.day_clicked.emit(self._selected)
                self.update()
                event.accept()
                return
        super().mousePressEvent(event)
