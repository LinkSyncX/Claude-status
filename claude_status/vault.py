"""凭据保险箱：按账号保存的 Claude Code 登录与 Claude Desktop 会话。

目录结构（位于数据目录的 ``vault`` 下）::

    <账号 ID>/code.bin       Claude Code 登录（加密的 JSON）
    <账号 ID>/code.json      登录元数据（邮箱、保存时间，不含令牌）
    <账号 ID>/desktop/       Desktop 会话快照
    <账号 ID>/desktop.json   快照元数据
    _unassigned/<时间>/      无法归属到账号的 Desktop 会话备份
    .trash/<账号 ID>-<时间>/ 已删除账号的数据（可撤销，一天后清理）

Claude Code 登录经 ``secure`` 加密（Windows DPAPI）；Desktop 快照中的
Cookie 与令牌缓存本身已由 Chromium 用同一 Windows 用户的密钥加密。
"""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import shutil
from typing import Any

from claude_status import code_config
from claude_status import secure
from claude_status import storage

TRASH_NAME = ".trash"
UNASSIGNED_NAME = "_unassigned"
TRASH_TTL = dt.timedelta(days=1)


def _now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


class Vault:
    """凭据保险箱。

    Args:
        root: 保险箱目录。
    """

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    def _dir(self, account_id: str) -> pathlib.Path:
        return self.root / account_id

    @staticmethod
    def _read_json(path: pathlib.Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    # ---- Claude Code ------------------------------------------------------

    def save_code(self, account_id: str, login: code_config.CodeLogin) -> None:
        """保存（覆盖）账号的 Claude Code 登录。"""
        folder = self._dir(account_id)
        payload = json.dumps(login.to_dict(), ensure_ascii=False)
        storage.atomic_write_bytes(
            folder / "code.bin", secure.protect(payload.encode("utf-8"))
        )
        expires = login.expires_at
        storage.atomic_write_json(
            folder / "code.json",
            {
                "email": login.email,
                "account_uuid": login.account_uuid,
                "subscription": login.subscription_type,
                "saved_at": _now_iso(),
                "expires_at": expires.isoformat() if expires else None,
            },
        )

    def load_code(self, account_id: str) -> code_config.CodeLogin | None:
        """读取账号的 Claude Code 登录；没有或无法解密时返回 None。"""
        path = self._dir(account_id) / "code.bin"
        try:
            raw = secure.unprotect(path.read_bytes())
            data = json.loads(raw.decode("utf-8"))
        except (OSError, ValueError, secure.SecureError):
            return None
        return code_config.CodeLogin.from_dict(data)

    def has_code(self, account_id: str) -> bool:
        """是否保存了 Claude Code 登录。"""
        return (self._dir(account_id) / "code.bin").is_file()

    def code_meta(self, account_id: str) -> dict[str, Any] | None:
        """Claude Code 登录的元数据。"""
        return self._read_json(self._dir(account_id) / "code.json")

    def delete_code(self, account_id: str) -> None:
        """删除账号保存的 Claude Code 登录。"""
        for name in ("code.bin", "code.json"):
            (self._dir(account_id) / name).unlink(missing_ok=True)

    # ---- Claude Desktop ---------------------------------------------------

    def desktop_path(self, account_id: str) -> pathlib.Path:
        """账号的 Desktop 会话快照目录。"""
        return self._dir(account_id) / "desktop"

    def has_desktop(self, account_id: str) -> bool:
        """是否保存了 Desktop 会话。"""
        return self.desktop_path(account_id).is_dir()

    def desktop_meta(self, account_id: str) -> dict[str, Any] | None:
        """Desktop 会话快照的元数据。"""
        return self._read_json(self._dir(account_id) / "desktop.json")

    def write_desktop_meta(
        self, account_id: str, size: int, account_uuid: str
    ) -> None:
        """记录 Desktop 快照的元数据。"""
        storage.atomic_write_json(
            self._dir(account_id) / "desktop.json",
            {
                "saved_at": _now_iso(),
                "size": size,
                "account_uuid": account_uuid,
            },
        )

    def delete_desktop(self, account_id: str) -> None:
        """删除账号保存的 Desktop 会话。"""
        shutil.rmtree(self.desktop_path(account_id), ignore_errors=True)
        (self._dir(account_id) / "desktop.json").unlink(missing_ok=True)

    def unassigned_path(self) -> pathlib.Path:
        """为无法归属的 Desktop 会话生成一个新的备份目录路径。"""
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        return self.root / UNASSIGNED_NAME / stamp

    # ---- 删除与撤销 -------------------------------------------------------

    def trash(self, account_id: str) -> pathlib.Path | None:
        """把账号的全部保存数据移入回收区，返回回收位置（用于撤销）。"""
        folder = self._dir(account_id)
        if not folder.exists():
            return None
        stamp = dt.datetime.now().strftime("%Y%m%d%H%M%S%f")
        target = self.root / TRASH_NAME / f"{account_id}-{stamp}"
        target.parent.mkdir(parents=True, exist_ok=True)
        folder.rename(target)
        return target

    def untrash(self, location: pathlib.Path, account_id: str) -> None:
        """撤销删除：把回收区中的数据放回原处。"""
        folder = self._dir(account_id)
        if location.exists() and not folder.exists():
            location.rename(folder)

    def purge_trash(self, now: dt.datetime | None = None) -> None:
        """清理超过保留期的回收区数据。"""
        trash = self.root / TRASH_NAME
        if not trash.is_dir():
            return
        now = now or dt.datetime.now()
        for item in trash.iterdir():
            modified = dt.datetime.fromtimestamp(item.stat().st_mtime)
            if now - modified > TRASH_TTL:
                shutil.rmtree(item, ignore_errors=True)
