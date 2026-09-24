"""在本工具中登录 Claude 账号的对话框（浏览器授权，自动回到本工具）。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import dialogs
from md3.components import progress
from md3.components import text_fields
from md3.tokens import spacing

from claude_status import models
from claude_status import oauth_login
from claude_status import state as state_module
from claude_status import switcher
from claude_status import tasks
from claude_status.widgets import common

POLL_MS = 200


class LoginDialog(dialogs.BasicDialog):
    """登录 Claude 账号并保存到账号。

    打开后立即在浏览器中打开授权页；授权完成后浏览器回调本机，本对话框
    自动换取令牌并保存，然后关闭。``account`` / ``created`` 为保存结果。

    Args:
        state: 应用状态。
        target: 要重新登录的账号；None 表示按登录结果匹配或新建账号。
        parent: 父控件。
    """

    def __init__(
        self,
        state: state_module.AppState,
        target: models.Account | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        headline = (
            f"登录「{target.display_name}」" if target else "登录 Claude 账号"
        )
        super().__init__(
            headline,
            "将在浏览器中打开 Claude 的登录页，登录并授权后会自动回到这里。"
            "登录在浏览器中完成，本工具不会接触你的密码。",
            parent=parent,
        )
        self._state = state
        self._target = target
        self.account: models.Account | None = None
        self.created = False
        self._manual = False
        self._busy = False
        self._server: oauth_login.CallbackServer | None = None
        self._pkce: oauth_login.Pkce | None = None
        self._redirect = ""
        self._url = ""
        self._build_content()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._start()

    # ---- 界面 -------------------------------------------------------------

    def _build_content(self) -> None:
        content = QtWidgets.QWidget()
        content.setMinimumWidth(440)
        column = QtWidgets.QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(round(spacing.SPACE_3))
        self._spinner = progress.CircularProgressIndicator(None)
        self._spinner.setFixedSize(28, 28)
        self._status = common.label("", "body-medium", wrap=True)
        status_row = QtWidgets.QHBoxLayout()
        status_row.setSpacing(round(spacing.SPACE_3))
        status_row.addWidget(self._spinner)
        status_row.addWidget(self._status, 1)  # 换行的文字占满剩余宽度
        column.addLayout(status_row)
        self._reopen = buttons.TextButton("重新打开浏览器", icon="open_in_browser")
        self._reopen.clicked.connect(self._open_browser)
        self._copy = buttons.TextButton("复制登录链接", icon="content_copy")
        self._copy.clicked.connect(self._copy_link)
        self._switch = buttons.TextButton("改用授权码", icon="password")
        self._switch.setToolTip(
            "浏览器没有自动回到本工具（例如在另一台设备上登录）时使用"
        )
        self._switch.clicked.connect(self._use_manual)
        column.addLayout(common.row(self._reopen, self._copy, self._switch, None))
        self._code = text_fields.OutlinedTextField(
            "授权码",
            "",
            leading_icon="key",
            supporting_text="登录后页面上显示的授权码（形如 xxxx#yyyy）",
        )
        self._code.return_pressed.connect(self._submit_code)
        self._code.hide()
        column.addWidget(self._code)
        self._error = common.label("", "body-small", "error", wrap=True)
        self._error.hide()
        column.addWidget(self._error)
        self.set_content(content)
        self.add_action("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self._retry = self.add_action(
            "重新登录", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
        )
        self._retry.clicked.connect(self._restart)
        self._retry.hide()
        self._finish = self.add_action(
            "完成", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
        )
        self._finish.clicked.connect(self._submit_code)
        self._finish.hide()

    def _set_status(self, text: str, busy: bool = True) -> None:
        self._status.setText(text)
        self._spinner.setVisible(busy)

    def _fail(self, message: str) -> None:
        self._busy = False
        self._timer.stop()
        self._error.setText(message)
        self._error.show()
        self._set_status("登录没有完成。", busy=False)
        self._retry.show()
        self._finish.setEnabled(True)

    # ---- 流程 -------------------------------------------------------------

    def _start(self) -> None:
        """准备一次新的登录：新的 PKCE、回调服务与授权地址。"""
        self._stop_server()
        self._pkce = oauth_login.Pkce.create()
        hint = self._target.email if self._target else ""
        if self._manual:
            redirect = oauth_login.MANUAL_REDIRECT_URL
        else:
            self._server = oauth_login.CallbackServer(self._pkce.state)
            self._server.start()
            redirect = oauth_login.local_redirect_uri(self._server.port)
            self._timer.start()
        self._redirect = redirect
        self._url = oauth_login.authorize_url(self._pkce, redirect, hint)
        self._error.hide()
        self._retry.hide()
        if self._manual:
            self._set_status(
                "在浏览器中登录并授权后，页面上会显示授权码，复制后粘贴到下面。",
                busy=False,
            )
        else:
            self._set_status("正在等待你在浏览器中完成登录…")
        QtCore.QTimer.singleShot(200, self._open_browser)

    def _restart(self) -> None:
        self._code.set_text("")
        self._start()

    def _open_browser(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._url))

    def _copy_link(self) -> None:
        QtGui.QGuiApplication.clipboard().setText(self._url)
        self._copy.setText("已复制")
        QtCore.QTimer.singleShot(
            2000, lambda: self._copy.setText("复制登录链接")
        )

    def _use_manual(self) -> None:
        self._manual = True
        self._switch.hide()
        self._code.show()
        self._finish.show()
        self._start()
        QtCore.QTimer.singleShot(0, self.adjustSize)

    def _poll(self) -> None:
        server = self._server
        if server is None or not server.done or self._busy:
            return
        self._timer.stop()
        if server.code:
            self._exchange(server.code)
        else:
            self._fail(server.error or "登录没有完成")

    def _submit_code(self) -> None:
        if self._busy or self._pkce is None:
            return
        try:
            code = oauth_login.parse_manual_code(self._code.text, self._pkce.state)
        except oauth_login.LoginError as exc:
            self._code.set_error(True, str(exc))
            return
        self._code.set_error(False)
        self._exchange(code)

    def _exchange(self, code: str) -> None:
        pkce, redirect = self._pkce, self._redirect
        if pkce is None:
            return
        self._busy = True
        self._finish.setEnabled(False)
        self._error.hide()
        self._set_status("已授权，正在完成登录…")
        proxy = self._state.settings.proxy
        tasks.run(
            lambda: oauth_login.complete_login(code, pkce, redirect, proxy),
            self._on_login,
            lambda error: self._fail(str(error)),
            self,
        )

    def _on_login(self, login) -> None:
        self._busy = False
        try:
            self.account, self.created = self._state.clients.add_login(
                login, self._target
            )
        except (switcher.SwitchError, OSError) as exc:
            self._fail(str(exc))
            return
        self.accept()

    def _stop_server(self) -> None:
        self._timer.stop()
        if self._server is not None:
            self._server.stop()
            self._server = None

    @override
    def done(self, result: int) -> None:
        self._stop_server()
        super().done(result)
