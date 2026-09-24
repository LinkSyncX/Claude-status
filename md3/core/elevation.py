"""海拔阴影绘制。

每个海拔等级由 ambient 与 key 两层高斯模糊阴影组成。阴影按
（尺寸、形状、等级、颜色、像素比）缓存为 ``QPixmap``，避免每帧模糊。
"""

from __future__ import annotations

import math

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.core import shape as shape_utils
from md3.theme import theme as theme_module
from md3.tokens import elevation as elevation_tokens
from md3.tokens import motion
from md3.tokens import shape as shape_tokens

Level = elevation_tokens.Level

_cache: dict[tuple, QtGui.QPixmap] = {}
_CACHE_LIMIT = 256


def shadow_margin(level: Level | int) -> int:
    """阴影越出容器的最大距离（逻辑像素）。"""
    shadow = elevation_tokens.shadow_for(level)
    return int(math.ceil(shadow.extent)) if shadow.layers else 0


_SYNC_EVENTS = frozenset(
    {
        QtCore.QEvent.Type.Move,
        QtCore.QEvent.Type.Resize,
        QtCore.QEvent.Type.Show,
        QtCore.QEvent.Type.Hide,
        QtCore.QEvent.Type.ParentChange,
        QtCore.QEvent.Type.ZOrderChange,
    }
)


class ShadowWidget(QtWidgets.QWidget):
    """位于目标控件下方、专门绘制海拔阴影的兄弟控件。

    阴影需要越出目标控件的矩形，而 Qt 的 ``QGraphicsEffect`` 在分数
    DPR 下并不可靠；因此把阴影画在与目标同级、略大一圈的透明控件上，
    并通过事件过滤器跟随目标的几何与显隐变化。
    """

    def __init__(
        self,
        target: QtWidgets.QWidget,
        level: Level | int = Level.LEVEL_1,
        shape_provider=None,
        color_provider=None,
        rect_provider=None,
    ) -> None:
        super().__init__(target.parentWidget())
        self._target = target
        self._level = Level(level)
        self._previous_level = self._level
        self._shape_provider = shape_provider
        self._color_provider = color_provider
        self._rect_provider = rect_provider
        # 等级切换时旧阴影淡出、新阴影淡入。
        self._blend = animation.AnimatedFloat(self, 1.0, self.update)
        self._blend.finished.connect(self._finish_blend)
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        target.installEventFilter(self)
        target.destroyed.connect(self.deleteLater)
        self.sync()

    @property
    def level(self) -> Level:
        """当前（目标）海拔等级。"""
        return self._level

    def set_level(self, level: Level | int) -> None:
        """更新海拔等级，以交叉淡入过渡并重新同步几何。"""
        level = Level(level)
        if level == self._level:
            return
        self._previous_level = self._level
        self._level = level
        self._blend.set(0.0)
        self._blend.animate_to(1.0, motion.SHORT4, motion.STANDARD)
        self.sync()
        self.update()

    def _finish_blend(self) -> None:
        if self._blend.value >= 0.999:
            self._previous_level = self._level
            self.sync()

    def _margin(self) -> int:
        return max(
            shadow_margin(self._level), shadow_margin(self._previous_level)
        )

    def sync(self) -> None:
        """跟随目标控件的父级、几何与可见性。"""
        target = self._target
        parent = target.parentWidget()
        if parent is not self.parentWidget():
            self.setParent(parent)
        margin = self._margin()
        local = (
            QtCore.QRectF(self._rect_provider())
            if self._rect_provider
            else QtCore.QRectF(target.rect())
        )
        rect = local.translated(target.pos()).adjusted(
            -margin, -margin, margin, margin
        )
        self.setGeometry(rect.toAlignedRect())
        has_shadow = (
            self._level != Level.LEVEL_0
            or self._previous_level != Level.LEVEL_0
        )
        visible = parent is not None and not target.isHidden() and has_shadow
        self.setVisible(visible)
        if visible:
            self.stackUnder(target)
            self.update()

    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:  # noqa: N802
        """目标控件移动、缩放或显隐时同步阴影。"""
        # 目标析构期间，本对象可能已交由 Qt 延迟删除而 Python 包装已释放，
        # 此时 Qt 会用一个不含实例属性的新包装调用本方法。
        if "_target" not in self.__dict__:
            return False
        if watched is self._target and event.type() in _SYNC_EVENTS:
            self.sync()
        return super().eventFilter(watched, event)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        """绘制缓存的阴影位图，过渡期间叠加新旧两级阴影。"""
        del event
        if "_target" not in self.__dict__:
            return
        blend = self._blend.value
        if self._level == Level.LEVEL_0 and (
            self._previous_level == Level.LEVEL_0 or blend >= 0.999
        ):
            return
        margin = self._margin()
        rect = QtCore.QRectF(self.rect()).adjusted(
            margin, margin, -margin, -margin
        )
        shape = (
            self._shape_provider()
            if self._shape_provider
            else shape_tokens.SHAPE_NONE
        )
        color = (
            self._color_provider()
            if self._color_provider
            else theme_module.current().color("shadow")
        )
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        dpr = self.devicePixelRatioF()
        if blend < 0.999 and self._previous_level != Level.LEVEL_0:
            painter.setOpacity(1.0 - blend)
            paint_shadow(painter, rect, shape, self._previous_level, color, dpr)
        if self._level != Level.LEVEL_0:
            painter.setOpacity(blend)
            paint_shadow(painter, rect, shape, self._level, color, dpr)
        painter.end()


