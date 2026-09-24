"""模型定价与费用估算。

单价为 Anthropic 官方 API 的一方价格（美元 / 百万 token，2026-06 版）。
缓存写入按输入单价的倍数计费：5 分钟缓存 1.25 倍、1 小时缓存 2 倍；
缓存读取单价按模型单列（多数模型为输入单价的 0.1 倍）。

订阅套餐（Pro / Max 等）并不按 token 计费，这里的金额只是"如果按 API
计价需要多少钱"的参考值。第三方中转或非 Claude 模型没有内置价格，可在
设置中添加自定义单价。
"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
import re

from claude_status import models

CACHE_WRITE_5M_MULTIPLIER = 1.25
CACHE_WRITE_1H_MULTIPLIER = 2.0
PER_MILLION = 1_000_000


@dataclasses.dataclass(frozen=True)
class ModelPrice:
    """一个模型的单价（美元 / 百万 token）。

    Attributes:
        input: 输入单价。
        output: 输出单价。
        cache_read: 缓存读取单价。
        display_name: 界面显示名。
        custom: 是否为用户自定义单价。
    """

    input: float
    output: float
    cache_read: float
    display_name: str = ""
    custom: bool = False

    @property
    def cache_write_5m(self) -> float:
        """5 分钟缓存写入单价。"""
        return self.input * CACHE_WRITE_5M_MULTIPLIER

    @property
    def cache_write_1h(self) -> float:
        """1 小时缓存写入单价。"""
        return self.input * CACHE_WRITE_1H_MULTIPLIER


def _price(
    name: str,
    input_price: float,
    output: float,
    cache_read: float | None = None,
) -> ModelPrice:
    return ModelPrice(
        input_price,
        output,
        input_price * 0.1 if cache_read is None else cache_read,
        name,
    )


# 按模型 ID 前缀匹配，越具体的前缀越靠前（匹配时按长度优先）。
BUILTIN_PRICES: dict[str, ModelPrice] = {
    "claude-fable-5-1": _price("Claude Fable 5.1", 10.0, 50.0, 0.25),
    "claude-mythos-5-1": _price("Claude Mythos 5.1", 10.0, 50.0, 0.25),
    "claude-fable-5": _price("Claude Fable 5", 10.0, 50.0, 1.0),
    "claude-mythos-5": _price("Claude Mythos 5", 10.0, 50.0, 1.0),
    "claude-opus-5-5": _price("Claude Opus 5.5", 4.0, 20.0, 0.2),
    "claude-opus-5": _price("Claude Opus 5", 5.0, 25.0),
    "claude-opus-4-8": _price("Claude Opus 4.8", 5.0, 25.0),
    "claude-opus-4-7": _price("Claude Opus 4.7", 5.0, 25.0),
    "claude-opus-4-6": _price("Claude Opus 4.6", 5.0, 25.0),
    "claude-opus-4-5": _price("Claude Opus 4.5", 5.0, 25.0),
    "claude-opus-4-1": _price("Claude Opus 4.1", 15.0, 75.0),
    "claude-opus-4": _price("Claude Opus 4", 15.0, 75.0),
    "claude-sonnet-5": _price("Claude Sonnet 5", 2.0, 10.0),
    "claude-sonnet-4-6": _price("Claude Sonnet 4.6", 3.0, 15.0),
    "claude-sonnet-4-5": _price("Claude Sonnet 4.5", 3.0, 15.0),
    "claude-sonnet-4": _price("Claude Sonnet 4", 3.0, 15.0),
    "claude-haiku-4-5": _price("Claude Haiku 4.5", 1.0, 5.0),
    "claude-3-7-sonnet": _price("Claude Sonnet 3.7", 3.0, 15.0),
    "claude-3-5-sonnet": _price("Claude Sonnet 3.5", 3.0, 15.0),
    "claude-3-opus": _price("Claude Opus 3", 15.0, 75.0),
    "claude-3-5-haiku": _price("Claude Haiku 3.5", 0.8, 4.0),
    "claude-3-haiku": _price("Claude Haiku 3", 0.25, 1.25, 0.03),
}

_DATE_SUFFIX = re.compile(r"[-@]\d{8}$")
_VERSION_SUFFIX = re.compile(r"-v\d+(:\d+)?$")
_BRACKET_SUFFIX = re.compile(r"\[[^\]]*\]$")
_PROVIDER_PREFIX = re.compile(r"^(?:[a-z]+\.)?anthropic[./]")


def normalize_model(model: str) -> str:
    """把各平台的模型名统一为官方别名。

    例如 ``us.anthropic.claude-sonnet-4-20250514-v1:0`` →
    ``claude-sonnet-4``、``claude-opus-4-6[1m]`` → ``claude-opus-4-6``、
    ``anthropic/claude-sonnet-4.5`` → ``claude-sonnet-4-5``。
    """
    name = model.strip().lower()
    name = _BRACKET_SUFFIX.sub("", name)
    name = _PROVIDER_PREFIX.sub("", name)
    name = _VERSION_SUFFIX.sub("", name)
    name = _DATE_SUFFIX.sub("", name)
    if name.startswith("claude"):
        name = name.replace(".", "-")
    return name


def model_family(model: str) -> str:
    """模型系列，用于配色与分组：Opus / Sonnet / Haiku / Fable / 其他。"""
    name = normalize_model(model)
    for family in ("fable", "mythos", "opus", "sonnet", "haiku"):
        if family in name and name.startswith("claude"):
            return family.capitalize()
    return "其他"


def display_name(model: str) -> str:
    """模型的界面显示名；未知模型原样返回。"""
    price = BUILTIN_PRICES.get(_match_builtin(normalize_model(model)) or "")
    return price.display_name if price is not None else model


def _match_builtin(name: str) -> str | None:
    if name in BUILTIN_PRICES:
        return name
    best: str | None = None
    for prefix in BUILTIN_PRICES:
        # 前缀之后必须是分隔符，避免 claude-opus-4 误匹配 claude-opus-40。
        if name.startswith(prefix) and name[len(prefix) : len(prefix) + 1] in (
            "",
            "-",
        ):
            if best is None or len(prefix) > len(best):
                best = prefix
    return best


class PriceBook:
    """价格表：内置单价 + 用户自定义单价（自定义优先，按原始名精确匹配）。"""

    def __init__(
        self, custom: Mapping[str, models.CustomPrice] | None = None
    ) -> None:
        self._custom: dict[str, ModelPrice] = {}
        for model, price in (custom or {}).items():
            cache_read = (
                price.cache_read
                if price.cache_read is not None
                else price.input * 0.1
            )
            self._custom[model.strip().lower()] = ModelPrice(
                price.input, price.output, cache_read, model, custom=True
            )

    def lookup(self, model: str) -> ModelPrice | None:
        """查找模型单价，未知模型返回 None。"""
        raw = model.strip().lower()
        if raw in self._custom:
            return self._custom[raw]
        normalized = normalize_model(model)
        if normalized in self._custom:
            return self._custom[normalized]
        key = _match_builtin(normalized)
        return BUILTIN_PRICES[key] if key is not None else None

    def cost(self, record: models.UsageRecord) -> float | None:
        """估算一条用量记录的费用（美元），未知模型返回 None。"""
        price = self.lookup(record.model)
        if price is None:
            return None
        return (
            record.input_tokens * price.input
            + record.output_tokens * price.output
            + record.cache_write_5m * price.cache_write_5m
            + record.cache_write_1h * price.cache_write_1h
            + record.cache_read * price.cache_read
        ) / PER_MILLION

    def rows(self) -> list[tuple[str, ModelPrice]]:
        """价格表中的全部条目（自定义在前）。"""
        custom = sorted(self._custom.items())
        return custom + list(BUILTIN_PRICES.items())
