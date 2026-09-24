"""Claude Desktop：安装检测、进程控制、登录会话快照与额度采样。

数据目录：Microsoft Store（MSIX）版的真实数据位于
``%LOCALAPPDATA%\\Packages\\Claude_*\\LocalCache\\Roaming\\Claude``——应用包
对 AppData 的写入会被虚拟化到这里，普通进程直接看 ``%APPDATA%\\Claude``
得到的并不是应用实际使用的文件；安装程序版使用 ``%APPDATA%\\Claude``。
可用环境变量 ``CLAUDE_STATUS_DESKTOP_DIR`` 覆盖（测试用）。

登录会话：Cookie、Local Storage、IndexedDB 等 Chromium 存储，加上
``config.json`` 中与账号相关的键（``oauth:tokenCache*``、
``lastKnownAccountUuid`` 等）。快照与恢复都必须在 Desktop 退出后进行；
``config.json`` 只替换账号相关的键，主题等其他设置保持不变；MCP 配置、
Claude Code 会话记录与额度采样历史属于全局数据，不随账号切换。
"""

from __future__ import annotations

import ctypes
import dataclasses
import datetime as dt
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any

from claude_status import storage

ENV_DATA_DIR = "CLAUDE_STATUS_DESKTOP_DIR"
CONFIG_NAME = "config.json"
MCP_CONFIG_NAME = "claude_desktop_config.json"
USAGE_HISTORY_NAME = "plan-usage-history.json"
ACCOUNT_SNAPSHOT_NAME = "account.json"
MSIX_APP_ID = "Claude"
# 随账号切换的 Chromium 会话存储（Desktop 退出后整体替换）。
SESSION_ITEMS = (
    "Local State",
    "Preferences",
    "Network",
    "Local Storage",
    "Session Storage",
    "IndexedDB",
    "WebStorage",
    "Partitions",
    "Shared Dictionary",
    "SharedStorage",
    "SharedStorage-wal",
    "DIPS",
    "DIPS-wal",
    "blob_storage",
    "File System",
)
# "登录新账号"时清空的项目：保留 Local State（其中的加密密钥供所有快照共用）。
CLEAR_ITEMS = tuple(item for item in SESSION_ITEMS if item != "Local State")
ACCOUNT_KEY_PREFIXES = ("oauth:", "dxt:", "remote_uploads_migration_done_v1_")
ACCOUNT_KEYS = frozenset({"lastKnownAccountUuid"})
_VERSION_IN_PATH = re.compile(r"Claude_(\d+(?:\.\d+)+)_", re.IGNORECASE)


class DesktopError(Exception):
    """Desktop 操作失败。"""


# ---- 路径与安装 -----------------------------------------------------------


def _package_dirs() -> list[pathlib.Path]:
    local = os.environ.get("LOCALAPPDATA")
    if sys.platform != "win32" or not local:
        return []
    packages = pathlib.Path(local) / "Packages"
    try:
        return sorted(packages.glob("Claude_*"))
    except OSError:
        return []


def data_dir() -> pathlib.Path:
    """Claude Desktop 实际使用的数据目录。"""
    override = os.environ.get(ENV_DATA_DIR)
    if override:
        return pathlib.Path(override).expanduser()
    if sys.platform == "win32":
        for package in _package_dirs():
            candidate = package / "LocalCache" / "Roaming" / "Claude"
            if (candidate / CONFIG_NAME).exists():
                return candidate
        appdata = os.environ.get("APPDATA")
        base = pathlib.Path(appdata) if appdata else pathlib.Path.home()
        return base / "Claude"
    if sys.platform == "darwin":
        return pathlib.Path.home() / "Library" / "Application Support" / "Claude"
    return pathlib.Path.home() / ".config" / "Claude"


@dataclasses.dataclass(frozen=True)
class Install:
    """Desktop 的安装信息。

    Attributes:
        kind: ``msix``（Microsoft Store）/ ``squirrel``（安装程序）/
            ``mac`` / 空字符串（未检测到）。
        version: 版本号，未知时为空字符串。
        executable: 可直接启动的程序路径（MSIX 版为 None）。
        app_id: MSIX 版的应用 ID（``包系列名!Claude``）。
    """

    kind: str = ""
    version: str = ""
    executable: pathlib.Path | None = None
    app_id: str = ""

    @property
    def installed(self) -> bool:
        """是否检测到安装。"""
        return bool(self.kind)

    @property
    def label(self) -> str:
        """安装方式的显示名称。"""
        return {
            "msix": "Microsoft Store 版",
            "squirrel": "安装程序版",
            "mac": "macOS 版",
        }.get(self.kind, "未检测到")


