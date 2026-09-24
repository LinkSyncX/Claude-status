"""AppState 测试：通过 CLAUDE_CONFIG_DIR 指向临时目录，与本机数据隔离。"""

import dataclasses
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from PySide6 import QtCore

from claude_status import models
from claude_status import state as state_module
from claude_status import storage
from tests import fixtures
from tests import qt

_APP = qt.application()


def _wait_for(signal, timeout_ms: int = 5000) -> bool:
    """等待信号发出，超时返回 False。"""
    loop = QtCore.QEventLoop()
    fired = []
    signal.connect(lambda *_args: (fired.append(True), loop.quit()))
    QtCore.QTimer.singleShot(timeout_ms, loop.quit)
    loop.exec()
    return bool(fired)


class AppStateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self._tmp.name)
        self.claude_dir = root / "claude"
        self.store = storage.Store(root / "data")
        patcher = mock.patch.dict(
            os.environ,
            {
                "CLAUDE_CONFIG_DIR": str(self.claude_dir),
                "CLAUDE_STATUS_DESKTOP_DIR": str(root / "desktop"),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self._tmp.cleanup)
        fixtures.isolate_desktop_processes(self)

    def _state(self, **kwargs) -> state_module.AppState:
        kwargs.setdefault("offline", True)
        app_state = state_module.AppState(self.store, **kwargs)
        self.addCleanup(app_state.shutdown)
        return app_state

    def test_first_run_without_claude_code(self):
        app_state = self._state()
        self.assertEqual(app_state.data_source, models.DataSource.DEMO)
        self.assertEqual(app_state.accounts, [])
        self.assertTrue(self.store.load().existed)

    def test_first_run_detects_login(self):
        (self.claude_dir / "projects").mkdir(parents=True)
        (self.claude_dir / ".claude.json").write_text(
            json.dumps(
                {
                    "oauthAccount": {
                        "emailAddress": "me@example.com",
                        "displayName": "Me",
                        "organizationType": "claude_pro",
                    }
                }
            ),
            encoding="utf-8",
        )
        app_state = self._state()
        self.assertEqual(app_state.data_source, models.DataSource.LOCAL)
        self.assertEqual(len(app_state.accounts), 1)
        account = app_state.accounts[0]
        self.assertTrue(account.link_local)
        self.assertEqual(account.plan, models.Plan.PRO)
        self.assertEqual(app_state.settings.active_account_id, account.id)

    def test_force_demo_adds_samples(self):
        app_state = self._state(force_demo=True)
        self.assertGreaterEqual(len(app_state.accounts), 5)
        app_state.refresh()
        self.assertTrue(app_state.dataset.records)
        ids = {a.id for a in app_state.accounts}
        self.assertTrue(
            all(r.account_id in ids for r in app_state.dataset.records)
        )

    def test_only_one_account_links_local_logs(self):
        app_state = self._state()
        first = models.Account(name="A", link_local=True)
        second = models.Account(name="B", link_local=True)
        app_state.add_account(first)
        app_state.add_account(second)
        self.assertEqual(app_state.linked_account(), second)
        self.assertFalse(first.link_local)
        app_state.update_account(
            dataclasses.replace(second, link_local=False)
        )
        self.assertIsNone(app_state.linked_account())

    def test_delete_and_undo_restore_order_and_active(self):
        app_state = self._state()
        accounts = [models.Account(name=name) for name in "ABC"]
        for account in accounts:
            app_state.add_account(account)
        app_state.set_active(accounts[1].id)
        self.assertIsNotNone(accounts[1].last_used_at)
        removed, active = app_state.delete_accounts({accounts[1].id})
        self.assertEqual([a.name for a in app_state.accounts], ["A", "C"])
        active_id = app_state.settings.active_account_id
        self.assertNotEqual(active_id, accounts[1].id)
        app_state.restore_accounts(removed, active)
        self.assertEqual([a.name for a in app_state.accounts], ["A", "B", "C"])
        self.assertEqual(app_state.settings.active_account_id, accounts[1].id)
        reloaded = self.store.load()
        self.assertEqual([a.name for a in reloaded.accounts], ["A", "B", "C"])

    def test_custom_price_reprices_dataset(self):
        app_state = self._state(force_demo=True)
        app_state.refresh()
        before = app_state.dataset.totals().cost
        app_state.set_custom_price(
            "claude-sonnet-5", models.CustomPrice(100.0, 100.0, 100.0)
        )
        self.assertGreater(app_state.dataset.totals().cost, before)
        app_state.set_custom_price("claude-sonnet-5", None)
        self.assertAlmostEqual(app_state.dataset.totals().cost, before)

    def test_local_scan_attributes_records_to_linked_account(self):
        project = self.claude_dir / "projects" / "F--demo"
        project.mkdir(parents=True)
        line = {
            "type": "assistant",
            "timestamp": "2026-09-01T10:00:00Z",
            "cwd": "F:\\demo",
            "message": {
                "id": "m1",
                "model": "claude-opus-5",
                "usage": {"input_tokens": 10, "output_tokens": 20},
            },
        }
        (project / "s.jsonl").write_text(json.dumps(line), encoding="utf-8")
        app_state = self._state()
        # 日志目录在首次启动前已存在，因此默认数据源就是本机日志。
        self.assertEqual(app_state.data_source, models.DataSource.LOCAL)
        account = models.Account(name="Local", link_local=True)
        app_state.add_account(account)
        app_state.refresh()
        self.assertTrue(app_state.loading)
        self.assertTrue(_wait_for(app_state.loading_changed))
        self.assertFalse(app_state.loading)
        records = app_state.dataset.records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].account_id, account.id)
        self.assertEqual(records[0].project, "demo")
        app_state.link_local(None)
        self.assertIsNone(app_state.dataset.records[0].account_id)


if __name__ == "__main__":
    unittest.main()
