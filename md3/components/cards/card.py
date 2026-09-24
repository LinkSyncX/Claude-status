"""卡片（Cards）。

卡片是承载内容与操作的容器，内部使用 ``QVBoxLayout`` 放置任意控件。
可点击的卡片具有悬停 / 按压状态层、涟漪与海拔变化。

- ``set_media`` 在卡片顶部放置一块媒体区（图片按比例裁切填满，随卡片
  圆角裁剪），内容自动下移。
- ``set_expandable`` 在内容末尾加入一个展开箭头与可折叠区域，
  ``expanded_layout`` 中的控件随 ``set_expanded`` 以高度动画展开 / 收起。
- ``set_draggable`` 让卡片在按住拖动时发起真正的 ``QDrag``（携带
  ``QMimeData``，拖动期间呈拖拽态），供接收方处理放置。
"""

from __future__ import annotations

import enum
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import icon_button
from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing
from md3.tokens import state as state_tokens

OUTLINE_WIDTH = 1.0
DEFAULT_MEDIA_ASPECT = 16 / 9
DEFAULT_DRAG_MIME_TYPE = "application/x-md3-card"


class CardVariant(enum.Enum):
    """卡片变体。"""

    ELEVATED = "elevated"
    FILLED = "filled"
    OUTLINED = "outlined"


