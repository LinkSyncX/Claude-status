"""字体加载与 ``QFont`` 构造。

首次调用时把随包分发的 Roboto 与 Material Symbols 注册到 Qt 字体库；
若字体文件缺失则回退到系统字体，并只记录一次警告。
"""

from __future__ import annotations

import dataclasses
import logging

from PySide6 import QtGui

from md3 import assets
from md3.tokens import typography

_LOGGER = logging.getLogger(__name__)

SYMBOLS_FAMILY = "Material Symbols Outlined"


@dataclasses.dataclass(frozen=True)
class FontFamilies:
    """已解析的字体族名称。

    Attributes:
        brand: 用于排版的字体族（Roboto，或缺失时的系统回退字体）。
        symbols: Material Symbols 字体族；未能加载时为 None。
        roboto_loaded: Roboto 是否成功加载。
    """

    brand: str
    symbols: str | None
    roboto_loaded: bool


# 模块级缓存：字体只应向 Qt 注册一次，且注册结果在整个进程内有效。
_families: FontFamilies | None = None


def load_fonts() -> FontFamilies:
    """注册随包字体并返回解析后的字体族，可重复调用。

    Raises:
        RuntimeError: 尚未创建 ``QGuiApplication``。
    """
    global _families  # pylint: disable=global-statement
    if _families is not None:
        return _families
    if QtGui.QGuiApplication.instance() is None:
        raise RuntimeError("加载字体前必须先创建 QApplication")

    roboto_loaded = _add_font(assets.ROBOTO_FONT_FILE)
    symbols_loaded = _add_font(assets.MATERIAL_SYMBOLS_FONT_FILE)
    available = set(QtGui.QFontDatabase.families())

    if roboto_loaded and typography.FONT_FAMILY_BRAND in available:
        brand = typography.FONT_FAMILY_BRAND
    else:
        brand = _pick_fallback(available)
        _LOGGER.warning(
            "未找到 Roboto 字体，回退到 %s；运行 python -m md3.assets.fetch "
            "可下载官方字体",
            brand,
        )
    symbols = SYMBOLS_FAMILY if symbols_loaded else None
    if symbols is None:
        _LOGGER.warning(
            "未找到 Material Symbols 字体，图标将无法显示；"
            "运行 python -m md3.assets.fetch 可下载"
        )
    _families = FontFamilies(brand, symbols, roboto_loaded)
    return _families


def families() -> FontFamilies:
    """返回字体族信息，必要时触发加载。"""
    return load_fonts()


def brand_family() -> str:
    """排版使用的字体族。"""
    return families().brand


def font_for(
    style: typography.TypeStyle, family: str | None = None
) -> QtGui.QFont:
    """由排版样式构造 ``QFont``。

    Args:
        style: 排版样式。
        family: 覆盖字体族；默认使用主题字体。
    """
    font = QtGui.QFont(family or brand_family())
    font.setPixelSize(max(1, round(style.size)))
    font.setWeight(QtGui.QFont.Weight(style.weight))
    font.setLetterSpacing(
        QtGui.QFont.SpacingType.AbsoluteSpacing, style.tracking
    )
    font.setHintingPreference(QtGui.QFont.HintingPreference.PreferNoHinting)
    return font


def symbols_font(
    size: float,
    fill: bool = False,
    weight: int = 400,
    grade: int = 0,
    optical_size: float | None = None,
) -> QtGui.QFont | None:
    """构造 Material Symbols 图标字体，未加载图标字体时返回 None。

    Args:
        size: 字号（像素），通常等于图标尺寸。
        fill: 是否使用填充样式。
        weight: 线条粗细，100–700。
        grade: 灰度调整，-25–200。
        optical_size: 光学尺寸轴，默认按字号在 20–48 间取值。
    """
    symbols = families().symbols
    if symbols is None:
        return None
    font = QtGui.QFont(symbols)
    font.setPixelSize(max(1, round(size)))
    tag = QtGui.QFont.Tag
    font.setVariableAxis(tag("FILL"), 1.0 if fill else 0.0)
    font.setVariableAxis(tag("wght"), float(min(700, max(100, weight))))
    font.setVariableAxis(tag("GRAD"), float(min(200, max(-25, grade))))
    if optical_size is None:
        optical_size = size
    font.setVariableAxis(tag("opsz"), float(min(48.0, max(20.0, optical_size))))
    return font


def _add_font(path) -> bool:
    if not path.is_file():
        return False
    font_id = QtGui.QFontDatabase.addApplicationFont(str(path))
    if font_id < 0:
        _LOGGER.warning("Qt 无法加载字体文件: %s", path)
        return False
    return True


def _pick_fallback(available: set[str]) -> str:
    for candidate in typography.FONT_FAMILY_FALLBACKS:
        if candidate in available:
            return candidate
    return QtGui.QFontDatabase.systemFont(
        QtGui.QFontDatabase.SystemFont.GeneralFont
    ).family()
