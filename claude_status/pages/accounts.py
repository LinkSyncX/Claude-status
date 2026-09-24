"""账号管理页：搜索筛选、卡片 / 列表视图、详情侧边面板与批量操作。"""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
import sys
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import cards
from md3.components import charts
from md3.components import chips
from md3.components import data_table
from md3.components import dialogs
from md3.components import feedback
from md3.components import menus
from md3.components import search
from md3.components import snackbar
from md3.components import text_fields
from md3.components import transitions
from md3.tokens import spacing

from claude_status import analytics
from claude_status import exporters
from claude_status import formatting
from claude_status import models
from claude_status import state as state_module
from claude_status import storage
from claude_status.pages import account_dialog
from claude_status.pages import actions
from claude_status.pages import export_dialog
from claude_status.widgets import account_card
from claude_status.widgets import common
from claude_status.widgets import dense_charts
from claude_status.widgets import quota_meter
from claude_status.widgets import stat_card

_STATUS_FILTERS: list[tuple[str, models.AccountStatus | None]] = [
    ("全部", None),
    *((status.label, status) for status in models.AccountStatus),
]
_SORTS = ("收藏优先", "名称", "本月用量", "最近使用", "创建时间")
_VIEW_CARDS, _VIEW_TABLE = 0, 1


def env_snippet(account: models.Account) -> str:
    """把账号的端点与密钥写成可直接粘贴到终端的环境变量设置。"""
    variables: list[tuple[str, str]] = []
    if account.base_url:
        variables.append(("ANTHROPIC_BASE_URL", account.base_url))
    if account.api_key:
        name = (
            "ANTHROPIC_API_KEY"
            if account.auth_type is models.AuthType.API_KEY
            else "ANTHROPIC_AUTH_TOKEN"
        )
        variables.append((name, account.api_key))
    if sys.platform == "win32":
        return "\n".join(f'$env:{key}="{value}"' for key, value in variables)
    return "\n".join(f"export {key}='{value}'" for key, value in variables)


def _percent_text(value: float) -> str:
    return f"{value:.0f}%"


@dataclasses.dataclass(frozen=True)
class DashColumn(data_table.Column):
    """没有值的单元格显示“—”（排序仍按原值，空值排在最后）。"""

    @override
    def text_of(self, row) -> str:
        return super().text_of(row) or "—"


