"""客户端页：Claude Code 与 Claude Desktop 的当前登录、保存的登录与一键切换。"""

from __future__ import annotations

import pathlib

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import charts
from md3.components import dividers
from md3.components import snackbar
from md3.tokens import spacing

from claude_status import claude_code
from claude_status import claude_desktop
from claude_status import code_config
from claude_status import formatting
from claude_status import models
from claude_status import quota as quota_module
from claude_status import secure
from claude_status import state as state_module
from claude_status.pages import actions
from claude_status.widgets import account_card
from claude_status.widgets import common
from claude_status.widgets import dense_charts
from claude_status.widgets import quota_meter

LOGIN_COMMAND = "claude /login"
# 额度走势最多显示的采样数（Desktop 约每 15 分钟采样一次）。
HISTORY_SAMPLES = 48
_SECRET_KEYS = (code_config.AUTH_TOKEN_KEY, code_config.API_KEY_KEY)


def open_path(path: pathlib.Path) -> None:
    """用系统默认程序打开文件或目录。"""
    QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(path)))


def _column() -> tuple[QtWidgets.QWidget, QtWidgets.QVBoxLayout]:
    content = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(round(spacing.SPACE_3))
    return content, layout


def _details(rows: list[tuple[str, str, str]]) -> QtWidgets.QWidget:
    """两列的"名称：值"表格，每行为 (名称, 值, 值的颜色角色)。"""
    content = QtWidgets.QWidget()
    grid = QtWidgets.QGridLayout(content)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(round(spacing.SPACE_6))
    grid.setVerticalSpacing(round(spacing.SPACE_2))
    for index, (name, value, color) in enumerate(rows):
        grid.addWidget(
            common.label(name, "label-large", "on_surface_variant"),
            index,
            0,
            QtCore.Qt.AlignmentFlag.AlignTop,
        )
        grid.addWidget(
            common.label(value, "body-medium", color, selectable=True, wrap=True),
            index,
            1,
        )
    grid.setColumnStretch(1, 1)
    return content


def _hint(text: str) -> QtWidgets.QLabel:
    return common.label(text, "body-medium", "on_surface_variant", wrap=True)


def _command_line(server: dict) -> str:
    """MCP 服务器的启动命令（或 URL）与参数。"""
    parts = [str(server.get("command") or server.get("url") or "—")]
    args = server.get("args")
    if isinstance(args, list):
        parts.extend(str(arg) for arg in args)
    text = " ".join(parts)
    env = server.get("env")
    if isinstance(env, dict) and env:
        text += f" · {len(env)} 个环境变量"
    return text


