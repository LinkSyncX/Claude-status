"""命令面板（Command palette）。

类似编辑器里 Ctrl+K / Ctrl+Shift+P 的命令搜索框：置顶居中的对话框，
顶部是搜索输入，下面是按匹配度排序的命令列表（图标、标题、分类与快捷键
提示，匹配片段以 ``primary`` 高亮）。方向键移动、回车执行、Esc 关闭；
空查询时显示最近执行过的命令。``install_shortcut`` 把面板绑定到窗口的
快捷键上。
"""

from __future__ import annotations

from collections.abc import Callable
from collections.abc import Sequence
import dataclasses
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.dialogs import dialog as dialog_module
from md3.core import elevation as elevation_utils
from md3.core import shape as shape_utils
from md3.core import typography
from md3.core import widget
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

PALETTE_WIDTH = 560
SEARCH_HEIGHT = 56.0
ROW_HEIGHT = 48.0
MAX_VISIBLE_ROWS = 8
ROW_PADDING = 16.0
ICON_SIZE = 24.0
ICON_GAP = 16.0
SHADOW_MARGIN = 24
TOP_OFFSET_RATIO = 0.18
TITLE_STYLE = typography_tokens.TypeRole.BODY_LARGE
META_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM
EMPTY_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
ELEVATION = elevation.Level.LEVEL_3


@dataclasses.dataclass
class Command:
    """一条命令。

    Attributes:
        title: 标题。
        callback: 执行时调用的函数。
        icon: 图标。
        category: 分类（显示在右侧）。
        shortcut: 快捷键提示文字。
        keywords: 额外的匹配关键词。
        enabled: 是否可执行。
        key: 业务侧标识。
    """

    title: str
    callback: Callable[[], None] | None = None
    icon: icons.IconLike = None
    category: str = ""
    shortcut: str = ""
    keywords: tuple[str, ...] = ()
    enabled: bool = True
    key: Any = None


@dataclasses.dataclass(frozen=True)
class Match:
    """一次匹配结果。

    Attributes:
        command: 命令。
        score: 分数，越大越靠前。
        span: 标题中高亮的 (起点, 长度)，无高亮为 None。
    """

    command: Command
    score: int
    span: tuple[int, int] | None


def match_command(query: str, command: Command) -> Match | None:
    """把查询与命令匹配：前缀 > 词首 > 包含 > 子序列 > 关键词 / 分类。"""
    query = query.strip().lower()
    if not query:
        return Match(command, 0, None)
    title = command.title.lower()
    position = title.find(query)
    if position == 0:
        return Match(command, 400, (0, len(query)))
    if position > 0:
        boundary = title[position - 1] in " -_/·"
        return Match(command, 300 if boundary else 200, (position, len(query)))
    for text in (*command.keywords, command.category):
        if query in text.lower():
            return Match(command, 100, None)
    # 子序列匹配：查询字符依次出现在标题中。
    index = 0
    for char in title:
        if char == query[index]:
            index += 1
            if index == len(query):
                return Match(command, 50, None)
    return None


