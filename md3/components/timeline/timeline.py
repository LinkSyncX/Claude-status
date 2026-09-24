"""时间线（Timeline）。

竖直排列的一串事件：左侧可选的时间列、中间的节点（圆点或图标）与连接
线、右侧的标题与说明。节点颜色按项的 ``color`` 色彩角色绘制，说明文字
自动换行，控件高度随内容变化。RTL 下整体镜像。
"""

from __future__ import annotations

import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

DOT_SIZE = 12.0
ICON_NODE_SIZE = 32.0
ICON_SIZE = 18.0
LINE_WIDTH = 2.0
TIME_COLUMN_WIDTH = 72.0
NODE_COLUMN_WIDTH = 40.0
CONTENT_GAP = 12.0
ITEM_GAP = 16.0
MIN_ITEM_HEIGHT = 40.0
TITLE_STYLE = typography_tokens.TypeRole.TITLE_SMALL
DESCRIPTION_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
TIME_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM


@dataclasses.dataclass
class TimelineItem:
    """时间线上的一项。

    Attributes:
        title: 标题。
        description: 说明文字，可多行。
        time: 时间列文字。
        icon: 节点图标；None 时显示圆点。
        color: 节点色彩角色。
        active: 为真时节点填充色更醒目（当前 / 已完成）。
        key: 业务侧标识。
    """

    title: str
    description: str = ""
    time: str = ""
    icon: icons.IconLike = None
    color: str = "primary"
    active: bool = True
    key: Any = None


