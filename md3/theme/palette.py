"""把 M3 色彩角色映射为 ``QPalette``，让原生 Qt 控件的配色与主题一致。"""

from __future__ import annotations

from PySide6 import QtGui

from md3.theme import theme as theme_module
from md3.tokens import state


def build_qpalette(theme: theme_module.Theme) -> QtGui.QPalette:
    """由主题生成 ``QPalette``。"""
    colors = theme.colors
    palette = QtGui.QPalette()
    role = QtGui.QPalette.ColorRole
    group = QtGui.QPalette.ColorGroup

    def qc(argb: int) -> QtGui.QColor:
        return theme_module.qcolor(argb)

    mapping = {
        role.Window: colors.surface,
        role.WindowText: colors.on_surface,
        role.Base: colors.surface_container_lowest,
        role.AlternateBase: colors.surface_container_low,
        role.Text: colors.on_surface,
        role.PlaceholderText: colors.on_surface_variant,
        role.Button: colors.surface_container_high,
        role.ButtonText: colors.on_surface,
        role.BrightText: colors.on_primary,
        role.Highlight: colors.primary,
        role.HighlightedText: colors.on_primary,
        role.Accent: colors.primary,
        role.Link: colors.primary,
        role.LinkVisited: colors.tertiary,
        role.ToolTipBase: colors.inverse_surface,
        role.ToolTipText: colors.inverse_on_surface,
        role.Light: colors.surface_bright,
        role.Midlight: colors.surface_container_highest,
        role.Mid: colors.outline_variant,
        role.Dark: colors.outline,
        role.Shadow: colors.shadow,
    }
    for color_role, argb in mapping.items():
        palette.setColor(color_role, qc(argb))

    disabled_text = qc(colors.on_surface)
    disabled_text.setAlphaF(state.DISABLED_CONTENT_OPACITY)
    for text_role in (
        role.WindowText,
        role.Text,
        role.ButtonText,
        role.PlaceholderText,
    ):
        palette.setColor(group.Disabled, text_role, disabled_text)
    disabled_fill = qc(colors.on_surface)
    disabled_fill.setAlphaF(state.DISABLED_CONTAINER_OPACITY)
    palette.setColor(group.Disabled, role.Button, disabled_fill)
    palette.setColor(group.Disabled, role.Highlight, disabled_fill)
    palette.setColor(group.Disabled, role.HighlightedText, disabled_text)
    return palette
