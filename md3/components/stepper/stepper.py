"""步骤条（Stepper）。

按顺序展示一个流程的若干步骤：24dp 圆形指示器（数字 / 勾 / 感叹号）、
标签与可选的说明文字，步骤之间用 1dp 连接线相连，已完成的段落为
``primary`` 色。支持水平（标签在指示器下方）与竖直（标签在右侧）两种
排列；``linear=True`` 时只能点击已完成的步骤、当前步骤或下一步。
"""

from __future__ import annotations

import dataclasses
import enum
from typing import Any
from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.navigation import _items
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import shape as shape_tokens
from md3.tokens import state as state_tokens
from md3.tokens import typography as typography_tokens

INDICATOR_SIZE = 24.0
INDICATOR_ICON_SIZE = 16.0
CONNECTOR_WIDTH = 1.0
CONNECTOR_GAP = 8.0
LABEL_GAP = 8.0
HORIZONTAL_ITEM_HEIGHT = 72.0
VERTICAL_ITEM_HEIGHT = 56.0
VERTICAL_ITEM_HEIGHT_WITH_DESCRIPTION = 72.0
VERTICAL_LABEL_GAP = 12.0
MIN_ITEM_WIDTH = 96.0
LABEL_STYLE = typography_tokens.TypeRole.LABEL_LARGE
DESCRIPTION_STYLE = typography_tokens.TypeRole.BODY_SMALL
NUMBER_STYLE = typography_tokens.TypeRole.LABEL_MEDIUM


class StepState(enum.Enum):
    """步骤状态。"""

    UPCOMING = "upcoming"
    ACTIVE = "active"
    COMPLETED = "completed"
    ERROR = "error"


@dataclasses.dataclass
class Step:
    """一个步骤。

    Attributes:
        label: 标签。
        description: 说明文字（竖直排列时显示在标签下方，水平时代替
            "可选"提示）。
        icon: 自定义指示器图标；None 时显示序号。
        optional: 是否为可选步骤（显示"可选"）。
        enabled: 是否可用。
        key: 业务侧标识。
    """

    label: str
    description: str = ""
    icon: icons.IconLike = None
    optional: bool = False
    enabled: bool = True
    key: Any = None


