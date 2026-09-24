"""读取本机 Claude Code 的用量日志与当前登录账号。

Claude Code 把每个会话记录为 ``~/.claude/projects/<项目>/<会话>.jsonl``，
助手消息行带有 ``message.usage``（输入 / 输出 / 缓存写入 / 缓存读取
token）。同一次 API 响应会按内容块拆成多行、续接会话时还会复制历史，
因此必须按 ``message.id`` 全局去重，否则用量会被重复计算数倍。

本模块只读取用量相关字段，不读取对话内容，也不会访问凭据文件。
设置了 ``CLAUDE_CONFIG_DIR`` 环境变量时从该目录读取。
"""

from __future__ import annotations

from collections.abc import Iterator
import dataclasses
import datetime as dt
import json
import os
import pathlib
import time

from claude_status import models

SYNTHETIC_MODEL = "<synthetic>"
_USAGE_MARKER = '"usage"'


def config_dir() -> pathlib.Path:
    """Claude Code 配置目录（默认 ``~/.claude``）。"""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path.home() / ".claude"


def default_projects_dir() -> pathlib.Path:
    """会话日志目录。"""
    return config_dir() / "projects"


def global_state_path() -> pathlib.Path:
    """全局状态文件 ``.claude.json`` 的位置。"""
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return pathlib.Path(env).expanduser() / ".claude.json"
    return pathlib.Path.home() / ".claude.json"


def parse_timestamp(value: object) -> dt.datetime | None:
    """解析 ISO 8601 时间戳并转换为本地时区，失败返回 None。"""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone()


def project_name(cwd: object, fallback: str = "") -> str:
    """由工作目录得到简短的项目名；用户主目录显示为 ``~``。"""
    if not isinstance(cwd, str) or not cwd:
        return fallback
    windows = "\\" in cwd
    path = pathlib.PureWindowsPath(cwd) if windows else pathlib.PurePath(cwd)
    try:
        if pathlib.Path(cwd) == pathlib.Path.home():
            return "~"
    except (OSError, ValueError):
        pass
    return path.name or cwd


def request_source(entrypoint: str, request_id: str) -> models.UsageSource:
    """由日志的 ``entrypoint`` 与 ``requestId`` 判断请求来源。

    ``entrypoint`` 区分客户端（``cli`` / ``claude-desktop`` /
    ``claude-desktop-3p`` …）；官方服务的响应带有 ``req_`` 开头的请求 ID，
    中转与第三方服务没有。
    """
    if entrypoint.endswith("-3p") or not request_id.startswith("req_"):
        return models.UsageSource.THIRD_PARTY
    if entrypoint.startswith("claude-desktop"):
        return models.UsageSource.DESKTOP
    return models.UsageSource.CODE


def _int(value: object) -> int:
    try:
        return max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


@dataclasses.dataclass
class _Entry:
    """去重过程中的一条请求（各 token 字段取所有重复行的最大值）。"""

    timestamp: dt.datetime
    model: str
    input_tokens: int
    output_tokens: int
    cache_write_5m: int
    cache_write_1h: int
    cache_read: int
    project: str
    session_id: str
    source: str

    def merge(self, other: _Entry) -> None:
        self.timestamp = min(self.timestamp, other.timestamp)
        self.input_tokens = max(self.input_tokens, other.input_tokens)
        self.output_tokens = max(self.output_tokens, other.output_tokens)
        self.cache_write_5m = max(self.cache_write_5m, other.cache_write_5m)
        self.cache_write_1h = max(self.cache_write_1h, other.cache_write_1h)
        self.cache_read = max(self.cache_read, other.cache_read)

    def to_record(self) -> models.UsageRecord:
        return models.UsageRecord(
            timestamp=self.timestamp,
            model=self.model,
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            cache_write_5m=self.cache_write_5m,
            cache_write_1h=self.cache_write_1h,
            cache_read=self.cache_read,
            project=self.project,
            session_id=self.session_id,
            source=self.source,
        )


