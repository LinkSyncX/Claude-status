"""头像（Avatar）与头像组（Avatar group）。

``Avatar`` 以圆形（或圆角方形）显示图片、图标或姓名首字母：首字母头像
的颜色由姓名哈希得到 HCT 色相，再按主题的容器 / 内容色调生成，同一个
名字在明暗主题下始终对应同一色相。可选的状态圆点位于右下角（RTL 为
左下角）。``AvatarGroup`` 把多个头像重叠排列，超出 ``max_visible`` 的
以 "+N" 头像收尾。
"""

from __future__ import annotations

import enum
from typing import override
import zlib

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.color import tonal_palette
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import typography as typography_tokens

DEFAULT_SIZE = 40.0
INITIALS_CHROMA = 40.0
STATUS_RATIO = 0.28
STATUS_BORDER = 2.0
OVERLAP_RATIO = 0.3


class AvatarStatus(enum.Enum):
    """在线状态，值为对应的色彩角色名。"""

    ONLINE = "online"
    AWAY = "away"
    BUSY = "busy"
    OFFLINE = "offline"


def initials_of(name: str) -> str:
    """从姓名提取首字母：多个单词取前两个单词的首字母，否则取前两个字符。

    中日韩姓名取第一个字符。
    """
    words = [word for word in name.replace("_", " ").split() if word]
    if not words:
        return ""
    if len(words) >= 2:
        return (words[0][0] + words[1][0]).upper()
    word = words[0]
    if any("\u4e00" <= char <= "\u9fff" for char in word):
        return word[0]
    return word[:2].upper()


def hue_of(name: str) -> float:
    """由姓名哈希得到 0–360 的稳定色相。"""
    return zlib.crc32(name.encode("utf-8")) % 360


def initials_colors(
    name: str, theme: theme_module.Theme | None = None
) -> tuple[QtGui.QColor, QtGui.QColor]:
    """首字母头像的 (背景色, 文字色)，按主题明暗取容器 / 内容色调。"""
    theme = theme or theme_module.current()
    palette = tonal_palette.TonalPalette.from_hue_and_chroma(
        hue_of(name), INITIALS_CHROMA
    )
    if theme.dark:
        return (
            theme_module.qcolor(palette.tone(30)),
            theme_module.qcolor(palette.tone(90)),
        )
    return (
        theme_module.qcolor(palette.tone(90)),
        theme_module.qcolor(palette.tone(30)),
    )


