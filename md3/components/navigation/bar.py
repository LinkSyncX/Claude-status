"""导航栏（Navigation bar）：底部 3–5 个目的地。"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.navigation import _items
from md3.components.navigation import destination as destination_module
from md3.core import shape as shape_utils
from md3.tokens import shape as shape_tokens

BAR_HEIGHT = 80.0
MIN_ITEMS = 3
MAX_ITEMS = 5


class LabelBehavior(enum.Enum):
    """标签显示策略。"""

    ALWAYS = "always"
    SELECTED_ONLY = "selected"
    HIDDEN = "hidden"


class NavigationBar(_items.SelectableItems):
    """底部导航栏。

    Args:
        destinations: 目的地列表（3–5 个）。
        selected_index: 初始选中下标。
        label_behavior: 标签显示策略。
        parent: 父控件。
    """

    def __init__(
        self,
        destinations: list[destination_module.Destination | str],
        selected_index: int = 0,
        label_behavior: LabelBehavior = LabelBehavior.ALWAYS,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent, horizontal_keys=True)
        self._destinations = destination_module.coerce_destinations(
            destinations
        )
        self._label_behavior = label_behavior
        self._selected = (
            selected_index
            if 0 <= selected_index < len(self._destinations)
            else -1
        )
        self._rebuild_states()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def destinations(self) -> list[destination_module.Destination]:
        """目的地列表。"""
        return list(self._destinations)

    def set_destinations(
        self, destinations: list[destination_module.Destination | str]
    ) -> None:
        """替换目的地。"""
        self._destinations = destination_module.coerce_destinations(
            destinations
        )
        self._selected = min(self._selected, len(self._destinations) - 1)
        self._rebuild_states()
        self.update()

    def set_badge(self, index: int, badge: int | str | None) -> None:
        """设置某个目的地的徽标。"""
        if 0 <= index < len(self._destinations):
            self._destinations[index].badge = badge
            self.update()

    @property
    def label_behavior(self) -> LabelBehavior:
        """标签显示策略。"""
        return self._label_behavior

    def set_label_behavior(self, behavior: LabelBehavior) -> None:
        """设置标签显示策略。"""
        self._label_behavior = behavior
        self.update()

    @override
    def item_count(self) -> int:
        return len(self._destinations)

    @override
    def item_label(self, index: int) -> str:
        if 0 <= index < len(self._destinations):
            return self._destinations[index].label
        return ""

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        rect = QtCore.QRectF(self.rect())
        count = max(1, len(self._destinations))
        width = rect.width() / count
        return self.visual_rect(
            QtCore.QRectF(
                rect.left() + index * width, rect.top(), width, rect.height()
            )
        )

    @override
    def item_enabled(self, index: int) -> bool:
        return self._destinations[index].enabled and self.isEnabled()

    @override
    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        rect = self.item_rect(index)
        indicator = QtCore.QRectF(
            rect.center().x() - destination_module.INDICATOR_WIDTH / 2,
            self._indicator_top(index),
            destination_module.INDICATOR_WIDTH,
            destination_module.INDICATOR_HEIGHT,
        )
        return shape_utils.rounded_rect_path(indicator, shape_tokens.SHAPE_FULL)

    def _show_label(self, index: int) -> bool:
        match self._label_behavior:
            case LabelBehavior.ALWAYS:
                return True
            case LabelBehavior.SELECTED_ONLY:
                return index == self._selected
            case _:
                return False

    def _indicator_top(self, index: int) -> float:
        rect = self.item_rect(index)
        label_height = (
            self.theme.style(destination_module.LABEL_STYLE).line_height
            if self._show_label(index)
            else 0.0
        )
        block = destination_module.INDICATOR_HEIGHT + (
            destination_module.LABEL_GAP + label_height if label_height else 0
        )
        return rect.center().y() - block / 2

    @override
    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(360, int(BAR_HEIGHT))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(int(48 * MIN_ITEMS), int(BAR_HEIGHT))

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        painter.fillRect(self.rect(), self.color("surface_container"))
        for index, destination in enumerate(self._destinations):
            destination_module.paint_destination(
                painter,
                self.item_rect(index),
                destination,
                index == self._selected,
                self.progress(index),
                self._show_label(index),
                enabled=self.isEnabled(),
                theme=self.theme,
                rtl=self.is_rtl(),
            )
            self.paint_item_overlays(painter, index)
