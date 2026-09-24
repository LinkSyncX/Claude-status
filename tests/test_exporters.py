"""导出到 sub2api / CPA（CLIProxyAPI）的测试。"""

import datetime as dt
import hashlib
import json
import sys
import unittest
from unittest import mock

from PySide6 import QtWidgets

import md3

from claude_status import app as app_module
from claude_status import code_config
from claude_status import exporters
from claude_status import models
from claude_status import state as state_module
from claude_status import storage
from claude_status import vault as vault_module
from claude_status.pages import accounts
from claude_status.pages import export_dialog
from tests import fixtures
from tests import qt

_APP = qt.application()
NOW = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC)


def _login(name: str, expires_in: float = 3600) -> code_config.CodeLogin:
    oauth_account = fixtures.oauth_account(name)
    oauth_account["organizationName"] = f"{name.upper()} Org"
    return code_config.CodeLogin(
        {"claudeAiOauth": fixtures.oauth(name, expires_in)}, oauth_account
    )


class ExportersTest(fixtures.IsolatedClaudeTest):
    def setUp(self):
        super().setUp()
        self.vault = vault_module.Vault(self.data_dir / "vault")
        self.alice = models.Account(name="Alice", email="alice@example.com")
        self.bob = models.Account(name="Bob", email="bob@example.com")
        self.desktop_only = models.Account(name="Desktop 账号", claude_uuid="uuid-d")
        self.relay = models.Account(
            name="Relay",
            auth_type=models.AuthType.RELAY,
            base_url="https://relay.example.com",
            api_key="relay-token",
        )
        self.empty_key = models.Account(name="空", auth_type=models.AuthType.API_KEY)
        self.vault.save_code(self.alice.id, _login("alice"))
        self.accounts = [
            self.alice,
            self.bob,
            self.desktop_only,
            self.relay,
            self.empty_key,
        ]

    def _items(self, live=None, owner=None):
        return exporters.collect(self.accounts, self.vault, live, owner)

    def test_collect_reasons_and_live_login(self):
        live = _login("bob")
        items = {item.account.name: item for item in self._items(live, self.bob)}
        self.assertTrue(items["Alice"].exportable)
        self.assertFalse(items["Alice"].live)
        # 没有保存、但正是 Claude Code 当前的登录：导出当前登录并提示。
        self.assertTrue(items["Bob"].exportable)
        self.assertTrue(items["Bob"].live)
        self.assertEqual(items["Bob"].login.email, "bob@example.com")
        # 只登录过 Desktop 的账号没有可导出的令牌。
        self.assertIn("登录…", items["Desktop 账号"].reason)
        self.assertTrue(items["Relay"].exportable)
        self.assertIsNone(items["Relay"].login)
        self.assertFalse(items["空"].exportable)

    def test_sub2api_payload(self):
        payload = exporters.to_sub2api(self._items(), NOW)
        self.assertEqual(payload["type"], "sub2api-data")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["exported_at"], "2026-09-24T12:00:00Z")
        self.assertEqual(payload["proxies"], [])
        by_name = {a["name"]: a for a in payload["accounts"]}
        self.assertEqual(sorted(by_name), ["Alice", "Relay"])
        alice = by_name["Alice"]
        self.assertEqual((alice["platform"], alice["type"]), ("anthropic", "oauth"))
        credentials = alice["credentials"]
        self.assertEqual(credentials["access_token"], "access-alice")
        self.assertEqual(credentials["refresh_token"], "refresh-alice")
        # expires_at 为 Unix 秒（字符串），与毫秒的 expiresAt 对应。
        saved = self.vault.load_code(self.alice.id)
        self.assertEqual(
            credentials["expires_at"], str(int(saved.expires_at.timestamp()))
        )
        self.assertEqual(credentials["scope"], "user:inference user:profile")
        self.assertEqual(
            alice["extra"],
            {
                "org_uuid": "org-alice",
                "account_uuid": "uuid-alice",
                "email_address": "alice@example.com",
            },
        )
        self.assertEqual((alice["concurrency"], alice["priority"]), (10, 1))
        relay = by_name["Relay"]
        self.assertEqual(relay["type"], "apikey")
        self.assertEqual(
            relay["credentials"],
            {"api_key": "relay-token", "base_url": "https://relay.example.com"},
        )
        self.assertNotIn("extra", relay)

    def test_cpa_file_name_matches_cliproxyapi(self):
        digest = hashlib.sha256(b"org-alice").hexdigest()[:8]
        self.assertEqual(
            exporters.cpa_file_name("alice@example.com", "org-alice", "uuid-alice"),
            f"claude-{digest}-alice@example.com.json",
        )
        account_digest = hashlib.sha256(b"uuid-alice").hexdigest()[:8]
        self.assertEqual(
            exporters.cpa_file_name("alice@example.com", "", "uuid-alice"),
            f"claude-{account_digest}-alice@example.com.json",
        )
        self.assertEqual(
            exporters.cpa_file_name("a@b.c"), "claude-a@b.c.json"
        )
        self.assertEqual(exporters.cpa_file_name("a/b:c"), "claude-a_b_c.json")

    def test_cpa_documents_and_api_key_snippet(self):
        files, keys = exporters.to_cpa(self._items(), NOW)
        [(name, document)] = files.items()
        self.assertTrue(name.startswith("claude-") and name.endswith(".json"))
        self.assertEqual(
            set(document),
            {
                "id_token",
                "access_token",
                "refresh_token",
                "last_refresh",
                "email",
                "account_uuid",
                "organization_uuid",
                "organization_name",
                "type",
                "expired",
            },
        )
        self.assertEqual(document["type"], "claude")
        self.assertEqual(document["last_refresh"], "2026-09-24T12:00:00Z")
        self.assertRegex(document["expired"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(document["organization_name"], "ALICE Org")
        self.assertIn("claude-api-key:", keys)
        self.assertIn('  - api-key: "relay-token"', keys)
        self.assertIn('    base-url: "https://relay.example.com"', keys)

    def test_write_files(self):
        items = self._items()
        out = self.root / "export"
        path = out / "sub2api.json"
        self.assertEqual(exporters.write_sub2api(path, items), 2)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["version"], 1)
        written = exporters.write_cpa(out / "cpa", items)
        self.assertEqual(len(written), 2)
        self.assertIn(exporters.CPA_API_KEYS_NAME, written)
        self.assertEqual(sorted(exporters.cpa_targets(items)), sorted(written))
        for name in written:
            self.assertTrue((out / "cpa" / name).is_file())


class ExportUiTest(fixtures.IsolatedClaudeTest):
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
        self.state.clients.capture_code()
        self.state.add_account(models.Account(name="Desktop 账号"))

    def tearDown(self):
        self.assertEqual(self.errors, [], "槽函数中出现异常")

    def test_dialog_selection(self):
        clients = self.state.clients
        items = exporters.collect(
            self.state.accounts, clients.vault, clients.code_login, clients.code_owner()
        )
        dialog = export_dialog.ExportDialog(exporters.CPA, items)
        self.addCleanup(dialog.deleteLater)
        # 不能导出的账号不单独列出，合并在说明里。
        [alice] = dialog._rows  # noqa: SLF001
        self.assertTrue(alice[0].checked)
        self.assertTrue(alice[1].live)
        self.assertIn("Desktop 账号", export_dialog.unavailable_text(items))
        self.assertEqual([item.account.name for item in dialog.selected()], ["ALICE"])
        alice[0].set_checked(False)
        self.assertFalse(dialog._export.isEnabled())  # noqa: SLF001

    def test_accounts_page_exports_to_cpa_directory(self):
        page = accounts.AccountsPage(self.state)
        self.addCleanup(page.deleteLater)
        target = self.root / "cli-proxy-api"
        with (
            mock.patch.object(
                export_dialog.ExportDialog,
                "exec",
                return_value=QtWidgets.QDialog.DialogCode.Accepted,
            ),
            mock.patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value=str(target),
            ),
        ):
            page.export_to(exporters.CPA)
        [file] = target.glob("claude-*.json")
        document = json.loads(file.read_text(encoding="utf-8"))
        self.assertEqual(document["email"], "alice@example.com")
        self.assertEqual(document["access_token"], "access-alice")


if __name__ == "__main__":
    unittest.main()
