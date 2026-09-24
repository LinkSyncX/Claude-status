"""应用状态：账号、设置与当前数据源的用量数据。

``AppState`` 是界面与数据层之间唯一的桥梁：页面只读取它的属性并监听
信号，所有修改都通过它的方法完成并立即保存。本机日志在后台线程扫描，
扫描结果按"关联本机日志"的账号归属；演示数据则为每个账号即时生成。
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib

from PySide6 import QtCore

from claude_status import analytics
from claude_status import claude_code
from claude_status import client_state
from claude_status import demo_data
from claude_status import models
from claude_status import pricing
from claude_status import storage
from claude_status import tasks

AUTO_REFRESH_MS = 60_000


class _ScanThread(QtCore.QThread):
    """在后台线程中扫描日志，完成后发出 ``scanned``。"""

    scanned = QtCore.Signal(object)

    def __init__(
        self,
        scanner: claude_code.LogScanner,
        directory: pathlib.Path,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._directory = directory

    def run(self) -> None:  # noqa: D102
        try:
            result = self._scanner.scan(self._directory)
        except Exception as exc:  # pylint: disable=broad-except
            result = claude_code.ScanResult(
                self._directory, errors=1, error=str(exc)
            )
        self.scanned.emit(result)


class AppState(QtCore.QObject):
    """全局状态。

    Args:
        store: 配置存储。
        force_demo: 为真时本次启动使用演示数据（不修改已保存的设置，
            首次启动时还会添加示例账号）。
        offline: 为真时不联网查询额度。
        parent: 父对象。
    """

    accounts_changed = QtCore.Signal()
    records_changed = QtCore.Signal()
    settings_changed = QtCore.Signal()
    loading_changed = QtCore.Signal(bool)
    notify = QtCore.Signal(str)

    def __init__(
        self,
        store: storage.Store,
        force_demo: bool = False,
        offline: bool = False,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        loaded = store.load()
        self.accounts: list[models.Account] = loaded.accounts
        self.settings: models.Settings = loaded.settings
        self.load_warning = loaded.warning
        self.local_login = claude_code.read_local_login()
        self.scan: claude_code.ScanResult | None = None
        self.dataset = analytics.Dataset([])
        self._force_demo = force_demo
        self._scanner = claude_code.LogScanner()
        self._thread: _ScanThread | None = None
        self._pending_refresh = False
        self._local_records: list[models.UsageRecord] = []
        self._signature: tuple | None = None
        self._trash: dict[str, pathlib.Path] = {}
        if not loaded.existed:
            self._first_run()
        self.clients = client_state.ClientManager(self, offline)
        self.clients.refresh()
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(AUTO_REFRESH_MS)
        self._timer.timeout.connect(self._auto_refresh)
        self._timer.start()

    # ---- 首次启动 ---------------------------------------------------------

    def _first_run(self) -> None:
        """首次启动：自动识别本机登录账号，并按是否有日志选择数据源。"""
        has_logs = claude_code.default_projects_dir().is_dir()
        if self._force_demo or not has_logs:
            self.settings.data_source = models.DataSource.DEMO
        if self._force_demo:
            self.accounts.extend(demo_data.sample_accounts())
            self.settings.active_account_id = self.accounts[0].id
        elif self.local_login is not None:
            account = self.account_from_login(self.local_login)
            self.accounts.append(account)
            self.settings.active_account_id = account.id
        self.settings.first_run = False
        self.save()

    @staticmethod
    def account_from_login(login: claude_code.LocalLogin) -> models.Account:
        """由本机登录信息创建账号（关联本机日志）。"""
        now = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        return models.Account(
            name=login.display_name or login.email.split("@")[0],
            email=login.email,
            plan=login.plan,
            organization=login.organization,
            link_local=True,
            tags=["Claude Code"],
            notes="从本机 Claude Code 登录信息自动识别。",
            last_used_at=now,
        )

    # ---- 查询 -------------------------------------------------------------

    @property
    def data_source(self) -> models.DataSource:
        """本次运行实际使用的数据源。"""
        if self._force_demo:
            return models.DataSource.DEMO
        return self.settings.data_source

    @property
    def demo_forced(self) -> bool:
        """本次启动是否以 --demo 强制使用演示数据（不改动真实客户端）。"""
        return self._force_demo

    @property
    def loading(self) -> bool:
        """是否正在扫描日志。"""
        return self._thread is not None

    @property
    def projects_dir(self) -> pathlib.Path:
        """日志目录（设置中的自定义目录或默认目录）。"""
        if self.settings.projects_dir:
            return pathlib.Path(self.settings.projects_dir).expanduser()
        return claude_code.default_projects_dir()

    def account(self, account_id: str | None) -> models.Account | None:
        """按 ID 查找账号。"""
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def account_name(self, account_id: str | None) -> str:
        """账号显示名；未归属或已删除的账号显示为"未归属"。"""
        account = self.account(account_id)
        return account.display_name if account is not None else "未归属"

    def linked_account(self) -> models.Account | None:
        """关联本机日志的账号。"""
        return next((a for a in self.accounts if a.link_local), None)

    def price_book(self) -> pricing.PriceBook:
        """当前价格表（含自定义单价）。"""
        return pricing.PriceBook(self.settings.custom_prices)

    def all_tags(self) -> list[str]:
        """全部账号使用过的标签。"""
        return sorted(
            {tag for account in self.accounts for tag in account.tags}
        )

    def known_models(self) -> list[str]:
        """数据中出现过的模型。"""
        return sorted({record.model for record in self.dataset.records})

    # ---- 持久化 -----------------------------------------------------------

    def save(self) -> None:
        """保存账号与设置；失败时通过 ``notify`` 提示。"""
        try:
            self.store.save(self.accounts, self.settings)
        except OSError as exc:
            self.notify.emit(f"保存失败：{exc}")

    # ---- 账号操作 ---------------------------------------------------------

    def _ensure_single_link(self, keep: models.Account) -> None:
        if keep.link_local:
            for account in self.accounts:
                if account is not keep:
                    account.link_local = False

    def add_account(self, account: models.Account) -> None:
        """新增账号。"""
        self.accounts.append(account)
        self._ensure_single_link(account)
        if self.settings.active_account_id is None:
            self.settings.active_account_id = account.id
        self._accounts_updated()

    def update_account(self, account: models.Account) -> None:
        """用编辑后的副本替换同 ID 的账号。

        编辑的正是 Claude Code 当前使用的中转 / API 账号时，新配置会同步
        写入 ``settings.json``。
        """
        before = self.clients.current_code_account()
        for index, existing in enumerate(self.accounts):
            if existing.id == account.id:
                account.touch()
                self.accounts[index] = account
                self._ensure_single_link(account)
                break
        else:
            self.accounts.append(account)
        self._accounts_updated()
        if self.clients.sync_edited_account(before, account):
            self.notify.emit("已把修改同步到 Claude Code 的 settings.json")

    def delete_accounts(
        self, ids: set[str]
    ) -> tuple[list[tuple[int, models.Account]], str | None]:
        """删除账号，返回 ([(原位置, 账号)], 原当前账号) 供撤销。"""
        removed = [
            (index, account)
            for index, account in enumerate(self.accounts)
            if account.id in ids
        ]
        previous_active = self.settings.active_account_id
        for account_id in ids:
            location = self.clients.vault.trash(account_id)
            if location is not None:
                self._trash[account_id] = location
        self.accounts = [a for a in self.accounts if a.id not in ids]
        if previous_active in ids:
            self.settings.active_account_id = (
                self.accounts[0].id if self.accounts else None
            )
        self._accounts_updated()
        return removed, previous_active

    def restore_accounts(
        self,
        removed: list[tuple[int, models.Account]],
        active_id: str | None = None,
    ) -> None:
        """撤销删除：按原位置放回，并恢复当前账号。"""
        existing = {a.id for a in self.accounts}
        for index, account in sorted(removed, key=lambda item: item[0]):
            if account.id not in existing:
                self.accounts.insert(min(index, len(self.accounts)), account)
            location = self._trash.pop(account.id, None)
            if location is not None:
                self.clients.vault.untrash(location, account.id)
        if active_id is not None and self.account(active_id) is not None:
            self.settings.active_account_id = active_id
        if any(account.link_local for _, account in removed):
            linked = next(a for _, a in removed if a.link_local)
            self._ensure_single_link(linked)
        self._accounts_updated()

    def set_active(self, account_id: str) -> None:
        """设为当前使用中的账号。"""
        account = self.account(account_id)
        if account is None:
            return
        account.last_used_at = dt.datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        self.settings.active_account_id = account_id
        self._accounts_updated(rebuild=False)

    def toggle_favorite(self, account_id: str) -> None:
        """切换收藏。"""
        account = self.account(account_id)
        if account is not None:
            account.favorite = not account.favorite
            self._accounts_updated(rebuild=False)

    def set_status(
        self, account_id: str, status: models.AccountStatus
    ) -> None:
        """修改账号状态。"""
        account = self.account(account_id)
        if account is not None:
            account.status = status
            account.touch()
            self._accounts_updated()

    def link_local(self, account_id: str | None) -> None:
        """把本机日志归属到指定账号（None 取消关联）。"""
        for account in self.accounts:
            account.link_local = account.id == account_id
        self._accounts_updated()

    def merge_accounts(
        self, incoming: list[models.Account]
    ) -> storage.MergeResult:
        """导入账号。"""
        result = storage.merge_accounts(self.accounts, incoming)
        self.accounts = result.accounts
        self._accounts_updated()
        return result

    def add_sample_accounts(self) -> int:
        """追加一组示例账号，返回数量。"""
        samples = demo_data.sample_accounts()
        for sample in samples:
            sample.tags.append("示例")
        self.accounts.extend(samples)
        if self.settings.active_account_id is None:
            self.settings.active_account_id = samples[0].id
        self._accounts_updated()
        return len(samples)

    def _accounts_updated(self, rebuild: bool = True) -> None:
        self.save()
        if rebuild:
            self._rebuild()
        self.accounts_changed.emit()

    def accounts_modified(self, rebuild: bool = True) -> None:
        """账号列表或资料在外部被修改后调用：保存、重建数据并通知界面。"""
        self._accounts_updated(rebuild)

    # ---- 设置 -------------------------------------------------------------

    def update_settings(self, **changes) -> None:
        """修改设置并保存；影响数据的修改会触发刷新。"""
        before = dataclasses.replace(self.settings)
        for key, value in changes.items():
            setattr(self.settings, key, value)
        self.save()
        self.settings_changed.emit()
        if (
            before.data_source != self.settings.data_source
            or before.projects_dir != self.settings.projects_dir
        ):
            self._force_demo = False
            self._signature = None
            self.refresh()
        elif before.custom_prices != self.settings.custom_prices:
            self._rebuild()

    def set_custom_price(
        self, model: str, price: models.CustomPrice | None
    ) -> None:
        """添加、修改或删除（price 为 None）自定义单价。"""
        prices = dict(self.settings.custom_prices)
        if price is None:
            prices.pop(model, None)
        else:
            prices[model] = price
        self.update_settings(custom_prices=prices)

    # ---- 数据刷新 ---------------------------------------------------------

    def refresh(self) -> None:
        """重新加载用量数据（本机日志在后台扫描）。"""
        if self.data_source is models.DataSource.DEMO:
            self._rebuild()
            return
        if self._thread is not None:
            self._pending_refresh = True
            return
        self._thread = _ScanThread(self._scanner, self.projects_dir, self)
        self._thread.scanned.connect(self._on_scanned)
        self._thread.finished.connect(self._on_thread_finished)
        self.loading_changed.emit(True)
        self._thread.start()

    def _auto_refresh(self) -> None:
        self.clients.refresh()
        if self.data_source is models.DataSource.LOCAL and not self.loading:
            self.refresh()

    def _on_scanned(self, result: claude_code.ScanResult) -> None:
        self.scan = result
        self._local_records = result.records
        signature = (
            len(result.records),
            result.last,
            sum(record.total_tokens for record in result.records),
        )
        # 定时增量扫描大多没有新数据，此时不必重建数据集与刷新图表。
        if signature != self._signature:
            self._signature = signature
            self._rebuild()

    def _on_thread_finished(self) -> None:
        # 线程真正结束后才释放引用，shutdown() 因此总能等到它。
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.deleteLater()
        self.loading_changed.emit(False)
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def reattribute(self) -> None:
        """账号身份或来源时间线变化后，重新归属本机用量。"""
        if self.data_source is models.DataSource.LOCAL:
            self._rebuild()

    def _rebuild(self) -> None:
        if self.data_source is models.DataSource.DEMO:
            records = demo_data.generate(self.accounts)
        else:
            records = self.clients.attributor().assign(self._local_records)
        self.dataset = analytics.Dataset(records, self.price_book())
        self.records_changed.emit()

    def shutdown(self) -> None:
        """退出前停止定时器并等待后台任务结束。"""
        self._timer.stop()
        self.clients.shutdown()
        if self._thread is not None:
            self._thread.wait(5000)
        tasks.Task.wait_all()
