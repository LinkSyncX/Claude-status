"""把 Claude Status 打包为独立的可执行程序（PyInstaller）。

用法::

    pip install -r requirements-build.txt
    python build.py              # 单文件程序
    python build.py --onedir     # 目录形式：不必每次解压，启动更快
    python build.py --console    # 保留控制台窗口，便于查看报错

生成的程序在 ``dist/`` 下，运行时不需要安装 Python：

* Windows：``ClaudeStatus.exe``（单个 exe）
* Linux：``claude-status``（单个可执行文件）
* macOS：``Claude Status.app``（应用包，总是目录形式）

构建定义在 ``ClaudeStatus.spec`` 中，本脚本负责检查环境、调用 PyInstaller，
并在构建完成后用演示数据在后台启动一次程序、渲染全部页面，确认程序可用。
PyInstaller 不能交叉编译，在哪个系统上构建就得到哪个系统的程序；各平台的
程序由 GitHub Actions（``.github/workflows/ci.yml``）分别构建。
"""

from __future__ import annotations

import argparse
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from md3 import assets

import claude_status
from claude_status import app_icon
from claude_status import main_window

ROOT = pathlib.Path(__file__).resolve().parent
SPEC_FILE = ROOT / "ClaudeStatus.spec"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
BUNDLE_ID = "io.github.claude-status"
CHECK_TIMEOUT = 300
# 不打包的模块。本程序不用 QtNetwork（联网用的是 urllib），排除后 PyInstaller
# 不再收集它的 TLS 插件与 Qt 自带的一份 OpenSSL。
EXCLUDED_MODULES = ["tkinter", "tests", "PySide6.QtNetwork"]
# Qt 的界面翻译：本程序没有加载，界面文字都是自己的中文。
_QT_TRANSLATION = re.compile(r"(^|/)PySide6/(Qt/)?translations/[^/]+\.qm$")
# Windows 上额外去掉的文件：软件 OpenGL 渲染器（本程序只用 QtWidgets 光栅
# 绘制），以及虚拟键盘与 PDF 图片插件（它们会带入 Qt Quick、QML 与 Qt PDF）。
_WINDOWS_UNWANTED = re.compile(
    r"(^|/)(opengl32sw\.dll"
    r"|plugins/platforminputcontexts/qtvirtualkeyboardplugin\.dll"
    r"|plugins/imageformats/qpdf\.dll)$",
    re.IGNORECASE,
)
_QT_LIBRARY = re.compile(r"^Qt6\w+\.dll$", re.IGNORECASE)
VERSION_INFO = """\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0),
  ),
  kids=[
    StringFileInfo([
      StringTable("080404B0", [
        StringStruct("FileDescription", {name!r}),
        StringStruct("FileVersion", {version!r}),
        StringStruct("InternalName", {exe_name!r}),
        StringStruct("OriginalFilename", {exe_name!r}),
        StringStruct("ProductName", {name!r}),
        StringStruct("ProductVersion", {version!r}),
      ])
    ]),
    VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
  ],
)
"""


def program_name() -> str:
    """各平台的程序名。"""
    if sys.platform == "win32":
        return claude_status.APP_NAME.replace(" ", "")
    if sys.platform == "darwin":
        return claude_status.APP_NAME
    return claude_status.APP_NAME.lower().replace(" ", "-")


def executable_path(name: str, onedir: bool) -> pathlib.Path:
    """构建产物中可以直接运行的文件。"""
    if sys.platform == "darwin":
        return DIST_DIR / f"{name}.app" / "Contents" / "MacOS" / name
    file_name = f"{name}.exe" if sys.platform == "win32" else name
    return DIST_DIR / name / file_name if onedir else DIST_DIR / file_name


def version_numbers(version: str) -> tuple[int, int, int, int]:
    """``0.1.0`` → ``(0, 1, 0, 0)``：Windows 文件版本固定为四段数字。

    每段只取开头的数字，如 ``2.0rc1`` → ``(2, 0, 0, 0)``。
    """
    numbers = []
    for part in version.split(".")[:4]:
        match = re.match(r"\d+", part)
        numbers.append(int(match.group()) if match else 0)
    numbers += [0] * (4 - len(numbers))
    return tuple(numbers)  # type: ignore[return-value]


def write_version_info(name: str) -> pathlib.Path:
    """Windows 文件属性中的名称与版本（任务管理器也显示这里的名称）。"""
    path = BUILD_DIR / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        VERSION_INFO.format(
            numbers=version_numbers(claude_status.__version__),
            version=claude_status.__version__,
            name=claude_status.APP_NAME,
            exe_name=f"{name}.exe",
        ),
        encoding="utf-8",
    )
    return path


def write_icon() -> pathlib.Path | None:
    """生成程序图标；Linux 的可执行文件不带图标（窗口图标由程序设置）。"""
    suffix = {"win32": ".ico", "darwin": ".icns"}.get(sys.platform)
    return app_icon.write(BUILD_DIR / f"app{suffix}") if suffix else None


def _posix(path: str) -> str:
    return path.replace("\\", "/")


def _base_name(entry: tuple) -> str:
    return pathlib.PurePosixPath(_posix(entry[0])).name


def unwanted_binary(dest: str) -> bool:
    """Windows 上不打包的文件（``dest`` 为包内路径）。"""
    return bool(_WINDOWS_UNWANTED.search(_posix(dest)))