def detect_install(processes: list[Process] | None = None) -> Install:
    """检测安装方式与版本（版本优先取自正在运行的进程路径）。"""
    running_paths = [p.path for p in (processes or [])]
    version = next(
        (
            match.group(1)
            for path in running_paths
            if (match := _VERSION_IN_PATH.search(path))
        ),
        "",
    )
    if sys.platform == "win32":
        packages = _package_dirs()
        if packages:
            config = read_config(data_dir())
            version = version or str(config.get("updaterLastSeenVersion") or "")
            return Install(
                "msix", version, None, f"{packages[0].name}!{MSIX_APP_ID}"
            )
        local = os.environ.get("LOCALAPPDATA")
        if local:
            root = pathlib.Path(local) / "AnthropicClaude"
            if (root / "claude.exe").exists():
                versions = sorted(
                    path.name.removeprefix("app-")
                    for path in root.glob("app-*")
                )
                return Install(
                    "squirrel",
                    version or (versions[-1] if versions else ""),
                    root / "claude.exe",
                )
        return Install()
    if sys.platform == "darwin":
        app = pathlib.Path("/Applications/Claude.app")
        if app.exists():
            return Install("mac", version, app)
    return Install()


# ---- 进程 -----------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Process:
    """一个进程。"""

    pid: int
    path: str


def is_desktop_executable(path: str) -> bool:
    """进程是否属于 Claude Desktop。

    Claude Code 的命令行程序与 Desktop 内置的 Claude Code 也叫
    ``claude.exe``，必须按安装位置区分，不能按进程名结束进程。
    """
    lower = path.replace("/", "\\").lower()
    if sys.platform == "darwin" or lower.startswith("\\applications"):
        return path.endswith("/Claude.app/Contents/MacOS/Claude")
    if lower.rsplit("\\", 1)[-1] != "claude.exe":
        return False
    if "\\claude-code\\" in lower or "\\.local\\bin\\" in lower:
        return False
    return "\\windowsapps\\claude_" in lower or "\\anthropicclaude\\" in lower


