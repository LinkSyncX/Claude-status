"""Claude Code 配置读写、Desktop 会话快照与一键切换测试。"""

import datetime as dt
import json
from unittest import mock

from claude_status import claude_desktop
from claude_status import code_config
from claude_status import models
from claude_status import switcher as switcher_module
from claude_status import vault as vault_module
from tests import fixtures


class CodeConfigTest(fixtures.IsolatedClaudeTest):
    def test_read_and_write_login_preserves_other_state(self):
        self.assertIsNone(code_config.read_code_login())
        self.login_code("alice")
        login = code_config.read_code_login()
        self.assertEqual(login.email, "alice@example.com")
        self.assertEqual(login.account_uuid, "uuid-alice")
        self.assertFalse(login.expired())
        self.login_code("bob")
        code_config.write_code_login(login)
        self.assertEqual(self.live_email(), "alice@example.com")
        state = fixtures.read_json(self.claude_dir / ".claude.json")
        self.assertEqual(state["projects"], {"F:/demo": {"history": [1, 2]}})
        credentials = fixtures.read_json(self.claude_dir / ".credentials.json")
        self.assertEqual(
            credentials["claudeAiOauth"]["accessToken"], "access-alice"
        )

    def test_expiry(self):
        self.login_code("alice")
        login = code_config.read_code_login()
        later = dt.datetime.now().astimezone() + dt.timedelta(hours=2)
        self.assertTrue(login.expired(later))

    def test_provider_env_only_touches_provider_keys(self):
        self.set_settings(
            env={
                "ANTHROPIC_BASE_URL": "https://old.example.com",
                "ANTHROPIC_AUTH_TOKEN": "old",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "old-opus",
                "CLAUDE_CODE_SUBAGENT_MODEL": "old-sub",
                "CLAUDE_CODE_EFFORT_LEVEL": "high",
            },
            statusLine={"type": "command"},
        )
        code_config.write_provider_env({"ANTHROPIC_API_KEY": "sk-new"})
        settings = self.settings()
        self.assertEqual(
            settings["env"],
            {"CLAUDE_CODE_EFFORT_LEVEL": "high", "ANTHROPIC_API_KEY": "sk-new"},
        )
        self.assertEqual(settings["statusLine"], {"type": "command"})
        code_config.write_provider_env({})
        self.assertEqual(
            self.settings()["env"], {"CLAUDE_CODE_EFFORT_LEVEL": "high"}
        )

    def test_provider_env_for_accounts(self):
        relay = models.Account(
            auth_type=models.AuthType.RELAY,
            base_url="https://relay.example.com",
            api_key="tok",
            env={"ANTHROPIC_DEFAULT_OPUS_MODEL": "m", "IGNORED": "x"},
        )
        env = code_config.provider_env_for(relay)
        self.assertEqual(
            env,
            {
                "ANTHROPIC_BASE_URL": "https://relay.example.com",
                "ANTHROPIC_AUTH_TOKEN": "tok",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "m",
            },
        )
        self.assertTrue(code_config.matches_provider_env(relay, env))
        api = models.Account(auth_type=models.AuthType.API_KEY, api_key="sk")
        self.assertEqual(
            code_config.provider_env_for(api), {"ANTHROPIC_API_KEY": "sk"}
        )
        self.assertEqual(code_config.provider_env_for(models.Account()), {})

    def test_account_from_env(self):
        relay = code_config.account_from_env(
            {
                "ANTHROPIC_BASE_URL": "https://relay.example.com/v1",
                "ANTHROPIC_AUTH_TOKEN": "tok",
                "ANTHROPIC_DEFAULT_OPUS_MODEL": "m",
            }
        )
        self.assertIs(relay.auth_type, models.AuthType.RELAY)
        self.assertEqual(relay.name, "中转 relay.example.com")
        self.assertEqual(relay.env, {"ANTHROPIC_DEFAULT_OPUS_MODEL": "m"})
        api = code_config.account_from_env(
            {"ANTHROPIC_BASE_URL": "https://x", "ANTHROPIC_API_KEY": "sk"}
        )
        self.assertIs(api.auth_type, models.AuthType.API_KEY)
        self.assertEqual(
            code_config.provider_env_for(api),
            {"ANTHROPIC_BASE_URL": "https://x", "ANTHROPIC_API_KEY": "sk"},
        )


