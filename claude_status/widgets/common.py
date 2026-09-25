"""页面骨架与通用小控件：分区卡片、状态标签、图标徽章与响应式网格。"""

from __future__ import annotations

from collections.abc import Sequence
import math
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets
import shiboken6

from md3.components import cards
from md3.components import feedback
from md3.components import sheets
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing

PAGE_MARGIN = round(spacing.SPACE_6)
PAGE_SPACING = round(spacing.SPACE_4)


class Page(QtWidgets.QWidget):
    """可滚动页面的内容区：统一的边距与纵向间距。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(
            PAGE_MARGIN, round(spacing.SPACE_2), PAGE_MARGIN, PAGE_MARGIN
        )
        self._layout.setSpacing(PAGE_SPACING)

    @property
    def body(self) -> QtWidgets.QVBoxLayout:
        """页面主布局。"""
        return self._layout


def wrap_scroll(page: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    """把页面放进无边框、背景透明的滚动区域。"""
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(
        QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    )
    scroll.viewport().setAutoFillBackground(False)
    page.setAutoFillBackground(False)
    scroll.setWidget(page)
    return scroll


def label(
    text: str = "",
    role: str = "body-medium",
    color_role: str = "on_surface",
    selectable: bool = False,
    wrap: bool = False,
) -> typography.Label:
    """创建主题标签；默认不可选中文字，使点击能传递给可点击的父控件。"""
    result = typography.Label(text, role, color_role)
    if not selectable:
        result.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.NoTextInteraction
        )
    result.setWordWrap(wrap)
    return result


class ElidedLabel(typography.Label):
    """单行标签：宽度不足时以省略号截断，完整文字显示在提示中。

    首选宽度仍是完整文字的宽度，但最小宽度很小，因此不会撑宽所在的
    卡片或网格列；不可选中文字，点击会传递给父控件。
    """

    MIN_WIDTH = 24

    def __init__(
        self,
        text: str = "",
        role: str = "body-medium",
        color_role: str = "on_surface",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__("", role, color_role, parent)
        self._full_text = ""
        self.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.NoTextInteraction
        )
        self.setText(text)

    @override
    def setText(self, text: str) -> None:
        self._full_text = text
        self._elide()
        self.updateGeometry()

    def full_text(self) -> str:
        """未截断的完整文字。"""
        return self._full_text

    def _elide(self) -> None:
        full = getattr(self, "_full_text", "")
        metrics = QtGui.QFontMetrics(self.font())
        width = max(0, self.contentsRect().width())
        elided = metrics.elidedText(
            full, QtCore.Qt.TextElideMode.ElideRight, width
        )
        QtWidgets.QLabel.setText(self, elided)
        self.setToolTip(full if elided != full else "")

    @override
    def sizeHint(self) -> QtCore.QSize:
        metrics = QtGui.QFontMetrics(self.font())
        margins = self.contentsMargins()
        width = (
            metrics.horizontalAdvance(getattr(self, "_full_text", ""))
            + margins.left()
            + margins.right()
            + 2
        )
        return QtCore.QSize(width, super().sizeHint().height())

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(
            self.MIN_WIDTH, super().minimumSizeHint().height()
        )

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._elide()

    @override
    def changeEvent(self, event: QtCore.QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QtCore.QEvent.Type.FontChange:
            self._elide()


# md3 的按钮、开关、分段按钮与筛选标签四周留有透明外边距（触控目标与焦点环）。
CONTROL_INSET = round(widget.DEFAULT_OUTER_MARGIN)


class FlushRow(QtWidgets.QHBoxLayout):
    """首个控件的可见边缘与文字、输入框左对齐的横排布局。

    md3 控件四周有透明外边距，直接放进布局时会比同一列的文字与输入框向右
    缩进 ``CONTROL_INSET``。这里把整行向左移动同样的距离：落在卡片的内边距
    里，焦点环不会被裁切。（Qt 布局不接受负边距，因此改写 ``setGeometry``。）
    """

    @override
    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect.adjusted(-CONTROL_INSET, 0, 0, 0))


def row(
    *widgets: QtWidgets.QWidget | int | None,
    spacing_px: int = round(spacing.SPACE_2),
    margins: tuple[int, int, int, int] = (0, 0, 0, 0),
    flush: bool = False,
) -> QtWidgets.QHBoxLayout:
    """横向排列控件；整数表示弹性空间的伸展系数，None 表示弹性空间。

    ``flush`` 为真时首个 md3 控件的可见边缘与左侧的文字对齐（见 ``FlushRow``）。
    """
    layout = FlushRow() if flush else QtWidgets.QHBoxLayout()
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing_px)
    for item in widgets:
        if item is None:
            layout.addStretch(1)
        elif isinstance(item, int):
            layout.addStretch(item)
        else:
            layout.addWidget(item)
    return layout


class SectionCard(cards.Card):
    """带标题栏的内容卡片：标题、说明与右侧的操作区。

    Args:
        title: 标题。
        subtitle: 标题下方的说明文字。
        variant: 卡片变体，默认描边卡片。
        parent: 父控件。
        icon: 标题左侧的图标徽章（可选）。
        icon_role: 图标徽章的颜色角色前缀。
    """

    ICON_SIZE = 40.0

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        variant: cards.CardVariant = cards.CardVariant.OUTLINED,
        parent: QtWidgets.QWidget | None = None,
        *,
        icon: icons.IconLike = None,
        icon_role: str = "primary",
    ) -> None:
        super().__init__(variant, parent=parent)
        self.set_content_margins(
            spacing.Insets.symmetric(spacing.SPACE_5, spacing.SPACE_4)
        )
        self.content_layout.setSpacing(round(spacing.SPACE_3))
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(round(spacing.SPACE_3))
        self.icon_badge: IconBadge | None = None
        if icon is not None:
            self.icon_badge = IconBadge(icon, icon_role, self.ICON_SIZE)
            header.addWidget(
                self.icon_badge, 0, QtCore.Qt.AlignmentFlag.AlignTop
            )
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(2)
        self.title_label = typography.Label(title, "title-medium", "on_surface")
        titles.addWidget(self.title_label)
        self.subtitle_label = typography.Label(
            subtitle, "body-small", "on_surface_variant"
        )
        self.subtitle_label.setWordWrap(True)
        titles.addWidget(self.subtitle_label)
        header.addLayout(titles, 1)
        self._actions = QtWidgets.QHBoxLayout()
        self._actions.setSpacing(round(spacing.SPACE_2))
        header.addLayout(self._actions)
        # 先把标题栏挂到卡片上，再设置可见性：没有父控件的控件调用
        # setVisible(True) 会显示成独立的顶层窗口（启动时一闪而过）。
        # 没有标题的卡片，标题栏里只有隐藏的控件，不占空间。
        self.content_layout.addLayout(header)
        self.title_label.setVisible(bool(title))
        self.subtitle_label.setVisible(bool(subtitle))
        self._header = header

    def add_header_widget(self, child: QtWidgets.QWidget) -> None:
        """在标题栏右侧追加控件（分段按钮、图标按钮等）。"""
        self._actions.addWidget(child, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)

    def set_subtitle(self, text: str) -> None:
        """更新说明文字。"""
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class Pill(widget.MaterialWidget):
    """小号的彩色标签（状态、套餐等），不可交互。

    Args:
        text: 文字。
        role: 颜色角色前缀：``success`` 使用 ``success_container`` /
            ``on_success_container``；``surface`` 使用
            ``surface_container_highest`` / ``on_surface_variant``；
            ``primary_solid`` 使用 ``primary`` / ``on_primary``。
        icon: 可选前置图标。
        parent: 父控件。
    """

    HEIGHT = 24.0
    ICON_SIZE = 16.0
    STYLE = typography.TypeRole.LABEL_MEDIUM

    def __init__(
        self,
        text: str,
        role: str = "secondary",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = text
        self._role = role
        self._icon = icons.coerce(icon, self.ICON_SIZE)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Fixed,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_text(self, text: str) -> None:
        """更换文字。"""
        self._text = text
        self.updateGeometry()
        self.update()

    def set_role(self, role: str, icon: icons.IconLike = None) -> None:
        """更换颜色角色与图标。"""
        self._role = role
        self._icon = icons.coerce(icon, self.ICON_SIZE)
        self.updateGeometry()
        self.update()

    def _colors(self) -> tuple[QtGui.QColor, QtGui.QColor]:
        role = self._role
        if role == "surface":
            return (
                self.color("surface_container_highest"),
                self.color("on_surface_variant"),
            )
        if role.endswith("_solid"):
            base = role.removesuffix("_solid")
            return self.color(base), self.color(f"on_{base}")
        if not self.theme.has_color(f"{role}_container"):
            role = "secondary"
        return self.color(f"{role}_container"), self.color(
            f"on_{role}_container"
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        width = typography.text_width(self._text, self.STYLE) + 20
        if self._icon is not None:
            width += self.ICON_SIZE + 4
        return typography.size_hint(width, self.HEIGHT)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        container, content = self._colors()
        rect = QtCore.QRectF(self.rect())
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_SMALL),
            container,
        )
        left = rect.left() + 10
        if self._icon is not None:
            self._icon.paint(
                painter,
                QtCore.QRectF(
                    left - 2,
                    rect.center().y() - self.ICON_SIZE / 2,
                    self.ICON_SIZE,
                    self.ICON_SIZE,
                ),
                content,
            )
            left += self.ICON_SIZE + 2
        typography.paint_text(
            painter,
            QtCore.QRectF(
                left, rect.top(), rect.right() - left - 8, rect.height()
            ),
            self._text,
            self.STYLE,
            content,
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter,
        )


class IconBadge(widget.MaterialWidget):
    """圆形色块中的图标，用于统计卡片与列表前导。

    Args:
        icon: 图标。
        role: 颜色角色前缀（``primary`` → ``primary_container``）。
        size: 直径。
        parent: 父控件。
    """

    def __init__(
        self,
        icon: icons.IconLike,
        role: str = "primary",
        size: float = 40.0,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon = icons.coerce(icon, round(size * 0.55))
        self._role = role
        self._size = size
        self.setFixedSize(round(size), round(size))

    def set_icon(self, icon: icons.IconLike, role: str | None = None) -> None:
        """更换图标与颜色。"""
        self._icon = icons.coerce(icon, round(self._size * 0.55))
        if role is not None:
            self._role = role
        self.update()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        role = self._role
        if not self.theme.has_color(f"{role}_container"):
            role = "primary"
        rect = QtCore.QRectF(self.rect())
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(self.color(f"{role}_container"))
        painter.drawEllipse(rect)
        if self._icon is not None:
            self._icon.paint(painter, rect, self.color(f"on_{role}_container"))


class ResponsiveGrid(QtWidgets.QWidget):
    """按可用宽度自动决定列数的网格（每列至少 ``min_column_width``）。

    Args:
        min_column_width: 单列最小宽度（px）。
        max_columns: 最多列数。
        spacing_px: 行列间距。
        balanced: 为真时列数不超过条目数且能整除条目数，使每行数量相同；
            为假时条目少于列数也保持列宽（例如只有一张卡片时占一列）。
        parent: 父控件。
    """

    def __init__(
        self,
        min_column_width: int = 320,
        max_columns: int = 4,
        spacing_px: int = PAGE_SPACING,
        balanced: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._min_width = min_column_width
        self._max_columns = max_columns
        self._balanced = balanced
        self._items: list[QtWidgets.QWidget] = []
        self._columns = 0
        self._grid = QtWidgets.QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(spacing_px)
        self._grid.setVerticalSpacing(spacing_px)

    def set_widgets(self, items: Sequence[QtWidgets.QWidget]) -> None:
        """替换全部子控件（旧控件会被删除）。"""
        for item in self._items:
            if item not in items:
                self._grid.removeWidget(item)
                item.deleteLater()
        self._items = list(items)
        self._columns = 0
        self._relayout()

    @property
    def widgets(self) -> list[QtWidgets.QWidget]:
        """当前子控件。"""
        return list(self._items)

    def _column_count(self) -> int:
        width = max(1, self.width())
        spacing_px = self._grid.horizontalSpacing()
        fit = (width + spacing_px) // (self._min_width + spacing_px)
        columns = max(1, min(self._max_columns, fit))
        if self._balanced:
            # 每行数量相同（6 个放不下一行时排成 3 + 3，而不是 5 + 1）。
            count = max(1, len(self._items))
            columns = min(columns, count)
            while columns > 1 and count % columns:
                columns -= 1
        return columns

    def _relayout(self) -> None:
        columns = self._column_count()
        if columns == self._columns and all(
            self._grid.indexOf(item) >= 0 for item in self._items
        ):
            return
        self._columns = columns
        for item in self._items:
            self._grid.removeWidget(item)
        for column in range(self._grid.columnCount()):
            self._grid.setColumnStretch(column, 0)
        for index, item in enumerate(self._items):
            self._grid.addWidget(item, index // columns, index % columns)
            item.show()
        for column in range(columns):
            self._grid.setColumnStretch(column, 1)

    @override
    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()


class DetailSheet(sheets.SideSheet):
    """可复用的模态侧边面板，并修正 md3 浮层的动画引用问题。

    md3 的 ``FloatingPanel`` 以 ``DeleteWhenStopped`` 启动几何动画却保留
    Python 引用：打开动画结束后 C++ 对象已删除，再次关闭面板或宿主窗口
    改变尺寸时会访问已删除的对象而抛出 ``RuntimeError``。这里在使用前
    丢弃失效的引用。
    """

    def __init__(self, host: QtWidgets.QWidget, title: str = "") -> None:
        super().__init__(host, title, modal=True, width=400)

    def _drop_dead_animation(self) -> None:
        animation = self._geometry_animation
        if animation is not None and not shiboken6.isValid(animation):
            self._geometry_animation = None

    def _animate_to(self, *args, **kwargs) -> None:  # noqa: D102
        self._drop_dead_animation()
        super()._animate_to(*args, **kwargs)

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        self._drop_dead_animation()
        return super().eventFilter(watched, event)

    def replace_content(self, content: QtWidgets.QWidget) -> None:
        """替换内容区的全部控件。"""
        clear_layout(self.content_layout)
        self.set_content(content)


class InfoBanner(feedback.Banner):
    """文字列可伸展的横幅。

    md3 的 ``Banner`` 在操作按钮与文字同行时没有给文字列设置伸展系数，
    内含弹性空间的按钮区会把文字挤成很窄的一列；这里让文字列独占剩余
    宽度。
    """

    def __init__(
        self,
        text: str,
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(text, icon=icon, parent=parent)
        self._grid.setColumnStretch(1, 1)


def empty_state(
    headline: str, supporting_text: str, icon: icons.IconLike
) -> feedback.EmptyState:
    """空状态。

    md3 的 ``EmptyState`` 在说明文字加入布局之前就让它可见，这时它还没有
    父控件，会显示成一闪而过的独立窗口；构造完成后再设置说明文字则不会。
    """
    state = feedback.EmptyState(headline, icon=icon)
    state.set_supporting_text(supporting_text)
    return state


def indented(child: QtWidgets.QWidget, left: int) -> QtWidgets.QWidget:
    """左侧缩进的容器。

    换行的标签若用自身的内容边距缩进，换行宽度不含边距，右侧会被裁切；
    放进带边距的布局则不会。
    """
    holder = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(holder)
    layout.setContentsMargins(left, 0, 0, 0)
    layout.addWidget(child)
    return holder


def fit_wrapped(label: QtWidgets.QLabel, width: int) -> None:
    """给换行标签固定宽度，并按实际排版设置高度。

    QLabel 按主字体（Roboto）的行距估算高度，而中文由回退字体绘制、行高
    更大；在按提示尺寸布局的对话框里，最后一行会因此被裁掉一截。
    """
    label.setFixedWidth(width)
    option = QtGui.QTextOption()
    option.setWrapMode(QtGui.QTextOption.WrapMode.WordWrap)
    layout = QtGui.QTextLayout(label.text(), label.font())
    layout.setTextOption(option)
    layout.beginLayout()
    height = 0.0
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        line.setPosition(QtCore.QPointF(0, height))
        height += line.height()
    layout.endLayout()
    label.setMinimumHeight(max(label.heightForWidth(width), math.ceil(height)))


def clear_layout(layout: QtWidgets.QLayout) -> None:
    """删除布局中的全部控件与子布局。"""
    while layout.count():
        item = layout.takeAt(0)
        child = item.widget()
        if child is not None:
            child.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())
