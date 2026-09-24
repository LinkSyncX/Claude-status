"""主窗口：左侧导航轨 + 顶部应用栏 + 以淡入淡出切换的页面。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.components import app_bars
from md3.components import buttons
from md3.components import dialogs
from md3.components import navigation
from md3.components import progress
from md3.components import snackbar
from md3.components import transitions
from md3.theme import theme as theme_module

import claude_status
from claude_status import models
from claude_status import state as state_module
from claude_status import themes
from claude_status.pages import accounts
from claude_status.pages import clients
from claude_status.pages import dashboard
from claude_status.pages import heatmap
from claude_status.pages import settings
from claude_status.widgets import common

PAGE_KEYS = ("accounts", "clients", "dashboard", "heatmap", "settings")
_DESTINATIONS = {
    "accounts": ("账号", "manage_accounts", "账号管理"),
    "clients": ("客户端", "devices", "客户端管理"),
    "dashboard": ("统计", "insights", "数据统计"),
    "heatmap": ("热力图", "calendar_month", "活跃热力图"),
    "settings": ("设置", "settings", "设置"),
}
_ACTION_REFRESH, _ACTION_THEME, _ACTION_HELP = 0, 1, 2
HELP_TEXT = (
    "1. 添加账号：账号页“新建账号 → 登录 Claude 账号”，在浏览器中登录并授权后"
    "自动保存，每个账号登录一次即可；中转 / API 账号选择“手动添加”。\n\n"
    "2. 一键切换：点击账号卡片上的“切换”，Claude Code 立即改用该账号（之后新开的"
    "会话生效，切换后的提示条中可以撤销）。切换前会自动备份当前配置，正在使用的"
    "中转配置也会先保存为账号，随时可以切回。\n\n"
    "3. Claude Desktop：Desktop 需要在它自己的窗口中登录。登录后到“客户端”页点击"
    "“关联到账号…”，再“保存会话…”；之后一键切换时会一起切换（需要重启 "
    "Desktop）。\n\n"
    "4. 查看当前账号：账号卡片上的“Code 使用中 / Desktop 使用中”标签，或"
    "“客户端”页。"
)


class MainWindow(QtWidgets.QMainWindow):
    """应用主窗口。

    Args:
        state: 应用状态。
    """

    def __init__(self, state: state_module.AppState) -> None:
        super().__init__()
        self._state = state
        self.setWindowTitle(claude_status.APP_NAME + " · Claude 账号管理")
        self.resize(1360, 900)
        self.setMinimumSize(960, 640)
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        fab = buttons.FloatingActionButton(
            "person_add",
            color=buttons.FabColor.TERTIARY,
            lowered=True,
            tooltip="新建账号",
        )
        fab.clicked.connect(
            lambda: self._create_account(
                fab.mapToGlobal(QtCore.QPoint(fab.width(), 0))
            )
        )
        self._rail = navigation.NavigationRail(
            [
                navigation.Destination(label, icon, key=key)
                for key, (label, icon, _title) in _DESTINATIONS.items()
            ],
            selected_index=0,
            header=fab,
        )
        self._rail.selection_changed.connect(self._on_rail_changed)
        root.addWidget(self._rail)

        right = QtWidgets.QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self._app_bar = app_bars.TopAppBar(
            _DESTINATIONS["accounts"][2],
            app_bars.TopAppBarVariant.SMALL,
            navigation_icon=None,
            actions=[
                app_bars.AppBarAction("refresh", "刷新数据"),
                app_bars.AppBarAction("dark_mode", "切换深色模式"),
                app_bars.AppBarAction("help", "如何切换账号"),
            ],
        )
        self._app_bar.action_triggered.connect(self._on_action)
        right.addWidget(self._app_bar)
        self._loading = progress.LinearProgressIndicator(None, thickness=3)
        self._loading.setFixedHeight(3)
        self._loading.setVisible(False)
        right.addWidget(self._loading)
        self._stack = transitions.AnimatedStackedWidget(
            transitions.Transition.FADE_THROUGH
        )
        right.addWidget(self._stack, 1)
        root.addLayout(right, 1)

        self._pages: dict[str, QtWidgets.QWidget] = {
            "accounts": accounts.AccountsPage(state),
            "clients": clients.ClientsPage(state),
            "dashboard": dashboard.DashboardPage(state),
            "heatmap": heatmap.HeatmapPage(state),
            "settings": settings.SettingsPage(state),
        }
        self._scrolls: dict[str, QtWidgets.QScrollArea] = {}
        for key in PAGE_KEYS:
            scroll = common.wrap_scroll(self._pages[key])
            self._scrolls[key] = scroll
            self._stack.addWidget(scroll)
        for key in ("accounts", "dashboard"):
            page = self._pages[key]
            assert isinstance(page, accounts.AccountsPage | dashboard.DashboardPage)
            page.navigate_requested.connect(self.show_page)

        state.loading_changed.connect(self._loading.setVisible)
        state.notify.connect(lambda text: snackbar.show(self, text))
        state.settings_changed.connect(self.apply_theme)
        state.accounts_changed.connect(self._update_badges)
        md3.theme_manager().theme_changed.connect(self._on_theme_changed)
        self.apply_theme()
        self._on_theme_changed(md3.current_theme())
        self._update_badges()
        self.show_page("accounts")
        if state.load_warning:
            warning = state.load_warning
            QtCore.QTimer.singleShot(
                800, lambda: snackbar.show(self, warning, closable=True)
            )
        # 启动后稍等再联网查询额度，避免拖慢首屏。
        QtCore.QTimer.singleShot(
            1500, lambda: state.clients.refresh_quotas(manual=False)
        )

    # ---- 导航 -------------------------------------------------------------

    def show_page(self, key: str) -> None:
        """切换到指定页面。"""
        if key not in self._pages:
            return
        index = PAGE_KEYS.index(key)
        if self._rail.selected_index != index:
            self._rail.set_selected_index(index)
        self._app_bar.set_title(_DESTINATIONS[key][2])
        scroll = self._scrolls[key]
        self._stack.set_current_widget(scroll)
        self._app_bar.attach_scroll_area(scroll)

    def page(self, key: str) -> QtWidgets.QWidget:
        """页面控件（供截图与测试使用）。"""
        return self._pages[key]

    def _on_rail_changed(self, index: int) -> None:
        self.show_page(PAGE_KEYS[index])

    def _create_account(self, pos: QtCore.QPoint) -> None:
        self.show_page("accounts")
        page = self._pages["accounts"]
        assert isinstance(page, accounts.AccountsPage)
        page.show_add_menu(pos)

    def show_help(self) -> None:
        """使用说明：如何添加并切换账号。"""
        dialogs.alert(self, "如何切换账号", HELP_TEXT, icon="help")

    def _update_badges(self) -> None:
        attention = sum(
            account.status
            in (models.AccountStatus.LIMITED, models.AccountStatus.EXPIRED)
            for account in self._state.accounts
        )
        self._rail.set_badge(0, attention or None)

    # ---- 主题 -------------------------------------------------------------

    def _on_action(self, index: int) -> None:
        if index == _ACTION_REFRESH:
            self._state.refresh()
            self._state.clients.refresh()
            self._state.clients.refresh_quotas(manual=False)
            source = self._state.data_source
            snackbar.show(
                self,
                "正在重新扫描本机日志…"
                if source is models.DataSource.LOCAL
                else "已重新生成演示数据",
            )
        elif index == _ACTION_THEME:
            self._state.update_settings(dark=not self._state.settings.dark)
        elif index == _ACTION_HELP:
            self.show_help()

    def apply_theme(self) -> None:
        """按设置应用界面风格、明暗模式与主题色（没有变化时不重绘）。"""
        md3.set_theme(themes.build(self._state.settings, md3.current_theme()))

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        buttons_ = self._app_bar.action_buttons
        if len(buttons_) > _ACTION_THEME:
            buttons_[_ACTION_THEME].set_icon(
                "light_mode" if theme.dark else "dark_mode"
            )
        palette = self.palette()
        palette.setColor(
            QtGui.QPalette.ColorRole.Window, theme.color("surface")
        )
        self.setPalette(palette)

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        self._state.shutdown()
        super().closeEvent(event)