class Avatar(widget.MaterialWidget):
    """头像。

    Args:
        name: 姓名，用于首字母与配色（也作为无障碍名称）。
        image: 图片；提供时优先显示。
        icon: 图标；无图片且无姓名时显示，默认 ``person``。
        size: 直径（dp）。
        rounded: 为真使用 12dp 圆角方形而非圆形。
        status: 在线状态或自定义颜色（色彩角色名 / ``QColor``）。
        label: 直接显示的文字（替代由姓名推导的首字母，例如 "+3"）。
        parent: 父控件。
    """

    def __init__(
        self,
        name: str = "",
        image: QtGui.QPixmap | None = None,
        icon: icons.IconLike = None,
        size: float = DEFAULT_SIZE,
        rounded: bool = False,
        status: AvatarStatus | str | QtGui.QColor | None = None,
        label: str = "",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._name = name
        self._image = image
        self._icon = icon
        self._size = size
        self._rounded = rounded
        self._status = status
        self._label = label
        self.setFixedSize(round(size), round(size))
        self.setToolTip(name)

    @property
    def label(self) -> str:
        """直接显示的文字。"""
        return self._label

    def set_label(self, label: str) -> None:
        """设置直接显示的文字。"""
        self._label = label
        self.update()

    # ---- 属性 -------------------------------------------------------------

    @property
    def name(self) -> str:
        """姓名。"""
        return self._name

    def set_name(self, name: str) -> None:
        """设置姓名。"""
        self._name = name
        self.setToolTip(name)
        self.update()

    @property
    def image(self) -> QtGui.QPixmap | None:
        """图片。"""
        return self._image

    def set_image(self, image: QtGui.QPixmap | None) -> None:
        """设置图片。"""
        self._image = image
        self.update()

    @property
    def avatar_size(self) -> float:
        """直径。"""
        return self._size

    def set_avatar_size(self, size: float) -> None:
        """设置直径。"""
        self._size = size
        self.setFixedSize(round(size), round(size))
        self.update()

    @property
    def status(self) -> AvatarStatus | str | QtGui.QColor | None:
        """状态。"""
        return self._status

    def set_status(
        self, status: AvatarStatus | str | QtGui.QColor | None
    ) -> None:
        """设置状态圆点。"""
        self._status = status
        self.update()

    @property
    def initials(self) -> str:
        """显示的文字：``label`` 优先，否则为姓名首字母。"""
        return self._label or initials_of(self._name)

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Graphic

    @override
    def accessible_name(self) -> str:
        return self._name or self.toolTip()

    # ---- 绘制 -------------------------------------------------------------

    def shape(self) -> shape_tokens.Shape:
        """容器形状。"""
        return (
            shape_tokens.SHAPE_MEDIUM
            if self._rounded
            else shape_tokens.SHAPE_FULL
        )

    def _status_color(self) -> QtGui.QColor | None:
        status = self._status
        if status is None:
            return None
        if isinstance(status, QtGui.QColor):
            return status
        if isinstance(status, AvatarStatus):
            role = {
                AvatarStatus.ONLINE: ("success", "tertiary"),
                AvatarStatus.AWAY: ("warning", "secondary"),
                AvatarStatus.BUSY: ("error", "error"),
                AvatarStatus.OFFLINE: ("outline", "outline"),
            }[status]
            theme = self.theme
            return theme.color(role[0] if theme.has_color(role[0]) else role[1])
        return self.color(status)

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        path = shape_utils.rounded_rect_path(rect, self.shape())
        if self._image is not None and not self._image.isNull():
            painter.save()
            painter.setClipPath(path)
            scaled = self._image.scaled(
                self.size() * self.devicePixelRatioF(),
                QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
            scaled.setDevicePixelRatio(self.devicePixelRatioF())
            size = scaled.deviceIndependentSize()
            painter.drawPixmap(
                QtCore.QPointF(
                    rect.center().x() - size.width() / 2,
                    rect.center().y() - size.height() / 2,
                ),
                scaled,
            )
            painter.restore()
        elif (self._name or self._label) and not self._icon:
            background, foreground = initials_colors(
                self._name or self._label, self.theme
            )
            shape_utils.fill_shape(painter, path, background)
            style = (
                typography_tokens.TypeRole.TITLE_MEDIUM
                if self._size >= 36
                else typography_tokens.TypeRole.LABEL_MEDIUM
            )
            typography.paint_text(
                painter,
                rect,
                self.initials,
                style,
                foreground,
                QtCore.Qt.AlignmentFlag.AlignCenter,
                elide=False,
            )
        else:
            shape_utils.fill_shape(
                painter, path, self.color("primary_container")
            )
            icon_size = self._size * 0.6
            icon = icons.coerce(self._icon or "person", icon_size)
            if icon is not None:
                icon.paint(
                    painter,
                    QtCore.QRectF(
                        rect.center().x() - icon_size / 2,
                        rect.center().y() - icon_size / 2,
                        icon_size,
                        icon_size,
                    ),
                    self.color("on_primary_container"),
                )
        status_color = self._status_color()
        if status_color is not None:
            diameter = max(8.0, self._size * STATUS_RATIO)
            logical = QtCore.QRectF(
                rect.right() - diameter,
                rect.bottom() - diameter,
                diameter,
                diameter,
            )
            dot = self.visual_rect(logical)
            painter.save()
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(self.color("surface"))
            painter.drawEllipse(
                dot.adjusted(
                    -STATUS_BORDER, -STATUS_BORDER, STATUS_BORDER, STATUS_BORDER
                )
            )
            painter.setBrush(status_color)
            painter.drawEllipse(dot)
            painter.restore()


class AvatarGroup(QtWidgets.QWidget):
    """重叠排列的头像组。

    Args:
        avatars: 头像列表（也可以直接给姓名）。
        max_visible: 最多显示的头像数，其余合并为 "+N"。
        size: 头像直径。
        parent: 父控件。
    """

    def __init__(
        self,
        avatars: list[Avatar | str] | None = None,
        max_visible: int = 4,
        size: float = 32.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._size = size
        self._max_visible = max(1, max_visible)
        self._avatars: list[Avatar] = []
        self._overflow: Avatar | None = None
        for avatar in avatars or ():
            self.add(avatar)
        self._relayout()

    @property
    def avatars(self) -> list[Avatar]:
        """全部头像（含未显示的）。"""
        return list(self._avatars)

    def add(self, avatar: Avatar | str) -> Avatar:
        """追加头像。"""
        if isinstance(avatar, str):
            avatar = Avatar(avatar, size=self._size)
        avatar.setParent(self)
        avatar.set_avatar_size(self._size)
        self._avatars.append(avatar)
        self._relayout()
        return avatar

    def clear(self) -> None:
        """移除全部头像。"""
        for avatar in self._avatars:
            avatar.setParent(None)
            avatar.deleteLater()
        self._avatars.clear()
        self._relayout()

    @property
    def overflow_count(self) -> int:
        """未单独显示、合并进 "+N" 的头像数。"""
        if len(self._avatars) <= self._max_visible:
            return 0
        return len(self._avatars) - (self._max_visible - 1)

    def _visible_avatars(self) -> list[Avatar]:
        if self.overflow_count:
            return self._avatars[: self._max_visible - 1]
        return list(self._avatars)

    def _relayout(self) -> None:
        step = self._size * (1.0 - OVERLAP_RATIO)
        visible = self._visible_avatars()
        for avatar in self._avatars:
            avatar.setVisible(avatar in visible)
        count = len(visible) + (1 if self.overflow_count else 0)
        total = self._size + max(0, count - 1) * step if count else 0.0
        rtl = self.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft
        for index, avatar in enumerate(visible):
            x = index * step
            if rtl:
                x = total - x - self._size
            avatar.move(round(x), 0)
            avatar.raise_()
        if self.overflow_count:
            if self._overflow is None:
                self._overflow = Avatar(
                    "overflow", size=self._size, parent=self
                )
            self._overflow.set_label(f"+{self.overflow_count}")
            x = len(visible) * step
            if rtl:
                x = total - x - self._size
            self._overflow.move(round(x), 0)
            self._overflow.show()
            self._overflow.raise_()
        elif self._overflow is not None:
            self._overflow.hide()
        self.setFixedSize(round(total), round(self._size))

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.LayoutDirectionChange:
            self._relayout()
