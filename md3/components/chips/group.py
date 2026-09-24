"""纸片组（Chip group）。

把一组纸片按流式布局排列，超出宽度自动换行；可管理过滤纸片的单选 /
多选，并在输入纸片被移除时把它从组中删掉。纸片增删后其余纸片会滑动到
新位置。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.chips import chip as chip_module
from md3.core import animation
from md3.core import widget
from md3.tokens import motion

SPACING = 8.0
ROW_SPACING = 8.0


class ChipGroup(widget.MaterialWidget):
    """纸片组。

    Args:
        chips: 初始纸片；字符串按 ``kind`` 转换为纸片。
        kind: 字符串成员的纸片类型。
        single_selection: 为真时过滤纸片互斥（单选）。
        spacing: 同一行纸片之间的距离（dp）。
        row_spacing: 行距（dp）。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(list)
    chip_removed = QtCore.Signal(str)

    def __init__(
        self,
        chips: Sequence[chip_module.Chip | str] = (),
        kind: chip_module.ChipKind = chip_module.ChipKind.FILTER,
        single_selection: bool = False,
        spacing: float = SPACING,
        row_spacing: float = ROW_SPACING,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._chips: list[chip_module.Chip] = []
        self._kind = kind
        self._single = single_selection
        self._spacing = spacing
        self._row_spacing = row_spacing
        self._syncing = False
        self._animate_moves = True
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        for item in chips:
            self.add_chip(item)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Grouping

    # ---- 成员 -------------------------------------------------------------

    @property
    def chips(self) -> list[chip_module.Chip]:
        """全部纸片。"""
        return list(self._chips)

    @property
    def texts(self) -> list[str]:
        """全部纸片的文字。"""
        return [chip.text for chip in self._chips]

    def add_chip(self, item: chip_module.Chip | str) -> chip_module.Chip:
        """追加一个纸片并返回它。"""
        chip = self._coerce(item)
        chip.setParent(self)
        chip.show()
        self._chips.append(chip)
        chip.toggled.connect(
            lambda checked, c=chip: self._on_toggled(c, checked)
        )
        chip.removed.connect(lambda c=chip: self.remove_chip(c))
        self.updateGeometry()
        self._relayout(animate=False, newcomer=chip)
        return chip

    def _coerce(self, item: chip_module.Chip | str) -> chip_module.Chip:
        if isinstance(item, chip_module.Chip):
            return item
        return chip_module.Chip(item, self._kind)

    def remove_chip(self, target: chip_module.Chip | int | str) -> None:
        """移除纸片（可按对象、下标或文字）。"""
        chip = self._find(target)
        if chip is None:
            return
        self._chips.remove(chip)
        chip.hide()
        chip.setParent(None)
        chip.deleteLater()
        self.chip_removed.emit(chip.text)
        self.updateGeometry()
        self._relayout(animate=True)
        if chip.selected:
            self.selection_changed.emit(self.selected_indices)

    def clear(self) -> None:
        """移除全部纸片。"""
        for chip in list(self._chips):
            self._chips.remove(chip)
            chip.hide()
            chip.setParent(None)
            chip.deleteLater()
        self.updateGeometry()
        self.update()

    def _find(
        self, target: chip_module.Chip | int | str
    ) -> chip_module.Chip | None:
        if isinstance(target, chip_module.Chip):
            return target if target in self._chips else None
        if isinstance(target, int):
            return (
                self._chips[target] if 0 <= target < len(self._chips) else None
            )
        for chip in self._chips:
            if chip.text == target:
                return chip
        return None

    # ---- 选择 -------------------------------------------------------------

    @property
    def selected_indices(self) -> list[int]:
        """已选中纸片的下标。"""
        return [i for i, chip in enumerate(self._chips) if chip.selected]

    @property
    def selected_texts(self) -> list[str]:
        """已选中纸片的文字。"""
        return [chip.text for chip in self._chips if chip.selected]

    def set_selected(self, indices: Sequence[int]) -> None:
        """设置选中集合（单选模式只保留第一个）。"""
        wanted = set(indices)
        if self._single and len(wanted) > 1:
            wanted = {min(wanted)}
        self._syncing = True
        try:
            for index, chip in enumerate(self._chips):
                chip.set_selected(index in wanted)
        finally:
            self._syncing = False
        self.selection_changed.emit(self.selected_indices)

    def clear_selection(self) -> None:
        """取消全部选中。"""
        self.set_selected([])

    def _on_toggled(self, chip: chip_module.Chip, checked: bool) -> None:
        if self._syncing:
            return
        if self._single and checked:
            self._syncing = True
            try:
                for other in self._chips:
                    if other is not chip:
                        other.set_selected(False)
            finally:
                self._syncing = False
        self.selection_changed.emit(self.selected_indices)

    # ---- 布局 -------------------------------------------------------------

    def positions(self, width: float) -> list[QtCore.QRect]:
        """在给定宽度下每个纸片的矩形（流式换行，RTL 下自右向左排）。"""
        rects: list[QtCore.QRect] = []
        x = y = 0.0
        row_height = 0.0
        rtl = self.is_rtl()
        for chip in self._chips:
            size = chip.sizeHint()
            if x > 0 and x + size.width() > width:
                x = 0.0
                y += row_height + self._row_spacing
                row_height = 0.0
            left = width - x - size.width() if rtl else x
            rects.append(
                QtCore.QRect(round(left), round(y), size.width(), size.height())
            )
            x += size.width() + self._spacing
            row_height = max(row_height, size.height())
        return rects

    @override
    def hasHeightForWidth(self) -> bool:
        return True

    @override
    def heightForWidth(self, width: int) -> int:
        rects = self.positions(max(1, width))
        if not rects:
            return 0
        return max(rect.bottom() + 1 for rect in rects)

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = self.width() if self.width() > 0 else 480
        return QtCore.QSize(width, self.heightForWidth(width))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        widest = max(
            (chip.sizeHint().width() for chip in self._chips), default=0
        )
        return QtCore.QSize(widest, self.heightForWidth(max(1, self.width())))

    def _relayout(
        self, animate: bool, newcomer: chip_module.Chip | None = None
    ) -> None:
        rects = self.positions(max(1, self.width()))
        for chip, rect in zip(self._chips, rects, strict=True):
            if chip is newcomer or not animate or not self._animate_moves:
                chip.setGeometry(rect)
            elif chip.pos() != rect.topLeft():
                chip.resize(rect.size())
                animation.run_property_animation(
                    chip,
                    b"pos",
                    rect.topLeft(),
                    motion.MEDIUM2,
                    motion.EMPHASIZED_DECELERATE,
                )
        self.update()

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout(animate=False)
        self.updateGeometry()
