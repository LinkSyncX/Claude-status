"""组件画廊主窗口。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.components import app_bars
from md3.components import navigation
from md3.components import transitions
from md3.demo import theme_panel
from md3.demo.pages import _common
from md3.demo.pages import actions
from md3.demo.pages import charts as charts_page
from md3.demo.pages import communication
from md3.demo.pages import containment
from md3.demo.pages import data as data_page
from md3.demo.pages import extras
from md3.demo.pages import icons as icons_page
from md3.demo.pages import native as native_page
from md3.demo.pages import navigation as navigation_page
from md3.demo.pages import pickers
from md3.demo.pages import selection
from md3.demo.pages import text_inputs
from md3.demo.pages import theme as theme_page
from md3.theme import theme as theme_module

PAGES: list[tuple[navigation.Destination, Callable[[], QtWidgets.QWidget]]] = [
    (navigation.Destination("操作", "smart_button"), actions.build),
    (navigation.Destination("选择", "check_box"), selection.build),
    (navigation.Destination("输入", "edit_note"), text_inputs.build),
    (navigation.Destination("容器", "dashboard"), containment.build),
    (navigation.Destination("通信", "notifications"), communication.build),
    (navigation.Destination("导航", "explore"), navigation_page.build),
    (navigation.Destination("选择器", "calendar_month"), pickers.build),
    (navigation.Destination("图表", "bar_chart"), charts_page.build),
    (navigation.Destination("数据", "table_view"), data_page.build),
    (navigation.Destination("扩展", "extension"), extras.build),
    (navigation.Destination("图标", "interests"), icons_page.build),
    (navigation.Destination("原生", "widgets"), native_page.build),
    (navigation.Destination("主题", "palette"), theme_page.build),
]


class GalleryWindow(QtWidgets.QMainWindow):
    """左侧导航轨 + 右侧分类页面的组件画廊。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Material Design 3 组件画廊")
        self.resize(1280, 860)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._rail = navigation.NavigationRail(
            [destination for destination, _ in PAGES],
            selected_index=0,
            menu_button=True,
            expandable=True,
        )
        self._rail.selection_changed.connect(self._show_page)
        root.addWidget(self._rail)

        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self._app_bar = app_bars.TopAppBar(
            "Material Design 3 组件画廊",
            app_bars.TopAppBarVariant.SMALL,
            navigation_icon=None,
            actions=["dark_mode"],
        )
        self._app_bar.action_triggered.connect(self._on_app_bar_action)
        right.addWidget(self._app_bar)
        self._theme_panel = theme_panel.ThemePanel()
        right.addWidget(self._theme_panel)
        # 页面切换使用 fade-through 过渡（彼此无空间关系的顶层目的地）。
        self._stack = transitions.AnimatedStackedWidget(
            transitions.Transition.FADE_THROUGH
        )
        right.addWidget(self._stack, 1)
        root.addLayout(right, 1)

        self._built: dict[int, QtWidgets.QWidget] = {}
        self._show_page(0)
        md3.theme_manager().theme_changed.connect(self._on_theme_changed)
        self._on_theme_changed(md3.current_theme())

    def _show_page(self, index: int) -> None:
        if index not in self._built:
            page = PAGES[index][1]()
            scroll = _common.wrap_scroll(page)
            self._built[index] = scroll
            self._stack.addWidget(scroll)
            attach = getattr(page, "attach_search_view", None)
            if attach is not None:
                attach()
        self._stack.set_current_widget(self._built[index])
        # 应用栏跟随当前页面的滚动区域切换滚动态容器色。
        self._app_bar.attach_scroll_area(self._built[index])

    def _on_app_bar_action(self, index: int) -> None:
        if index == 0:
            md3.toggle_dark()

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        if self._app_bar.action_buttons:
            self._app_bar.action_buttons[0].set_icon(
                "light_mode" if theme.dark else "dark_mode"
            )
        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window, theme.color("surface")
        )
        self.setPalette(palette)
