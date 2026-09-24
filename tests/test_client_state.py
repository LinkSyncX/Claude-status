"""ClientManager、额度查询任务与界面切换流程的测试。

全部在临时目录中进行：Claude Code 配置、Desktop 数据目录与进程列表都是
假的（见 ``fixtures.IsolatedClaudeTest``），不会联网，也不会接触本机真实
的 Claude Desktop。
"""

import sys
import time
import unittest
from unittest import mock

from PySide6 import QtCore
from PySide6 import QtWidgets

import md3
from md3.components import dialogs

from claude_status import app as app_module
from claude_status import client_state
from claude_status import code_config
from claude_status import models
from claude_status import quota
from claude_status import state as state_module
from claude_status import storage
from claude_status.pages import actions
from claude_status.pages import clients as clients_page
from tests import fixtures
from tests import qt

_APP = qt.application()


def _pump_until(predicate, timeout_ms: int = 5000) -> bool:
    """处理事件直到条件成立，超时返回 False。"""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if predicate():
            return True
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(20, loop.quit)
        loop.exec()
    return predicate()


def _login(name: str, expires_in: float = 3600) -> code_config.CodeLogin:
    return code_config.CodeLogin(
        {"claudeAiOauth": fixtures.oauth(name, expires_in)},
        fixtures.oauth_account(name),
    )


class QuotaJobsTest(unittest.TestCase):
    """后台额度查询：正在使用的登录绝不刷新令牌。"""

    def test_live_login_is_never_refreshed(self):
        job = client_state._QuotaJob("a", _login("a", -60), allow_refresh=False)
        with (
            mock.patch.object(quota, "refresh_oauth") as refresh,
            mock.patch.object(quota, "fetch_usage") as fetch,
        ):
            [result] = client_state._run_quota_jobs([job], "")
        refresh.assert_not_called()
        fetch.assert_not_called()
        self.assertIsNone(result.quota)
        self.assertIn("过期", result.error)

    def test_live_login_auth_error_is_reported_without_refresh(self):
        job = client_state._QuotaJob("a", _login("a"), allow_refresh=False)
        with (
            mock.patch.object(quota, "refresh_oauth") as refresh,
            mock.patch.object(
                quota, "fetch_usage", side_effect=quota.QuotaError("auth", "401")
            ),
        ):
            [result] = client_state._run_quota_jobs([job], "")
        refresh.assert_not_called()
        self.assertEqual(result.error, "401")

    def test_saved_login_refreshes_once_after_auth_error(self):
        job = client_state._QuotaJob("a", _login("a"), allow_refresh=True)
        fetch = mock.Mock(
            side_effect=[
                quota.QuotaError("auth", "401"),
                {"five_hour": {"utilization": 7}},
            ]
        )
        with (
            mock.patch.object(
                quota, "refresh_oauth", return_value=fixtures.oauth("a2")
            ) as refresh,
            mock.patch.object(quota, "fetch_usage", fetch),
        ):
            [result] = client_state._run_quota_jobs([job], "")
        refresh.assert_called_once()
        self.assertEqual(fetch.call_args_list[1].args[0], "access-a2")
        self.assertEqual(result.quota.five_hour.percent, 7)
        self.assertEqual(result.refreshed.access_token, "access-a2")


