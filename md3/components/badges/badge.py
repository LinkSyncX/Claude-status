"""徽标（Badges）：6dp 小圆点或带数字 / 文字的 16dp 胶囊。

``Badge`` 可以独立摆放，也可以用 ``attach`` 挂到任意控件的右上角（如图标
按钮）并随其尺寸变化自动定位；数字变化时徽标会以弹簧"弹跳"一下，出现与
消失时缩放过渡。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

SMALL_SIZE = 6.0
LARGE_HEIGHT = 16.0
LARGE_MIN_WIDTH = 16.0
LARGE_PADDING = 4.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_SMALL
MAX_COUNT = 999
# 计数变化时的弹跳幅度（相对尺寸）。
BUMP_SCALE = 1.25
# 挂载徽标时，默认把锚点视为控件中央的 24dp 图标。
DEFAULT_ANCHOR_ICON = 24.0


def badge_text(count: int | None, max_count: int = MAX_COUNT) -> str:
    """把计数转换为徽标文字，超过上限时显示 ``999+``。"""
    if count is None:
        return ""
    if count > max_count:
        return f"{max_count}+"
    return str(count)


def badge_size(text: str) -> QtCore.QSizeF:
    """徽标的尺寸（dp）。"""
    if not text:
        return QtCore.QSizeF(SMALL_SIZE, SMALL_SIZE)
    width = typography.text_width(text, LABEL_STYLE) + 2 * LARGE_PADDING
    return QtCore.QSizeF(max(LARGE_MIN_WIDTH, width), LARGE_HEIGHT)


def badge_rect(
    anchor: QtCore.QRectF, text: str, rtl: bool = False
) -> QtCore.QRectF:
    """徽标相对锚点（通常是图标矩形）的位置。

    小徽标位于锚点末尾侧上角内侧；大徽标的起始侧下角贴近锚点末尾侧上角，
    与 M3 导航项中的位置一致。``rtl`` 为真时末尾侧为左边。
    """
    size = badge_size(text)
    if not text:
        x = anchor.left() if rtl else anchor.right() - SMALL_SIZE
        return QtCore.QRectF(x, anchor.top(), size.width(), size.height())
    x = anchor.left() + 6.0 - size.width() if rtl else anchor.right() - 6.0
    return QtCore.QRectF(x, anchor.top() - 6.0, size.width(), size.height())


def paint_badge(
    painter: QtGui.QPainter,
    anchor: QtCore.QRectF,
    text: str = "",
    theme: theme_module.Theme | None = None,
    rtl: bool = False,
) -> QtCore.QRectF:
    """在锚点末尾侧上角绘制徽标并返回其矩形。"""
    theme = theme or theme_module.current()
    rect = badge_rect(anchor, text, rtl)
    path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_FULL)
    shape_utils.fill_shape(painter, path, theme.color("error"))
    if text:
        typography.paint_text(
            painter,
            rect,
            text,
            LABEL_STYLE,
            theme.color("on_error"),
            QtCore.Qt.AlignmentFlag.AlignCenter,
            elide=False,
        )
    return rect


class Badge(widget.MaterialWidget):
    """独立的徽标控件。

    Args:
        count: 数字；None 表示小圆点。
        text: 自定义文字（优先于 count）。
        max_count: 数字上限，超过后显示 ``N+``。
        parent: 父控件。
    """

    def __init__(
        self,
        count: int | None = None,
        text: str = "",
        max_count: int = MAX_COUNT,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._count = count
        self._text = text
        self._max_count = max_count
        # 缩放系数：出现 0→1、计数变化时短暂超过 1 再回落。
        self._scale = animation.AnimatedFloat(self, 1.0, self.update)
        self._scale.finished.connect(self._after_scale)
        self._hiding = False
        self.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def label(self) -> str:
        """实际显示的文字。"""
        return self._text or badge_text(self._count, self._max_count)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.StaticText

    @override
    def accessible_name(self) -> str:
        return self.label

    @property
    def count(self) -> int | None:
        """数字。"""
        return self._count

    def set_count(self, count: int | None) -> None:
        """设置数字；文字变化时徽标弹跳一下。"""
        previous = self.label
        self._count = count
        self._text = ""
        self._apply_label_change(previous)

    def set_text(self, text: str) -> None:
        """设置自定义文字。"""
        previous = self.label
        self._text = text
        self._apply_label_change(previous)

    def _apply_label_change(self, previous: str) -> None:
        self.updateGeometry()
        if self.label != previous and self.isVisible():
            self.bump()
        self.update()

    def bump(self) -> None:
        """播放一次弹跳动画（放大后以弹簧回落）。"""
        self._scale.set(BUMP_SCALE)
        self._scale.spring_to(1.0, motion.EXPRESSIVE_FAST_SPATIAL)

    @property
    def scale(self) -> float:
        """当前缩放系数。"""
        return self._scale.value

    def show_animated(self) -> None:
        """以缩放动画出现。"""
        self._hiding = False
        if not self.isVisible():
            self._scale.set(0.0)
            self.show()
        self._scale.spring_to(1.0, motion.EXPRESSIVE_DEFAULT_SPATIAL)

    def hide_animated(self) -> None:
        """以缩放动画消失。"""
        if not self.isVisible():
            return
        self._hiding = True
        self._scale.animate_to(0.0, motion.SHORT3, motion.EMPHASIZED_ACCELERATE)

    def _after_scale(self) -> None:
        if self._hiding and self._scale.value <= 0.001:
            self._hiding = False
            self.hide()

    @override
    def sizeHint(self) -> QtCore.QSize:
        size = badge_size(self.label)
        return typography.size_hint(size.width(), size.height())

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        text = self.label
        rect = QtCore.QRectF(self.rect())
        size = badge_size(text)
        badge = QtCore.QRectF(
            rect.center().x() - size.width() / 2,
            rect.center().y() - size.height() / 2,
            size.width(),
            size.height(),
        )
        scale = self._scale.value
        if scale <= 0.001:
            return
        painter.save()
        if abs(scale - 1.0) > 1e-3:
            painter.translate(badge.center())
            painter.scale(scale, scale)
            painter.translate(-badge.center())
        path = shape_utils.rounded_rect_path(badge, shape_tokens.SHAPE_FULL)
        shape_utils.fill_shape(painter, path, self.color("error"))
        if text:
            typography.paint_text(
                painter,
                badge,
                text,
                LABEL_STYLE,
                self.color("on_error"),
                QtCore.Qt.AlignmentFlag.AlignCenter,
                elide=False,
            )
        painter.restore()


class AttachedBadge(Badge):
    """挂在目标控件右上角的徽标，随目标位置、尺寸与可见性自动同步。

    徽标放在目标的父控件中而不是目标内部，因此多位数字可以越出 48dp 的
    图标按钮而不被裁掉；目标尚未加入父控件时暂作其子控件，之后自动迁移。
    位置按 M3 规范相对"图标矩形"计算：目标若实现 ``badge_anchor_rect()``
    则使用其返回值，否则视为居中的 24dp 图标。

    Args:
        target: 被挂载的控件。
        count: 数字；None 表示小圆点。
        text: 自定义文字。
        max_count: 数字上限。
    """

    _TRACKED_EVENTS = frozenset(
        {
            QtCore.QEvent.Type.Resize,
            QtCore.QEvent.Type.Move,
            QtCore.QEvent.Type.Show,
            QtCore.QEvent.Type.Hide,
            QtCore.QEvent.Type.ParentChange,
            QtCore.QEvent.Type.ZOrderChange,
        }
    )

    def __init__(
        self,
        target: QtWidgets.QWidget,
        count: int | None = None,
        text: str = "",
        max_count: int = MAX_COUNT,
    ) -> None:
        super().__init__(count, text, max_count, target)
        self._target = target
        self._user_hidden = False
        target.installEventFilter(self)
        target.destroyed.connect(self.deleteLater)
        self._sync()

    @property
    def target(self) -> QtWidgets.QWidget:
        """被挂载的控件。"""
        return self._target

    def anchor_rect(self) -> QtCore.QRectF:
        """徽标所依附的锚点矩形（目标坐标）。"""
        provider = getattr(self._target, "badge_anchor_rect", None)
        if callable(provider):
            return QtCore.QRectF(provider())
        rect = QtCore.QRectF(self._target.rect())
        return QtCore.QRectF(
            rect.center().x() - DEFAULT_ANCHOR_ICON / 2,
            rect.center().y() - DEFAULT_ANCHOR_ICON / 2,
            DEFAULT_ANCHOR_ICON,
            DEFAULT_ANCHOR_ICON,
        )

    def _adopt_parent(self) -> None:
        """迁移到目标的父控件，以便越出目标边界。"""
        parent = self._target.parentWidget() or self._target
        if self.parentWidget() is not parent:
            self.setParent(parent)

    def reposition(self) -> None:
        """按锚点重新摆放徽标。"""
        rtl = (
            self._target.layoutDirection()
            == QtCore.Qt.LayoutDirection.RightToLeft
        )
        rect = badge_rect(self.anchor_rect(), self.label, rtl)
        offset = (
            self._target.pos()
            if self.parentWidget() is not self._target
            else QtCore.QPoint()
        )
        # 控件矩形略大于徽标，为弹跳放大留出空间。
        margin = 4
        self.setGeometry(
            QtCore.QRect(
                round(rect.left() - margin) + offset.x(),
                round(rect.top() - margin) + offset.y(),
                round(rect.width() + 2 * margin),
                round(rect.height() + 2 * margin),
            )
        )

    def _sync(self) -> None:
        self._adopt_parent()
        self.reposition()
        self.setVisible(self._target.isVisible() and not self._user_hidden)
        self.raise_()

    @override
    def show_animated(self) -> None:
        self._user_hidden = False
        super().show_animated()

    @override
    def hide_animated(self) -> None:
        self._user_hidden = True
        super().hide_animated()

    @override
    def _apply_label_change(self, previous: str) -> None:
        self.reposition()
        super()._apply_label_change(previous)

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if watched is self._target and event.type() in self._TRACKED_EVENTS:
            self._sync()
        return super().eventFilter(watched, event)


def attach(
    target: QtWidgets.QWidget,
    count: int | None = None,
    text: str = "",
    max_count: int = MAX_COUNT,
) -> AttachedBadge:
    """给控件挂上徽标并返回它。

    Example:
        >>> badge = badges.attach(icon_button, 3)
        >>> badge.set_count(4)          # 弹跳一下
        >>> badge.hide_animated()       # 缩放消失
    """
    return AttachedBadge(target, count, text, max_count)
