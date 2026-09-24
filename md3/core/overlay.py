"""覆盖层工具：遮罩（scrim）与在窗口内浮动的面板。

对话框、底部面板、侧面板与模态抽屉都以父窗口为宿主：遮罩覆盖整个
窗口并可点击关闭，面板作为窗口的子控件浮在最上层。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.theme import theme as theme_module
from md3.tokens import motion

SCRIM_OPACITY = 0.32


def host_window(widget: QtWidgets.QWidget | None) -> QtWidgets.QWidget | None:
    """返回控件所属的顶层窗口（或其中央部件容器）。"""
    if widget is None:
        return None
    window = widget.window()
    if isinstance(window, QtWidgets.QMainWindow) and window.centralWidget():
        return window
    return window


class Scrim(QtWidgets.QWidget):
    """覆盖整个宿主窗口的半透明遮罩。"""

    clicked = QtCore.Signal()

    def __init__(self, host: QtWidgets.QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._opacity = animation.AnimatedFloat(self, 0.0, self.update)
        self._opacity.finished.connect(self._hide_if_transparent)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False
        )
        self.hide()
        host.installEventFilter(self)

    def fade_in(self) -> None:
        """铺满宿主并淡入。"""
        self.setGeometry(self._host.rect())
        self.show()
        self.raise_()
        self._opacity.animate_to(
            1.0, motion.MEDIUM2, motion.STANDARD_DECELERATE
        )

    def fade_out(self) -> None:
        """淡出后隐藏。"""
        self._opacity.animate_to(0.0, motion.SHORT4, motion.STANDARD_ACCELERATE)

    def _hide_if_transparent(self) -> None:
        if self._opacity.value <= 0.001:
            self.hide()

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if watched is self._host and event.type() == QtCore.QEvent.Type.Resize:
            self.setGeometry(self._host.rect())
        return super().eventFilter(watched, event)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        color = theme_module.current().color("scrim")
        color.setAlphaF(SCRIM_OPACITY * self._opacity.value)
        painter.fillRect(self.rect(), color)
        painter.end()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        event.accept()

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self.clicked.emit()
        event.accept()


class FloatingPanel(QtWidgets.QWidget):
    """浮在宿主窗口之上的面板基类，负责随宿主尺寸变化重新布局。"""

    opened = QtCore.Signal()
    closed = QtCore.Signal()

    def __init__(self, host: QtWidgets.QWidget, modal: bool) -> None:
        super().__init__(host)
        self._host = host
        self._modal = modal
        self._scrim: Scrim | None = Scrim(host) if modal else None
        if self._scrim is not None:
            self._scrim.clicked.connect(self.close_panel)
        self._is_open = False
        self._geometry_animation: QtCore.QPropertyAnimation | None = None
        host.installEventFilter(self)
        theme_module.manager().theme_changed.connect(self._on_theme_changed)
        self.hide()

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    @property
    def host(self) -> QtWidgets.QWidget:
        """宿主窗口。"""
        return self._host

    @property
    def is_open(self) -> bool:
        """面板是否打开。"""
        return self._is_open

    @property
    def modal(self) -> bool:
        """是否为模态（带遮罩）。"""
        return self._modal

    def open_geometry(self) -> QtCore.QRect:
        """打开状态的几何，由子类实现。"""
        return self._host.rect()

    def closed_geometry(self) -> QtCore.QRect:
        """关闭状态（滑出屏幕）的几何，由子类实现。"""
        return self.open_geometry()

    def open_panel(self) -> None:
        """打开面板（带滑入动画）。"""
        if self._is_open:
            return
        self._is_open = True
        if self._scrim is not None:
            self._scrim.fade_in()
        self.setGeometry(self.closed_geometry())
        self.show()
        self.raise_()
        self._animate_to(
            self.open_geometry(), motion.MEDIUM4, motion.EMPHASIZED_DECELERATE
        )
        self.opened.emit()

    def close_panel(self) -> None:
        """关闭面板（带滑出动画）。"""
        if not self._is_open:
            return
        self._is_open = False
        if self._scrim is not None:
            self._scrim.fade_out()
        self._animate_to(
            self.closed_geometry(),
            motion.SHORT4,
            motion.EMPHASIZED_ACCELERATE,
            hide_when_done=True,
        )
        self.closed.emit()

    def toggle(self) -> None:
        """切换开关。"""
        if self._is_open:
            self.close_panel()
        else:
            self.open_panel()

    def _animate_to(
        self,
        target: QtCore.QRect,
        duration: int,
        easing: motion.Easing,
        hide_when_done: bool = False,
    ) -> None:
        if self._geometry_animation is not None:
            self._geometry_animation.stop()
        if not animation.animations_enabled():
            self.setGeometry(target)
            if hide_when_done:
                self.hide()
            return
        anim = QtCore.QPropertyAnimation(self, b"geometry", self)
        anim.setEndValue(target)
        anim.setDuration(duration)
        anim.setEasingCurve(animation.easing_curve(easing))
        if hide_when_done:
            anim.finished.connect(self.hide)
        anim.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._geometry_animation = anim

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if watched is self._host and event.type() == QtCore.QEvent.Type.Resize:
            if self._is_open and (
                self._geometry_animation is None
                or self._geometry_animation.state()
                != QtCore.QAbstractAnimation.State.Running
            ):
                self.setGeometry(self.open_geometry())
        return super().eventFilter(watched, event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Escape and self._modal:
            self.close_panel()
            event.accept()
            return
        super().keyPressEvent(event)
