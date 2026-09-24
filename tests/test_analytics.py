"""统计聚合测试。"""

import datetime as dt
import unittest

from claude_status import analytics
from claude_status import models

TZ = dt.timezone(dt.timedelta(hours=8))


def _record(day: int, hour: int = 10, **kwargs) -> models.UsageRecord:
    values = {"model": "claude-sonnet-5", "output_tokens": 100}
    values.update(kwargs)
    return models.UsageRecord(
        timestamp=dt.datetime(2026, 9, day, hour, tzinfo=TZ), **values
    )


class DatasetTest(unittest.TestCase):
    def setUp(self):
        self.records = [
            _record(1, account_id="a", cache_read=900, input_tokens=100),
            _record(1, 22, account_id="b", model="grok-4.6"),
            _record(3, account_id="a", model="claude-opus-5", requests=3),
            _record(7, account_id=None, project="docs"),
        ]
        self.data = analytics.Dataset(self.records)

    def test_totals_and_unpriced(self):
        totals = self.data.totals()
        self.assertEqual(totals.requests, 6)
        self.assertEqual(totals.total_tokens, 1400)
        self.assertEqual(totals.unpriced_tokens, 100)
        self.assertAlmostEqual(totals.cache_hit_rate, 0.9)
        self.assertGreater(totals.cost, 0)

    def test_filter_by_date_and_account(self):
        subset = self.data.filter(
            dt.date(2026, 9, 1), dt.date(2026, 9, 3), ["a"]
        )
        self.assertEqual(len(subset), 2)
        self.assertEqual(len(subset.costs), 2)
        unassigned = self.data.filter(account_ids=[None])
        self.assertEqual(len(unassigned), 1)

    def test_daily_fills_gaps(self):
        daily = self.data.daily(dt.date(2026, 9, 1), dt.date(2026, 9, 7))
        self.assertEqual(len(daily), 7)
        requests = [d.totals.requests for d in daily]
        self.assertEqual(requests, [2, 0, 3, 0, 0, 0, 1])

    def test_grouping_sorted_by_tokens(self):
        models_ = self.data.by_model()
        self.assertEqual(models_[0].key, "claude-sonnet-5")
        accounts = {g.key for g in self.data.by_account()}
        self.assertEqual(accounts, {"a", "b", None})
        families = {g.key for g in self.data.by_family()}
        self.assertEqual(families, {"Sonnet", "Opus", "其他"})

    def test_weekday_hour_matrix(self):
        matrix = self.data.weekday_hour(analytics.Metric.REQUESTS)
        # 2026-09-01 是周二。
        self.assertEqual(matrix[1][10], 1)
        self.assertEqual(matrix[1][22], 1)
        self.assertEqual(sum(map(sum, matrix)), 6)

    def test_bucket_weekly(self):
        daily = self.data.daily(dt.date(2026, 9, 1), dt.date(2026, 9, 7))
        weeks = analytics.bucket_weekly(daily)
        # 9/1–9/6 属于 8/31 开始的一周，9/7 是下一周的周一。
        self.assertEqual(
            [w.day for w in weeks], [dt.date(2026, 8, 31), dt.date(2026, 9, 7)]
        )
        self.assertEqual([w.totals.requests for w in weeks], [5, 1])

    def test_monthly_by_account(self):
        months = analytics.month_sequence(dt.date(2026, 9, 30), 3)
        self.assertEqual(months, [(2026, 7), (2026, 8), (2026, 9)])
        grid = self.data.monthly_by_account(months, analytics.Metric.REQUESTS)
        self.assertEqual(grid["a"], [0, 0, 4])

    def test_compare_previous_period(self):
        comparison = analytics.compare(
            self.data, dt.date(2026, 9, 4), dt.date(2026, 9, 7)
        )
        self.assertEqual(comparison.current.requests, 1)
        self.assertEqual(comparison.previous.requests, 5)
        self.assertAlmostEqual(
            comparison.delta(lambda totals: totals.requests), -0.8
        )
        self.assertEqual(comparison.days, 4)


class ActivityTest(unittest.TestCase):
    def test_streaks(self):
        start = dt.date(2026, 9, 1)
        values = {
            start + dt.timedelta(days=offset): 1.0 for offset in (0, 1, 2, 5, 6)
        }
        values[start + dt.timedelta(days=6)] = 9.0
        end = start + dt.timedelta(days=6)
        summary = analytics.activity(values, start, end)
        self.assertEqual(summary.active_days, 5)
        self.assertEqual(summary.longest_streak, 3)
        self.assertEqual(summary.longest_start, start)
        self.assertEqual(summary.current_streak, 2)
        self.assertEqual(summary.busiest_day, start + dt.timedelta(days=6))

    def test_current_streak_tolerates_quiet_today(self):
        start = dt.date(2026, 9, 1)
        values = {start: 1.0, start + dt.timedelta(days=1): 1.0}
        end = start + dt.timedelta(days=2)
        summary = analytics.activity(values, start, end)
        self.assertEqual(summary.current_streak, 2)

    def test_levels(self):
        thresholds = analytics.level_thresholds([0, 1, 2, 3, 4, 100])
        self.assertEqual(len(thresholds), 4)
        self.assertEqual(analytics.level_of(0, thresholds), 0)
        self.assertEqual(analytics.level_of(1, thresholds), 1)
        self.assertEqual(analytics.level_of(100, thresholds), 4)
        self.assertEqual(analytics.level_thresholds([0, 0]), [])


if __name__ == "__main__":
    unittest.main()
