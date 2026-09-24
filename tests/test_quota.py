"""额度解析、联网获取与令牌刷新测试（网络请求用假的 opener 模拟）。"""

import datetime as dt
import io
import json
import unittest
import urllib.error

from claude_status import quota
from claude_status import secure

NOW = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _opener(payload=None, error=None, seen=None):
    def open_(request, timeout):
        if seen is not None:
            seen.append((request, timeout))
        if error is not None:
            raise error
        return _Response(json.dumps(payload).encode("utf-8"))

    return open_


class ParseTest(unittest.TestCase):
    def test_limits_format(self):
        payload = {
            "limits": [
                {
                    "kind": "session",
                    "percent": 38,
                    "resets_at": "2026-09-24T14:00:00+00:00",
                },
                {"kind": "weekly_all", "percent": 56, "resets_at": None},
                {
                    "kind": "weekly_scoped",
                    "percent": 12,
                    "is_active": True,
                    "scope": {"model": {"display_name": "Fable"}},
                },
                {"kind": "weekly_scoped", "percent": 0, "is_active": False},
            ],
            # 同时存在旧字段时以 limits 为准。
            "five_hour": {"utilization": 99},
        }
        result = quota.parse_usage(payload, NOW)
        self.assertEqual(result.five_hour.percent, 38)
        self.assertEqual(
            result.five_hour.resets_at, dt.datetime(2026, 9, 24, 14, tzinfo=dt.UTC)
        )
        self.assertEqual(result.seven_day.percent, 56)
        self.assertEqual([w.label for w in result.scoped], ["Fable"])
        self.assertEqual(result.source, quota.Source.API)

    def test_legacy_format(self):
        payload = {
            "five_hour": {"utilization": 4.5, "resets_at": "2026-09-24T15:00:00Z"},
            "seven_day": {"utilization": 56},
            "seven_day_opus": {"utilization": 20},
            "seven_day_sonnet": {"utilization": 0},
        }
        result = quota.parse_usage(payload, NOW)
        self.assertEqual(result.five_hour.percent, 4.5)
        self.assertIsNotNone(result.five_hour.resets_at)
        self.assertEqual(result.seven_day.percent, 56)
        self.assertEqual([w.label for w in result.scoped], ["Opus"])

    def test_state_accounts_for_resets(self):
        result = quota.parse_usage(
            {
                "five_hour": {
                    "utilization": 80,
                    "resets_at": "2026-09-24T11:00:00Z",
                },
                "seven_day": {"utilization": 40},
            },
            NOW - dt.timedelta(days=8),
        )
        five = result.state(result.five_hour, quota.FIVE_HOURS, NOW)
        self.assertTrue(five.reset)
        self.assertEqual(five.percent, 0)
        # 没有重置时间、采样超过一周：视为已重置。
        week = result.state(result.seven_day, quota.ONE_WEEK, NOW)
        self.assertTrue(week.reset)
        fresh = result.state(
            result.seven_day, quota.ONE_WEEK, NOW - dt.timedelta(days=7, hours=1)
        )
        self.assertFalse(fresh.reset)
        self.assertEqual(fresh.percent, 40)

    def test_desktop_and_cache_sources(self):
        sample = quota.from_desktop_sample({"fh": 12, "sd": 31}, 1790249372838)
        self.assertEqual(sample.source, quota.Source.DESKTOP)
        self.assertEqual(
            (sample.five_hour.percent, sample.seven_day.percent), (12, 31)
        )
        cache = {
            "fetchedAtMs": 1786536445577,
            "accountUuid": "u1",
            "utilization": {"five_hour": {"utilization": 4}},
        }
        account, parsed = quota.from_claude_code_cache(cache)
        self.assertEqual(account, "u1")
        self.assertEqual(parsed.source, quota.Source.CLAUDE_CODE)
        self.assertIsNone(quota.from_claude_code_cache({"accountUuid": 1}))

    def test_roundtrip_and_newest(self):
        original = quota.parse_usage(
            {
                "five_hour": {"utilization": 1, "resets_at": "2026-09-24T15:00:00Z"},
                "seven_day_opus": {"utilization": 3},
            },
            NOW,
        )
        restored = quota.Quota.from_dict(
            json.loads(json.dumps(original.to_dict()))
        )
        self.assertEqual(restored, original)
        older = quota.from_desktop_sample({"fh": 1}, 1)
        self.assertIs(quota.newest(older, None, original), original)
        self.assertIsNone(quota.Quota.from_dict({"source": "nope"}))


class NetworkTest(unittest.TestCase):
    def test_fetch_sends_oauth_headers(self):
        seen = []
        data = quota.fetch_usage(
            "token-123", _opener({"five_hour": {"utilization": 5}}, seen=seen)
        )
        self.assertEqual(data["five_hour"]["utilization"], 5)
        request, _timeout = seen[0]
        self.assertEqual(request.full_url, quota.USAGE_URL)
        self.assertEqual(request.get_header("Authorization"), "Bearer token-123")
        self.assertEqual(request.get_header("Anthropic-beta"), quota.OAUTH_BETA)

    def test_errors_are_classified(self):
        unauthorized = urllib.error.HTTPError(
            quota.USAGE_URL, 401, "Unauthorized", {}, None
        )
        with self.assertRaises(quota.QuotaError) as caught:
            quota.fetch_usage("t", _opener(error=unauthorized))
        self.assertEqual(caught.exception.kind, "auth")
        with self.assertRaises(quota.QuotaError) as caught:
            quota.fetch_usage("t", _opener(error=urllib.error.URLError("down")))
        self.assertEqual(caught.exception.kind, "network")

    def test_refresh_matches_official_request_format(self):
        seen = []
        oauth = {
            "accessToken": "old",
            "refreshToken": "r-old",
            "expiresAt": 1,
            "scopes": ["user:inference", "user:profile"],
            "subscriptionType": "max",
        }
        updated = quota.refresh_oauth(
            oauth,
            _opener(
                {
                    "access_token": "new",
                    "refresh_token": "r-new",
                    "expires_in": 3600,
                },
                seen=seen,
            ),
        )
        request, _timeout = seen[0]
        self.assertEqual(request.full_url, quota.TOKEN_URL)
        self.assertEqual(request.get_method(), "POST")
        body = json.loads(request.data)
        self.assertEqual(
            body,
            {
                "grant_type": "refresh_token",
                "refresh_token": "r-old",
                "client_id": quota.CLIENT_ID,
                "scope": "user:inference user:profile",
            },
        )
        self.assertEqual(updated["accessToken"], "new")
        self.assertEqual(updated["refreshToken"], "r-new")
        self.assertGreater(updated["expiresAt"], 1)
        self.assertEqual(updated["subscriptionType"], "max")
        with self.assertRaises(quota.QuotaError):
            quota.refresh_oauth({"accessToken": "x"}, _opener({}))


class SecureTest(unittest.TestCase):
    def test_roundtrip(self):
        blob = secure.protect(b"secret-value")
        self.assertNotIn(b"secret-value", blob if secure.available() else b"")
        self.assertEqual(secure.unprotect(blob), b"secret-value")
        text = secure.protect_text("令牌 sk-ant-1")
        self.assertTrue(text.startswith(secure.TEXT_PREFIX))
        self.assertEqual(secure.unprotect_text(text), "令牌 sk-ant-1")
        self.assertEqual(secure.unprotect_text("legacy"), "legacy")
        self.assertEqual(secure.protect_text(""), "")
        with self.assertRaises(secure.SecureError):
            secure.unprotect(b"garbage")


if __name__ == "__main__":
    unittest.main()