class ClientManagerTest(fixtures.IsolatedClaudeTest):
    def setUp(self):
        super().setUp()
        self.login_code("alice")
        self.login_desktop("alice")
        now_ms = int(time.time() * 1000)
        samples = [
            (now_ms - 1_800_000, {"fh": 10, "sd": 30}),
            (now_ms - 300_000, {"fh": 20, "sd": 40}),
        ]
        fixtures.write_json(
            self.desktop_dir / "plan-usage-history.json",
            {
                "version": 2,
                "samples": [
                    {"t": stamp, "org": "org-alice", "u": usage}
                    for stamp, usage in samples
                ],
            },
        )
        self.desktop_processes.start_desktop()

    def _state(self, **kwargs) -> state_module.AppState:
        kwargs.setdefault("offline", True)
        app_state = state_module.AppState(storage.Store(self.data_dir), **kwargs)
        self.addCleanup(app_state.shutdown)
        return app_state

    def test_identity_learned_without_saving_login(self):
        # 首次启动时由本机登录信息创建的账号还没有保存登录，但 ~/.claude.json
        # 中同邮箱的 UUID 足以让 Desktop 识别它并对应上额度采样。
        state = self._state()
        clients = state.clients
        [alice] = state.accounts
        self.assertEqual(
            (alice.claude_uuid, alice.org_uuid), ("uuid-alice", "org-alice")
        )
        self.assertIs(clients.code_owner(), alice)
        self.assertIs(clients.current_code_account(), alice)
        self.assertIs(clients.current_desktop_account(), alice)
        self.assertEqual(state.settings.desktop_account_id, alice.id)
        info = clients.info(alice)
        self.assertFalse(info.code_saved or info.desktop_saved)
        self.assertIs(info.quota.source, quota.Source.DESKTOP)
        self.assertEqual(
            (info.quota.five_hour.percent, info.quota.seven_day.percent),
            (20, 40),
        )
        # 身份与额度随配置保存。
        [saved] = storage.Store(self.data_dir).load().accounts
        self.assertEqual(saved.claude_uuid, "uuid-alice")
        self.assertEqual(saved.quota["source"], quota.Source.DESKTOP.value)

    def test_identity_is_not_learned_for_other_email(self):
        state = self._state()
        [alice] = state.accounts
        alice.claude_uuid = alice.org_uuid = ""
        alice.email = "someone-else@example.com"
        state.clients.refresh()
        self.assertEqual(alice.claude_uuid, "")
        self.assertIsNone(state.clients.current_desktop_account())

    def test_capture_saves_current_login(self):
        state = self._state()
        clients = state.clients
        [alice] = state.accounts
        account, created = clients.capture_code()
        self.assertIs(account, alice)
        self.assertFalse(created)
        info = clients.info(alice)
        self.assertTrue(info.code_saved and info.code_current)
        self.assertTrue(info.desktop_current)
        self.assertFalse(info.desktop_saved)
        self.assertEqual(info.switch_targets(True), (False, False))

    def test_claude_code_cache_is_newer_than_desktop_sample(self):
        self.login_code(
            "alice",
            cachedUsageUtilization={
                "fetchedAtMs": int(time.time() * 1000),
                "accountUuid": "uuid-alice",
                "utilization": {"five_hour": {"utilization": 55}},
            },
        )
        state = self._state()
        [alice] = state.accounts
        state.clients.capture_code()
        info = state.clients.info(alice)
        self.assertIs(info.quota.source, quota.Source.CLAUDE_CODE)
        self.assertEqual(info.quota.five_hour.percent, 55)

    def test_online_refresh_reads_live_token_without_refreshing(self):
        state = self._state(offline=False)
        clients = state.clients
        [alice] = state.accounts
        clients.capture_code()
        payload = {"five_hour": {"utilization": 66}, "seven_day": {"utilization": 12}}
        with (
            mock.patch.object(quota, "fetch_usage", return_value=payload) as fetch,
            mock.patch.object(quota, "refresh_oauth") as refresh,
        ):
            self.assertTrue(clients.refresh_quotas(manual=True))
            self.assertTrue(_pump_until(lambda: not clients.quota_loading))
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0], "access-alice")
        refresh.assert_not_called()
        info = clients.info(alice)
        self.assertIs(info.quota.source, quota.Source.API)
        self.assertEqual(info.quota.five_hour.percent, 66)

    def test_offline_mode_never_queries(self):
        state = self._state()
        state.clients.capture_code()
        with mock.patch.object(quota, "fetch_usage") as fetch:
            self.assertFalse(state.clients.refresh_quotas(manual=True))
        fetch.assert_not_called()