def trim_binaries(binaries: list[tuple]) -> list[tuple]:
    """去掉用不到的 Qt 组件，以及因此不再被任何文件引用的 Qt 库。

    只在 Windows 上裁剪：按各文件的链接依赖，从 Python 扩展模块、Qt 插件等
    非 Qt 库文件出发，保留能到达的 Qt 库。其他平台保持 PyInstaller 的默认
    收集。``binaries`` 为 PyInstaller 的 ``(包内路径, 源文件, 类型)`` 列表。
    """
    if sys.platform != "win32":
        return binaries
    # pylint: disable-next=import-outside-toplevel
    from PyInstaller.depend import bindepend

    kept = [entry for entry in binaries if not unwanted_binary(entry[0])]
    qt_libraries = {
        _base_name(entry).lower(): entry
        for entry in kept
        if _QT_LIBRARY.match(_base_name(entry))
    }
    pending = [entry for entry in kept if not _QT_LIBRARY.match(_base_name(entry))]
    needed: set[str] = set()
    while pending:
        entry = pending.pop()
        for name, _path in bindepend.get_imports(entry[1]):
            key = pathlib.PurePosixPath(_posix(name)).name.lower()
            if key in qt_libraries and key not in needed:
                needed.add(key)
                pending.append(qt_libraries[key])
    return [
        entry
        for entry in kept
        if not _QT_LIBRARY.match(_base_name(entry))
        or _base_name(entry).lower() in needed
    ]


def trim_datas(datas: list[tuple]) -> list[tuple]:
    """去掉 Qt 的界面翻译文件。"""
    return [
        entry for entry in datas if not _QT_TRANSLATION.search(_posix(entry[0]))
    ]


def check_prerequisites() -> None:
    """缺少 PyInstaller 或 md3 字体时给出处理方法并退出。"""
    try:
        import PyInstaller  # pylint: disable=import-outside-toplevel
    except ImportError:
        raise SystemExit(
            "没有安装 PyInstaller，请先运行：pip install -r requirements-build.txt"
        ) from None
    if not assets.assets_available():
        raise SystemExit(
            "缺少 md3 的字体与图标素材，请先运行：python -m md3.assets.fetch"
        )
    print(f"PyInstaller {PyInstaller.__version__}，Python {sys.version.split()[0]}")


def smoke_check(executable: pathlib.Path) -> None:
    """用演示数据在后台启动一次，确认各页面都能渲染。"""
    with tempfile.TemporaryDirectory(prefix="claude-status-check-") as tmp:
        root = pathlib.Path(tmp)
        shots = root / "shots"
        env = dict(
            os.environ,
            QT_QPA_PLATFORM="offscreen",
            CLAUDE_CONFIG_DIR=str(root / "claude"),
            CLAUDE_STATUS_DESKTOP_DIR=str(root / "desktop"),
        )
        command = [
            str(executable),
            "--demo",
            "--data-dir",
            str(root / "data"),
            "--screenshot",
            str(shots),
            "--size",
            "1200x800",
        ]
        try:
            result = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                timeout=CHECK_TIMEOUT,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise SystemExit(
                f"检查失败：程序 {CHECK_TIMEOUT} 秒内没有退出"
            ) from None
        rendered = [shots / f"{key}.png" for key in main_window.PAGE_KEYS]
        missing = [path.name for path in rendered if not path.is_file()]
        if result.returncode != 0 or missing:
            output = (result.stdout + result.stderr).strip()[-3000:]
            raise SystemExit(
                f"检查失败：退出码 {result.returncode}，"
                f"缺少截图 {missing or '无'}\n{output}"
            )


def main(argv: list[str] | None = None) -> int:
    """构建并检查，返回退出码。"""
    parser = argparse.ArgumentParser(description="把 Claude Status 打包为可执行程序")
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="生成目录而不是单个文件（启动更快；macOS 总是目录形式的 .app）",
    )
    parser.add_argument(
        "--console", action="store_true", help="保留控制台窗口，便于查看报错"
    )
    parser.add_argument(
        "--clean", action="store_true", help="清除 PyInstaller 缓存后重新构建"
    )
    parser.add_argument(
        "--no-check", action="store_true", help="构建后不启动程序检查"
    )
    args = parser.parse_args(argv)
    check_prerequisites()
    onedir = args.onedir or sys.platform == "darwin"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(SPEC_FILE),
        "--noconfirm",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / "pyinstaller"),
    ]
    if args.clean:
        command.append("--clean")
    # "--" 之后是 ClaudeStatus.spec 自己的参数。
    command.append("--")
    if onedir:
        command.append("--onedir")
    if args.console:
        command.append("--console")
    subprocess.run(command, check=True, cwd=ROOT)
    name = program_name()
    executable = executable_path(name, onedir)
    if not executable.is_file():
        raise SystemExit(f"没有找到构建产物：{executable}")
    if sys.platform == "darwin":
        output = DIST_DIR / f"{name}.app"
    else:
        output = DIST_DIR / name if onedir else executable
    if not args.no_check:
        print("正在检查：用演示数据在后台启动并渲染各页面…")
        smoke_check(executable)
        print("检查通过")
    size = sum(
        path.stat().st_size
        for path in ([output] if output.is_file() else output.rglob("*"))
        if path.is_file()
    )
    print(f"已生成：{output}（{size / 1024 / 1024:.1f} MB）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
