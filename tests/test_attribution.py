"""本机用量按来源归属的测试：来源判断、身份时间线与关联 Desktop。"""

import datetime as dt
import sys
import time
import unittest
from unittest import mock

from PySide6 import QtCore

import md3
from md3.components import dialogs

from claude_status import app as app_module
from claude_status import attribution
from claude_status import claude_code
from claude_status import models
from claude_status import state as state_module
from claude_status import storage
from claude_status.pages import actions
from claude_status.pages import clients as clients_page
from tests import fixtures
from tests import qt

_APP = qt.application()
Source = models.UsageSource
T0 = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC)


def _at(hours: float) -> dt.datetime:
    return T0 + dt.timedelta(hours=hours)


def _record(source: Source, hours: float) -> models.UsageRecord:
    return models.UsageRecord(_at(hours), "claude-opus-5", 10, 10, source=source)


class SourceTest(unittest.TestCase):
    def test_request_source(self):
        cases = [
            ("cli", "req_011abc", Source.CODE),
            ("sdk-ts", "req_011abc", Source.CODE),
            ("claude-desktop", "req_011abc", Source.DESKTOP),
            ("claude-desktop-3p", "", Source.THIRD_PARTY),
            ("claude-desktop-3p", "req_011abc", Source.THIRD_PARTY),
            ("cli", "", Source.THIRD_PARTY),  # 中转没有官方请求 ID
            ("", "", Source.THIRD_PARTY),
        ]
        for entrypoint, request_id, expected in cases:
            with self.subTest(entrypoint=entrypoint, request_id=request_id):
                self.assertIs(
                    claude_code.request_source(entrypoint, request_id), expected
                )

    def test_parse_line_keeps_source(self):
        line = (
            '{"type": "assistant", "timestamp": "2026-09-01T12:00:00Z", '
            '"entrypoint": "claude-desktop", "requestId": "req_011x", '
            '"message": {"id": "msg_1", "model": "claude-opus-5", '
            '"usage": {"input_tokens": 3, "output_tokens": 4}}}'
        )
        _key, entry = claude_code.parse_line(line)
        self.assertEqual(entry.to_record().source, Source.DESKTOP)

    def test_current_code_identity(self):
        relay = {
            "ANTHROPIC_BASE_URL": "https://relay",
            "ANTHROPIC_AUTH_TOKEN": "secret-token-123",
        }
        source, identity = attribution.current_code_identity(None, relay)
        self.assertIs(source, Source.THIRD_PARTY)
        self.assertTrue(identity.startswith("env:"))
        self.assertNotIn("secret-token-123", identity)  # 只记录不可逆的指纹
        api = {"ANTHROPIC_API_KEY": "sk-ant-1"}
        self.assertIs(attribution.current_code_identity(None, api)[0], Source.CODE)
        self.assertIsNone(attribution.current_code_identity(None, {}))


class TimelineTest(unittest.TestCase):
    def test_record_event_dedupes_by_kind(self):
        raw: list[dict] = []
        self.assertTrue(
            attribution.record_event(raw, Source.DESKTOP, "account:a", _at(0))
        )
        self.assertFalse(
            attribution.record_event(raw, Source.DESKTOP, "account:a", _at(1))
        )
        # 采样的组织身份与实时观察的账号身份交替出现，不会无限追加。
        for hour in range(2, 6):
            attribution.record_event(raw, Source.DESKTOP, "org:o", _at(hour))
            attribution.record_event(raw, Source.DESKTOP, "account:a", _at(hour))
        self.assertEqual(len(raw), 2)
        # 可以插入过去的时刻，时间线保持有序。
        self.assertTrue(
            attribution.record_event(raw, Source.DESKTOP, "account:b", _at(-5))
        )
        times = [attribution.Event.from_dict(item).since for item in raw]
        self.assertEqual(times, sorted(times))

    def test_attribution_follows_switches(self):
        alice = models.Account(name="A", claude_uuid="uuid-a", org_uuid="org-a")
        bob = models.Account(name="B", claude_uuid="uuid-b")
        relay = models.Account(
            name="R",
            auth_type=models.AuthType.RELAY,
            base_url="https://relay/",
            api_key="tok",
        )
        env = {"ANTHROPIC_BASE_URL": "https://relay", "ANTHROPIC_AUTH_TOKEN": "tok"}
        events = [
            attribution.Event(Source.DESKTOP, "account:uuid-a", _at(0)),
            attribution.Event(Source.DESKTOP, "account:uuid-b", _at(10)),
            attribution.Event(Source.DESKTOP, "account:uuid-x", _at(20)),
            attribution.Event(
                Source.THIRD_PARTY, attribution.env_identity(env), _at(0)
            ),
        ]
        attributor = attribution.Attributor(
            events,
            [alice, bob, relay],
            default_account_id="default",
            fallback={Source.CODE: "account:uuid-b"},
        )
        records = [
            _record(Source.DESKTOP, -30),  # 最早观察之前：按最早的身份
            _record(Source.DESKTOP, 5),
            _record(Source.DESKTOP, 15),
            _record(Source.DESKTOP, 25),  # 未关联的账号
            _record(Source.THIRD_PARTY, 3),  # 端点末尾的 / 不影响识别
            _record(Source.CODE, 3),  # 没观察到：用回退身份
        ]
        owners = [r.account_id for r in attributor.assign(records)]
        self.assertEqual(
            owners, [alice.id, alice.id, bob.id, None, relay.id, bob.id]
        )
        empty = attribution.Attributor([], [alice], default_account_id="d")
        self.assertEqual(empty.account_for(Source.DESKTOP, _at(0)), "d")

    def test_org_identity_needs_a_unique_account(self):
        solo = models.Account(name="S", org_uuid="org-s")
        team = [
            models.Account(name="T1", org_uuid="org-t"),
            models.Account(name="T2", org_uuid="org-t"),
        ]
        resolve = attribution.Resolver([solo, *team])
        self.assertEqual(resolve("org:org-s"), solo.id)
        self.assertIsNone(resolve("org:org-t"))
        self.assertIsNone(resolve("org:"))
        self.assertIsNone(resolve("bogus"))

    def test_events_survive_settings_roundtrip(self):
        settings = models.Settings()
        attribution.record_event(
            settings.usage_sources, Source.CODE, "account:a", _at(0)
        )
        restored = models.Settings.from_dict(settings.to_dict())
        [event] = attribution.load_events(restored.usage_sources)
        self.assertEqual(event, attribution.Event(Source.CODE, "account:a", _at(0)))


