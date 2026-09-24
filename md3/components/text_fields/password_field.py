"""密码输入框（Password field）：可见性切换与密码强度指示。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui

from md3 import i18n
from md3.components.text_fields import text_field
from md3.core import shape as shape_utils
from md3.tokens import shape as shape_tokens

METER_HEIGHT = 4.0
METER_GAP = 4.0
SEGMENT_GAP = 4.0
SEGMENTS = 4
# 五个强度等级（0–4）对应的字符串键；0 级不显示文字。
STRENGTH_KEYS = (
    "",
    "strength_weak",
    "strength_fair",
    "strength_strong",
    "strength_very_strong",
)


def default_strength_labels() -> tuple[str, ...]:
    """当前语言下的默认强度文字。"""
    return tuple(i18n.tr(key) if key else "" for key in STRENGTH_KEYS)


def password_strength(text: str) -> int:
    """估算密码强度：0 为空，1–4 由长度与字符类别数决定。"""
    if not text:
        return 0
    classes = sum(
        (
            any(c.islower() for c in text),
            any(c.isupper() for c in text),
            any(c.isdigit() for c in text),
            any(not c.isalnum() for c in text),
        )
    )
    score = 0
    if len(text) >= 8:
        score += 1
    if len(text) >= 12:
        score += 1
    if classes >= 2:
        score += 1
    if classes >= 3:
        score += 1
    if classes == 4 and len(text) >= 10:
        score += 1
    return max(1, min(SEGMENTS, score))


class PasswordField(text_field.TextField):
    """密码输入框。

    Args:
        label: 浮动标签，默认为当前语言的"密码"。
        text: 初始文字。
        variant: 样式（默认 outlined）。
        show_strength: 是否在容器下方显示四段强度条与强度文字。
        strength_labels: 五个强度等级（0–4）对应的文字，默认取当前语言。
        **kwargs: 其余参数同 ``TextField``。
    """

    strength_changed = QtCore.Signal(int)

    def __init__(
        self,
        label: str | None = None,
        text: str = "",
        variant: text_field.TextFieldVariant = (
            text_field.TextFieldVariant.OUTLINED
        ),
        show_strength: bool = True,
        strength_labels: Sequence[str] | None = None,
        **kwargs,
    ) -> None:
        kwargs.pop("password", None)
        kwargs.pop("multiline", None)
        if label is None:
            label = i18n.tr("password")
        self._show_strength = show_strength
        self._labels = tuple(
            strength_labels
            if strength_labels is not None
            else default_strength_labels()
        )
        self._strength = password_strength(text)
        super().__init__(label, text, variant, password=True, **kwargs)
        self.text_changed.connect(self._update_strength)

    @property
    def strength(self) -> int:
        """当前强度 0–4。"""
        return self._strength

    @property
    def show_strength(self) -> bool:
        """是否显示强度条。"""
        return self._show_strength

    def set_show_strength(self, show: bool) -> None:
        """设置是否显示强度条。"""
        self._show_strength = show
        self.updateGeometry()
        self.update()

    def strength_label(self) -> str:
        """当前强度对应的文字。"""
        if 0 <= self._strength < len(self._labels):
            return self._labels[self._strength]
        return ""

    def _update_strength(self, text: str) -> None:
        strength = password_strength(text)
        if strength != self._strength:
            self._strength = strength
            self.strength_changed.emit(strength)
        self.update()

    def _strength_color(self) -> QtGui.QColor:
        if self._strength <= 1:
            return self.color("error")
        if self._strength == 2:
            return self.color("tertiary")
        return self.color("primary")

    # ---- 几何与绘制 -------------------------------------------------------

    @override
    def extra_bottom_height(self) -> float:
        if not self._show_strength:
            return 0.0
        return METER_GAP + METER_HEIGHT

    @override
    def _has_supporting(self) -> bool:
        return super()._has_supporting() or self._show_strength

    def meter_rect(self) -> QtCore.QRectF:
        """强度条矩形。"""
        rect = self.container_rect()
        return QtCore.QRectF(
            rect.left() + text_field.HORIZONTAL_PADDING,
            rect.bottom() + METER_GAP,
            rect.width() - 2 * text_field.HORIZONTAL_PADDING,
            METER_HEIGHT,
        )

    @override
    def supporting_message(self) -> str:
        message = super().supporting_message()
        if message or not self._show_strength:
            return message
        # 没有辅助文字时用强度文字占据辅助行。
        return self.strength_label()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        super().paint(painter)
        if self._show_strength:
            self._paint_meter(painter)

    def _paint_meter(self, painter: QtGui.QPainter) -> None:
        rect = self.meter_rect()
        width = (rect.width() - SEGMENT_GAP * (SEGMENTS - 1)) / SEGMENTS
        active = self._strength_color()
        inactive = self.color("surface_container_highest")
        if self.variant is text_field.TextFieldVariant.FILLED:
            inactive = self.color("outline_variant")
        for index in range(SEGMENTS):
            segment = QtCore.QRectF(
                rect.left() + index * (width + SEGMENT_GAP),
                rect.top(),
                width,
                rect.height(),
            )
            color = active if index < self._strength else inactive
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(segment, shape_tokens.SHAPE_FULL),
                color,
            )
