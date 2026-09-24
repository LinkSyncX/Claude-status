"""账号与设置的本地持久化。

数据保存在 ``~/.claude-status/config.json``，可用环境变量
``CLAUDE_STATUS_HOME`` 覆盖。不放在 AppData 下：Microsoft Store 版 Claude
Desktop 的子进程（例如其中的终端）对 AppData 的写入会被虚拟化到应用包
目录，同一份配置会因启动方式不同而"分裂"成两份。旧版本使用的目录会在
首次启动时自动迁移。

写入时先写临时文件再原子替换，并保留上一版为 ``config.json.bak``；文件
损坏时改名隔离后以空配置启动，不会覆盖原文件。API Key 在 Windows 上用
DPAPI 加密后保存；导出时可选择不包含密钥（导出文件中为明文）。
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import os
import pathlib
import shutil
import sys
import tempfile
from typing import Any

from claude_status import models
from claude_status import secure

CONFIG_NAME = "config.json"
EXPORT_FORMAT = "claude-status/accounts"
SCHEMA_VERSION = 1


def default_data_dir() -> pathlib.Path:
    """用户数据目录 ``~/.claude-status``（可用 CLAUDE_STATUS_HOME 覆盖）。"""
    env = os.environ.get("CLAUDE_STATUS_HOME")
    if env:
        return pathlib.Path(env).expanduser()
    return pathlib.Path.home() / ".claude-status"


def legacy_data_dir() -> pathlib.Path:
    """0.1 版本按平台约定使用的数据目录（用于迁移）。"""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = pathlib.Path(base) if base else pathlib.Path.home()
        return root / "ClaudeStatus"
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library/Application Support/ClaudeStatus"
    base = os.environ.get("XDG_CONFIG_HOME")
    root = pathlib.Path(base) if base else pathlib.Path.home() / ".config"
    return root / "claude-status"


@dataclasses.dataclass
class LoadResult:
    """读取配置的结果。

    Attributes:
        accounts: 账号列表。
        settings: 设置。
        existed: 配置文件是否已存在（False 表示首次启动）。
        warning: 读取过程中的问题说明（例如文件损坏已隔离）。
    """

    accounts: list[models.Account]
    settings: models.Settings
    existed: bool
    warning: str = ""


def migrate_legacy(target: pathlib.Path) -> bool:
    """目标目录还没有配置而旧目录有时，把旧目录复制过来，返回是否迁移。"""
    legacy = legacy_data_dir()
    if (target / CONFIG_NAME).exists():
        return False
    if not (legacy / CONFIG_NAME).exists():
        return False
    shutil.copytree(legacy, target, dirs_exist_ok=True)
    return True


def atomic_write_bytes(path: pathlib.Path, data: bytes) -> None:
    """先写同目录临时文件再原子替换，避免留下写到一半的文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except BaseException:
        pathlib.Path(temp_name).unlink(missing_ok=True)
        raise


