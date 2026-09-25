"""应用入口：创建 QApplication、安装 md3 主题并打开主窗口。"""

from __future__ import annotations

import argparse
import ctypes
import os
import pathlib
import ssl
import sys

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.theme import fonts

import claude_status
from claude_status import app_icon
from claude_status import main_window
from claude_status import state as state_module
from claude_status import storage

# Windows 任务栏用它区分应用（见 _use_own_taskbar_icon）。
APP_USER_MODEL_ID = "ClaudeStatus.ClaudeStatus"
# 各系统自带的根证书文件（见 _use_system_certificates）。
CA_BUNDLES = (
    "/etc/ssl/cert.pem",  # macOS、Alpine
    "/etc/ssl/certs/ca-certificates.crt",  # Debian、Ubuntu、Arch
    "/etc/pki/tls/certs/ca-bundle.crt",  # Fedora、RHEL
    "/etc/ssl/ca-bundle.pem",  # openSUSE
)
EXTENDED_COLORS = {
    "success": "#2E7D32",
    "warning": "#F9A825",
    "info": "#0288D1",
}
# 中文字形回退：Roboto 没有 CJK 字形，按平台常见字体依次尝试。
CJK_FALLBACKS = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Noto Sans CJK SC",
    "Noto Sans SC",
    "Source Han Sans SC",
    "WenQuanYi Micro Hei",
)


def font_family() -> str:
    """Roboto + 系统中可用的中文字体，逗号分隔（Qt 按顺序逐字回退）。"""
    brand = fonts.load_fonts().brand
    available = set(QtGui.QFontDatabase.families())
    cjk = [family for family in CJK_FALLBACKS if family in available]
    return ", ".join([brand, *cjk[:2]])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        prog="claude_status", description="Claude 账号管理与用量统计"
    )
    parser.add_argument(
        "--demo", action="store_true", help="本次启动使用演示数据"
    )
    parser.add_argument(
        "--dark", action="store_true", help="以深色主题启动（并记住该选择）"
    )
    parser.add_argument(
        "--data-dir", type=pathlib.Path, help="配置目录（默认用户数据目录）"
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="不联网查询订阅额度（截图模式总是离线）",
    )
    parser.add_argument(
        "--page",
        choices=list(main_window.PAGE_KEYS),
        default="accounts",
        help="启动后显示的页面",
    )
    parser.add_argument(
        "--screenshot",
        type=pathlib.Path,
        metavar="DIR",
        help="不显示窗口，把每个页面渲染为 PNG 保存到 DIR 后退出",
    )
    parser.add_argument(
        "--size", default="1360x900", help="截图模式的窗口尺寸，如 1360x900"
    )
    return parser.parse_args(argv)


def _wait(milliseconds: int) -> None:
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def _grab_page(page: QtWidgets.QWidget) -> QtGui.QPixmap:
    """渲染整个页面（含滚动区域外的部分），背景填充为 surface 色。"""
    ratio = page.devicePixelRatioF()
    pixmap = QtGui.QPixmap(page.size() * ratio)
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(md3.current_theme().color("surface"))
    page.render(pixmap)
    return pixmap


def capture(
    window: main_window.MainWindow,
    state: state_module.AppState,
    directory: pathlib.Path,
    size: QtCore.QSize,
) -> list[pathlib.Path]:
    """依次切换页面并保存窗口截图与整页长图。"""
    directory.mkdir(parents=True, exist_ok=True)
    window.setAttribute(QtCore.Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.resize(size)
    window.show()
    for _ in range(100):
        if not state.loading:
            break
        _wait(100)
    saved = []
    for key in main_window.PAGE_KEYS:
        window.show_page(key)
        _wait(1600)
        path = directory / f"{key}.png"
        window.grab().save(str(path))
        full = directory / f"{key}-full.png"
        _grab_page(window.page(key)).save(str(full))
        saved += [path, full]
    return saved


def _use_own_taskbar_icon() -> None:
    """从源码运行时，让 Windows 任务栏单独显示本工具及其图标。

    不设置时，任务栏把窗口归到 python.exe 名下，显示 Python 的图标；
    打包后的程序本身就带图标，不需要设置。
    """
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except (AttributeError, OSError):
        pass


def _use_system_certificates() -> None:
    """打包后的程序在 macOS / Linux 上找不到根证书时，改用系统的证书文件。

    打包进程序的 OpenSSL 按构建机上的路径查找根证书；用户电脑上没有这个
    路径时，查询额度与登录的 HTTPS 请求会因证书校验失败而出错。Windows 上
    Python 直接读取系统证书库，不受影响。
    """
    if sys.platform == "win32" or not getattr(sys, "frozen", False):
        return
    defaults = ssl.get_default_verify_paths()
    if defaults.cafile or defaults.capath or os.environ.get("SSL_CERT_FILE"):
        return
    for path in CA_BUNDLES:
        if os.path.isfile(path):
            os.environ["SSL_CERT_FILE"] = path
            return


def main(argv: list[str] | None = None) -> int:
    """启动应用并进入事件循环，返回退出码。"""
    args = parse_args(argv)
    _use_own_taskbar_icon()
    _use_system_certificates()
    QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
        QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QtWidgets.QApplication(sys.argv[:1])
    app.setApplicationName(claude_status.APP_NAME)
    app.setApplicationDisplayName(claude_status.APP_NAME)
    app.setApplicationVersion(claude_status.__version__)
    app.setWindowIcon(app_icon.icon())
    state = state_module.AppState(
        storage.Store(args.data_dir),
        force_demo=args.demo,
        offline=args.offline or args.screenshot is not None,
    )
    if args.dark and not state.settings.dark:
        state.settings.dark = True
        state.save()
    md3.install(
        app,
        seed=state.settings.seed,
        dark=state.settings.dark,
        font_family=font_family(),
        extended=EXTENDED_COLORS,
        locale="zh",
    )
    window = main_window.MainWindow(state)
    window.show_page(args.page)
    state.refresh()
    if args.screenshot is not None:
        width, _, height = args.size.partition("x")
        saved = capture(
            window,
            state,
            args.screenshot,
            QtCore.QSize(int(width), int(height)),
        )
        for path in saved:
            print(path)
        state.shutdown()
        return 0
    window.show()
    code = app.exec()
    state.shutdown()
    return code
