"""账号卡片：头像、状态、客户端登录、额度、本月用量、预算与快捷操作。"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import avatar
from md3.components import buttons
from md3.components import cards
from md3.components import progress
from md3.tokens import spacing

from claude_status import analytics
from claude_status import client_state
from claude_status import formatting
from claude_status import models
from claude_status.widgets import common
from claude_status.widgets import quota_meter

_AVATAR_STATUS = {
    models.AccountStatus.ACTIVE: avatar.AvatarStatus.ONLINE,
    models.AccountStatus.LIMITED: avatar.AvatarStatus.AWAY,
    models.AccountStatus.EXPIRED: avatar.AvatarStatus.BUSY,
    models.AccountStatus.DISABLED: avatar.AvatarStatus.OFFLINE,
}


def avatar_status(status: models.AccountStatus) -> avatar.AvatarStatus:
    """账号状态对应的头像状态点。"""
    return _AVATAR_STATUS[status]


def _is_cjk(char: str) -> bool:
    return 0x4E00 <= ord(char) <= 0x9FFF


def avatar_label(name: str) -> str:
    """头像文字：中文开头取首字，中英混排取第一个词的前两个字母。

    返回空字符串时由 md3 按默认规则取首字母（纯英文多词名称取各词首字母）。
    """
    name = name.strip()
    if not name:
        return ""
    if _is_cjk(name[0]):
        return name[0]
    if any(_is_cjk(char) for char in name):
        return name.split()[0][:2].upper()
    return ""


def account_avatar(account: models.Account, size: float) -> avatar.Avatar:
    """带状态点的账号头像。"""
    return avatar.Avatar(
        account.display_name,
        size=size,
        status=avatar_status(account.status),
        label=avatar_label(account.display_name),
    )


def status_pill(status: models.AccountStatus) -> common.Pill:
    """账号状态标签。"""
    return common.Pill(status.label, status.color_role, status.icon)


def client_pills(
    account: models.Account, info: client_state.ClientInfo
) -> list[common.Pill]:
    """套餐与两个客户端的登录状态标签。"""
    pills = [common.Pill(account.plan.label, "secondary", "workspace_premium")]
    if info.code_current:
        pills.append(common.Pill("Code 使用中", "primary_solid", "terminal"))
    elif info.code_saved:
        pills.append(common.Pill("Code", "tertiary", "terminal"))
    if info.desktop_current:
        pills.append(
            common.Pill("Desktop 使用中", "primary_solid", "desktop_windows")
        )
    elif info.desktop_saved:
        pills.append(common.Pill("Desktop", "tertiary", "desktop_windows"))
    return pills


def switch_description(code: bool, desktop: bool) -> str:
    """切换目标的说明（按钮提示与确认对话框使用）。"""
    if code and desktop:
        return "切换 Claude Code 与 Claude Desktop 到此账号"
    if desktop:
        return "切换 Claude Desktop 到此账号"
    return "切换 Claude Code 到此账号"


class RoleProgress(progress.LinearProgressIndicator):
    """可以改变颜色的线性进度条（接近 / 超出预算时显示警告 / 错误色）。"""

    def __init__(self, value: float = 0.0) -> None:
        super().__init__(value)
        self._role = "primary"

    def set_role(self, role: str) -> None:
        """设置进度的颜色角色。"""
        if role != self._role:
            self._role = role
            self.update()

    @override
    def active_color(self) -> QtGui.QColor:
        return self.color(self._role)


class AccountCard(cards.Card):
    """一个账号的概要卡片；点击卡片空白处发出 ``clicked``。

    Args:
        account: 账号。
        info: 账号在两个客户端中的状态。
        include_desktop: 一键切换是否包含 Claude Desktop。
        parent: 父控件。
    """

    edit_requested = QtCore.Signal(str)
    switch_requested = QtCore.Signal(str)
    menu_requested = QtCore.Signal(str, QtCore.QPoint)

    def __init__(
        self,
        account: models.Account,
        info: client_state.ClientInfo,
        include_desktop: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            cards.CardVariant.OUTLINED, clickable=True, parent=parent
        )
        self.account = account
        self.set_content_margins(
            spacing.Insets(
                spacing.SPACE_4,
                spacing.SPACE_4,
                spacing.SPACE_3,
                spacing.SPACE_2,
            )
        )
        self.content_layout.setSpacing(round(spacing.SPACE_3))
        self._build_header(account)
        pills = QtWidgets.QHBoxLayout()
        pills.setSpacing(round(spacing.SPACE_2))
        for pill in client_pills(account, info):
            pills.addWidget(pill)
        tags = common.ElidedLabel(
            "  ".join(f"#{tag}" for tag in account.tags),
            "label-medium",
            "on_surface_variant",
        )
        pills.addWidget(tags, 1)
        self.content_layout.addLayout(pills)
        self._usage = common.ElidedLabel("", "body-medium")
        self.content_layout.addWidget(self._usage)
        self._quota_box = QtWidgets.QWidget()
        quota_layout = QtWidgets.QVBoxLayout(self._quota_box)
        quota_layout.setContentsMargins(0, 0, 0, 0)
        quota_layout.setSpacing(4)
        self._meters = [quota_meter.QuotaMeter() for _ in range(2)]
        for meter in self._meters:
            quota_layout.addWidget(meter)
        self._quota_hint = common.ElidedLabel(
            "", "body-small", "on_surface_variant"
        )
        quota_layout.addWidget(self._quota_hint)
        self._quota_box.setVisible(
            account.auth_type is models.AuthType.OAUTH
        )
        self.content_layout.addWidget(self._quota_box)
        self._budget_row = QtWidgets.QWidget()
        budget_layout = QtWidgets.QVBoxLayout(self._budget_row)
        budget_layout.setContentsMargins(0, 0, 0, 0)
        budget_layout.setSpacing(4)
        self._budget_bar = RoleProgress(0.0)
        budget_layout.addWidget(self._budget_bar)
        self._budget_label = common.ElidedLabel(
            "", "body-small", "on_surface_variant"
        )
        budget_layout.addWidget(self._budget_label)
        self.content_layout.addWidget(self._budget_row)
        self.content_layout.addStretch(1)
        self._build_footer(account, info, include_desktop)
        self.set_quota(info)
        self.setToolTip("点击查看详情")

    def _build_header(self, account: models.Account) -> None:
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(round(spacing.SPACE_3))
        self._avatar = account_avatar(account, 44)
        header.addWidget(self._avatar, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        names = QtWidgets.QVBoxLayout()
        names.setSpacing(0)
        title = account.display_name + ("  ★" if account.favorite else "")
        names.addWidget(common.ElidedLabel(title, "title-medium"))
        target = account.email or account.base_url
        subtitle = " · ".join(
            part for part in (target, account.auth_type.label) if part
        )
        names.addWidget(
            common.ElidedLabel(subtitle, "body-small", "on_surface_variant")
        )
        header.addLayout(names, 1)
        header.addWidget(
            status_pill(account.status), 0, QtCore.Qt.AlignmentFlag.AlignTop
        )
        self.content_layout.addLayout(header)

    def _build_footer(
        self,
        account: models.Account,
        info: client_state.ClientInfo,
        include_desktop: bool,
    ) -> None:
        footer = QtWidgets.QHBoxLayout()
        footer.setSpacing(round(spacing.SPACE_1))
        self._info = common.ElidedLabel("", "body-small", "on_surface_variant")
        footer.addWidget(self._info, 1)
        code, desktop = info.switch_targets(include_desktop)
        if code or desktop:
            switch = buttons.TextButton("切换", icon="swap_horiz")
            switch.setToolTip(switch_description(code, desktop))
            switch.clicked.connect(
                lambda: self.switch_requested.emit(account.id)
            )
            footer.addWidget(switch)
        edit = buttons.IconButton("edit", tooltip="编辑")
        edit.clicked.connect(lambda: self.edit_requested.emit(account.id))
        footer.addWidget(edit)
        more = buttons.IconButton("more_vert", tooltip="更多操作")
        more.clicked.connect(
            lambda: self.menu_requested.emit(
                account.id, more.mapToGlobal(QtCore.QPoint(0, more.height()))
            )
        )
        footer.addWidget(more)
        self.content_layout.addLayout(footer)

    def set_quota(self, info: client_state.ClientInfo) -> None:
        """显示 5 小时与每周额度。"""
        lines = quota_meter.quota_lines(info.quota)
        for index, meter in enumerate(self._meters):
            meter.setVisible(index < len(lines))
        quota_meter.align(self._meters, lines)
        tooltip = quota_meter.describe_source(info.quota)
        for meter in self._meters:
            meter.setToolTip(tooltip)
        if info.quota_error:
            self._quota_hint.setText(f"额度查询失败：{info.quota_error}")
            self._quota_hint.set_color_role("error")
        elif not lines:
            self._quota_hint.setText("额度：暂无数据（保存登录后可查询）")
            self._quota_hint.set_color_role("on_surface_variant")
        else:
            self._quota_hint.setText("")
        self._quota_hint.setVisible(bool(self._quota_hint.full_text()))

    def set_usage(self, totals: analytics.Totals) -> None:
        """显示本月用量、预算进度与"最近使用"的相对时间。"""
        self._info.setText(
            f"最近使用 {formatting.relative(self.account.last_used_at)}"
        )
        local = " · 本机日志" if self.account.link_local else ""
        if totals.total_tokens == 0:
            self._usage.setText("本月暂无用量" + local)
            self._usage.set_color_role("on_surface_variant")
        else:
            cost = formatting.money(totals.cost) if totals.priced else "未计价"
            self._usage.setText(
                f"本月 {formatting.tokens(totals.total_tokens)} tokens · "
                f"{cost} · {formatting.count(totals.requests)} 次请求{local}"
            )
            self._usage.set_color_role("on_surface")
        budget = self.account.monthly_budget
        self._budget_row.setVisible(budget > 0)
        if budget > 0:
            ratio = totals.cost / budget
            self._budget_bar.set_value(min(1.0, ratio))
            self._budget_bar.set_role(
                "error" if ratio > 1 else "warning" if ratio >= 0.9 else "primary"
            )
            over = "（已超出）" if ratio > 1 else ""
            self._budget_label.setText(
                f"月度预算 {formatting.percent(ratio, 0)} · "
                f"{formatting.money(totals.cost)} / "
                f"{formatting.money(budget)}{over}"
            )
            self._budget_label.set_color_role(
                "error" if ratio >= 0.9 else "on_surface_variant"
            )
