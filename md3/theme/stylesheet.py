"""为原生 Qt 控件生成与 M3 主题一致的 QSS。

M3 组件均为自绘，无需样式表；这里处理的是应用中仍会出现的原生控件：
按钮、输入框、下拉框、数字框、复选框 / 单选框、滑块、进度条、标签页、
分组框、分割条、菜单栏、工具栏、停靠窗口、表头、滚动条与提示，使它们
的配色、圆角与状态层和主题一致。

复选框勾号、下拉箭头等需要位图的部分由 Material Symbols 渲染到临时目录
（含 ``@2x`` 版本），按颜色缓存，主题切换时重新生成。

注意：应用级样式表不得包含字体规则（``font-size`` 等），否则会覆盖
控件自身通过 ``setFont`` 设置的排版角色。M3 组件内嵌的编辑器会自行把
边框 / 内边距重置为零，因此这里的 ``QLineEdit`` 规则不会影响它们。
"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui

from md3.color import blend
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import color as color_tokens
from md3.tokens import shape
from md3.tokens import state

_icon_dir: QtCore.QTemporaryDir | None = None
_icon_files: dict[tuple, str] = {}


def _hex(argb: int, alpha: float | None = None) -> str:
    if alpha is None:
        return color_tokens.argb_to_hex(argb)
    red = color_tokens.red_of(argb)
    green = color_tokens.green_of(argb)
    blue = color_tokens.blue_of(argb)
    return f"rgba({red}, {green}, {blue}, {alpha:.3f})"


def _layered(foreground: int, background: int, opacity: float) -> str:
    """把状态层（前景色 × 不透明度）叠到不透明背景上得到的颜色。"""
    return _hex(
        blend.alpha_composite(
            color_tokens.with_alpha(foreground, opacity), background
        )
    )


def _icon_directory() -> str:
    global _icon_dir  # pylint: disable=global-statement
    if _icon_dir is None or not _icon_dir.isValid():
        _icon_dir = QtCore.QTemporaryDir()
    return _icon_dir.path()


def icon_url(name: str, argb: int, size: int = 24, fill: bool = False) -> str:
    """把 Material Symbols 图标渲染为 PNG 并返回 QSS ``url(...)``。

    图标缺失（未下载字体）时返回 ``none``，控件退回平台默认绘制。
    """
    key = (name, argb, size, fill)
    cached = _icon_files.get(key)
    if cached is not None:
        return f"url({cached})"
    icon = icons.Icon(name, size, fill=fill)
    color = theme_module.qcolor(argb)
    base = f"{_icon_directory()}/{name}_{argb & 0xFFFFFFFF:08x}_{size}"
    if fill:
        base += "_fill"
    path = f"{base}.png"
    pixmap = icon.pixmap(color, 1.0)
    if pixmap.isNull() or not pixmap.save(path, "PNG"):
        return "none"
    icon.pixmap(color, 2.0).save(f"{base}@2x.png", "PNG")
    _icon_files[key] = path
    return f"url({path})"


def dot_url(argb: int, box: int = 16, diameter: int = 10) -> str:
    """渲染一个居中的实心圆点（单选框选中态）并返回 ``url(...)``。"""
    key = ("dot", argb, box, diameter)
    cached = _icon_files.get(key)
    if cached is not None:
        return f"url({cached})"
    base = f"{_icon_directory()}/dot_{argb & 0xFFFFFFFF:08x}_{box}_{diameter}"
    path = f"{base}.png"
    for ratio, suffix in ((1, ""), (2, "@2x")):
        pixmap = QtGui.QPixmap(box * ratio, box * ratio)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(theme_module.qcolor(argb))
        offset = (box - diameter) / 2 * ratio
        painter.drawEllipse(
            QtCore.QRectF(offset, offset, diameter * ratio, diameter * ratio)
        )
        painter.end()
        if not pixmap.save(f"{base}{suffix}.png", "PNG"):
            return "none"
    _icon_files[key] = path
    return f"url({path})"


def build_stylesheet(theme: theme_module.Theme) -> str:
    """由主题生成应用级 QSS 字符串。"""
    return "\n".join(
        (
            _base_rules(theme),
            _menu_rules(theme),
            _scroll_rules(theme),
            _button_rules(theme),
            _field_rules(theme),
            _choice_rules(theme),
            _slider_progress_rules(theme),
            _container_rules(theme),
        )
    )


def _base_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    surface = _hex(colors.surface)
    on_surface = _hex(colors.on_surface)
    disabled = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    return f"""
