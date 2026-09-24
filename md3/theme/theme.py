"""主题对象与全局主题管理。

``Theme`` 是不可变的数据对象；``ThemeManager`` 持有当前主题并在切换时
发出 ``theme_changed`` 信号，组件基类据此重绘。
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
import dataclasses

from PySide6 import QtCore
from PySide6 import QtGui

from md3.color import dynamic
from md3.color import extended as extended_module
from md3.color import scheme
from md3.color import variant as variant_module
from md3.theme import fonts
from md3.tokens import color as color_tokens
from md3.tokens import typography

DEFAULT_SEED = 0xFF6750A4
Variant = variant_module.Variant
ContrastLevel = dynamic.ContrastLevel
ExtendedColor = extended_module.ExtendedColor


def qcolor(value: int) -> QtGui.QColor:
    """把 ARGB 整数转换为 ``QColor``。"""
    return QtGui.QColor.fromRgba(value & 0xFFFFFFFF)


def argb(color: QtGui.QColor) -> int:
    """把 ``QColor`` 转换为 ARGB 整数。"""
    return color.rgba() & 0xFFFFFFFF


def with_alpha(color: QtGui.QColor, alpha: float) -> QtGui.QColor:
    """返回替换了不透明度（0.0–1.0）的颜色副本。"""
    result = QtGui.QColor(color)
    result.setAlphaF(max(0.0, min(1.0, alpha)))
    return result


TRANSPARENT = QtGui.QColor(0, 0, 0, 0)


def parse_seed(seed: int | str | QtGui.QColor) -> int:
    """把 ``#RRGGBB`` 字符串、``QColor`` 或整数统一为 ARGB 整数。"""
    if isinstance(seed, QtGui.QColor):
        return argb(seed)
    if isinstance(seed, str):
        return color_tokens.hex_to_argb(seed)
    return seed & 0xFFFFFFFF


ExtendedSpec = (
    Mapping[str, int | str | QtGui.QColor]
    | Sequence[extended_module.ExtendedColor]
    | None
)


def coerce_extended(
    spec: ExtendedSpec,
) -> tuple[extended_module.ExtendedColor, ...]:
    """把 ``{"success": "#2E7D32"}`` 或 ``ExtendedColor`` 序列统一为元组。"""
    if not spec:
        return ()
    if isinstance(spec, Mapping):
        return tuple(
            extended_module.ExtendedColor(name, parse_seed(value))
            for name, value in spec.items()
        )
    return tuple(spec)


