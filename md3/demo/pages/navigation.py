"""Navigation 页面：应用栏、标签页、导航栏、导航轨、抽屉。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.components import app_bars
from md3.components import buttons
from md3.components import navigation
from md3.components import transitions
from md3.core import typography
from md3.demo.pages import _common

DESTINATIONS = [
    navigation.Destination("首页", "home"),
    navigation.Destination("收藏", "favorite", badge=3),
    navigation.Destination("消息", "chat", badge=""),
    navigation.Destination("设置", "settings"),
]


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "导航", "顶部 / 底部应用栏、标签页、导航栏、导航轨与导航抽屉。"
    )

    bars = page.section("顶部应用栏")
    for variant, title in (
        (app_bars.TopAppBarVariant.SMALL, "小型"),
        (app_bars.TopAppBarVariant.CENTER_ALIGNED, "居中"),
        (app_bars.TopAppBarVariant.MEDIUM, "中型"),
        (app_bars.TopAppBarVariant.LARGE, "大型"),
    ):
        bar = app_bars.TopAppBar(
            f"{title}应用栏",
            variant,
            actions=["attach_file", "calendar_today", "more_vert"],
        )
        bars.addWidget(bar)

    transition_section = page.section(
        "页面过渡",
        "AnimatedStackedWidget 按 M3 过渡模式切换页面：标签页之间用共享轴，"
        "顶层目的地之间用 fade-through。",
    )
    transition_section.addWidget(_transition_demo())

    collapsing = page.section(
        "折叠应用栏与溢出菜单",
        "大型应用栏接到下方的滚动区域：滚轮先把展开区域折叠到 64dp，"
        "内容才开始滚动；超过 3 个的操作进入溢出菜单。",
    )
    collapsing.addWidget(_collapsing_demo())

    tabs = page.section("标签页")
    tabs.addWidget(
        navigation.Tabs(
            [
                navigation.Tab("视频", "videocam"),
                navigation.Tab("照片", "photo", badge=12),
                navigation.Tab("音频", "audiotrack"),
            ],
            selected_index=1,
        )
    )
    tabs.addWidget(
        navigation.Tabs(
            ["全部", "未读", "已归档", "垃圾邮件"],
            variant=navigation.TabsVariant.SECONDARY,
        )
    )
    scrollable = navigation.Tabs(
        [
            "推荐",
            "关注",
            "科技",
            "设计",
            "财经",
            "体育",
            "娱乐",
            "游戏",
            "汽车",
            "旅行",
            "美食",
            "教育",
        ],
        scrollable=True,
    )
    scrollable.setMaximumWidth(640)
    tabs.addWidget(scrollable)
    tabs.addWidget(
        typography.Label(
            "可滚动标签页：滚轮、拖拽或两侧箭头滚动，选中项自动滚入视野。",
            "body-medium",
            "on_surface_variant",
        )
    )

    bottom = page.section("导航栏与底部应用栏")
    bottom.addWidget(navigation.NavigationBar(DESTINATIONS, selected_index=1))
    bottom.addWidget(
        app_bars.BottomAppBar(
            ["check_box", "brush", "mic", "image"],
            fab=buttons.FloatingActionButton("add"),
        )
    )

    side = page.section("导航轨与导航抽屉")
    row = QtWidgets.QHBoxLayout()
    row.setSpacing(24)
    rail = navigation.NavigationRail(
        DESTINATIONS,
        selected_index=0,
        header=buttons.FloatingActionButton("edit"),
        menu_button=True,
        expandable=True,
    )
    rail.setFixedHeight(420)
    row.addWidget(rail)
    drawer = navigation.NavigationDrawer(
        [
            navigation.DrawerItem.section("邮件"),
            navigation.DrawerItem("收件箱", "inbox", badge="24"),
            navigation.DrawerItem("已发送", "send"),
            navigation.DrawerItem("草稿", "drafts", badge="2"),
            navigation.DrawerItem.separator(),
            navigation.DrawerItem.section("标签"),
            navigation.DrawerItem("工作", "label"),
            navigation.DrawerItem("个人", "label"),
        ],
        selected_index=1,
    )
    drawer.setFixedHeight(420)
    row.addWidget(drawer)
    modal_button = buttons.OutlinedButton("打开模态抽屉", icon="menu")

    def open_modal() -> None:
        modal = navigation.ModalNavigationDrawer(
            page.window(), drawer.content.items, 1
        )
        modal.open_panel()

    modal_button.clicked.connect(open_modal)
    column = QtWidgets.QVBoxLayout()
    column.addWidget(modal_button)
    column.addWidget(
        typography.Label(
            "模态抽屉从窗口左侧滑入，点击遮罩关闭；"
            "左侧导航轨的菜单按钮可在折叠与展开之间切换。",
            "body-medium",
            "on_surface_variant",
        )
    )
    column.addStretch()
    row.addLayout(column)
    row.addStretch()
    side.addLayout(row)
    page.finish()
    return page


_TRANSITIONS = (
    ("共享轴 X", transitions.Transition.SHARED_AXIS_X),
    ("共享轴 Y", transitions.Transition.SHARED_AXIS_Y),
    ("共享轴 Z", transitions.Transition.SHARED_AXIS_Z),
    ("Fade through", transitions.Transition.FADE_THROUGH),
    ("Fade", transitions.Transition.FADE),
)


def _transition_demo() -> QtWidgets.QWidget:
    frame = QtWidgets.QWidget()
    frame.setMaximumWidth(560)
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    chooser = buttons.SegmentedButton(
        [buttons.Segment(label) for label, _ in _TRANSITIONS], selected=[0]
    )
    layout.addWidget(chooser)
    tabs = navigation.Tabs(["概览", "详情", "评论", "设置"])
    layout.addWidget(tabs)
    stack = transitions.AnimatedStackedWidget(
        transitions.Transition.SHARED_AXIS_X
    )
    stack.setFixedHeight(160)
    colors = (
        "primary_container",
        "secondary_container",
        "tertiary_container",
        "surface_container_highest",
    )
    for index, (title, color) in enumerate(zip(tabs.tabs, colors, strict=True)):
        page = _ColorPage(f"第 {index + 1} 页 · {title.label}", color)
        stack.addWidget(page)
    layout.addWidget(stack)
    tabs.selection_changed.connect(stack.set_current_index)
    chooser.selection_changed.connect(
        lambda indices: (
            stack.set_transition(_TRANSITIONS[indices[0]][1])
            if indices
            else None
        )
    )
    return frame


class _ColorPage(QtWidgets.QWidget):
    """过渡演示用的纯色页面。"""

    def __init__(self, text: str, color_role: str) -> None:
        super().__init__()
        self._color_role = color_role
        layout = QtWidgets.QVBoxLayout(self)
        label = typography.Label(text, "title-medium", "on_surface")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(md3.current_theme().color(self._color_role))
        painter.drawRoundedRect(QtCore.QRectF(self.rect()), 16, 16)
        painter.end()


def _collapsing_demo() -> QtWidgets.QWidget:
    frame = QtWidgets.QFrame()
    frame.setFixedHeight(360)
    frame.setMaximumWidth(560)
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    bar = app_bars.TopAppBar(
        "收件箱",
        app_bars.TopAppBarVariant.LARGE,
        navigation_icon="menu",
        actions=[
            app_bars.AppBarAction("search", "搜索"),
            app_bars.AppBarAction("filter_list", "筛选"),
            app_bars.AppBarAction("refresh", "刷新"),
            app_bars.AppBarAction("archive", "归档全部"),
            app_bars.AppBarAction("mark_email_read", "全部标为已读"),
            app_bars.AppBarAction("settings", "设置"),
        ],
    )
    layout.addWidget(bar)
    scroll = QtWidgets.QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    body = QtWidgets.QWidget()
    body_layout = QtWidgets.QVBoxLayout(body)
    body_layout.setContentsMargins(16, 8, 16, 8)
    for index in range(1, 25):
        body_layout.addWidget(
            typography.Label(
                f"第 {index} 封邮件 —— 滚动查看应用栏如何折叠", "body-large"
            )
        )
    scroll.setWidget(body)
    layout.addWidget(scroll, 1)
    bar.attach_scroll_area(scroll)
    status = typography.Label("", "body-small", "on_surface_variant")
    bar.action_triggered.connect(
        lambda index: status.setText(
            f"触发操作：{bar.action_items[index].text}"
        )
    )
    layout.addWidget(status)
    return frame
