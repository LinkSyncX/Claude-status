"""主题控制面板：种子色、配色变体、对比度等级与明暗切换。"""

from __future__ import annotations

from typing import override

from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.components import buttons
from md3.components import menus
from md3.components import pickers
from md3.components import selection
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens

PRESET_SEEDS = (
    ("#6750A4", "紫"),
    ("#0061A4", "蓝"),
    ("#006D3A", "绿"),
    ("#B3261E", "红"),
    ("#7D5700", "琥珀"),
    ("#006A6A", "青"),
)
CONTRAST_LEVELS = (
    ("标准", md3.ContrastLevel.STANDARD),
    ("中", md3.ContrastLevel.MEDIUM),
    ("高", md3.ContrastLevel.HIGH),
)


class SeedSwatch(widget.InteractiveWidget):
    """可点击的种子色色块。"""

    def __init__(
        self, seed: str, tooltip: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._seed = seed
        self.setToolTip(tooltip)
        self.setFixedSize(40, 40)
        self.set_outer_margin(4.0)

    @property
    def seed(self) -> str:
        """十六进制种子色。"""
        return self._seed

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_FULL

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        path = self.container_path()
        shape_utils.fill_shape(painter, path, QtGui.QColor(self._seed))
        if self.theme.seed == theme_module.parse_seed(self._seed):
            shape_utils.fill_shape(
                painter, path, None, self.color("on_surface"), 2.0
            )


class ThemePanel(QtWidgets.QWidget):
    """放在顶部应用栏下方的主题控制条。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(24, 8, 24, 8)
        layout.setSpacing(12)
        layout.addWidget(
            typography.Label("种子色", "label-large", "on_surface_variant")
        )
        for seed, name in PRESET_SEEDS:
            swatch = SeedSwatch(seed, name)
            swatch.clicked.connect(lambda s=seed: md3.set_seed(s))
            layout.addWidget(swatch)
        custom = buttons.OutlinedButton("自定义…", icon="palette")
        custom.clicked.connect(self._pick_custom)
        layout.addWidget(custom)
        layout.addSpacing(12)
        self._variant = menus.DropdownMenu(
            [variant.value.replace("_", " ") for variant in md3.Variant],
            label="配色变体",
            selected_index=list(md3.Variant).index(md3.current_theme().variant),
        )
        self._variant.selection_changed.connect(self._on_variant)
        layout.addWidget(self._variant)
        layout.addSpacing(12)
        layout.addWidget(
            typography.Label("对比度", "label-large", "on_surface_variant")
        )
        self._contrast = buttons.SegmentedButton(
            [label for label, _ in CONTRAST_LEVELS],
            selected={self._contrast_index(md3.current_theme())},
            show_check_icon=False,
        )
        self._contrast.selection_changed.connect(self._on_contrast)
        layout.addWidget(self._contrast)
        layout.addStretch()
        self._dark = selection.Switch(
            "暗色模式", checked=md3.current_theme().dark, show_icons=True
        )
        self._dark.toggled.connect(md3.set_dark)
        layout.addWidget(self._dark)
        md3.theme_manager().theme_changed.connect(self._on_theme_changed)

    @staticmethod
    def _contrast_index(theme: theme_module.Theme) -> int:
        for index, (_label, level) in enumerate(CONTRAST_LEVELS):
            if level.value == theme.contrast:
                return index
        return 0

    def _on_contrast(self, indices: list[int]) -> None:
        if indices:
            md3.set_contrast(CONTRAST_LEVELS[indices[0]][1])

    def _pick_custom(self) -> None:
        dialog = pickers.ColorPickerDialog(
            theme_module.qcolor(md3.current_theme().seed),
            headline="选择种子色",
            presets=[seed for seed, _ in PRESET_SEEDS],
            parent=self,
        )
        dialog.color_selected.connect(md3.set_seed)
        dialog.open()

    def _on_variant(self, index: int) -> None:
        variant = list(md3.Variant)[index]
        md3.set_seed(md3.current_theme().seed, variant)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        if self._dark.checked != theme.dark:
            self._dark.set_checked(theme.dark)
        index = self._contrast_index(theme)
        if self._contrast.selected_indices != [index]:
            self._contrast.set_selected({index})
        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window,
            theme.color("surface_container_low"),
        )
        self.setPalette(palette)
        self.setAutoFillBackground(True)
