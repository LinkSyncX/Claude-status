"""带 M3 过渡模式的堆叠容器（Animated stacked widget）。

``AnimatedStackedWidget`` 是 ``QStackedWidget`` 的替代品：切换页面时按
M3 的过渡模式播放动画——

- ``FADE``：交叉淡入淡出。
- ``FADE_THROUGH``：旧页先淡出（90ms），新页再淡入并从 92% 放大到 100%
  （210ms），适合彼此无空间关系的页面（底部导航切换）。
- ``SHARED_AXIS_X`` / ``SHARED_AXIS_Y``：旧页沿轴滑出 30dp 并淡出，
  新页从另一侧滑入并淡入，适合有前后顺序的页面（标签页、向导步骤）；
  ``reverse`` 为真时方向反转，RTL 布局下横向自动镜像。
- ``SHARED_AXIS_Z``：旧页放大到 110% 淡出，新页从 80% 放大淡入，适合
  层级进入 / 返回。

动画期间两页以快照绘制在覆盖层上，因此对页面内容没有任何要求。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.tokens import motion

# 共享轴过渡的位移距离（dp）与各阶段在总时长中的占比：旧页 90ms 淡出，
# 新页在剩余 210ms 内淡入（总时长 300ms）。
SLIDE_DISTANCE = 30.0
OUTGOING_FRACTION = 0.3
FADE_THROUGH_SCALE = 0.92
SHARED_Z_INCOMING_SCALE = 0.8
SHARED_Z_OUTGOING_SCALE = 1.1
DEFAULT_DURATION = motion.MEDIUM2


class Transition(enum.Enum):
    """页面切换的过渡模式。"""

    NONE = "none"
    FADE = "fade"
    FADE_THROUGH = "fade_through"
    SHARED_AXIS_X = "shared_axis_x"
    SHARED_AXIS_Y = "shared_axis_y"
    SHARED_AXIS_Z = "shared_axis_z"


def _phase(progress: float, start: float, end: float) -> float:
    """把总进度映射到 [start, end] 阶段内的 0–1 进度。"""
    if end <= start:
        return 1.0
    return max(0.0, min(1.0, (progress - start) / (end - start)))


class _TransitionOverlay(QtWidgets.QWidget):
    """播放两张页面快照之间过渡动画的覆盖层。"""

    finished = QtCore.Signal()

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        outgoing: QtGui.QPixmap,
        incoming: QtGui.QPixmap,
        transition: Transition,
        reverse: bool,
        duration: int,
    ) -> None:
        super().__init__(parent)
        self._outgoing = outgoing
        self._incoming = incoming
        self._transition = transition
        self._reverse = reverse
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self._progress = animation.AnimatedFloat(self, 0.0, self.update)
        self._progress.finished.connect(self.finished)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self._progress.animate_to(1.0, duration, motion.LINEAR)

    def finish_now(self) -> None:
        """立即结束动画。"""
        self._progress.set(1.0)
        self.finished.emit()

    # ---- 各模式的关键帧 ---------------------------------------------------

    def _slide_offset(self, progress: float, incoming: bool) -> QtCore.QPointF:
        eased = animation.ease(motion.STANDARD, progress)
        direction = -1.0 if self._reverse else 1.0
        if self._transition is Transition.SHARED_AXIS_X:
            if self.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft:
                direction = -direction
            axis = QtCore.QPointF(1.0, 0.0)
        elif self._transition is Transition.SHARED_AXIS_Y:
            axis = QtCore.QPointF(0.0, 1.0)
        else:
            return QtCore.QPointF()
        if incoming:
            # 新页从前进方向的远端滑到原位。
            distance = SLIDE_DISTANCE * (1.0 - eased) * direction
        else:
            distance = -SLIDE_DISTANCE * eased * direction
        return axis * distance

    def _outgoing_frame(self, progress: float) -> tuple[float, float]:
        """旧页的 (不透明度, 缩放)。"""
        match self._transition:
            case Transition.FADE:
                return 1.0 - animation.ease(motion.STANDARD, progress), 1.0
            case Transition.SHARED_AXIS_Z:
                fade = _phase(progress, 0.0, OUTGOING_FRACTION)
                scale = 1.0 + (SHARED_Z_OUTGOING_SCALE - 1.0) * (
                    animation.ease(motion.STANDARD, progress)
                )
                return 1.0 - animation.ease(
                    motion.STANDARD_ACCELERATE, fade
                ), scale
            case _:
                fade = _phase(progress, 0.0, OUTGOING_FRACTION)
                return 1.0 - animation.ease(
                    motion.STANDARD_ACCELERATE, fade
                ), 1.0

    def _incoming_frame(self, progress: float) -> tuple[float, float]:
        """新页的 (不透明度, 缩放)。"""
        match self._transition:
            case Transition.FADE:
                return animation.ease(motion.STANDARD, progress), 1.0
            case Transition.FADE_THROUGH:
                enter = _phase(progress, OUTGOING_FRACTION, 1.0)
                eased = animation.ease(motion.STANDARD_DECELERATE, enter)
                return eased, FADE_THROUGH_SCALE + (
                    1.0 - FADE_THROUGH_SCALE
                ) * eased
            case Transition.SHARED_AXIS_Z:
                enter = _phase(progress, OUTGOING_FRACTION, 1.0)
                eased = animation.ease(motion.STANDARD_DECELERATE, enter)
                scale = SHARED_Z_INCOMING_SCALE + (
                    1.0 - SHARED_Z_INCOMING_SCALE
                ) * animation.ease(motion.STANDARD, progress)
                return eased, scale
            case _:
                enter = _phase(progress, OUTGOING_FRACTION, 1.0)
                return animation.ease(motion.STANDARD_DECELERATE, enter), 1.0

    def _draw(
        self,
        painter: QtGui.QPainter,
        pixmap: QtGui.QPixmap,
        opacity: float,
        scale: float,
        offset: QtCore.QPointF,
    ) -> None:
        if opacity <= 0.001 or pixmap.isNull():
            return
        painter.save()
        painter.setOpacity(opacity)
        center = QtCore.QRectF(self.rect()).center() + offset
        painter.translate(center)
        painter.scale(scale, scale)
        size = pixmap.deviceIndependentSize()
        painter.drawPixmap(
            QtCore.QRectF(
                -size.width() / 2,
                -size.height() / 2,
                size.width(),
                size.height(),
            ),
            pixmap,
            QtCore.QRectF(pixmap.rect()),
        )
        painter.restore()

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        progress = self._progress.value
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        opacity, scale = self._outgoing_frame(progress)
        self._draw(
            painter,
            self._outgoing,
            opacity,
            scale,
            self._slide_offset(progress, incoming=False),
        )
        opacity, scale = self._incoming_frame(progress)
        self._draw(
            painter,
            self._incoming,
            opacity,
            scale,
            self._slide_offset(progress, incoming=True),
        )
        painter.end()


class AnimatedStackedWidget(QtWidgets.QStackedWidget):
    """切换页面时播放 M3 过渡动画的堆叠容器。

    Args:
        transition: 默认过渡模式。
        duration: 过渡时长（ms）。
        parent: 父控件。
    """

    transition_started = QtCore.Signal(int, int)
    transition_finished = QtCore.Signal(int)

    def __init__(
        self,
        transition: Transition = Transition.FADE_THROUGH,
        duration: int = DEFAULT_DURATION,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._transition = transition
        self._duration = duration
        self._overlay: _TransitionOverlay | None = None
        self._hidden_page: QtWidgets.QWidget | None = None

    @property
    def transition(self) -> Transition:
        """默认过渡模式。"""
        return self._transition

    def set_transition(self, transition: Transition) -> None:
        """设置默认过渡模式。"""
        self._transition = transition

    @property
    def duration(self) -> int:
        """过渡时长（ms）。"""
        return self._duration

    def set_duration(self, duration: int) -> None:
        """设置过渡时长。"""
        self._duration = max(0, duration)

    @property
    def is_animating(self) -> bool:
        """是否正在播放过渡。"""
        return self._overlay is not None

    def set_current_index(
        self,
        index: int,
        transition: Transition | None = None,
        reverse: bool | None = None,
    ) -> None:
        """切换到第 index 页。

        Args:
            index: 目标页下标。
            transition: 本次使用的过渡模式，None 取默认值。
            reverse: 共享轴过渡的方向；None 时目标下标小于当前视为后退。
        """
        current = self.currentIndex()
        if not 0 <= index < self.count() or index == current:
            return
        mode = self._transition if transition is None else transition
        if (
            mode is Transition.NONE
            or current < 0
            or not self.isVisible()
            or self._duration <= 0
            or not animation.animations_enabled()
        ):
            self.finish_transition()
            super().setCurrentIndex(index)
            return
        self.finish_transition()
        if reverse is None:
            reverse = index < current
        outgoing_widget = self.widget(current)
        outgoing = outgoing_widget.grab()
        super().setCurrentIndex(index)
        incoming_widget = self.widget(index)
        incoming_widget.setGeometry(self.rect())
        if incoming_widget.layout() is not None:
            incoming_widget.layout().activate()
        incoming = incoming_widget.grab()
        # 动画期间隐藏真实页面，只显示覆盖层上的快照。
        incoming_widget.hide()
        self._hidden_page = incoming_widget
        self._overlay = _TransitionOverlay(
            self, outgoing, incoming, mode, reverse, self._duration
        )
        self._overlay.finished.connect(self.finish_transition)
        self.transition_started.emit(current, index)

    def set_current_widget(
        self,
        widget: QtWidgets.QWidget,
        transition: Transition | None = None,
        reverse: bool | None = None,
    ) -> None:
        """切换到指定页面控件。"""
        self.set_current_index(self.indexOf(widget), transition, reverse)

    @override
    def setCurrentIndex(self, index: int) -> None:
        self.set_current_index(index)

    @override
    def setCurrentWidget(self, widget: QtWidgets.QWidget) -> None:
        self.set_current_widget(widget)

    def finish_transition(self) -> None:
        """立即结束正在播放的过渡（无过渡时不做任何事）。"""
        overlay = self._overlay
        if overlay is None:
            return
        self._overlay = None
        overlay.finished.disconnect(self.finish_transition)
        overlay.hide()
        overlay.setParent(None)
        overlay.deleteLater()
        page = self._hidden_page
        self._hidden_page = None
        if page is not None and page is self.currentWidget():
            page.show()
        self.transition_finished.emit(self.currentIndex())

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        # 尺寸变化时快照已失效，直接结束过渡。
        self.finish_transition()

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        self.finish_transition()