class AccountsPage(common.Page):
    """账号管理页。

    Args:
        state: 应用状态。
        parent: 父控件。
    """

    navigate_requested = QtCore.Signal(str)

    def __init__(
        self,
        state: state_module.AppState,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._state = state
        self._month_usage: dict[str | None, analytics.Totals] = {}
        self._table_ids: list[str] = []
        self._sheet: common.DetailSheet | None = None
        self._sheet_account: str | None = None
        self._card_signature: list | None = None
        self._banner_slot = QtWidgets.QVBoxLayout()
        self._banner_slot.setContentsMargins(0, 0, 0, 0)
        self.body.addLayout(self._banner_slot)
        self._banner: feedback.Banner | None = None
        self._banner_key: str | None = None
        self._build_summary()
        self._build_toolbar()
        self._build_views()
        state.accounts_changed.connect(self.refresh)
        state.records_changed.connect(self.refresh)
        state.clients.changed.connect(self.refresh)
        state.clients.quota_loading_changed.connect(self._on_quota_loading)
        self.refresh()

    # ---- 构建 -------------------------------------------------------------

    def _build_summary(self) -> None:
        self._total_card = stat_card.StatCard("账号总数", "group", "primary")
        self._healthy_card = stat_card.StatCard(
            "状态正常", "check_circle", "success"
        )
        self._attention_card = stat_card.StatCard(
            "需要关注", "report", "error", increase_is_good=False
        )
        self._month_card = stat_card.StatCard(
            "本月估算费用", "payments", "tertiary", increase_is_good=False
        )
        grid = common.ResponsiveGrid(min_column_width=200, max_columns=4)
        grid.set_widgets(
            [
                self._total_card,
                self._healthy_card,
                self._attention_card,
                self._month_card,
            ]
        )
        self.body.addWidget(grid)

    def _build_toolbar(self) -> None:
        self._search = search.SearchBar("搜索名称、邮箱、标签、组织或备注")
        self._search.setMaximumWidth(460)
        self._search.setMinimumWidth(200)
        self._search.text_changed.connect(lambda _text: self._apply_filter())
        self._sort = text_fields.SelectField("排序", _SORTS, 0)
        self._sort.setFixedWidth(150)
        self._sort.selection_changed.connect(lambda _i: self._apply_filter())
        self._view = buttons.SegmentedButton(
            [
                buttons.Segment("卡片", "grid_view"),
                buttons.Segment("列表", "table_rows"),
            ],
            selected=[_VIEW_CARDS],
            show_check_icon=False,
        )
        self._view.selection_changed.connect(self._on_view_changed)
        self._quota_button = buttons.IconButton(
            "speed", tooltip="刷新各账号的 5 小时与每周额度"
        )
        self._quota_button.clicked.connect(self.refresh_quotas)
        add = buttons.FilledButton("新建账号", icon="person_add")
        add.clicked.connect(
            lambda: self.show_add_menu(
                add.mapToGlobal(QtCore.QPoint(0, add.height()))
            )
        )
        more = buttons.IconButton("more_vert", tooltip="导入 / 导出")
        more.clicked.connect(
            lambda: self._tools_menu().popup(
                more.mapToGlobal(QtCore.QPoint(0, more.height()))
            )
        )
        top = common.row(
            self._search,
            None,
            self._sort,
            self._view,
            self._quota_button,
            add,
            more,
            spacing_px=round(spacing.SPACE_3),
        )
        self.body.addLayout(top)
        self._filters = chips.ChipGroup(
            [label for label, _ in _STATUS_FILTERS], single_selection=True
        )
        self._filters.set_selected([0])
        self._filters.selection_changed.connect(lambda _i: self._apply_filter())
        self._result_label = common.label(
            "", "body-small", "on_surface_variant"
        )
        filter_row = common.FlushRow()  # 筛选标签与上方的卡片左对齐
        filter_row.addWidget(self._filters, 1)
        filter_row.addWidget(
            self._result_label, 0, QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.body.addLayout(filter_row)

    def _build_views(self) -> None:
        self._stack = transitions.AnimatedStackedWidget(
            transitions.Transition.FADE_THROUGH
        )
        self._grid = common.ResponsiveGrid(min_column_width=340, max_columns=3)
        grid_holder = QtWidgets.QWidget()
        grid_layout = QtWidgets.QVBoxLayout(grid_holder)
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.addWidget(self._grid)
        grid_layout.addStretch(1)
        self._stack.addWidget(grid_holder)
        self._table = data_table.DataTable(
            [
                data_table.Column("name", "名称"),
                data_table.Column("email", "邮箱"),
                data_table.Column("plan", "套餐", width=96),
                data_table.Column("auth", "认证方式", width=132),
                data_table.Column("status", "状态", width=88),
                data_table.Column(
                    "tokens",
                    "本月 Token",
                    numeric=True,
                    formatter=formatting.tokens,
                    width=110,
                ),
                data_table.Column(
                    "cost",
                    "本月费用",
                    numeric=True,
                    formatter=formatting.money,
                    width=100,
                ),
                DashColumn(
                    "five_hour",
                    "5 小时",
                    numeric=True,
                    formatter=_percent_text,
                    width=84,
                ),
                DashColumn(
                    "seven_day",
                    "本周",
                    numeric=True,
                    formatter=_percent_text,
                    width=84,
                ),
                data_table.Column("clients", "已保存登录", width=132),
                data_table.Column("last_used", "最近使用", width=110),
            ],
            page_size=25,
        )
        self._table.setMinimumHeight(420)
        self._table.row_activated.connect(self._on_table_activated)
        self._stack.addWidget(self._table)
        self._empty = feedback.EmptyState(
            "还没有账号",
            "添加你的第一个 Claude 账号，或从本机 Claude Code 自动识别当前登录。",
            icon="manage_accounts",
        )
        self._empty.add_action("新建账号").clicked.connect(self.create_account)
        self._empty.add_action("添加示例账号", primary=False).clicked.connect(
            self._add_samples
        )
        self._stack.addWidget(self._empty)
        self._no_match = feedback.EmptyState(
            "没有匹配的账号", "换个关键词或筛选条件试试。", icon="search_off"
        )
        self._stack.addWidget(self._no_match)
        self.body.addWidget(self._stack, 1)

    # ---- 刷新 -------------------------------------------------------------

    def refresh(self) -> None:
        """重新计算本月用量并刷新摘要与列表。"""
        today = dt.date.today()
        month = self._state.dataset.filter(analytics.month_start(today), today)
        self._month_usage = {
            group.key: group.totals for group in month.by_account()
        }
        accounts = self._state.accounts
        healthy = sum(a.status is models.AccountStatus.ACTIVE for a in accounts)
        attention = [
            a
            for a in accounts
            if a.status
            in (models.AccountStatus.LIMITED, models.AccountStatus.EXPIRED)
        ]
        over_budget = [
            a
            for a in accounts
            if a.monthly_budget > 0
            and self._usage(a.id).cost >= a.monthly_budget * 0.9
        ]
        self._total_card.set_value(
            str(len(accounts)),
            caption=f"{sum(a.favorite for a in accounts)} 个收藏",
        )
        self._healthy_card.set_value(
            str(healthy),
            caption=formatting.percent(healthy / len(accounts), 0) + " 可用"
            if accounts
            else "",
        )
        self._attention_card.set_value(
            str(len(attention) + len(over_budget)),
            caption=f"受限/过期 {len(attention)} · 预算告警 {len(over_budget)}",
        )
        total = month.totals()
        self._month_card.set_value(
            formatting.money(total.cost) if total.priced else "—",
            caption=f"{formatting.tokens(total.total_tokens)} tokens",
        )
        self._apply_filter()
        self._refresh_sheet()
        self._update_banner()

    def _usage(self, account_id: str) -> analytics.Totals:
        return self._month_usage.get(account_id, analytics.Totals())

    def _filtered(self) -> list[models.Account]:
        query = self._search.text.strip().lower()
        selected = self._filters.selected_indices
        status = _STATUS_FILTERS[selected[0]][1] if selected else None
        result = []
        for account in self._state.accounts:
            if status is not None and account.status is not status:
                continue
            if query:
                haystack = " ".join(
                    [
                        account.name,
                        account.email,
                        account.organization,
                        account.notes,
                        account.base_url,
                        account.plan.label,
                        *account.tags,
                    ]
                ).lower()
                if query not in haystack:
                    continue
            result.append(account)
        sort = self._sort.selected_index
        if sort == 1:
            result.sort(key=lambda a: a.display_name.lower())
        elif sort == 2:
            result.sort(key=lambda a: -self._usage(a.id).total_tokens)
        elif sort == 3:
            result.sort(key=lambda a: a.last_used_at or "", reverse=True)
        elif sort == 4:
            result.sort(key=lambda a: a.created_at, reverse=True)
        else:
            active = self._state.settings.active_account_id
            result.sort(
                key=lambda a: (a.id != active, not a.favorite, a.display_name)
            )
        return result

    def _apply_filter(self) -> None:
        accounts = self._filtered()
        total = len(self._state.accounts)
        self._result_label.setText(
            f"显示 {len(accounts)} / {total} 个账号" if total else ""
        )
        clients = self._state.clients
        include_desktop = (
            self._state.settings.switch_desktop and actions.desktop_available()
        )
        infos = {account.id: clients.info(account) for account in accounts}
        # 账号资料、客户端状态与顺序都没变时（例如后台刷新了用量或额度）
        # 只更新数值，不重建卡片。
        signature = [
            (
                {k: v for k, v in a.to_dict().items() if k != "quota"},
                dataclasses.replace(infos[a.id], quota=None, quota_error=""),
            )
            for a in accounts
        ]
        signature.append(include_desktop)
        if signature == self._card_signature:
            for card in self._grid.widgets:
                card.set_usage(self._usage(card.account.id))
                card.set_quota(infos[card.account.id])
        else:
            self._card_signature = signature
            cards = []
            for account in accounts:
                card = account_card.AccountCard(
                    account, infos[account.id], include_desktop
                )
                card.set_usage(self._usage(account.id))
                card.clicked.connect(
                    lambda account_id=account.id: self.open_details(account_id)
                )
                card.edit_requested.connect(self.edit_account)
                card.switch_requested.connect(self.switch_account)
                card.menu_requested.connect(self._show_account_menu)
                cards.append(card)
            self._grid.set_widgets(cards)
        rows = []
        self._table_ids = []
        now = dt.datetime.now().astimezone()
        for account in accounts:
            usage = self._usage(account.id)
            info = infos[account.id]
            lines = {
                line.title: line.percent
                for line in quota_meter.quota_lines(info.quota, now)
            }
            saved = [
                name
                for name, flag in (
                    ("Code", info.code_saved),
                    ("Desktop", info.desktop_saved),
                )
                if flag
            ]
            current = info.code_current or info.desktop_current
            self._table_ids.append(account.id)
            rows.append(
                {
                    "name": ("● " if current else "") + account.display_name,
                    "email": account.email or "—",
                    "plan": account.plan.label,
                    "auth": account.auth_type.label,
                    "status": account.status.label,
                    "tokens": usage.total_tokens,
                    "cost": usage.cost if usage.priced else None,
                    "five_hour": lines.get("5 小时"),
                    "seven_day": lines.get("本周"),
                    "clients": " / ".join(saved) or "—",
                    "last_used": formatting.relative(account.last_used_at),
                }
            )
        self._table.set_rows(rows)
        self._show_current_view(bool(accounts))

    def _show_current_view(self, has_rows: bool) -> None:
        if not self._state.accounts:
            target: QtWidgets.QWidget = self._empty
        elif not has_rows:
            target = self._no_match
        elif self._view.selected_indices == [_VIEW_TABLE]:
            target = self._table
        else:
            target = self._stack.widget(0)
        if self._stack.currentWidget() is not target:
            self._stack.set_current_widget(target)

    def _on_view_changed(self, _indices: list[int]) -> None:
        self._show_current_view(bool(self._table_ids))

    def _on_table_activated(self, row: int) -> None:
        if 0 <= row < len(self._table_ids):
            self.open_details(self._table_ids[row])

    # ---- 操作 -------------------------------------------------------------

    def _duplicate_email(self, email: str, own_id: str) -> bool:
        return any(
            a.email.lower() == email.lower() and a.id != own_id
            for a in self._state.accounts
        )

    def show_add_menu(self, pos: QtCore.QPoint) -> None:
        """“新建账号”菜单：在本工具中登录，或手动添加 API / 中转账号。"""
        menu = menus.Menu(
            [
                menus.MenuItem("登录 Claude 账号…", "login", key="login"),
                menus.MenuItem(
                    "手动添加（API Key / 中转）…", "edit_note", key="manual"
                ),
            ],
            parent=self,
        )
        # 延迟到菜单关闭之后再弹出模态对话框。
        menu.triggered.connect(
            lambda item: QtCore.QTimer.singleShot(
                0, lambda: self._on_add(item.key)
            )
        )
        menu.closed.connect(menu.deleteLater)
        menu.popup(pos)

    def _on_add(self, key: str) -> None:
        if key == "login":
            actions.login_account(self, self._state)
        else:
            self.create_account()

    def create_account(self) -> None:
        """打开新建账号对话框（手动填写）。"""
        dialog = account_dialog.AccountDialog(
            None, self._state.all_tags(), self._duplicate_email, self.window()
        )
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            account = dialog.result_account()
            self._state.add_account(account)
            snackbar.show(self, f"已添加账号「{account.display_name}」")

    def edit_account(self, account_id: str) -> None:
        """打开编辑对话框。"""
        account = self._state.account(account_id)
        if account is None:
            return
        dialog = account_dialog.AccountDialog(
            account,
            self._state.all_tags(),
            self._duplicate_email,
            self.window(),
        )
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self._state.update_account(dialog.result_account())
            snackbar.show(self, "已保存修改")

    def switch_account(
        self,
        account_id: str,
        code: bool | None = None,
        desktop: bool | None = None,
    ) -> None:
        """一键切换到该账号（未指定时按设置决定切换哪些客户端）。"""
        account = self._state.account(account_id)
        if account is not None:
            actions.switch_account(self, self._state, account, code, desktop)

    def refresh_quotas(self) -> None:
        """联网刷新各账号的额度。"""
        clients = self._state.clients
        if not clients.online_enabled():
            clients.refresh()
            snackbar.show(
                self, "已从本机数据更新额度（联网查询已在设置中关闭）"
            )
            return
        if clients.refresh_quotas(manual=True):
            snackbar.show(self, "正在查询各账号的额度…")

    def _on_quota_loading(self, loading: bool) -> None:
        self._quota_button.setEnabled(not loading)

    def delete_account(self, account_id: str) -> None:
        """确认后删除账号，可在提示条中撤销。"""
        account = self._state.account(account_id)
        if account is None:
            return
        if not dialogs.confirm(
            self.window(),
            f"删除「{account.display_name}」？",
            "账号资料、保存的密钥与客户端登录将从本机移除（可立即撤销）；"
            "本机日志中的用量记录不受影响。",
            confirm_text="删除",
            icon="delete",
        ):
            return
        self._close_sheet()
        removed, active = self._state.delete_accounts({account_id})
        snackbar.show(
            self,
            f"已删除「{account.display_name}」",
            "撤销",
            lambda: self._state.restore_accounts(removed, active),
            duration_ms=6000,
        )

    def _copy(self, text: str, message: str) -> None:
        QtGui.QGuiApplication.clipboard().setText(text)
        snackbar.show(self, message)

    def _add_samples(self) -> None:
        count = self._state.add_sample_accounts()
        snackbar.show(self, f"已添加 {count} 个示例账号，可随时删除")

    def _show_account_menu(self, account_id: str, pos: QtCore.QPoint) -> None:
        account = self._state.account(account_id)
        if account is None:
            return
        info = self._state.clients.info(account)
        items: list[menus.MenuItem] = [
            menus.MenuItem("查看详情", "info", key=("details", None)),
            menus.MenuItem("编辑", "edit", key=("edit", None)),
            menus.MenuItem(separator=True),
            menus.MenuItem(
                "切换 Claude Code 到此账号",
                "terminal",
                enabled=info.code_ready and not info.code_current,
                key=("switch_code", None),
            ),
            menus.MenuItem(
                "切换 Claude Desktop 到此账号",
                "desktop_windows",
                enabled=info.desktop_saved and not info.desktop_current,
                key=("switch_desktop", None),
            ),
        ]
        if account.auth_type is models.AuthType.OAUTH:
            items.append(
                menus.MenuItem(
                    "重新登录…" if info.code_saved else "登录…",
                    "login",
                    key=("login", None),
                )
            )
        if self._can_link_desktop(account):
            items.append(
                menus.MenuItem(
                    "关联为 Desktop 当前登录",
                    "link",
                    key=("link_desktop", None),
                )
            )
        if info.code_saved:
            items.append(
                menus.MenuItem(
                    "删除保存的 Claude Code 登录",
                    "key_off",
                    key=("forget_code", None),
                )
            )
        if info.desktop_saved:
            items.append(
                menus.MenuItem(
                    "删除保存的 Desktop 登录",
                    "key_off",
                    key=("forget_desktop", None),
                )
            )
        items += [
            menus.MenuItem(separator=True),
            menus.MenuItem(
                "取消收藏" if account.favorite else "收藏",
                "star",
                key=("favorite", None),
            ),
            menus.MenuItem(
                "取消用量默认归属" if account.link_local else "设为用量默认归属",
                "move_to_inbox",
                key=("link", None),
            ),
        ]
        if account.api_key:
            items.append(
                menus.MenuItem("复制密钥", "content_copy", key=("copy_key", None))
            )
        if account.api_key or account.base_url:
            items.append(
                menus.MenuItem(
                    "复制环境变量", "terminal", key=("copy_env", None)
                )
            )
        items.append(menus.MenuItem(separator=True))
        for status in models.AccountStatus:
            if status is not account.status:
                items.append(
                    menus.MenuItem(
                        f"标记为{status.label}",
                        status.icon,
                        key=("status", status),
                    )
                )
        items.append(menus.MenuItem(separator=True))
        items.append(menus.MenuItem("删除", "delete", key=("delete", None)))
        menu = menus.Menu(items, parent=self)
        menu.triggered.connect(
            lambda item: self._on_account_action(account_id, item.key)
        )
        menu.closed.connect(menu.deleteLater)
        menu.popup(pos)

    def _on_account_action(self, account_id: str, key) -> None:
        action, value = key
        account = self._state.account(account_id)
        if account is None:
            return
        if action == "details":
            self.open_details(account_id)
        elif action == "edit":
            self.edit_account(account_id)
        elif action == "switch_code":
            self.switch_account(account_id, code=True, desktop=False)
        elif action == "switch_desktop":
            self.switch_account(account_id, code=False, desktop=True)
        elif action == "link_desktop":
            actions.link_desktop(self, self._state, account)
        elif action == "login":
            QtCore.QTimer.singleShot(
                0, lambda: actions.login_account(self, self._state, account)
            )
        elif action == "forget_code":
            actions.forget_login(self, self._state, account, desktop=False)
        elif action == "forget_desktop":
            actions.forget_login(self, self._state, account, desktop=True)
        elif action == "favorite":
            self._state.toggle_favorite(account_id)
        elif action == "link":
            linking = not account.link_local
            self._state.link_local(account_id if linking else None)
            snackbar.show(
                self,
                f"无法识别来源的本机用量将计入「{account.display_name}」"
                if linking
                else "已取消用量默认归属",
            )
        elif action == "copy_key":
            self._copy(account.api_key, "密钥已复制到剪贴板")
        elif action == "copy_env":
            self._copy(env_snippet(account), "环境变量已复制，可粘贴到终端")
        elif action == "status":
            self._state.set_status(account_id, value)
        elif action == "delete":
            self.delete_account(account_id)

    def _tools_menu(self) -> menus.Menu:
        items = [
            menus.MenuItem("导入账号…", "upload", key="import"),
            menus.MenuItem("导出账号（不含密钥）…", "download", key="export"),
            menus.MenuItem("导出账号（含密钥）…", "key", key="export_secret"),
            menus.MenuItem("导出到 sub2api…", "cloud_upload", key="export_sub2api"),
            menus.MenuItem(
                "导出到 CPA（CLIProxyAPI）…", "cloud_upload", key="export_cpa"
            ),
            menus.MenuItem(separator=True),
            menus.MenuItem(
                "保存本机 Claude Code 当前登录",
                "terminal",
                enabled=self._state.clients.code_login is not None,
                key="detect",
            ),
            menus.MenuItem("添加示例账号", "science", key="samples"),
        ]
        menu = menus.Menu(items, parent=self)
        menu.triggered.connect(lambda item: self._on_tool(item.key))
        menu.closed.connect(menu.deleteLater)
        return menu

    def _on_tool(self, key: str) -> None:
        # 延迟到菜单关闭之后再弹出模态对话框。
        QtCore.QTimer.singleShot(0, lambda: self._run_tool(key))

    def _run_tool(self, key: str) -> None:
        if key == "import":
            path, _ = QtWidgets.QFileDialog.getOpenFileName(
                self.window(), "导入账号", "", "JSON (*.json)"
            )
            if not path:
                return
            try:
                incoming = storage.read_export(pathlib.Path(path))
            except (OSError, ValueError) as exc:
                dialogs.alert(self.window(), "无法导入", str(exc))
                return
            result = self._state.merge_accounts(incoming)
            snackbar.show(
                self, f"导入完成：新增 {result.added} 个，更新 {result.updated} 个"
            )
        elif key in ("export", "export_secret"):
            secret = key == "export_secret"
            if secret and not dialogs.confirm(
                self.window(),
                "导出包含密钥？",
                "导出的文件会以明文包含 API Key 与令牌，请妥善保管。",
                confirm_text="继续导出",
                icon="key",
            ):
                return
            name = f"claude-accounts-{dt.date.today():%Y%m%d}.json"
            path, _ = QtWidgets.QFileDialog.getSaveFileName(
                self.window(), "导出账号", name, "JSON (*.json)"
            )
            if not path:
                return
            try:
                storage.export_accounts(
                    pathlib.Path(path), self._state.accounts, secret
                )
            except OSError as exc:
                dialogs.alert(self.window(), "导出失败", str(exc))
                return
            snackbar.show(self, f"已导出 {len(self._state.accounts)} 个账号")
        elif key == "export_sub2api":
            self.export_to(exporters.SUB2API)
        elif key == "export_cpa":
            self.export_to(exporters.CPA)
        elif key == "detect":
            self.import_local_login()
        elif key == "samples":
            self._add_samples()

    def export_to(self, fmt: str) -> None:
        """导出到 sub2api 或 CPA（CLIProxyAPI）。"""
        clients = self._state.clients
        items = exporters.collect(
            self._state.accounts,
            clients.vault,
            clients.code_login,
            clients.code_owner(),
        )
        dialog = export_dialog.ExportDialog(fmt, items, self.window())
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected()
        try:
            if fmt == exporters.SUB2API:
                self._export_sub2api(chosen)
            else:
                self._export_cpa(chosen)
        except OSError as exc:
            dialogs.alert(self.window(), "导出失败", str(exc))

    def _export_sub2api(self, chosen: list[exporters.ExportItem]) -> None:
        name = f"sub2api-accounts-{dt.date.today():%Y%m%d}.json"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.window(), "导出到 sub2api", name, "JSON (*.json)"
        )
        if not path:
            return
        count = exporters.write_sub2api(pathlib.Path(path), chosen)
        snackbar.show(
            self,
            f"已导出 {count} 个账号：在 sub2api 管理后台的账号管理中导入该文件",
            duration_ms=6000,
        )

    def _export_cpa(self, chosen: list[exporters.ExportItem]) -> None:
        start = exporters.CPA_AUTH_DIR
        directory = QtWidgets.QFileDialog.getExistingDirectory(
            self.window(),
            "选择 CLIProxyAPI 的认证目录",
            str(start if start.is_dir() else pathlib.Path.home()),
        )
        if not directory:
            return
        target = pathlib.Path(directory)
        existing = [
            name for name in exporters.cpa_targets(chosen) if (target / name).exists()
        ]
        if existing and not dialogs.confirm(
            self.window(),
            "覆盖同名文件？",
            f"目录中已有 {len(existing)} 个同名文件（{'、'.join(existing[:3])}"
            f"{'…' if len(existing) > 3 else ''}），导出会覆盖它们。",
            confirm_text="覆盖",
            icon="warning",
        ):
            return
        written = exporters.write_cpa(target, chosen)
        note = (
            f"；把 {exporters.CPA_API_KEYS_NAME} 中的条目合并到 config.yaml"
            if exporters.CPA_API_KEYS_NAME in written
            else ""
        )
        snackbar.show(
            self,
            f"已写入 {len(written)} 个文件到 {target}{note}",
            duration_ms=8000,
        )

    def import_local_login(self) -> None:
        """保存本机 Claude Code 当前的订阅登录（没有对应账号时新建）。"""
        actions.capture_code(self, self._state)

    # ---- 提示横幅 ---------------------------------------------------------

    def _can_link_desktop(self, account: models.Account) -> bool:
        """Desktop 已登录但还没有关联账号时，该账号能否关联为当前登录。"""
        clients = self._state.clients
        desktop = clients.desktop
        return (
            desktop is not None
            and desktop.logged_in
            and bool(desktop.account_uuid)
            and clients.current_desktop_account() is None
            and account.auth_type is models.AuthType.OAUTH
            and account.claude_uuid in ("", desktop.account_uuid)
        )

    def _banner_spec(self) -> tuple[str, str, str, str] | None:
        """(键, 文字, 图标, 操作)；当前登录都已保存时返回 None。"""
        clients = self._state.clients
        vault = clients.vault
        desktop = clients.desktop
        if (
            desktop is not None
            and desktop.logged_in
            and clients.current_desktop_account() is None
        ):
            return (
                f"desktop-link:{desktop.account_uuid}",
                "Claude Desktop 当前登录的账号还没有关联：关联后显示它的额度，"
                "Code 标签页的用量也会计入它（不需要退出 Desktop）。",
                "desktop_windows",
                "link_desktop",
            )
        login = clients.code_login
        if login is not None:
            owner = clients.code_owner()
            if owner is None or not vault.has_code(owner.id):
                who = login.email or "当前账号"
                return (
                    f"code:{login.account_uuid or login.email}",
                    f"Claude Code 当前登录的 {who} 还没有保存，保存后才能随时"
                    "一键切换回来。",
                    "terminal",
                    "save_code",
                )
        if clients.provider_env and clients.env_owner() is None:
            base = clients.provider_env.get("ANTHROPIC_BASE_URL", "API Key")
            return (
                f"env:{base}",
                f"Claude Code 当前使用的中转 / API 配置（{base}）还没有保存为"
                "账号，保存后切换到其他账号时可以切回。",
                "hub",
                "save_env",
            )
        owner = clients.current_desktop_account()
        if owner is not None and not vault.has_desktop(owner.id):
            return (
                f"desktop:{owner.id}",
                "Claude Desktop 的登录会话还没有保存，保存后才能一键切换回"
                f"「{owner.display_name}」。",
                "desktop_windows",
                "clients",
            )
        return None

    def _update_banner(self) -> None:
        spec = self._banner_spec()
        key = spec[0] if spec else None
        if key == self._banner_key:
            return
        self._banner_key = key
        if self._banner is not None:
            self._banner_slot.removeWidget(self._banner)
            self._banner.deleteLater()
            self._banner = None
        if spec is None:
            return
        _key, text, icon, action = spec
        banner = common.InfoBanner(text, icon=icon)
        label = {"clients": "前往客户端", "link_desktop": "关联…"}.get(
            action, "立即保存"
        )
        banner.add_action(label).clicked.connect(
            lambda: self._on_banner_action(action)
        )
        banner.add_action("稍后")
        self._banner = banner
        self._banner_slot.addWidget(banner)

    def _on_banner_action(self, action: str) -> None:
        if action == "save_code":
            actions.capture_code(self, self._state)
        elif action == "save_env":
            actions.import_provider_env(self, self._state)
        elif action == "link_desktop":
            actions.link_desktop(self, self._state)
        else:
            self.navigate_requested.emit("clients")

    # ---- 详情面板 ---------------------------------------------------------

    def _close_sheet(self) -> None:
        if self._sheet is not None and self._sheet.is_open:
            self._sheet.close_panel()

    def _ensure_sheet(self) -> common.DetailSheet:
        if self._sheet is None:
            sheet = common.DetailSheet(self.window(), "账号详情")
            sheet.add_action("编辑", primary=True).clicked.connect(
                lambda: self._on_sheet_action(self.edit_account)
            )
            sheet.add_action("删除").clicked.connect(
                lambda: self._on_sheet_action(self.delete_account)
            )
            self._sheet = sheet
        return self._sheet

    def _on_sheet_action(self, action) -> None:
        if self._sheet_account is not None:
            action(self._sheet_account)

    def _refresh_sheet(self) -> None:
        """账号资料或用量变化后刷新已打开的详情面板。"""
        if self._sheet is None or not self._sheet.is_open:
            return
        account = self._state.account(self._sheet_account)
        if account is None:
            self._sheet.close_panel()
            return
        self._sheet.replace_content(self._details_widget(account))

    def open_details(self, account_id: str) -> None:
        """在右侧面板中显示账号详情。"""
        account = self._state.account(account_id)
        if account is None:
            return
        sheet = self._ensure_sheet()
        self._sheet_account = account_id
        sheet.replace_content(self._details_widget(account))
        sheet.open_panel()

    def _details_widget(self, account: models.Account) -> QtWidgets.QWidget:
        body = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(spacing.SPACE_4))
        info = self._state.clients.info(account)
        header = QtWidgets.QHBoxLayout()
        header.setSpacing(round(spacing.SPACE_3))
        header.addWidget(account_card.account_avatar(account, 56))
        names = QtWidgets.QVBoxLayout()
        names.setSpacing(2)
        names.addWidget(
            common.label(account.display_name, "title-large", selectable=True)
        )
        names.addWidget(
            common.label(
                account.email or "未填写邮箱",
                "body-medium",
                "on_surface_variant",
                selectable=True,
            )
        )
        header.addLayout(names, 1)
        layout.addLayout(header)
        # 面板较窄：状态与套餐一行，客户端登录状态另起一行。
        pills = [account_card.status_pill(account.status)]
        pills += account_card.client_pills(account, info)
        for chunk in (pills[:2], pills[2:]):
            if chunk:
                layout.addLayout(
                    common.row(*chunk, None, spacing_px=round(spacing.SPACE_2))
                )
        code, desktop = info.switch_targets(
            self._state.settings.switch_desktop and actions.desktop_available()
        )
        if code or desktop:
            switch = buttons.FilledTonalButton("切换到此账号", icon="swap_horiz")
            switch.setToolTip(account_card.switch_description(code, desktop))
            switch.clicked.connect(lambda: self.switch_account(account.id))
            layout.addLayout(common.row(switch, None, flush=True))
        if account.auth_type is models.AuthType.OAUTH:
            layout.addWidget(self._quota_card(account, info))
        layout.addWidget(self._usage_chart(account))
        oauth = account.auth_type is models.AuthType.OAUTH
        details = [
            ("套餐", account.plan.label),
            ("认证方式", account.auth_type.label),
            ("组织", account.organization or "—"),
        ]
        if not oauth:
            details += [
                ("Base URL", account.base_url or "官方 API"),
                ("密钥", account.masked_key() or "—"),
            ]
            if account.env:
                details.append(("额外变量", "、".join(sorted(account.env))))
        details += [
            (
                "月度预算",
                formatting.money(account.monthly_budget)
                if account.monthly_budget
                else "不限",
            ),
            ("标签", "、".join(account.tags) or "—"),
            (
                "创建时间",
                formatting.datetime_text(
                    formatting.parse_iso(account.created_at)
                ),
            ),
            ("最近使用", formatting.relative(account.last_used_at)),
        ]
        if oauth:
            details += [
                ("Claude Code", self._saved_text(account, desktop=False)),
                ("Desktop", self._saved_text(account, desktop=True)),
            ]
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(round(spacing.SPACE_4))
        grid.setVerticalSpacing(round(spacing.SPACE_2))
        for index, (name, value) in enumerate(details):
            grid.addWidget(
                common.label(name, "label-large", "on_surface_variant"),
                index,
                0,
                QtCore.Qt.AlignmentFlag.AlignTop,
            )
            text = common.label(
                value, "body-medium", selectable=True, wrap=True
            )
            grid.addWidget(text, index, 1)
            if name == "密钥" and account.api_key:
                copy = buttons.IconButton("content_copy", tooltip="复制密钥")
                copy.clicked.connect(
                    lambda: self._copy(account.api_key, "密钥已复制到剪贴板")
                )
                grid.addWidget(copy, index, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        if account.notes:
            layout.addWidget(
                common.label("备注", "label-large", "on_surface_variant")
            )
            layout.addWidget(
                common.label(
                    account.notes, "body-medium", selectable=True, wrap=True
                )
            )
        layout.addStretch(1)
        return common.wrap_scroll(body)

    def _saved_text(self, account: models.Account, desktop: bool) -> str:
        vault = self._state.clients.vault
        meta = (
            vault.desktop_meta(account.id)
            if desktop
            else vault.code_meta(account.id)
        )
        saved = vault.has_desktop(account.id) if desktop else vault.has_code(
            account.id
        )
        if not saved:
            return "未保存登录"
        when = (meta or {}).get("saved_at")
        return formatting.ago(when, "保存") if when else "已保存"

    def _quota_card(
        self, account: models.Account, info
    ) -> QtWidgets.QWidget:
        card = common.SectionCard(
            "订阅额度",
            quota_meter.describe_source(info.quota)
            or "暂无数据：保存 Claude Code 登录或在 Desktop 中登录后可获取",
            variant=cards.CardVariant.FILLED,
        )
        lines = quota_meter.quota_lines(info.quota, include_scoped=True)
        meters = [quota_meter.QuotaMeter() for _ in lines]
        quota_meter.align(meters, lines)
        for meter in meters:
            card.add_widget(meter)
        if info.quota_error:
            card.add_widget(
                common.label(
                    f"最近一次查询失败：{info.quota_error}",
                    "body-small",
                    "error",
                    wrap=True,
                )
            )
        samples = self._state.clients.samples_for(account)
        if len(samples) >= 2:
            recent = samples[-48:]
            chart = dense_charts.DenseLineChart(
                [
                    charts.Series(
                        "5 小时", [float(s.usage.get("fh") or 0) for s in recent]
                    ),
                    charts.Series(
                        "本周", [float(s.usage.get("sd") or 0) for s in recent]
                    ),
                ],
                formatting.time_labels([s.time for s in recent]),
                smooth=False,  # 5 小时窗口重置时陡降，平滑曲线会冲出坐标范围
                show_points=False,
            )
            chart.set_y_range(0, 100)
            chart.set_value_formatter(lambda v: f"{v:.0f}%")
            chart.setFixedHeight(180)
            card.add_widget(
                common.label(
                    "额度走势（Claude Desktop 采样）",
                    "label-medium",
                    "on_surface_variant",
                )
            )
            card.add_widget(chart)
        return card

    def _usage_chart(self, account: models.Account) -> QtWidgets.QWidget:
        today = dt.date.today()
        start = today - dt.timedelta(days=29)
        subset = self._state.dataset.filter(start, today, [account.id])
        daily = subset.daily(start, today)
        totals = subset.totals()
        card = common.SectionCard(
            "近 30 天用量",
            f"{formatting.tokens(totals.total_tokens)} tokens · "
            f"{formatting.money(totals.cost) if totals.priced else '未计价'} · "
            f"{formatting.count(totals.requests)} 次请求",
            variant=cards.CardVariant.FILLED,
        )
        chart = charts.LineChart(
            [
                charts.Series(
                    "Token", [float(d.totals.total_tokens) for d in daily]
                )
            ],
            [formatting.date_short(d.day) for d in daily],
            fill_area=True,
            show_points=False,
            show_legend=False,
        )
        chart.set_show_axes(False)
        chart.set_value_formatter(formatting.tokens)
        chart.set_empty_text("近 30 天没有用量")
        chart.setFixedHeight(120)
        card.add_widget(chart)
        return card
