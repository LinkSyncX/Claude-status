"""Containment 页面：卡片、分隔线、对话框、列表、面板。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

import md3
from md3.components import buttons
from md3.components import cards
from md3.components import carousel
from md3.components import dialogs
from md3.components import dividers
from md3.components import lists
from md3.components import selection
from md3.components import sheets
from md3.components import snackbar
from md3.core import typography
from md3.demo.pages import _common


def _card(variant: cards.CardVariant) -> cards.Card:
    card = cards.Card(variant, clickable=True)
    card.add_widget(
        typography.Label(f"{variant.value.title()} card", "title-medium")
    )
    body = typography.Label(
        "卡片内容区域可以放置任意控件，包括文字、图片与按钮。",
        "body-medium",
        "on_surface_variant",
    )
    body.setWordWrap(True)
    card.add_widget(body)
    row = QtWidgets.QHBoxLayout()
    row.addStretch()
    row.addWidget(buttons.TextButton("取消"))
    row.addWidget(buttons.FilledButton("确定"))
    card.content_layout.addLayout(row)
    card.setFixedWidth(300)
    card.clicked.connect(
        lambda: snackbar.show(card, f"点击了 {variant.value} card")
    )
    return card


_CAROUSEL_COLORS = (
    "#6750A4",
    "#0061A4",
    "#006D3A",
    "#B3261E",
    "#7D5700",
    "#006A6A",
    "#8E4585",
    "#4A6363",
)
_CAROUSEL_TITLES = (
    "山间晨雾",
    "城市夜景",
    "森林小径",
    "沙漠日落",
    "海岸线",
    "极光",
    "花田",
    "雪山",
)


def _picture(index: int) -> QtGui.QPixmap:
    """生成一张渐变占位图。"""
    pixmap = QtGui.QPixmap(480, 320)
    gradient = QtGui.QLinearGradient(0, 0, 480, 320)
    start = QtGui.QColor(_CAROUSEL_COLORS[index % len(_CAROUSEL_COLORS)])
    end = QtGui.QColor(_CAROUSEL_COLORS[(index + 3) % len(_CAROUSEL_COLORS)])
    gradient.setColorAt(0.0, start)
    gradient.setColorAt(1.0, end.lighter(160))
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.fillRect(pixmap.rect(), gradient)
    painter.setPen(QtCore.Qt.PenStyle.NoPen)
    painter.setBrush(QtGui.QColor(255, 255, 255, 80))
    painter.drawEllipse(QtCore.QPointF(360, 100), 90, 90)
    painter.setBrush(QtGui.QColor(0, 0, 0, 40))
    painter.drawEllipse(QtCore.QPointF(120, 260), 140, 60)
    painter.end()
    return pixmap


def _media_card() -> cards.Card:
    card = cards.ElevatedCard()
    card.set_media(_picture(0))
    card.add_widget(typography.Label("山间晨雾", "title-medium"))
    body = typography.Label(
        "媒体区按 16:9 比例随卡片宽度变化，图片按比例裁切填满。",
        "body-medium",
        "on_surface_variant",
    )
    body.setWordWrap(True)
    card.add_widget(body)
    card.setFixedWidth(280)
    return card


def _expandable_card() -> cards.Card:
    card = cards.FilledCard()
    card.add_widget(typography.Label("行程摘要", "title-medium"))
    summary = typography.Label(
        "3 天 2 晚 · 2 位成人 · 含早餐", "body-medium", "on_surface_variant"
    )
    card.add_widget(summary)
    for line in ("第 1 天：抵达并入住", "第 2 天：徒步与温泉", "第 3 天：返程"):
        card.expanded_layout.addWidget(
            typography.Label(line, "body-medium", "on_surface_variant")
        )
    card.setFixedWidth(280)
    return card


class _DropZone(QtWidgets.QFrame):
    """接收可拖动卡片的放置区。"""

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setFixedSize(160, 120)
        layout = QtWidgets.QVBoxLayout(self)
        self._label = typography.Label(
            "拖到这里", "body-medium", "on_surface_variant"
        )
        self._label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)
        self._active = False

    def dragEnterEvent(self, event: QtGui.QDragEnterEvent) -> None:
        if event.mimeData().hasFormat(cards.card.DEFAULT_DRAG_MIME_TYPE):
            self._active = True
            self.update()
            event.acceptProposedAction()

    def dragLeaveEvent(self, event: QtGui.QDragLeaveEvent) -> None:
        del event
        self._active = False
        self.update()

    def dropEvent(self, event: QtGui.QDropEvent) -> None:
        payload = bytes(
            event.mimeData().data(cards.card.DEFAULT_DRAG_MIME_TYPE)
        ).decode("utf-8")
        self._label.setText(f"收到：{payload}")
        self._active = False
        self.update()
        event.acceptProposedAction()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        del event
        theme = md3.current_theme()
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        pen = QtGui.QPen(
            theme.color("primary" if self._active else "outline"), 1.5
        )
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(
            theme.color("primary_container")
            if self._active
            else QtCore.Qt.BrushStyle.NoBrush
        )
        painter.drawRoundedRect(
            QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12
        )
        painter.end()


def _drag_demo() -> QtWidgets.QWidget:
    holder = QtWidgets.QWidget()
    row = QtWidgets.QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(16)
    card = cards.OutlinedCard()
    card.add_widget(typography.Label("可拖动卡片", "title-medium"))
    hint = typography.Label(
        "按住并拖动，卡片会以拖拽态跟随指针。",
        "body-medium",
        "on_surface_variant",
    )
    hint.setWordWrap(True)
    card.add_widget(hint)
    card.set_draggable(True, payload="可拖动卡片")
    card.setFixedWidth(200)
    row.addWidget(card, 0, QtCore.Qt.AlignmentFlag.AlignTop)
    row.addWidget(_DropZone(), 0, QtCore.Qt.AlignmentFlag.AlignTop)
    return holder


def _build_carousel_section(page: _common.Page) -> None:
    """轮播分节：可切换布局，点击项目提示。"""
    section = page.section(
        "轮播",
        "拖动、滚轮或方向键浏览；项目沿关键线从大到小收缩，点击小项会把它"
        "滚动到主位置。",
    )
    items = [
        carousel.CarouselItem(_picture(i), title, "点击查看详情")
        for i, title in enumerate(_CAROUSEL_TITLES)
    ]
    widget = carousel.Carousel(items, item_height=196)
    kinds = [
        ("Multi-browse", carousel.CarouselLayout.MULTI_BROWSE),
        ("Hero", carousel.CarouselLayout.HERO),
        ("Uncontained", carousel.CarouselLayout.UNCONTAINED),
    ]
    switcher = buttons.SegmentedButton(
        [buttons.Segment(label) for label, _ in kinds], selected=[0]
    )
    switcher.selection_changed.connect(
        lambda indices: (
            widget.set_layout(kinds[indices[0]][1]) if indices else None
        )
    )
    result = typography.Label("", "body-medium", "on_surface_variant")
    widget.item_clicked.connect(
        lambda index: result.setText(f"点击了「{_CAROUSEL_TITLES[index]}」")
    )
    page.row(section, [switcher, result], gap=16)
    section.addWidget(widget)
    full = carousel.Carousel(
        items[:4], carousel.CarouselLayout.FULL_SCREEN, item_height=220
    )
    full.setFixedHeight(220)
    section.addWidget(
        typography.Label(
            "全屏布局（竖向分页）：", "body-medium", "on_surface_variant"
        )
    )
    section.addWidget(full)


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "容器", "卡片、轮播、分隔线、对话框、列表、底部面板与侧面板。"
    )

    card_section = page.section("卡片")
    page.row(
        card_section,
        [_card(v) for v in cards.CardVariant],
        gap=16,
        align_top=True,
    )
    rich_section = page.section(
        "媒体卡片、可展开卡片与可拖动卡片",
        "媒体区随卡片圆角裁切；点击箭头展开更多内容；按住第三张卡片拖动，"
        "放到右侧的放置区。",
    )
    page.row(
        rich_section,
        [_media_card(), _expandable_card(), _drag_demo()],
        gap=16,
        align_top=True,
    )

    _build_carousel_section(page)

    divider_section = page.section("分隔线")
    divider_section.addWidget(dividers.Divider())
    divider_section.addWidget(dividers.Divider.inset())
    divider_section.addWidget(dividers.Divider.middle_inset())

    _build_list_sections(page)
    _build_dialog_section(page)
    page.finish()
    return page


def _build_list_sections(page: _common.Page) -> None:
    list_section = page.section("列表")
    view = lists.ListView(lists.SelectionMode.SINGLE, dividers=True)
    view.add("单行列表项", leading_icon="inbox", trailing_text="12")
    view.add(
        "两行列表项",
        supporting_text="辅助文字描述",
        leading_avatar="A",
        trailing_icon="chevron_right",
    )
    view.add(
        "三行列表项",
        supporting_text="这是一段很长的辅助文字，会自动换行到第二行以展示三行列表项的排版效果。",
        leading_icon="image",
        lines=3,
    )
    view.add(
        "带开关",
        supporting_text="后置控件",
        trailing_widget=selection.Switch(checked=True),
    )
    view.add("带复选框", leading_widget=selection.Checkbox(checked=True))
    view.setFixedSize(420, 330)
    list_section.addWidget(view)

    swipe_section = page.section(
        "滑动操作与拖动排序",
        "向右滑显露归档 / 标记，向左滑过 40% 行宽删除；按住上下拖动可排序。",
    )
    swipe_view = lists.ListView(dividers=True, reorderable=True)
    archive = lists.SwipeAction("archive", "归档", color="primary_container")
    flag = lists.SwipeAction("flag", "标记", color="tertiary_container")
    delete = lists.SwipeAction("delete", color="error", dismiss=True)
    for subject, sender in (
        ("周会纪要", "产品组"),
        ("发票已开具", "财务"),
        ("设计评审邀请", "设计组"),
        ("版本发布通知", "工程"),
    ):
        entry = swipe_view.add(
            subject, supporting_text=sender, leading_avatar=sender[0]
        )
        entry.set_swipe_actions(leading=[archive, flag], trailing=[delete])
    status = typography.Label("", "body-small", "on_surface_variant")
    swipe_view.swipe_action_triggered.connect(
        lambda index, action: status.setText(
            f"第 {index + 1} 项：{action.text or '删除'}"
        )
    )
    swipe_view.items_reordered.connect(
        lambda source, target: status.setText(
            f"已把第 {source + 1} 项移到第 {target + 1} 位"
        )
    )
    swipe_view.setFixedSize(420, 300)
    swipe_section.addWidget(swipe_view)
    swipe_section.addWidget(status)


def _build_dialog_section(page: _common.Page) -> None:
    dialog_section = page.section(
        "对话框与面板",
        "点击按钮打开。底部面板有三个停靠点，拖动把手或按方向键在停靠点"
        "之间切换、快速下拉关闭；detached 侧面板与窗口边缘保持 16dp 间距。",
    )
    basic = buttons.OutlinedButton("基础对话框", icon="chat_bubble")
    full = buttons.OutlinedButton("全屏对话框", icon="open_in_full")
    choose_one = buttons.OutlinedButton("单选列表", icon="radio_button_checked")
    choose_many = buttons.OutlinedButton("多选列表", icon="checklist")
    prompt = buttons.OutlinedButton("输入对话框", icon="edit")
    progress = buttons.OutlinedButton("进度对话框", icon="hourglass_top")
    bottom = buttons.OutlinedButton("底部面板", icon="vertical_align_bottom")
    side = buttons.OutlinedButton("侧面板", icon="view_sidebar")
    detached = buttons.OutlinedButton("detached 侧面板", icon="dock_to_left")
    page.row(dialog_section, [basic, full, choose_one, choose_many, prompt])
    page.row(dialog_section, [progress, bottom, side, detached])
    dialog_result = typography.Label("", "body-small", "on_surface_variant")
    dialog_section.addWidget(dialog_result)
    _connect_dialog_buttons(
        page, dialog_result, choose_one, choose_many, prompt, progress
    )
    _connect_panel_buttons(page, basic, full, bottom, side, detached)


def _connect_dialog_buttons(
    page: _common.Page,
    dialog_result: typography.Label,
    choose_one: buttons.Button,
    choose_many: buttons.Button,
    prompt: buttons.Button,
    progress: buttons.Button,
) -> None:
    def open_choose_one() -> None:
        index = dialogs.choose(
            page, "铃声", ["无", "默认", "清脆", "低沉"], selected=1
        )
        dialog_result.setText(
            "已取消" if index is None else f"选择了第 {index + 1} 项"
        )

    def open_choose_many() -> None:
        chosen = dialogs.choose_many(
            page, "标签", ["工作", "个人", "旅行", "账单"], [0, 2]
        )
        dialog_result.setText(
            "已取消" if chosen is None else f"选择了 {len(chosen)} 项"
        )

    def open_prompt() -> None:
        name = dialogs.prompt(page, "重命名", "名称", "未命名文档")
        dialog_result.setText("已取消" if name is None else f"新名称：{name}")

    def open_progress() -> None:
        dialog = dialogs.ProgressDialog("正在导出", "准备中…", parent=page)
        timer = QtCore.QTimer(dialog)
        state = {"done": 0}

        def step() -> None:
            state["done"] += 1
            dialog.set_progress(
                state["done"], 20, f"已导出 {state['done']} / 20"
            )
            if state["done"] >= 20:
                timer.stop()
                dialog.finish()

        timer.timeout.connect(step)
        dialog.canceled.connect(timer.stop)
        timer.start(150)
        dialog.exec()

    choose_one.clicked.connect(open_choose_one)
    choose_many.clicked.connect(open_choose_many)
    prompt.clicked.connect(open_prompt)
    progress.clicked.connect(open_progress)


def _connect_panel_buttons(
    page: _common.Page,
    basic: buttons.Button,
    full: buttons.Button,
    bottom: buttons.Button,
    side: buttons.Button,
    detached: buttons.Button,
) -> None:
    def open_basic() -> None:
        dialog = dialogs.BasicDialog(
            "重置设置？",
            "这将清除所有本地保存的偏好设置，且无法撤销。",
            icon="restart_alt",
            parent=page,
        )
        dialog.add_action(
            "取消", QtWidgets.QDialogButtonBox.ButtonRole.RejectRole
        )
        dialog.add_action("重置")
        dialog.exec()

    def open_full() -> None:
        dialog = dialogs.FullScreenDialog("新建事件", parent=page)
        dialog.add_widget(typography.Label("全屏对话框内容", "body-large"))
        dialog.exec()

    def open_bottom() -> None:
        sheet = sheets.BottomSheet(
            page.window(), modal=True, detents=[260, 0.6, 0.92]
        )
        label = typography.Label("底部面板内容 · 停靠点 1 / 3", "body-large")
        sheet.detent_changed.connect(
            lambda index: label.setText(
                f"底部面板内容 · 停靠点 {index + 1} / {len(sheet.detents)}"
            )
        )
        sheet.set_content(label)
        sheet.open_panel()

    def open_side() -> None:
        sheet = sheets.SideSheet(page.window(), "侧面板", modal=True)
        sheet.set_content(typography.Label("侧面板内容", "body-large"))
        sheet.add_action("保存", primary=True).clicked.connect(
            sheet.close_panel
        )
        sheet.add_action("取消").clicked.connect(sheet.close_panel)
        sheet.open_panel()

    def open_detached() -> None:
        sheet = sheets.SideSheet(
            page.window(), "筛选", detached=True, show_back=True
        )
        sheet.set_content(
            typography.Label("detached 侧面板浮于内容之上。", "body-large")
        )
        sheet.back_clicked.connect(sheet.close_panel)
        sheet.open_panel()

    basic.clicked.connect(open_basic)
    full.clicked.connect(open_full)
    bottom.clicked.connect(open_bottom)
    side.clicked.connect(open_side)
    detached.clicked.connect(open_detached)