class LinkDesktopTest(fixtures.IsolatedClaudeTest):
    """Desktop 登录着一个未知账号：不退出 Desktop 也能关联并显示额度。"""

    def setUp(self):
        super().setUp()
        self.errors: list[BaseException] = []
        previous_hook = sys.excepthook
        sys.excepthook = lambda _type, value, _tb: self.errors.append(value)
        self.addCleanup(setattr, sys, "excepthook", previous_hook)
        self.login_code("alice")
        self.login_desktop("bob")
        now_ms = int(time.time() * 1000)
        fixtures.write_json(
            self.desktop_dir / "plan-usage-history.json",
            {
                "samples": [
                    {"t": now_ms - 7_200_000, "org": "org-alice", "u": {"fh": 5}},
                    {"t": now_ms - 600_000, "org": "org-bob", "u": {"fh": 42}},
                ]
            },
        )
        self.desktop_processes.start_desktop()
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
        self.page = clients_page.ClientsPage(self.state)
        self.addCleanup(self.page.close)

    def tearDown(self):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(30, loop.quit)
        loop.exec()
        self.assertEqual(self.errors, [], "槽函数中出现异常")

    def test_link_new_account_without_quitting(self):
        clients = self.state.clients
        self.assertIsNone(clients.current_desktop_account())
        created = models.Account(name="Bob")
        with mock.patch.object(
            actions, "choose_account", return_value=(created, True)
        ):
            linked = actions.link_desktop(self.page, self.state)
        self.assertIs(linked, created)
        self.assertIn(created, self.state.accounts)
        self.assertEqual(
            (created.claude_uuid, created.org_uuid), ("uuid-bob", "org-bob")
        )
        self.assertIs(clients.current_desktop_account(), created)
        self.assertEqual(self.desktop_processes.calls, [])  # 没有退出 Desktop
        self.assertEqual(clients.info(created).quota.five_hour.percent, 42)
        # 采样补上的历史：两小时前 Desktop 登录的是 alice 的组织。
        attributor = clients.attributor()
        earlier = dt.datetime.now().astimezone() - dt.timedelta(minutes=90)
        self.assertEqual(
            attributor.account_for(Source.DESKTOP, earlier), self.alice.id
        )
        self.assertEqual(
            attributor.account_for(
                Source.DESKTOP, dt.datetime.now().astimezone()
            ),
            created.id,
        )

    def test_link_refuses_account_of_another_claude_user(self):
        with (
            mock.patch.object(
                actions, "choose_account", return_value=(self.alice, False)
            ),
            mock.patch.object(dialogs, "alert") as alert,
        ):
            self.assertIsNone(actions.link_desktop(self.page, self.state))
        alert.assert_called_once()
        self.assertEqual(self.alice.claude_uuid, "uuid-alice")
        self.assertIsNone(self.state.clients.current_desktop_account())

    def test_cancelled_choice_creates_nothing(self):
        with mock.patch.object(actions, "choose_account", return_value=None):
            self.assertIsNone(actions.link_desktop(self.page, self.state))
        self.assertEqual(len(self.state.accounts), 1)


if __name__ == "__main__":
    unittest.main()