class _ExpandButton(icon_button.IconButton):
    """展开箭头：展开时旋转 180 度。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            "expand_more", tooltip=i18n.tr("expand"), parent=parent
        )
        self._angle = animation.AnimatedFloat(self, 0.0, self.update)

    def set_expanded(self, expanded: bool) -> None:
        """按展开状态旋转箭头。"""
        self._angle.animate_to(
            180.0 if expanded else 0.0, motion.MEDIUM2, motion.EMPHASIZED
        )
        self.set_tooltip(i18n.tr("collapse" if expanded else "expand"))

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        center = self.icon_rect().center()
        painter.save()
        painter.translate(center)
        painter.rotate(self._angle.value)
        painter.translate(-center)
        super().paint_content(painter)
        painter.restore()


class Card(widget.InteractiveWidget):
    """卡片容器。

    Args:
        variant: 变体。
        clickable: 是否可点击（显示状态层、涟漪并发出 ``clicked``）。
        parent: 父控件。
    """

    expanded_changed = QtCore.Signal(bool)
    drag_started = QtCore.Signal()
    drag_finished = QtCore.Signal(object)

    def __init__(
        self,
        variant: CardVariant = CardVariant.ELEVATED,
        clickable: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._variant = variant
        self._clickable = clickable
        self._dragged = False
        self._media: QtGui.QPixmap | None = None
        self._media_height: float | None = None
        self._media_aspect = DEFAULT_MEDIA_ASPECT
        self._content_insets = spacing.Insets.all(spacing.SPACE_4)
        self._expand_button: _ExpandButton | None = None
        self._expanded_area: QtWidgets.QWidget | None = None
        self._expanded_layout: QtWidgets.QVBoxLayout | None = None
        self._expanded = False
        self._expand = animation.AnimatedFloat(
            self, 0.0, self._apply_expand_progress
        )
        self._draggable = False
        self._drag_mime_type = DEFAULT_DRAG_MIME_TYPE
        self._drag_payload = ""
        self._drag_press: QtCore.QPointF | None = None
        self.set_outer_margin(0.0)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setSpacing(round(spacing.SPACE_2))
        self._apply_content_margins()
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Preferred,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        self._apply_clickable()
        self._update_elevation()

    # ---- 内容 -------------------------------------------------------------

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """内容布局。"""
        return self._layout

    def add_widget(self, child: QtWidgets.QWidget, stretch: int = 0) -> None:
        """向内容区追加控件（位于展开区域之前）。"""
        if self._expanded_area is not None:
            index = self._layout.indexOf(self._expanded_area) - 1
            self._layout.insertWidget(max(0, index), child, stretch)
            return
        self._layout.addWidget(child, stretch)

    def set_content_margins(self, margin: float | spacing.Insets) -> None:
        """设置内容边距（dp）；有媒体区时顶部边距叠加在媒体之下。"""
        self._content_insets = (
            margin
            if isinstance(margin, spacing.Insets)
            else spacing.Insets.all(margin)
        )
        self._apply_content_margins()

    def _apply_content_margins(self) -> None:
        insets = self._content_insets
        self._layout.setContentsMargins(
            round(insets.left),
            round(insets.top + self.media_height()),
            round(insets.right),
            round(insets.bottom),
        )

    # ---- 媒体区 -----------------------------------------------------------

    def set_media(
        self,
        pixmap: QtGui.QPixmap | None,
        height: float | None = None,
        aspect_ratio: float = DEFAULT_MEDIA_ASPECT,
    ) -> None:
        """设置顶部媒体图片。

        Args:
            pixmap: 图片；None 移除媒体区。
            height: 固定高度（dp）；None 时按 ``aspect_ratio`` 随宽度变化。
            aspect_ratio: 宽高比，仅在 ``height`` 为 None 时使用。
        """
        self._media = pixmap
        self._media_height = height
        self._media_aspect = max(0.1, aspect_ratio)
        self._apply_content_margins()
        self.updateGeometry()
        self.update()

    @property
    def media(self) -> QtGui.QPixmap | None:
        """媒体图片。"""
        return self._media

    def media_height(self) -> float:
        """媒体区当前高度（无媒体时为 0）。"""
        if self._media is None:
            return 0.0
        if self._media_height is not None:
            return self._media_height
        return self.width() / self._media_aspect

    def media_rect(self) -> QtCore.QRectF:
        """媒体区矩形。"""
        rect = self.container_rect()
        return QtCore.QRectF(
            rect.left(), rect.top(), rect.width(), self.media_height()
        )

    @override
    def hasHeightForWidth(self) -> bool:
        return self._media is not None and self._media_height is None

    @override
    def heightForWidth(self, width: int) -> int:
        if not self.hasHeightForWidth():
            return -1
        media = width / self._media_aspect
        content = self._layout.totalMinimumSize().height() - round(
            self.media_height()
        )
        return round(media + max(0, content))

    # ---- 可展开内容 -------------------------------------------------------

    def set_expandable(self, expandable: bool) -> None:
        """启用后在内容末尾显示展开箭头与可折叠区域。"""
        if expandable and self._expanded_area is None:
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.addStretch()
            self._expand_button = _ExpandButton(self)
            self._expand_button.clicked.connect(self.toggle_expanded)
            row.addWidget(self._expand_button)
            self._layout.addLayout(row)
            self._expanded_area = QtWidgets.QWidget(self)
            self._expanded_layout = QtWidgets.QVBoxLayout(self._expanded_area)
            self._expanded_layout.setContentsMargins(0, 0, 0, 0)
            self._expanded_layout.setSpacing(round(spacing.SPACE_2))
            self._layout.addWidget(self._expanded_area)
            self._apply_expand_progress()
        elif not expandable and self._expanded_area is not None:
            index = self._layout.indexOf(self._expanded_area)
            row_item = self._layout.takeAt(index - 1)
            if row_item is not None and row_item.layout() is not None:
                row_item.layout().deleteLater()
            self._layout.removeWidget(self._expanded_area)
            self._expanded_area.deleteLater()
            if self._expand_button is not None:
                self._expand_button.deleteLater()
            self._expanded_area = None
            self._expanded_layout = None
            self._expand_button = None

    @property
    def expandable(self) -> bool:
        """是否可展开。"""
        return self._expanded_area is not None

    @property
    def expanded_layout(self) -> QtWidgets.QVBoxLayout:
        """展开区域的布局；未启用可展开时自动启用。"""
        layout = self._expanded_layout
        if layout is None:
            self.set_expandable(True)
            layout = self._expanded_layout
        if layout is None:
            raise RuntimeError("无法创建展开区域")
        return layout

    @property
    def expanded(self) -> bool:
        """展开区域是否展开。"""
        return self._expanded

    @property
    def expand_button(self) -> icon_button.IconButton | None:
        """展开箭头按钮。"""
        return self._expand_button

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        """展开或收起可折叠区域。"""
        if self._expanded_area is None:
            self.set_expandable(True)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        if self._expand_button is not None:
            self._expand_button.set_expanded(expanded)
        target = 1.0 if expanded else 0.0
        if animate:
            self._expand.animate_to(target, motion.MEDIUM2, motion.EMPHASIZED)
        else:
            self._expand.set(target)
        self.expanded_changed.emit(expanded)

    def toggle_expanded(self) -> None:
        """切换展开状态。"""
        self.set_expanded(not self._expanded)

    def _apply_expand_progress(self) -> None:
        area = self._expanded_area
        if area is None:
            return
        progress = self._expand.value
        full = area.sizeHint().height()
        height = round(full * progress)
        area.setVisible(height > 0)
        area.setMaximumHeight(height if progress < 0.999 else 16777215)
        self.updateGeometry()

    # ---- 拖动 -------------------------------------------------------------

    def set_draggable(
        self,
        draggable: bool,
        mime_type: str = DEFAULT_DRAG_MIME_TYPE,
        payload: str = "",
    ) -> None:
        """允许按住拖动卡片发起 ``QDrag``。

        Args:
            draggable: 是否可拖动。
            mime_type: 拖动数据的 MIME 类型。
            payload: 随拖动携带的文本数据；也可覆写 ``drag_mime_data``。
        """
        self._draggable = draggable
        self._drag_mime_type = mime_type
        self._drag_payload = payload

    @property
    def draggable(self) -> bool:
        """是否可拖动。"""
        return self._draggable

    def drag_mime_data(self) -> QtCore.QMimeData:
        """构造拖动携带的数据，子类可覆写。"""
        data = QtCore.QMimeData()
        data.setData(self._drag_mime_type, self._drag_payload.encode("utf-8"))
        if self._drag_payload:
            data.setText(self._drag_payload)
        return data

    def start_drag(self) -> QtCore.Qt.DropAction:
        """立即发起拖动并阻塞直到放下，返回放置动作。"""
        drag = QtGui.QDrag(self)
        drag.setMimeData(self.drag_mime_data())
        pixmap = self.grab()
        drag.setPixmap(pixmap)
        hotspot = (
            self._drag_press.toPoint()
            if self._drag_press is not None
            else self.rect().center()
        )
        drag.setHotSpot(hotspot)
        self.cancel_press()
        self.set_dragged(True)
        self.drag_started.emit()
        try:
            action = drag.exec(
                QtCore.Qt.DropAction.MoveAction
                | QtCore.Qt.DropAction.CopyAction
            )
        finally:
            self.set_dragged(False)
            self._drag_press = None
        self.drag_finished.emit(action)
        return action

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if (
            self._draggable
            and event.button() == QtCore.Qt.MouseButton.LeftButton
        ):
            self._drag_press = event.position()
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_press is not None and self._draggable:
            distance = (event.position() - self._drag_press).manhattanLength()
            if distance >= QtWidgets.QApplication.startDragDistance():
                self.start_drag()
                event.accept()
                return
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        self._drag_press = None
        super().mouseReleaseEvent(event)

    # ---- 属性 -------------------------------------------------------------

    @property
    def variant(self) -> CardVariant:
        """变体。"""
        return self._variant

    def set_variant(self, variant: CardVariant) -> None:
        """切换变体。"""
        self._variant = variant
        self._update_elevation()
        self.update()

    @property
    def clickable(self) -> bool:
        """是否可点击。"""
        return self._clickable

    def set_clickable(self, clickable: bool) -> None:
        """设置是否可点击。"""
        self._clickable = clickable
        self._apply_clickable()
        self.update()

    @property
    def dragged(self) -> bool:
        """是否处于拖拽态。"""
        return self._dragged

    def set_dragged(self, dragged: bool) -> None:
        """设置拖拽态（更高海拔与 16% 状态层）。"""
        self._dragged = dragged
        self.state_layer.set_dragged(dragged)
        self._update_elevation()

    def _apply_clickable(self) -> None:
        self.setFocusPolicy(
            QtCore.Qt.FocusPolicy.StrongFocus
            if self._clickable
            else QtCore.Qt.FocusPolicy.NoFocus
        )
        self.setCursor(
            QtCore.Qt.CursorShape.PointingHandCursor
            if self._clickable
            else QtCore.Qt.CursorShape.ArrowCursor
        )
        self.ripple.set_enabled(self._clickable)

    @override
    def is_interactive(self) -> bool:
        return self._clickable and self.isEnabled()

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        if self._clickable:
            return QtGui.QAccessible.Role.Button
        return QtGui.QAccessible.Role.Grouping

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_MEDIUM

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._media is not None and self._media_height is None:
            self._apply_content_margins()

    # ---- 颜色 -------------------------------------------------------------

    def _container_color(self) -> QtGui.QColor:
        disabled = not self.isEnabled()
        match self._variant:
            case CardVariant.ELEVATED:
                base = self.color("surface_container_low")
                if disabled:
                    return theme_module.with_alpha(
                        self.color("surface_variant"),
                        state_tokens.DISABLED_CONTENT_OPACITY,
                    )
                return base
            case CardVariant.FILLED:
                if disabled:
                    return theme_module.with_alpha(
                        self.color("surface_variant"),
                        state_tokens.DISABLED_CONTENT_OPACITY,
                    )
                return self.color("surface_container_highest")
            case _:
                return self.color("surface")

    def _outline_color(self) -> QtGui.QColor | None:
        if self._variant is not CardVariant.OUTLINED:
            return None
        if not self.isEnabled():
            return theme_module.with_alpha(
                self.color("outline"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
        return self.color("outline_variant")

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("on_surface")

    # ---- 绘制与海拔 -------------------------------------------------------

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        shape_utils.fill_shape(
            painter,
            self.container_path(),
            self._container_color(),
            self._outline_color(),
            OUTLINE_WIDTH,
        )

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        if self._media is None:
            return
        target = self.media_rect()
        if target.isEmpty():
            return
        painter.save()
        painter.setClipPath(self.container_path())
        # 按比例放大到覆盖整个媒体区后居中裁切。
        source_size = QtCore.QSizeF(self._media.deviceIndependentSize())
        scale = max(
            target.width() / source_size.width(),
            target.height() / source_size.height(),
        )
        scaled = QtCore.QSizeF(
            source_size.width() * scale, source_size.height() * scale
        )
        draw_rect = QtCore.QRectF(
            target.center().x() - scaled.width() / 2,
            target.center().y() - scaled.height() / 2,
            scaled.width(),
            scaled.height(),
        )
        painter.setClipRect(target, QtCore.Qt.ClipOperation.IntersectClip)
        painter.drawPixmap(
            draw_rect,
            self._media,
            QtCore.QRectF(0, 0, self._media.width(), self._media.height()),
        )
        painter.restore()

    @override
    def paint_overlays(self, painter: QtGui.QPainter) -> None:
        if self._clickable or self._dragged:
            super().paint_overlays(painter)

    def _update_elevation(self) -> None:
        hovered = self._clickable and self.state_layer.has(
            state_tokens.InteractionState.HOVERED
        )
        if not self.isEnabled():
            level = (
                elevation.Level.LEVEL_1
                if self._variant is CardVariant.ELEVATED
                else elevation.Level.LEVEL_0
            )
        elif self._dragged:
            level = (
                elevation.Level.LEVEL_4
                if self._variant is CardVariant.ELEVATED
                else elevation.Level.LEVEL_3
            )
        else:
            match self._variant:
                case CardVariant.ELEVATED:
                    level = (
                        elevation.Level.LEVEL_2
                        if hovered
                        else elevation.Level.LEVEL_1
                    )
                case CardVariant.FILLED:
                    level = (
                        elevation.Level.LEVEL_1
                        if hovered
                        else elevation.Level.LEVEL_0
                    )
                case _:
                    level = (
                        elevation.Level.LEVEL_1
                        if hovered
                        else elevation.Level.LEVEL_0
                    )
        self.set_elevation(level)

    @override
    def enterEvent(self, event: QtGui.QEnterEvent) -> None:
        super().enterEvent(event)
        self._update_elevation()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        super().leaveEvent(event)
        self._update_elevation()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.EnabledChange:
            self._update_elevation()


class ElevatedCard(Card):
    """带阴影的卡片。"""

    def __init__(
        self, clickable: bool = False, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(CardVariant.ELEVATED, clickable, parent)


class FilledCard(Card):
    """填充色卡片。"""

    def __init__(
        self, clickable: bool = False, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(CardVariant.FILLED, clickable, parent)


class OutlinedCard(Card):
    """描边卡片。"""

    def __init__(
        self, clickable: bool = False, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(CardVariant.OUTLINED, clickable, parent)
