"""持久化、导入导出与演示数据测试。"""

import datetime as dt
import json
import pathlib
import tempfile
import unittest

from claude_status import demo_data
from claude_status import models
from claude_status import storage


class StoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = pathlib.Path(self._tmp.name)
        self.store = storage.Store(self.dir)

    def tearDown(self):
        self._tmp.cleanup()

    def test_first_run(self):
        result = self.store.load()
        self.assertFalse(result.existed)
        self.assertTrue(result.settings.first_run)

    def test_roundtrip(self):
        account = models.Account(
            name="主号",
            email="a@example.com",
            plan=models.Plan.MAX_5X,
            auth_type=models.AuthType.RELAY,
            api_key="sk-ant-123456789",
            tags=["工作"],
            monthly_budget=12.5,
        )
        settings = models.Settings(
            data_source=models.DataSource.DEMO,
            dark=True,
            active_account_id=account.id,
            custom_prices={"grok-4.6": models.CustomPrice(1, 2, None)},
            first_run=False,
        )
        self.store.save([account], settings)
        self.store.save([account], settings)
        self.assertTrue((self.dir / "config.json.bak").exists())
        loaded = self.store.load()
        self.assertTrue(loaded.existed)
        self.assertEqual(loaded.accounts, [account])
        self.assertEqual(loaded.settings.to_dict(), settings.to_dict())

    def test_corrupt_file_is_quarantined(self):
        self.store.path.write_text("{oops", encoding="utf-8")
        result = self.store.load()
        self.assertEqual(result.accounts, [])
        self.assertIn("无法读取", result.warning)
        self.assertFalse(self.store.path.exists())
        self.assertTrue(any(self.dir.glob("config.json.corrupt-*")))

    def test_unknown_enum_values_fall_back(self):
        account = models.Account.from_dict(
            {"name": "x", "plan": "platinum", "status": "??", "tags": None}
        )
        self.assertEqual(account.plan, models.Plan.PRO)
        self.assertEqual(account.status, models.AccountStatus.ACTIVE)
        self.assertEqual(account.tags, [])


class ExportMergeTest(unittest.TestCase):
    def test_export_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "out.json"
            account = models.Account(name="k", api_key="secret-value-123")
            storage.export_accounts(path, [account], include_secrets=False)
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["format"], storage.EXPORT_FORMAT)
            self.assertEqual(data["accounts"][0]["api_key"], "")
            self.assertEqual(storage.read_export(path)[0].name, "k")

    def test_merge_by_id_and_email(self):
        local = models.Account(
            name="旧名", email="A@example.com", api_key="keep", link_local=True
        )
        other = models.Account(name="其他", email="b@example.com")
        incoming = [
            models.Account(name="新名", email="a@example.com"),
            models.Account(id=other.id, name="其他-改"),
            models.Account(name="全新", email="c@example.com", link_local=True),
        ]
        result = storage.merge_accounts([local, other], incoming)
        self.assertEqual((result.added, result.updated), (1, 2))
        names = [account.name for account in result.accounts]
        self.assertEqual(names, ["新名", "其他-改", "全新"])
        merged = result.accounts[0]
        self.assertEqual(merged.id, local.id)
        self.assertEqual(merged.api_key, "keep")
        self.assertTrue(merged.link_local)
        self.assertFalse(result.accounts[2].link_local)


class DemoDataTest(unittest.TestCase):
    def test_deterministic_and_respects_status(self):
        accounts = demo_data.sample_accounts()
        # 演示数据以账号 ID 为随机种子：固定 ID 使测试结果确定。
        for index, account in enumerate(accounts):
            account.id = f"sample-{index}"
        now = dt.datetime(2026, 9, 24, 15, 30, tzinfo=dt.UTC)
        today = now.date()
        first = demo_data.generate(accounts, days=365, now=now)
        second = demo_data.generate(accounts, days=365, now=now)
        self.assertTrue(
            all(r.timestamp <= now.replace(minute=59) for r in first)
        )
        self.assertEqual(first, second)
        self.assertTrue(first)
        expired = next(
            a for a in accounts if a.status is models.AccountStatus.EXPIRED
        )
        last_expired = max(
            (r.day for r in first if r.account_id == expired.id), default=None
        )
        self.assertIsNotNone(last_expired)
        self.assertLess(last_expired, today - dt.timedelta(days=40))
        self.assertTrue(all(r.day <= today for r in first))
        self.assertTrue(all(r.requests >= 1 for r in first))


if __name__ == "__main__":
    unittest.main()
