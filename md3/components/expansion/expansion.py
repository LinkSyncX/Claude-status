"""折叠面板（Expansion panel）与手风琴（Accordion）。

``ExpansionPanel`` 由可点击的头部（前置图标、标题、副标题、旋转的展开
箭头）与可折叠的内容区组成，内容区以高度动画展开 / 收起；容器为 12dp
圆角的 ``surface_container_low``（或描边）。``Accordion`` 把若干面板竖直
堆叠，``exclusive=True`` 时同一时间只展开一个。
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
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

HEADER_HEIGHT = 56.0
HEADER_HEIGHT_WITH_SUBTITLE = 72.0
HEADER_PADDING = 16.0
ICON_SIZE = 24.0
ICON_GAP = 16.0
CHEVRON_SIZE = 24.0
TITLE_STYLE = typography_tokens.TypeRole.TITLE_MEDIUM
SUBTITLE_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
OUTLINE_WIDTH = 1.0


class _Header(widget.InteractiveWidget):
    """面板头部：整行可点击。"""

    def __init__(self, panel: ExpansionPanel) -> None:
        super().__init__(panel)
        self._panel = panel
        self._angle = animation.AnimatedFloat(self, 0.0, self.update)
        self.set_outer_margin(0.0)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_expanded(self, expanded: bool, animate: bool) -> None:
        """旋转箭头。"""
        target = 180.0 if expanded else 0.0
        if animate:
            self._angle.animate_to(target, motion.MEDIUM2, motion.EMPHASIZED)
        else:
            self._angle.set(target)

    @override
    def accessible_name(self) -> str:
        return self._panel.title

    @override
    def accessible_state(self, state: QtGui.QAccessible.State) -> None:
        super().accessible_state(state)
        state.expandable = True
        state.expanded = self._panel.expanded
        state.collapsed = not self._panel.expanded

    @override
    def container_shape(self) -> shape_tokens.Shape:
        return self._panel.header_shape()

    @override
    def focus_ring_extent(self) -> float:
        return 0.0

    @override
    def sizeHint(self) -> QtCore.QSize:
        return typography.size_hint(200.0, self._panel.header_height())

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return typography.size_hint(120.0, self._panel.header_height())

    @override
    def paint_content(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        panel = self._panel
        enabled = self.isEnabled()
        color = (
            self.color("on_surface")
            if enabled
            else theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        )
        secondary = self.color("on_surface_variant") if enabled else color
        left = rect.left() + HEADER_PADDING
        icon = icons.coerce(panel.icon, ICON_SIZE)
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
                secondary,
            )
            left += ICON_SIZE + ICON_GAP
        right = rect.right() - HEADER_PADDING - CHEVRON_SIZE - ICON_GAP
        title_height = self.theme.style(TITLE_STYLE).line_height
        subtitle_height = (
            self.theme.style(SUBTITLE_STYLE).line_height
            if panel.subtitle
            else 0
        )
        top = rect.center().y() - (title_height + subtitle_height) / 2
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(left, top, max(0.0, right - left), title_height)
            ),
            panel.title,
            TITLE_STYLE,
            color,
            self.start_alignment(),
        )
        if panel.subtitle:
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        left,
                        top + title_height,
                        max(0.0, right - left),
                        subtitle_height,
                    )
                ),
                panel.subtitle,
                SUBTITLE_STYLE,
                secondary,
                self.start_alignment(),
            )
        chevron = icons.coerce("expand_more", CHEVRON_SIZE)
        if chevron is not None:
            chevron_rect = self.visual_rect(
                QtCore.QRectF(
                    rect.right() - HEADER_PADDING - CHEVRON_SIZE,
                    rect.center().y() - CHEVRON_SIZE / 2,
                    CHEVRON_SIZE,
                    CHEVRON_SIZE,
                )
            )
            painter.save()
            center = chevron_rect.center()
            painter.translate(center)
            painter.rotate(self._angle.value)
            painter.translate(-center)
            chevron.paint(painter, chevron_rect, secondary)
            painter.restore()


class ExpansionPanel(widget.MaterialWidget):
    """折叠面板。

    Args:
        title: 标题。
        subtitle: 副标题。
        icon: 前置图标。
        expanded: 初始是否展开。
        outlined: 为真使用描边容器，否则为 ``surface_container_low`` 填充。
        parent: 父控件。
    """

    expanded_changed = QtCore.Signal(bool)

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        icon: icons.IconLike = None,
        expanded: bool = False,
        outlined: bool = False,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._icon = icon
        self._outlined = outlined
        self._expanded = expanded
        self._progress = animation.AnimatedFloat(
            self, 1.0 if expanded else 0.0, self._apply_progress
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._header = _Header(self)
        self._header.clicked.connect(self.toggle)
        self._header.set_expanded(expanded, animate=False)
        layout.addWidget(self._header)
        self._content = QtWidgets.QWidget(self)
        self._content_layout = QtWidgets.QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(
            round(spacing.SPACE_4),
            0,
            round(spacing.SPACE_4),
            round(spacing.SPACE_4),
        )
        self._content_layout.setSpacing(round(spacing.SPACE_2))
        layout.addWidget(self._content)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )
        self._apply_progress()

    # ---- 属性 -------------------------------------------------------------

    @property
    def title(self) -> str:
        """标题。"""
        return self._title

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self._title = title
        self._header.update()

    @property
    def subtitle(self) -> str:
        """副标题。"""
        return self._subtitle

    def set_subtitle(self, subtitle: str) -> None:
        """设置副标题。"""
        self._subtitle = subtitle
        self._header.updateGeometry()
        self._header.update()

    @property
    def icon(self) -> icons.IconLike:
        """前置图标。"""
        return self._icon

    @property
    def header(self) -> _Header:
        """头部控件。"""
        return self._header

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """内容区布局。"""
        return self._content_layout

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """放入内容控件。"""
        self._content_layout.addWidget(content)

    @property
    def expanded(self) -> bool:
        """是否展开。"""
        return self._expanded

    def set_expanded(self, expanded: bool, animate: bool = True) -> None:
        """展开或收起。"""
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._header.set_expanded(expanded, animate)
        target = 1.0 if expanded else 0.0
        if animate:
            self._progress.animate_to(target, motion.MEDIUM2, motion.EMPHASIZED)
        else:
            self._progress.set(target)
        self.expanded_changed.emit(expanded)

    def toggle(self) -> None:
        """切换展开状态。"""
        self.set_expanded(not self._expanded)

    def header_height(self) -> float:
        """头部高度。"""
        return HEADER_HEIGHT_WITH_SUBTITLE if self._subtitle else HEADER_HEIGHT

    def header_shape(self) -> shape_tokens.Shape:
        """头部状态层的形状：展开时只圆化顶部。"""
        if self._progress.value > 0.001:
            return shape_tokens.Shape.top(shape_tokens.MEDIUM)
        return shape_tokens.SHAPE_MEDIUM

    def _apply_progress(self) -> None:
        progress = self._progress.value
        full = self._content.sizeHint().height()
        height = round(full * progress)
        self._content.setVisible(height > 0)
        self._content.setMaximumHeight(height if progress < 0.999 else 16777215)
        self.updateGeometry()
        self.update()

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        rect = QtCore.QRectF(self.rect())
        if self._outlined:
            inset = OUTLINE_WIDTH / 2
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(
                    rect.adjusted(inset, inset, -inset, -inset),
                    shape_tokens.SHAPE_MEDIUM,
                ),
                None,
                self.color("outline_variant"),
                OUTLINE_WIDTH,
            )
        else:
            shape_utils.fill_shape(
                painter,
                shape_utils.rounded_rect_path(rect, shape_tokens.SHAPE_MEDIUM),
                self.color("surface_container_low"),
            )


class Accordion(QtWidgets.QWidget):
    """手风琴：竖直堆叠的折叠面板。

    Args:
        exclusive: 为真时同一时间只展开一个面板。
        spacing: 面板间距。
        parent: 父控件。
    """

    expanded_changed = QtCore.Signal(int, bool)

    def __init__(
        self,
        exclusive: bool = True,
        spacing_px: int = 8,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._exclusive = exclusive
        self._panels: list[ExpansionPanel] = []
        self._syncing = False
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(spacing_px)

    @property
    def panels(self) -> list[ExpansionPanel]:
        """全部面板。"""
        return list(self._panels)

    @property
    def exclusive(self) -> bool:
        """是否互斥展开。"""
        return self._exclusive

    def add_panel(
        self,
        title: str,
        subtitle: str = "",
        icon: icons.IconLike = None,
        content: QtWidgets.QWidget | None = None,
        expanded: bool = False,
        outlined: bool = False,
    ) -> ExpansionPanel:
        """新建并追加一个面板。"""
        panel = ExpansionPanel(title, subtitle, icon, expanded, outlined)
        if content is not None:
            panel.set_content(content)
        return self.add(panel)

    def add(self, panel: ExpansionPanel) -> ExpansionPanel:
        """追加已有面板。"""
        self._panels.append(panel)
        panel.expanded_changed.connect(
            lambda expanded, panel=panel: self._on_panel_changed(
                panel, expanded
            )
        )
        self._layout.addWidget(panel)
        if self._exclusive and panel.expanded:
            self._collapse_others(panel)
        return panel

    @property
    def expanded_index(self) -> int:
        """互斥模式下当前展开的面板下标，没有则为 -1。"""
        for index, panel in enumerate(self._panels):
            if panel.expanded:
                return index
        return -1

    def expand(self, index: int) -> None:
        """展开第 index 个面板。"""
        if 0 <= index < len(self._panels):
            self._panels[index].set_expanded(True)

    def collapse_all(self) -> None:
        """收起全部面板。"""
        for panel in self._panels:
            panel.set_expanded(False)

    def _collapse_others(self, keep: ExpansionPanel) -> None:
        self._syncing = True
        try:
            for other in self._panels:
                if other is not keep:
                    other.set_expanded(False)
        finally:
            self._syncing = False

    def _on_panel_changed(self, panel: ExpansionPanel, expanded: bool) -> None:
        if panel in self._panels:
            self.expanded_changed.emit(self._panels.index(panel), expanded)
        if expanded and self._exclusive and not self._syncing:
            self._collapse_others(panel)
