# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 构建定义，一般通过 ``python build.py`` 使用（见其说明）。

也可以直接运行 ``pyinstaller ClaudeStatus.spec``；本文件自己的参数写在
``--`` 之后，如 ``pyinstaller ClaudeStatus.spec -- --onedir --console``。
"""

import argparse
import sys

from PyInstaller.utils.hooks import collect_data_files

sys.path.insert(0, SPECPATH)

import build  # noqa: E402  程序名、图标、版本信息与 Qt 组件的裁剪
import claude_status  # noqa: E402

parser = argparse.ArgumentParser(prog="ClaudeStatus.spec")
parser.add_argument("--onedir", action="store_true", help="生成目录而不是单个文件")
parser.add_argument("--console", action="store_true", help="保留控制台窗口")
options = parser.parse_args()
onedir = options.onedir or sys.platform == "darwin"  # macOS 的 .app 总是目录
name = build.program_name()
icon = build.write_icon()
version = build.write_version_info(name) if sys.platform == "win32" else None

a = Analysis(
    [str(build.ROOT / "main.py")],
    pathex=[str(build.ROOT)],
    # md3 的字体、图标码点表、SVG 形状与第三方许可证。
    datas=collect_data_files("md3"),
    excludes=build.EXCLUDED_MODULES,
)
a.binaries = build.trim_binaries(a.binaries)
a.datas = build.trim_datas(a.datas)
pyz = PYZ(a.pure)

exe_options = dict(
    name=name,
    console=options.console,
    # UPX 压缩 Qt 的库与插件容易导致无法加载。
    upx=False,
    icon=[str(icon)] if icon else None,
    version=str(version) if version else None,
)
if onedir:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)
    coll = COLLECT(exe, a.binaries, a.datas, name=name, upx=False)
    if sys.platform == "darwin":
        app = BUNDLE(
            coll,
            name=f"{name}.app",
            icon=str(icon),
            bundle_identifier=build.BUNDLE_ID,
            version=claude_status.__version__,
        )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **exe_options)