def parse_line(
    line: str, fallback_project: str = ""
) -> tuple[str, _Entry] | None:
    """解析一行日志，返回 (去重键, 条目)；非用量行返回 None。"""
    if _USAGE_MARKER not in line:
        return None
    try:
        obj = json.loads(line)
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    message = obj.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    model = message.get("model")
    if not isinstance(usage, dict) or not isinstance(model, str):
        return None
    if not model or model == SYNTHETIC_MODEL:
        return None
    timestamp = parse_timestamp(obj.get("timestamp"))
    if timestamp is None:
        return None
    key = message.get("id") or obj.get("requestId") or obj.get("uuid")
    if not isinstance(key, str) or not key:
        return None
    creation = usage.get("cache_creation")
    write_1h = write_5m = 0
    if isinstance(creation, dict):
        write_1h = _int(creation.get("ephemeral_1h_input_tokens"))
        write_5m = _int(creation.get("ephemeral_5m_input_tokens"))
    # 旧版日志只有合计字段：未细分的部分按 5 分钟缓存计。
    write_total = _int(usage.get("cache_creation_input_tokens"))
    write_5m += max(0, write_total - write_1h - write_5m)
    entry = _Entry(
        timestamp=timestamp,
        model=model,
        input_tokens=_int(usage.get("input_tokens")),
        output_tokens=_int(usage.get("output_tokens")),
        cache_write_5m=write_5m,
        cache_write_1h=write_1h,
        cache_read=_int(usage.get("cache_read_input_tokens")),
        project=project_name(obj.get("cwd"), fallback_project),
        session_id=str(obj.get("sessionId") or ""),
        source=request_source(
            str(obj.get("entrypoint") or ""), str(obj.get("requestId") or "")
        ),
    )
    return key, entry


@dataclasses.dataclass
class ScanResult:
    """一次扫描的结果与统计信息。

    Attributes:
        directory: 扫描的目录。
        records: 去重后的用量记录（按时间升序）。
        files: 扫描的日志文件数。
        rows: 含用量的日志行数（去重前）。
        duplicates: 被去重合并的行数。
        errors: 无法读取的文件数。
        elapsed: 耗时（秒）。
        exists: 目录是否存在。
        error: 扫描异常中止时的错误信息。
    """

    directory: pathlib.Path
    records: list[models.UsageRecord] = dataclasses.field(default_factory=list)
    files: int = 0
    rows: int = 0
    duplicates: int = 0
    errors: int = 0
    elapsed: float = 0.0
    exists: bool = True
    error: str = ""

    @property
    def first(self) -> dt.datetime | None:
        """最早一条记录的时间。"""
        return self.records[0].timestamp if self.records else None

    @property
    def last(self) -> dt.datetime | None:
        """最近一条记录的时间。"""
        return self.records[-1].timestamp if self.records else None


class LogScanner:
    """扫描会话日志；按文件的修改时间与大小缓存解析结果，重复扫描时增量更新。"""

    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, int, list[tuple[str, _Entry]]]] = {}

    def _parse_file(
        self, path: pathlib.Path, fallback_project: str
    ) -> list[tuple[str, _Entry]]:
        stat = path.stat()
        cache_key = str(path)
        cached = self._cache.get(cache_key)
        if cached is not None and cached[:2] == (stat.st_mtime, stat.st_size):
            return cached[2]
        entries: list[tuple[str, _Entry]] = []
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parsed = parse_line(line, fallback_project)
                if parsed is not None:
                    entries.append(parsed)
        self._cache[cache_key] = (stat.st_mtime, stat.st_size, entries)
        return entries

    def scan(self, directory: pathlib.Path | None = None) -> ScanResult:
        """扫描目录下全部 ``*.jsonl`` 并返回去重后的记录。"""
        started = time.perf_counter()
        directory = directory or default_projects_dir()
        result = ScanResult(directory=directory)
        if not directory.is_dir():
            result.exists = False
            return result
        merged: dict[str, _Entry] = {}
        seen_files: set[str] = set()
        for path in _iter_logs(directory):
            seen_files.add(str(path))
            top = path.relative_to(directory).parts[0]
            try:
                entries = self._parse_file(path, _decode_dir_name(top))
            except OSError:
                result.errors += 1
                continue
            result.files += 1
            for key, entry in entries:
                result.rows += 1
                existing = merged.get(key)
                if existing is None:
                    merged[key] = dataclasses.replace(entry)
                else:
                    existing.merge(entry)
                    result.duplicates += 1
        # 丢弃已删除文件的缓存。
        for stale in set(self._cache) - seen_files:
            del self._cache[stale]
        result.records = sorted(
            (entry.to_record() for entry in merged.values()),
            key=lambda record: record.timestamp,
        )
        result.elapsed = time.perf_counter() - started
        return result