def atomic_write_json(path: pathlib.Path, payload: Any) -> None:
    """以 UTF-8、两空格缩进原子写入 JSON。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    atomic_write_bytes(path, text.encode("utf-8"))


class Store:
    """``config.json`` 的读写。

    Args:
        directory: 数据目录，默认 ``default_data_dir()``。
    """

    def __init__(self, directory: pathlib.Path | None = None) -> None:
        self.directory = directory or default_data_dir()
        # 只在使用默认目录时迁移旧版数据，显式指定的目录保持原样。
        self.migrated = (
            directory is None
            and not os.environ.get("CLAUDE_STATUS_HOME")
            and migrate_legacy(self.directory)
        )

    @property
    def path(self) -> pathlib.Path:
        """配置文件路径。"""
        return self.directory / CONFIG_NAME

    def load(self) -> LoadResult:
        """读取配置；文件不存在时返回默认值。"""
        path = self.path
        if not path.exists():
            return LoadResult([], models.Settings(), existed=False)
        try:
            with path.open(encoding="utf-8") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                raise ValueError("顶层不是对象")
            accounts = [
                models.Account.from_dict(item)
                for item in data.get("accounts", [])
                if isinstance(item, dict)
            ]
            settings = models.Settings.from_dict(data.get("settings") or {})
            undecryptable = _decrypt_keys(accounts)
        except (OSError, ValueError, TypeError) as exc:
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            quarantine = path.with_name(f"{path.name}.corrupt-{stamp}")
            try:
                path.replace(quarantine)
            except OSError:
                quarantine = path
            return LoadResult(
                [],
                models.Settings(),
                existed=False,
                warning=f"配置文件无法读取（{exc}），已另存为 {quarantine.name}",
            )
        warning = (
            f"{undecryptable} 个账号的密钥无法解密（配置可能来自其他电脑或"
            "其他用户），已清空，请重新填写"
            if undecryptable
            else ""
        )
        return LoadResult(accounts, settings, existed=True, warning=warning)

    def save(
        self, accounts: list[models.Account], settings: models.Settings
    ) -> None:
        """保存配置，上一版备份为 ``config.json.bak``。"""
        path = self.path
        if path.exists():
            backup = path.with_name(path.name + ".bak")
            try:
                backup.write_bytes(path.read_bytes())
            except OSError:
                pass
        atomic_write_json(
            path,
            {
                "version": SCHEMA_VERSION,
                "accounts": [_encrypt_key(account) for account in accounts],
                "settings": settings.to_dict(),
            },
        )


def _encrypt_key(account: models.Account) -> dict[str, Any]:
    data = account.to_dict()
    data["api_key"] = secure.protect_text(account.api_key)
    data["env"] = {
        key: secure.protect_text(value)
        if models.is_secret_env_key(key)
        else value
        for key, value in account.env.items()
    }
    return data


def _decrypt_keys(accounts: list[models.Account]) -> int:
    """就地解密各账号的 API Key 与密钥类变量，返回无法解密（已清空）的数量。"""
    failed = 0
    for account in accounts:
        try:
            account.api_key = secure.unprotect_text(account.api_key)
            account.env = {
                key: secure.unprotect_text(value)
                if models.is_secret_env_key(key)
                else value
                for key, value in account.env.items()
            }
        except secure.SecureError:
            account.api_key = ""
            account.env = {
                key: value
                for key, value in account.env.items()
                if not models.is_secret_env_key(key)
            }
            failed += 1
    return failed


def export_accounts(
    path: pathlib.Path,
    accounts: list[models.Account],
    include_secrets: bool = False,
) -> None:
    """导出账号到 JSON 文件。"""
    atomic_write_json(
        path,
        {
            "format": EXPORT_FORMAT,
            "version": SCHEMA_VERSION,
            "exported_at": dt.datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "accounts": [
                account.to_dict(include_secret=include_secrets)
                for account in accounts
            ],
        },
    )


def read_export(path: pathlib.Path) -> list[models.Account]:
    """读取导出文件（也接受完整的 ``config.json``）。

    Raises:
        ValueError: 文件不是可识别的账号数据。
    """
    with path.open(encoding="utf-8") as stream:
        data = json.load(stream)
    items = data.get("accounts") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("文件中没有账号列表")
    return [
        models.Account.from_dict(item)
        for item in items
        if isinstance(item, dict)
    ]


@dataclasses.dataclass
class MergeResult:
    """导入合并的结果。"""

    accounts: list[models.Account]
    added: int = 0
    updated: int = 0


def merge_accounts(
    existing: list[models.Account], incoming: list[models.Account]
) -> MergeResult:
    """把导入的账号合并进现有列表。

    先按 ID、再按邮箱（忽略大小写）匹配；匹配到则更新资料（保留本地的
    ID、创建时间与本机日志关联；导入数据未带密钥时保留本地密钥），否则
    作为新账号追加。
    """
    merged = [dataclasses.replace(account) for account in existing]
    by_id = {account.id: account for account in merged}
    by_email = {
        account.email.lower(): account for account in merged if account.email
    }
    result = MergeResult(merged)
    for item in incoming:
        target = by_id.get(item.id) or (
            by_email.get(item.email.lower()) if item.email else None
        )
        if target is None:
            fresh = dataclasses.replace(item, link_local=False)
            merged.append(fresh)
            by_id[fresh.id] = fresh
            if fresh.email:
                by_email[fresh.email.lower()] = fresh
            result.added += 1
            continue
        keep = {
            "id": target.id,
            "created_at": target.created_at,
            "link_local": target.link_local,
            "api_key": item.api_key or target.api_key,
        }
        updated = dataclasses.replace(item, **keep)
        updated.touch()
        merged[merged.index(target)] = updated
        by_id[updated.id] = updated
        if updated.email:
            by_email[updated.email.lower()] = updated
        result.updated += 1
    return result
