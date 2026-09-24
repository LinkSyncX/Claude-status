"""排版绘制与测量工具，以及跟随主题的 ``Label`` 控件。"""

from __future__ import annotations

import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.theme import fonts
from md3.theme import theme as theme_module
from md3.tokens import typography as typography_tokens

TypeRole = typography_tokens.TypeRole
TypeStyle = typography_tokens.TypeStyle

_ELIDE_MODE = QtCore.Qt.TextElideMode.ElideRight


def resolve_style(role: TypeRole | TypeStyle | str) -> TypeStyle:
    """接受角色、令牌名或样式对象，统一返回 ``TypeStyle``。"""
    if isinstance(role, TypeStyle):
        return role
    return theme_module.current().style(role)


def font_for(role: TypeRole | TypeStyle | str) -> QtGui.QFont:
    """按当前主题构造排版字体。"""
    return fonts.font_for(
        resolve_style(role), theme_module.current().font_family
    )


def text_width(text: str, role: TypeRole | TypeStyle | str) -> float:
    """单行文本宽度（含字距）。"""
    metrics = QtGui.QFontMetricsF(font_for(role))
    return metrics.horizontalAdvance(text)


def size_hint(width: float, height: float) -> QtCore.QSize:
    """把浮点尺寸向上取整为 ``QSize``，避免内容被亚像素截断。"""
    return QtCore.QSize(math.ceil(width - 1e-6), math.ceil(height - 1e-6))


def text_size(
    text: str,
    role: TypeRole | TypeStyle | str,
    max_width: float | None = None,
) -> QtCore.QSizeF:
    """文本尺寸；给定最大宽度时按 M3 行高计算多行高度。"""
    style = resolve_style(role)
    font = font_for(style)
    metrics = QtGui.QFontMetricsF(font)
    if max_width is None or not text:
        width = metrics.horizontalAdvance(text) if text else 0.0
        lines = max(1, text.count("\n") + 1)
        return QtCore.QSizeF(width, style.line_height * lines)
    layout = build_layout(text, style, max_width)
    lines = max(1, layout.lineCount())
    return QtCore.QSizeF(
        min(max_width, layout.boundingRect().width()),
        style.line_height * lines,
    )


def build_layout(
    text: str,
    style: TypeStyle,
    width: float,
    alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft,
) -> QtGui.QTextLayout:
    """构造已完成换行的 ``QTextLayout``，行距按 M3 行高。

    ``alignment`` 只取水平分量，且按绝对方向解释（AlignRight 即靠右）。
    """
    font = font_for(style)
    layout = QtGui.QTextLayout(text, font)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
    option.setAlignment(
        (alignment & QtCore.Qt.AlignmentFlag.AlignHorizontal_Mask)
        | QtCore.Qt.AlignmentFlag.AlignAbsolute
    )
    layout.setTextOption(option)
    layout.beginLayout()
    y = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1.0, width))
        line.setPosition(QtCore.QPointF(0, y))
        y += style.line_height
    layout.endLayout()
    return layout


def paint_text(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    text: str,
    role: TypeRole | TypeStyle | str,
    color: QtGui.QColor,
    alignment: QtCore.Qt.AlignmentFlag = (
        QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter
    ),
    elide: bool = True,
) -> None:
    """绘制单行文本，超出宽度时按需省略。

    水平对齐按绝对方向解释：``AlignLeft`` 总是靠矩形左边，与文字本身的
    书写方向无关；需要跟随布局方向时由调用方通过
    ``MaterialWidget.visual_alignment`` 翻转。
    """
    if not text:
        return
    font = font_for(role)
    painter.save()
    painter.setFont(font)
    painter.setPen(color)
    if elide:
        metrics = QtGui.QFontMetricsF(font)
        # 容忍亚像素误差，避免因布局取整而误省略最后一个字符。
        if metrics.horizontalAdvance(text) > rect.width() + 0.5:
            text = metrics.elidedText(text, _ELIDE_MODE, rect.width())
    painter.drawText(
        rect, int(alignment | QtCore.Qt.AlignmentFlag.AlignAbsolute), text
    )
    painter.restore()


