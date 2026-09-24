"""额度条：一行显示窗口名称、用量进度与"百分比 · 重置时间"。"""

from __future__ import annotations

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
        text += f" · 采样于 {formatting.relative(quota.fetched_at, now)}"
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
    return f"来源：{quota.source.label} · 更新于 {formatting.relative(quota.fetched_at)}"


class QuotaMeter(widget.MaterialWidget):
    """一行额度。

    Args:
        title_width: 标题列宽度。
        parent: 父控件。
    """

    HEIGHT = 20.0
    BAR_HEIGHT = 6.0
    STYLE = typography.TypeRole.LABEL_MEDIUM
    GAP = 8.0

    def __init__(
        self,
        title_width: float = 40.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title_width = title_width
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

    def _text_width(self) -> float:
        return typography.text_width(self._line.text, self.STYLE) + 2

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
        muted = self.color("on_surface_variant")
        typography.paint_text(
            painter,
            QtCore.QRectF(rect.left(), rect.top(), self._title_width, rect.height()),
            self._line.title,
            self.STYLE,
            muted,
        )
        text_width = self._text_width()
        typography.paint_text(
            painter,
            QtCore.QRectF(
                rect.right() - text_width, rect.top(), text_width, rect.height()
            ),
            self._line.text,
            self.STYLE,
            self.color("on_surface"),
            QtCore.Qt.AlignmentFlag.AlignRight
            | QtCore.Qt.AlignmentFlag.AlignVCenter,
            elide=False,
        )
        left = rect.left() + self._title_width + self.GAP
        right = rect.right() - text_width - self.GAP
        if right - left < 8:
            return
        track = QtCore.QRectF(
            left,
            rect.center().y() - self.BAR_HEIGHT / 2,
            right - left,
            self.BAR_HEIGHT,
        )
        # 与 md3 线性进度条一致：轨道用 secondary_container，在描边卡片与
        # 填充卡片（surface_container_highest 背景）上都看得见。
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(track, shape_tokens.SHAPE_FULL),
            self.color("secondary_container"),
        )
        percent = self._line.percent
        if percent is None or percent <= 0:
            return
        fill = QtCore.QRectF(track)
        fill.setWidth(max(self.BAR_HEIGHT, track.width() * min(1.0, percent / 100)))
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(fill, shape_tokens.SHAPE_FULL),
            self.color(level_role(percent)),
        )


def title_width(lines: list[QuotaLine]) -> float:
    """让一组额度条的标题列对齐、又不多占宽度的标题宽度。"""
    widest = max(
        (typography.text_width(line.title, QuotaMeter.STYLE) for line in lines),
        default=0.0,
    )
    return widest + 4
