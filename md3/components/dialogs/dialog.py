"""对话框（Dialogs）。

``BasicDialog`` 是居中的模态对话框：28dp 圆角、``surface_container_high``
容器、level 3 阴影、可选图标、标题、说明文字、自定义内容与操作按钮，
父窗口上覆盖 32% 的遮罩。``FullScreenDialog`` 占满父窗口，顶部带关闭
按钮、标题与确认操作。

``ListDialog`` 在标题与操作之间放置一组带单选 / 复选框的选项（上下各一
条分隔线，选项多时滚动）；``ProgressDialog`` 显示线性进度与可选的取消
按钮。模块级便捷函数 ``alert`` / ``confirm`` / ``prompt`` / ``choose`` /
``choose_many`` 以同步方式弹出对话框并返回结果。
"""

from __future__ import annotations

from typing import override

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from md3 import i18n
from md3.components.buttons import common as buttons
from md3.components.buttons import icon_button
from md3.components.lists import list_view
from md3.components.progress import indicators
from md3.components.selection import checkbox as checkbox_module
from md3.components.selection import radio as radio_module
from md3.components.text_fields import text_field
from md3.core import animation
from md3.core import elevation as elevation_utils
from md3.core import overlay
from md3.core import shape as shape_utils
from md3.core import typography
from md3.theme import icons
from md3.theme import theme as theme_module
from md3.tokens import elevation
from md3.tokens import motion
from md3.tokens import shape as shape_tokens
from md3.tokens import spacing
from md3.tokens import typography as typography_tokens

MIN_WIDTH = 280
MAX_WIDTH = 560
PADDING = 24
ICON_SIZE = 24.0
SHADOW_MARGIN = 24
ACTION_GAP = 8
HEADLINE_STYLE = typography_tokens.TypeRole.HEADLINE_SMALL
SUPPORTING_STYLE = typography_tokens.TypeRole.BODY_MEDIUM
ELEVATION = elevation.Level.LEVEL_3
# 列表对话框可见区域的最大高度，超出后滚动。
LIST_MAX_HEIGHT = 320


class _DialogBase(QtWidgets.QDialog):
    """无边框、透明背景的对话框基类，负责遮罩与主题订阅。"""

    def __init__(self, parent: QtWidgets.QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.WindowType.Dialog
            | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self._scrim: overlay.Scrim | None = None
        self._fade = animation.AnimatedFloat(self, 1.0, self._apply_opacity)
        theme_module.manager().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, theme: theme_module.Theme) -> None:
        del theme
        self.update()

    def _apply_opacity(self) -> None:
        self.setWindowOpacity(self._fade.value)

    def _host(self) -> QtWidgets.QWidget | None:
        parent = self.parentWidget()
        return parent.window() if parent is not None else None

    @override
    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        host = self._host()
        if host is not None:
            if self._scrim is None:
                self._scrim = overlay.Scrim(host)
            self._scrim.fade_in()
        self._center_on_host()
        # 对话框淡入，与遮罩同步出现。
        self._fade.set(0.0)
        self._fade.animate_to(1.0, motion.MEDIUM2, motion.STANDARD_DECELERATE)

    @override
    def hideEvent(self, event: QtGui.QHideEvent) -> None:
        super().hideEvent(event)
        if self._scrim is not None:
            self._scrim.fade_out()

    def _center_on_host(self) -> None:
        host = self._host()
        self.adjustSize()
        if host is None:
            return
        center = host.mapToGlobal(host.rect().center())
        self.move(
            center.x() - self.width() // 2, center.y() - self.height() // 2
        )


