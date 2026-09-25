"""界面冒烟测试：在 offscreen 平台上走一遍各页面的主要交互。

槽函数中的异常不会直接让测试失败（Qt 只会打印），因此这里临时替换
``sys.excepthook`` 收集异常，并在每个用例结束时断言没有异常发生。
"""

import datetime as dt
import os
import pathlib
import sys
import tempfile
from typing import override
import unittest
from unittest import mock

from PySide6 import QtCore
from PySide6 import QtWidgets

import md3
from md3.components import dialogs

from claude_status import app as app_module
from claude_status import code_config
from claude_status import main_window
from claude_status import models
from claude_status import state as state_module
from claude_status import storage
from tests import fixtures
from tests import qt

_APP = qt.application()


def _pump(milliseconds: int = 50) -> None:
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


_LEGIT_WINDOWS = (
    QtCore.Qt.WindowType.Dialog,
    QtCore.Qt.WindowType.Popup,
    QtCore.Qt.WindowType.ToolTip,
)


class StrayWindowWatcher(QtCore.QObject):
    """记录主窗口、对话框与弹出层之外显示出来的顶层窗口。

    没有父控件的控件一旦 ``setVisible(True)`` 就会显示成独立窗口，等加入
    布局后才变回子控件——启动时就会看到一堆窗口一闪而过。
    """

    def __init__(self) -> None:
        super().__init__()
        self.stray: list[str] = []

    @override
    def eventFilter(self, watched: QtCore.QObject, event: QtCore.QEvent) -> bool:
        if (
            event.type() == QtCore.QEvent.Type.Show
            and isinstance(watched, QtWidgets.QWidget)
            and watched.isWindow()
            and not isinstance(watched, main_window.MainWindow)
            and watched.windowType() not in _LEGIT_WINDOWS
        ):
            text = watched.text() if isinstance(watched, QtWidgets.QLabel) else ""
            self.stray.append(f"{type(watched).__name__} {text!r}")
        return False


