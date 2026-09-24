"""动效令牌到 Qt 动画框架的映射，以及常用动画辅助类。

除贝塞尔缓动外，本模块还把 M3 Expressive 的弹簧令牌解析为
``QEasingCurve``：以单位质量弹簧的解析解作为自定义缓动函数，并按阻尼
包络计算动画时长，使弹簧可以直接用于 ``QVariantAnimation``。
"""

from __future__ import annotations

from collections.abc import Callable
import functools
import math

from PySide6 import QtCore

from md3.tokens import motion

# 帧驱动动画（不确定态进度、形状变形）的默认帧间隔，约 60 fps。
FRAME_INTERVAL_MS = 16
# 弹簧默认的静止阈值：与目标值相差不足此比例即视为结束。
SPRING_REST_THRESHOLD = 0.001
_SPRING_MAX_DURATION_S = 60.0


def easing_curve(easing: motion.Easing) -> QtCore.QEasingCurve:
    """把 M3 缓动令牌转换为 ``QEasingCurve``。"""
    curve = QtCore.QEasingCurve(QtCore.QEasingCurve.Type.BezierSpline)
    if isinstance(easing, motion.CubicBezier):
        curve.addCubicBezierSegment(
            QtCore.QPointF(easing.x1, easing.y1),
            QtCore.QPointF(easing.x2, easing.y2),
            QtCore.QPointF(1.0, 1.0),
        )
        return curve
    for segment in easing.segments:
        curve.addCubicBezierSegment(
            QtCore.QPointF(*segment.c1),
            QtCore.QPointF(*segment.c2),
            QtCore.QPointF(*segment.end),
        )
    return curve


@functools.cache
def _cached_curve(easing: motion.Easing) -> QtCore.QEasingCurve:
    return easing_curve(easing)


def ease(easing: motion.Easing, progress: float) -> float:
    """按缓动令牌计算 ``progress``（0–1）对应的缓动值。"""
    progress = max(0.0, min(1.0, progress))
    return _cached_curve(easing).valueForProgress(progress)


def keyframe(
    elapsed_ms: float,
    start_ms: float,
    duration_ms: float,
    easing: motion.Easing = motion.LINEAR,
) -> float:
    """关键帧区间内的进度：开始前为 0，结束后为 1，中间按缓动插值。

    用于把一段循环动画的已运行时间映射到各条轨道的 0–1 进度，
    对应 Compose ``keyframes`` 中 ``0 at start`` / ``1 at start + duration``。
    """
    if duration_ms <= 0:
        return 1.0 if elapsed_ms >= start_ms else 0.0
    return ease(easing, (elapsed_ms - start_ms) / duration_ms)


# ---- 弹簧 -------------------------------------------------------------------


def spring_position(spring: motion.Spring, seconds: float) -> float:
    """单位质量弹簧从 0 静止释放、趋向 1 时在 ``seconds`` 秒的位置。

    阻尼比小于 1 时会越过 1 再回弹，因此返回值可能大于 1。
    """
    if seconds <= 0:
        return 0.0
    omega = math.sqrt(spring.stiffness)
    zeta = spring.damping_ratio
    if zeta < 1.0:
        damped = omega * math.sqrt(1.0 - zeta * zeta)
        decay = math.exp(-zeta * omega * seconds)
        return 1.0 - decay * (
            math.cos(damped * seconds)
            + zeta * omega / damped * math.sin(damped * seconds)
        )
    if zeta == 1.0:
        return 1.0 - math.exp(-omega * seconds) * (1.0 + omega * seconds)
    root = math.sqrt(zeta * zeta - 1.0)
    s1 = -omega * (zeta - root)
    s2 = -omega * (zeta + root)
    return 1.0 - (s2 * math.exp(s1 * seconds) - s1 * math.exp(s2 * seconds)) / (
        s2 - s1
    )


@functools.cache
def spring_duration(
    spring: motion.Spring, threshold: float = SPRING_REST_THRESHOLD
) -> int:
    """弹簧与目标值的偏差持续小于 ``threshold`` 所需的毫秒数。"""
    omega = math.sqrt(spring.stiffness)
    zeta = spring.damping_ratio
    if zeta < 1.0:
        # 欠阻尼：用振幅包络 e^(-ζωt)·sqrt(1 + (ζω/ωd)²) 给出保守的静止时间。
        damped = omega * math.sqrt(1.0 - zeta * zeta)
        envelope = math.sqrt(1.0 + (zeta * omega / damped) ** 2)
        seconds = math.log(envelope / threshold) / (zeta * omega)
    else:
        # 临界 / 过阻尼时偏差单调递减，可直接二分。
        low, high = 0.0, _SPRING_MAX_DURATION_S
        for _ in range(48):
            mid = (low + high) / 2
            if 1.0 - spring_position(spring, mid) > threshold:
                low = mid
            else:
                high = mid
        seconds = high
    return max(1, math.ceil(min(seconds, _SPRING_MAX_DURATION_S) * 1000))


def spring_curve(
    spring: motion.Spring, threshold: float = SPRING_REST_THRESHOLD
) -> tuple[QtCore.QEasingCurve, int]:
    """把弹簧令牌解析为（自定义缓动曲线, 时长 ms）。

    曲线在进度 1 处精确返回 1，避免动画结束时留下阈值以内的残差。
    注意：自定义缓动的回调由返回的 Python 对象持有，把曲线交给
    ``setEasingCurve`` 后仍需保留该对象直到动画结束，否则回调会被回收。
    """
    duration = spring_duration(spring, threshold)
    seconds = duration / 1000.0

    def evaluate(progress: float) -> float:
        if progress >= 1.0:
            return 1.0
        return spring_position(spring, progress * seconds)

    # setCustomType 会自行把类型切换为 Custom；直接以 Custom 构造会被 Qt 拒绝。
    curve = QtCore.QEasingCurve()
    curve.setCustomType(evaluate)
    return curve, duration