QMainWindow, QDialog {{
    background-color: {surface};
    color: {on_surface};
}}
QToolTip {{
    background-color: {_hex(colors.inverse_surface)};
    color: {_hex(colors.inverse_on_surface)};
    border: none;
    border-radius: {int(shape.EXTRA_SMALL)}px;
    padding: 4px 8px;
}}
QLabel {{
    color: {on_surface};
    background: transparent;
}}
QLabel:disabled {{
    color: {disabled};
}}
QStatusBar {{
    color: {_hex(colors.on_surface_variant)};
}}
QStatusBar::item {{
    border: none;
}}
"""


def _menu_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    on_surface = _hex(colors.on_surface)
    hover_layer = _hex(colors.on_surface, state.HOVER_STATE_LAYER_OPACITY)
    pressed_layer = _hex(colors.on_surface, state.PRESSED_STATE_LAYER_OPACITY)
    disabled = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    outline_variant = _hex(colors.outline_variant)
    return f"""
QMenuBar {{
    background-color: {_hex(colors.surface)};
    color: {on_surface};
    padding: 2px 4px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: {int(shape.SMALL)}px;
}}
QMenuBar::item:selected {{
    background-color: {hover_layer};
}}
QMenuBar::item:pressed {{
    background-color: {pressed_layer};
}}
QMenu {{
    background-color: {_hex(colors.surface_container)};
    color: {on_surface};
    border: none;
    border-radius: {int(shape.EXTRA_SMALL)}px;
    padding: 8px 0px;
}}
QMenu::item {{
    padding: 8px 12px;
    min-height: 32px;
}}
QMenu::item:selected {{
    background-color: {hover_layer};
}}
QMenu::item:disabled {{
    color: {disabled};
}}
QMenu::separator {{
    height: 1px;
    background: {outline_variant};
    margin: 8px 0px;
}}
QMenu::indicator {{
    width: 18px;
    height: 18px;
    left: 8px;
}}
QMenu::indicator:checked {{
    image: {icon_url("check", colors.on_surface_variant, 18)};
}}
QMenu::right-arrow {{
    image: {icon_url("arrow_right", colors.on_surface_variant, 18)};
    width: 18px;
    height: 18px;
}}
"""


def _scroll_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    thumb = _hex(colors.on_surface_variant, 0.5)
    thumb_hover = _hex(colors.on_surface_variant, 0.8)
    return f"""