class Stepper(_items.SelectableItems):
    """步骤条。

    Args:
        steps: 步骤列表（字符串会转换为只有标签的步骤）。
        current: 当前步骤下标。
        orientation: 水平或竖直排列。
        linear: 为真时只能跳到已完成 / 当前 / 下一步。
        clickable: 是否允许点击切换步骤。
        parent: 父控件。
    """

    step_changed = QtCore.Signal(int)

    def __init__(
        self,
        steps: list[Step | str],
        current: int = 0,
        orientation: QtCore.Qt.Orientation = QtCore.Qt.Orientation.Horizontal,
        linear: bool = True,
        clickable: bool = True,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(
            parent,
            horizontal_keys=orientation == QtCore.Qt.Orientation.Horizontal,
        )
        self._steps = [
            Step(label=step) if isinstance(step, str) else step
            for step in steps
        ]
        self._orientation = orientation
        self._linear = linear
        self._clickable = clickable
        self._completed: set[int] = set()
        self._errors: set[int] = set()
        self._selected = current if 0 <= current < len(self._steps) else -1
        self._rebuild_states()
        self.selection_changed.connect(self.step_changed)
        if orientation == QtCore.Qt.Orientation.Horizontal:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Expanding,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )
        else:
            self.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Fixed,
            )

    # ---- 步骤与状态 -------------------------------------------------------

    @property
    def steps(self) -> list[Step]:
        """步骤列表。"""
        return list(self._steps)

    def set_steps(self, steps: list[Step | str]) -> None:
        """替换步骤。"""
        self._steps = [
            Step(label=step) if isinstance(step, str) else step
            for step in steps
        ]
        self._completed = {i for i in self._completed if i < len(self._steps)}
        self._errors = {i for i in self._errors if i < len(self._steps)}
        self._selected = min(self._selected, len(self._steps) - 1)
        self._rebuild_states()
        self.updateGeometry()
        self.update()

    @property
    def orientation(self) -> QtCore.Qt.Orientation:
        """排列方向。"""
        return self._orientation

    @property
    def horizontal(self) -> bool:
        """是否水平排列。"""
        return self._orientation == QtCore.Qt.Orientation.Horizontal

    @property
    def current_step(self) -> int:
        """当前步骤下标。"""
        return self._selected

    def set_current_step(self, index: int) -> None:
        """跳到指定步骤（不检查线性限制）。"""
        self.set_selected_index(index)

    def next_step(self, complete_current: bool = True) -> bool:
        """进入下一步，可同时把当前步骤标为已完成；已是最后一步返回 False。"""
        if self._selected >= len(self._steps) - 1:
            if complete_current and self._selected >= 0:
                self.set_completed(self._selected, True)
            return False
        if complete_current and self._selected >= 0:
            self.set_completed(self._selected, True)
        self.set_selected_index(self._selected + 1)
        return True

    def previous_step(self) -> bool:
        """回到上一步；已是第一步返回 False。"""
        if self._selected <= 0:
            return False
        self.set_selected_index(self._selected - 1)
        return True

    @property
    def completed_steps(self) -> list[int]:
        """已完成的步骤下标。"""
        return sorted(self._completed)

    def set_completed(self, index: int, completed: bool = True) -> None:
        """标记步骤是否完成。"""
        if not 0 <= index < len(self._steps):
            return
        if completed:
            self._completed.add(index)
            self._errors.discard(index)
        else:
            self._completed.discard(index)
        self.update()

    def set_error(self, index: int, error: bool = True) -> None:
        """标记步骤是否出错。"""
        if not 0 <= index < len(self._steps):
            return
        if error:
            self._errors.add(index)
            self._completed.discard(index)
        else:
            self._errors.discard(index)
        self.update()

    def reset(self) -> None:
        """清空完成与错误标记并回到第一步。"""
        self._completed.clear()
        self._errors.clear()
        self.set_selected_index(0 if self._steps else -1)
        self.update()

    def state_of(self, index: int) -> StepState:
        """步骤当前的状态。"""
        if index in self._errors:
            return StepState.ERROR
        if index in self._completed:
            return StepState.COMPLETED
        if index == self._selected:
            return StepState.ACTIVE
        return StepState.UPCOMING

    @property
    def linear(self) -> bool:
        """是否为线性流程。"""
        return self._linear

    def set_linear(self, linear: bool) -> None:
        """设置是否为线性流程。"""
        self._linear = linear

    def can_activate(self, index: int) -> bool:
        """点击是否可以切换到该步骤。"""
        if not self._clickable or not 0 <= index < len(self._steps):
            return False
        if not self._steps[index].enabled:
            return False
        if not self._linear:
            return True
        # 线性流程：已完成的、当前的，以及当前 / 最远完成步骤之后的一步。
        furthest = max(self._completed, default=-1)
        return (
            index in self._completed
            or index <= self._selected + 1
            or index <= furthest + 1
        )

    # ---- 无障碍 -----------------------------------------------------------

    @override
    def accessible_role(self) -> QtGui.QAccessible.Role:
        return QtGui.QAccessible.Role.PageTabList

    # ---- 项接口 -----------------------------------------------------------

    @override
    def item_count(self) -> int:
        return len(self._steps)

    @override
    def item_label(self, index: int) -> str:
        if 0 <= index < len(self._steps):
            return self._steps[index].label
        return ""

    @override
    def item_enabled(self, index: int) -> bool:
        return self.isEnabled() and self.can_activate(index)

    def _item_height(self) -> float:
        if self.horizontal:
            return HORIZONTAL_ITEM_HEIGHT
        if any(step.description or step.optional for step in self._steps):
            return VERTICAL_ITEM_HEIGHT_WITH_DESCRIPTION
        return VERTICAL_ITEM_HEIGHT

    def _logical_item_rect(self, index: int) -> QtCore.QRectF:
        count = max(1, len(self._steps))
        if self.horizontal:
            width = self.width() / count
            return QtCore.QRectF(index * width, 0.0, width, self.height())
        height = self._item_height()
        return QtCore.QRectF(0.0, index * height, self.width(), height)

    @override
    def item_rect(self, index: int) -> QtCore.QRectF:
        return self.visual_rect(self._logical_item_rect(index))

    def indicator_rect(self, index: int) -> QtCore.QRectF:
        """第 index 步指示器的矩形。"""
        rect = self._logical_item_rect(index)
        if self.horizontal:
            logical = QtCore.QRectF(
                rect.center().x() - INDICATOR_SIZE / 2,
                12.0,
                INDICATOR_SIZE,
                INDICATOR_SIZE,
            )
        else:
            logical = QtCore.QRectF(
                12.0,
                rect.center().y() - INDICATOR_SIZE / 2,
                INDICATOR_SIZE,
                INDICATOR_SIZE,
            )
        return self.visual_rect(logical)

    @override
    def item_state_path(self, index: int) -> QtGui.QPainterPath:
        return shape_utils.rounded_rect_path(
            self.indicator_rect(index).adjusted(-8, -8, 8, 8),
            shape_tokens.SHAPE_FULL,
        )

    @override
    def item_state_color(self, index: int) -> QtGui.QColor:
        return self.color("primary")

    @override
    def activate_item(self, index: int) -> None:
        if self.can_activate(index):
            self.set_selected_index(index)

    @override
    def sizeHint(self) -> QtCore.QSize:
        count = max(1, len(self._steps))
        if self.horizontal:
            return typography.size_hint(
                MIN_ITEM_WIDTH * count, HORIZONTAL_ITEM_HEIGHT
            )
        widest = max(
            (
                typography.text_width(step.label, LABEL_STYLE)
                for step in self._steps
            ),
            default=0.0,
        )
        return typography.size_hint(
            12.0 + INDICATOR_SIZE + VERTICAL_LABEL_GAP + widest + 16.0,
            self._item_height() * count,
        )

    @override
    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    # ---- 绘制 -------------------------------------------------------------

    def _indicator_colors(
        self, state: StepState, enabled: bool
    ) -> tuple[QtGui.QColor, QtGui.QColor]:
        """指示器 (填充色, 内容色)。"""
        if not enabled:
            return (
                theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTAINER_OPACITY,
                ),
                theme_module.with_alpha(
                    self.color("on_surface"),
                    state_tokens.DISABLED_CONTENT_OPACITY,
                ),
            )
        match state:
            case StepState.ERROR:
                return self.color("error"), self.color("on_error")
            case StepState.COMPLETED | StepState.ACTIVE:
                return self.color("primary"), self.color("on_primary")
            case _:
                return (
                    self.color("surface_container_highest"),
                    self.color("on_surface_variant"),
                )

    @override
    def paint(self, painter: QtGui.QPainter) -> None:
        for index in range(len(self._steps) - 1):
            self._paint_connector(painter, index)
        for index, step in enumerate(self._steps):
            self._paint_step(painter, index, step)
            self.paint_item_overlays(painter, index)

    def _paint_connector(self, painter: QtGui.QPainter, index: int) -> None:
        start = self.indicator_rect(index)
        end = self.indicator_rect(index + 1)
        done = index in self._completed
        color = self.color("primary" if done else "outline_variant")
        if self.horizontal:
            left, right = sorted((start.center().x(), end.center().x()))
            rect = QtCore.QRectF(
                left + INDICATOR_SIZE / 2 + CONNECTOR_GAP,
                start.center().y() - CONNECTOR_WIDTH / 2,
                max(0.0, right - left - INDICATOR_SIZE - 2 * CONNECTOR_GAP),
                CONNECTOR_WIDTH,
            )
        else:
            rect = QtCore.QRectF(
                start.center().x() - CONNECTOR_WIDTH / 2,
                start.bottom() + CONNECTOR_GAP,
                CONNECTOR_WIDTH,
                max(0.0, end.top() - start.bottom() - 2 * CONNECTOR_GAP),
            )
        painter.fillRect(rect, color)

    def _paint_step(
        self, painter: QtGui.QPainter, index: int, step: Step
    ) -> None:
        state = self.state_of(index)
        enabled = self.isEnabled() and step.enabled
        fill, content = self._indicator_colors(state, enabled)
        indicator = self.indicator_rect(index)
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(indicator, shape_tokens.SHAPE_FULL),
            fill,
        )
        icon_name: str | None = None
        if state is StepState.COMPLETED:
            icon_name = "check"
        elif state is StepState.ERROR:
            icon_name = "priority_high"
        icon = (
            icons.coerce(icon_name, INDICATOR_ICON_SIZE)
            if icon_name
            else icons.coerce(step.icon, INDICATOR_ICON_SIZE)
        )
        if icon is not None:
            icon.paint(
                painter,
                QtCore.QRectF(
                    indicator.center().x() - INDICATOR_ICON_SIZE / 2,
                    indicator.center().y() - INDICATOR_ICON_SIZE / 2,
                    INDICATOR_ICON_SIZE,
                    INDICATOR_ICON_SIZE,
                ),
                content,
            )
        else:
            typography.paint_text(
                painter,
                indicator,
                str(index + 1),
                NUMBER_STYLE,
                content,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
        if not enabled:
            label_color = theme_module.with_alpha(
                self.color("on_surface"), state_tokens.DISABLED_CONTENT_OPACITY
            )
        elif state is StepState.ERROR:
            label_color = self.color("error")
        elif state is StepState.UPCOMING:
            label_color = self.color("on_surface_variant")
        else:
            label_color = self.color("on_surface")
        secondary = step.description or (
            i18n.tr("step_optional") if step.optional else ""
        )
        rect = self._logical_item_rect(index)
        label_height = self.theme.style(LABEL_STYLE).line_height
        description_height = self.theme.style(DESCRIPTION_STYLE).line_height
        if self.horizontal:
            top = indicator.bottom() + LABEL_GAP
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        rect.left() + 4, top, rect.width() - 8, label_height
                    )
                ),
                step.label,
                LABEL_STYLE,
                label_color,
                QtCore.Qt.AlignmentFlag.AlignCenter,
            )
            if secondary:
                typography.paint_text(
                    painter,
                    self.visual_rect(
                        QtCore.QRectF(
                            rect.left() + 4,
                            top + label_height,
                            rect.width() - 8,
                            description_height,
                        )
                    ),
                    secondary,
                    DESCRIPTION_STYLE,
                    self.color("on_surface_variant"),
                    QtCore.Qt.AlignmentFlag.AlignCenter,
                )
            return
        left = 12.0 + INDICATOR_SIZE + VERTICAL_LABEL_GAP
        block = label_height + (description_height if secondary else 0.0)
        top = rect.center().y() - block / 2
        typography.paint_text(
            painter,
            self.visual_rect(
                QtCore.QRectF(left, top, rect.width() - left - 8, label_height)
            ),
            step.label,
            LABEL_STYLE,
            label_color,
            self.start_alignment(),
        )
        if secondary:
            typography.paint_text(
                painter,
                self.visual_rect(
                    QtCore.QRectF(
                        left,
                        top + label_height,
                        rect.width() - left - 8,
                        description_height,
                    )
                ),
                secondary,
                DESCRIPTION_STYLE,
                self.color("on_surface_variant"),
                self.start_alignment(),
            )
