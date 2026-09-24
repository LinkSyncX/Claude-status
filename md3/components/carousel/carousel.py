"""轮播（Carousel）。

M3 轮播用一组"关键线"（keyline）描述项目在视口中的尺寸与位置：项目在
未调整的滚动轴上等宽排列，绘制时按所处位置在相邻关键线之间插值出实际
尺寸与中心，于是项目从大到中到小平滑收缩、在边缘被遮罩裁掉。

- ``MULTI_BROWSE``：若干大项 + 一中一小，靠近末尾时关键线镜像，使最后
  一项能以大尺寸显示在右侧。
- ``HERO``：一大一小。
- ``UNCONTAINED``：等宽项目自由滚动并在边缘被裁切。
- ``FULL_SCREEN``：竖向分页，一次显示一项。

项目容器为 28dp 圆角，图片按大尺寸绘制并随容器收缩被遮罩（而不是
压扁）；标题在小项上淡出。支持拖动、滚轮、方向键，松手后吸附到最近的
项目。
"""

from __future__ import annotations

from collections.abc import Sequence
import dataclasses
import enum
import math
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.core import animation
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ITEM_GAP = 8.0
SMALL_SIZE = 56.0
SMALL_MIN = 40.0
ANCHOR_SIZE = 4.0
DEFAULT_ITEM_HEIGHT = 200.0
DEFAULT_PREFERRED_WIDTH = 240.0
LABEL_PADDING = 16.0
TITLE_STYLE = typography_tokens.TypeRole.TITLE_MEDIUM
SUBTITLE_STYLE = typography_tokens.TypeRole.BODY_SMALL
SNAP_DURATION = motion.MEDIUM4
# 项目宽度低于大尺寸的此比例时标题完全淡出。
LABEL_FADE_START = 0.85
LABEL_FADE_END = 0.55
# 拖动超过此距离才视为拖动而非点击。
DRAG_THRESHOLD = 6.0


class CarouselLayout(enum.Enum):
    """轮播布局。"""

    MULTI_BROWSE = "multi_browse"
    HERO = "hero"
    UNCONTAINED = "uncontained"
    FULL_SCREEN = "full_screen"


@dataclasses.dataclass
class CarouselItem:
    """一个轮播项。

    Attributes:
        pixmap: 图片；None 时以 ``color`` 填充（默认
            ``surface_container_highest``）。
        title: 标题，叠加在项目底部。
        subtitle: 副标题。
        color: 无图片时的填充色（``QColor``、色彩角色名或十六进制）。
        icon: 无图片时居中显示的图标。
        key: 业务侧标识。
    """

    pixmap: QtGui.QPixmap | None = None
    title: str = ""
    subtitle: str = ""
    color: QtGui.QColor | str | None = None
    icon: icons.IconLike = None
    key: Any = None


@dataclasses.dataclass(frozen=True)
class Keyline:
    """一条关键线。

    Attributes:
        size: 位于该关键线的项目尺寸。
        offset: 项目中心在视口中的位置。
        unadjusted: 项目中心在未调整滚动轴上的位置。
    """

    size: float
    offset: float
    unadjusted: float


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def arrangement_sizes(
    viewport: float,
    preferred: float,
    layout: CarouselLayout,
    gap: float = ITEM_GAP,
) -> list[float]:
    """按视口宽度计算起始状态下各非锚点关键线的尺寸（从左到右）。

    Args:
        viewport: 视口宽度。
        preferred: 大项的期望宽度。
        layout: ``MULTI_BROWSE`` 或 ``HERO``。
        gap: 项目间距。
    """
    viewport = max(1.0, viewport)
    if layout is CarouselLayout.HERO:
        small = min(SMALL_SIZE, max(SMALL_MIN, viewport * 0.15))
        large = viewport - small - gap
        if large < small * 2:
            return [viewport]
        return [large, small]
    small = SMALL_SIZE
    medium = max(small * 1.5, min(preferred * 0.6, viewport * 0.3))
    remaining = viewport - small - medium - 2 * gap
    if remaining < preferred * 0.6:
        # 视口太窄：退化为一大一小，仍不够则只放一项。
        small = min(SMALL_SIZE, max(SMALL_MIN, viewport * 0.15))
        large = viewport - small - gap
        return [large, small] if large >= small * 2 else [viewport]
    count = max(1, round(remaining / (preferred + gap)))
    large = (remaining - gap * (count - 1)) / count
    while count > 1 and large < medium:
        count -= 1
        large = (remaining - gap * (count - 1)) / count
    return [large] * count + [medium, small]