class _Slot(QtWidgets.QWidget):
    """内容可以整体替换的容器（刷新时整体替换，避免逐个删除子布局）。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._content: QtWidgets.QWidget | None = None

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """替换内容。"""
        if self._content is not None:
            self._content.hide()
            self._content.deleteLater()
        self._content = content
        self._layout.addWidget(content)


class ClientsPage(common.Page):
    """客户端页。

    Args:
        state: 应用状态。
        parent: 父控件。
    """

    def __init__(
        self,
        state: state_module.AppState,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        code_card = common.SectionCard(
            "Claude Code",
            "命令行与 IDE 插件共用 ~/.claude 中的订阅登录；settings.json 中"
            "配置了中转 / API 时优先使用该配置。",
        )
        folder = buttons.IconButton("folder_open", tooltip="打开配置目录")
        folder.clicked.connect(lambda: open_path(claude_code.config_dir()))
        code_card.add_header_widget(folder)
        self._code = _Slot()
        code_card.add_widget(self._code)
        self.body.addWidget(code_card)
        desktop_card = common.SectionCard(
            "Claude Desktop",
            "桌面应用的登录会话可以按账号保存、一键切换；切换时需要重启 Desktop。",
        )
        self._desktop = _Slot()
        desktop_card.add_widget(self._desktop)
        self.body.addWidget(desktop_card)
        self.body.addWidget(
            common.label(
                f"保存的登录{secure.description()}，存放在 "
                f"{state.clients.vault.root}；每次切换 Claude Code 前都会"
                "备份当前配置，可在切换后的提示条中撤销。",
                "body-small",
                "on_surface_variant",
                selectable=True,
                wrap=True,
            )
        )
        self.body.addStretch(1)
        state.clients.changed.connect(self.refresh)
        state.accounts_changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        """按两个客户端的最新状态重建内容。"""
        self._code.set_content(self._code_content())
        self._desktop.set_content(self._desktop_content())

    # ---- 通用 -------------------------------------------------------------

    def _account_row(
        self,
        account: models.Account,
        subtitle: str,
        current: bool,
        trailing: list[QtWidgets.QWidget],
    ) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(round(spacing.SPACE_3))
        layout.addWidget(account_card.account_avatar(account, 36))
        texts = QtWidgets.QVBoxLayout()
        texts.setSpacing(0)
        texts.addWidget(common.ElidedLabel(account.display_name, "title-small"))
        texts.addWidget(
            common.ElidedLabel(subtitle, "body-small", "on_surface_variant")
        )
        layout.addLayout(texts, 1)
        if current:
            layout.addWidget(common.Pill("使用中", "primary_solid", "check"))
        for widget in trailing:
            layout.addWidget(widget)
        return row

    def _switch_button(
        self, account: models.Account, code: bool, desktop: bool
    ) -> buttons.TextButton:
        button = buttons.TextButton("切换", icon="swap_horiz")
        button.setToolTip(account_card.switch_description(code, desktop))
        button.clicked.connect(
            lambda: actions.switch_account(
                self, self._state, account, code, desktop
            )
        )
        return button

    def _forget_button(
        self, account: models.Account, desktop: bool
    ) -> buttons.IconButton:
        button = buttons.IconButton("delete", tooltip="删除保存的登录")
        button.clicked.connect(
            lambda: actions.forget_login(self, self._state, account, desktop)
        )
        return button

    # ---- Claude Code ------------------------------------------------------

    def _effective_text(self) -> str:
        clients = self._state.clients
        if clients.provider_env:
            owner = clients.env_owner()
            if owner is None:
                return "中转 / API 配置（尚未保存为账号）"
            return f"中转 / API 配置 · {owner.display_name}"
        login = clients.code_login
        if login is None:
            return "未登录"
        owner = clients.code_owner()
        if owner is None:
            return f"订阅登录 · {login.email or '未知账号'}（尚未保存）"
        return f"订阅登录 · {owner.display_name}"

    def _login_text(self) -> str:
        clients = self._state.clients
        login = clients.code_login
        if login is None:
            return f"未登录（在终端运行 {LOGIN_COMMAND} 登录）"
        parts = [
            login.email or "未知邮箱",
            login.subscription_type.capitalize() or "未知套餐",
        ]
        expires = login.expires_at
        if expires is not None and login.expired():
            parts.append("访问令牌已过期，使用 Claude Code 时会自动续期")
        elif expires is not None:
            parts.append(f"令牌有效至 {formatting.datetime_text(expires)}")
        owner = clients.code_owner()
        if owner is not None and clients.vault.has_code(owner.id):
            parts.append(f"已保存到「{owner.display_name}」")
        else:
            parts.append("尚未保存")
        if clients.provider_env:
            parts.append("当前被中转 / API 配置覆盖")
        return " · ".join(parts)

    def _env_text(self) -> str:
        clients = self._state.clients
        env = clients.provider_env
        if not env:
            return "未配置（使用订阅登录）"
        parts = [env.get(code_config.BASE_URL_KEY) or "官方 API"]
        secret = next((env[key] for key in _SECRET_KEYS if env.get(key)), "")
        parts.append(
            f"密钥 {models.mask_secret(secret)}" if secret else "未设置密钥"
        )
        extra = sum(1 for key in env if key not in code_config.IDENTITY_KEYS)
        if extra:
            parts.append(f"另有 {extra} 个变量（模型映射等）")
        owner = clients.env_owner()
        parts.append(
            f"已保存为「{owner.display_name}」" if owner else "尚未保存为账号"
        )
        return " · ".join(parts)

    def _code_content(self) -> QtWidgets.QWidget:
        clients = self._state.clients
        content, layout = _column()
        layout.addWidget(
            _details(
                [
                    ("当前生效", self._effective_text(), "primary"),
                    ("订阅登录", self._login_text(), "on_surface"),
                    ("中转 / API", self._env_text(), "on_surface"),
                ]
            )
        )
        save = buttons.FilledTonalButton("保存当前登录", icon="save")
        save.setEnabled(clients.code_login is not None)
        save.setToolTip("把当前的订阅登录保存到对应账号（没有时新建账号）")
        save.clicked.connect(lambda: actions.capture_code(self, self._state))
        import_env = buttons.OutlinedButton("保存中转配置为账号", icon="hub")
        import_env.setEnabled(
            bool(clients.provider_env) and clients.env_owner() is None
        )
        import_env.clicked.connect(
            lambda: actions.import_provider_env(self, self._state)
        )
        copy = buttons.TextButton("复制登录命令", icon="content_copy")
        copy.setToolTip(
            f"添加账号：在终端运行 {LOGIN_COMMAND} 登录后，点击“保存当前登录”"
        )
        copy.clicked.connect(self._copy_login_command)
        layout.addLayout(common.row(save, import_env, copy, None))
        layout.addWidget(dividers.Divider())
        layout.addWidget(common.label("可切换的账号", "title-small"))
        rows = [self._code_row(account) for account in self._state.accounts]
        rows = [row for row in rows if row is not None]
        for row in rows:
            layout.addWidget(row)
        if not rows:
            layout.addWidget(
                _hint(
                    "还没有可切换的账号：点击“保存当前登录”保存订阅登录，或在"
                    "账号页为中转 / API 账号填写 Base URL 与密钥。"
                )
            )
        return content

    def _code_row(self, account: models.Account) -> QtWidgets.QWidget | None:
        clients = self._state.clients
        info = clients.info(account)
        if account.auth_type is models.AuthType.OAUTH:
            if not (info.code_saved or info.code_current):
                return None
            meta = clients.vault.code_meta(account.id) or {}
            email = meta.get("email") or account.email or "未知邮箱"
            if info.code_saved:
                saved = f"保存于 {formatting.relative(meta.get('saved_at'))}"
            else:
                saved = "尚未保存"
            subtitle = f"订阅登录 · {email} · {saved}"
        else:
            if not info.code_ready:
                return None
            parts = [account.auth_type.label, account.base_url or "官方 API"]
            if account.api_key:
                parts.append(account.masked_key())
            subtitle = " · ".join(parts)
        trailing: list[QtWidgets.QWidget] = []
        if info.code_ready and not info.code_current:
            trailing.append(self._switch_button(account, True, False))
        if info.code_saved:
            trailing.append(self._forget_button(account, desktop=False))
        return self._account_row(account, subtitle, info.code_current, trailing)

    def _copy_login_command(self) -> None:
        QtGui.QGuiApplication.clipboard().setText(LOGIN_COMMAND)
        snackbar.show(
            self,
            f"已复制 {LOGIN_COMMAND}：在终端运行并登录后，回到这里点击“保存当前登录”",
            duration_ms=6000,
        )

    # ---- Claude Desktop ---------------------------------------------------

    def _desktop_content(self) -> QtWidgets.QWidget:
        clients = self._state.clients
        desktop = clients.desktop
        content, layout = _column()
        if desktop is None:
            layout.addWidget(_hint("无法读取 Claude Desktop 的状态。"))
            return content
        if not desktop.exists and not desktop.install.installed:
            layout.addWidget(
                _hint(
                    "没有检测到 Claude Desktop。安装并登录后，这里会显示它的"
                    "登录状态。"
                )
            )
            return content
        layout.addWidget(_details(self._desktop_rows(desktop)))
        save = buttons.FilledTonalButton("保存当前登录…", icon="save")
        save.setEnabled(desktop.logged_in)
        save.setToolTip("把 Desktop 当前的登录会话保存到账号，之后可以一键切换回来")
        save.clicked.connect(lambda: actions.capture_desktop(self, self._state))
        new_login = buttons.OutlinedButton("登录新账号…", icon="person_add")
        new_login.setToolTip("保存当前会话后清空登录，并启动 Desktop 登录其他账号")
        new_login.clicked.connect(
            lambda: actions.new_desktop_login(self, self._state)
        )
        if desktop.running:
            toggle = buttons.TextButton("退出 Desktop", icon="power_settings_new")
            toggle.clicked.connect(
                lambda: actions.quit_desktop(self, self._state)
            )
        else:
            toggle = buttons.TextButton("启动 Desktop", icon="play_arrow")
            toggle.setEnabled(desktop.install.installed)
            toggle.clicked.connect(
                lambda: actions.launch_desktop(self, self._state)
            )
        folder = buttons.TextButton("打开数据目录", icon="folder_open")
        folder.setEnabled(desktop.exists)
        folder.clicked.connect(lambda: open_path(desktop.data_dir))
        layout.addLayout(common.row(save, new_login, toggle, folder, None))
        layout.addWidget(dividers.Divider())
        layout.addWidget(common.label("已保存的登录会话", "title-small"))
        current = clients.current_desktop_account()
        rows = 0
        for account in self._state.accounts:
            if not clients.vault.has_desktop(account.id):
                continue
            meta = clients.vault.desktop_meta(account.id) or {}
            subtitle = f"保存于 {formatting.relative(meta.get('saved_at'))}"
            size = meta.get("size")
            if isinstance(size, int):
                subtitle += f" · {formatting.size(size)}"
            is_current = account is current
            trailing: list[QtWidgets.QWidget] = []
            if not is_current:
                trailing.append(self._switch_button(account, False, True))
            trailing.append(self._forget_button(account, desktop=True))
            layout.addWidget(
                self._account_row(account, subtitle, is_current, trailing)
            )
            rows += 1
        if not rows:
            layout.addWidget(
                _hint(
                    "还没有保存的会话：点击“保存当前登录…”保存 Desktop 当前登录的"
                    "账号；要添加其他账号，点击“登录新账号…”。"
                )
            )
        self._add_usage_history(layout, desktop)
        self._add_mcp_servers(layout, desktop)
        return content

    def _desktop_rows(
        self, desktop: claude_desktop.DesktopState
    ) -> list[tuple[str, str, str]]:
        clients = self._state.clients
        install = desktop.install
        version = f" {install.version}" if install.version else ""
        if desktop.running:
            running = f"运行中（{len(desktop.processes)} 个进程）"
        else:
            running = "未运行"
        current = clients.current_desktop_account()
        if not desktop.logged_in:
            login = "未登录"
        elif current is None:
            login = "未识别的账号（尚未保存）"
        elif clients.vault.has_desktop(current.id):
            login = f"{current.display_name}（已保存）"
        else:
            login = f"{current.display_name}（尚未保存）"
        return [
            ("安装", f"{install.label}{version}", "on_surface"),
            ("运行状态", running, "on_surface"),
            ("当前登录", login, "primary"),
            ("数据目录", str(desktop.data_dir), "on_surface_variant"),
        ]

    def _add_usage_history(
        self,
        layout: QtWidgets.QVBoxLayout,
        desktop: claude_desktop.DesktopState,
    ) -> None:
        if not desktop.samples:
            return
        org = desktop.samples[-1].org
        recent = [s for s in desktop.samples if s.org == org][-HISTORY_SAMPLES:]
        latest = recent[-1]
        owner = next(
            (a for a in self._state.accounts if org and a.org_uuid == org), None
        )
        who = owner.display_name if owner else "最近登录的账号"
        layout.addWidget(dividers.Divider())
        layout.addWidget(
            common.label(f"订阅额度 · {who}（Desktop 采样）", "title-small")
        )
        quota = quota_module.from_desktop_sample(
            latest.usage, int(latest.time.timestamp() * 1000)
        )
        lines = quota_meter.quota_lines(quota)
        width = quota_meter.title_width(lines)
        for line in lines:
            meter = quota_meter.QuotaMeter(title_width=width)
            meter.set_line(line)
            layout.addWidget(meter)
        if len(recent) < 2:
            return
        chart = dense_charts.DenseLineChart(
            [
                charts.Series(
                    "5 小时", [float(s.usage.get("fh") or 0) for s in recent]
                ),
                charts.Series(
                    "本周", [float(s.usage.get("sd") or 0) for s in recent]
                ),
            ],
            [s.time.strftime("%m-%d %H:%M") for s in recent],
            smooth=False,  # 5 小时窗口重置时陡降，平滑曲线会冲出坐标范围
            show_points=False,
        )
        chart.set_y_range(0, 100)
        chart.set_value_formatter(lambda v: f"{v:.0f}%")
        chart.setMinimumHeight(200)
        layout.addWidget(chart)

    def _add_mcp_servers(
        self,
        layout: QtWidgets.QVBoxLayout,
        desktop: claude_desktop.DesktopState,
    ) -> None:
        layout.addWidget(dividers.Divider())
        config = desktop.data_dir / claude_desktop.MCP_CONFIG_NAME
        edit = buttons.TextButton("打开配置文件", icon="edit_note")
        edit.setEnabled(config.is_file())
        edit.clicked.connect(lambda: open_path(config))
        title = common.label(
            f"MCP 服务器（{len(desktop.mcp_servers)}）", "title-small"
        )
        layout.addLayout(common.row(title, None, edit))
        if not desktop.mcp_servers:
            layout.addWidget(
                _hint(
                    "没有配置 MCP 服务器。MCP 配置属于 Desktop 的全局设置，"
                    "切换账号时保持不变。"
                )
            )
            return
        for name, server in desktop.mcp_servers.items():
            row = QtWidgets.QWidget()
            row_layout = QtWidgets.QHBoxLayout(row)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(round(spacing.SPACE_3))
            row_layout.addWidget(common.IconBadge("extension", "secondary", 36))
            texts = QtWidgets.QVBoxLayout()
            texts.setSpacing(0)
            texts.addWidget(common.ElidedLabel(name, "title-small"))
            texts.addWidget(
                common.ElidedLabel(
                    _command_line(server), "body-small", "on_surface_variant"
                )
            )
            row_layout.addLayout(texts, 1)
            layout.addWidget(row)