def _iter_logs(directory: pathlib.Path) -> Iterator[pathlib.Path]:
    for root, _dirs, files in os.walk(directory):
        for name in files:
            if name.endswith(".jsonl"):
                yield pathlib.Path(root) / name


def _decode_dir_name(name: str) -> str:
    """项目目录名（``F--work-demo``）的最后一段，作为缺少 cwd 时的回退。"""
    parts = [part for part in name.split("-") if part]
    return parts[-1] if parts else name


# ---- 当前登录账号 ---------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class LocalLogin:
    """``.claude.json`` 中记录的当前 Claude Code 登录账号（只读）。

    Attributes:
        email: 登录邮箱。
        display_name: 显示名。
        organization: 组织名。
        plan: 推断出的套餐。
        billing_type: 计费方式（如 ``stripe_subscription``）。
        five_hour: 5 小时窗口的限额使用率（0–100），无缓存时为 None。
        seven_day: 7 天窗口的限额使用率（0–100）。
        five_hour_resets: 5 小时窗口重置时间。
        seven_day_resets: 7 天窗口重置时间。
        utilization_fetched: 使用率缓存的获取时间。
        subscription_created: 订阅开始时间。
    """

    email: str
    display_name: str = ""
    organization: str = ""
    plan: models.Plan = models.Plan.FREE
    billing_type: str = ""
    five_hour: float | None = None
    seven_day: float | None = None
    five_hour_resets: dt.datetime | None = None
    seven_day_resets: dt.datetime | None = None
    utilization_fetched: dt.datetime | None = None
    subscription_created: dt.datetime | None = None


def infer_plan(account: dict) -> models.Plan:
    """由 ``oauthAccount`` 的组织类型与限速档位推断套餐。"""
    org_type = str(account.get("organizationType") or "").lower()
    tiers = " ".join(
        str(account.get(key) or "").lower()
        for key in (
            "userRateLimitTier",
            "organizationRateLimitTier",
            "seatTier",
        )
    )
    if "max" in org_type:
        return models.Plan.MAX_20X if "20x" in tiers else models.Plan.MAX_5X
    if "pro" in org_type:
        return models.Plan.PRO
    if "team" in org_type:
        return models.Plan.TEAM
    if "enterprise" in org_type:
        return models.Plan.ENTERPRISE
    return models.Plan.FREE


def _window(
    utilization: dict, name: str
) -> tuple[float | None, dt.datetime | None]:
    window = utilization.get(name)
    if not isinstance(window, dict):
        return None, None
    value = window.get("utilization")
    percent = float(value) if isinstance(value, int | float) else None
    return percent, parse_timestamp(window.get("resets_at"))


def read_local_login(path: pathlib.Path | None = None) -> LocalLogin | None:
    """读取当前登录账号；未登录、文件不存在或格式异常时返回 None。"""
    path = path or global_state_path()
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    account = data.get("oauthAccount") if isinstance(data, dict) else None
    if not isinstance(account, dict) or not account.get("emailAddress"):
        return None
    five_hour = seven_day = None
    five_resets = seven_resets = fetched = None
    cached = data.get("cachedUsageUtilization")
    # 只有缓存属于当前账号时才采用其中的限额使用率。
    if (
        isinstance(cached, dict)
        and cached.get("accountUuid") == account.get("accountUuid")
        and isinstance(cached.get("utilization"), dict)
    ):
        five_hour, five_resets = _window(cached["utilization"], "five_hour")
        seven_day, seven_resets = _window(cached["utilization"], "seven_day")
        fetched_ms = cached.get("fetchedAtMs")
        if isinstance(fetched_ms, int | float):
            fetched = dt.datetime.fromtimestamp(fetched_ms / 1000).astimezone()
    return LocalLogin(
        email=str(account.get("emailAddress")),
        display_name=str(
            account.get("displayName") or account.get("fullName") or ""
        ),
        organization=str(account.get("organizationName") or ""),
        plan=infer_plan(account),
        billing_type=str(account.get("billingType") or ""),
        five_hour=five_hour,
        seven_day=seven_day,
        five_hour_resets=five_resets,
        seven_day_resets=seven_resets,
        utilization_fetched=fetched,
        subscription_created=parse_timestamp(
            account.get("subscriptionCreatedAt")
        ),
    )
