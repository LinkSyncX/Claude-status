"""扩展页面：步骤条、折叠面板、头像、骨架屏、反馈与布局类补充组件。

包含空状态、横幅、面包屑、评分、时间线、分割视图、拖放区、颜色文本框、
命令面板与无边框窗口的演示。
"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.components import avatar
from md3.components import breadcrumb
from md3.components import buttons
from md3.components import cards
from md3.components import command_palette
from md3.components import drop_zone
from md3.components import expansion
from md3.components import feedback
from md3.components import pickers
from md3.components import rating
from md3.components import selection
from md3.components import skeleton
from md3.components import snackbar
from md3.components import split_view
from md3.components import stepper
from md3.components import timeline
from md3.components import window
from md3.core import typography
from md3.demo.pages import _common

_TEAM = ["李娜", "Ada Lovelace", "王芳", "Grace Hopper", "张伟", "刘洋", "陈静"]


def _status_label(text: str = "") -> typography.Label:
    return typography.Label(text, "body-medium", "on_surface_variant")


def _build_stepper(page: _common.Page) -> None:
    section = page.section(
        "步骤条",
        "线性流程只允许前进到下一步或回到已完成的步骤；非线性流程可任意"
        "跳转。可选步骤会标注“可选”，出错步骤以 error 色显示。",
    )
    steps = [
        stepper.Step("账户", "邮箱与密码"),
        stepper.Step("资料", "头像与昵称", optional=True),
        stepper.Step("偏好", "语言与主题"),
        stepper.Step("完成", icon="flag"),
    ]
    horizontal = stepper.Stepper(steps)
    section.addWidget(horizontal)
    previous = buttons.TextButton("上一步", icon="arrow_back")
    nxt = buttons.FilledButton("下一步")
    error = buttons.OutlinedButton("标记出错")
    reset = buttons.TextButton("重置")
    status = _status_label("第 1 步 / 4")

    def sync(index: int) -> None:
        status.setText(f"第 {index + 1} 步 / {len(steps)}")
        previous.setEnabled(index > 0)
        nxt.set_text("下一步" if index < len(steps) - 1 else "提交")

    horizontal.step_changed.connect(sync)
    previous.clicked.connect(horizontal.previous_step)

    def advance() -> None:
        if not horizontal.next_step():
            horizontal.set_completed(horizontal.current_step)
            snackbar.show(horizontal, "流程已完成")

    nxt.clicked.connect(advance)
    error.clicked.connect(lambda: horizontal.set_error(horizontal.current_step))
    reset.clicked.connect(horizontal.reset)
    reset.clicked.connect(lambda: sync(0))
    page.row(section, [previous, nxt, error, reset, status], gap=12)
    vertical = stepper.Stepper(
        ["选择套餐", "填写信息", "确认支付"],
        current=1,
        orientation=QtCore.Qt.Orientation.Vertical,
        linear=False,
    )
    vertical.set_completed(0)
    vertical.setFixedWidth(280)
    page.row(section, [vertical], align_top=True)


def _build_expansion(page: _common.Page) -> None:
    section = page.section(
        "折叠面板",
        "点击头部展开或收起内容，箭头随之旋转；Accordion 默认互斥展开。",
    )
    single = expansion.ExpansionPanel(
        "高级设置", "代理、缓存与日志", icon="tune", outlined=True
    )
    form = QtWidgets.QWidget()
    form_layout = QtWidgets.QVBoxLayout(form)
    form_layout.setContentsMargins(0, 0, 0, 0)
    for text in ("使用系统代理", "启用磁盘缓存", "记录详细日志"):
        form_layout.addWidget(selection.Switch(text))
    single.set_content(form)
    section.addWidget(single)
    accordion = expansion.Accordion()
    faq = (
        ("如何切换主题？", "在右上角的应用栏中点击月亮 / 太阳图标。"),
        ("支持从右到左布局吗？", "支持，所有组件都会随布局方向镜像。"),
        ("能替换字体吗？", "可以，通过 typography 令牌覆盖字体族与字号。"),
    )
    for question, answer in faq:
        label = typography.Label(answer, "body-medium", "on_surface_variant")
        label.setWordWrap(True)
        accordion.add_panel(question, icon="help", content=label)
    accordion.expand(0)
    section.addWidget(accordion)


def _sample_pixmap() -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(96, 96)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    gradient = QtGui.QLinearGradient(0, 0, 96, 96)
    gradient.setColorAt(0, QtGui.QColor("#FFB4AB"))
    gradient.setColorAt(1, QtGui.QColor("#6750A4"))
    painter.fillRect(pixmap.rect(), gradient)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(255, 255, 255, 160))
    painter.drawEllipse(QtCore.QRectF(28, 18, 40, 40))
    painter.end()
    return pixmap


def _build_avatars(page: _common.Page) -> None:
    section = page.section(
        "头像",
        "姓名首字母自动配色（由名字哈希决定色相）；支持图片、图标、状态点"
        "与圆角方形；头像组重叠排列并折叠为 +N。",
    )
    page.row(
        section,
        [
            avatar.Avatar("李娜", status=avatar.AvatarStatus.ONLINE),
            avatar.Avatar("Ada Lovelace", status=avatar.AvatarStatus.AWAY),
            avatar.Avatar("王芳", status=avatar.AvatarStatus.BUSY),
            avatar.Avatar("Grace Hopper", status=avatar.AvatarStatus.OFFLINE),
            avatar.Avatar(image=_sample_pixmap(), size=48),
            avatar.Avatar(icon="group", size=48, rounded=True),
            avatar.Avatar("张伟", size=56),
            avatar.Avatar("刘洋", size=24),
        ],
        gap=12,
    )
    page.row(
        section,
        [
            avatar.AvatarGroup(_TEAM, max_visible=4),
            avatar.AvatarGroup(_TEAM[:3], size=40),
        ],
        gap=24,
    )


def _build_skeleton(page: _common.Page) -> None:
    section = page.section(
        "骨架屏", "内容加载时的占位：矩形、圆形与文本行，带流光动画。"
    )
    loading = selection.Switch("加载中", checked=True)
    section.addWidget(loading)
    stack = QtWidgets.QStackedWidget()
    placeholder = QtWidgets.QWidget()
    placeholder_layout = QtWidgets.QVBoxLayout(placeholder)
    placeholder_layout.setContentsMargins(0, 0, 0, 0)
    for _ in range(3):
        placeholder_layout.addWidget(skeleton.skeleton_list_item())
    real = QtWidgets.QWidget()
    real_layout = QtWidgets.QVBoxLayout(real)
    real_layout.setContentsMargins(0, 0, 0, 0)
    for name, line in (
        ("李娜", "季度报表已更新，请查看附件。"),
        ("Ada Lovelace", "The analytical engine weaves algebraic patterns."),
        ("王芳", "明天上午十点的评审会议改到 B 会议室。"),
    ):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(16)
        row.addWidget(avatar.Avatar(name))
        texts = QtWidgets.QVBoxLayout()
        texts.addWidget(typography.Label(name, "body-large", "on_surface"))
        texts.addWidget(_status_label(line))
        row.addLayout(texts, 1)
        holder = QtWidgets.QWidget()
        holder.setLayout(row)
        real_layout.addWidget(holder)
    stack.addWidget(placeholder)
    stack.addWidget(real)
    loading.toggled.connect(
        lambda checked: stack.setCurrentIndex(0 if checked else 1)
    )
    stack.setMaximumWidth(520)
    section.addWidget(stack)
    page.row(
        section,
        [
            skeleton.Skeleton(160, 120, radius=12),
            skeleton.Skeleton(72, shape=skeleton.SkeletonShape.CIRCLE),
            skeleton.Skeleton(220, 14, shape=skeleton.SkeletonShape.TEXT),
        ],
        gap=16,
    )


def _build_feedback(page: _common.Page) -> None:
    section = page.section(
        "空状态与横幅",
        "EmptyState 用图标 / 插图、标题、说明与操作填充空白区域；Banner 在"
        "内容顶部展示需要处理的信息，窄宽度时操作换行。",
    )
    banner = feedback.Banner(
        "你的存储空间即将用完，升级以获得更多空间。", icon="cloud"
    )
    banner.add_action("升级")
    banner.add_action("稍后")
    section.addWidget(banner)
    reshow = buttons.TextButton("重新显示横幅", icon="refresh")
    reshow.clicked.connect(banner.show_animated)
    empty = feedback.EmptyState(
        "还没有项目",
        "创建第一个项目，或从模板开始。",
        icon="folder_open",
    )
    empty.add_action("新建项目").clicked.connect(
        lambda: snackbar.show(empty, "已创建项目")
    )
    empty.add_action("浏览模板", primary=False)
    empty.setMinimumHeight(300)
    card = cards.OutlinedCard()
    card.content_layout.addWidget(empty)
    section.addWidget(card)
    page.row(section, [reshow])


def _build_small_widgets(page: _common.Page) -> None:
    section = page.section(
        "面包屑、评分与时间线",
        "面包屑超出上限时折叠为省略号菜单；评分支持半星、键盘与只读；"
        "时间线按内容高度自适应。",
    )
    crumbs = breadcrumb.Breadcrumb(
        [
            breadcrumb.BreadcrumbItem("首页", icon="home"),
            "设计系统",
            "组件",
            "导航",
            "面包屑",
        ]
    )
    status = _status_label("")
    crumbs.item_clicked.connect(
        lambda index: status.setText(f"跳转到：{crumbs.items[index].text}")
    )
    page.row(section, [crumbs, status], gap=16)
    stars = rating.Rating(3.5, step=0.5)
    score = _status_label("3.5 / 5")
    stars.value_changed.connect(lambda value: score.setText(f"{value:g} / 5"))
    hearts = rating.Rating(4, icon="favorite", read_only=True, size=24)
    page.row(section, [stars, score, hearts, _status_label("只读")], gap=16)
    history = timeline.Timeline(
        [
            timeline.TimelineItem("订单已创建", "等待商家确认", "09:12"),
            timeline.TimelineItem(
                "商家已接单", "预计 30 分钟内送达", "09:15", icon="storefront"
            ),
            timeline.TimelineItem(
                "骑手已取货", "距离你 2.3 km", "09:41", icon="two_wheeler"
            ),
            timeline.TimelineItem("已送达", active=False, color="tertiary"),
        ]
    )
    history.setMaximumWidth(480)
    section.addWidget(history)


def _build_split_and_drop(page: _common.Page) -> None:
    section = page.section(
        "分割视图、拖放区与颜色文本框",
        "分割视图的把手在悬停 / 拖动时显示主色抓手；拖放区按扩展名过滤，"
        "点击可浏览文件；颜色文本框可键入十六进制或打开取色器。",
    )
    split = split_view.SplitView()
    left = typography.Label("左侧面板", "title-medium", "on_surface")
    left.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    right = typography.Label("右侧面板", "title-medium", "on_surface")
    right.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
    split.addWidget(left)
    split.addWidget(right)
    split.setSizes([200, 400])
    split.setFixedHeight(140)
    section.addWidget(split)
    zone = drop_zone.DropZone(extensions=[".png", ".jpg", ".svg"])
    files = _status_label("尚未选择文件")
    zone.files_dropped.connect(
        lambda paths: files.setText("已选择：" + "、".join(paths))
    )
    zone.rejected.connect(
        lambda paths: snackbar.show(zone, f"已忽略 {len(paths)} 个不支持的文件")
    )
    color_field = pickers.ColorField("主题色", "#6750A4")
    swatch = QtWidgets.QFrame()
    swatch.setFixedSize(56, 56)

    def paint_swatch(color: QtGui.QColor) -> None:
        swatch.setStyleSheet(
            f"background: {color.name()}; border-radius: 12px;"
        )

    paint_swatch(color_field.selected_color)
    color_field.color_changed.connect(paint_swatch)
    column = QtWidgets.QVBoxLayout()
    column.setSpacing(16)
    column.addWidget(color_field)
    color_row = QtWidgets.QHBoxLayout()
    color_row.addWidget(swatch)
    color_row.addStretch()
    column.addLayout(color_row)
    column.addStretch()
    row = QtWidgets.QHBoxLayout()
    row.setSpacing(24)
    row.addWidget(zone, 2)
    row.addLayout(column, 1)
    section.addLayout(row)
    section.addWidget(files)


def _build_palette_and_window(page: _common.Page) -> None:
    section = page.section(
        "命令面板与无边框窗口",
        "命令面板以模糊匹配检索命令并记住最近使用；MaterialWindow 用自绘"
        "标题栏替代系统边框，支持拖动、双击最大化与边缘缩放。",
    )
    commands = [
        command_palette.Command(
            "切换深色模式",
            md3.toggle_dark,
            icon="dark_mode",
            category="外观",
            shortcut="Ctrl+D",
            keywords=("theme", "dark"),
        ),
        command_palette.Command(
            "新建项目", lambda: snackbar.show(page, "已新建项目"), icon="add"
        ),
        command_palette.Command(
            "打开设置", lambda: snackbar.show(page, "设置"), icon="settings"
        ),
        command_palette.Command(
            "查看文档",
            lambda: snackbar.show(page, "文档"),
            icon="menu_book",
            category="帮助",
        ),
        command_palette.Command(
            "导出（不可用）", icon="download", enabled=False
        ),
    ]
    palette = command_palette.CommandPalette(commands, parent=page)
    palette.install_shortcut(page, "Ctrl+K")
    open_palette = buttons.FilledTonalButton(
        "打开命令面板", icon="keyboard_command_key"
    )
    open_palette.clicked.connect(palette.open_palette)
    open_window = buttons.OutlinedButton("打开无边框窗口", icon="open_in_new")

    def show_window() -> None:
        win = window.MaterialWindow("Material 窗口", icon="widgets")
        body = QtWidgets.QVBoxLayout()
        body.setContentsMargins(24, 24, 24, 24)
        body.addWidget(
            typography.Label(
                "这是一个无边框窗口。", "title-medium", "on_surface"
            )
        )
        body.addWidget(
            _status_label("拖动标题栏移动，双击标题栏最大化，边缘可缩放。")
        )
        body.addStretch()
        content = QtWidgets.QWidget()
        content.setLayout(body)
        win.set_content(content)
        win.resize(520, 360)
        win.show()
        page.frameless_window = win  # type: ignore[attr-defined]  # 持有引用

    open_window.clicked.connect(show_window)
    page.row(
        section, [open_palette, open_window, _status_label("快捷键 Ctrl+K")]
    )


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "扩展",
        "在 M3 规范组件之外，桌面应用常用的补充组件：流程、折叠、身份、"
        "占位、反馈、导航辅助、布局与窗口。",
    )
    _build_stepper(page)
    _build_expansion(page)
    _build_avatars(page)
    _build_skeleton(page)
    _build_feedback(page)
    _build_small_widgets(page)
    _build_split_and_drop(page)
    _build_palette_and_window(page)
    page.finish()
    return page
