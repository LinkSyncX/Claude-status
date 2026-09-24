"""统计卡片：图标、指标名、数值与相对上期的变化。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import cards
from md3.core import typography
from md3.tokens import spacing

from claude_status import formatting
from claude_status.widgets import common


class StatCard(cards.Card):
    """一个关键指标。

    Args:
        title: 指标名。
        icon: 图标。
        role: 图标底色角色（``primary`` / ``tertiary`` / ``secondary`` …）。
        increase_is_good: 数值上升是否为好事（决定变化率的颜色）。
        parent: 父控件。
    """

    def __init__(
        self,
        title: str,
        icon: str,
        role: str = "primary",
        increase_is_good: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(cards.CardVariant.FILLED, parent=parent)
        self._increase_is_good = increase_is_good
        self.set_content_margins(spacing.Insets.all(spacing.SPACE_4))
        self.content_layout.setSpacing(round(spacing.SPACE_1))
        top = QtWidgets.QHBoxLayout()
        top.setSpacing(round(spacing.SPACE_3))
        self._badge = common.IconBadge(icon, role, 36)
        top.addWidget(self._badge)
        self._title = typography.Label(
            title, "label-large", "on_surface_variant"
        )
        top.addWidget(self._title, 1)
        self.content_layout.addLayout(top)
        self.content_layout.addSpacing(round(spacing.SPACE_2))
        self._value = typography.Label("—", "headline-medium", "on_surface")
        self.content_layout.addWidget(self._value)
        bottom = QtWidgets.QHBoxLayout()
        bottom.setSpacing(round(spacing.SPACE_2))
        self._delta = common.Pill("", "surface")
        self._delta.setToolTip("与上一个等长区间相比")
        self._delta.hide()
        bottom.addWidget(self._delta, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._caption = common.ElidedLabel("", "body-small", "on_surface_variant")
        bottom.addWidget(self._caption, 1)
        self.content_layout.addLayout(bottom)
        self.setMinimumWidth(180)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_value(
        self,
        value: str,
        change: float | None | str = "",
        caption: str = "",
    ) -> None:
        """更新数值。

        Args:
            value: 已格式化的数值文字。
            change: 相对上期的变化率；None 表示无上期数据，空字符串表示
                不显示变化。
            caption: 额外说明，显示在变化率之后。
        """
        self._value.setText(value)
        prefix = ""
        numeric = change if isinstance(change, float) else None
        if change == "":
            self._delta.hide()
        elif numeric is None:
            self._delta.hide()
            prefix = "无上期数据"
        else:
            prefix = "较上期"
            if abs(numeric) < 0.0005:
                self._delta.set_text("持平")
                self._delta.set_role("secondary", "trending_flat")
            else:
                good = (numeric > 0) == self._increase_is_good
                self._delta.set_text(formatting.change_percent(numeric))
                self._delta.set_role(
                    "success" if good else "error",
                    "trending_up" if numeric > 0 else "trending_down",
                )
            self._delta.show()
        self._caption.setText(" · ".join(part for part in (prefix, caption) if part))
