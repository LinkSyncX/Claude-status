"""底部面板（Bottom sheets）：standard 与 modal。

面板可以有多个停靠点（detent）：以像素或宿主高度的比例给出，例如
``detents=[0.3, 0.6, 1.0]``。拖动把手时面板跟随指针，松手后按位置吸附到
最近的停靠点；快速拖动（fling）则前进到拖动方向上的下一个停靠点，从最
低停靠点继续向下拖动或甩动会关闭面板。方向键 Up / Down 也能在停靠点
之间切换。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import overlay
from md3.core import shape as shape_utils
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing

HANDLE_WIDTH = 32.0
HANDLE_HEIGHT = 4.0
HANDLE_TOP = 22.0
HEADER_HEIGHT = 48.0
MAX_WIDTH = 640
DRAG_CLOSE_DISTANCE = 80
# 松手时速度超过该值（px/s）视为甩动，直接前进到下一个停靠点。
FLING_VELOCITY = 600.0
# 估算速度时只看最近这段时间内的移动。
VELOCITY_WINDOW_MS = 100


class BottomSheet(overlay.FloatingPanel):
    """从窗口底部滑入的面板。

    Args:
        host: 宿主窗口（面板覆盖其底部）。
        modal: 为真时显示遮罩并可点击遮罩关闭。
        height: 面板高度（px）；提供 ``detents`` 时忽略。
        show_handle: 是否显示顶部拖拽把手。
        detents: 停靠点列表，按高度升序给出；≤ 1.0 的值为宿主高度的
            比例，否则为像素（例如 ``[240, 0.6, 1.0]``）。默认只有
            ``height`` 一个停靠点。
    """

    detent_changed = QtCore.Signal(int)

    def __init__(
        self,
        host: QtWidgets.QWidget,
        modal: bool = True,
        height: int = 320,
        show_handle: bool = True,
        detents: list[float] | None = None,
    ) -> None:
        super().__init__(host, modal)
        self._detents: list[float] = list(detents or [float(height)])
        self._detent = 0
        self._show_handle = show_handle
        self._drag_start: QtCore.QPointF | None = None
        self._drag_origin_y = 0
        self._samples: list[tuple[int, float]] = []
        self._clock = QtCore.QElapsedTimer()
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self._layout = QtWidgets.QVBoxLayout(self)
        top = int(HANDLE_TOP + HANDLE_HEIGHT + 22) if show_handle else 24
        self._layout.setContentsMargins(
            round(spacing.SPACE_6),
            top,
            round(spacing.SPACE_6),
            round(spacing.SPACE_6),
        )
        self._layout.setSpacing(round(spacing.SPACE_4))

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """内容布局。"""
        return self._layout

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """放入内容控件。"""
        self._layout.addWidget(content, 1)

    # ---- 停靠点 -----------------------------------------------------------

    @property
    def detents(self) -> list[float]:
        """停靠点列表（按高度升序）。"""
        return list(self._detents)

    def set_detents(self, detents: list[float]) -> None:
        """替换停靠点（按高度升序）；当前下标超出范围时回到最高的一个。"""
        if not detents:
            raise ValueError("至少需要一个停靠点")
        self._detents = list(detents)
        self._detent = min(self._detent, len(self._detents) - 1)
        if self.is_open:
            self._animate_to(
                self.open_geometry(),
                motion.MEDIUM2,
                motion.EMPHASIZED_DECELERATE,
            )

    @property
    def current_detent(self) -> int:
        """当前停靠点下标。"""
        return self._detent

    def detent_height(self, index: int) -> float:
        """第 index 个停靠点对应的面板高度（px）。"""
        host_height = float(self.host.height())
        detent = self._detents[index]
        pixels = detent * host_height if detent <= 1.0 else detent
        return max(0.0, min(pixels, host_height))

    def set_detent(self, index: int, animate: bool = True) -> None:
        """切换到第 index 个停靠点。"""
        if not 0 <= index < len(self._detents):
            return
        changed = index != self._detent
        self._detent = index
        if self.is_open:
            if animate:
                self._animate_to(
                    self.open_geometry(),
                    motion.MEDIUM2,
                    motion.EMPHASIZED_DECELERATE,
                )
            else:
                self.setGeometry(self.open_geometry())
        if changed:
            self.detent_changed.emit(index)

    def set_height(self, height: int) -> None:
        """设置面板高度（等价于只有一个停靠点）。"""
        self._detent = 0
        self.set_detents([float(height)])

    def open_panel(self, detent: int | None = None) -> None:
        """打开面板，可指定初始停靠点。"""
        if detent is not None and 0 <= detent < len(self._detents):
            if detent != self._detent:
                self._detent = detent
                self.detent_changed.emit(detent)
        super().open_panel()

    @override
    def open_geometry(self) -> QtCore.QRect:
        host = self.host.rect()
        width = min(host.width(), MAX_WIDTH)
        height = round(self.detent_height(self._detent))
        return QtCore.QRect(
            (host.width() - width) // 2, host.height() - height, width, height
        )

    @override
    def closed_geometry(self) -> QtCore.QRect:
        rect = self.open_geometry()
        return rect.translated(0, rect.height())

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self.rect()).adjusted(
            0, 0, 0, shape_tokens.EXTRA_LARGE
        )
        path = shape_utils.rounded_rect_path(
            rect, shape_tokens.Shape.top(shape_tokens.EXTRA_LARGE)
        )
        shape_utils.fill_shape(
            painter, path, theme.color("surface_container_low")
        )
        if self._show_handle:
            handle = QtCore.QRectF(
                (self.width() - HANDLE_WIDTH) / 2,
                HANDLE_TOP,
                HANDLE_WIDTH,
                HANDLE_HEIGHT,
            )
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(handle, shape_tokens.SHAPE_FULL),
                theme_module.with_alpha(theme.color("on_surface_variant"), 0.4),
            )
        painter.end()

    # ---- 拖拽 -------------------------------------------------------------

    def _visible_height(self) -> float:
        return float(self.host.height() - self.y())

    def _nearest_detent(self, height: float) -> int:
        return min(
            range(len(self._detents)),
            key=lambda index: abs(self.detent_height(index) - height),
        )

    def _velocity(self) -> float:
        """最近一段拖动的速度（px/s，向下为正）。"""
        if len(self._samples) < 2:
            return 0.0
        now = self._samples[-1][0]
        window = [
            sample
            for sample in self._samples
            if now - sample[0] <= VELOCITY_WINDOW_MS
        ]
        if len(window) < 2:
            window = self._samples[-2:]
        (t0, y0), (t1, y1) = window[0], window[-1]
        if t1 <= t0:
            return 0.0
        return (y1 - y0) / (t1 - t0) * 1000.0

    def _settle(self) -> None:
        """松手后决定关闭、吸附或甩动到相邻停靠点。"""
        height = self._visible_height()
        velocity = self._velocity()
        lowest = self.detent_height(0)
        if height < lowest - DRAG_CLOSE_DISTANCE:
            self._is_open = True
            self.close_panel()
            return
        if velocity > FLING_VELOCITY:
            lower = [
                index
                for index in range(len(self._detents))
                if self.detent_height(index) < height - 1
            ]
            if not lower:
                self._is_open = True
                self.close_panel()
                return
            target = lower[-1]
        elif velocity < -FLING_VELOCITY:
            higher = [
                index
                for index in range(len(self._detents))
                if self.detent_height(index) > height + 1
            ]
            target = higher[0] if higher else len(self._detents) - 1
        else:
            target = self._nearest_detent(height)
        if target == self._detent:
            self._animate_to(
                self.open_geometry(),
                motion.MEDIUM2,
                motion.EMPHASIZED_DECELERATE,
            )
        else:
            self.set_detent(target)

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            event.button() == QtCore.Qt.MouseButton.LeftButton
            and event.position().y() < HEADER_HEIGHT
        ):
            self._drag_start = event.position()
            self._drag_origin_y = self.y()
            self._clock.start()
            self._samples = [(0, float(self.y()))]
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_start is not None:
            delta = event.position().y() - self._drag_start.y()
            host_height = self.host.height()
            top = host_height - round(
                self.detent_height(len(self._detents) - 1)
            )
            new_y = int(max(top, min(host_height, self._drag_origin_y + delta)))
            self.setGeometry(self.x(), new_y, self.width(), host_height - new_y)
            self._samples.append((self._clock.elapsed(), float(new_y)))
            if len(self._samples) > 32:
                del self._samples[0]
            event.accept()
            return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_start is not None:
            self._drag_start = None
            self._settle()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == QtCore.Qt.Key.Key_Up:
            self.set_detent(self._detent + 1)
            event.accept()
            return
        if event.key() == QtCore.Qt.Key.Key_Down:
            if self._detent > 0:
                self.set_detent(self._detent - 1)
            else:
                self.close_panel()
            event.accept()
            return
        super().keyPressEvent(event)