def build_keylines(
    sizes: Sequence[float],
    large: float,
    gap: float = ITEM_GAP,
    mirrored: bool = False,
) -> list[Keyline]:
    """由尺寸序列生成含两端锚点的关键线列表。

    未调整位置按每项都是 ``large`` 宽计算；``mirrored`` 为真时尺寸顺序反转
    （用于末尾状态），未调整位置保持不变。
    """
    ordered = list(reversed(sizes)) if mirrored else list(sizes)
    keylines: list[Keyline] = []
    step = large + gap
    # 左锚点：位于视口外一个极小尺寸，使项目滑出时收缩到几乎不可见。
    keylines.append(
        Keyline(ANCHOR_SIZE, -ANCHOR_SIZE / 2 - gap, -step + large / 2)
    )
    cursor = 0.0
    for index, size in enumerate(ordered):
        keylines.append(
            Keyline(size, cursor + size / 2, index * step + large / 2)
        )
        cursor += size + gap
    total = cursor - gap
    keylines.append(
        Keyline(
            ANCHOR_SIZE,
            total + gap + ANCHOR_SIZE / 2,
            len(ordered) * step + large / 2,
        )
    )
    return keylines


def interpolate_keylines(
    start: Sequence[Keyline], end: Sequence[Keyline], fraction: float
) -> list[Keyline]:
    """在起始与末尾关键线之间按比例插值（两者数量相同）。"""
    fraction = max(0.0, min(1.0, fraction))
    return [
        Keyline(
            _lerp(a.size, b.size, fraction),
            _lerp(a.offset, b.offset, fraction),
            a.unadjusted,
        )
        for a, b in zip(start, end, strict=True)
    ]


def place(
    keylines: Sequence[Keyline], unadjusted: float
) -> tuple[float, float]:
    """把未调整位置映射为 (视口中心, 尺寸)。超出锚点范围时返回尺寸 0。"""
    if (
        unadjusted < keylines[0].unadjusted
        or unadjusted > keylines[-1].unadjusted
    ):
        return 0.0, 0.0
    for lower, upper in zip(keylines, keylines[1:], strict=False):
        if lower.unadjusted <= unadjusted <= upper.unadjusted:
            span = upper.unadjusted - lower.unadjusted or 1.0
            t = (unadjusted - lower.unadjusted) / span
            return _lerp(lower.offset, upper.offset, t), _lerp(
                lower.size, upper.size, t
            )
    return 0.0, 0.0