@dataclasses.dataclass(frozen=True)
class Theme:
    """一套完整的 M3 主题。

    Attributes:
        colors: 色彩角色。
        dark: 是否为暗色主题。
        seed: 生成配色的种子色。
        variant: 配色变体。
        font_family: 排版字体族，None 表示使用随包 Roboto 或系统回退字体。
        type_scale: 排版标度。
        contrast: 对比度等级（-1.0～1.0）。
        extended: 扩展色定义（success / warning 等）。
        extended_roles: 由扩展色生成的角色 ``{"success": ARGB, ...}``，
            随明暗与对比度一起重新计算；``color()`` 可直接按名取用。
    """

    colors: color_tokens.ColorRoles
    dark: bool = False
    seed: int = DEFAULT_SEED
    variant: Variant = Variant.BASELINE
    font_family: str | None = None
    type_scale: Mapping[typography.TypeRole, typography.TypeStyle] = (
        dataclasses.field(default_factory=lambda: typography.TYPE_SCALE)
    )
    contrast: float = 0.0
    extended: tuple[extended_module.ExtendedColor, ...] = ()
    extended_roles: Mapping[str, int] = dataclasses.field(default_factory=dict)

    @classmethod
    def from_seed(
        cls,
        seed: int | str | QtGui.QColor = DEFAULT_SEED,
        dark: bool = False,
        variant: Variant = Variant.BASELINE,
        font_family: str | None = None,
        contrast: ContrastLevel | float = ContrastLevel.STANDARD,
        extended: ExtendedSpec = None,
    ) -> Theme:
        """由种子色生成主题。

        Args:
            seed: 种子色。
            dark: 是否为暗色主题。
            variant: 配色变体。
            font_family: 排版字体族。
            contrast: 对比度等级（``ContrastLevel`` 或 -1.0～1.0 的数值）。
            extended: 扩展色，``{"success": "#2E7D32", "warning": ...}`` 或
                ``ExtendedColor`` 序列；每个扩展色派生出 ``<name>`` /
                ``on_<name>`` / ``<name>_container`` /
                ``on_<name>_container`` 四个角色。
        """
        seed_argb = parse_seed(seed)
        level = dynamic.coerce_level(contrast)
        colors = coerce_extended(extended)
        return cls(
            colors=scheme.from_seed(
                seed_argb, is_dark=dark, variant=variant, contrast_level=level
            ),
            dark=dark,
            seed=seed_argb,
            variant=variant,
            font_family=font_family,
            contrast=level,
            extended=colors,
            extended_roles=extended_module.resolve_all(
                colors, seed_argb, dark, level
            ),
        )

    @property
    def contrast_level(self) -> ContrastLevel | None:
        """对比度等级枚举；数值不在三档之内时为 None。"""
        for level in ContrastLevel:
            if level.value == self.contrast:
                return level
        return None

    @classmethod
    def from_colors(
        cls,
        colors: color_tokens.ColorRoles,
        dark: bool = False,
        font_family: str | None = None,
    ) -> Theme:
        """由自定义色彩角色构造主题。"""
        return cls(
            colors=colors,
            dark=dark,
            seed=colors.primary,
            font_family=font_family,
        )

    def has_color(self, role: str) -> bool:
        """是否存在该色彩角色（标准角色或扩展色角色）。"""
        name = role.replace("-", "_")
        return name in self.extended_roles or name in color_tokens.ROLE_NAMES

    def argb(self, role: str) -> int:
        """按角色名取 ARGB 整数（含扩展色角色）。

        Raises:
            KeyError: 角色名不存在。
        """
        name = role.replace("-", "_")
        if name in self.extended_roles:
            return self.extended_roles[name]
        return self.colors.get(name)

    def color(self, role: str) -> QtGui.QColor:
        """按角色名取 ``QColor``，例如 ``theme.color("on_surface")``。"""
        return qcolor(self.argb(role))

    def extended_group(
        self, name: str
    ) -> extended_module.ExtendedColorGroup | None:
        """返回某个扩展色的四个角色，不存在时为 None。"""
        for color in self.extended:
            if color.name == name:
                return extended_module.resolve(
                    color, self.seed, self.dark, self.contrast
                )
        return None

    def style(self, role: typography.TypeRole | str) -> typography.TypeStyle:
        """按角色取排版样式。"""
        if isinstance(role, str):
            role = typography.TypeRole(role)
        return self.type_scale[role]

    def font(self, role: typography.TypeRole | str) -> QtGui.QFont:
        """按排版角色构造 ``QFont``。"""
        return fonts.font_for(self.style(role), self.font_family)

    def _derive(self, **overrides: object) -> Theme:
        """按当前参数重新生成主题，可覆盖部分参数。"""
        params: dict[str, object] = {
            "seed": self.seed,
            "dark": self.dark,
            "variant": self.variant,
            "font_family": self.font_family,
            "contrast": self.contrast,
            "extended": self.extended,
        }
        params.update(overrides)
        return Theme.from_seed(**params)  # type: ignore[arg-type]

    def with_dark(self, dark: bool) -> Theme:
        """返回明暗模式切换后的主题（重新生成配色）。"""
        if dark == self.dark:
            return self
        return self._derive(dark=dark)

    def with_seed(
        self,
        seed: int | str | QtGui.QColor,
        variant: Variant | None = None,
    ) -> Theme:
        """返回替换种子色（可选替换变体）后的主题。"""
        return self._derive(
            seed=seed, variant=self.variant if variant is None else variant
        )

    def with_contrast(self, contrast: ContrastLevel | float) -> Theme:
        """返回替换对比度等级后的主题。"""
        level = dynamic.coerce_level(contrast)
        if level == self.contrast:
            return self
        return self._derive(contrast=level)

    def with_extended(self, extended: ExtendedSpec) -> Theme:
        """返回替换扩展色后的主题。"""
        return self._derive(extended=coerce_extended(extended))

    def toggled(self) -> Theme:
        """返回明暗反转后的主题。"""
        return self.with_dark(not self.dark)


class ThemeManager(QtCore.QObject):
    """持有当前主题并广播变更。"""

    theme_changed = QtCore.Signal(object)

    def __init__(self, theme: Theme | None = None) -> None:
        super().__init__()
        self._theme = theme or Theme.from_seed()

    def theme(self) -> Theme:
        """当前主题。"""
        return self._theme

    def set_theme(self, theme: Theme) -> None:
        """替换当前主题，主题不同时发出 ``theme_changed``。"""
        if theme == self._theme:
            return
        self._theme = theme
        self.theme_changed.emit(theme)


# 全局唯一的主题管理器；通过下方函数访问，避免直接修改。
_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    """返回全局主题管理器，首次调用时以默认主题创建。"""
    global _manager  # pylint: disable=global-statement
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def current() -> Theme:
    """当前主题。"""
    return manager().theme()


def set_theme(theme: Theme) -> None:
    """替换当前主题。"""
    manager().set_theme(theme)


def set_dark(dark: bool) -> None:
    """切换明暗模式。"""
    set_theme(current().with_dark(dark))


def toggle_dark() -> None:
    """反转明暗模式。"""
    set_theme(current().toggled())


def set_seed(
    seed: int | str | QtGui.QColor, variant: Variant | None = None
) -> None:
    """替换种子色（可选替换变体）。"""
    set_theme(current().with_seed(seed, variant))


def set_contrast(contrast: ContrastLevel | float) -> None:
    """替换对比度等级。"""
    set_theme(current().with_contrast(contrast))


def set_extended(extended: ExtendedSpec) -> None:
    """替换扩展色（success / warning 等语义色）。"""
    set_theme(current().with_extended(extended))