QScrollBar:vertical {{
    background: transparent;
    width: 12px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {thumb};
    min-height: 32px;
    border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {thumb_hover};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 12px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {thumb};
    min-width: 32px;
    border-radius: 4px;
    margin: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {thumb_hover};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0px;
    height: 0px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
QAbstractScrollArea {{
    background: transparent;
    border: none;
}}
QAbstractScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QAbstractItemView {{
    selection-background-color: {_hex(colors.secondary_container)};
    selection-color: {_hex(colors.on_secondary_container)};
    outline: 0;
}}
QHeaderView::section {{
    background-color: {_hex(colors.surface)};
    color: {_hex(colors.on_surface_variant)};
    border: none;
    border-bottom: 1px solid {_hex(colors.outline_variant)};
    padding: 8px 12px;
}}
QTableCornerButton::section {{
    background-color: {_hex(colors.surface)};
    border: none;
    border-bottom: 1px solid {_hex(colors.outline_variant)};
}}
"""


def _button_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    tonal = colors.secondary_container
    on_tonal = colors.on_secondary_container
    hover = state.HOVER_STATE_LAYER_OPACITY
    pressed = state.PRESSED_STATE_LAYER_OPACITY
    disabled_bg = _hex(colors.on_surface, state.DISABLED_CONTAINER_OPACITY)
    disabled_fg = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    return f"""
QPushButton {{
    background-color: {_hex(tonal)};
    color: {_hex(on_tonal)};
    border: none;
    border-radius: 20px;
    padding: 0px 24px;
    min-height: 40px;
}}
QPushButton:hover {{
    background-color: {_layered(on_tonal, tonal, hover)};
}}
QPushButton:pressed {{
    background-color: {_layered(on_tonal, tonal, pressed)};
}}
QPushButton:default, QPushButton:checked {{
    background-color: {_hex(colors.primary)};
    color: {_hex(colors.on_primary)};
}}
QPushButton:default:hover, QPushButton:checked:hover {{
    background-color: {_layered(colors.on_primary, colors.primary, hover)};
}}
QPushButton:default:pressed, QPushButton:checked:pressed {{
    background-color: {_layered(colors.on_primary, colors.primary, pressed)};
}}
QPushButton:flat {{
    background-color: transparent;
    color: {_hex(colors.primary)};
    padding: 0px 12px;
}}
QPushButton:flat:hover {{
    background-color: {_hex(colors.primary, hover)};
}}
QPushButton:flat:pressed {{
    background-color: {_hex(colors.primary, pressed)};
}}
QPushButton:disabled {{
    background-color: {disabled_bg};
    color: {disabled_fg};
}}
QPushButton:flat:disabled {{
    background-color: transparent;
}}
QPushButton::menu-indicator {{
    image: {icon_url("arrow_drop_down", on_tonal, 18)};
    subcontrol-origin: padding;
    subcontrol-position: right center;
    right: 8px;
    width: 18px;
    height: 18px;
}}
QToolButton {{
    background: transparent;
    color: {_hex(colors.on_surface_variant)};
    border: none;
    border-radius: 20px;
    padding: 8px;
}}
QToolButton:hover {{
    background-color: {_hex(colors.on_surface_variant, hover)};
}}
QToolButton:pressed {{
    background-color: {_hex(colors.on_surface_variant, pressed)};
}}
QToolButton:checked {{
    background-color: {_hex(tonal)};
    color: {_hex(on_tonal)};
}}
QToolButton:disabled {{
    color: {disabled_fg};
}}
QToolButton::menu-indicator {{
    image: none;
}}
QToolButton[popupMode="MenuButtonPopup"] {{
    padding-right: 20px;
}}
QToolButton::menu-button {{
    border: none;
    width: 16px;
}}
QToolButton::menu-arrow {{
    image: {icon_url("arrow_drop_down", colors.on_surface_variant, 16)};
}}
"""


def _field_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    on_surface = _hex(colors.on_surface)
    outline = _hex(colors.outline)
    primary = _hex(colors.primary)
    disabled_outline = _hex(colors.on_surface, state.DISABLED_OUTLINE_OPACITY)
    disabled_fg = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    arrow = icon_url("arrow_drop_down", colors.on_surface_variant, 24)
    arrow_disabled = icon_url("arrow_drop_down", colors.on_surface, 24)
    up_arrow = icon_url("arrow_drop_up", colors.on_surface_variant, 16)
    down_arrow = icon_url("arrow_drop_down", colors.on_surface_variant, 16)
    hover_layer = _hex(colors.on_surface, state.HOVER_STATE_LAYER_OPACITY)
    fields = "QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox"
    return f"""
{fields} {{
    background-color: transparent;
    color: {on_surface};
    border: 1px solid {outline};
    border-radius: {int(shape.EXTRA_SMALL)}px;
    padding: 8px 12px;
    selection-background-color: {primary};
    selection-color: {_hex(colors.on_primary)};
}}
QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover,
QAbstractSpinBox:hover, QComboBox:hover {{
    border-color: {on_surface};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QAbstractSpinBox:focus, QComboBox:focus, QComboBox:on {{
    border: 2px solid {primary};
    padding: 7px 11px;
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QAbstractSpinBox:disabled, QComboBox:disabled {{
    border-color: {disabled_outline};
    color: {disabled_fg};
}}
QLineEdit:read-only {{
    border-style: dashed;
}}
QComboBox {{
    padding-right: 36px;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 32px;
    border: none;
    background: transparent;
}}
QComboBox::down-arrow {{
    image: {arrow};
    width: 24px;
    height: 24px;
}}
QComboBox::down-arrow:disabled {{
    image: {arrow_disabled};
}}
QComboBox QAbstractItemView {{
    background-color: {_hex(colors.surface_container)};
    color: {on_surface};
    border: none;
    border-radius: {int(shape.EXTRA_SMALL)}px;
    padding: 8px 0px;
    selection-background-color: {hover_layer};
    selection-color: {on_surface};
    outline: 0;
}}
QComboBox QAbstractItemView::item {{
    min-height: 32px;
    padding: 4px 12px;
}}
QAbstractSpinBox {{
    padding-right: 28px;
}}
QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
    subcontrol-origin: border;
    width: 24px;
    border: none;
    background: transparent;
}}
QAbstractSpinBox::up-button {{
    subcontrol-position: top right;
    margin-top: 2px;
}}
QAbstractSpinBox::down-button {{
    subcontrol-position: bottom right;
    margin-bottom: 2px;
}}
QAbstractSpinBox::up-arrow {{
    image: {up_arrow};
    width: 16px;
    height: 16px;
}}
QAbstractSpinBox::down-arrow {{
    image: {down_arrow};
    width: 16px;
    height: 16px;
}}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{
    background-color: {hover_layer};
    border-radius: {int(shape.EXTRA_SMALL)}px;
}}
"""


def _choice_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    on_surface = _hex(colors.on_surface)
    variant = _hex(colors.on_surface_variant)
    primary = _hex(colors.primary)
    disabled_fg = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    check = icon_url("check", colors.on_primary, 14, fill=False)
    indeterminate = icon_url("remove", colors.on_primary, 14)
    check_disabled = icon_url("check", colors.surface, 14)
    dot = dot_url(colors.primary)
    dot_disabled = dot_url(
        color_tokens.with_alpha(
            colors.on_surface, state.DISABLED_CONTENT_OPACITY
        )
    )
    return f"""
QCheckBox, QRadioButton {{
    color: {on_surface};
    spacing: 8px;
    background: transparent;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {disabled_fg};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {variant};
    border-radius: 2px;
    background: transparent;
}}
QCheckBox::indicator:hover {{
    border-color: {on_surface};
}}
QCheckBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
    image: {check};
}}
QCheckBox::indicator:indeterminate {{
    background-color: {primary};
    border-color: {primary};
    image: {indeterminate};
}}
QCheckBox::indicator:disabled {{
    border-color: {disabled_fg};
}}
QCheckBox::indicator:checked:disabled,
QCheckBox::indicator:indeterminate:disabled {{
    background-color: {disabled_fg};
    border-color: transparent;
    image: {check_disabled};
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {variant};
    border-radius: 10px;
    background: transparent;
}}
QRadioButton::indicator:hover {{
    border-color: {on_surface};
}}
QRadioButton::indicator:checked {{
    border-color: {primary};
    image: {dot};
}}
QRadioButton::indicator:disabled {{
    border-color: {disabled_fg};
}}
QRadioButton::indicator:checked:disabled {{
    image: {dot_disabled};
}}
"""


def _slider_progress_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    primary = _hex(colors.primary)
    inactive = _hex(colors.secondary_container)
    disabled_fg = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    disabled_bg = _hex(colors.on_surface, state.DISABLED_CONTAINER_OPACITY)
    handle_hover = _layered(
        colors.on_primary, colors.primary, state.HOVER_STATE_LAYER_OPACITY
    )
    return f"""
QSlider::groove:horizontal {{
    height: 4px;
    background: {inactive};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {primary};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 20px;
    height: 20px;
    margin: -8px 0px;
    background: {primary};
    border-radius: 10px;
}}
QSlider::groove:vertical {{
    width: 4px;
    background: {inactive};
    border-radius: 2px;
}}
QSlider::add-page:vertical {{
    background: {primary};
    border-radius: 2px;
}}
QSlider::handle:vertical {{
    width: 20px;
    height: 20px;
    margin: 0px -8px;
    background: {primary};
    border-radius: 10px;
}}
QSlider::handle:hover {{
    background: {handle_hover};
}}
QSlider::handle:disabled {{
    background: {disabled_fg};
}}
QSlider::sub-page:horizontal:disabled, QSlider::add-page:vertical:disabled {{
    background: {disabled_fg};
}}
QSlider::groove:disabled {{
    background: {disabled_bg};
}}
QProgressBar {{
    background-color: {inactive};
    color: transparent;
    border: none;
    border-radius: 2px;
    min-height: 4px;
    max-height: 4px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {primary};
    border-radius: 2px;
}}
"""


def _container_rules(theme: theme_module.Theme) -> str:
    colors = theme.colors
    on_surface = _hex(colors.on_surface)
    variant = _hex(colors.on_surface_variant)
    outline_variant = _hex(colors.outline_variant)
    primary = _hex(colors.primary)
    hover_layer = _hex(colors.on_surface, state.HOVER_STATE_LAYER_OPACITY)
    disabled_fg = _hex(colors.on_surface, state.DISABLED_CONTENT_OPACITY)
    surface_container = _hex(colors.surface_container)
    return f"""
QTabWidget::pane {{
    border: none;
    border-top: 1px solid {_hex(colors.surface_variant)};
    top: -1px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {variant};
    padding: 12px 16px;
    min-width: 90px;
    border-bottom: 3px solid transparent;
}}
QTabBar::tab:hover {{
    background-color: {hover_layer};
}}
QTabBar::tab:selected {{
    color: {primary};
    border-bottom: 3px solid {primary};
}}
QTabBar::tab:disabled {{
    color: {disabled_fg};
}}
QGroupBox {{
    color: {on_surface};
    border: 1px solid {outline_variant};
    border-radius: {int(shape.MEDIUM)}px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 0px 4px;
    color: {variant};
}}
QGroupBox::indicator {{
    width: 14px;
    height: 14px;
    border: 2px solid {variant};
    border-radius: 2px;
}}
QGroupBox::indicator:checked {{
    background-color: {primary};
    border-color: {primary};
    image: {icon_url("check", colors.on_primary, 14)};
}}
QSplitter::handle {{
    background: {outline_variant};
}}
QSplitter::handle:horizontal {{
    width: 1px;
    margin: 0px 4px;
}}
QSplitter::handle:vertical {{
    height: 1px;
    margin: 4px 0px;
}}
QSplitter::handle:hover {{
    background: {primary};
}}
QToolBar {{
    background-color: {surface_container};
    border: none;
    padding: 4px;
    spacing: 4px;
}}
QToolBar::separator {{
    background: {outline_variant};
    width: 1px;
    margin: 6px 4px;
}}
QToolBar::handle {{
    image: {icon_url("drag_indicator", colors.on_surface_variant, 16)};
}}
QDockWidget {{
    color: {on_surface};
    titlebar-close-icon: {icon_url("close", colors.on_surface_variant, 16)};
    titlebar-normal-icon: {
        icon_url("open_in_new", colors.on_surface_variant, 16)
    };
}}
QDockWidget::title {{
    background-color: {surface_container};
    padding: 8px 12px;
    text-align: left;
}}
QDockWidget::close-button, QDockWidget::float-button {{
    border: none;
    background: transparent;
    padding: 2px;
    border-radius: 10px;
}}
QDockWidget::close-button:hover, QDockWidget::float-button:hover {{
    background-color: {hover_layer};
}}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {outline_variant};
}}
"""