class _ResultList(widget.MaterialWidget):
    """命令列表：高亮行、悬停行与滚动。"""

    activated = QtCore.Signal(int)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._matches: list[Match] = []
        self._highlight = -1
        self._hovered = -1
        self._scroll = 0
        self._query = ""
        self.setMouseTracking(True)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    @property
    def matches(self) -> list[Match]:
        """当前显示的匹配。"""
        return list(self._matches)

    @property
    def highlighted(self) -> int:
        """高亮行下标。"""
        return self._highlight

    def set_matches(self, matches: Sequence[Match], query: str) -> None:
        """替换列表内容。"""
        self._matches = list(matches)
        self._query = query.strip().lower()
        self._highlight = 0 if self._matches else -1
        self._hovered = -1
        self._scroll = 0
        self.updateGeometry()
        self.update()

    def move_highlight(self, delta: int) -> None:
        """上下移动高亮行（循环）并保持可见。"""
        if not self._matches:
            return
        self._highlight = (self._highlight + delta) % len(self._matches)
        if self._highlight < self._scroll:
            self._scroll = self._highlight
        elif self._highlight >= self._scroll + MAX_VISIBLE_ROWS:
            self._scroll = self._highlight - MAX_VISIBLE_ROWS + 1
        self.update()

    def visible_rows(self) -> int:
        """实际显示的行数。"""
        return min(len(self._matches), MAX_VISIBLE_ROWS)

    def row_at(self, point: QtCore.QPointF) -> int:
        """位置对应的匹配下标，不在任何行上时为 -1。"""
        if not self._matches:
            return -1
        row = int(point.y() // ROW_HEIGHT) + self._scroll
        if 0 <= row < len(self._matches) and 0 <= point.y():
            return row
        return -1

    @override
    def sizeHint(self) -> QtCore.QSize:
        rows = max(1, self.visible_rows())
        return typography.size_hint(PALETTE_WIDTH, ROW_HEIGHT * rows)

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        if not self._matches:
            typography.paint_text(
                painter,
                QtCore.QRectF(self.rect()),
                i18n.tr("no_results"),
                EMPTY_STYLE,
                self.color("on_surface_variant"),
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
            return
        for offset in range(self.visible_rows()):
            index = self._scroll + offset
            if index >= len(self._matches):
                break
            self._paint_row(painter, index, offset)

    def _paint_row(
        self, painter: QtGui.QPainter, index: int, offset: int
    ) -> None:
        match = self._matches[index]
        command = match.command
        rect = QtCore.QRectF(0, offset * ROW_HEIGHT, self.width(), ROW_HEIGHT)
        if index == self._highlight:
            painter.fillRect(
                rect,
                theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.FOCUS_STATE_LAYER_OPACITY,
                ),
            )
        elif index == self._hovered:
            painter.fillRect(
                rect,
                theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.HOVER_STATE_LAYER_OPACITY,
                ),
            )
        enabled = command.enabled
        color = (
            self.color("on_surface")
            if enabled
            else theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        )
        meta_color = self.color("on_surface_variant") if enabled else color
        left = rect.left() + ROW_PADDING
        icon = icons.coerce(command.icon, ICON_SIZE)
        if icon is not None:
            icon.paint(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        left,
                        rect.center().y() - ICON_SIZE / 2,
                        ICON_SIZE,
                        ICON_SIZE,
                    )
                ),
                meta_color,
            )
        left += ICON_SIZE + ICON_GAP
        right = rect.right() - ROW_PADDING
        meta = " · ".join(
            part for part in (command.category, command.shortcut) if part
        )
        if meta:
            width = typography.text_width(meta, META_STYLE)
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        right - width, rect.top(), width, rect.height()
                    )
                ),
                meta,
                META_STYLE,
                meta_color,
                self.visual_alignment(
                    QtCore.Qt.AlignmentFlag.AlignRight
                    | QtCore.Qt.AlignmentFlag.AlignVCenter
                ),
            )
            right -= width + ICON_GAP
        title_rect = self.visual_rect(
            QtCore.QRectF(
                left, rect.top(), max(0.0, right - left), rect.height()
            )
        )
        if match.span is None or self.is_rtl():
            typography.paint_text(
                painter,
                title_rect,
                command.title,
                TITLE_STYLE,
                color,
                self.start_alignment(),
            )
            return
        start, length = match.span
        x = title_rect.left()
        for fragment, fragment_color in (
            (command.title[:start], color),
            (command.title[start : start + length], self.color("primary")),
            (command.title[start + length :], color),
        ):
            if not fragment:
                continue
            width = typography.text_width(fragment, TITLE_STYLE)
            typography.paint_text(
                painter,
                QtCore.QRectF(x, rect.top(), width + 2, rect.height()),
                fragment,
                TITLE_STYLE,
                fragment_color,
                elide=False,
            )
            x += width

    @override
    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        hovered = self.row_at(event.position())
        if hovered != self._hovered:
            self._hovered = hovered
            self.update()
        super().mouseMoveEvent(event)

    @override
    def leaveEvent(self, event: QtCore.QEvent) -> None:
        self._hovered = -1
        self.update()
        super().leaveEvent(event)

    @override
    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        index = self.row_at(event.position())
        if index >= 0:
            self.activated.emit(index)
        event.accept()

    @override
    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        steps = event.angleDelta().y() // 120
        if steps == 0:
            super().wheelEvent(event)
            return
        maximum = max(0, len(self._matches) - MAX_VISIBLE_ROWS)
        self._scroll = max(0, min(maximum, self._scroll - steps))
        self.update()
        event.accept()


