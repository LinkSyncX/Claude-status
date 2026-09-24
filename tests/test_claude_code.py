"""Claude Code 日志解析测试（使用临时目录中的合成日志）。"""

import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

from claude_status import claude_code
from claude_status import models


def _assistant(
    message_id: str,
    output: int,
    timestamp: str = "2026-09-01T10:00:00.000Z",
    model: str = "claude-opus-5",
    **usage,
) -> str:
    body = {
        "input_tokens": 10,
        "output_tokens": output,
        "cache_creation_input_tokens": usage.pop("total_write", 0),
        "cache_read_input_tokens": usage.pop("cache_read", 0),
    }
    body.update(usage)
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": timestamp,
            "sessionId": "s1",
            "cwd": "F:\\work\\demo-app",
            "requestId": "req_" + message_id,
            "message": {
                "id": message_id,
                "model": model,
                "role": "assistant",
                "content": [{"type": "text", "text": "内容不应被读取"}],
                "usage": body,
            },
        }
    )


class ParseLineTest(unittest.TestCase):
    def test_skips_non_usage_lines(self):
        self.assertIsNone(claude_code.parse_line('{"type": "user"}'))
        self.assertIsNone(claude_code.parse_line("not json but has \"usage\""))

    def test_skips_synthetic_messages(self):
        line = _assistant("m1", 5, model="<synthetic>")
        self.assertIsNone(claude_code.parse_line(line))

    def test_splits_cache_creation_by_ttl(self):
        line = _assistant(
            "m1",
            5,
            total_write=300,
            cache_read=40,
            cache_creation={
                "ephemeral_5m_input_tokens": 100,
                "ephemeral_1h_input_tokens": 200,
            },
        )
        key, entry = claude_code.parse_line(line)
        self.assertEqual(key, "m1")
        self.assertEqual(entry.cache_write_5m, 100)
        self.assertEqual(entry.cache_write_1h, 200)
        self.assertEqual(entry.cache_read, 40)
        self.assertEqual(entry.project, "demo-app")
        self.assertEqual(entry.timestamp.utcoffset() is not None, True)

    def test_legacy_total_counts_as_5m(self):
        line = _assistant("m1", 5, total_write=70)
        _key, entry = claude_code.parse_line(line)
        self.assertEqual((entry.cache_write_5m, entry.cache_write_1h), (70, 0))


class ScannerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        project = self.root / "F--work-demo-app"
        (project / "subagents").mkdir(parents=True)
        # 同一条消息被拆成多行（输出 token 递增），另一文件中又被续接会话复制。
        (project / "a.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"type": "user", "message": {"content": "hi"}}),
                    _assistant("m1", 3, timestamp="2026-09-01T10:00:01Z"),
                    _assistant("m1", 9, timestamp="2026-09-01T10:00:02Z"),
                    _assistant("m2", 4, timestamp="2026-09-02T08:00:00Z"),
                    "{broken json",
                ]
            ),
            encoding="utf-8",
        )
        (project / "subagents" / "b.jsonl").write_text(
            _assistant("m1", 9) + "\n" + _assistant("m3", 1, model="grok-4.6"),
            encoding="utf-8",
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_deduplicates_across_lines_and_files(self):
        result = claude_code.LogScanner().scan(self.root)
        self.assertEqual(result.files, 2)
        self.assertEqual(result.rows, 5)
        self.assertEqual(result.duplicates, 2)
        self.assertEqual(len(result.records), 3)
        first = result.records[0]
        self.assertEqual(first.output_tokens, 9)
        self.assertEqual(first.requests, 1)
        self.assertLessEqual(result.first, result.last)

    def test_rescan_uses_cache_and_picks_up_changes(self):
        scanner = claude_code.LogScanner()
        scanner.scan(self.root)
        log = self.root / "F--work-demo-app" / "a.jsonl"
        with log.open("a", encoding="utf-8") as stream:
            stream.write("\n" + _assistant("m9", 2))
        self.assertEqual(len(scanner.scan(self.root).records), 4)

    def test_missing_directory(self):
        result = claude_code.LogScanner().scan(self.root / "nope")
        self.assertFalse(result.exists)
        self.assertEqual(result.records, [])

    def test_config_dir_env(self):
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.root)}):
            self.assertEqual(
                claude_code.default_projects_dir(), self.root / "projects"
            )
            self.assertEqual(
                claude_code.global_state_path(), self.root / ".claude.json"
            )


class LocalLoginTest(unittest.TestCase):
    def _write(self, data) -> pathlib.Path:
        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False, encoding="utf-8"
        )
        with handle:
            json.dump(data, handle)
        self.addCleanup(os.unlink, handle.name)
        return pathlib.Path(handle.name)

    def test_reads_account_and_matching_utilization(self):
        path = self._write(
            {
                "oauthAccount": {
                    "accountUuid": "u1",
                    "emailAddress": "me@example.com",
                    "displayName": "Me",
                    "organizationName": "Org",
                    "organizationType": "claude_max",
                    "userRateLimitTier": "default_claude_max_20x",
                },
                "cachedUsageUtilization": {
                    "accountUuid": "u1",
                    "fetchedAtMs": 1786536445577,
                    "utilization": {
                        "five_hour": {"utilization": 4, "resets_at": None},
                        "seven_day": {
                            "utilization": 56,
                            "resets_at": "2026-08-17T03:00:00+00:00",
                        },
                    },
                },
            }
        )
        login = claude_code.read_local_login(path)
        self.assertEqual(login.email, "me@example.com")
        self.assertEqual(login.plan, models.Plan.MAX_20X)
        self.assertEqual((login.five_hour, login.seven_day), (4.0, 56.0))
        self.assertIsNotNone(login.seven_day_resets)

    def test_ignores_utilization_of_other_account(self):
        path = self._write(
            {
                "oauthAccount": {
                    "accountUuid": "u1",
                    "emailAddress": "me@example.com",
                    "organizationType": "claude_pro",
                },
                "cachedUsageUtilization": {
                    "accountUuid": "someone-else",
                    "utilization": {"five_hour": {"utilization": 90}},
                },
            }
        )
        login = claude_code.read_local_login(path)
        self.assertEqual(login.plan, models.Plan.PRO)
        self.assertIsNone(login.five_hour)

    def test_not_logged_in(self):
        self.assertIsNone(claude_code.read_local_login(self._write({})))
        self.assertIsNone(
            claude_code.read_local_login(pathlib.Path("does-not-exist.json"))
        )


if __name__ == "__main__":
    unittest.main()
