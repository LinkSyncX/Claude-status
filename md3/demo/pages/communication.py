"""Communication 页面：徽标、进度指示器、Snackbar、提示。"""

from __future__ import annotations

import random

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import badges
from md3.components import buttons
from md3.components import progress
from md3.components import selection
from md3.components import slider
from md3.components import snackbar
from md3.components import tooltips
from md3.core import typography
from md3.demo.pages import _common
from md3.tokens import spacing


class TaskDemo(QtWidgets.QWidget):
    """用同一进度驱动各类确定态指示器，并可模拟一次下载任务。"""

    STEP_MS = 400

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._indicators: list[progress.ProgressIndicator] = [
            progress.LinearProgressIndicator(0.0),
            progress.LinearWavyProgressIndicator(0.0),
        ]
        self._rings: list[progress.ProgressIndicator] = [
            progress.CircularProgressIndicator(0.0),
            progress.CircularWavyProgressIndicator(0.0),
            progress.LoadingIndicator(0.0),
        ]
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(self.STEP_MS)
        self._timer.timeout.connect(self._advance)
        self._progress = 0.0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(spacing.SPACE_3))
        controls = QtWidgets.QHBoxLayout()
        controls.setSpacing(round(spacing.SPACE_2))
        self._slider = slider.Slider(0, 100, 0)
        self._slider.value_changed.connect(self._on_slider)
        controls.addWidget(self._slider, 1)
        self._label = typography.Label(
            "0%", "label-large", "on_surface_variant"
        )
        self._label.setFixedWidth(44)
        controls.addWidget(self._label)
        layout.addLayout(controls)

        actions = QtWidgets.QHBoxLayout()
        actions.setSpacing(round(spacing.SPACE_2))
        self._start = buttons.FilledTonalButton("模拟下载", icon="download")
        self._start.clicked.connect(self.start_task)
        indeterminate = buttons.OutlinedButton("不确定态", icon="hourglass_top")
        indeterminate.clicked.connect(self.set_indeterminate)
        reset = buttons.TextButton("重置", icon="restart_alt")
        reset.clicked.connect(self.reset)
        for button in (self._start, indeterminate, reset):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        for indicator in self._indicators:
            layout.addWidget(indicator)
        rings = QtWidgets.QHBoxLayout()
        rings.setSpacing(round(spacing.SPACE_4))
        for ring in self._rings:
            rings.addWidget(ring, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)
        rings.addStretch()
        layout.addLayout(rings)

    @property
    def indicators(self) -> list[progress.ProgressIndicator]:
        """受控的全部指示器。"""
        return [*self._indicators, *self._rings]

    def set_progress(self, value: float) -> None:
        """设置所有指示器的进度（0–1）。"""
        self._progress = max(0.0, min(1.0, value))
        for indicator in self.indicators:
            indicator.set_value(self._progress)
        self._label.setText(f"{self._progress * 100:.0f}%")
        if abs(self._slider.value - self._progress * 100) > 0.5:
            self._slider.set_value(self._progress * 100)

    def set_indeterminate(self) -> None:
        """全部切换为不确定态。"""
        self._timer.stop()
        for indicator in self.indicators:
            indicator.set_indeterminate(True)
        self._label.setText("…")

    def start_task(self) -> None:
        """从头模拟一次进度不均匀的下载。"""
        self.set_progress(0.0)
        self._start.setEnabled(False)
        self._timer.start()

    def reset(self) -> None:
        """停止模拟并归零。"""
        self._timer.stop()
        self._start.setEnabled(True)
        self.set_progress(0.0)

    def _advance(self) -> None:
        step = random.uniform(0.04, 0.18)  # noqa: S311 - 仅用于演示
        self.set_progress(self._progress + step)
        if self._progress >= 1.0:
            self._timer.stop()
            self._start.setEnabled(True)
            snackbar.show(self, "下载完成", action="打开")

    def _on_slider(self, value: float) -> None:
        if self._timer.isActive():
            return
        self.set_progress(value / 100.0)


