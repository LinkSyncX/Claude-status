"""基于 PySide6 的 Material Design 3 组件库。

典型用法::

    from PySide6 import QtWidgets

    import md3
    from md3.components import buttons

    app = QtWidgets.QApplication([])
    md3.install(app, seed="#6750A4", dark=False)
    button = buttons.FilledButton("保存")
"""

from __future__ import annotations

from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n as _i18n
from md3.color import dynamic as _dynamic
from md3.color import variant as _variant
from md3.core import accessibility as _accessibility
from md3.theme import fonts as _fonts
from md3.theme import palette as _palette
from md3.theme import stylesheet as _stylesheet
from md3.theme import system as _system
from md3.theme import theme as _theme
from md3.tokens import typography as _typography

__version__ = "0.1.0"

Theme = _theme.Theme
Variant = _variant.Variant
ContrastLevel = _dynamic.ContrastLevel
ExtendedColor = _theme.ExtendedColor
Strings = _i18n.Strings
current_theme = _theme.current
set_theme = _theme.set_theme
set_dark = _theme.set_dark
toggle_dark = _theme.toggle_dark
set_seed = _theme.set_seed
set_contrast = _theme.set_contrast
set_extended = _theme.set_extended
theme_manager = _theme.manager
set_locale = _i18n.set_locale
set_strings = _i18n.set_strings
tr = _i18n.tr

# 记录已安装的应用，避免重复连接信号。
_installed_apps: set[int] = set()


SYSTEM = "system"
_watcher: _system.SystemThemeWatcher | None = None


def install(
    app: QtWidgets.QApplication,
    seed: int | str | QtGui.QColor = _theme.DEFAULT_SEED,
    dark: bool | None = False,
    variant: Variant = Variant.BASELINE,
    font_family: str | None = None,
    apply_palette: bool = True,
    apply_stylesheet: bool = True,
    contrast: ContrastLevel | float = ContrastLevel.STANDARD,
    accessibility: bool = True,
    locale: str | None = None,
    extended: _theme.ExtendedSpec = None,
    follow_system: bool = False,
) -> Theme:
    """把 M3 主题接入 Qt 应用。

    加载随包字体、生成主题、设置应用调色板与样式表，并在之后每次主题
    变更时自动重新应用。

    Args:
        app: 已创建的 ``QApplication``。
        seed: 种子色，支持 ``#RRGGBB`` 字符串、ARGB 整数或 ``QColor``；
            传 ``"system"`` 使用系统强调色（不可用时回退默认种子色）。
        dark: 是否使用暗色主题；None 或 ``follow_system`` 为真时按系统
            当前的明暗方案决定。
        variant: 配色变体。
        font_family: 覆盖排版字体族；默认使用 Roboto。
        apply_palette: 是否把主题映射到 ``QPalette``。
        apply_stylesheet: 是否为原生控件应用 QSS。
        contrast: 对比度等级（标准 / 中 / 高）。
        accessibility: 是否为自绘组件注册 ``QAccessible`` 接口工厂。
        locale: 组件内置文字的语言（``"zh"`` / ``"en"`` / ``"system"``）；
            None 保持当前设置（默认中文）。
        extended: 扩展色，例如 ``{"success": "#2E7D32", "warning":
            "#F9A825"}``；生成 ``success`` / ``on_success`` /
            ``success_container`` / ``on_success_container`` 等角色。
        follow_system: 为真时持续跟随系统明暗切换；``seed`` 为
            ``"system"`` 时同时跟随强调色变化。

    Returns:
        已生效的主题。
    """
    _system.capture_platform_palette()
    if locale is not None:
        _i18n.set_locale(locale)
    families = _fonts.load_fonts()
    if accessibility:
        _accessibility.install()
    use_system_seed = isinstance(seed, str) and seed.lower() == SYSTEM
    if use_system_seed:
        accent = _system.accent_color()
        seed = accent if accent is not None else _theme.DEFAULT_SEED
    if dark is None or follow_system:
        dark = _system.prefers_dark(bool(dark))
    theme = Theme.from_seed(
        seed,
        dark=dark,
        variant=variant,
        font_family=font_family or families.brand,
        contrast=contrast,
        extended=extended,
    )
    manager = _theme.manager()

    def apply(new_theme: Theme) -> None:
        app.setFont(new_theme.font(_typography.TypeRole.BODY_MEDIUM))
        if apply_palette:
            app.setPalette(_palette.build_qpalette(new_theme))
        if apply_stylesheet:
            app.setStyleSheet(_stylesheet.build_stylesheet(new_theme))

    if id(app) not in _installed_apps:
        _installed_apps.add(id(app))
        manager.theme_changed.connect(apply)
    manager.set_theme(theme)
    apply(theme)
    _set_follow_system(follow_system, use_system_seed)
    return theme


def _set_follow_system(enabled: bool, follow_accent: bool) -> None:
    global _watcher  # pylint: disable=global-statement
    if _watcher is not None:
        _watcher.stop()
        _watcher.deleteLater()
        _watcher = None
    if not enabled:
        return
    _watcher = _system.SystemThemeWatcher(follow_accent=follow_accent)
    _watcher.dark_changed.connect(_theme.set_dark)
    if follow_accent:
        _watcher.accent_changed.connect(_theme.set_seed)


def set_follow_system(
    enabled: bool = True, follow_accent: bool = False
) -> None:
    """开启或关闭主题跟随系统明暗（可选同时跟随强调色）。"""
    _set_follow_system(enabled, follow_accent)


def system_watcher() -> _system.SystemThemeWatcher | None:
    """当前的系统外观监听器（未开启跟随时为 None）。"""
    return _watcher


__all__ = [
    "ContrastLevel",
    "ExtendedColor",
    "Strings",
    "Theme",
    "Variant",
    "__version__",
    "current_theme",
    "install",
    "set_contrast",
    "set_dark",
    "set_extended",
    "set_follow_system",
    "set_locale",
    "set_seed",
    "set_strings",
    "set_theme",
    "system_watcher",
    "theme_manager",
    "toggle_dark",
    "tr",
]