if sys.platform == "win32":
    from ctypes import wintypes

    _psapi = ctypes.WinDLL("psapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi.EnumProcesses.argtypes = [
        ctypes.POINTER(wintypes.DWORD),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _psapi.EnumProcesses.restype = wintypes.BOOL
    _kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _QUERY_LIMITED_INFORMATION = 0x1000

    def _windows_processes() -> list[Process]:
        size = 2048
        while True:
            pids = (wintypes.DWORD * size)()
            needed = wintypes.DWORD()
            if not _psapi.EnumProcesses(
                pids, ctypes.sizeof(pids), ctypes.byref(needed)
            ):
                return []
            count = needed.value // ctypes.sizeof(wintypes.DWORD)
            if count < size:
                break
            size *= 2
        result: list[Process] = []
        buffer = ctypes.create_unicode_buffer(1024)
        for pid in pids[:count]:
            if not pid:
                continue
            handle = _kernel32.OpenProcess(
                _QUERY_LIMITED_INFORMATION, False, pid
            )
            if not handle:
                continue
            try:
                length = wintypes.DWORD(len(buffer))
                if _kernel32.QueryFullProcessImageNameW(
                    handle, 0, buffer, ctypes.byref(length)
                ):
                    result.append(Process(int(pid), buffer.value))
            finally:
                _kernel32.CloseHandle(handle)
        return result


def _posix_processes() -> list[Process]:
    try:
        output = subprocess.run(
            ["ps", "-axo", "pid=,comm="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    result = []
    for line in output.splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit():
            result.append(Process(int(pid), command.strip()))
    return result


def list_processes() -> list[Process]:
    """系统中的全部进程（取不到路径的进程会被跳过）。"""
    if sys.platform == "win32":
        return _windows_processes()
    return _posix_processes()


def running(processes: list[Process] | None = None) -> list[Process]:
    """正在运行的 Claude Desktop 进程。"""
    if processes is None:
        processes = list_processes()
    return [p for p in processes if is_desktop_executable(p.path)]


def _taskkill(processes: list[Process], force: bool) -> None:
    if not processes:
        return
    command = ["taskkill"]
    if force:
        command += ["/F", "/T"]
    for process in processes:
        command += ["/PID", str(process.pid)]
    subprocess.run(
        command,
        capture_output=True,
        timeout=15,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def request_quit(processes: list[Process]) -> None:
    """请求 Desktop 正常退出（向窗口发送关闭消息）。"""
    if sys.platform == "win32":
        _taskkill(processes, force=False)
    elif sys.platform == "darwin":
        subprocess.run(
            ["osascript", "-e", 'tell application "Claude" to quit'],
            capture_output=True,
            timeout=15,
            check=False,
        )


def force_quit(processes: list[Process]) -> None:
    """强制结束 Desktop 及其子进程。"""
    if sys.platform == "win32":
        _taskkill(processes, force=True)
        return
    for process in processes:
        try:
            os.kill(process.pid, 9)
        except OSError:
            pass


def wait_until_closed(timeout: float = 8.0, interval: float = 0.3) -> bool:
    """等待 Desktop 全部进程退出，返回是否已退出。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not running():
            return True
        time.sleep(interval)
    return not running()


def launch(install: Install) -> bool:
    """启动 Desktop，返回是否成功发出启动请求。"""
    try:
        if install.kind == "msix" and install.app_id:
            subprocess.Popen(  # pylint: disable=consider-using-with
                ["explorer.exe", "shell:AppsFolder\\" + install.app_id]
            )
            return True
        if install.kind == "squirrel" and install.executable:
            os.startfile(install.executable)  # type: ignore[attr-defined]
            return True
        if install.kind == "mac":
            subprocess.Popen(  # pylint: disable=consider-using-with
                ["open", "-a", "Claude"]
            )
            return True
    except OSError:
        return False
    return False


# ---- 数据读取 -------------------------------------------------------------


def read_config(root: pathlib.Path) -> dict[str, Any]:
    """读取 Desktop 的 ``config.json``（不存在或损坏时为空字典）。"""
    try:
        with (root / CONFIG_NAME).open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def current_account_uuid(root: pathlib.Path) -> str:
    """Desktop 当前（最近一次）登录的账号 UUID。"""
    return str(read_config(root).get("lastKnownAccountUuid") or "")


def is_logged_in(root: pathlib.Path) -> bool:
    """是否保存有登录令牌。"""
    return any(
        key.startswith("oauth:tokenCache") and bool(value)
        for key, value in read_config(root).items()
    )


@dataclasses.dataclass(frozen=True)
class Sample:
    """一条额度采样。"""

    time: dt.datetime
    org: str
    usage: dict[str, Any]


def read_samples(root: pathlib.Path) -> list[Sample]:
    """``plan-usage-history.json`` 中的采样（按时间升序）。"""
    try:
        with (root / USAGE_HISTORY_NAME).open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return []
    samples = []
    for item in (data.get("samples") if isinstance(data, dict) else None) or []:
        if not isinstance(item, dict):
            continue
        stamp = item.get("t")
        usage = item.get("u")
        if not isinstance(stamp, int | float) or not isinstance(usage, dict):
            continue
        samples.append(
            Sample(
                dt.datetime.fromtimestamp(stamp / 1000, dt.UTC).astimezone(),
                str(item.get("org") or ""),
                usage,
            )
        )
    samples.sort(key=lambda sample: sample.time)
    return samples


def read_mcp_servers(root: pathlib.Path) -> dict[str, dict[str, Any]]:
    """``claude_desktop_config.json`` 中配置的 MCP 服务器。"""
    try:
        with (root / MCP_CONFIG_NAME).open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    if not isinstance(servers, dict):
        return {}
    return {
        str(name): value
        for name, value in servers.items()
        if isinstance(value, dict)
    }


def dir_size(path: pathlib.Path) -> int:
    """目录（或文件）占用的字节数。"""
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (pathlib.Path(root) / name).stat().st_size
            except OSError:
                pass
    return total


@dataclasses.dataclass
class DesktopState:
    """Desktop 的当前状态（界面展示用）。"""

    install: Install
    data_dir: pathlib.Path
    exists: bool
    processes: list[Process]
    logged_in: bool
    account_uuid: str
    samples: list[Sample]
    mcp_servers: dict[str, dict[str, Any]]

    @property
    def running(self) -> bool:
        """是否正在运行。"""
        return bool(self.processes)


def read_state() -> DesktopState:
    """读取 Desktop 的安装、运行、登录与采样信息（只读）。"""
    root = data_dir()
    processes = running()
    return DesktopState(
        install=detect_install(processes),
        data_dir=root,
        exists=root.is_dir(),
        processes=processes,
        logged_in=is_logged_in(root),
        account_uuid=current_account_uuid(root),
        samples=read_samples(root),
        mcp_servers=read_mcp_servers(root),
    )


# ---- 会话快照 -------------------------------------------------------------


def is_account_key(key: str) -> bool:
    """``config.json`` 中随账号切换的键。"""
    return key in ACCOUNT_KEYS or key.startswith(ACCOUNT_KEY_PREFIXES)


def _remove(path: pathlib.Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _copy(source: pathlib.Path, target: pathlib.Path) -> None:
    if source.is_dir():
        shutil.copytree(source, target)
    elif source.is_file():
        shutil.copy2(source, target)


def snapshot_session(root: pathlib.Path, dest: pathlib.Path) -> int:
    """把当前登录会话复制到 ``dest``（整体替换旧快照），返回快照大小。

    Desktop 必须已经退出，否则数据库文件可能处于写入中。
    """
    if not root.is_dir():
        raise DesktopError(f"找不到 Claude Desktop 数据目录：{root}")
    partial = dest.with_name(dest.name + ".partial")
    _remove(partial)
    partial.mkdir(parents=True)
    try:
        for name in SESSION_ITEMS:
            _copy(root / name, partial / name)
        account = {
            key: value
            for key, value in read_config(root).items()
            if is_account_key(key)
        }
        storage.atomic_write_json(partial / ACCOUNT_SNAPSHOT_NAME, account)
        old = dest.with_name(dest.name + ".old")
        _remove(old)
        if dest.exists():
            dest.rename(old)
        partial.rename(dest)
        _remove(old)
    except BaseException:
        shutil.rmtree(partial, ignore_errors=True)
        raise
    return dir_size(dest)


def _write_account_keys(root: pathlib.Path, account: dict[str, Any]) -> None:
    config = {
        key: value
        for key, value in read_config(root).items()
        if not is_account_key(key)
    }
    config.update(account)
    storage.atomic_write_json(root / CONFIG_NAME, config)


def restore_session(snapshot: pathlib.Path, root: pathlib.Path) -> None:
    """用快照替换当前登录会话；任何一步失败都会回滚到原状态。

    Desktop 必须已经退出。
    """
    if not (snapshot / ACCOUNT_SNAPSHOT_NAME).is_file():
        raise DesktopError("登录快照不完整，请重新保存该账号的 Desktop 登录")
    try:
        account = json.loads(
            (snapshot / ACCOUNT_SNAPSHOT_NAME).read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise DesktopError(f"登录快照已损坏：{exc}") from exc
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    trash = root.parent / f".claude-status-trash-{stamp}"
    trash.mkdir(parents=True)
    try:
        for name in SESSION_ITEMS:
            if (root / name).exists():
                (root / name).rename(trash / name)
        for name in SESSION_ITEMS:
            _copy(snapshot / name, root / name)
        _write_account_keys(root, account if isinstance(account, dict) else {})
    except BaseException:
        for name in SESSION_ITEMS:
            _remove(root / name)
            if (trash / name).exists():
                (trash / name).rename(root / name)
        shutil.rmtree(trash, ignore_errors=True)
        raise
    shutil.rmtree(trash, ignore_errors=True)


def clear_session(root: pathlib.Path) -> None:
    """清空登录会话，下次启动 Desktop 时显示登录界面。

    调用前应先用 ``snapshot_session`` 保存当前会话。保留 Local State，
    其中的加密密钥供所有快照共用。
    """
    for name in CLEAR_ITEMS:
        _remove(root / name)
    _write_account_keys(root, {})