class BadgeCounterDemo(QtWidgets.QWidget):
    """挂在图标按钮上的徽标：计数变化弹跳，归零时缩放消失。"""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._count = 3
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(round(spacing.SPACE_2))
        self._target = buttons.IconButton(
            "notifications",
            variant=buttons.IconButtonVariant.TONAL,
            tooltip="通知",
        )
        self._badge = badges.attach(self._target, self._count)
        layout.addWidget(self._target)
        layout.addSpacing(round(spacing.SPACE_4))
        for text, icon, delta in (("+1", "add", 1), ("-1", "remove", -1)):
            button = buttons.OutlinedButton(text, icon=icon)
            button.clicked.connect(lambda _=None, d=delta: self.adjust(d))
            layout.addWidget(button)
        clear = buttons.TextButton("清零", icon="clear_all")
        clear.clicked.connect(lambda: self.set_count(0))
        layout.addWidget(clear)
        layout.addStretch()

    @property
    def badge(self) -> badges.AttachedBadge:
        """演示用的徽标。"""
        return self._badge

    def adjust(self, delta: int) -> None:
        """增减计数。"""
        self.set_count(self._count + delta)

    def set_count(self, count: int) -> None:
        """设置计数；0 时隐藏徽标。"""
        self._count = max(0, count)
        if self._count == 0:
            self._badge.hide_animated()
            return
        self._badge.set_count(self._count)
        if not self._badge.isVisible():
            self._badge.show_animated()


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page("通信", "徽标、进度指示器、Snackbar 与提示。")

    badge_section = page.section(
        "徽标", "独立徽标，以及用 badges.attach 挂到任意控件右上角的徽标。"
    )
    mail = buttons.IconButton("mail", tooltip="邮件")
    badges.attach(mail)
    chat = buttons.IconButton("chat", tooltip="消息")
    badges.attach(chat, 128)
    inbox = buttons.IconButton("inbox", tooltip="收件箱")
    badges.attach(inbox, 5000)
    fab = buttons.FloatingActionButton(icon="shopping_cart")
    badges.attach(fab, text="NEW")
    page.row(
        badge_section,
        [
            badges.Badge(),
            badges.Badge(3),
            badges.Badge(1200),
            badges.Badge(text="NEW"),
            mail,
            chat,
            inbox,
            fab,
        ],
        gap=24,
    )
    badge_section.addWidget(BadgeCounterDemo())

    linear = page.section(
        "线性进度指示器",
        "确定态数值以 M3 进度弹簧平滑过渡；不确定态为两条相继扫过的活动段。",
    )
    linear.addWidget(progress.LinearProgressIndicator(0.35))
    linear.addWidget(progress.LinearProgressIndicator(None))

    wavy = page.section(
        "波浪进度指示器",
        "M3 Expressive：活动段为流动的正弦波，进度低于 10% 或高于 95% 时"
        "振幅平滑归零；可自定义粗细与振幅。",
    )
    wavy.addWidget(progress.LinearWavyProgressIndicator(0.35))
    wavy.addWidget(progress.LinearWavyProgressIndicator(None))
    wavy.addWidget(progress.LinearWavyProgressIndicator(0.6, thickness=8.0))

    circular = page.section("环形进度指示器")
    page.row(
        circular,
        [
            progress.CircularProgressIndicator(0.3),
            progress.CircularProgressIndicator(0.75),
            progress.CircularProgressIndicator(None),
            progress.CircularProgressIndicator(0.6, size=24, show_track=False),
            progress.CircularWavyProgressIndicator(0.3),
            progress.CircularWavyProgressIndicator(0.75),
            progress.CircularWavyProgressIndicator(None),
            progress.CircularWavyProgressIndicator(
                0.5, size=64, thickness=6.0, amplitude=2.4
            ),
        ],
        gap=16,
    )

    loading = page.section(
        "加载指示器",
        "M3 Expressive：在七个 Material 形状之间带回弹地变形与旋转；"
        "确定态按进度从圆形变为 soft burst。",
    )
    page.row(
        loading,
        [
            progress.LoadingIndicator(),
            progress.ContainedLoadingIndicator(),
            progress.LoadingIndicator(0.5),
            progress.LoadingIndicator(size=72),
        ],
        gap=16,
    )

    task = page.section(
        "同一进度驱动多种指示器",
        "拖动滑块或模拟一次下载，观察数值过渡与振幅变化。",
    )
    task.addWidget(TaskDemo())

    snack = page.section(
        "Snackbar",
        "指针悬停时暂停自动消失的计时；向下或向侧面拖动可以把它划走。",
    )
    reason_label = typography.Label("", "body-medium", "on_surface_variant")

    def on_dismiss(reason: snackbar.DismissReason) -> None:
        names = {
            snackbar.DismissReason.TIMEOUT: "超时",
            snackbar.DismissReason.ACTION: "点击操作",
            snackbar.DismissReason.CLOSE: "点击关闭",
            snackbar.DismissReason.SWIPE: "划走",
            snackbar.DismissReason.PROGRAMMATIC: "程序关闭",
        }
        reason_label.setText(f"上一条关闭原因：{names[reason]}")

    short = buttons.FilledTonalButton("显示 Snackbar")
    short.clicked.connect(
        lambda: snackbar.show(
            short, "文件已删除", action="撤销", on_dismiss=on_dismiss
        )
    )
    long_one = buttons.FilledTonalButton("两行 + 关闭按钮")
    long_one.clicked.connect(
        lambda: snackbar.show(
            long_one,
            "这是一条较长的提示信息，会自动换行显示到第二行，并带有关闭按钮。",
            closable=True,
            duration_ms=snackbar.LONG_DURATION_MS,
            on_dismiss=on_dismiss,
        )
    )
    new_line = buttons.FilledTonalButton("长操作另起一行")
    new_line.clicked.connect(
        lambda: snackbar.show(
            new_line,
            "已把 12 封邮件归档到「工作」文件夹，可以在归档列表中找到它们。",
            action="查看全部已归档邮件",
            closable=True,
            duration_ms=snackbar.LONG_DURATION_MS,
            action_on_new_line=True,
            on_dismiss=on_dismiss,
        )
    )
    align_switch = selection.Switch("左对齐")

    def on_align(checked: bool) -> None:
        host = snackbar.SnackbarHost.for_widget(page)
        host.set_alignment(
            snackbar.SnackbarAlignment.START
            if checked
            else snackbar.SnackbarAlignment.CENTER
        )

    align_switch.toggled.connect(on_align)
    page.row(snack, [short, long_one, new_line, align_switch])
    snack.addWidget(reason_label)

    tips = page.section(
        "提示",
        "悬停在按钮上查看；富提示可以把指针移入其中阅读，带操作的富提示"
        "点击外部或按 Esc 关闭。",
    )
    placements = []
    for icon, placement, name in (
        ("north", tooltips.Placement.TOP, "上方"),
        ("south", tooltips.Placement.BOTTOM, "下方"),
        ("west", tooltips.Placement.START, "左侧"),
        ("east", tooltips.Placement.END, "右侧"),
    ):
        button = buttons.IconButton(icon)
        tooltips.install_plain(button, f"显示在{name}的提示", placement)
        placements.append(button)
    plain = buttons.OutlinedButton("纯文字提示", icon="info")
    tooltips.install_plain(plain, "保存当前文档")
    rich = buttons.OutlinedButton("富提示（可停留）", icon="help")
    tooltips.install_rich(
        rich,
        "富提示可以包含较长的说明文字，帮助用户理解此功能；把指针移入提示"
        "本身时它会保持显示。",
        subhead="标题",
        placement=tooltips.Placement.BOTTOM,
    )
    persistent = buttons.OutlinedButton("带操作的富提示", icon="help")
    tooltips.install_rich(
        persistent,
        "带操作的富提示会一直停留，直到点击操作、点击别处或按下 Esc。",
        subhead="持久提示",
        actions=["了解更多"],
    )
    page.row(tips, [*placements, plain, rich, persistent])
    page.finish()
    return page
