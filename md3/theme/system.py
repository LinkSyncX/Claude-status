r"""与操作系统外观联动：明暗方案与强调色。

- ``prefers_dark()`` 读取系统当前是否为深色模式（Qt 6.5+ 的
  ``QStyleHints.colorScheme``）。
- ``accent_color()`` 读取系统强调色：Windows 取注册表
  ``HKCU\Software\Microsoft\Windows\DWM\AccentColor``，其他平台取
  平台调色板的 ``Accent`` 角色（Qt 6.6+）；不可用时返回 None。
- ``SystemThemeWatcher`` 监听明暗切换（信号）并按固定间隔轮询强调色，
  ``md3.install(..., follow_system=True)`` 用它让主题跟随系统变化。
"""

from __future__ import annotations

import sys

from PySide6 import QtCore
from PySide6 import QtGui

_platform_palette: QtGui.QPalette | None = None
DEFAULT_ACCENT_POLL_MS = 2000
_WINDOWS_DWM_KEY = r"HKEY_CURRENT_USER\Software\Microsoft\Windows\DWM"


def capture_platform_palette() -> None:
    """记录应用安装 M3 主题之前的平台调色板（只记录一次）。"""
    global _platform_palette  # pylint: disable=global-statement
    if _platform_palette is None and QtGui.QGuiApplication.instance():
        _platform_palette = QtGui.QPalette(QtGui.QGuiApplication.palette())


def color_scheme() -> QtCore.Qt.ColorScheme:
    """系统明暗方案；平台不支持时为 ``Unknown``。"""
    app = QtGui.QGuiApplication.instance()
    if app is None:
        return QtCore.Qt.ColorScheme.Unknown
    hints = QtGui.QGuiApplication.styleHints()
    getter = getattr(hints, "colorScheme", None)
    if getter is None:
        return QtCore.Qt.ColorScheme.Unknown
    return getter()


def prefers_dark(default: bool = False) -> bool:
    """系统是否偏好深色；无法判断时返回 ``default``。"""
    scheme = color_scheme()
    if scheme == QtCore.Qt.ColorScheme.Dark:
        return True
    if scheme == QtCore.Qt.ColorScheme.Light:
        return False
    return default


def _windows_accent() -> int | None:
    settings = QtCore.QSettings(
        _WINDOWS_DWM_KEY, QtCore.QSettings.Format.NativeFormat
    )
    value = settings.value("AccentColor")
    if value is None:
        return None
    try:
        abgr = int(value) & 0xFFFFFFFF
    except (TypeError, ValueError):
        return None
    red = abgr & 0xFF
    green = (abgr >> 8) & 0xFF
    blue = (abgr >> 16) & 0xFF
    return 0xFF000000 | (red << 16) | (green << 8) | blue


def _palette_accent() -> int | None:
    palette = _platform_palette
    if palette is None and QtGui.QGuiApplication.instance():
        palette = QtGui.QGuiApplication.palette()
    if palette is None:
        return None
    role = getattr(QtGui.QPalette.ColorRole, "Accent", None)
    if role is None:
        return None
    color = palette.color(role)
    if not color.isValid():
        return None
    # 平台未提供强调色时 Qt 回退为 Highlight，这时不视为系统强调色。
    if color == palette.color(QtGui.QPalette.ColorRole.Highlight):
        return None
    return color.rgba() & 0xFFFFFFFF


def accent_color() -> int | None:
    """系统强调色（ARGB），不可用时为 None。"""
    if sys.platform.startswith("win"):
        accent = _windows_accent()
        if accent is not None:
            return accent
    return _palette_accent()


class SystemThemeWatcher(QtCore.QObject):
    """监听系统明暗与强调色变化。

    Args:
        follow_accent: 是否轮询强调色。
        interval_ms: 强调色轮询间隔。
        parent: 父对象。
    """

    dark_changed = QtCore.Signal(bool)
    # ARGB 可能超过有符号 32 位整数范围，因此以 object 传递。
    accent_changed = QtCore.Signal(object)

    def __init__(
        self,
        follow_accent: bool = False,
        interval_ms: int = DEFAULT_ACCENT_POLL_MS,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = prefers_dark()
        self._accent = accent_color()
        hints = QtGui.QGuiApplication.styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            signal.connect(self._on_scheme_changed)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(max(200, interval_ms))
        self._timer.timeout.connect(self.poll)
        if follow_accent:
            self._timer.start()

    @property
    def dark(self) -> bool:
        """最近一次读到的系统深色状态。"""
        return self._dark

    @property
    def accent(self) -> int | None:
        """最近一次读到的系统强调色。"""
        return self._accent

    def _on_scheme_changed(self, scheme: QtCore.Qt.ColorScheme) -> None:
        if scheme == QtCore.Qt.ColorScheme.Unknown:
            return
        dark = scheme == QtCore.Qt.ColorScheme.Dark
        if dark != self._dark:
            self._dark = dark
            self.dark_changed.emit(dark)

    def poll(self) -> None:
        """立即读取一次系统外观并在变化时发出信号。"""
        dark = prefers_dark(self._dark)
        if dark != self._dark:
            self._dark = dark
            self.dark_changed.emit(dark)
        accent = accent_color()
        if accent is not None and accent != self._accent:
            self._accent = accent
            self.accent_changed.emit(accent)

    def stop(self) -> None:
        """停止轮询。"""
        self._timer.stop()
