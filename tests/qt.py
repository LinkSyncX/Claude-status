"""测试共用的 Qt 应用实例（offscreen 平台，无需显示器）。"""

import os

from PySide6 import QtWidgets

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def application() -> QtWidgets.QApplication:
    """返回进程内唯一的 QApplication。"""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app  # type: ignore[return-value]
