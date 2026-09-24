"""文件拖放区（Drop zone）。

12dp 圆角的虚线描边区域：图标、提示文字与"浏览文件"链接。把文件拖入时
描边与背景切换为 ``primary`` 强调，文件类型不符时切换为 ``error``；放下
后发出 ``files_dropped``。点击区域（或按空格 / 回车）打开系统文件对话框，
``picker`` 参数可注入自定义选择函数以便测试。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
import pathlib
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
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

Picker = Callable[["DropZone"], list[str]]
ICON_SIZE = 40.0
OUTLINE_WIDTH = 1.5
DASH_LENGTH = 6.0
TEXT_STYLE = typography_tokens.TypeRole.BODY_LARGE
HINT_STYLE = typography_tokens.TypeRole.LABEL_LARGE
MIN_HEIGHT = 160.0


class DropZone(widget.InteractiveWidget):
    """文件拖放区。

    Args:
        text: 主提示文字，默认"拖放文件到这里"。
        hint: 次要文字（作为点击浏览的提示），默认"浏览文件"。
        icon: 图标。
        extensions: 接受的扩展名（如 ``[".png", ".jpg"]``），空表示全部。
        multiple: 是否接受多个文件。
        picker: 自定义选择函数 ``zone -> [路径]``，替代系统对话框。
        parent: 父控件。
    """

    files_dropped = QtCore.Signal(list)
    rejected = QtCore.Signal(list)

    def __init__(
        self,
        text: str | None = None,
        hint: str | None = None,
        icon: icons.IconLike = "upload_file",
        extensions: Sequence[str] = (),
        multiple: bool = True,
        picker: Picker | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._text = i18n.tr("drop_files_here") if text is None else text
        self._hint = i18n.tr("browse_files") if hint is None else hint
        self._icon = icons.coerce(icon, ICON_SIZE)
        self._extensions = tuple(ext.lower() for ext in extensions)
        self._multiple = multiple
        self._picker = picker
        self._drag_state = ""  # "" / "accept" / "reject"
        self._highlight = animation.AnimatedFloat(self, 0.0, self.update)
        self.set_outer_margin(0.0)
        self.setAcceptDrops(True)
        self.setMinimumHeight(round(MIN_HEIGHT))
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )

    # ---- 属性 -------------------------------------------------------------

    @property
    def extensions(self) -> tuple[str, ...]:
        """接受的扩展名。"""
        return self._extensions

    def set_extensions(self, extensions: Sequence[str]) -> None:
        """设置接受的扩展名。"""
        self._extensions = tuple(ext.lower() for ext in extensions)

    @property
    def drag_state(self) -> str:
        """当前拖入状态：空、``accept`` 或 ``reject``。"""
        return self._drag_state

    def set_text(self, text: str) -> None:
        """设置主提示文字。"""
        self._text = text
        self.update()

    def accepts(self, path: str) -> bool:
        """文件是否符合扩展名要求。"""
        if not self._extensions:
            return True
        return pathlib.Path(path).suffix.lower() in self._extensions

    def _paths_of(self, mime: QtCore.QMimeData) -> list[str]:
        return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.Button

    @override
    def accessible_name(self) -> str:
        return self._text

    # ---- 浏览 -------------------------------------------------------------

    @override
    def activate(self) -> None:
        self.browse()
        super().activate()

    def browse(self) -> list[str]:
        """打开文件对话框；选定后发出 ``files_dropped``。"""
        if self._picker is not None:
            paths = list(self._picker(self))
        else:
            name_filter = ""
            if self._extensions:
                patterns = " ".join(f"*{ext}" for ext in self._extensions)
                name_filter = f"({patterns})"
            if self._multiple:
                paths, _selected = QtWidgets.QFileDialog.getOpenFileNames(
                    self.window(), self._hint, "", name_filter
                )
            else:
                path, _selected = QtWidgets.QFileDialog.getOpenFileName(
                    self.window(), self._hint, "", name_filter
                )
                paths = [path] if path else []
        accepted = [path for path in paths if path and self.accepts(path)]
        if accepted:
            self.files_dropped.emit(accepted)
        return accepted

    # ---- 拖放 -------------------------------------------------------------

    def _set_drag_state(self, state: str) -> None:
        if state == self._drag_state:
            return
        self._drag_state = state
        self._highlight.animate_to(
            1.0 if state else 0.0, motion.SHORT3, motion.STANDARD
        )
        self.update()

    @override
    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        paths = self._paths_of(event.mimeData())
        if not paths or not self.isEnabled():
            event.ignore()
            return
        # 单文件模式与 dropEvent 一致，只看第一个文件。
        if not self._multiple:
            paths = paths[:1]
        accepted = [path for path in paths if self.accepts(path)]
        self._set_drag_state("accept" if accepted else "reject")
        event.acceptProposedAction()

    @override
    def dragMoveEvent(self, event: QtGui.QDragMoveEvent) -> None:
        event.acceptProposedAction()

    @override
    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent) -> None:
        del event
        self._set_drag_state("")

    @override
    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        paths = self._paths_of(event.mimeData())
        self._set_drag_state("")
        if not self._multiple:
            paths = paths[:1]
        accepted = [path for path in paths if self.accepts(path)]
        refused = [path for path in paths if not self.accepts(path)]
        if refused:
            self.rejected.emit(refused)
        if accepted:
            self.files_dropped.emit(accepted)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return shape_tokens.SHAPE_MEDIUM

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    @override
    def state_layer_color(self) -> QtGui.QColor:
        return self.color("primary")

    def _accent(self) -> QtGui.QColor:
        if self._drag_state == "reject":
            return self.color("error")
        return self.color("primary")

    @override
    def paint_container(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect()).adjusted(
            OUTLINE_WIDTH, OUTLINE_WIDTH, -OUTLINE_WIDTH, -OUTLINE_WIDTH
        )
        path = shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_MEDIUM)
        progress = self._highlight.value
        enabled = self.isEnabled()
        if progress > 0.001:
            fill = QtGui.QColor(self._accent())
            fill.setAlphaF(0.08 * progress)
            shape_utils.fill_shape(painter, path, fill)
        outline = (
            theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_OUTLINE_OPACITY
            )
            if not enabled
            else self.color("outline")
        )
        if progress > 0.001 and enabled:
            accent = self._accent()
            outline = QtGui.QColor.fromRgbF(
                outline.redF() + (accent.redF() - outline.redF()) * progress,
                outline.greenF()
                + (accent.greenF() - outline.greenF()) * progress,
                outline.blueF() + (accent.blueF() - outline.blueF()) * progress,
            )
        pen = QtGui.QPen(outline, OUTLINE_WIDTH)
        pen.setStyle(QtCore.Qt.PenStyle.CustomDashLine)
        pen.setDashPattern(
            [DASH_LENGTH / OUTLINE_WIDTH, DASH_LENGTH / OUTLINE_WIDTH]
        )
        pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawPath(path)
        painter.restore()

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        enabled = self.isEnabled()
        content_color = (
            theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
            if not enabled
            else self.color("on_surface_variant")
        )
        text_height = self.theme.style(TEXT_STYLE).line_height
        hint_height = self.theme.style(HINT_STYLE).line_height
        block = ICON_SIZE + 12 + text_height + hint_height
        top = rect.center().y() - block / 2
        if self._icon is not None:
            self._icon.paint(
                painter,
                QtCore.QRectF(
                    rect.center().x() - ICON_SIZE / 2, top, ICON_SIZE, ICON_SIZE
                ),
                self._accent()
                if self._highlight.value > 0.5
                else content_color,
            )
        typography.paint_text(
            painter,
            QtCore.QRectF(
                rect.left() + 16,
                top + ICON_SIZE + 12,
                rect.width() - 32,
                text_height,
            ),
            self._text,
            TEXT_STYLE,
            self.color("on_surface") if enabled else content_color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        typography.paint_text(
            painter,
            QtCore.QRectF(
                rect.left() + 16,
                top + ICON_SIZE + 12 + text_height,
                rect.width() - 32,
                hint_height,
            ),
            self._hint,
            HINT_STYLE,
            self.color("primary") if enabled else content_color,
            QtCore.Qt.AlignmentFlag.AlignCenter,
        )

    @override
    def sizeHint(self) -> QtCore.QSize:
        return typography.size_hint(320.0, MIN_HEIGHT)
