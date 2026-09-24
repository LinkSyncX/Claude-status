"""Actions 页面：按钮族。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import menus
from md3.components import snackbar
from md3.components import toolbar
from md3.core import typography
from md3.demo.pages import _common


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page("操作", "按钮、图标按钮、悬浮操作按钮与分段按钮。")

    common = page.section(
        "通用按钮", "五种强调层级：elevated、filled、tonal、outlined、text。"
    )
    page.row(
        common,
        [
            buttons.ElevatedButton("Elevated"),
            buttons.FilledButton("Filled"),
            buttons.FilledTonalButton("Tonal"),
            buttons.OutlinedButton("Outlined"),
            buttons.TextButton("Text"),
        ],
    )
    with_icons = [
        buttons.ElevatedButton("添加", icon="add"),
        buttons.FilledButton("发送", icon="send"),
        buttons.FilledTonalButton("下载", icon="download"),
        buttons.OutlinedButton("编辑", icon="edit"),
        buttons.TextButton("分享", icon="share"),
    ]
    page.row(common, with_icons)
    disabled = [
        buttons.ElevatedButton("Elevated"),
        buttons.FilledButton("Filled"),
        buttons.FilledTonalButton("Tonal"),
        buttons.OutlinedButton("Outlined"),
        buttons.TextButton("Text"),
    ]
    for button in disabled:
        button.setEnabled(False)
    page.row(common, disabled)
    feedback = buttons.FilledButton("点击显示 Snackbar", icon="notifications")
    feedback.clicked.connect(
        lambda: snackbar.show(feedback, "这是一条 Snackbar 提示", action="撤销")
    )
    page.row(common, [feedback])

    icon_section = page.section(
        "图标按钮", "standard / filled / tonal / outlined，均支持切换态。"
    )
    page.row(
        icon_section,
        [
            buttons.IconButton("settings", variant, tooltip=variant.value)
            for variant in buttons.IconButtonVariant
        ],
    )
    page.row(
        icon_section,
        [
            buttons.IconButton(
                "favorite", variant, checkable=True, checked=True
            )
            for variant in buttons.IconButtonVariant
        ]
        + [
            buttons.IconButton("favorite", variant, checkable=True)
            for variant in buttons.IconButtonVariant
        ],
    )

    fab_section = page.section(
        "悬浮操作按钮", "small / regular / large 与四种配色，以及扩展 FAB。"
    )
    page.row(
        fab_section,
        [
            buttons.FloatingActionButton("edit", buttons.FabSize.SMALL),
            buttons.FloatingActionButton("edit"),
            buttons.FloatingActionButton(
                "edit", color=buttons.FabColor.SURFACE
            ),
            buttons.FloatingActionButton(
                "edit", color=buttons.FabColor.SECONDARY
            ),
            buttons.FloatingActionButton(
                "edit", color=buttons.FabColor.TERTIARY
            ),
            buttons.FloatingActionButton("edit", buttons.FabSize.LARGE),
            buttons.ExtendedFab("撰写", icon="edit"),
            buttons.ExtendedFab("无图标", lowered=True),
        ],
        gap=16,
    )

    segmented = page.section("分段按钮", "单选或多选，2–5 个分段。")
    page.row(
        segmented,
        [
            buttons.SegmentedButton(["日", "周", "月", "年"], selected={1}),
            buttons.SegmentedButton(
                [
                    buttons.Segment("粗体", "format_bold"),
                    buttons.Segment("斜体", "format_italic"),
                    buttons.Segment("下划线", "format_underlined"),
                ],
                multi_select=True,
                selected={0, 2},
            ),
        ],
        gap=16,
    )
    _build_expressive_sections(page)
    page.finish()
    return page


def _build_expressive_sections(page: _common.Page) -> None:
    """M3 Expressive 新增的操作组件。"""
    toggles = page.section(
        "切换按钮",
        "未选中为胶囊形，选中后换用强调配色并以弹簧过渡收成方角。",
    )
    page.row(
        toggles,
        [
            buttons.ToggleButton(variant.value.title(), "star", variant)
            for variant in buttons.ButtonVariant
        ],
    )

    groups = page.section(
        "按钮组",
        "按下某个按钮时它横向扩张、邻近按钮收缩；连接组内按钮相接，选中的"
        "切换按钮变为完整胶囊。",
    )
    groups.addWidget(
        buttons.ButtonGroup(
            [
                buttons.FilledButton("保存", "save"),
                buttons.FilledTonalButton("另存为"),
                buttons.OutlinedButton("导出"),
                buttons.TextButton("放弃"),
            ]
        ),
        0,
        QtCore.Qt.AlignmentFlag.AlignLeft,
    )
    period = buttons.ButtonGroup(
        [buttons.ToggleButton(label) for label in ("日", "周", "月", "年")],
        connected=True,
        single_selection=True,
    )
    period.set_checked(1)
    formats = buttons.ButtonGroup(
        [
            buttons.IconButton(
                icon,
                variant=buttons.IconButtonVariant.TONAL,
                checkable=True,
                checked=index == 0,
                tooltip=tip,
            )
            for index, (icon, tip) in enumerate(
                (
                    ("format_bold", "粗体"),
                    ("format_italic", "斜体"),
                    ("format_underlined", "下划线"),
                    ("format_strikethrough", "删除线"),
                )
            )
        ],
        connected=True,
    )
    page.row(groups, [period, formats], gap=24)

    split_section = page.section(
        "拆分按钮", "主操作 + 下拉箭头；菜单打开时箭头旋转、右段变为胶囊。"
    )
    result = typography.Label("", "body-medium", "on_surface_variant")
    export_menu = menus.Menu(
        [
            menus.MenuItem("导出为 PDF", icon="picture_as_pdf"),
            menus.MenuItem("导出为 PNG", icon="image"),
            menus.MenuItem("导出为 SVG", icon="polyline"),
        ]
    )
    split = buttons.SplitButton("导出", "download", menu=export_menu)
    split.clicked.connect(lambda: result.setText("执行了主操作：导出"))
    split.triggered.connect(
        lambda item: result.setText(f"选择了「{item.text}」")
    )
    tonal_split = buttons.SplitButton(
        "分享",
        "share",
        variant=buttons.ButtonVariant.TONAL,
        menu=menus.Menu(["复制链接", "发送邮件"]),
    )
    outlined_split = buttons.SplitButton(
        "更多",
        variant=buttons.ButtonVariant.OUTLINED,
        menu=menus.Menu(["重命名", "删除"]),
    )
    page.row(split_section, [split, tonal_split, outlined_split, result])

    toolbar_section = page.section(
        "工具栏", "浮动工具栏（标准 / 鲜明配色）与横跨底部的停靠工具栏。"
    )
    editing = toolbar.Toolbar(
        ["undo", "redo", "content_cut", "content_copy", "content_paste"]
    )
    vibrant = toolbar.Toolbar(
        [
            "format_bold",
            "format_italic",
            "format_underlined",
            "format_color_text",
        ],
        color=toolbar.ToolbarColor.VIBRANT,
    )
    for index, tip in enumerate(("加粗", "斜体", "下划线", "文字颜色")):
        vibrant.action_buttons[index].set_tooltip(tip)
    page.row(toolbar_section, [editing, vibrant], gap=24)
    docked = toolbar.Toolbar(
        ["home", "search", "favorite", "person"], floating=False
    )
    docked.add_stretch()
    docked.add_action("settings", "设置")
    toolbar_section.addWidget(docked)

    fab_section = page.section(
        "FAB 菜单",
        "点击 FAB 展开一组带标签的操作，再次点击、点击别处或按 Esc 收起。",
    )
    fab_result = typography.Label("", "body-medium", "on_surface_variant")
    fab_menu = buttons.FabMenu(
        [
            buttons.FabMenuItem("新建文档", "description"),
            buttons.FabMenuItem("新建表格", "table_chart"),
            buttons.FabMenuItem("新建演示", "slideshow"),
        ]
    )
    fab_menu.triggered.connect(
        lambda item: fab_result.setText(f"选择了「{item.text}」")
    )
    row = QtWidgets.QHBoxLayout()
    row.addWidget(fab_result)
    row.addStretch()
    row.addWidget(fab_menu)
    fab_section.addSpacing(200)  # 为向上展开的操作项预留空间
    fab_section.addLayout(row)
