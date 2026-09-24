"""Icons 页面：SVG 图标接入、内置形状库与 Material Symbols 图库。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import chips
from md3.components import icon_gallery
from md3.components import selection
from md3.components import snackbar
from md3.components import text_fields
from md3.core import typography
from md3.core import widget
from md3.demo.pages import _common
from md3.theme import icons

SYMBOL_LIMIT = 200
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
<circle cx="8" cy="8" r="6" fill="#4285F4"/>
<circle cx="16" cy="8" r="6" fill="#EA4335" opacity="0.9"/>
<circle cx="8" cy="16" r="6" fill="#FBBC05" opacity="0.9"/>
<circle cx="16" cy="16" r="6" fill="#34A853" opacity="0.9"/>
</svg>"""


class _SizeRow(widget.MaterialWidget):
    """同一 SVG 在不同尺寸、不同色彩角色下的渲染。"""

    SIZES = (16, 24, 32, 48, 64)
    ROLES = ("primary", "secondary", "tertiary", "error", "on_surface")

    def __init__(
        self, name: str, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._name = name
        self.setFixedHeight(72)
        self.setMinimumWidth(sum(self.SIZES) + 24 * len(self.SIZES))

    def paint(self, painter: QtGui.QPainter) -> None:  # noqa: D102
        x = 0.0
        for size, role in zip(self.SIZES, self.ROLES, strict=True):
            icon = icons.coerce(self._name, size)
            rect = QtCore.QRectF(x, (self.height() - size) / 2, size, size)
            icon.paint(painter, rect, self.color(role))
            x += size + 24


def _copy_name(page: QtWidgets.QWidget, name: str) -> None:
    QtWidgets.QApplication.clipboard().setText(name)
    snackbar.show(page, f"已复制图标名：{name}")


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "图标",
        "所有接受图标的组件都可以传入 Material Symbols 图标名、SVG 文件路径、"
        "SvgIcon 对象或注册到图标库中的名称；点击图库中的图标可复制其名称。",
    )

    logo = icons.SvgIcon.from_data(LOGO_SVG, tint=False, name="logo")
    usage = page.section(
        "SVG 图标接入",
        "随包形状库以 shapes/ 前缀注册；彩色 SVG 可用 tint=False 保留原色。",
    )
    page.row(
        usage,
        [
            buttons.FilledButton("形状", icon="shapes/soft_burst"),
            buttons.FilledTonalButton("Logo", icon=logo),
            buttons.OutlinedButton("胶囊", icon="shapes/pill"),
            buttons.IconButton("shapes/heart", tooltip="shapes/heart"),
            buttons.IconButton(
                "shapes/heart",
                variant=buttons.IconButtonVariant.FILLED,
                checkable=True,
                checked=True,
            ),
            buttons.FloatingActionButton(icon="shapes/sunny"),
            chips.AssistChip("宝石", icon="shapes/gem"),
            chips.FilterChip("花朵", icon="shapes/flower", selected=True),
            selection.Switch("", checked=True),
        ],
        gap=12,
    )
    field = text_fields.OutlinedTextField(
        "带 SVG 前置图标", leading_icon="shapes/clover_4_leaf"
    )
    field.setMaximumWidth(320)
    usage.addWidget(field)
    usage.addWidget(
        typography.Label(
            "同一 SVG 按尺寸等比缩放，并以内容色着色：",
            "body-medium",
            "on_surface_variant",
        )
    )
    usage.addWidget(_SizeRow("shapes/very_sunny"))

    shapes_section = page.section(
        "内置形状图库",
        "M3 Expressive 形状库的 33 个形状，由 md3.core.polygon 生成为带精确圆弧"
        "的 SVG。",
    )
    shapes = icon_gallery.IconGallery(icons.svg_names("shapes/"))
    shapes.icon_clicked.connect(lambda name: _copy_name(page, name))
    shapes_section.addWidget(shapes)

    symbols_section = page.section(
        "Material Symbols 图库", f"输入关键字搜索，最多显示 {SYMBOL_LIMIT} 个。"
    )
    controls = QtWidgets.QHBoxLayout()
    controls.setSpacing(16)
    search = text_fields.OutlinedTextField(
        "搜索图标", placeholder="例如 home、arrow、check", leading_icon="search"
    )
    search.setMaximumWidth(360)
    controls.addWidget(search)
    fill_switch = selection.Switch("填充样式")
    controls.addWidget(fill_switch)
    count = typography.Label("", "label-large", "on_surface_variant")
    controls.addWidget(count)
    controls.addStretch()
    symbols_section.addLayout(controls)
    symbols = icon_gallery.IconGallery(
        icons.search_icons("", limit=SYMBOL_LIMIT)
    )
    symbols.icon_clicked.connect(lambda name: _copy_name(page, name))
    symbols_section.addWidget(symbols)

    def refresh(query: str) -> None:
        names = icons.search_icons(query, limit=SYMBOL_LIMIT)
        symbols.set_icons(names)
        total = len(icons.search_icons(query, limit=10_000))
        count.setText(f"匹配 {total} 个" if query else f"共 {total} 个")

    search.text_changed.connect(refresh)
    fill_switch.toggled.connect(symbols.set_fill)
    refresh("")

    custom_section = page.section(
        "从文件夹加载 SVG",
        "选择一个包含 *.svg 的文件夹，注册为 custom/ 前缀的图标"
        "（*_filled.svg 自动作为同名图标的填充版）。",
    )
    load = buttons.OutlinedButton("选择文件夹…", icon="folder_open")
    loaded = typography.Label("", "body-medium", "on_surface_variant")
    page.row(custom_section, [load, loaded])
    custom = icon_gallery.IconGallery()
    custom.icon_clicked.connect(lambda name: _copy_name(page, name))
    custom_section.addWidget(custom)

    def choose_directory() -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            page, "选择 SVG 文件夹"
        )
        if not directory:
            return
        names = icons.register_svg_directory(directory, prefix="custom/")
        custom.set_icons(names)
        loaded.setText(f"已注册 {len(names)} 个图标")

    load.clicked.connect(choose_directory)
    page.finish()
    return page