class BasicDialog(_DialogBase):
    """基础对话框。

    Args:
        headline: 标题。
        supporting_text: 说明文字。
        icon: 可选图标，存在时标题居中。
        parent: 父控件，对话框会居中于其窗口并显示遮罩。
    """

    def __init__(
        self,
        headline: str = "",
        supporting_text: str = "",
        icon: icons.IconLike = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._headline = headline
        self._supporting_text = supporting_text
        self._icon = icons.coerce(icon, ICON_SIZE)
        self._actions: list[buttons.TextButton] = []
        self._content: QtWidgets.QWidget | None = None
        self._build()

    def _build(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(
            SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN
        )
        self._panel = QtWidgets.QWidget(self)
        root.addWidget(self._panel)
        layout = QtWidgets.QVBoxLayout(self._panel)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)
        layout.setSpacing(round(spacing.SPACE_4))
        centered = self._icon is not None
        if self._icon is not None:
            self._icon_label = QtWidgets.QLabel(self._panel)
            self._icon_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
            self._icon_label.setFixedHeight(int(ICON_SIZE))
            layout.addWidget(self._icon_label)
        self._headline_label = typography.Label(
            self._headline, HEADLINE_STYLE, "on_surface", self._panel
        )
        self._headline_label.setWordWrap(True)
        if centered:
            self._headline_label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignCenter
            )
        layout.addWidget(self._headline_label)
        self._supporting_label = typography.Label(
            self._supporting_text,
            SUPPORTING_STYLE,
            "on_surface_variant",
            self._panel,
        )
        self._supporting_label.setWordWrap(True)
        self._supporting_label.setVisible(bool(self._supporting_text))
        layout.addWidget(self._supporting_label)
        self._content_slot = QtWidgets.QVBoxLayout()
        self._content_slot.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(self._content_slot)
        self._actions_layout = QtWidgets.QHBoxLayout()
        self._actions_layout.setContentsMargins(0, round(spacing.SPACE_2), 0, 0)
        self._actions_layout.setSpacing(ACTION_GAP)
        self._actions_layout.addStretch()
        layout.addLayout(self._actions_layout)
        self._panel.setMinimumWidth(MIN_WIDTH)
        self._panel.setMaximumWidth(MAX_WIDTH)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if self._icon is None:
            return
        pixmap = self._icon.pixmap(
            theme_module.current().color("secondary"), self.devicePixelRatioF()
        )
        self._icon_label.setPixmap(pixmap)

    # ---- 内容与操作 -------------------------------------------------------

    @property
    def headline(self) -> str:
        """标题。"""
        return self._headline

    def set_headline(self, headline: str) -> None:
        """设置标题。"""
        self._headline = headline
        self._headline_label.setText(headline)

    def set_supporting_text(self, text: str) -> None:
        """设置说明文字。"""
        self._supporting_text = text
        self._supporting_label.setText(text)
        self._supporting_label.setVisible(bool(text))

    def set_content(self, content: QtWidgets.QWidget) -> None:
        """放入自定义内容控件（位于说明文字与操作之间）。"""
        if self._content is not None:
            self._content_slot.removeWidget(self._content)
            self._content.setParent(None)
        self._content = content
        self._content_slot.addWidget(content)

    def add_action(
        self,
        text: str,
        role: QtWidgets.QDialogButtonBox.ButtonRole = (
            QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole
        ),
    ) -> buttons.TextButton:
        """追加一个文字按钮操作。

        Args:
            text: 按钮文字。
            role: ``AcceptRole`` 触发 ``accept``、``RejectRole`` 触发
                ``reject``，其他角色仅发出按钮的 ``clicked``。

        Returns:
            创建的按钮，可继续连接信号。
        """
        button = buttons.TextButton(text, parent=self._panel)
        if role == QtWidgets.QDialogButtonBox.ButtonRole.AcceptRole:
            button.clicked.connect(self.accept)
        elif role == QtWidgets.QDialogButtonBox.ButtonRole.RejectRole:
            button.clicked.connect(self.reject)
        self._actions.append(button)
        self._actions_layout.addWidget(button)
        return button

    @property
    def action_buttons(self) -> list[buttons.TextButton]:
        """已添加的操作按钮。"""
        return list(self._actions)

    # ---- 绘制 -------------------------------------------------------------

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = QtCore.QRectF(self._panel.geometry())
        shape = shape_tokens.SHAPE_EXTRA_LARGE
        elevation_utils.paint_shadow(
            painter,
            rect,
            shape,
            ELEVATION,
            theme.color("shadow"),
            self.devicePixelRatioF(),
        )
        shape_utils.fill_shape(
            painter,
            shape_utils.rounded_rect_path(rect, shape),
            theme.color("surface_container_high"),
        )
        painter.end()
        self._refresh_icon()


