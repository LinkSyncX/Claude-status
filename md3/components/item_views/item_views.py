"""Material 风格的表格 / 树 / 列表视图。

原生 ``QTableView`` ``QTreeView`` ``QListView`` 只靠样式表无法得到 M3 的
数据表外观，这里用委托与表头把它们画成 M3 样子：52dp 行高、1dp
``outline_variant`` 分隔线、悬停 8% 状态层、选中行 ``secondary_container``、
表头 label-large 与 Material Symbols 排序箭头、勾选列使用 M3 复选框。

``apply_material_style(view)`` 可套用到任何现有视图；``MaterialTableView``
等子类在构造时已套用，并把树的展开箭头也换成 Material 图标。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components.selection import checkbox as checkbox_module
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

ROW_HEIGHT = 52
DENSE_ROW_HEIGHT = 40
HEADER_HEIGHT = 56
DENSE_HEADER_HEIGHT = 44
CELL_PADDING = 16.0
ICON_SIZE = 24.0
ICON_GAP = 12.0
SORT_ICON_SIZE = 18.0
DIVIDER_WIDTH = 1.0
CELL_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
HEADER_STYLE = typography_tokens.TypeRole.LABEL_LARGE
BRANCH_ICON_SIZE = 20.0


def paint_checkbox(
    painter: QtGui.QPainter,
    rect: QtCore.QRectF,
    state: QtCore.Qt.CheckState,
    theme: theme_module.Theme,
    enabled: bool = True,
) -> None:
    """按 M3 复选框样式绘制一个静态的勾选框。"""
    box = QtCore.QRectF(
        rect.center().x() - checkbox_module.BOX_SIZE / 2,
        rect.center().y() - checkbox_module.BOX_SIZE / 2,
        checkbox_module.BOX_SIZE,
        checkbox_module.BOX_SIZE,
    )
    radius = checkbox_module.BOX_RADIUS
    painter.save()
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    if state == QtCore.Qt.CheckState.Unchecked:
        outline = theme.color("on_surface_variant")
        if not enabled:
            outline = theme_module.with_alpha(
                theme.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        painter.setPen(QtGui.QPen(outline, checkbox_module.OUTLINE_WIDTH))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(box.adjusted(1, 1, -1, -1), radius, radius)
    else:
        fill = theme.color("primary")
        mark = theme.color("on_primary")
        if not enabled:
            fill = theme_module.with_alpha(
                theme.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            mark = theme.color("surface")
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawRoundedRect(box, radius, radius)
        pen = QtGui.QPen(mark, checkbox_module.MARK_WIDTH)
        pen.setCapStyle(QtCore.Qt.PenCapStyle.SquareCap)
        pen.setJoinStyle(QtCore.Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        if state == QtCore.Qt.CheckState.PartiallyChecked:
            y = box.center().y()
            painter.drawLine(
                QtCore.QPointF(box.left() + 4, y),
                QtCore.QPointF(box.right() - 4, y),
            )
        else:
            scale = box.width() / 18.0
            path = QtGui.QPainterPath(
                QtCore.QPointF(
                    box.left() + 4.0 * scale, box.top() + 9.5 * scale
                )
            )
            path.lineTo(box.left() + 7.5 * scale, box.top() + 13.0 * scale)
            path.lineTo(box.left() + 14.5 * scale, box.top() + 5.5 * scale)
            painter.drawPath(path)
    painter.restore()


class MaterialItemDelegate(QtWidgets.QStyledItemDelegate):
    """按 M3 数据表规范绘制单元格的委托。

    Args:
        dense: 为真时行高 40dp（默认 52dp）。
        dividers: 是否绘制行分隔线。
        parent: 父对象。
    """

    def __init__(
        self,
        dense: bool = False,
        dividers: bool = True,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._dense = dense
        self._dividers = dividers

    @property
    def dense(self) -> bool:
        """是否为紧凑密度。"""
        return self._dense

    def row_height(self) -> int:
        """行高（dp）。"""
        return DENSE_ROW_HEIGHT if self._dense else ROW_HEIGHT

    @override
    def sizeHint(
        self, option: QtWidgets.QStyleOptionViewItem, index: QtCore.QModelIndex
    ) -> QtCore.QSize:
        hint = super().sizeHint(option, index)
        return QtCore.QSize(hint.width(), self.row_height())

    @override
    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        theme = theme_module.current()
        rect = QtCore.QRectF(option.rect)
        state = option.state
        selected = bool(state & QtWidgets.QStyle.StateFlag.State_Selected)
        hovered = bool(state & QtWidgets.QStyle.StateFlag.State_MouseOver)
        enabled = bool(state & QtWidgets.QStyle.StateFlag.State_Enabled)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
        # 背景：选中行 secondary-container，悬停叠加 8% 状态层。
        if selected:
            painter.fillRect(rect, theme.color("secondary_container"))
        if hovered and enabled:
            painter.fillRect(
                rect,
                theme_module.with_alpha(
                    theme.color("on_surface"),
                    state_tokens.HOVER_STATE_LAYER_OPACITY,
                ),
            )
        if self._dividers:
            painter.fillRect(
                QtCore.QRectF(
                    rect.left(),
                    rect.bottom() - DIVIDER_WIDTH,
                    rect.width(),
                    DIVIDER_WIDTH,
                ),
                theme.color("outline_variant"),
            )
        content = rect.adjusted(CELL_PADDING, 0, -CELL_PADDING, 0)
        text_color = (
            theme.color("on_secondary_container")
            if selected
            else theme.color("on_surface")
        )
        if not enabled:
            text_color = theme_module.with_alpha(
                theme.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        left = content.left()
        check = index.data(QtCore.Qt.ItemDataRole.CheckStateRole)
        if check is not None:
            box = QtCore.QRectF(
                left, rect.top(), checkbox_module.BOX_SIZE, rect.height()
            )
            paint_checkbox(
                painter, box, QtCore.Qt.CheckState(check), theme, enabled
            )
            left += checkbox_module.BOX_SIZE + ICON_GAP
        decoration = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
        icon = self._coerce_icon(decoration)
        if icon is not None:
            icon_rect = QtCore.QRectF(
                left, rect.center().y() - ICON_SIZE / 2, ICON_SIZE, ICON_SIZE
            )
            if isinstance(icon, QtGui.QIcon):
                icon.paint(painter, icon_rect.toRect())
            else:
                icon.paint(
                    painter,
                    icon_rect,
                    text_color
                    if selected
                    else theme.color("on_surface_variant"),
                )
            left += ICON_SIZE + ICON_GAP
        text = index.data(QtCore.Qt.ItemDataRole.DisplayRole)
        if text is not None and str(text):
            alignment = index.data(QtCore.Qt.ItemDataRole.TextAlignmentRole)
            flags = (
                QtCore.Qt.AlignmentFlag(int(alignment))
                if alignment is not None
                else QtCore.Qt.AlignmentFlag.AlignLeft
                | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            if not flags & QtCore.Qt.AlignmentFlag.AlignVertical_Mask:
                flags |= QtCore.Qt.AlignmentFlag.AlignVCenter
            typography.paint_text(
                painter,
                QtCore.QRectF(
                    left,
                    rect.top(),
                    max(0.0, content.right() - left),
                    rect.height(),
                ),
                str(text),
                CELL_STYLE,
                text_color,
                flags,
            )
        painter.restore()

    @staticmethod
    def _coerce_icon(decoration: object) -> QtGui.QIcon | icons.AnyIcon | None:
        if decoration is None:
            return None
        if isinstance(decoration, QtGui.QIcon):
            return decoration if not decoration.isNull() else None
        if isinstance(decoration, QtGui.QPixmap):
            return QtGui.QIcon(decoration)
        if isinstance(decoration, str | icons.Icon | icons.SvgIcon):
            return icons.coerce(decoration, ICON_SIZE)
        return None

    @override
    def createEditor(
        self,
        parent: QtWidgets.QWidget,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtWidgets.QWidget:
        editor = super().createEditor(parent, option, index)
        theme = theme_module.current()
        editor.setFont(theme.font(CELL_STYLE))
        editor.setStyleSheet(
            f"padding-left: {int(CELL_PADDING) - 4}px;"
            f"border: 2px solid {theme.color('primary').name()};"
            f"background: {theme.color('surface_container_highest').name()};"
            f"color: {theme.color('on_surface').name()};"
        )
        return editor


class MaterialHeaderView(QtWidgets.QHeaderView):
    """M3 数据表表头：label-large 文字、底部分隔线与 Material 排序箭头。"""

    def __init__(
        self,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        dense: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(orientation, parent)
        self._dense = dense
        self.setHighlightSections(False)
        self.setDefaultAlignment(
            QtCore.Qt.AlignmentFlag.AlignLeft
            | QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.setSectionsClickable(True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
        self.setMouseTracking(True)
        self._hovered = -1
        self.setStretchLastSection(True)
        # 绑定方法作为槽：表头销毁时 Qt 会自动断开连接。
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.viewport().update()

    def header_height(self) -> int:
        """表头高度（dp）。"""
        return DENSE_HEADER_HEIGHT if self._dense else HEADER_HEIGHT

    @override
    def sizeHint(self) -> QtCore.QSize:
        hint = super().sizeHint()
        if self.orientation() == QtCore.Qt.Orientation.Horizontal:
            return QtCore.QSize(hint.width(), self.header_height())
        return hint

    @override
    def paintSection(
        self, painter: QtGui.QPainter, rect: QtCore.QRect, logical_index: int
    ) -> None:
        theme = theme_module.current()
        area = QtCore.QRectF(rect)
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(area, theme.color("surface"))
        if logical_index == self._hovered and self.sectionsClickable():
            painter.fillRect(
                area,
                theme_module.with_alpha(
                    theme.color("on_surface"),
                    state_tokens.HOVER_STATE_LAYER_OPACITY,
                ),
            )
        painter.fillRect(
            QtCore.QRectF(
                area.left(),
                area.bottom() - DIVIDER_WIDTH,
                area.width(),
                DIVIDER_WIDTH,
            ),
            theme.color("outline_variant"),
        )
        model = self.model()
        text = ""
        alignment = self.defaultAlignment()
        if model is not None:
            value = model.headerData(
                logical_index,
                self.orientation(),
                QtCore.Qt.ItemDataRole.DisplayRole,
            )
            text = "" if value is None else str(value)
            # 模型给出的对齐（如数值列右对齐）优先于表头默认对齐。
            align_value = model.headerData(
                logical_index,
                self.orientation(),
                QtCore.Qt.ItemDataRole.TextAlignmentRole,
            )
            if align_value is not None:
                alignment = QtCore.Qt.AlignmentFlag(int(align_value))
        if not alignment & QtCore.Qt.AlignmentFlag.AlignVertical_Mask:
            alignment |= QtCore.Qt.AlignmentFlag.AlignVCenter
        alignment = QtWidgets.QStyle.visualAlignment(
            self.layoutDirection(), alignment
        )
        content = area.adjusted(CELL_PADDING, 0, -CELL_PADDING, 0)
        sorted_here = (
            self.isSortIndicatorShown()
            and self.sortIndicatorSection() == logical_index
        )
        color = theme.color(
            "on_surface" if sorted_here else "on_surface_variant"
        )
        if sorted_here:
            self._paint_sort_arrow(painter, content, text, alignment, color)
        typography.paint_text(
            painter, content, text, HEADER_STYLE, color, alignment
        )
        painter.restore()

    def _paint_sort_arrow(
        self,
        painter: QtGui.QPainter,
        content: QtCore.QRectF,
        text: str,
        alignment: QtCore.Qt.AlignmentFlag,
        color: QtGui.QColor,
    ) -> None:
        """在表头文字旁绘制排序箭头，并从 ``content`` 中扣掉箭头占用的宽度。

        右对齐（数值）列的箭头画在文字左侧，其余列画在文字右侧。
        """
        ascending = (
            self.sortIndicatorOrder() == QtCore.Qt.SortOrder.AscendingOrder
        )
        arrow = icons.coerce(
            "arrow_upward" if ascending else "arrow_downward", SORT_ICON_SIZE
        )
        text_width = typography.text_width(text, HEADER_STYLE)
        right_aligned = bool(alignment & QtCore.Qt.AlignmentFlag.AlignRight)
        if right_aligned:
            x = max(
                content.right() - text_width - 4 - SORT_ICON_SIZE,
                content.left(),
            )
            content.setLeft(content.left() + SORT_ICON_SIZE + 4)
        else:
            x = min(
                content.left() + text_width + 4,
                content.right() - SORT_ICON_SIZE,
            )
            content.setRight(content.right() - SORT_ICON_SIZE - 4)
        if arrow is not None:
            arrow.paint(
                painter,
                QtCore.QRectF(
                    x,
                    content.center().y() - SORT_ICON_SIZE / 2,
                    SORT_ICON_SIZE,
                    SORT_ICON_SIZE,
                ),
                color,
            )

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hovered = self.logicalIndexAt(event.position().toPoint())
        if hovered != self._hovered:
            self._hovered = hovered
            self.viewport().update()
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = -1
        self.viewport().update()
        super().leaveEvent(event)


def apply_material_style(
    view: QtWidgets.QAbstractItemView,
    dense: bool = False,
    dividers: bool = True,
) -> MaterialItemDelegate:
    """把 M3 委托、表头与视口配色套用到任意项视图，返回创建的委托。"""
    delegate = MaterialItemDelegate(dense, dividers, view)
    view.setItemDelegate(delegate)
    view.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    view.setMouseTracking(True)
    view.viewport().setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)
    view.setAlternatingRowColors(False)
    view.setSelectionBehavior(
        QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
    )
    view.setVerticalScrollMode(
        QtWidgets.QAbstractItemView.ScrollMode.ScrollPerPixel
    )
    if isinstance(view, QtWidgets.QTableView):
        view.setShowGrid(False)
        view.setHorizontalHeader(
            MaterialHeaderView(QtCore.Qt.Orientation.Horizontal, dense, view)
        )
        view.verticalHeader().hide()
        view.verticalHeader().setDefaultSectionSize(delegate.row_height())
    elif isinstance(view, QtWidgets.QTreeView):
        view.setHeader(
            MaterialHeaderView(QtCore.Qt.Orientation.Horizontal, dense, view)
        )
        view.setIndentation(28)
        view.setUniformRowHeights(True)
        view.setExpandsOnDoubleClick(True)
    _apply_palette(view)
    if (
        view.findChild(
            _PaletteSync, "", QtCore.Qt.FindChildOption.FindDirectChildrenOnly
        )
        is None
    ):
        _PaletteSync(view)
    return delegate


class _PaletteSync(QtCore.QObject):
    """随视图一起销毁的主题监听器，避免悬空的 lambda 槽。"""

    def __init__(self, view: QtWidgets.QAbstractItemView) -> None:
        super().__init__(view)
        self._view = view
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        _apply_palette(self._view)


def _apply_palette(view: QtWidgets.QAbstractItemView) -> None:
    theme = theme_module.current()
    palette = view.palette()
    palette.setColor(QtGui.QPalette.ColorRole.Base, theme.color("surface"))
    palette.setColor(QtGui.QPalette.ColorRole.Window, theme.color("surface"))
    palette.setColor(QtGui.QPalette.ColorRole.Text, theme.color("on_surface"))
    palette.setColor(
        QtGui.QPalette.ColorRole.Highlight, theme.color("secondary_container")
    )
    palette.setColor(
        QtGui.QPalette.ColorRole.HighlightedText,
        theme.color("on_secondary_container"),
    )
    view.setPalette(palette)
    view.viewport().setPalette(palette)
    view.viewport().update()


class MaterialTableView(QtWidgets.QTableView):
    """已套用 M3 样式的表格视图。"""

    def __init__(
        self,
        dense: bool = False,
        dividers: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.material_delegate = apply_material_style(self, dense, dividers)


class MaterialListView(QtWidgets.QListView):
    """已套用 M3 样式的列表视图。"""

    def __init__(
        self,
        dense: bool = False,
        dividers: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.material_delegate = apply_material_style(self, dense, dividers)


class MaterialTreeView(QtWidgets.QTreeView):
    """已套用 M3 样式的树视图，展开箭头使用 Material 图标。"""

    def __init__(
        self,
        dense: bool = False,
        dividers: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.material_delegate = apply_material_style(self, dense, dividers)
        self.setRootIsDecorated(True)

    @override
    def drawBranches(
        self,
        painter: QtGui.QPainter,
        rect: QtCore.QRect,
        index: QtCore.QModelIndex,
    ) -> None:
        model = self.model()
        if model is None or not model.hasChildren(index):
            return
        theme = theme_module.current()
        expanded = self.isExpanded(index)
        icon = icons.coerce(
            "keyboard_arrow_down" if expanded else "keyboard_arrow_right",
            BRANCH_ICON_SIZE,
        )
        if icon is None:
            return
        indent = self.indentation()
        # 箭头位于本级缩进格子的中央。
        cell = QtCore.QRectF(
            rect.right() - indent + 1, rect.top(), indent, rect.height()
        )
        painter.save()
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        icon.paint(
            painter,
            QtCore.QRectF(
                cell.center().x() - BRANCH_ICON_SIZE / 2,
                cell.center().y() - BRANCH_ICON_SIZE / 2,
                BRANCH_ICON_SIZE,
                BRANCH_ICON_SIZE,
            ),
            theme.color("on_surface_variant"),
        )
        painter.restore()