def paint_multiline(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    text: str,
    role: TypeRole | TypeStyle | str,
    color: QtGui.QColor,
    max_lines: int | None = None,
    alignment: QtCore.Qt.AlignmentFlag = QtCore.Qt.AlignmentFlag.AlignLeft,
) -> float:
    """按 M3 行高绘制多行文本，返回实际占用高度。"""
    if not text:
        return 0.0
    style = resolve_style(role)
    layout = build_layout(text, style, rect.width(), alignment)
    metrics = QtGui.QFontMetricsF(layout.font())
    ascent_offset = (style.line_height - metrics.height()) / 2
    painter.save()
    painter.setPen(color)
    painter.setFont(layout.font())
    count = layout.lineCount()
    if max_lines is not None:
        count = min(count, max_lines)
    # QTextLine.draw 会自行加上该行在布局中的位置，因此这里只给布局原点。
    origin = QtCore.QPointF(rect.left(), rect.top() + ascent_offset)
    for index in range(count):
        line = layout.lineAt(index)
        if (
            max_lines is not None
            and index == max_lines - 1
            and (layout.lineCount() > max_lines)
        ):
            start = line.textStart()
            fragment = text[start : start + line.textLength()]
            elided = metrics.elidedText(
                fragment + "…", _ELIDE_MODE, rect.width()
            )
            painter.drawText(
                QtCore.QRectF(
                    origin.x(),
                    origin.y() + line.position().y(),
                    rect.width(),
                    metrics.height(),
                ),
                int(
                    (alignment & QtCore.Qt.AlignmentFlag.AlignHorizontal_Mask)
                    | QtCore.Qt.AlignmentFlag.AlignAbsolute
                ),
                elided,
            )
        else:
            line.draw(painter, origin)
    painter.restore()
    return count * style.line_height


class Label(QtWidgets.QLabel):
    """使用 M3 排版角色与色彩角色的文本标签，主题切换时自动更新。"""

    def __init__(
        self,
        text: str = "",
        role: TypeRole | str = TypeRole.BODY_MEDIUM,
        color_role: str = "on_surface",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self._role = TypeRole(role) if isinstance(role, str) else role
        self._color_role = color_role
        self._logical_alignment = (
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._apply_theme(theme_module.current())
        self._sync_alignment()
        theme_module.manager().theme_changed.connect(self._apply_theme)

    def setAlignment(self, alignment: QtCore.Qt.AlignmentFlag) -> None:
        """记录逻辑对齐（Left = 起始侧），并按当前布局方向应用。"""
        self._logical_alignment = QtCore.Qt.AlignmentFlag(alignment)
        self._sync_alignment()

    def _sync_alignment(self) -> None:
        # 启用文本选择后 QLabel 按文字方向而非布局方向对齐，这里显式换算成
        # 绝对对齐：RTL 下 AlignLeft 表示靠右。
        alignment = self._logical_alignment
        if alignment & QtCore.Qt.AlignmentFlag.AlignAbsolute:
            super().setAlignment(alignment)
            return
        rtl = self.layoutDirection() == QtCore.Qt.LayoutDirection.RightToLeft
        left = QtCore.Qt.AlignmentFlag.AlignLeft
        right = QtCore.Qt.AlignmentFlag.AlignRight
        if rtl and alignment & left:
            alignment = (alignment & ~left) | right
        elif rtl and alignment & right:
            alignment = (alignment & ~right) | left
        super().setAlignment(alignment | QtCore.Qt.AlignmentFlag.AlignAbsolute)

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.LayoutDirectionChange:
            self._sync_alignment()

    def set_role(self, role: TypeRole | str) -> None:
        """更换排版角色。"""
        self._role = TypeRole(role) if isinstance(role, str) else role
        self._apply_theme(theme_module.current())

    def set_color_role(self, color_role: str) -> None:
        """更换文字色彩角色。"""
        self._color_role = color_role
        self._apply_theme(theme_module.current())

    def _apply_theme(self, theme: theme_module.Theme) -> None:
        self.setFont(theme.font(self._role))
        palette = self.palette()
        color = theme.color(self._color_role)
        palette.setColor(QtGui.QPalette.ColorRole.WindowText, color)
        palette.setColor(QtGui.QPalette.ColorRole.Text, color)
        self.setPalette(palette)