class FullScreenDialog(_DialogBase):
    """全屏对话框：覆盖父窗口，顶部为关闭按钮、标题与确认操作。

    Args:
        title: 标题。
        action_text: 右上角确认操作的文字，为空则不显示。
        parent: 父控件。
    """

    APP_BAR_HEIGHT = 56

    def __init__(
        self,
        title: str = "",
        action_text: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if action_text is None:
            action_text = i18n.tr("save")
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._bar = QtWidgets.QWidget(self)
        self._bar.setFixedHeight(self.APP_BAR_HEIGHT)
        bar_layout = QtWidgets.QHBoxLayout(self._bar)
        bar_layout.setContentsMargins(4, 0, 4, 0)
        bar_layout.setSpacing(4)
        self._close_button = icon_button.IconButton(
            "close", tooltip=i18n.tr("close")
        )
        self._close_button.clicked.connect(self.reject)
        bar_layout.addWidget(self._close_button)
        self._title_label = typography.Label(
            title, typography_tokens.TypeRole.TITLE_LARGE, "on_surface"
        )
        bar_layout.addWidget(self._title_label, 1)
        self._action_button: buttons.TextButton | None = None
        if action_text:
            self._action_button = buttons.TextButton(action_text)
            self._action_button.clicked.connect(self.accept)
            bar_layout.addWidget(self._action_button)
        root.addWidget(self._bar)
        self._scroll = QtWidgets.QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._body = QtWidgets.QWidget()
        self._body_layout = QtWidgets.QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(
            PADDING, round(spacing.SPACE_4), PADDING, PADDING
        )
        self._body_layout.setSpacing(round(spacing.SPACE_4))
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

    @property
    def content_layout(self) -> QtWidgets.QVBoxLayout:
        """内容区布局。"""
        return self._body_layout

    def add_widget(self, child: QtWidgets.QWidget) -> None:
        """向内容区追加控件。"""
        self._body_layout.addWidget(child)

    @property
    def action_button(self) -> buttons.TextButton | None:
        """右上角操作按钮。"""
        return self._action_button

    def set_title(self, title: str) -> None:
        """设置标题。"""
        self._title_label.setText(title)

    @override
    def _center_on_host(self) -> None:
        host = self._host()
        if host is None:
            return
        self.setGeometry(
            QtCore.QRect(host.mapToGlobal(QtCore.QPoint(0, 0)), host.size())
        )

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = theme_module.current()
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), theme.color("surface"))
        painter.fillRect(
            QtCore.QRectF(0, self.APP_BAR_HEIGHT - 1, self.width(), 1),
            theme.color("outline_variant"),
        )
        painter.end()