class Timeline(widget.MaterialWidget):
    """时间线。

    Args:
        items: 初始项。
        show_time: 是否显示时间列。
        parent: 父控件。
    """

    def __init__(
        self,
        items: list[TimelineItem] | None = None,
        show_time: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[TimelineItem] = list(items or [])
        self._show_time = show_time
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    # ---- 项 ---------------------------------------------------------------

    @property
    def items(self) -> list[TimelineItem]:
        """全部项。"""
        return list(self._items)

    def set_items(self, items: list[TimelineItem]) -> None:
        """替换全部项。"""
        self._items = list(items)
        self.updateGeometry()
        self.update()

    def add_item(self, item: TimelineItem) -> TimelineItem:
        """追加一项。"""
        self._items.append(item)
        self.updateGeometry()
        self.update()
        return item

    def clear(self) -> None:
        """移除全部项。"""
        self.set_items([])

    @property
    def show_time(self) -> bool:
        """是否显示时间列。"""
        return self._show_time

    # ---- 几何 -------------------------------------------------------------

    def _time_width(self) -> float:
        return TIME_COLUMN_WIDTH if self._show_time else 0.0

    def _content_left(self) -> float:
        return self._time_width() + NODE_COLUMN_WIDTH + CONTENT_GAP

    def _content_width(self, total_width: float) -> float:
        return max(40.0, total_width - self._content_left() - 8.0)

    def item_height(self, item: TimelineItem, width: float) -> float:
        """某一项在给定控件宽度下的高度。"""
        height = self.theme.style(TITLE_STYLE).line_height
        if item.description:
            height += typography.text_size(
                item.description, DESCRIPTION_STYLE, self._content_width(width)
            ).height()
        return max(MIN_ITEM_HEIGHT, height)

    def item_rect(
        self, index: int, width: float | None = None
    ) -> QtCore.QRectF:
        """第 index 项占用的（逻辑）矩形。"""
        width = float(self.width()) if width is None else width
        y = 0.0
        for current, item in enumerate(self._items):
            height = self.item_height(item, width)
            if current == index:
                return QtCore.QRectF(0.0, y, width, height)
            y += height + ITEM_GAP
        return QtCore.QRectF()

    def total_height(self, width: float | None = None) -> float:
        """全部项的总高度。"""
        width = float(self.width()) if width is None else width
        if not self._items:
            return 0.0
        return sum(
            self.item_height(item, width) for item in self._items
        ) + ITEM_GAP * (len(self._items) - 1)

    @override
    def hasHeightForWidth(self) -> bool:
        return True

    @override
    def heightForWidth(self, width: int) -> int:
        return round(self.total_height(max(1.0, float(width))))

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = float(self.width()) if self.width() > 0 else 360.0
        return typography.size_hint(width, self.total_height(width))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return typography.size_hint(
            self._content_left() + 80.0, self.total_height(240.0)
        )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.updateGeometry()

    # ---- 绘制 -------------------------------------------------------------

    def _node_rect(
        self, item: TimelineItem, rect: QtCore.QRectF
    ) -> QtCore.QRectF:
        size = ICON_NODE_SIZE if item.icon is not None else DOT_SIZE
        center_x = self._time_width() + NODE_COLUMN_WIDTH / 2
        title_height = self.theme.style(TITLE_STYLE).line_height
        return QtCore.QRectF(
            center_x - size / 2,
            rect.top() + title_height / 2 - size / 2,
            size,
            size,
        )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        if not self._items:
            return
        line_x = self._time_width() + NODE_COLUMN_WIDTH / 2
        rects = [self.item_rect(index) for index in range(len(self._items))]
        nodes = [
            self._node_rect(item, rect)
            for item, rect in zip(self._items, rects, strict=True)
        ]
        # 连接线：相邻节点之间。
        for start, end in zip(nodes, nodes[1:], strict=False):
            painter.fillRect(
                self.visual_rect(
                    QtCore.QRectF(
                        line_x - LINE_WIDTH / 2,
                        start.bottom() + 4,
                        LINE_WIDTH,
                        max(0.0, end.top() - start.bottom() - 8),
                    )
                ),
                self.color("outline_variant"),
            )
        for item, rect, node in zip(self._items, rects, nodes, strict=True):
            self._paint_item(painter, item, rect, node)

    def _paint_item(
        self,
        painter: QtGui.QPainter,
        item: TimelineItem,
        rect: QtCore.QRectF,
        node: QtCore.QRectF,
    ) -> None:
        accent = self.color(
            item.color if self.theme.has_color(item.color) else "primary"
        )
        visual_node = self.visual_rect(node)
        if item.icon is not None:
            fill = (
                accent
                if item.active
                else self.color("surface_container_highest")
            )
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    visual_node, shape_tokens.SHAPE_FULL
                ),
                fill,
            )
            icon = icons.coerce(item.icon, ICON_SIZE)
            if icon is not None:
                on_role = f"on_{item.color}"
                content = (
                    self.color(on_role)
                    if item.active and self.theme.has_color(on_role)
                    else self.color("on_surface_variant")
                )
                icon.paint(
                    painter,
                    QtCore.QRectF(
                        visual_node.center().x() - ICON_SIZE / 2,
                        visual_node.center().y() - ICON_SIZE / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    ),
                    content,
                )
        else:
            painter.save()
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            if item.active:
                painter.setBrush(accent)
                painter.drawEllipse(visual_node)
            else:
                painter.setBrush(self.color("surface"))
                painter.drawEllipse(visual_node)
                painter.setPen(QtGui.QPen(self.color("outline"), LINE_WIDTH))
                painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
                painter.drawEllipse(visual_node.adjusted(1, 1, -1, -1))
            painter.restore()
        title_height = self.theme.style(TITLE_STYLE).line_height
        if self._show_time and item.time:
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        0.0, rect.top(), TIME_COLUMN_WIDTH - 8.0, title_height
                    )
                ),
                item.time,
                TIME_STYLE,
                self.color("on_surface_variant"),
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )
        left = self._content_left()
        width = self._content_width(rect.width())
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(left, rect.top(), width, title_height)
            ),
            item.title,
            TITLE_STYLE,
            self.color("on_surface"),
            self.start_alignment(),
        )
        if item.description:
            typography.paint_multiline(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        left,
                        rect.top() + title_height,
                        width,
                        rect.height() - title_height,
                    )
                ),
                item.description,
                DESCRIPTION_STYLE,
                self.color("on_surface_variant"),
                alignment=self.start_alignment(),
            )
