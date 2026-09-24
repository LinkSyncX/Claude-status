"""导航目的地模型与公共绘制逻辑。"""

from __future__ import annotations

import dataclasses
from typing import Any

from PySide6 import QtCore
from PySide6 import QtGui

from md3.components.badges import badge as badge_module
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ICON_SIZE = 24.0
INDICATOR_WIDTH = 64.0
INDICATOR_HEIGHT = 32.0
RAIL_INDICATOR_WIDTH = 56.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
LABEL_GAP = 4.0


@dataclasses.dataclass
class Destination:
    """导航目的地。

    Attributes:
        label: 标签文字。
        icon: 未选中图标。
        selected_icon: 选中图标；默认为同名填充图标。
        badge: 徽标数字或文字；``""`` 显示小圆点，None 不显示。
        enabled: 是否可用。
        key: 业务侧标识。
    """

    label: str
    icon: icons.IconLike = None
    selected_icon: icons.IconLike = None
    badge: int | str | None = None
    enabled: bool = True
    key: Any = None

    def badge_text(self) -> str | None:
        """徽标文字；None 表示无徽标，空字符串表示小圆点。"""
        if self.badge is None:
            return None
        if isinstance(self.badge, int):
            return badge_module.badge_text(self.badge)
        return self.badge

    def current_icon(self, selected: bool) -> icons.AnyIcon | None:
        """按选中状态返回图标。"""
        if selected:
            if self.selected_icon is not None:
                return icons.coerce(self.selected_icon, ICON_SIZE)
            base = icons.coerce(self.icon, ICON_SIZE)
            return base.with_fill(True) if base is not None else None
        return icons.coerce(self.icon, ICON_SIZE)


def paint_destination(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    destination: Destination,
    selected: bool,
    progress: float,
    show_label: bool,
    indicator_width: float = INDICATOR_WIDTH,
    enabled: bool = True,
    theme: theme_module.Theme | None = None,
    rtl: bool = False,
) -> QtCore.QRectF:
    """在矩形内绘制图标、活动指示器、标签与徽标，返回指示器矩形。

    Args:
        painter: 画笔。
        rect: 目的地占用的矩形。
        destination: 目的地。
        selected: 是否选中。
        progress: 选中过渡进度 0–1，控制指示器宽度与颜色。
        show_label: 是否绘制标签。
        indicator_width: 指示器宽度（导航栏 64、导航轨 56）。
        enabled: 是否可用。
        theme: 主题，默认当前主题。
        rtl: 为真时徽标挂在图标左上角。
    """
    theme = theme or theme_module.current()
    label_height = theme.style(LABEL_STYLE).line_height if show_label else 0.0
    block_height = INDICATOR_HEIGHT + (
        LABEL_GAP + label_height if show_label else 0
    )
    top = rect.center().y() - block_height / 2
    indicator = QtCore.QRectF(
        rect.center().x() - indicator_width / 2,
        top,
        indicator_width,
        INDICATOR_HEIGHT,
    )
    if progress > 0.001:
        width = indicator_width * progress
        animated = QtCore.QRectF(
            rect.center().x() - width / 2, top, width, INDICATOR_HEIGHT
        )
        color = theme.color("secondary_container")
        color.setAlphaF(min(1.0, progress * 1.5))
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(animated, shape_tokens.SHAPE_FULL),
            color,
        )
    if not enabled or not destination.enabled:
        icon_color = theme_module.with_alpha(
            theme.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
        )
        label_color = icon_color
    elif selected:
        icon_color = theme.color("on_secondary_container")
        label_color = theme.color("on_surface")
    else:
        icon_color = theme.color("on_surface_variant")
        label_color = theme.color("on_surface_variant")
    icon = destination.current_icon(selected)
    icon_rect = QtCore.QRectF(
        indicator.center().x() - ICON_SIZE / 2,
        indicator.center().y() - ICON_SIZE / 2,
        ICON_SIZE,
        ICON_SIZE,
    )
    if icon is not None:
        icon.paint(painter, icon_rect, icon_color)
    badge_text = destination.badge_text()
    if badge_text is not None:
        badge_module.paint_badge(painter, icon_rect, badge_text, theme, rtl)
    if show_label:
        label_rect = QtCore.QRectF(
            rect.left(),
            indicator.bottom() + LABEL_GAP,
            rect.width(),
            label_height,
        )
        typography.paint_text(
            painter,
            label_rect,
            destination.label,
            LABEL_STYLE,
            label_color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
    return indicator


def coerce_destinations(items: list[Destination | str]) -> list[Destination]:
    """把字符串统一转换为 ``Destination``。"""
    return [
        Destination(label=item) if isinstance(item, str) else item
        for item in items
    ]