class CommandPalette(dialog_module._DialogBase):  # pylint: disable=protected-access
    """命令面板。

    Args:
        commands: 初始命令列表。
        placeholder: 搜索框占位文字。
        max_recent: 空查询时显示的最近命令数。
        parent: 父控件（面板会覆盖其所在窗口）。
    """

    command_triggered = QtCore.Signal(object)

    def __init__(
        self,
        commands: Sequence[Command] = (),
        placeholder: str | None = None,
        max_recent: int = 5,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._commands: list[Command] = list(commands)
        self._recent: list[Command] = []
        self._max_recent = max(0, max_recent)
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )
        self._panel = QtWidgets.QWidget(self)
        self._panel.setFixedWidth(PALETTE_WIDTH)
        root.addWidget(self._panel)
        layout = QtWidgets.QVBoxLayout(self._panel)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(0)
        search_row = QtWidgets.QWidget(self._panel)
        search_row.setFixedHeight(round(SEARCH_HEIGHT))
        search_layout = QtWidgets.QHBoxLayout(search_row)
        search_layout.setContentsMargins(
            round(ROW_PADDING), 0, round(ROW_PADDING), 0
        )
        search_layout.setSpacing(round(ICON_GAP))
        self._search_icon = QtWidgets.QLabel(search_row)
        self._search_icon.setFixedSize(round(ICON_SIZE), round(ICON_SIZE))
        search_layout.addWidget(self._search_icon)
        self._edit = QtWidgets.QLineEdit(search_row)
        self._edit.setFrame(False)
        self._edit.setPlaceholderText(
            i18n.tr("type_to_search") if placeholder is None else placeholder
        )
        self._edit.textChanged.connect(self.refresh)
        self._edit.installEventFilter(self)
        search_layout.addWidget(self._edit, 1)
        layout.addWidget(search_row)
        self._divider = QtWidgets.QFrame(self._panel)
        self._divider.setFixedHeight(1)
        self._divider.setAutoFillBackground(True)
        layout.addWidget(self._divider)
        self._list = _ResultList(self._panel)
        self._list.activated.connect(self._trigger_index)
        layout.addWidget(self._list)
        self._apply_theme(theme_module.current())
        self.refresh()

    # ---- 命令 -------------------------------------------------------------

    @property
    def commands(self) -> list[Command]:
        """全部命令。"""
        return list(self._commands)

    def set_commands(self, commands: Sequence[Command]) -> None:
        """替换命令列表。"""
        self._commands = list(commands)
        self._recent = [c for c in self._recent if c in self._commands]
        self.refresh()

    def add_command(self, command: Command) -> Command:
        """追加命令。"""
        self._commands.append(command)
        self.refresh()
        return command

    @property
    def recent(self) -> list[Command]:
        """最近执行过的命令（最新在前）。"""
        return list(self._recent)

    @property
    def query(self) -> str:
        """当前查询文字。"""
        return self._edit.text()

    def set_query(self, text: str) -> None:
        """设置查询文字。"""
        self._edit.setText(text)

    @property
    def results(self) -> list[Match]:
        """当前显示的匹配结果。"""
        return self._list.matches

    @property
    def result_list(self) -> _ResultList:
        """结果列表控件。"""
        return self._list

    @property
    def editor(self) -> QtWidgets.QLineEdit:
        """搜索输入框。"""
        return self._edit

    def matches(self, query: str) -> list[Match]:
        """按查询返回排序后的匹配。"""
        if not query.strip():
            recent = [Match(c, 0, None) for c in self._recent if c.enabled]
            others = [
                Match(c, 0, None)
                for c in self._commands
                if c not in self._recent
            ]
            return recent + others
        found = [
            match
            for match in (match_command(query, c) for c in self._commands)
            if match is not None
        ]
        found.sort(key=lambda m: (-m.score, m.command.title.lower()))
        return found

    def refresh(self) -> None:
        """按当前查询刷新列表。"""
        self._list.set_matches(
            self.matches(self._edit.text()), self._edit.text()
        )
        self._panel.adjustSize()
        self.adjustSize()
        if self.isVisible():
            self._center_on_host()

    def _trigger_index(self, index: int) -> None:
        matches = self._list.matches
        if not 0 <= index < len(matches):
            return
        command = matches[index].command
        if not command.enabled:
            return
        self.accept()
        self._remember(command)
        if command.callback is not None:
            command.callback()
        self.command_triggered.emit(command)

    def _remember(self, command: Command) -> None:
        if self._max_recent <= 0:
            return
        if command in self._recent:
            self._recent.remove(command)
        self._recent.insert(0, command)
        del self._recent[self._max_recent :]

    def trigger_highlighted(self) -> bool:
        """执行高亮的命令，返回是否有命令被执行。"""
        index = self._list.highlighted
        if index < 0:
            return False
        self._trigger_index(index)
        return True

    # ---- 显示 -------------------------------------------------------------

    def open_palette(self) -> None:
        """清空查询并显示面板。"""
        self._edit.clear()
        self.refresh()
        self.open()
        self._edit.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)

    def install_shortcut(
        self, target: QtWidgets.QWidget, sequence: str = "Ctrl+K"
    ) -> QtGui.QShortcut:
        """在 ``target`` 上安装打开面板的快捷键。"""
        shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), target)
        shortcut.setContext(QtCore.Qt.ShortcutContext.WindowShortcut)
        shortcut.activated.connect(self.open_palette)
        return shortcut

    @override
    def _center_on_host(self) -> None:
        host = self._host()
        self.adjustSize()
        if host is None:
            return
        top_left = host.mapToGlobal(QtCore.QPoint(0, 0))
        x = top_left.x() + (host.width() - self.width()) // 2
        y = (
            top_left.y()
            + round(host.height() * TOP_OFFSET_RATIO)
            - SHADOW_MARGIN
        )
        self.move(x, max(top_left.y(), y))

    @override
    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        super()._on_theme_changed(theme)
        self._apply_theme(theme)

    def _apply_theme(self, theme: theme_module.Theme) -> None:
        icon = icons.coerce("search", ICON_SIZE)
        if icon is not None:
            self._search_icon.setPixmap(
                icon.pixmap(
                    theme.color("on_surface_variant"), self.devicePixelRatioF()
                )
            )
        self._edit.setFont(theme.font(TITLE_STYLE))
        palette = self._edit.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Text, theme.color("on_surface")
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.PlaceholderText,
            theme.color("on_surface_variant"),
        )
        palette.setColor(
            QtGui.QPalette.ColorRole.Base, theme_module.TRANSPARENT
        )
        self._edit.setPalette(palette)
        self._edit.setStyleSheet(
            "background: transparent; border: none; padding: 0px; margin: 0px;"
        )
        divider_palette = self._divider.palette()
        divider_palette.setColor(
            QtGui.QPalette.ColorRole.Window, theme.color("outline_variant")
        )
        self._divider.setPalette(divider_palette)

    # ---- 事件 -------------------------------------------------------------

    @override
    def eventFilter(
        self, watched: QtCore.QObject, event: QtCore.QEvent
    ) -> bool:
        if (
            watched is self._edit
            and event.type() == QtCore.QEvent.Type.KeyPress
        ):
            key = event.key()
            if key == QtCore.Qt.Key.Key_Down:
                self._list.move_highlight(1)
                return True
            if key == QtCore.Qt.Key.Key_Up:
                self._list.move_highlight(-1)
                return True
            if key in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                self.trigger_highlighted()
                return True
            if key == QtCore.Qt.Key.Key_Escape:
                self.reject()
                return True
        return super().eventFilter(watched, event)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self._panel.geometry())
        shape = shape_tokens.SHAPE_EXTRA_LARGE
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            ELEVATION,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape),
            theme.color("surface_container_high"),
        )
        painter.end()