class UiSmokeTest(unittest.TestCase):
    def setUp(self):
        self.errors: list[BaseException] = []
        previous_hook = sys.excepthook
        sys.excepthook = lambda _type, value, _tb: self.errors.append(value)
        self.addCleanup(setattr, sys, "excepthook", previous_hook)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        env = mock.patch.dict(
            os.environ,
            {
                "CLAUDE_CONFIG_DIR": str(root / "claude"),
                "CLAUDE_STATUS_DESKTOP_DIR": str(root / "desktop"),
            },
        )
        env.start()
        self.addCleanup(env.stop)
        fixtures.isolate_desktop_processes(self)
        self.watcher = StrayWindowWatcher()
        _APP.installEventFilter(self.watcher)
        self.addCleanup(_APP.removeEventFilter, self.watcher)
        self.state = state_module.AppState(
            storage.Store(root / "data"), force_demo=True, offline=True
        )
        md3.install(
            _APP,
            seed=self.state.settings.seed,
            dark=False,
            extended=app_module.EXTENDED_COLORS,
            locale="zh",
        )
        self.window = main_window.MainWindow(self.state)
        self.window.resize(1280, 860)
        self.window.show()
        self.state.refresh()
        _pump(200)
        self.addCleanup(self.window.close)

    def tearDown(self):
        _pump()
        self.assertEqual(self.errors, [], "槽函数中出现异常")
        self.assertEqual(self.watcher.stray, [], "出现了一闪而过的独立窗口")

    def test_startup_shows_no_stray_windows(self):
        # setUp 已经走完启动流程：创建主窗口、显示并刷新数据。
        self.assertEqual(self.watcher.stray, [])
        self.state.update_settings(theme_style="minimal", dark=True)
        self.window.apply_theme()
        self.state.refresh()
        _pump(200)
        self.assertEqual(self.watcher.stray, [])

    def test_all_pages_render(self):
        for key in main_window.PAGE_KEYS:
            self.window.show_page(key)
            _pump(80)
            self.assertFalse(self.window.page(key).grab().isNull())

    def test_accounts_page_interactions(self):
        page = self.window.page("accounts")
        state = self.state
        # 只有中转账号的 Base URL 匹配。
        page._search.set_text("relay.example")
        _pump()
        self.assertEqual(len(page._table_ids), 1)
        page._search.set_text("API")  # 名称与"API 按量"套餐都会匹配
        _pump()
        self.assertEqual(len(page._table_ids), 2)
        page._search.set_text("")
        page._filters.set_selected([3])  # 已过期
        _pump()
        self.assertEqual(len(page._table_ids), 1)
        page._filters.set_selected([0])
        page._view.set_selected([1])
        for sort in range(len(page._sort.options)):
            page._sort.set_selected_index(sort)
        _pump()
        target = state.accounts[2]
        # 演示模式：不改动真实客户端的配置。
        page.switch_account(target.id)
        self.assertEqual(code_config.read_provider_env(), {})
        page._on_account_action(target.id, ("favorite", None))
        self.assertTrue(target.favorite)
        page._on_account_action(target.id, ("link", None))
        self.assertTrue(target.link_local)
        page._on_account_action(
            target.id, ("status", models.AccountStatus.DISABLED)
        )
        self.assertIs(target.status, models.AccountStatus.DISABLED)
        page.open_details(target.id)
        _pump(500)
        with mock.patch.object(dialogs, "confirm", return_value=True):
            page.delete_account(target.id)
        _pump(300)
        self.assertIsNone(state.account(target.id))
        self.assertFalse(page._sheet.is_open)
        page.open_details(state.accounts[0].id)
        _pump(500)
        page._close_sheet()
        _pump(300)

    def test_dashboard_and_heatmap_controls(self):
        dashboard = self.window.page("dashboard")
        self.window.show_page("dashboard")
        for range_index in range(5):
            dashboard._range.set_selected([range_index])
            for metric_index in range(3):
                dashboard._metric.set_selected([metric_index])
        dashboard._accounts.set_selected_index(1)
        _pump()
        heatmap = self.window.page("heatmap")
        self.window.show_page("heatmap")
        for period in range(len(heatmap._periods)):
            heatmap._period.set_selected([period])
            for metric_index in range(3):
                heatmap._metric.set_selected([metric_index])
        heatmap._on_day_clicked(dt.date.today() - dt.timedelta(days=3))
        heatmap._on_day_clicked(None)
        _pump()

    def test_minimal_theme_from_settings(self):
        settings_page = self.window.page("settings")
        self.window.show_page("settings")
        settings_page._style.set_selected([1])  # 极简白
        _pump()
        self.assertEqual(self.state.settings.theme_style, "minimal")
        self.assertEqual(md3.current_theme().argb("surface") & 0xFFFFFF, 0xFFFFFF)
        self.assertFalse(settings_page._seeds.isEnabled())
        self.state.update_settings(dark=True)  # 极简黑
        self.assertEqual(md3.current_theme().argb("surface") & 0xFFFFFF, 0x141414)
        settings_page._style.set_selected([0])  # 回到 Material
        _pump()
        self.assertTrue(settings_page._seeds.isEnabled())
        self.assertNotEqual(
            md3.current_theme().argb("surface") & 0xFFFFFF, 0x141414
        )
        for key in main_window.PAGE_KEYS:
            self.window.show_page(key)
            _pump(50)

    def test_settings_changes(self):
        settings_page = self.window.page("settings")
        self.window.show_page("settings")
        settings_page._seeds.set_selected([2])
        _pump()
        self.assertEqual(self.state.settings.seed, "#0061A4")
        self.assertEqual(md3.current_theme().seed & 0xFFFFFF, 0x0061A4)
        self.state.update_settings(dark=True)
        self.assertTrue(md3.current_theme().dark)
        self.state.set_custom_price(
            "grok-4.6", models.CustomPrice(1.0, 2.0, None)
        )
        settings_page._source.set_selected([0])  # 本机日志（目录不存在）
        for _ in range(50):
            if not self.state.loading:
                break
            _pump(100)
        dashboard = self.window.page("dashboard")
        self.assertEqual(dashboard._banner_key, "missing")


if __name__ == "__main__":
    unittest.main()
