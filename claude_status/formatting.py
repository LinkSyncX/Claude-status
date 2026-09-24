"""数字、金额与时间的中文格式化。"""

from __future__ import annotations

import datetime as dt

WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
WEEKDAYS_SHORT = ("一", "二", "三", "四", "五", "六", "日")


_UNITS = ((1e9, "B"), (1e6, "M"), (1e3, "K"))


def _significant(scaled: float) -> str:
    """保留 3 位有效数字并去掉多余的 0：``4.56`` / ``12.3`` / ``607``。"""
    magnitude = abs(scaled)
    digits = 2 if magnitude < 10 else 1 if magnitude < 100 else 0
    text = f"{scaled:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def tokens(value: float) -> str:
    """token 数量：``9,999`` / ``12.3K`` / ``4.56M`` / ``607M`` / ``1.2B``。

    1 万以下直接显示整数，避免 "1.23K" 这类读数；其余保留 3 位有效数字。
    """
    if abs(value) < 1e4:
        return f"{int(round(value)):,}"
    for index, (divisor, suffix) in enumerate(_UNITS):
        if abs(value) < divisor and suffix != "K":
            continue
        text = _significant(value / divisor)
        # 四舍五入进位到 1000 时改用更大的单位（999.95K → 1M）。
        if abs(float(text)) >= 1000 and index > 0:
            divisor, suffix = _UNITS[index - 1]
            text = _significant(value / divisor)
        return text + suffix
    return f"{int(round(value)):,}"


def count(value: float) -> str:
    """次数：带千分位。"""
    return f"{int(round(value)):,}"


def money(value: float | None) -> str:
    """美元金额；小额保留更多有效位，None 显示为破折号。"""
    if value is None:
        return "—"
    if value == 0:
        return "$0"
    if abs(value) < 0.01:
        return f"${value:.4f}"
    if abs(value) >= 10_000:
        return f"${value / 1000:,.1f}K"
    return f"${value:,.2f}"


def percent(fraction: float | None, digits: int = 1) -> str:
    """0–1 的比例格式化为百分数。"""
    if fraction is None:
        return "—"
    return f"{fraction * 100:.{digits}f}%"


def delta(fraction: float | None) -> str:
    """变化率：``↑ 12.5%`` / ``↓ 3%`` / ``持平``。"""
    if fraction is None:
        return "无上期数据"
    if abs(fraction) < 0.0005:
        return "与上期持平"
    arrow = "↑" if fraction > 0 else "↓"
    value = abs(fraction) * 100
    text = f"{value:.0f}" if value >= 100 else f"{value:.1f}"
    return f"{arrow} {text}% 较上期"


def date_short(day: dt.date) -> str:
    """``9月24日``。"""
    return f"{day.month}月{day.day}日"


def date_full(day: dt.date) -> str:
    """``2026年9月24日 周四``。"""
    return f"{day.year}年{day.month}月{day.day}日 {WEEKDAYS[day.weekday()]}"


def date_axis(day: dt.date) -> str:
    """坐标轴标签：``9/24``。"""
    return f"{day.month}/{day.day}"


def datetime_text(value: dt.datetime | None) -> str:
    """``2026-09-24 14:05``。"""
    if value is None:
        return "—"
    return value.strftime("%Y-%m-%d %H:%M")


def parse_iso(value: str | None) -> dt.datetime | None:
    """解析 ISO 8601 字符串，失败返回 None。"""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed


def relative(
    value: dt.datetime | str | None, now: dt.datetime | None = None
) -> str:
    """相对时间：``刚刚`` / ``5 分钟前`` / ``昨天`` / ``3 天前`` / 日期。"""
    if isinstance(value, str):
        value = parse_iso(value)
    if value is None:
        return "从未"
    now = now or dt.datetime.now().astimezone()
    seconds = (now - value).total_seconds()
    if seconds < 0:
        return datetime_text(value)
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    days = (now.date() - value.date()).days
    if days == 1:
        return "昨天"
    if days < 30:
        return f"{days} 天前"
    return value.strftime("%Y-%m-%d")


def reset_text(resets_at: dt.datetime | None, now: dt.datetime | None = None) -> str:
    """额度重置时间：``45 分钟后重置`` / ``3 小时 20 分后重置`` / ``周五 11:00 重置``。"""
    if resets_at is None:
        return ""
    now = now or dt.datetime.now().astimezone()
    seconds = (resets_at - now).total_seconds()
    if seconds <= 0:
        return "已重置"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{max(1, minutes)} 分钟后重置"
    if minutes < 24 * 60:
        hours, rest = divmod(minutes, 60)
        return f"{hours} 小时 {rest} 分后重置" if rest else f"{hours} 小时后重置"
    local = resets_at.astimezone()
    return f"{WEEKDAYS[local.weekday()]} {local:%H:%M} 重置"


def size(value: float) -> str:
    """文件大小：``512 B`` / ``3.4 KB`` / ``6.3 MB``。"""
    for limit, unit in ((1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "KB")):
        if value >= limit:
            return f"{value / limit:.1f} {unit}"
    return f"{int(value)} B"
