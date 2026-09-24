"""测试夹具：在临时目录中伪造 Claude Code 与 Claude Desktop 的配置。"""

import json
import os
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from claude_status import claude_desktop

FAKE_DESKTOP_EXE = (
    "C:/Program Files/WindowsApps/Claude_9.9.0.0_x64__test/app/Claude.exe"
)


def isolate_desktop_processes(test: unittest.TestCase) -> "FakeProcesses":
    """用假的进程列表替换 Desktop 的进程控制，测试绝不接触本机真实进程。"""
    fake = FakeProcesses()
    for name, value in (
        ("list_processes", fake.list),
        ("request_quit", fake.request_quit),
        ("force_quit", fake.force_quit),
        ("launch", fake.launch),
    ):
        patcher = mock.patch.object(claude_desktop, name, value)
        patcher.start()
        test.addCleanup(patcher.stop)
    return fake


class FakeProcesses:
    """假的 Desktop 进程：记录退出与启动请求。

    Attributes:
        processes: 当前"运行中"的进程。
        ignore_quit: 为真时模拟最小化到托盘、不响应正常退出。
    """

    def __init__(self) -> None:
        self.processes: list[claude_desktop.Process] = []
        self.ignore_quit = False
        self.calls: list[str] = []

    def start_desktop(self) -> None:
        self.processes = [claude_desktop.Process(4242, FAKE_DESKTOP_EXE)]

    def list(self) -> list[claude_desktop.Process]:
        return list(self.processes)

    def request_quit(self, _processes) -> None:
        self.calls.append("quit")
        if not self.ignore_quit:
            self.processes = []

    def force_quit(self, _processes) -> None:
        self.calls.append("force")
        self.processes = []

    def launch(self, _install) -> bool:
        self.calls.append("launch")
        self.start_desktop()
        return True


def write_json(path: pathlib.Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def read_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def oauth(token: str, expires_in: float = 3600) -> dict:
    return {
        "accessToken": f"access-{token}",
        "refreshToken": f"refresh-{token}",
        "expiresAt": int((time.time() + expires_in) * 1000),
        "scopes": ["user:inference", "user:profile"],
        "subscriptionType": "max",
    }


def oauth_account(name: str) -> dict:
    return {
        "accountUuid": f"uuid-{name}",
        "emailAddress": f"{name}@example.com",
        "organizationUuid": f"org-{name}",
        "displayName": name.upper(),
    }


class IsolatedClaudeTest(unittest.TestCase):
    """把 Claude Code（CLAUDE_CONFIG_DIR）与 Desktop 数据目录指向临时目录。"""

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = pathlib.Path(self._tmp.name)
        self.claude_dir = self.root / "claude"
        self.desktop_dir = self.root / "desktop"
        self.data_dir = self.root / "data"
        self.claude_dir.mkdir()
        patcher = mock.patch.dict(
            os.environ,
            {
                "CLAUDE_CONFIG_DIR": str(self.claude_dir),
                "CLAUDE_STATUS_DESKTOP_DIR": str(self.desktop_dir),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.desktop_processes = isolate_desktop_processes(self)

    # ---- Claude Code ------------------------------------------------------

    def login_code(self, name: str, **extra_state) -> None:
        """模拟 Claude Code 以某个账号登录。"""
        write_json(
            self.claude_dir / ".credentials.json", {"claudeAiOauth": oauth(name)}
        )
        state_path = self.claude_dir / ".claude.json"
        state = read_json(state_path) if state_path.exists() else {}
        state.update({"projects": {"F:/demo": {"history": [1, 2]}}})
        state.update(extra_state)
        state["oauthAccount"] = oauth_account(name)
        write_json(state_path, state)

    def set_settings(self, env: dict | None = None, **other) -> None:
        data = {"model": "opus", **other}
        if env is not None:
            data["env"] = env
        write_json(self.claude_dir / "settings.json", data)

    def settings(self) -> dict:
        return read_json(self.claude_dir / "settings.json")

    def live_email(self) -> str:
        return read_json(self.claude_dir / ".claude.json")["oauthAccount"][
            "emailAddress"
        ]

    # ---- Claude Desktop ---------------------------------------------------

    def login_desktop(self, name: str) -> None:
        """模拟 Desktop 以某个账号登录（伪造 Chromium 会话文件）。"""
        root = self.desktop_dir
        (root / "Network").mkdir(parents=True, exist_ok=True)
        (root / "Network" / "Cookies").write_text(f"cookies-{name}")
        (root / "Local Storage" / "leveldb").mkdir(parents=True, exist_ok=True)
        (root / "Local Storage" / "leveldb" / "000.log").write_text(f"ls-{name}")
        (root / "Local State").write_text("os-crypt-key")
        config_path = root / "config.json"
        config = read_json(config_path) if config_path.exists() else {}
        config = {
            key: value
            for key, value in config.items()
            if not key.startswith(("oauth:", "dxt:"))
        }
        config.update(
            {
                "userThemeMode": config.get("userThemeMode", "dark"),
                "lastKnownAccountUuid": f"uuid-{name}",
                "oauth:tokenCache": f"encrypted-{name}",
                f"dxt:allowlistEnabled:org-{name}": True,
            }
        )
        write_json(config_path, config)
        # 全局数据：不随账号切换。
        write_json(root / "claude_desktop_config.json", {"mcpServers": {}})
        (root / "claude-code").mkdir(exist_ok=True)

    def desktop_config(self) -> dict:
        return read_json(self.desktop_dir / "config.json")

    def cookies(self) -> str:
        return (self.desktop_dir / "Network" / "Cookies").read_text()
