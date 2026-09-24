"""新建 / 编辑账号对话框。"""

from __future__ import annotations

import dataclasses
import re

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import dialogs
from md3.components import selection
from md3.components import text_fields
from md3.tokens import spacing

from claude_status import code_config
from claude_status import models

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_OUTLINED = text_fields.TextFieldVariant.OUTLINED
_PLANS = list(models.Plan)
_AUTHS = list(models.AuthType)
_STATUSES = list(models.AccountStatus)


def _required(text: str) -> str | None:
    return None if text.strip() else "请输入名称"


def _email(text: str) -> str | None:
    if not text.strip() or _EMAIL.match(text.strip()):
        return None
    return "邮箱格式不正确"


def _env(text: str) -> str | None:
    try:
        code_config.parse_env_lines(text)
    except ValueError as exc:
        return str(exc)
    return None


def _url(text: str) -> str | None:
    value = text.strip()
    if not value or value.startswith(("http://", "https://")):
        return None
    return "需以 http:// 或 https:// 开头"


class AccountDialog(dialogs.BasicDialog):
    """账号表单。

    Args:
        account: 要编辑的账号；None 表示新建。
        tag_suggestions: 标签补全候选。
        duplicate_email: 判断邮箱是否已被其他账号使用的函数。
        parent: 父控件。
    """

    def __init__(
        self,
        account: models.Account | None,
        tag_suggestions: list[str],
        duplicate_email=None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        self._creating = account is None
        super().__init__(
            "新建账号" if self._creating else "编辑账号",
            "账号信息只保存在本机。" if self._creating else "",
            parent=parent,
        )
        self._account = (
            dataclasses.replace(account)
            if account is not None
            else models.Account()
        )
        self._duplicate_email = duplicate_email
        source = self._account
        form = QtWidgets.QWidget()
        form.setMinimumWidth(500)
        grid = QtWidgets.QGridLayout(form)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(round(spacing.SPACE_3))
        grid.setVerticalSpacing(round(spacing.SPACE_2))

        self.name = text_fields.OutlinedTextField(
            "名称 *", source.name, validator=_required, clearable=True
        )
        self.email = text_fields.OutlinedTextField(
            "邮箱", source.email, validator=_email, leading_icon="mail"
        )
        grid.addWidget(self.name, 0, 0)
        grid.addWidget(self.email, 0, 1)

        self.plan = text_fields.SelectField(
            "套餐", [plan.label for plan in _PLANS], _PLANS.index(source.plan)
        )
        self.status = text_fields.SelectField(
            "状态",
            [status.label for status in _STATUSES],
            _STATUSES.index(source.status),
        )
        grid.addWidget(self.plan, 1, 0)
        grid.addWidget(self.status, 1, 1)

        self.auth = text_fields.SelectField(
            "认证方式",
            [auth.label for auth in _AUTHS],
            _AUTHS.index(source.auth_type),
        )
        self.organization = text_fields.OutlinedTextField(
            "组织", source.organization, leading_icon="apartment"
        )
        grid.addWidget(self.auth, 2, 0)
        grid.addWidget(self.organization, 2, 1)

        self.api_key = text_fields.PasswordField(
            "API Key / 令牌",
            source.api_key,
            show_strength=False,
            variant=_OUTLINED,
            supporting_text="加密保存在本机",
        )
        grid.addWidget(self.api_key, 3, 0, 1, 2)
        self.base_url = text_fields.OutlinedTextField(
            "Base URL",
            source.base_url,
            placeholder="https://api.anthropic.com",
            validator=_url,
            leading_icon="link",
        )
        grid.addWidget(self.base_url, 4, 0, 1, 2)
        self.env = text_fields.TextArea(
            "额外环境变量",
            code_config.format_env_lines(source.env),
            min_rows=2,
            max_rows=5,
            variant=_OUTLINED,
            validator=_env,
            supporting_text="每行一个 KEY=VALUE（模型映射等），"
            "切换时写入 Claude Code 的 settings.json",
        )
        grid.addWidget(self.env, 5, 0, 1, 2)

        self.budget = text_fields.NumberField(
            "月度预算",
            source.monthly_budget,
            minimum=0,
            maximum=1_000_000,
            step=10,
            decimals=2,
            prefix="$",
            variant=_OUTLINED,
            supporting_text="0 表示不限；按 API 价格估算",
        )
        switches = QtWidgets.QVBoxLayout()
        switches.setSpacing(0)
        self.link_local = selection.Switch("用量默认归属", source.link_local)
        self.link_local.setToolTip(
            "无法判断来源账号的本机日志用量计入此账号（同一时间只能有一个）"
        )
        self.favorite = selection.Switch("收藏", source.favorite)
        switches.addWidget(self.link_local)
        switches.addWidget(self.favorite)
        grid.addWidget(self.budget, 6, 0)
        grid.addLayout(switches, 6, 1)

        self.tags = text_fields.TagField(
            "标签", source.tags, suggestions=tag_suggestions
        )
        grid.addWidget(self.tags, 7, 0, 1, 2)
        self.notes = text_fields.TextArea(
            "备注", source.notes, min_rows=2, max_rows=4, variant=_OUTLINED
        )
        grid.addWidget(self.notes, 8, 0, 1, 2)
        self.set_content(form)

        self.add_action("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        save = self.add_action(
            "保存", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
        )
        save.clicked.connect(self._submit)
        self.name.return_pressed.connect(self._submit)
        self.auth.selection_changed.connect(self._sync_auth_fields)
        self._sync_auth_fields()
        QtCore.QTimer.singleShot(0, self.name.setFocus)

    def _sync_auth_fields(self, *_args) -> None:
        auth = _AUTHS[max(0, self.auth.selected_index)]
        self.api_key.setVisible(auth.uses_key)
        self.base_url.setVisible(auth is not models.AuthType.OAUTH)
        self.env.setVisible(auth is not models.AuthType.OAUTH)
        plan_index = self.plan.selected_index
        if (
            self._creating
            and auth is models.AuthType.API_KEY
            and plan_index >= 0
            and _PLANS[plan_index] is models.Plan.PRO
        ):
            self.plan.set_selected_index(_PLANS.index(models.Plan.API))
        self.adjustSize()

    def _submit(self) -> None:
        valid = all(
            field.validate()
            for field in (self.name, self.email, self.base_url, self.env)
            if field.isVisible()
        )
        email = self.email.text.strip()
        if valid and email and self._duplicate_email is not None:
            if self._duplicate_email(email, self._account.id):
                self.email.set_error(True, "已有账号使用此邮箱")
                valid = False
        if valid:
            self.accept()

    def result_account(self) -> models.Account:
        """表单内容对应的账号（新建时带新的 ID）。"""
        account = self._account
        account.name = self.name.text.strip()
        account.email = self.email.text.strip()
        account.plan = _PLANS[max(0, self.plan.selected_index)]
        account.status = _STATUSES[max(0, self.status.selected_index)]
        account.auth_type = _AUTHS[max(0, self.auth.selected_index)]
        account.organization = self.organization.text.strip()
        account.api_key = (
            self.api_key.text.strip() if account.auth_type.uses_key else ""
        )
        account.base_url = (
            self.base_url.text.strip()
            if account.auth_type is not models.AuthType.OAUTH
            else ""
        )
        account.env = (
            code_config.parse_env_lines(self.env.text)
            if account.auth_type is not models.AuthType.OAUTH
            else {}
        )
        account.monthly_budget = float(self.budget.value)
        account.link_local = self.link_local.checked
        account.favorite = self.favorite.checked
        account.tags = self.tags.tags
        account.notes = self.notes.text.strip()
        return account
