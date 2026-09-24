"""额度条：一行显示窗口名称、用量进度与"百分比 · 重置时间"。"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
import datetime as dt
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.tokens import shape as shape_tokens

from claude_status import formatting
from claude_status import quota as quota_module

WARNING_PERCENT = 70.0
CRITICAL_PERCENT = 90.0


@dataclasses.dataclass(frozen=True)
class QuotaLine:
    """一行额度的展示内容。"""

    title: str
    percent: float | None
    text: str


def level_role(percent: float) -> str:
    """用量对应的颜色角色。"""
    if percent >= CRITICAL_PERCENT:
        return "error"
    if percent >= WARNING_PERCENT:
        return "warning"
    return "primary"


def _line(
    title: str,
    quota: quota_module.Quota,
    window: quota_module.Window | None,
    span: dt.timedelta,
    now: dt.datetime,
) -> QuotaLine | None:
    state = quota.state(window, span, now)
    if state is None:
        return None
    if state.reset:
        return QuotaLine(title, 0.0, "0% · 已重置")
    text = f"{state.percent:.0f}%"
    if state.resets_at is not None:
        text += " · " + formatting.reset_text(state.resets_at, now)
    else:
        text += " · " + formatting.ago(quota.fetched_at, "采样", now)
    return QuotaLine(title, state.percent, text)


def quota_lines(
    quota: quota_module.Quota | None,
    now: dt.datetime | None = None,
    include_scoped: bool = False,
) -> list[QuotaLine]:
    """额度的各行（5 小时、本周，可选按模型的周额度）。"""
    if quota is None:
        return []
    now = now or dt.datetime.now().astimezone()
    lines = [
        _line("5 小时", quota, quota.five_hour, quota_module.FIVE_HOURS, now),
        _line("本周", quota, quota.seven_day, quota_module.ONE_WEEK, now),
    ]
    if include_scoped:
        for window in quota.scoped:
            lines.append(
                _line(
                    f"本周 · {window.label}",
                    quota,
                    window,
                    quota_module.ONE_WEEK,
                    now,
                )
            )
    return [line for line in lines if line is not None]


def describe_source(quota: quota_module.Quota | None) -> str:
    """额度来源与更新时间的说明。"""
    if quota is None:
        return ""
    return f"来源：{quota.source.label} · {formatting.ago(quota.fetched_at, '更新')}"


class QuotaMeter(widget.MaterialWidget):
    """一行额度：标题、进度条与右侧的“百分比 · 重置时间”。

    一组额度条可以用 ``align`` 统一标题列与文字列的宽度，使进度条等长。

    Args:
        title_width: 标题列宽度。
        role: 固定的进度条颜色角色；为 None 时按用量显示正常 / 警告 / 危险色
            （占比条等不表示额度的场合使用固定颜色）。
        parent: 父控件。
    """

    HEIGHT = 20.0
    BAR_HEIGHT = 6.0
    STYLE = typography.TypeRole.LABEL_MEDIUM
    GAP = 10.0
    SEPARATOR = " · "

    def __init__(
        self,
        title_width: float = 40.0,
        role: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title_width = title_width
        self._role = role
        self._text_column = 0.0
        self._line = QuotaLine("", None, "")
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_line(self, line: QuotaLine) -> None:
        """更新内容。"""
        self._line = line
        self.updateGeometry()
        self.update()

    def set_columns(self, title: float, text: float) -> None:
        """设置标题列宽度与文字列的最小宽度（用于一组额度条对齐）。"""
        self._title_width = title
        self._text_column = text
        self.updateGeometry()
        self.update()

    def _parts(self) -> tuple[str, str]:
        """文字分为强调的百分比与其后的说明。"""
        head, separator, tail = self._line.text.partition(self.SEPARATOR)
        return head, separator + tail

    def _text_width(self) -> float:
        return max(measure(self._line.text), self._text_column)

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = self._title_width + 120 + self._text_width() + 2 * self.GAP
        return typography.size_hint(width, self.HEIGHT)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        width = self._title_width + 40 + self._text_width() + 2 * self.GAP
        return typography.size_hint(width, self.HEIGHT)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        typography.paint_text(
            painter,
            QtCore.QRectF(rect.left(), rect.top(), self._title_width, rect.height()),
            self._line.title,
            self.STYLE,
            self.color("on_surface_variant"),
        )
        percent = self._line.percent
        head, tail = self._parts()
        role = self._fill_role()
        head_color = self.color(
            role if role in ("warning", "error") and not self._role else "on_surface"
        )
        tail_width = measure(tail) if tail else 0.0
        head_width = measure(head)
        right = rect.right()
        for part, width, color in (
            (tail, tail_width, self.color("on_surface_variant")),
            (head, head_width, head_color),
        ):
            if not part:
                continue
            typography.paint_text(
                painter,
                QtCore.QRectF(right - width, rect.top(), width, rect.height()),
                part,
                self.STYLE,
                color,
                QtCore.Qt.AlignmentFlag.AlignRight
                | QtCore.Qt.AlignmentFlag.AlignVCenter,
                elide=False,
            )
            right -= width
        left = rect.left() + self._title_width + self.GAP
        bar_right = rect.right() - self._text_width() - self.GAP
        if bar_right - left < 8:
            return
        track = QtCore.QRectF(
            left,
            rect.center().y() - self.BAR_HEIGHT / 2,
            bar_right - left,
            self.BAR_HEIGHT,
        )
        # 与 md3 线性进度条一致：轨道用 secondary_container，在描边卡片与
        # 填充卡片（surface_container_highest 背景）上都看得见。
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(track, shape_tokens.SHAPE_FULL),
            self.color("secondary_container"),
        )
        if percent is None or percent <= 0:
            return
        fill = QtCore.QRectF(track)
        fill.setWidth(max(self.BAR_HEIGHT, track.width() * min(1.0, percent / 100)))
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(fill, shape_tokens.SHAPE_FULL),
            self.color(role),
        )

    def _fill_role(self) -> str:
        if self._role:
            return self._role
        percent = self._line.percent
        return level_role(percent) if percent is not None else "primary"


def measure(text: str) -> float:
    """额度条文字的宽度。"""
    return typography.text_width(text, QuotaMeter.STYLE) + 2 if text else 0.0


def title_width(lines: Sequence[QuotaLine]) -> float:
    """让一组额度条的标题列对齐、又不多占宽度的标题宽度。"""
    widest = max(
        (typography.text_width(line.title, QuotaMeter.STYLE) for line in lines),
        default=0.0,
    )
    return widest + 4


def align(meters: Sequence[QuotaMeter], lines: Sequence[QuotaLine]) -> None:
    """设置一组额度条的内容，并统一标题列与文字列宽度，使进度条等长。"""
    title = title_width(lines)
    text = max((measure(line.text) for line in lines), default=0.0)
    for meter, line in zip(meters, lines, strict=False):
        meter.set_columns(title, text)
        meter.set_line(line)
