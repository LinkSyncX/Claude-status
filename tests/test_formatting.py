"""格式化函数测试。"""

import datetime as dt
import unittest

from claude_status import formatting


class FormattingTest(unittest.TestCase):
    def test_tokens(self):
        cases = {
            0: "0",
            9_999: "9,999",
            12_345: "12.3K",
            500_000: "500K",
            999_949: "1M",
            1_234_567: "1.23M",
            56_400_000: "56.4M",
            607_400_000: "607M",
            100_000_000: "100M",
            2_890_000_000: "2.89B",
            -45_600: "-45.6K",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(formatting.tokens(value), expected)

    def test_money(self):
        self.assertEqual(formatting.money(None), "—")
        self.assertEqual(formatting.money(0), "$0")
        self.assertEqual(formatting.money(0.0042), "$0.0042")
        self.assertEqual(formatting.money(1234.5), "$1,234.50")
        self.assertEqual(formatting.money(25_300), "$25.3K")

    def test_delta(self):
        self.assertEqual(formatting.delta(None), "无上期数据")
        self.assertEqual(formatting.delta(0.0001), "与上期持平")
        self.assertEqual(formatting.delta(0.125), "↑ 12.5% 较上期")
        self.assertEqual(formatting.delta(-2.5), "↓ 250% 较上期")

    def test_relative(self):
        now = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC)
        ago = lambda **kw: now - dt.timedelta(**kw)  # noqa: E731
        self.assertEqual(formatting.relative(None, now), "从未")
        self.assertEqual(formatting.relative(ago(seconds=20), now), "刚刚")
        self.assertEqual(formatting.relative(ago(minutes=5), now), "5 分钟前")
        self.assertEqual(formatting.relative(ago(hours=3), now), "3 小时前")
        self.assertEqual(formatting.relative(ago(hours=30), now), "昨天")
        self.assertEqual(formatting.relative(ago(days=4), now), "4 天前")
        self.assertEqual(formatting.relative(ago(days=70), now), "2026-07-16")
        self.assertEqual(
            formatting.relative(ago(minutes=5).isoformat(), now), "5 分钟前"
        )

    def test_dates(self):
        day = dt.date(2026, 9, 24)
        self.assertEqual(formatting.date_short(day), "9月24日")
        self.assertEqual(formatting.date_full(day), "2026年9月24日 周四")
        self.assertEqual(formatting.date_axis(day), "9/24")

    def test_change_percent(self):
        self.assertEqual(formatting.change_percent(0.125), "12.5%")
        self.assertEqual(formatting.change_percent(-2.5), "250%")

    def test_join_cjk(self):
        self.assertEqual(formatting.join_cjk("按", "Token", "着色"), "按 Token 着色")
        self.assertEqual(formatting.join_cjk("各账号的", "费用"), "各账号的费用")
        self.assertEqual(
            formatting.join_cjk("按", "Token", "，共 4 个"), "按 Token，共 4 个"
        )
        self.assertEqual(formatting.join_cjk("", "Token"), "Token")

    def test_ago(self):
        now = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.UTC)
        self.assertEqual(formatting.ago(now, "采样", now), "刚刚采样")
        earlier = now - dt.timedelta(minutes=5)
        self.assertEqual(formatting.ago(earlier, "保存", now), "5 分钟前保存")
        old = now - dt.timedelta(days=90)
        self.assertEqual(formatting.ago(old, "保存", now), "2026-06-26 保存")
        self.assertEqual(formatting.ago(None, "保存", now), "从未保存")

    def test_time_labels(self):
        start = dt.datetime(2026, 9, 23, 22, 0)
        short = [start, start + dt.timedelta(hours=3)]
        self.assertEqual(formatting.time_labels(short), ["22:00", "01:00"])
        long = [start, start + dt.timedelta(days=2)]
        self.assertEqual(
            formatting.time_labels(long), ["09-23 22:00", "09-25 22:00"]
        )
        self.assertEqual(formatting.time_labels([]), [])


if __name__ == "__main__":
    unittest.main()