def paint_shadow(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    shape: shape_tokens.Shape,
    level: Level | int,
    color: QtGui.QColor,
    device_pixel_ratio: float = 1.0,
) -> None:
    """在矩形周围绘制指定海拔等级的阴影。

    Args:
        painter: 目标画笔。
        rect: 投影容器的矩形（逻辑坐标）。
        shape: 容器形状。
        level: 海拔等级。
        color: 阴影颜色（通常为 ``shadow`` 角色）。
        device_pixel_ratio: 设备像素比，用于生成高清阴影。
    """
    shadow = elevation_tokens.shadow_for(level)
    if not shadow.layers or rect.isEmpty():
        return
    margin = shadow_margin(level)
    width = int(round(rect.width()))
    height = int(round(rect.height()))
    resolved = shape.resolved(rect.width(), rect.height())
    key = (
        width,
        height,
        resolved,
        Level(level),
        color.rgba(),
        round(device_pixel_ratio, 2),
    )
    pixmap = _cache.get(key)
    if pixmap is None:
        pixmap = _render_shadow(
            width, height, resolved, shadow, color, device_pixel_ratio, margin
        )
        if len(_cache) >= _CACHE_LIMIT:
            _cache.clear()
        _cache[key] = pixmap
    target = QtCore.QPointF(rect.left() - margin, rect.top() - margin)
    painter.drawPixmap(target, pixmap)


def _render_shadow(
    width: int,
    height: int,
    shape: shape_tokens.Shape,
    shadow: elevation_tokens.Shadow,
    color: QtGui.QColor,
    dpr: float,
    margin: int,
) -> QtGui.QPixmap:
    total_w = width + 2 * margin
    total_h = height + 2 * margin
    image = QtGui.QImage(
        int(total_w * dpr),
        int(total_h * dpr),
        QtGui.QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(dpr)
    image.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(image)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    for layer in shadow.layers:
        _paint_layer(painter, layer, width, height, shape, color, dpr, margin)
    painter.end()
    return QtGui.QPixmap.fromImage(image)


def _paint_layer(
    painter: QtGui.QPainter,
    layer: elevation_tokens.ShadowLayer,
    width: int,
    height: int,
    shape: shape_tokens.Shape,
    color: QtGui.QColor,
    dpr: float,
    margin: int,
) -> None:
    """渲染单层阴影：绘制扩展后的形状，再高斯模糊。"""
    spread = layer.spread
    rect = QtCore.QRectF(
        margin - spread,
        margin - spread + layer.offset_y,
        width + 2 * spread,
        height + 2 * spread,
    )
    layer_color = QtGui.QColor(color)
    layer_color.setAlphaF(layer.opacity)
    path = shape_utils.rounded_rect_path(
        rect, shape_utils.outset_shape(shape, spread)
    )
    if layer.blur <= 0:
        painter.fillPath(path, layer_color)
        return

    total_w = width + 2 * margin
    total_h = height + 2 * margin
    source = QtGui.QImage(
        int(total_w * dpr),
        int(total_h * dpr),
        QtGui.QImage.Format.Format_ARGB32_Premultiplied,
    )
    source.setDevicePixelRatio(dpr)
    source.fill(QtCore.Qt.GlobalColor.transparent)
    source_painter = QtGui.QPainter(source)
    source_painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    source_painter.fillPath(path, layer_color)
    source_painter.end()

    scene = QtWidgets.QGraphicsScene()
    # 场景内统一使用设备像素：清除 DPR，避免 QGraphicsPixmapItem 按逻辑
    # 尺寸计算边界而与下面按设备像素设置的场景矩形不一致。
    source_pixmap = QtGui.QPixmap.fromImage(source)
    source_pixmap.setDevicePixelRatio(1.0)
    item = QtWidgets.QGraphicsPixmapItem(source_pixmap)
    effect = QtWidgets.QGraphicsBlurEffect()
    # 实测 Qt 的 blurRadius 约等于 2σ，与 CSS box-shadow 的 blur 值一致。
    effect.setBlurRadius(layer.blur * dpr)
    effect.setBlurHints(QtWidgets.QGraphicsBlurEffect.BlurHint.QualityHint)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    scene.setSceneRect(0, 0, source.width(), source.height())
    painter.save()
    painter.scale(1.0 / dpr, 1.0 / dpr)
    scene.render(
        painter,
        QtCore.QRectF(0, 0, source.width(), source.height()),
        scene.sceneRect(),
    )
    painter.restore()


def tonal_surface(
    theme: theme_module.Theme, level: Level | int
) -> QtGui.QColor:
    """暗色主题下叠加 surface tint 的表面色（旧版色调海拔）。"""
    base = theme.color("surface")
    opacity = elevation_tokens.SURFACE_TINT_OPACITY[Level(level)]
    if opacity <= 0:
        return base
    tint = theme.color("surface_tint")
    return blend_colors(base, tint, opacity)


def blend_colors(
    base: QtGui.QColor, overlay: QtGui.QColor, opacity: float
) -> QtGui.QColor:
    """把 overlay 以给定不透明度叠加在 base 上。"""
    inv = 1.0 - opacity
    return QtGui.QColor(
        round(base.red() * inv + overlay.red() * opacity),
        round(base.green() * inv + overlay.green() * opacity),
        round(base.blue() * inv + overlay.blue() * opacity),
        base.alpha(),
    )


def clear_cache() -> None:
    """清空阴影缓存（主题切换时阴影色可能变化）。"""
    _cache.clear()
