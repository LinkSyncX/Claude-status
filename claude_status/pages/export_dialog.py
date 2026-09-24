"""导出到其他工具（sub2api / CPA）时选择账号的对话框。"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import dialogs
from md3.components.dialogs import dialog as md3_dialog
from md3.components import selection
from md3.tokens import spacing

from claude_status import exporters
from claude_status import formatting
from claude_status import models
from claude_status.widgets import common

FORMATS = {
    exporters.SUB2API: (
        "导出到 sub2api",
        "生成 sub2api 管理后台“导入数据”可用的 JSON（sub2api-data）：订阅账号"
        "导出为 Anthropic OAuth 账号，API / 中转账号导出为 API Key 账号。",
    ),
    exporters.CPA: (
        "导出到 CPA（CLIProxyAPI）",
        "每个订阅账号生成一个 claude-*.json 认证文件，放进 CLIProxyAPI 的认证"
        "目录（默认 ~/.cli-proxy-api）即可使用；API / 中转账号生成 "
        "claude-api-key 配置片段，需合并到 config.yaml。",
    ),
}
# 复选框的方框加间距的宽度：说明文字与复选框的文字对齐。
CHECKBOX_TEXT_INDENT = 52
# 对话框内容区的宽度（md3 对话框最宽 560，两侧各有内边距）。
LIST_WIDTH = md3_dialog.MAX_WIDTH - 2 * md3_dialog.PADDING


def item_title(item: exporters.ExportItem) -> str:
    """列表中账号的标题：名称与账号类型。"""
    account = item.account
    oauth = account.auth_type is models.AuthType.OAUTH
    kind = "订阅" if oauth else account.auth_type.label
    return f"{account.display_name}（{kind}）"


def _wrapped(text: str, color: str, width: int) -> QtWidgets.QLabel:
    """固定宽度的换行说明：按实际宽度算出高度，避免对话框按提示尺寸裁掉末行。"""
    label = common.label(text, "body-small", color, wrap=True)
    common.fit_wrapped(label, width)
    return label


def unavailable_text(items: Sequence[exporters.ExportItem]) -> str:
    """不能导出的账号按原因合并成一段说明（没有时为空字符串）。"""
    groups: dict[str, list[str]] = {}
    for item in items:
        if item.reason:
            groups.setdefault(item.reason, []).append(item.account.display_name)
    return "\n".join(
        f"无法导出：{'、'.join(names)}。{reason}。"
        for reason, names in groups.items()
    )


def item_detail(item: exporters.ExportItem) -> str:
    """账号下方的说明：不能导出的原因、令牌状态或端点。"""
    if item.reason:
        return item.reason
    login = item.login
    if login is None:
        return item.account.base_url or "官方 API"
    parts = [login.email or item.account.email or "未知邮箱"]
    expires = login.expires_at
    if expires is not None:
        state = "已过期，导入后由对方续期" if login.expired() else "有效"
        parts.append(f"访问令牌{state}（{formatting.datetime_text(expires)}）")
    if item.live:
        parts.append(
            "这是 Claude Code 正在使用的登录：代理续期后本机会掉线，"
            "建议导出后在终端重新 claude /login 该账号并保存"
        )
    return " · ".join(parts)


class ExportDialog(dialogs.BasicDialog):
    """选择要导出的账号。

    Args:
        fmt: 导出格式（``exporters.SUB2API`` / ``exporters.CPA``）。
        items: 各账号的导出准备情况。
        parent: 父控件。
    """

    def __init__(
        self,
        fmt: str,
        items: Sequence[exporters.ExportItem],
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        title, text = FORMATS[fmt]
        super().__init__(title, text, parent=parent)
        self._rows: list[tuple[selection.Checkbox, exporters.ExportItem]] = []
        content = QtWidgets.QWidget()
        content.setFixedWidth(LIST_WIDTH)
        column = QtWidgets.QVBoxLayout(content)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(round(spacing.SPACE_1))
        for item in items:
            if not item.exportable:
                continue
            box = selection.Checkbox(item_title(item), True)
            box.toggled.connect(lambda _checked: self._sync())
            column.addWidget(box)
            detail = _wrapped(
                item_detail(item),
                "error" if item.live else "on_surface_variant",
                LIST_WIDTH - CHECKBOX_TEXT_INDENT,
            )
            holder = common.indented(detail, CHECKBOX_TEXT_INDENT)
            # 高度已按宽度算好：固定容器高度，避免布局按“高随宽变”把它压扁。
            holder.setFixedHeight(detail.minimumHeight())
            column.addWidget(holder)
            column.addSpacing(round(spacing.SPACE_2))
            self._rows.append((box, item))
        if not self._rows:
            column.addWidget(
                common.label("没有可以导出的账号。", "body-medium", wrap=True)
            )
        notes = [
            unavailable_text(items),
            "导出的文件包含明文登录令牌与密钥，请妥善保管，导入后建议删除。",
        ]
        column.addSpacing(round(spacing.SPACE_2))
        for note in filter(None, notes):
            column.addWidget(_wrapped(note, "on_surface_variant", LIST_WIDTH))
        self.set_content(content)
        self.add_action("取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole)
        self._export = self.add_action("导出…")
        self._sync()
        QtCore.QTimer.singleShot(0, self.adjustSize)

    def selected(self) -> list[exporters.ExportItem]:
        """勾选的、可以导出的账号。"""
        return [item for box, item in self._rows if box.checked and item.exportable]

    def _sync(self) -> None:
        self._export.setEnabled(bool(self.selected()))
