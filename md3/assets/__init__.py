"""随包分发的字体、图标码点表、SVG 形状库与第三方许可证。

字体文件体积较大（Material Symbols 约 10 MB），通过
``python -m md3.assets.fetch`` 从 Google 官方仓库下载到本目录；
缺失时组件库会回退到系统字体并给出一次性警告。``svg/shapes/`` 中的
M3 形状库由 ``scripts/generate_shape_svgs.py`` 生成，随源码一起提交。
"""

import pathlib

ASSETS_DIR = pathlib.Path(__file__).resolve().parent
FONTS_DIR = ASSETS_DIR / "fonts"
ICONS_DIR = ASSETS_DIR / "icons"
SVG_DIR = ASSETS_DIR / "svg"
LICENSES_DIR = ASSETS_DIR / "LICENSES"

ROBOTO_FONT_FILE = FONTS_DIR / "Roboto[wdth,wght].ttf"
MATERIAL_SYMBOLS_FONT_FILE = (
    FONTS_DIR / "MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].ttf"
)
MATERIAL_SYMBOLS_CODEPOINTS_FILE = (
    ICONS_DIR / "MaterialSymbolsOutlined.codepoints"
)


def assets_available() -> bool:
    """返回字体与图标码点表是否已全部下载到本地。"""
    return all(
        path.is_file()
        for path in (
            ROBOTO_FONT_FILE,
            MATERIAL_SYMBOLS_FONT_FILE,
            MATERIAL_SYMBOLS_CODEPOINTS_FILE,
        )
    )
