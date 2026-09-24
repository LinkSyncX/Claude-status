"""Selection 页面：复选框、单选、开关、滑块、纸片、菜单。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.components import buttons
from md3.components import chips
from md3.components import menus
from md3.components import selection
from md3.components import slider
from md3.core import typography
from md3.demo.pages import _common


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page("选择", "复选框、单选按钮、开关、滑块、纸片与菜单。")

    boxes = page.section("复选框")
    tri = selection.Checkbox("三态", tristate=True)
    tri.set_state(selection.CheckState.INDETERMINATE)
    disabled = selection.Checkbox("禁用", checked=True)
    disabled.setEnabled(False)
    page.row(
        boxes,
        [
            selection.Checkbox("未选中"),
            selection.Checkbox("已选中", checked=True),
            tri,
            selection.Checkbox("错误", checked=True, error=True),
            disabled,
        ],
    )

    radios = page.section("单选按钮")
    group = selection.RadioGroup()
    radio_widgets = []
    for index, label in enumerate(["选项 A", "选项 B", "选项 C"]):
        button = selection.RadioButton(label, checked=index == 0)
        group.add(button)
        radio_widgets.append(button)
    disabled_radio = selection.RadioButton("禁用")
    disabled_radio.setEnabled(False)
    page.row(radios, [*radio_widgets, disabled_radio])

    switches = page.section("开关")
    disabled_switch = selection.Switch("禁用", checked=True)
    disabled_switch.setEnabled(False)
    page.row(
        switches,
        [
            selection.Switch("关闭"),
            selection.Switch("开启", checked=True),
            selection.Switch("带图标", checked=True, show_icons=True),
            disabled_switch,
        ],
    )

    _build_slider_sections(page)
    _build_chip_and_menu_sections(page)
    page.finish()
    return page


def _build_slider_sections(page: _common.Page) -> None:
    sliders = page.section("滑块", "连续、离散与范围滑块；拖动时显示数值。")
    continuous = slider.Slider(0, 100, 40)
    value_label = typography.Label("40", "label-large", "on_surface_variant")
    continuous.value_changed.connect(lambda v: value_label.setText(f"{v:.0f}"))
    row = QtWidgets.QHBoxLayout()
    row.addWidget(continuous, 1)
    row.addWidget(value_label)
    sliders.addLayout(row)
    sliders.addWidget(slider.Slider(0, 10, 6, step=1))
    sliders.addWidget(slider.RangeSlider(0, 100, 20, 70))
    off = slider.Slider(0, 100, 30)
    off.setEnabled(False)
    sliders.addWidget(off)

    expressive = page.section(
        "尺寸、居中与竖直滑块",
        "XS–XL 五种轨道粗细，M 以上可在轨道内放置图标；居中滑块的活动"
        "轨道从中点出发；竖直滑块自下而上增大。",
    )
    for size, value in (
        (slider.SliderSize.SMALL, 35),
        (slider.SliderSize.MEDIUM, 55),
        (slider.SliderSize.LARGE, 70),
    ):
        sized = slider.Slider(0, 100, value, size=size)
        sized.set_track_icons("volume_mute", "volume_up")
        expressive.addWidget(sized)
    balance = slider.Slider(-50, 50, 20, step=5, centered=True)
    expressive.addWidget(balance)
    verticals = QtWidgets.QHBoxLayout()
    verticals.setSpacing(24)
    for size, value in (
        (slider.SliderSize.EXTRA_SMALL, 30),
        (slider.SliderSize.MEDIUM, 60),
    ):
        tall = slider.Slider(
            0,
            100,
            value,
            orientation=QtCore.Qt.Orientation.Vertical,
            size=size,
        )
        tall.setFixedHeight(200)
        verticals.addWidget(tall)
    tall_range = slider.RangeSlider(
        0, 100, 25, 75, orientation=QtCore.Qt.Orientation.Vertical
    )
    tall_range.setFixedHeight(200)
    verticals.addWidget(tall_range)
    verticals.addStretch()
    expressive.addLayout(verticals)


def _build_chip_and_menu_sections(page: _common.Page) -> None:
    chip_section = page.section(
        "纸片", "assist / filter / input / suggestion。"
    )
    page.row(
        chip_section,
        [
            chips.AssistChip("添加到日历", icon="event"),
            chips.AssistChip("Elevated", icon="event", elevated=True),
            chips.FilterChip("过滤"),
            chips.FilterChip("已选", selected=True),
            chips.FilterChip("更多", trailing_icon="arrow_drop_down"),
            chips.InputChip("输入项"),
            chips.InputChip("联系人", icon="person"),
            chips.SuggestionChip("建议"),
        ],
    )

    group_section = page.section(
        "纸片组",
        "流式换行；过滤纸片可单选或多选，输入纸片移除后其余纸片滑动补位。",
    )
    filters = chips.ChipGroup(
        ["全部", "未读", "已加星", "有附件", "重要", "已归档", "草稿"],
        single_selection=True,
    )
    filters.set_selected([0])
    chosen = typography.Label("已选：全部", "body-medium", "on_surface_variant")
    filters.selection_changed.connect(
        lambda _indices: chosen.setText(
            "已选：" + ("、".join(filters.selected_texts) or "无")
        )
    )
    group_section.addWidget(filters)
    group_section.addWidget(chosen)
    inputs = chips.ChipGroup(
        [
            chips.InputChip(name, icon="person")
            for name in ("张伟", "李娜", "王芳", "刘洋")
        ]
    )
    group_section.addWidget(inputs)

    menu_section = page.section("菜单与下拉选择")
    menu = menus.Menu(
        [
            menus.MenuItem("撤销", icon="undo", trailing_text="Ctrl+Z"),
            menus.MenuItem(
                "重做", icon="redo", trailing_text="Ctrl+Y", enabled=False
            ),
            menus.MenuItem.divider(),
            menus.MenuItem("显示网格", checkable=True, checked=True),
            menus.MenuItem("更多", submenu=menus.Menu(["子项 1", "子项 2"])),
        ]
    )
    open_menu = buttons.OutlinedButton("打开菜单", icon="more_vert")
    open_menu.clicked.connect(
        lambda: menu.popup(
            open_menu.mapToGlobal(QtCore.QPoint(0, open_menu.height()))
        )
    )
    result = typography.Label("", "body-medium", "on_surface_variant")
    menu.triggered.connect(
        lambda item: result.setText(f"选择了「{item.text}」")
    )
    page.row(
        menu_section,
        [
            open_menu,
            menus.DropdownMenu(
                ["苹果", "香蕉", "樱桃"], label="水果", selected_index=1
            ),
            menus.DropdownMenu(
                ["小", "中", "大"], label="尺寸", outlined=False
            ),
            result,
        ],
        gap=16,
    )