class Carousel(widget.MaterialWidget):
    """轮播控件。

    Args:
        items: 轮播项。
        layout: 布局。
        item_height: 项目高度（横向布局）；全屏布局忽略。
        preferred_item_width: 大项的期望宽度（multi-browse）或等宽项的宽度
            （uncontained）。
        parent: 父控件。
    """

    item_clicked = QtCore.Signal(int)
    current_changed = QtCore.Signal(int)

    def __init__(
        self,
        items: Sequence[CarouselItem] | None = None,
        layout: CarouselLayout = CarouselLayout.MULTI_BROWSE,
        item_height: float = DEFAULT_ITEM_HEIGHT,
        preferred_item_width: float = DEFAULT_PREFERRED_WIDTH,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[CarouselItem] = list(items or [])
        self._layout_kind = layout
        self._item_height = item_height
        self._preferred = preferred_item_width
        self._gap = ITEM_GAP
        # 滚动偏移（未调整轴上的像素），带过渡动画。
        self._scroll = animation.AnimatedFloat(self, 0.0, self._on_scroll)
        self._current = 0
        self._hovered = -1
        self._press_pos: QtCore.QPointF | None = None
        self._press_scroll = 0.0
        self._dragging = False
        self._layers: dict[int, float] = {}
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
            if layout is CarouselLayout.FULL_SCREEN
            else QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.List

    @override
    def accessible_value(self) -> str:
        if not self._items:
            return ""
        return f"{self.current_index + 1}/{len(self._items)}"

    # ---- 数据 -------------------------------------------------------------

    @property
    def items(self) -> list[CarouselItem]:
        """轮播项。"""
        return list(self._items)

    def set_items(self, items: Sequence[CarouselItem]) -> None:
        """替换轮播项并回到开头。"""
        self._items = list(items)
        self._hovered = -1
        self._scroll.set(0.0)
        self._set_current(0)
        self.update()

    @property
    def layout_kind(self) -> CarouselLayout:
        """布局。"""
        return self._layout_kind

    def set_layout(self, layout: CarouselLayout) -> None:
        """切换布局，保持当前项。"""
        current = self._current
        self._layout_kind = layout
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding
            if layout is CarouselLayout.FULL_SCREEN
            else QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._scroll.set(self._scroll_for(current))
        self.updateGeometry()
        self.update()

    @property
    def item_height(self) -> float:
        """项目高度。"""
        return self._item_height

    def set_item_height(self, height: float) -> None:
        """设置项目高度（横向布局）。"""
        self._item_height = height
        self.updateGeometry()
        self.update()

    @property
    def current_index(self) -> int:
        """当前项（位于第一条大关键线 / 当前页）。"""
        return self._current

    @property
    def scroll_offset(self) -> float:
        """当前滚动偏移（未调整轴上的像素）。"""
        return self._scroll.value

    # ---- 几何 -------------------------------------------------------------

    def viewport_rect(self) -> QtCore.QRectF:
        """项目所在的视口矩形。"""
        return QtCore.QRectF(self.rect())

    def _horizontal(self) -> bool:
        return self._layout_kind is not CarouselLayout.FULL_SCREEN

    def _extent(self) -> float:
        """滚动轴上的视口长度。"""
        rect = self.viewport_rect()
        return rect.width() if self._horizontal() else rect.height()

    def _sizes(self) -> list[float]:
        """起始状态下的非锚点关键线尺寸。"""
        extent = self._extent()
        match self._layout_kind:
            case CarouselLayout.MULTI_BROWSE | CarouselLayout.HERO:
                return arrangement_sizes(
                    extent, self._preferred, self._layout_kind, self._gap
                )
            case CarouselLayout.UNCONTAINED:
                return [min(self._preferred, extent)]
            case _:
                return [extent]

    def large_size(self) -> float:
        """大项（未调整轴上的项目）尺寸。"""
        sizes = self._sizes()
        return sizes[0] if sizes else 1.0

    def _step(self) -> float:
        return self.large_size() + self._gap

    def keylines(self) -> list[Keyline]:
        """当前滚动位置下生效的关键线。"""
        sizes = self._sizes()
        large = self.large_size()
        if self._layout_kind in (
            CarouselLayout.UNCONTAINED,
            CarouselLayout.FULL_SCREEN,
        ):
            # 等宽项目：视口内放尽可能多的关键线，再加两端锚点保持满尺寸。
            step = large + self._gap
            count = max(1, math.ceil(self._extent() / step) + 1)
            keylines = [
                Keyline(
                    large, index * step + large / 2, index * step + large / 2
                )
                for index in range(-1, count + 1)
            ]
            return keylines
        start = build_keylines(sizes, large, self._gap)
        if len(sizes) <= 1:
            return start
        end = build_keylines(sizes, large, self._gap, mirrored=True)
        # 末尾状态相对起始状态，大关键线整体右移了中、小项占据的距离；
        # 最后这段滚动距离内在两种排列之间插值。
        smaller = [size for size in sizes if size < large]
        shift_range = sum(smaller) + self._gap * len(smaller)
        max_scroll = self.max_scroll()
        if shift_range <= 0 or max_scroll <= 0:
            return start
        fraction = (
            self._scroll.value - (max_scroll - shift_range)
        ) / shift_range
        return interpolate_keylines(start, end, fraction)

    def max_scroll(self) -> float:
        """最大滚动偏移。"""
        count = len(self._items)
        if count == 0:
            return 0.0
        step = self._step()
        if self._layout_kind in (
            CarouselLayout.UNCONTAINED,
            CarouselLayout.FULL_SCREEN,
        ):
            total = count * step - self._gap
            return max(0.0, total - self._extent())
        visible = len(self._sizes())
        return max(0.0, (count - visible) * step)

    def _scroll_for(self, index: int) -> float:
        index = max(0, min(len(self._items) - 1, index)) if self._items else 0
        return max(0.0, min(self.max_scroll(), index * self._step()))

    def item_rects(self) -> list[tuple[int, QtCore.QRectF]]:
        """当前可见项目的 (下标, 矩形)。"""
        if not self._items:
            return []
        keylines = self.keylines()
        large = self.large_size()
        step = self._step()
        rect = self.viewport_rect()
        result: list[tuple[int, QtCore.QRectF]] = []
        for index in range(len(self._items)):
            unadjusted = index * step + large / 2 - self._scroll.value
            center, size = place(keylines, unadjusted)
            if size < 1.0:
                continue
            if self._horizontal():
                item_rect = QtCore.QRectF(
                    rect.left() + center - size / 2,
                    rect.top(),
                    size,
                    rect.height(),
                )
            else:
                item_rect = QtCore.QRectF(
                    rect.left(),
                    rect.top() + center - size / 2,
                    rect.width(),
                    size,
                )
            if item_rect.intersects(rect):
                result.append((index, item_rect))
        return result

    def index_at(self, position: QtCore.QPointF) -> int:
        """位置对应的项目下标，无命中返回 -1。"""
        for index, item_rect in self.item_rects():
            if item_rect.contains(position):
                return index
        return -1

    @override
    def sizeHint(self) -> QtCore.QSize:
        if self._layout_kind is CarouselLayout.FULL_SCREEN:
            return QtCore.QSize(360, int(self._item_height))
        return QtCore.QSize(480, int(self._item_height))

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(160, 80)

    # ---- 滚动 -------------------------------------------------------------

    def scroll_to(self, index: int, animate: bool = True) -> None:
        """滚动使第 index 项成为当前项。"""
        if not self._items:
            return
        index = max(0, min(len(self._items) - 1, index))
        target = self._scroll_for(index)
        if animate:
            self._scroll.animate_to(
                target, SNAP_DURATION, motion.EMPHASIZED_DECELERATE
            )
        else:
            self._scroll.set(target)
        self._set_current(index)

    def snap(self, animate: bool = True) -> None:
        """吸附到离当前偏移最近的项目。"""
        if not self._items:
            return
        index = round(self._scroll.value / self._step())
        self.scroll_to(index, animate)

    def _set_current(self, index: int) -> None:
        if index != self._current:
            self._current = index
            self.current_changed.emit(index)

    def _on_scroll(self) -> None:
        self.update()

    def _set_scroll_raw(self, value: float) -> None:
        self._scroll.set(max(0.0, min(self.max_scroll(), value)))

    # ---- 绘制 -------------------------------------------------------------

    def _item_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_EXTRA_LARGE

    def _fill_color(self, item: CarouselItem) -> QtGui.QColor:
        if item.color is None:
            return self.color("surface_container_highest")
        if isinstance(item.color, QtGui.QColor):
            return item.color
        if item.color.startswith("#"):
            return QtGui.QColor(item.color)
        return self.color(item.color)

    def _label_opacity(self, size: float) -> float:
        large = self.large_size()
        if large <= 0:
            return 1.0
        ratio = size / large
        if ratio >= LABEL_FADE_START:
            return 1.0
        if ratio <= LABEL_FADE_END:
            return 0.0
        return (ratio - LABEL_FADE_END) / (LABEL_FADE_START - LABEL_FADE_END)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        large = self.large_size()
        for index, item_rect in self.item_rects():
            item = self._items[index]
            path = shape_utils.rounded_rect_path(item_rect, self._item_shape())
            painter.save()
            painter.setClipPath(path)
            self._paint_item_content(painter, item, item_rect, large)
            if index == self._hovered:
                shape_utils.fill_shape(
                    painter,
                    path,
                    theme_module.with_alpha(
                        self.color("on_surface"),
                        state_tokens.HOVER_STATE_LAYER_OPACITY,
                    ),
                )
            painter.restore()
            if self.hasFocus() and index == self._current:
                shape_utils.fill_shape(
                    painter, path, None, self.color("secondary"), 2.0
                )

    def _paint_item_content(
        self,
        painter: QtGui.QPainter,
        item: CarouselItem,
        item_rect: QtCore.QRectF,
        large: float,
    ) -> None:
        horizontal = self._horizontal()
        full = (
            QtCore.QRectF(
                item_rect.center().x() - large / 2,
                item_rect.top(),
                large,
                item_rect.height(),
            )
            if horizontal
            else QtCore.QRectF(
                item_rect.left(),
                item_rect.center().y() - large / 2,
                item_rect.width(),
                large,
            )
        )
        if item.pixmap is not None and not item.pixmap.isNull():
            # 图片按大尺寸居中绘制，收缩时被裁剪而不是压扁。
            scaled = item.pixmap.scaled(
                full.size().toSize(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            source = QtCore.QRectF(
                (scaled.width() - full.width()) / 2,
                (scaled.height() - full.height()) / 2,
                full.width(),
                full.height(),
            )
            painter.drawPixmap(full, scaled, source)
        else:
            painter.fillRect(item_rect, self._fill_color(item))
            icon = icons.coerce(item.icon, 48)
            if icon is not None:
                painter.setOpacity(self._label_opacity(item_rect.width()))
                icon.paint(
                    painter,
                    QtCore.QRectF(
                        full.center().x() - 24, full.center().y() - 40, 48, 48
                    ),
                    self.color("on_surface_variant"),
                )
                painter.setOpacity(1.0)
        if item.title or item.subtitle:
            self._paint_label(painter, item, item_rect, full)

    def _paint_label(
        self,
        painter: QtGui.QPainter,
        item: CarouselItem,
        item_rect: QtCore.QRectF,
        full: QtCore.QRectF,
    ) -> None:
        size = item_rect.width() if self._horizontal() else item_rect.height()
        opacity = self._label_opacity(size)
        if opacity <= 0.01:
            return
        title_style = self.theme.style(TITLE_STYLE)
        subtitle_style = self.theme.style(SUBTITLE_STYLE)
        block = title_style.line_height if item.title else 0.0
        block += subtitle_style.line_height if item.subtitle else 0.0
        scrim_height = block + 2 * LABEL_PADDING + 24
        gradient = QtGui.QLinearGradient(
            QtCore.QPointF(0, item_rect.bottom() - scrim_height),
            QtCore.QPointF(0, item_rect.bottom()),
        )
        gradient.setColorAt(0.0, QtGui.QColor(0, 0, 0, 0))
        gradient.setColorAt(1.0, QtGui.QColor(0, 0, 0, int(160 * opacity)))
        painter.fillRect(
            QtCore.QRectF(
                item_rect.left(),
                item_rect.bottom() - scrim_height,
                item_rect.width(),
                scrim_height,
            ),
            gradient,
        )
        painter.setOpacity(opacity)
        text_left = full.left() + LABEL_PADDING
        width = max(0.0, full.width() - 2 * LABEL_PADDING)
        y = item_rect.bottom() - LABEL_PADDING - block
        color = QtGui.QColor("white")
        if item.title:
            typography.paint_text(
                painter,
                QtCore.QRectF(text_left, y, width, title_style.line_height),
                item.title,
                TITLE_STYLE,
                color,
            )
            y += title_style.line_height
        if item.subtitle:
            typography.paint_text(
                painter,
                QtCore.QRectF(text_left, y, width, subtitle_style.line_height),
                item.subtitle,
                SUBTITLE_STYLE,
                theme_module.with_alpha(color, 0.85),
            )
        painter.setOpacity(1.0)

    # ---- 交互 -------------------------------------------------------------

    def _axis(self, point: QtCore.QPointF) -> float:
        return point.x() if self._horizontal() else point.y()

    @override
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._press_pos = event.position()
            self._press_scroll = self._scroll.value
            self._dragging = False
            self.setFocus(QtCore.Qt.FocusReason.MouseFocusReason)
            event.accept()
            return
        super().mousePressEvent(event)

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._press_pos is not None:
            delta = self._axis(self._press_pos) - self._axis(event.position())
            if self._dragging or abs(delta) > DRAG_THRESHOLD:
                self._dragging = True
                self._set_scroll_raw(self._press_scroll + delta)
                event.accept()
                return
        hovered = self.index_at(event.position())
        if hovered != self._hovered:
            self._hovered = hovered
            self.setCursor(
                QtCore.Qt.CursorShape.PointingHandCursor
                if hovered >= 0
                else QtCore.Qt.CursorShape.ArrowCursor
            )
            self.update()
        super().mouseMoveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._press_pos is None:
            super().mouseReleaseEvent(event)
            return
        self._press_pos = None
        if self._dragging:
            self._dragging = False
            self.snap()
        else:
            index = self.index_at(event.position())
            if index >= 0:
                self.item_clicked.emit(index)
                # 点击非当前项时把它滚动到主位置。
                if index != self._current:
                    self.scroll_to(index)
        event.accept()

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        delta = event.angleDelta().y() or event.angleDelta().x()
        if delta == 0:
            super().wheelEvent(event)
            return
        self.scroll_to(self._current + (-1 if delta > 0 else 1))
        event.accept()

    @override
    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        key = event.key()
        forward = (
            (QtCore.Qt.Key.Key_Right, QtCore.Qt.Key.Key_Down)
            if self._horizontal()
            else (QtCore.Qt.Key.Key_Down, QtCore.Qt.Key.Key_Right)
        )
        backward = (
            (QtCore.Qt.Key.Key_Left, QtCore.Qt.Key.Key_Up)
            if self._horizontal()
            else (QtCore.Qt.Key.Key_Up, QtCore.Qt.Key.Key_Left)
        )
        if key in forward:
            self.scroll_to(self._current + 1)
        elif key in backward:
            self.scroll_to(self._current - 1)
        elif key == QtCore.Qt.Key.Key_Home:
            self.scroll_to(0)
        elif key == QtCore.Qt.Key.Key_End:
            self.scroll_to(len(self._items) - 1)
        elif key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
            if self._items:
                self.item_clicked.emit(self._current)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        # 视口变化后关键线尺寸改变，保持当前项对齐。
        self._scroll.set(self._scroll_for(self._current))
