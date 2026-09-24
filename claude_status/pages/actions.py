"""界面操作编排：一键切换、保存登录，以及需要先退出 Claude Desktop 的操作。

需要改动 Desktop 数据的操作（切换、保存、登录新账号）都经由
``DesktopRunner``：Desktop 正在运行时先征得确认并请求其正常退出，超时
仍未退出（例如最小化到托盘）再询问是否强制结束，然后执行操作，最后按
设置重新启动 Desktop。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import dialogs
from md3.components import snackbar
from md3.components import text_fields

from claude_status import claude_desktop
from claude_status import formatting
from claude_status import models
from claude_status import state as state_module
from claude_status import switcher
from claude_status import tasks
from claude_status.pages import login_dialog
from claude_status.widgets import account_card

QUIT_TIMEOUT = 8.0
_ERRORS = (switcher.SwitchError, claude_desktop.DesktopError, OSError)


class DesktopRunner(QtCore.QObject):
    """退出 Desktop（需要时）→ 执行操作 → 按需重新启动 Desktop。

    Args:
        widget: 用于定位对话框与提示条的控件。
        state: 应用状态。
        headline: 需要退出 Desktop 时确认对话框的标题。
        action: 在 Desktop 退出后执行的操作，返回完成提示；为 None 时只
            退出 Desktop。
        launch: ``"auto"`` 按设置在原本运行时重新启动；``"always"`` 总是
            启动；``"never"`` 不启动。
    """

    finished = QtCore.Signal(bool)

    def __init__(
        self,
        widget: QtWidgets.QWidget,
        state: state_module.AppState,
        headline: str,
        action: Callable[[], str] | None,
        launch: str = "auto",
    ) -> None:
        super().__init__(widget)
        self._widget = widget
        self._state = state
        self._headline = headline
        self._action = action
        self._launch = launch
        self._was_running = False
        self._progress: dialogs.ProgressDialog | None = None

    def _window(self) -> QtWidgets.QWidget:
        return self._widget.window()

    def start(self) -> None:
        """开始执行。"""
        processes = claude_desktop.running()
        self._was_running = bool(processes)
        if not processes:
            self._run_action()
            return
        if not dialogs.confirm(
            self._window(),
            self._headline,
            "需要先退出 Claude Desktop：正在 Desktop 中进行的对话（包括"
            " Code 标签页中的会话）会被中断，完成后会按设置重新启动。",
            confirm_text="退出并继续",
            icon="desktop_windows",
        ):
            self._done(False, "")
            return
        self._show_progress("正在退出 Claude Desktop…")
        tasks.run(
            lambda: self._quit(processes, force=False),
            self._after_quit,
            self._on_error,
            self,
        )

    @staticmethod
    def _quit(processes: list[claude_desktop.Process], force: bool) -> bool:
        if force:
            claude_desktop.force_quit(claude_desktop.running() or processes)
        else:
            claude_desktop.request_quit(processes)
        return claude_desktop.wait_until_closed(QUIT_TIMEOUT)

    def _show_progress(self, text: str) -> None:
        if self._progress is None:
            self._progress = dialogs.ProgressDialog(
                "请稍候", text, None, "", self._window()
            )
        self._progress.set_supporting_text(text)
        self._progress.show()

    def _hide_progress(self) -> None:
        if self._progress is not None:
            self._progress.hide()

    def _after_quit(self, closed: bool) -> None:
        if closed:
            self._run_action()
            return
        self._hide_progress()
        if not dialogs.confirm(
            self._window(),
            "Claude Desktop 没有退出",
            "它可能被最小化到了系统托盘。是否强制结束？尚未发送的输入会丢失。",
            confirm_text="强制结束",
            icon="warning",
        ):
            self._done(False, "已取消，Claude Desktop 仍在运行")
            return
        self._show_progress("正在结束 Claude Desktop…")
        tasks.run(
            lambda: self._quit([], force=True),
            self._after_force,
            self._on_error,
            self,
        )

    def _after_force(self, closed: bool) -> None:
        if not closed:
            self._done(False, "无法结束 Claude Desktop，请手动退出后重试")
            return
        self._run_action()

    def _on_error(self, error: BaseException) -> None:
        self._done(False, f"操作失败：{error}")

    def _run_action(self) -> None:
        message = "Claude Desktop 已退出"
        if self._action is not None:
            self._show_progress("正在处理 Claude Desktop 数据…")
            try:
                message = self._action()
            except _ERRORS as exc:
                self._done(False, str(exc))
                return
        should_launch = self._launch == "always" or (
            self._launch == "auto"
            and self._was_running
            and self._state.settings.relaunch_desktop
        )
        if should_launch:
            install = claude_desktop.detect_install()
            if claude_desktop.launch(install):
                message += "，正在重新启动 Claude Desktop"
        self._done(True, message)

    def _done(self, ok: bool, message: str) -> None:
        if self._progress is not None:
            self._progress.hide()
            self._progress.deleteLater()
            self._progress = None
        if message:
            snackbar.show(self._widget, message, duration_ms=5000)
        self._state.clients.refresh()
        self.finished.emit(ok)
        self.deleteLater()


def _alert(widget: QtWidgets.QWidget, headline: str, text: str) -> None:
    dialogs.alert(widget.window(), headline, text, icon="info")


def login_account(
    widget: QtWidgets.QWidget,
    state: state_module.AppState,
    target: models.Account | None = None,
    announce: bool = True,
) -> models.Account | None:
    """在本工具中登录 Claude 账号（浏览器授权），返回保存到的账号。"""
    if state.clients.offline:
        _alert(widget, "无法登录", "已通过 --offline 参数禁用联网，登录需要联网。")
        return None
    dialog = login_dialog.LoginDialog(state, target, widget.window())
    accepted = dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted
    account = dialog.account if accepted else None
    dialog.deleteLater()
    if account is not None and announce:
        verb = "已新建账号" if dialog.created else "已保存到"
        snackbar.show(
            widget,
            f"登录成功，{verb}「{account.display_name}」；点击“切换”即可让 "
            "Claude Code 使用它",
            duration_ms=6000,
        )
    return account


def _login_then_switch(
    widget: QtWidgets.QWidget,
    state: state_module.AppState,
    account: models.Account,
    code: bool | None,
    desktop: bool | None,
) -> None:
    """订阅账号还没有 Claude Code 登录：征得同意后先登录，再继续切换。"""
    if not dialogs.confirm(
        widget.window(),
        f"先登录「{account.display_name}」？",
        "该账号还没有 Claude Code 登录。在浏览器中登录并授权后，会自动继续切换。",
        confirm_text="登录并切换",
        icon="login",
    ):
        return
    if login_account(widget, state, account, announce=False) is not None:
        switch_account(widget, state, account, code, desktop)


def desktop_available() -> bool:
    """是否检测到 Claude Desktop（数据目录存在）。"""
    return claude_desktop.data_dir().is_dir()


def switch_account(
    widget: QtWidgets.QWidget,
    state: state_module.AppState,
    account: models.Account,
    code: bool | None = None,
    desktop: bool | None = None,
) -> None:
    """切换到该账号；两者都未指定时按设置决定切换哪些客户端。"""
    if state.demo_forced:
        snackbar.show(widget, "演示模式下不会切换真实的 Claude Code / Desktop")
        return
    clients = state.clients
    info = clients.info(account)
    if code is None and desktop is None:
        include_desktop = state.settings.switch_desktop and desktop_available()
        code, desktop = info.switch_targets(include_desktop)
        if not code and not desktop:
            if info.code_current or info.desktop_current:
                snackbar.show(
                    widget, f"「{account.display_name}」已是当前使用的账号"
                )
            elif account.auth_type is models.AuthType.OAUTH:
                _login_then_switch(widget, state, account, None, None)
            else:
                _ready, reason = clients.switcher.code_ready(
                    account, state.accounts
                )
                _alert(widget, "无法切换到该账号", reason)
            return
    code, desktop = bool(code), bool(desktop)
    if code and not info.code_ready:
        if account.auth_type is models.AuthType.OAUTH:
            _login_then_switch(widget, state, account, code, desktop)
            return
        _ready, reason = clients.switcher.code_ready(account, state.accounts)
        _alert(widget, "无法切换 Claude Code", reason)
        return
    if desktop and not info.desktop_saved:
        _alert(
            widget,
            "无法切换 Claude Desktop",
            "该账号还没有保存 Claude Desktop 会话：请先在 Desktop 中登录"
            "该账号，再在“客户端”页点击“保存会话…”。",
        )
        return
    if not code and not desktop:
        return
    name = account.display_name
    if not desktop:
        try:
            result = clients.switch_code(account)
        except _ERRORS as exc:
            _alert(widget, "切换失败", str(exc))
            return
        message = f"Claude Code 已切换到「{name}」"
        created = result.preserved.created
        if created:
            names = "、".join(a.display_name for a in created)
            message += f"（原配置已保存为「{names}」）"
        snackbar.show(
            widget,
            message,
            "撤销",
            lambda: clients.undo_code(result.backup),
            duration_ms=8000,
        )
        return

    def action() -> str:
        parts = []
        if code:
            clients.switch_code(account)
            parts.append("Claude Code")
        clients.switch_desktop(account)
        parts.append("Claude Desktop")
        return f"{' 与 '.join(parts)} 已切换到「{name}」"

    DesktopRunner(
        widget,
        state,
        account_card.switch_description(code, True),
        action,
    ).start()


def capture_code(widget: QtWidgets.QWidget, state: state_module.AppState) -> None:
    """保存当前的 Claude Code 订阅登录。"""
    try:
        account, created = state.clients.capture_code()
    except _ERRORS as exc:
        _alert(widget, "无法保存登录", str(exc))
        return
    verb = "已新建账号并保存" if created else "已保存到"
    snackbar.show(
        widget, f"Claude Code 登录{verb}「{account.display_name}」"
    )


def import_provider_env(
    widget: QtWidgets.QWidget, state: state_module.AppState
) -> None:
    """把当前的中转 / API 配置保存为账号。"""
    account = state.clients.import_provider_env()
    if account is None:
        snackbar.show(widget, "Claude Code 当前没有中转 / API 配置")
        return
    snackbar.show(widget, f"当前配置已保存为「{account.display_name}」")


def choose_account(
    widget: QtWidgets.QWidget,
    state: state_module.AppState,
    headline: str,
    text: str,
    preferred: models.Account | None,
    confirm_text: str = "保存",
    claude_uuid: str = "",
) -> tuple[models.Account, bool] | None:
    """让用户选择一个订阅账号或“新建账号”，返回 (账号, 是否新建)。

    新建的账号还没有加入账号列表，由调用方在操作成功后加入，取消或失败时
    不会留下空账号。``claude_uuid`` 不为空时，标出记录着其他 Claude 账号的
    选项。
    """
    oauth = [
        a for a in state.accounts if a.auth_type is models.AuthType.OAUTH
    ]
    options = []
    for account in oauth:
        detail = account.email or "未填写邮箱"
        if claude_uuid and account.claude_uuid not in ("", claude_uuid):
            detail += " · 对应其他 Claude 账号"
        options.append(f"{account.display_name}（{detail}）")
    options.append("＋ 新建账号")
    index = oauth.index(preferred) if preferred in oauth else len(oauth)
    dialog = dialogs.BasicDialog(headline, text, parent=widget.window())
    field = text_fields.SelectField("账号", options, index)
    field.setMinimumWidth(400)
    dialog.set_content(field)
    dialog.add_action("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
    dialog.add_action(confirm_text)
    if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
        return None
    chosen = field.selected_index
    if 0 <= chosen < len(oauth):
        return oauth[chosen], False
    account = models.Account(
        name="Claude Desktop 账号",
        tags=["Claude Desktop"],
        notes="关联 Claude Desktop 登录时新建，可编辑名称与邮箱。",
    )
    return account, True


def _desktop_candidate(state: state_module.AppState) -> models.Account | None:
    """关联 Desktop 时预选的账号：之前为 Desktop 新建、还没有身份的账号。"""
    return next(
        (
            a
            for a in state.accounts
            if a.auth_type is models.AuthType.OAUTH
            and not a.claude_uuid
            and "Claude Desktop" in a.tags
        ),
        None,
    )


def link_desktop(
    widget: QtWidgets.QWidget,
    state: state_module.AppState,
    account: models.Account | None = None,
    offer_save: bool = True,
) -> models.Account | None:
    """把 Desktop 当前登录的账号关联到账号（不需要退出 Desktop）。

    未指定账号时让用户选择。关联后即可显示该账号的额度，Desktop Code
    标签页的用量也会计入它；返回关联的账号，取消或失败时返回 None。
    """
    clients = state.clients
    desktop = clients.desktop
    if desktop is None or not desktop.logged_in:
        _alert(widget, "无法关联", "Claude Desktop 当前没有登录。")
        return None
    created = False
    if account is None:
        chosen = choose_account(
            widget,
            state,
            "关联 Claude Desktop 账号",
            "Desktop 当前登录的是哪个账号？关联后会显示它的 5 小时与每周"
            "额度，Code 标签页的用量也会计入该账号；不需要退出 Desktop。",
            _desktop_candidate(state),
            confirm_text="关联",
            claude_uuid=desktop.account_uuid,
        )
        if chosen is None:
            return None
        account, created = chosen
    if created:
        state.accounts.append(account)
    try:
        clients.link_desktop(account)
    except _ERRORS as exc:
        if created:
            state.accounts.remove(account)
        _alert(widget, "无法关联", str(exc))
        return None
    if offer_save and not clients.vault.has_desktop(account.id):
        snackbar.show(
            widget,
            f"Desktop 已关联到「{account.display_name}」；保存会话后可以一键切换回来",
            "保存会话",
            lambda: capture_desktop(widget, state),
            duration_ms=8000,
        )
    elif offer_save:
        snackbar.show(widget, f"Desktop 已关联到「{account.display_name}」")
    return account


def capture_desktop(
    widget: QtWidgets.QWidget, state: state_module.AppState
) -> None:
    """保存 Desktop 当前登录的会话（需要退出 Desktop），之后可一键切换回来。

    当前登录还没有关联账号时先关联。
    """
    clients = state.clients
    desktop = clients.desktop
    if desktop is None or not desktop.logged_in:
        _alert(widget, "无法保存", "Claude Desktop 当前没有登录。")
        return
    target = clients.current_desktop_account()
    if target is None:
        target = link_desktop(widget, state, offer_save=False)
        if target is None:
            return
    account = target

    def action() -> str:
        size = clients.capture_desktop(account)
        return (
            f"Desktop 会话已保存到「{account.display_name}」"
            f"（{formatting.size(size)}）"
        )

    DesktopRunner(widget, state, "保存 Claude Desktop 会话", action).start()


def new_desktop_login(
    widget: QtWidgets.QWidget, state: state_module.AppState
) -> None:
    """保存当前 Desktop 会话后清空登录，并启动 Desktop 以登录新账号。"""
    if not dialogs.confirm(
        widget.window(),
        "在 Claude Desktop 中登录新账号？",
        "当前的登录会话会先保存到它所属的账号（无法识别时另存备份），然后"
        "清空登录并启动 Desktop。登录新账号后，回到这里点击“保存当前登录”。",
        confirm_text="继续",
        icon="person_add",
    ):
        return

    def action() -> str:
        result = state.clients.new_desktop_login()
        if result.previous is not None:
            name = result.previous.display_name
            return f"原登录已保存到「{name}」，请在 Desktop 中登录新账号"
        if result.unassigned_backup is not None:
            return "原登录已另存备份，请在 Desktop 中登录新账号"
        return "请在 Claude Desktop 中登录新账号"

    DesktopRunner(
        widget, state, "登录新账号", action, launch="always"
    ).start()


def forget_login(
    widget: QtWidgets.QWidget,
    state: state_module.AppState,
    account: models.Account,
    desktop: bool,
) -> None:
    """确认后删除账号保存的 Claude Code 登录或 Desktop 会话。"""
    client = "Claude Desktop" if desktop else "Claude Code"
    if not dialogs.confirm(
        widget.window(),
        f"删除保存的 {client} 登录？",
        f"删除后将无法一键把 {client} 切换到「{account.display_name}」，"
        "需要重新登录并保存。",
        confirm_text="删除",
        icon="key_off",
    ):
        return
    if desktop:
        state.clients.forget_desktop(account)
    else:
        state.clients.forget_code(account)
    snackbar.show(widget, f"已删除「{account.display_name}」的 {client} 登录")


def quit_desktop(widget: QtWidgets.QWidget, state: state_module.AppState) -> None:
    """退出 Claude Desktop。"""
    DesktopRunner(
        widget, state, "退出 Claude Desktop？", None, launch="never"
    ).start()


def launch_desktop(
    widget: QtWidgets.QWidget, state: state_module.AppState
) -> None:
    """启动 Claude Desktop。"""
    install = claude_desktop.detect_install()
    if claude_desktop.launch(install):
        snackbar.show(widget, "正在启动 Claude Desktop…")
    else:
        snackbar.show(widget, "没有找到 Claude Desktop 的安装")
    QtCore.QTimer.singleShot(4000, state.clients.refresh)

