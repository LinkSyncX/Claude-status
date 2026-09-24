"""定价与模型名规范化测试。"""

import datetime as dt
import unittest

from claude_status import models
from claude_status import pricing

NOW = dt.datetime(2026, 9, 1, 12, tzinfo=dt.UTC)


def _record(model: str, **tokens: int) -> models.UsageRecord:
    return models.UsageRecord(timestamp=NOW, model=model, **tokens)


class NormalizeModelTest(unittest.TestCase):
    def test_strips_platform_decorations(self):
        cases = {
            "claude-sonnet-4-20250514": "claude-sonnet-4",
            "us.anthropic.claude-sonnet-4-20250514-v1:0": "claude-sonnet-4",
            "apac.anthropic.claude-haiku-4-5-20251001-v1:0": "claude-haiku-4-5",
            "claude-opus-4-5@20251101": "claude-opus-4-5",
            "claude-opus-4-6[1m]": "claude-opus-4-6",
            "anthropic/claude-sonnet-4.5": "claude-sonnet-4-5",
            "Claude-Opus-5": "claude-opus-5",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(pricing.normalize_model(raw), expected)

    def test_non_claude_models_are_left_alone(self):
        self.assertEqual(pricing.normalize_model("gpt-5.6-sol"), "gpt-5.6-sol")

    def test_family(self):
        self.assertEqual(pricing.model_family("claude-opus-5-5"), "Opus")
        self.assertEqual(pricing.model_family("claude-3-5-haiku"), "Haiku")
        self.assertEqual(pricing.model_family("claude-fable-5-1"), "Fable")
        self.assertEqual(pricing.model_family("grok-4.6"), "其他")


class PriceBookTest(unittest.TestCase):
    def setUp(self):
        self.book = pricing.PriceBook()

    def test_exact_and_prefix_lookup(self):
        self.assertEqual(self.book.lookup("claude-opus-5").input, 5.0)
        self.assertEqual(self.book.lookup("claude-opus-5-5").input, 4.0)
        # 旧别名 claude-opus-4-0 回落到 claude-opus-4 的价格。
        self.assertEqual(self.book.lookup("claude-opus-4-0").input, 15.0)
        dated = self.book.lookup("claude-opus-4-1-20250805")
        self.assertEqual(dated.output, 75.0)

    def test_prefix_requires_separator(self):
        self.assertIsNone(self.book.lookup("claude-opus-40"))

    def test_unknown_model_has_no_price(self):
        self.assertIsNone(self.book.lookup("grok-4.6"))
        self.assertIsNone(self.book.cost(_record("grok-4.6", output_tokens=10)))

    def test_cost_includes_cache_multipliers(self):
        record = _record(
            "claude-sonnet-5",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_write_5m=1_000_000,
            cache_write_1h=1_000_000,
            cache_read=1_000_000,
        )
        # 2 + 10 + 2×1.25 + 2×2 + 0.2
        self.assertAlmostEqual(self.book.cost(record), 18.7)

    def test_model_specific_cache_read(self):
        record = _record("claude-fable-5-1", cache_read=1_000_000)
        self.assertAlmostEqual(self.book.cost(record), 0.25)

    def test_custom_price_overrides_builtin_and_prices_unknown(self):
        book = pricing.PriceBook(
            {
                "grok-4.6": models.CustomPrice(1.0, 2.0),
                "claude-opus-5": models.CustomPrice(1.0, 1.0, 0.5),
            }
        )
        grok = book.cost(
            _record("grok-4.6", input_tokens=500_000, cache_read=10**6)
        )
        self.assertAlmostEqual(grok, 0.5 + 0.1)
        self.assertTrue(book.lookup("claude-opus-5").custom)
        self.assertEqual(book.rows()[0][0], "claude-opus-5")


if __name__ == "__main__":
    unittest.main()