class DesktopTest(fixtures.IsolatedClaudeTest):
    def test_process_classification(self):
        desktop = (
            "C:\\Program Files\\WindowsApps\\Claude_2.7032.0.0_x64__pzs8"
            "sxrjxfjjc\\app\\Claude.exe"
        )
        bundled = (
            "C:\\Users\\me\\AppData\\Roaming\\Claude\\claude-code\\2.1.280"
            "\\claude.exe"
        )
        cli = "C:\\Users\\me\\.local\\bin\\claude.exe"
        squirrel = (
            "C:\\Users\\me\\AppData\\Local\\AnthropicClaude\\app-0.9.1"
            "\\claude.exe"
        )
        self.assertTrue(claude_desktop.is_desktop_executable(desktop))
        self.assertTrue(claude_desktop.is_desktop_executable(squirrel))
        self.assertFalse(claude_desktop.is_desktop_executable(bundled))
        self.assertFalse(claude_desktop.is_desktop_executable(cli))
        self.assertFalse(
            claude_desktop.is_desktop_executable("C:\\Windows\\explorer.exe")
        )

    def test_data_dir_override_and_readers(self):
        self.assertEqual(claude_desktop.data_dir(), self.desktop_dir)
        self.login_desktop("alice")
        fixtures.write_json(
            self.desktop_dir / "plan-usage-history.json",
            {
                "version": 2,
                "samples": [
                    {"t": 2000, "org": "org-a", "u": {"fh": 5, "sd": 10}},
                    {"t": 1000, "org": "org-a", "u": {"fh": 1, "sd": 9}},
                    {"t": "bad"},
                ],
            },
        )
        fixtures.write_json(
            self.desktop_dir / "claude_desktop_config.json",
            {"mcpServers": {"fs": {"command": "npx"}, "bad": 1}},
        )
        samples = claude_desktop.read_samples(self.desktop_dir)
        self.assertEqual([s.usage["fh"] for s in samples], [1, 5])
        self.assertEqual(
            list(claude_desktop.read_mcp_servers(self.desktop_dir)), ["fs"]
        )
        self.assertTrue(claude_desktop.is_logged_in(self.desktop_dir))
        self.assertEqual(
            claude_desktop.current_account_uuid(self.desktop_dir), "uuid-alice"
        )

    def test_snapshot_and_restore_swap_only_session(self):
        self.login_desktop("alice")
        snapshot = self.root / "snap-alice"
        size = claude_desktop.snapshot_session(self.desktop_dir, snapshot)
        self.assertGreater(size, 0)
        self.login_desktop("bob")
        config = self.desktop_config()
        config["userThemeMode"] = "light"  # 切换期间改过的普通设置
        fixtures.write_json(self.desktop_dir / "config.json", config)
        claude_desktop.restore_session(snapshot, self.desktop_dir)
        restored = self.desktop_config()
        self.assertEqual(self.cookies(), "cookies-alice")
        self.assertEqual(restored["lastKnownAccountUuid"], "uuid-alice")
        self.assertEqual(restored["oauth:tokenCache"], "encrypted-alice")
        self.assertNotIn("dxt:allowlistEnabled:org-bob", restored)
        self.assertEqual(restored["userThemeMode"], "light")
        self.assertTrue((self.desktop_dir / "claude-code").is_dir())
        leftovers = list(self.root.glob(".claude-status-trash-*"))
        self.assertEqual(leftovers, [])

    def test_restore_rolls_back_on_failure(self):
        self.login_desktop("alice")
        snapshot = self.root / "snap"
        claude_desktop.snapshot_session(self.desktop_dir, snapshot)
        self.login_desktop("bob")
        original_copy = claude_desktop._copy  # pylint: disable=protected-access

        def failing_copy(source, target):
            if source.name == "Local Storage":
                raise OSError("disk full")
            original_copy(source, target)

        with mock.patch.object(claude_desktop, "_copy", failing_copy):
            with self.assertRaises(OSError):
                claude_desktop.restore_session(snapshot, self.desktop_dir)
        self.assertEqual(self.cookies(), "cookies-bob")
        self.assertEqual(
            self.desktop_config()["lastKnownAccountUuid"], "uuid-bob"
        )
        ls = self.desktop_dir / "Local Storage" / "leveldb" / "000.log"
        self.assertEqual(ls.read_text(), "ls-bob")

    def test_clear_session_keeps_key_and_global_data(self):
        self.login_desktop("alice")
        claude_desktop.clear_session(self.desktop_dir)
        self.assertFalse((self.desktop_dir / "Network").exists())
        self.assertTrue((self.desktop_dir / "Local State").exists())
        self.assertTrue((self.desktop_dir / "claude-code").is_dir())
        config = self.desktop_config()
        self.assertNotIn("oauth:tokenCache", config)
        self.assertNotIn("lastKnownAccountUuid", config)
        self.assertEqual(config["userThemeMode"], "dark")
        self.assertFalse(claude_desktop.is_logged_in(self.desktop_dir))