# ---- 全局开关 ---------------------------------------------------------------


def animations_enabled() -> bool:
    """是否播放动画；测试环境或无障碍设置可通过环境变量关闭。"""
    return not QtCore.QCoreApplication.instance().property(
        "md3_disable_animations"
    )


def set_animations_enabled(enabled: bool) -> None:
    """全局开启或关闭动画（关闭后所有过渡立即完成）。"""
    QtCore.QCoreApplication.instance().setProperty(
        "md3_disable_animations", not enabled
    )


# ---- 动画值 -----------------------------------------------------------------


class AnimatedFloat(QtCore.QObject):
    """带过渡动画的浮点值。

    每次值变化时调用 ``on_change`` 回调（通常是 ``widget.update``）。
    """

    finished = QtCore.Signal()

    def __init__(
        self,
        parent: QtCore.QObject | None,
        initial: float = 0.0,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._value = initial
        self._target = initial
        self._on_change = on_change
        self._animation = QtCore.QVariantAnimation(self)
        self._animation.valueChanged.connect(self._apply)
        self._animation.finished.connect(self.finished)
        # 自定义（弹簧）缓动的回调随 Python 曲线对象存活，需持有引用。
        self._curve: QtCore.QEasingCurve | None = None

    @property
    def value(self) -> float:
        """当前值。"""
        return self._value

    @property
    def target(self) -> float:
        """动画目标值。"""
        return self._target

    def is_running(self) -> bool:
        """动画是否正在进行。"""
        return (
            self._animation.state() == QtCore.QAbstractAnimation.State.Running
        )

    def set(self, value: float) -> None:
        """立即设置值，取消进行中的动画。"""
        self._animation.stop()
        self._target = value
        self._apply(value)

    def animate_to(
        self,
        target: float,
        duration: int = motion.SHORT4,
        easing: motion.Easing = motion.STANDARD,
    ) -> None:
        """从当前值过渡到目标值。"""
        if not self._begin(target):
            return
        self._start(target, duration, easing_curve(easing))

    def spring_to(
        self,
        target: float,
        spring: motion.Spring = motion.EXPRESSIVE_DEFAULT_SPATIAL,
        threshold: float = SPRING_REST_THRESHOLD,
    ) -> None:
        """以弹簧动效从当前值过渡到目标值。

        Args:
            target: 目标值。
            spring: 弹簧令牌；阻尼比小于 1 时会略微过冲后回弹。
            threshold: 静止阈值（相对于本次位移），决定动画时长。
        """
        if not self._begin(target):
            return
        curve, duration = spring_curve(spring, threshold)
        self._start(target, duration, curve)

    def _begin(self, target: float) -> bool:
        """记录新目标；若目标未变且无需动画则返回 False。"""
        if target == self._target and (
            self.is_running() or self._value == target
        ):
            return False
        self._target = target
        self._animation.stop()
        return True

    def _start(
        self, target: float, duration: int, curve: QtCore.QEasingCurve
    ) -> None:
        if not animations_enabled() or duration <= 0:
            self._apply(target)
            self.finished.emit()
            return
        # 先替换动画内部的曲线，再释放旧曲线：setDuration 等会立即用当前
        # 曲线重算插值，若旧回调已被回收则会崩溃。
        self._animation.setEasingCurve(curve)
        self._curve = curve
        self._animation.setStartValue(float(self._value))
        self._animation.setEndValue(float(target))
        self._animation.setDuration(duration)
        self._animation.start()

    def _apply(self, value: float) -> None:
        self._value = float(value)
        if self._on_change is not None:
            self._on_change()


class FrameClock(QtCore.QObject):
    """约 60 fps 的帧时钟，驱动没有固定终点的持续动画。

    ``ticked`` 每帧发出一次；``elapsed_ms`` 返回自启动以来的毫秒数，供
    循环动画按时间计算相位，从而不受丢帧影响。
    """

    ticked = QtCore.Signal()

    def __init__(
        self,
        parent: QtCore.QObject | None = None,
        interval_ms: int = FRAME_INTERVAL_MS,
    ) -> None:
        super().__init__(parent)
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(interval_ms)
        self._timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self.ticked)
        self._elapsed = QtCore.QElapsedTimer()

    def is_active(self) -> bool:
        """时钟是否在运行。"""
        return self._timer.isActive()

    def start(self) -> None:
        """启动时钟（已运行时不重置计时）。"""
        if not self._timer.isActive():
            self._elapsed.start()
            self._timer.start()

    def stop(self) -> None:
        """停止时钟。"""
        self._timer.stop()

    def restart(self) -> None:
        """从零开始重新计时。"""
        self._elapsed.start()
        if not self._timer.isActive():
            self._timer.start()

    def elapsed_ms(self) -> int:
        """自启动以来的毫秒数；未启动过时为 0。"""
        return self._elapsed.elapsed() if self._elapsed.isValid() else 0


def run_property_animation(
    target: QtCore.QObject,
    property_name: bytes,
    end_value: object,
    duration: int = motion.MEDIUM2,
    easing: motion.Easing = motion.STANDARD,
    start_value: object | None = None,
) -> QtCore.QPropertyAnimation:
    """启动一个 ``QPropertyAnimation`` 并返回它（动画结束后自动删除）。"""
    animation = QtCore.QPropertyAnimation(target, property_name, target)
    if start_value is not None:
        animation.setStartValue(start_value)
    animation.setEndValue(end_value)
    animation.setDuration(duration if animations_enabled() else 0)
    animation.setEasingCurve(easing_curve(easing))
    animation.start(QtCore.QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
    return animation