class SwitchFlowTest(fixtures.IsolatedClaudeTest):
    """界面层的切换编排（actions 与客户端页）。"""

    def setUp(self):
        super().setUp()
        self.errors: list[BaseException] = []
        previous_hook = sys.excepthook
        sys.excepthook = lambda _type, value, _tb: self.errors.append(value)
        self.addCleanup(setattr, sys, "excepthook", previous_hook)
        self.login_code("alice")
        self.state = state_module.AppState(
            storage.Store(self.data_dir), offline=True
        )
        self.addCleanup(self.state.shutdown)
        md3.install(
            _APP,
            seed=self.state.settings.seed,
            extended=app_module.EXTENDED_COLORS,
            locale="zh",
        )
        [self.alice] = self.state.accounts
        self.state.clients.capture_code()
        self.page = clients_page.ClientsPage(self.state)
        self.page.resize(1100, 1600)
        self.page.show()
        self.addCleanup(self.page.close)

    def tearDown(self):
        _pump_until(lambda: False, 50)
        self.assertEqual(self.errors, [], "槽函数中出现异常")

    def _texts(self) -> str:
        _pump_until(lambda: False, 30)
        return "\n".join(
            label.text() for label in self.page.findChildren(QtWidgets.QLabel)
        )

    def test_oauth_switch_and_undo(self):
        self.login_code("bob")
        self.state.clients.refresh()
        bob, created = self.state.clients.capture_code()
        self.assertTrue(created)
        self.assertEqual(self.live_email(), "bob@example.com")
        with mock.patch.object(actions.snackbar, "show") as show:
            actions.switch_account(self.page, self.state, self.alice)
        self.assertEqual(self.live_email(), "alice@example.com")
        self.assertIs(self.state.clients.current_code_account(), self.alice)
        self.assertEqual(self.state.settings.active_account_id, self.alice.id)
        # 提示条中的"撤销"恢复切换前的登录。
        _widget, _message, action_text, undo = show.call_args.args[:4]
        self.assertEqual(action_text, "撤销")
        undo()
        self.assertEqual(self.live_email(), "bob@example.com")
        self.assertIs(self.state.clients.current_code_account(), bob)

    def test_relay_switch_writes_provider_env(self):
        self.set_settings()  # 已有的其他设置（model）切换时保持不变
        relay = models.Account(
            name="Relay",
            auth_type=models.AuthType.RELAY,
            base_url="https://relay.example.com",
            api_key="relay-token",
            env={"ANTHROPIC_DEFAULT_OPUS_MODEL": "relay-opus"},
        )
        self.state.add_account(relay)
        actions.switch_account(self.page, self.state, relay)
        self.assertEqual(
            code_config.read_provider_env(),
            {
                "ANTHROPIC_BASE_URL": "https://relay.example.com",
                "ANTHROPIC_AUTH_TOKEN": "relay-token",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "relay-opus",
            },
        )
        self.assertIs(self.state.clients.current_code_account(), relay)
        self.assertIn("中转 / API 配置 · Relay", self._texts())
        # 订阅登录仍然保留，切回订阅账号时清除中转配置。
        actions.switch_account(self.page, self.state, self.alice)
        self.assertEqual(code_config.read_provider_env(), {})
        self.assertEqual(self.settings()["model"], "opus")

    def test_oauth_without_saved_login_explains(self):
        other = models.Account(name="Other", email="other@example.com")
        self.state.add_account(other)
        with mock.patch.object(dialogs, "alert") as alert:
            actions.switch_account(self.page, self.state, other)
        alert.assert_called_once()
        self.assertEqual(self.live_email(), "alice@example.com")

    def test_desktop_capture_quits_and_relaunches(self):
        self.login_desktop("alice")
        self.desktop_processes.start_desktop()
        self.state.clients.refresh()
        self.assertIn("运行中（1 个进程）", self._texts())
        with (
            mock.patch.object(actions, "choose_account", return_value=self.alice),
            mock.patch.object(dialogs, "confirm", return_value=True),
        ):
            actions.capture_desktop(self.page, self.state)
            vault = self.state.clients.vault
            self.assertTrue(_pump_until(lambda: vault.has_desktop(self.alice.id)))
            self.assertTrue(
                _pump_until(lambda: "launch" in self.desktop_processes.calls)
            )
        self.assertEqual(self.desktop_processes.calls, ["quit", "launch"])
        info = self.state.clients.info(self.alice)
        self.assertTrue(info.desktop_saved and info.desktop_current)
        self.assertIn("ALICE（已保存）", self._texts())

    def test_desktop_switch_forces_quit_when_tray_ignores_close(self):
        # 先保存 alice 的会话，再让 Desktop 登录 bob 并保存到新账号。
        self.login_desktop("alice")
        self.state.clients.capture_desktop(self.alice)
        self.login_code("bob")
        self.state.clients.refresh()
        bob, _created = self.state.clients.capture_code()
        self.login_desktop("bob")
        self.state.clients.capture_desktop(bob)
        self.assertEqual(self.cookies(), "cookies-bob")
        self.desktop_processes.start_desktop()
        self.desktop_processes.ignore_quit = True
        with (
            mock.patch.object(dialogs, "confirm", return_value=True) as confirm,
            mock.patch.object(actions, "QUIT_TIMEOUT", 0.2),
        ):
            actions.switch_account(
                self.page, self.state, self.alice, code=False, desktop=True
            )
            self.assertTrue(
                _pump_until(lambda: self.cookies() == "cookies-alice")
            )
            self.assertTrue(
                _pump_until(lambda: "launch" in self.desktop_processes.calls)
            )
        # 两次确认：退出 Desktop、强制结束。
        self.assertEqual(confirm.call_count, 2)
        self.assertEqual(
            self.desktop_processes.calls, ["quit", "force", "launch"]
        )
        self.assertEqual(self.live_email(), "bob@example.com")  # 只切换了 Desktop
        self.assertIs(self.state.clients.current_desktop_account(), self.alice)

    def test_forget_saved_login(self):
        with mock.patch.object(dialogs, "confirm", return_value=True):
            actions.forget_login(self.page, self.state, self.alice, desktop=False)
        self.assertFalse(self.state.clients.vault.has_code(self.alice.id))
        self.assertIn("尚未保存", self._texts())


class EnvLinesTest(unittest.TestCase):
    def test_parse_and_format(self):
        env = code_config.parse_env_lines(
            "# 注释\n\nANTHROPIC_DEFAULT_OPUS_MODEL = relay-opus\n"
            "CLAUDE_CODE_SUBAGENT_MODEL=haiku\n"
        )
        self.assertEqual(
            env,
            {
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "relay-opus",
                "CLAUDE_CODE_SUBAGENT_MODEL": "haiku",
            },
        )
        self.assertEqual(
            code_config.parse_env_lines(code_config.format_env_lines(env)), env
        )

    def test_rejects_bad_lines(self):
        for text, message in (
            ("ANTHROPIC_MODEL", "第 1 行应为 KEY=VALUE"),
            ("\nANTHROPIC_BASE_URL=https://x", "第 2 行"),
            ("PATH=/usr/bin", "只支持"),
        ):
            with self.subTest(text=text):
                with self.assertRaises(ValueError) as caught:
                    code_config.parse_env_lines(text)
                self.assertIn(message, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