class SwitcherTest(fixtures.IsolatedClaudeTest):
    def setUp(self):
        super().setUp()
        self.vault = vault_module.Vault(self.data_dir / "vault")
        self.running = False
        self.switcher = switcher_module.Switcher(
            self.vault, self.data_dir / "backups", lambda: self.running
        )
        self.alice = models.Account(
            name="Alice", email="alice@example.com", claude_uuid="uuid-alice"
        )
        self.bob = models.Account(name="Bob", email="bob@example.com")
        self.relay = models.Account(
            name="Relay",
            plan=models.Plan.API,
            auth_type=models.AuthType.RELAY,
            base_url="https://relay.example.com",
            api_key="relay-token",
            env={"ANTHROPIC_DEFAULT_OPUS_MODEL": "relay-opus"},
        )
        self.accounts = [self.alice, self.bob, self.relay]

    def test_vault_encrypts_code_login(self):
        self.login_code("alice")
        login = code_config.read_code_login()
        self.vault.save_code(self.alice.id, login)
        raw = (self.vault.root / self.alice.id / "code.bin").read_bytes()
        if code_config.storage.secure.available():
            self.assertNotIn(b"access-alice", raw)
        self.assertEqual(self.vault.load_code(self.alice.id), login)
        self.assertEqual(
            self.vault.code_meta(self.alice.id)["email"], "alice@example.com"
        )

    def test_oauth_switch_saves_current_login_and_is_undoable(self):
        self.login_code("bob")
        bob_login = code_config.read_code_login()
        self.vault.save_code(self.bob.id, bob_login)
        self.login_code("alice")
        self.set_settings(env={"CLAUDE_CODE_EFFORT_LEVEL": "high"})
        result = self.switcher.switch_code(self.bob, self.accounts)
        self.assertEqual(self.live_email(), "bob@example.com")
        # 切换前的 alice 登录（含最新令牌）已保存到 alice 名下。
        self.assertEqual(
            self.vault.load_code(self.alice.id).access_token, "access-alice"
        )
        self.assertEqual(result.preserved.created, [])
        self.assertEqual(
            self.settings()["env"], {"CLAUDE_CODE_EFFORT_LEVEL": "high"}
        )
        self.switcher.restore_code_state(result.backup)
        self.assertEqual(self.live_email(), "alice@example.com")

    def test_relay_switch_imports_unknown_config_first(self):
        self.login_code("alice")
        manual = {
            "ANTHROPIC_BASE_URL": "https://manual.example.com",
            "ANTHROPIC_AUTH_TOKEN": "manual-token",
            "ANTHROPIC_DEFAULT_OPUS_MODEL": "manual-opus",
        }
        self.set_settings(env={**manual, "CLAUDE_CODE_EFFORT_LEVEL": "low"})
        result = self.switcher.switch_code(self.relay, self.accounts)
        env = self.settings()["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://relay.example.com")
        self.assertEqual(env["ANTHROPIC_AUTH_TOKEN"], "relay-token")
        self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "relay-opus")
        self.assertEqual(env["CLAUDE_CODE_EFFORT_LEVEL"], "low")
        created = result.preserved.created
        self.assertEqual(len(created), 1)
        self.assertEqual(code_config.provider_env_for(created[0]), manual)
        # 订阅登录（alice）也被保存，之后可以切回。
        self.assertTrue(self.vault.has_code(self.alice.id))
        switched_back = self.switcher.switch_code(
            self.alice, self.accounts + created
        )
        self.assertNotIn("ANTHROPIC_BASE_URL", self.settings()["env"])
        self.assertEqual(self.live_email(), "alice@example.com")
        # 中转配置与账号一致，不会重复新建账号。
        self.assertEqual(switched_back.preserved.created, [])

    def test_relay_extras_synced_back_before_switching_away(self):
        env = code_config.provider_env_for(self.relay)
        env["ANTHROPIC_DEFAULT_OPUS_MODEL"] = "edited-by-hand"
        self.set_settings(env=env)
        self.login_code("alice")
        self.vault.save_code(self.alice.id, code_config.read_code_login())
        result = self.switcher.switch_code(self.alice, self.accounts)
        self.assertIn(self.relay, result.preserved.updated)
        self.assertEqual(
            self.relay.env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "edited-by-hand"
        )

    def test_oauth_target_without_saved_login_is_rejected(self):
        self.login_code("alice")
        ready, reason = self.switcher.code_ready(self.bob, self.accounts)
        self.assertFalse(ready)
        self.assertIn("claude /login", reason)
        with self.assertRaises(switcher_module.SwitchError):
            self.switcher.switch_code(self.bob, self.accounts)
        self.assertEqual(list((self.data_dir / "backups").glob("*")), [])
        # 当前登录的账号即使没保存过也可以"切换"（只移除中转配置）。
        self.assertTrue(self.switcher.code_ready(self.alice, self.accounts)[0])

    def test_unknown_login_becomes_new_account(self):
        self.login_code("carol")
        owner, created = self.switcher.capture_code(self.accounts)
        self.assertTrue(created)
        self.assertEqual(owner.email, "carol@example.com")
        self.assertEqual(owner.claude_uuid, "uuid-carol")
        self.assertTrue(self.vault.has_code(owner.id))
        again, created_again = self.switcher.capture_code(
            self.accounts + [owner]
        )
        self.assertIs(again, owner)
        self.assertFalse(created_again)

    def test_desktop_switch_round_trip(self):
        self.login_desktop("alice")
        self.switcher.capture_desktop(self.alice, self.desktop_dir)
        self.login_desktop("bob")
        self.switcher.capture_desktop(self.bob, self.desktop_dir)
        self.assertEqual(self.bob.claude_uuid, "uuid-bob")
        result = self.switcher.switch_desktop(
            self.alice, self.accounts, self.desktop_dir
        )
        self.assertIs(result.previous, self.bob)
        self.assertEqual(self.cookies(), "cookies-alice")
        self.assertEqual(
            self.desktop_config()["lastKnownAccountUuid"], "uuid-alice"
        )
        self.switcher.switch_desktop(self.bob, self.accounts, self.desktop_dir)
        self.assertEqual(self.cookies(), "cookies-bob")

    def test_desktop_guards(self):
        self.login_desktop("alice")
        self.running = True
        with self.assertRaises(switcher_module.SwitchError):
            self.switcher.capture_desktop(self.alice, self.desktop_dir)
        self.running = False
        other = models.Account(name="Other", claude_uuid="uuid-other")
        with self.assertRaises(switcher_module.SwitchError):
            self.switcher.capture_desktop(other, self.desktop_dir)
        self.switcher.capture_desktop(
            other, self.desktop_dir, allow_mismatch=True
        )
        with self.assertRaises(switcher_module.SwitchError):
            self.switcher.switch_desktop(
                self.bob, self.accounts, self.desktop_dir
            )

    def test_unknown_desktop_session_is_backed_up(self):
        self.login_desktop("alice")
        self.switcher.capture_desktop(self.alice, self.desktop_dir)
        self.login_desktop("stranger")
        result = self.switcher.switch_desktop(
            self.alice, self.accounts, self.desktop_dir
        )
        self.assertIsNone(result.previous)
        backup = result.unassigned_backup
        self.assertTrue((backup / "Network" / "Cookies").exists())
        account = json.loads((backup / "account.json").read_text())
        self.assertEqual(account["lastKnownAccountUuid"], "uuid-stranger")

    def test_new_desktop_login_stashes_and_clears(self):
        self.login_desktop("alice")
        self.alice.claude_uuid = "uuid-alice"
        self.switcher.new_desktop_login(self.accounts, self.desktop_dir)
        self.assertTrue(self.vault.has_desktop(self.alice.id))
        self.assertFalse(claude_desktop.is_logged_in(self.desktop_dir))

    def test_trash_and_untrash(self):
        self.login_code("alice")
        self.vault.save_code(self.alice.id, code_config.read_code_login())
        location = self.vault.trash(self.alice.id)
        self.assertFalse(self.vault.has_code(self.alice.id))
        self.vault.untrash(location, self.alice.id)
        self.assertTrue(self.vault.has_code(self.alice.id))
        self.vault.trash(self.alice.id)
        self.vault.purge_trash(dt.datetime.now() + dt.timedelta(days=2))
        self.assertEqual(
            list((self.vault.root / vault_module.TRASH_NAME).iterdir()), []
        )
