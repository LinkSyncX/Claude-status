"""组件画廊入口：``python -m md3.demo``。"""

from __future__ import annotations

import argparse
import sys

from PySide6 import QtWidgets

import md3
from md3.demo import gallery

EXTENDED_COLORS = {
    "success": "#2E7D32",
    "warning": "#F9A825",
    "info": "#0288D1",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """解析命令行参数，支持 ``--dark``、``--seed #RRGGBB`` 与 ``--locale``。"""
    parser = argparse.ArgumentParser(description="Material Design 3 组件画廊")
    parser.add_argument("--dark", action="store_true", help="以暗色主题启动")
    parser.add_argument(
        "--seed", default="#6750A4", help="种子色，例如 #0061A4"
    )
    parser.add_argument(
        "--locale",
        default=None,
        help="组件内置文字的语言：zh / en / system",
    )
    parser.add_argument(
        "--follow-system",
        action="store_true",
        help="跟随系统明暗切换；配合 --seed system 同时跟随系统强调色",
    )
    return parser.parse_args(argv)


def create_window(
    app: QtWidgets.QApplication, args: argparse.Namespace
) -> gallery.GalleryWindow:
    """安装主题并创建画廊窗口。"""
    follow = getattr(args, "follow_system", False)
    md3.install(
        app,
        seed=args.seed,
        dark=None if follow else args.dark,
        locale=getattr(args, "locale", None),
        extended=EXTENDED_COLORS,
        follow_system=follow,
    )
    return gallery.GalleryWindow()


def main(argv: list[str] | None = None) -> int:
    """启动画廊窗口并进入事件循环。

    Args:
        argv: 命令行参数，为 None 时使用 ``sys.argv``。

    Returns:
        进程退出码。
    """
    args = parse_args(argv)
    app = QtWidgets.QApplication(sys.argv[:1])
    window = create_window(app, args)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