class _DividerLine(QtWidgets.QWidget):
    """对话框内部的 1px 分隔线。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(1)

    @override
    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.fillRect(
            self.rect(), theme_module.current().color("outline_variant")
        )
        painter.end()


class ListDialog(BasicDialog):
    """列表对话框：在标题与操作之间提供单选或多选的选项列表。

    Args:
        headline: 标题。
        options: 选项文字列表。
        selected: 初始选中下标（单选给一个 int，多选给列表）。
        multiple: 为真时使用复选框多选，否则使用单选按钮。
        supporting_text: 说明文字。
        icon: 可选图标。
        confirm_text: 确认按钮文字。
        cancel_text: 取消按钮文字。
        parent: 父控件。
    """

    selection_changed = QtCore.Signal(list)

    def __init__(
        self,
        headline: str,
        options: list[str],
        selected: int | list[int] | None = None,
        multiple: bool = False,
        supporting_text: str = "",
        icon: icons.IconLike = None,
        confirm_text: str | None = None,
        cancel_text: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(headline, supporting_text, icon, parent)
        confirm_text = _text_or_default(confirm_text, "confirm")
        cancel_text = _text_or_default(cancel_text, "cancel")
        self._multiple = multiple
        self._options = list(options)
        self._controls: list[
            checkbox_module.Checkbox | radio_module.RadioButton
        ] = []
        self._group: radio_module.RadioGroup | None = None
        container = QtWidgets.QWidget()
        column = QtWidgets.QVBoxLayout(container)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(_DividerLine())
        self._list = list_view.ListView()
        self._list.setMaximumHeight(LIST_MAX_HEIGHT)
        if not multiple:
            self._group = radio_module.RadioGroup(parent=self)
        for index, text in enumerate(options):
            control: checkbox_module.Checkbox | radio_module.RadioButton
            if multiple:
                control = checkbox_module.Checkbox()
            else:
                control = radio_module.RadioButton()
                self._group.add(control)
            control.toggled.connect(self._on_control_toggled)
            self._controls.append(control)
            item = self._list.add(text, leading_widget=control)
            item.clicked.connect(
                lambda checked=False, index=index: self._on_item_clicked(index)
            )
        column.addWidget(self._list)
        column.addWidget(_DividerLine())
        self.set_content(container)
        self._list.setMinimumHeight(
            min(LIST_MAX_HEIGHT, 56 * len(options) + 16)
        )
        if selected is not None:
            self.set_selected(
                [selected] if isinstance(selected, int) else list(selected)
            )
        if cancel_text:
            self.add_action(
                cancel_text, QtWidgets.QDialogButtonBox.ButtonRole.RejectRole
            )
        self.add_action(confirm_text)

    @property
    def options(self) -> list[str]:
        """选项文字。"""
        return list(self._options)

    @property
    def selected_indices(self) -> list[int]:
        """当前选中的下标。"""
        return [
            index
            for index, control in enumerate(self._controls)
            if control.checked
        ]

    @property
    def selected_index(self) -> int:
        """单选时的选中下标，未选择为 -1。"""
        indices = self.selected_indices
        return indices[0] if indices else -1

    def set_selected(self, indices: list[int]) -> None:
        """设置选中项（单选只取第一个）。"""
        chosen = set(indices)
        if not self._multiple and len(chosen) > 1:
            chosen = {min(chosen)}
        for index, control in enumerate(self._controls):
            control.set_checked(index in chosen)

    def _on_item_clicked(self, index: int) -> None:
        control = self._controls[index]
        if self._multiple:
            control.set_checked(not control.checked)
        else:
            control.set_checked(True)

    def _on_control_toggled(self, checked: bool) -> None:
        del checked
        self.selection_changed.emit(self.selected_indices)


class ProgressDialog(BasicDialog):
    """进度对话框：标题、说明与线性进度指示器，可选取消按钮。

    Args:
        headline: 标题。
        supporting_text: 说明文字（可用 ``set_supporting_text`` 更新）。
        value: 初始进度 0–1；None 为不确定态。
        cancel_text: 取消按钮文字，为空则不可取消。
        parent: 父控件。
    """

    canceled = QtCore.Signal()

    def __init__(
        self,
        headline: str,
        supporting_text: str = "",
        value: float | None = None,
        cancel_text: str | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(headline, supporting_text, parent=parent)
        cancel_text = _text_or_default(cancel_text, "cancel")
        self._indicator = indicators.LinearProgressIndicator(value)
        self._indicator.setMinimumWidth(MIN_WIDTH - 2 * PADDING)
        self.set_content(self._indicator)
        self._cancel_button: buttons.TextButton | None = None
        if cancel_text:
            self._cancel_button = self.add_action(
                cancel_text, QtWidgets.QDialogButtonBox.ButtonRole.RejectRole
            )
            self.rejected.connect(self.canceled)

    @property
    def indicator(self) -> indicators.LinearProgressIndicator:
        """进度指示器。"""
        return self._indicator

    @property
    def value(self) -> float | None:
        """当前进度；不确定态为 None。"""
        if self._indicator.indeterminate:
            return None
        return self._indicator.value

    def set_value(self, value: float | None) -> None:
        """设置进度（None 切换为不确定态）。"""
        if value is None:
            self._indicator.set_indeterminate(True)
            return
        self._indicator.set_indeterminate(False)
        self._indicator.set_value(value)

    def set_progress(self, done: int, total: int, text: str = "") -> None:
        """按已完成 / 总数设置进度，并可同时更新说明文字。"""
        self.set_value(done / total if total > 0 else None)
        if text:
            self.set_supporting_text(text)

    def finish(self) -> None:
        """进度完成，关闭对话框。"""
        self.accept()


# ---- 便捷函数 -----------------------------------------------------------


def _text_or_default(text: str | None, key: str) -> str:
    """None 时取当前语言的默认文字（空字符串表示不显示）。"""
    return i18n.tr(key) if text is None else text


def alert(
    parent: QtWidgets.QWidget | None,
    headline: str,
    supporting_text: str = "",
    ok_text: str | None = None,
    icon: icons.IconLike = None,
) -> None:
    """弹出只有一个确认按钮的提示对话框并等待关闭。"""
    dialog = BasicDialog(headline, supporting_text, icon, parent)
    dialog.add_action(_text_or_default(ok_text, "confirm"))
    dialog.exec()


def confirm(
    parent: QtWidgets.QWidget | None,
    headline: str,
    supporting_text: str = "",
    confirm_text: str | None = None,
    cancel_text: str | None = None,
    icon: icons.IconLike = None,
) -> bool:
    """弹出确认 / 取消对话框，确认返回 True。"""
    dialog = BasicDialog(headline, supporting_text, icon, parent)
    dialog.add_action(
        _text_or_default(cancel_text, "cancel"),
        QtWidgets.QDialogButtonBox.ButtonRole.RejectRole,
    )
    dialog.add_action(_text_or_default(confirm_text, "confirm"))
    return dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted


def prompt(
    parent: QtWidgets.QWidget | None,
    headline: str,
    label: str = "",
    text: str = "",
    supporting_text: str = "",
    confirm_text: str | None = None,
    cancel_text: str | None = None,
    placeholder: str = "",
) -> str | None:
    """弹出带文本框的输入对话框，确认返回输入内容，取消返回 None。"""
    dialog = BasicDialog(headline, supporting_text, parent=parent)
    field = text_field.OutlinedTextField(label, text, placeholder=placeholder)
    dialog.set_content(field)
    dialog.add_action(
        _text_or_default(cancel_text, "cancel"),
        QtWidgets.QDialogButtonBox.ButtonRole.RejectRole,
    )
    dialog.add_action(_text_or_default(confirm_text, "confirm"))
    field.return_pressed.connect(dialog.accept)
    QtCore.QTimer.singleShot(0, field.setFocus)
    if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        return field.text
    return None


def choose(
    parent: QtWidgets.QWidget | None,
    headline: str,
    options: list[str],
    selected: int = -1,
    supporting_text: str = "",
) -> int | None:
    """弹出单选列表对话框，返回选中下标；取消返回 None。"""
    dialog = ListDialog(
        headline,
        options,
        selected if selected >= 0 else None,
        supporting_text=supporting_text,
        parent=parent,
    )
    if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        return dialog.selected_index
    return None


def choose_many(
    parent: QtWidgets.QWidget | None,
    headline: str,
    options: list[str],
    selected: list[int] | None = None,
    supporting_text: str = "",
) -> list[int] | None:
    """弹出多选列表对话框，返回选中下标列表；取消返回 None。"""
    dialog = ListDialog(
        headline,
        options,
        selected,
        multiple=True,
        supporting_text=supporting_text,
        parent=parent,
    )
    if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
        return dialog.selected_indices
    return None
