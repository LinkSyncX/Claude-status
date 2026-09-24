"""设置页：数据源、切换与额度、外观、模型单价与数据管理。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import chips
from md3.components import data_table
from md3.components import dialogs
from md3.components import progress
from md3.components import selection
from md3.components import snackbar
from md3.components import text_fields
from md3.tokens import spacing

import claude_status
from claude_status import claude_code
from claude_status import models
from claude_status import pricing
from claude_status import secure
from claude_status import state as state_module
from claude_status.widgets import common

SEEDS: list[tuple[str, str]] = [
    ("Claude 陶土橙", "#D97757"),
    ("薰衣草紫", "#6750A4"),
    ("海湾蓝", "#0061A4"),
    ("松林绿", "#386A20"),
    ("琥珀金", "#8B5000"),
]
_SOURCES = [models.DataSource.LOCAL, models.DataSource.DEMO]
# 开关轨道加间距的宽度：开关下方的说明文字从这里开始。
SWITCH_TEXT_INDENT = 62
PRICE_COLUMNS = [
    ("input", "输入"),
    ("output", "输出"),
    ("write", "缓存写入 5m"),
    ("write_1h", "缓存写入 1h"),
    ("read", "缓存读取"),
]


def _price_text(value: float) -> str:
    return f"${value:g}"


class PriceDialog(dialogs.BasicDialog):
    """添加 / 编辑自定义单价。

    Args:
        models_: 可选择的模型（数据中出现过的模型）。
        model: 预选的模型。
        price: 已有的自定义单价；不为 None 时显示"删除"按钮。
        parent: 父控件。
    """

    DELETE = 2

    def __init__(
        self,
        models_: list[str],
        model: str = "",
        price: models.CustomPrice | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            "自定义单价",
            "单位为美元 / 百万 token。缓存写入按输入单价的 1.25 倍（5 分钟）"
            "与 2 倍（1 小时）计算；缓存读取填 0 表示按输入单价的 10% 计算。",
            parent=parent,
        )
        options = sorted(set(models_) | ({model} if model else set()))
        self.model = text_fields.SelectField(
            "模型 ID",
            options,
            options.index(model) if model in options else -1,
            editable=True,
            allow_custom=True,
        )
        if model and model not in options:
            self.model.set_text(model)
        defaults = (
            (price.input, price.output, price.cache_read or 0.0)
            if price is not None
            else (1.0, 5.0, 0.0)
        )
        self.input, self.output, self.cache_read = (
            text_fields.NumberField(
                label,
                value,
                minimum=0,
                maximum=1000,
                decimals=3,
                show_steppers=False,
                prefix="$",
                variant=text_fields.TextFieldVariant.OUTLINED,
            )
            for label, value in zip(
                ("输入", "输出", "缓存读取"), defaults, strict=True
            )
        )
        form = QtWidgets.QWidget()
        form.setMinimumWidth(460)
        layout = QtWidgets.QGridLayout(form)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(round(spacing.SPACE_3))
        layout.setVerticalSpacing(round(spacing.SPACE_2))
        layout.addWidget(self.model, 0, 0, 1, 3)
        fields = (self.input, self.output, self.cache_read)
        for column, field in enumerate(fields):
            layout.addWidget(field, 1, column, QtCore.Qt.AlignmentFlag.AlignTop)
        self.set_content(form)
        if price is not None:
            self.add_action(
                "删除", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
            ).clicked.connect(lambda: self.done(self.DELETE))
        self.add_action("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        save = self.add_action(
            "保存", QtWidgets.QDialogButtonBox.ButtonRole.ActionRole
        )
        save.clicked.connect(self._submit)

    def _submit(self) -> None:
        if not self.model_id():
            self.model.set_error(True, "请输入或选择模型 ID")
            return
        self.accept()

    def model_id(self) -> str:
        """输入的模型 ID。"""
        return self.model.text.strip()

    def price(self) -> models.CustomPrice:
        """输入的单价。"""
        cache_read = float(self.cache_read.value)
        return models.CustomPrice(
            float(self.input.value),
            float(self.output.value),
            cache_read if cache_read > 0 else None,
        )


class SettingsPage(common.Page):
    """设置页。

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
        self._price_rows: list[tuple[str, bool]] = []
        self._build_source()
        self._build_clients()
        self._build_appearance()
        self._build_prices()
        self._build_data()
        self.body.addStretch(1)
        state.settings_changed.connect(self._sync)
        state.loading_changed.connect(self._on_loading)
        state.records_changed.connect(self._sync)
        self._sync()

    # ---- 数据源 -----------------------------------------------------------

    def _build_source(self) -> None:
        card = common.SectionCard(
            "数据源",
            "本机日志读取 Claude Code 写在 ~/.claude/projects 中的会话记录，"
            "只统计用量字段、不读取对话内容；演示数据按账号列表模拟生成。",
            icon="database",
        )
        self._source = buttons.SegmentedButton(
            [
                buttons.Segment(source.label, icon)
                for source, icon in zip(
                    _SOURCES, ("terminal", "science"), strict=True
                )
            ],
            selected=[0],
        )
        self._source.selection_changed.connect(self._on_source_changed)
        card.content_layout.addLayout(common.row(self._source, None))
        self._directory = text_fields.OutlinedTextField(
            "日志目录",
            str(self._state.projects_dir),
            leading_icon="folder",
            supporting_text="留空使用默认位置（支持 CLAUDE_CONFIG_DIR 环境变量）",
        )
        self._directory.editing_finished.connect(self._on_directory_edited)
        browse = buttons.OutlinedButton("浏览…", icon="folder_open")
        browse.clicked.connect(self._browse)
        default = buttons.TextButton("恢复默认")
        default.clicked.connect(
            lambda: self._state.update_settings(projects_dir="")
        )
        directory_row = QtWidgets.QHBoxLayout()
        directory_row.setSpacing(round(spacing.SPACE_2))
        directory_row.addWidget(self._directory, 1)
        directory_row.addWidget(browse, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        directory_row.addWidget(default, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        card.content_layout.addLayout(directory_row)
        self._rescan = buttons.FilledTonalButton("重新扫描", icon="refresh")
        self._rescan.clicked.connect(self._state.refresh)
        self._scan_progress = progress.CircularProgressIndicator(None)
        self._scan_progress.setFixedSize(28, 28)
        self._scan_progress.hide()
        self._scan_label = common.label(
            "", "body-small", "on_surface_variant", wrap=True, selectable=True
        )
        scan_row = common.row(
            self._rescan, self._scan_progress, spacing_px=round(spacing.SPACE_3)
        )
        scan_row.addWidget(self._scan_label, 1)
        card.content_layout.addLayout(scan_row)
        self.body.addWidget(card)

    def _on_source_changed(self, indices: list[int]) -> None:
        if indices:
            self._state.update_settings(data_source=_SOURCES[indices[0]])

    def _on_directory_edited(self) -> None:
        text = self._directory.text.strip()
        default = str(claude_code.default_projects_dir())
        value = "" if text in ("", default) else text
        if value != self._state.settings.projects_dir:
            self._state.update_settings(projects_dir=value)

    def _browse(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self.window(), "选择 Claude Code 日志目录", str(self._state.projects_dir)
        )
        if path:
            self._directory.set_text(path)
            self._on_directory_edited()

    def _on_loading(self, loading: bool) -> None:
        self._scan_progress.setVisible(loading)
        local = self._state.data_source is models.DataSource.LOCAL
        self._rescan.setEnabled(local and not loading)
        self._scan_label.setText(
            "正在扫描日志…" if loading else self._scan_text()
        )

    def _scan_text(self) -> str:
        state = self._state
        if state.data_source is models.DataSource.DEMO:
            count = len(state.dataset.records)
            return f"演示数据：{len(state.accounts)} 个账号，{count:,} 条按小时聚合的记录"
        scan = state.scan
        if scan is None:
            return "尚未扫描"
        if scan.error:
            return f"扫描失败：{scan.error}"
        if not scan.exists:
            return f"目录不存在：{scan.directory}"
        span = ""
        if scan.first and scan.last:
            span = (
                f" · {scan.first:%Y-%m-%d} 至 {scan.last:%Y-%m-%d}"
            )
        return (
            f"{scan.files} 个日志文件 · {scan.rows:,} 行用量记录，去重后 "
            f"{len(scan.records):,} 次请求（合并 {scan.duplicates:,} 条重复）"
            f"{span} · 耗时 {scan.elapsed:.2f} 秒"
        )

    # ---- 切换与额度 -------------------------------------------------------

    def _build_clients(self) -> None:
        card = common.SectionCard(
            "切换与额度",
            "一键切换账号与订阅额度查询；Claude Code、Claude Desktop 的登录"
            "管理在“客户端”页。",
            icon="swap_horiz",
        )
        settings = self._state.settings
        self._switch_desktop = selection.Switch(
            "一键切换时同时切换 Claude Desktop（需保存过该账号的 Desktop 登录）",
            settings.switch_desktop,
        )
        self._switch_desktop.toggled.connect(
            lambda checked: self._state.update_settings(switch_desktop=checked)
        )
        card.add_widget(self._switch_desktop)
        self._relaunch = selection.Switch(
            "切换后重新启动 Claude Desktop（切换前它正在运行时）",
            settings.relaunch_desktop,
        )
        self._relaunch.toggled.connect(
            lambda checked: self._state.update_settings(relaunch_desktop=checked)
        )
        card.add_widget(self._relaunch)
        self._quota_online = selection.Switch(
            "联网查询订阅额度", settings.quota_online
        )
        self._quota_online.toggled.connect(self._on_quota_online)
        offline = self._state.clients.offline
        self._quota_online.setEnabled(not offline)
        card.add_widget(self._quota_online)
        hint = common.label(
            "已通过 --offline 参数禁用联网。"
            if offline
            else "用保存的登录令牌查询 api.anthropic.com，每 10 分钟自动刷新；"
            "Claude Code 正在使用的登录只读取、不续期令牌。关闭后只使用 "
            "Claude Desktop 采样与 Claude Code 缓存中的额度。",
            "body-small",
            "on_surface_variant",
            wrap=True,
        )
        # 与开关的文字对齐，而不是与开关本身对齐。
        card.add_widget(common.indented(hint, SWITCH_TEXT_INDENT))
        self._proxy = text_fields.OutlinedTextField(
            "代理",
            settings.proxy,
            leading_icon="lan",
            supporting_text="例如 http://127.0.0.1:7890；留空时使用系统代理",
        )
        self._proxy.editing_finished.connect(self._on_proxy_edited)
        card.add_widget(self._proxy)
        card.add_widget(
            common.label(
                f"保存的登录、会话备份与 API Key {secure.description()}。",
                "body-small",
                "on_surface_variant",
                wrap=True,
            )
        )
        self.body.addWidget(card)

    def _on_quota_online(self, checked: bool) -> None:
        self._state.update_settings(quota_online=checked)
        if checked:
            self._state.clients.refresh_quotas(manual=False)

    def _on_proxy_edited(self) -> None:
        value = self._proxy.text.strip()
        if value != self._state.settings.proxy:
            self._state.update_settings(proxy=value)

    # ---- 外观 -------------------------------------------------------------

    def _build_appearance(self) -> None:
        card = common.SectionCard(
            "外观", "Material Design 3 动态配色", icon="palette"
        )
        self._dark = selection.Switch("深色模式", self._state.settings.dark)
        self._dark.toggled.connect(
            lambda checked: self._state.update_settings(dark=checked)
        )
        card.add_widget(self._dark)
        card.add_widget(
            common.label("主题色", "label-large", "on_surface_variant")
        )
        self._seeds = chips.ChipGroup(
            [
                chips.FilterChip(name, icon="palette")
                for name, _color in SEEDS
            ],
            single_selection=True,
        )
        self._seeds.selection_changed.connect(self._on_seed_changed)
        card.add_widget(self._seeds)
        self.body.addWidget(card)

    def _on_seed_changed(self, indices: list[int]) -> None:
        if indices:
            self._state.update_settings(seed=SEEDS[indices[0]][1])

    # ---- 单价 -------------------------------------------------------------

    def _build_prices(self) -> None:
        self._prices_card = common.SectionCard(
            "模型单价",
            "美元 / 百万 token（Anthropic 一方 API 价格，2026-06）。订阅套餐不按"
            " token 计费，金额仅供参考；双击自定义条目可修改或删除。",
            icon="sell",
        )
        add = buttons.FilledTonalButton("添加自定义单价", icon="add")
        add.clicked.connect(lambda: self._edit_price(""))
        self._prices_card.add_header_widget(add)
        self._unpriced = common.label("", "body-small", "error", wrap=True)
        self._prices_card.add_widget(self._unpriced)
        self._price_table = data_table.DataTable(
            [
                data_table.Column("model", "模型 ID", width=190),
                data_table.Column("name", "名称", width=170),
                *(
                    data_table.Column(
                        key, title, numeric=True, formatter=_price_text
                    )
                    for key, title in PRICE_COLUMNS
                ),
                data_table.Column("source", "来源", width=80),
            ],
            page_size=10,
            dense=True,
        )
        self._price_table.setMinimumHeight(420)
        self._price_table.row_activated.connect(self._on_price_activated)
        self._prices_card.add_widget(self._price_table)
        self.body.addWidget(self._prices_card)

    def _sync_prices(self) -> None:
        book = self._state.price_book()
        rows = []
        self._price_rows = []
        for model, price in book.rows():
            self._price_rows.append((model, price.custom))
            rows.append(
                {
                    "model": model,
                    "name": price.display_name,
                    "input": price.input,
                    "output": price.output,
                    "write": price.cache_write_5m,
                    "write_1h": price.cache_write_1h,
                    "read": price.cache_read,
                    "source": "自定义" if price.custom else "内置",
                }
            )
        self._price_table.set_rows(rows)
        unknown = self._unpriced_models(book)
        self._unpriced.setVisible(bool(unknown))
        if unknown:
            shown = "、".join(unknown[:6]) + ("…" if len(unknown) > 6 else "")
            self._unpriced.setText(
                f"数据中有 {len(unknown)} 个模型没有单价（费用不计入）：{shown}"
            )

    def _unpriced_models(self, book: pricing.PriceBook) -> list[str]:
        return [
            model
            for model in self._state.known_models()
            if book.lookup(model) is None
        ]

    def _on_price_activated(self, row: int) -> None:
        if 0 <= row < len(self._price_rows):
            model, custom = self._price_rows[row]
            self._edit_price(model if custom else "", model)

    def _edit_price(self, custom_model: str, prefill: str = "") -> None:
        book = self._state.price_book()
        choices = self._unpriced_models(book)
        existing = self._state.settings.custom_prices.get(custom_model)
        dialog = PriceDialog(
            choices + ([custom_model] if custom_model else []),
            custom_model or prefill or (choices[0] if choices else ""),
            existing,
            self.window(),
        )
        result = dialog.exec()
        if result == PriceDialog.DELETE:
            self._state.set_custom_price(custom_model, None)
            snackbar.show(self, f"已删除 {custom_model} 的自定义单价")
        elif result == QtWidgets.QDialog.DialogCode.Accepted:
            model = dialog.model_id()
            if custom_model and model != custom_model:
                self._state.set_custom_price(custom_model, None)
            self._state.set_custom_price(model, dialog.price())
            snackbar.show(self, f"已保存 {model} 的单价")

    # ---- 数据管理 ---------------------------------------------------------

    def _build_data(self) -> None:
        card = common.SectionCard(
            "数据管理",
            "账号、设置与保存的登录都在本机数据目录中；API Key 与登录令牌"
            f"{secure.description()}。",
            icon="folder",
        )
        path = common.label(
            str(self._state.store.path), "body-small", "on_surface_variant",
            selectable=True,
        )
        card.add_widget(path)
        open_dir = buttons.OutlinedButton("打开数据目录", icon="folder_open")
        open_dir.clicked.connect(self._open_data_dir)
        samples = buttons.TextButton("添加示例账号", icon="science")
        samples.clicked.connect(self._add_samples)
        clear = buttons.TextButton("清空全部账号", icon="delete_forever")
        clear.clicked.connect(self._clear_accounts)
        card.content_layout.addLayout(
            common.row(open_dir, samples, clear, None)
        )
        card.add_widget(
            common.label(
                f"{claude_status.APP_NAME} {claude_status.__version__} · "
                "界面基于 md3（PySide6 Material Design 3 组件库）",
                "body-small",
                "on_surface_variant",
            )
        )
        self.body.addWidget(card)

    def _open_data_dir(self) -> None:
        directory = self._state.store.directory
        directory.mkdir(parents=True, exist_ok=True)
        QtGui.QDesktopServices.openUrl(
            QtCore.QUrl.fromLocalFile(str(directory))
        )

    def _add_samples(self) -> None:
        count = self._state.add_sample_accounts()
        snackbar.show(self, f"已添加 {count} 个示例账号（标签“示例”）")

    def _clear_accounts(self) -> None:
        if not self._state.accounts:
            snackbar.show(self, "没有可清空的账号")
            return
        if not dialogs.confirm(
            self.window(),
            f"清空全部 {len(self._state.accounts)} 个账号？",
            "账号资料与保存的密钥将从本机删除（配置文件会保留一份 .bak 备份）。",
            confirm_text="全部清空",
            icon="delete_forever",
        ):
            return
        removed, active = self._state.delete_accounts(
            {a.id for a in self._state.accounts}
        )
        snackbar.show(
            self,
            f"已清空 {len(removed)} 个账号",
            "撤销",
            lambda: self._state.restore_accounts(removed, active),
            duration_ms=8000,
        )

    # ---- 同步 -------------------------------------------------------------

    def _sync(self) -> None:
        settings = self._state.settings
        index = _SOURCES.index(self._state.data_source)
        if self._source.selected_indices != [index]:
            self._source.blockSignals(True)
            self._source.set_selected([index])
            self._source.blockSignals(False)
        local = self._state.data_source is models.DataSource.LOCAL
        self._directory.setEnabled(local)
        self._rescan.setEnabled(local and not self._state.loading)
        directory = str(self._state.projects_dir)
        editing = self._directory.editor.hasFocus()
        if self._directory.text != directory and not editing:
            self._directory.set_text(directory)
        self._scan_label.setText(self._scan_text())
        for switch, value in (
            (self._dark, settings.dark),
            (self._switch_desktop, settings.switch_desktop),
            (self._relaunch, settings.relaunch_desktop),
            (self._quota_online, settings.quota_online),
        ):
            if switch.checked != value:
                switch.blockSignals(True)
                switch.set_checked(value)
                switch.blockSignals(False)
        if self._proxy.text != settings.proxy and not self._proxy.editor.hasFocus():
            self._proxy.set_text(settings.proxy)
        seed = settings.seed.lower()
        selected = [
            index
            for index, (_name, color) in enumerate(SEEDS)
            if color.lower() == seed
        ]
        if self._seeds.selected_indices != selected:
            self._seeds.blockSignals(True)
            self._seeds.set_selected(selected)
            self._seeds.blockSignals(False)
        self._sync_prices()
