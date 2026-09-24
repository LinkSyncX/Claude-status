"""Text inputs 页面：文本框。"""

from __future__ import annotations

from PySide6 import QtWidgets

from md3.components import search
from md3.components import text_fields
from md3.core import typography
from md3.demo.pages import _common


def _validate_email(text: str) -> str | None:
    if not text:
        return None
    if "@" not in text or text.startswith("@") or text.endswith("@"):
        return "请输入有效的邮箱地址"
    return None


def _build_more_inputs(page: _common.Page) -> None:
    section = page.section(
        "更多输入类型",
        "数字输入框（步进按钮、方向键、滚轮、范围与小数位）、带强度指示的"
        "密码框、文件 / 目录选择框，以及验证码输入格。",
    )
    grid = QtWidgets.QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(16)
    quantity = text_fields.NumberField(
        "数量", 3, minimum=0, maximum=10, suffix="件"
    )
    price = text_fields.NumberField(
        "单价",
        19.9,
        minimum=0,
        step=0.5,
        decimals=2,
        prefix="¥",
        variant=text_fields.TextFieldVariant.FILLED,
        supporting_text="步长 0.5，可回车 / 失焦时自动格式化",
    )
    password = text_fields.PasswordField(
        "密码", supporting_text="至少 8 位，混合大小写、数字与符号"
    )
    strong = text_fields.PasswordField(
        "确认密码",
        "Str0ng!Passw0rd",
        variant=text_fields.TextFieldVariant.FILLED,
    )
    avatar = text_fields.FileField(
        "头像",
        name_filter="图片 (*.png *.jpg *.svg)",
        supporting_text="PNG / JPG / SVG",
    )
    export = text_fields.FileField(
        "导出目录",
        mode=text_fields.FileMode.DIRECTORY,
        variant=text_fields.TextFieldVariant.FILLED,
    )
    for index, field in enumerate(
        (quantity, price, password, strong, avatar, export)
    ):
        grid.addWidget(field, index // 2, index % 2)
    section.addLayout(grid)

    pin_row = QtWidgets.QHBoxLayout()
    pin_row.setSpacing(24)
    pin = text_fields.PinField(6, group_size=3)
    status = typography.Label(
        "输入 6 位验证码", "body-medium", "on_surface_variant"
    )
    pin.completed.connect(lambda code: status.setText(f"已输入：{code}"))
    pin.code_changed.connect(
        lambda code: (
            status.setText("输入 6 位验证码") if len(code) < 6 else None
        )
    )
    masked = text_fields.PinField(4, masked=True)
    pin_row.addWidget(pin)
    pin_row.addWidget(masked)
    pin_row.addWidget(status)
    pin_row.addStretch()
    section.addLayout(pin_row)


def _build_select_fields(page: _common.Page) -> None:
    section = page.section(
        "下拉选择",
        "SelectField 以文本框形态承载单选菜单：点击或空格 / 回车 / 方向键展开，"
        "字母键定位；可编辑模式在输入时过滤候选，允许自定义值时保留输入。",
    )
    grid = QtWidgets.QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(16)
    status = typography.Label("尚未选择", "body-medium", "on_surface_variant")
    plain = text_fields.SelectField(
        "语言",
        ["简体中文", "English", "日本語", "Deutsch", "Français"],
        selected_index=0,
        leading_icon="language",
    )
    plain.selection_changed.connect(
        lambda index: status.setText(f"已选择：{plain.selected_text}")
    )
    filled = text_fields.SelectField(
        "优先级",
        ["紧急", "高", "中", "低"],
        variant=text_fields.TextFieldVariant.FILLED,
        supporting_text="填充样式",
    )
    editable = text_fields.SelectField(
        "国家或地区",
        [
            "中国",
            "美国",
            "日本",
            "德国",
            "法国",
            "英国",
            "加拿大",
            "澳大利亚",
            "新加坡",
            "韩国",
        ],
        editable=True,
        supporting_text="可输入过滤",
    )
    custom = text_fields.SelectField(
        "字体",
        ["Roboto", "Inter", "Noto Sans", "Source Han Sans"],
        editable=True,
        allow_custom=True,
        supporting_text="允许自定义值",
    )
    grid.addWidget(plain, 0, 0)
    grid.addWidget(filled, 0, 1)
    grid.addWidget(editable, 1, 0)
    grid.addWidget(custom, 1, 1)
    section.addLayout(grid)
    section.addWidget(status)


def build() -> QtWidgets.QWidget:
    """构建页面。"""
    page = _common.Page(
        "文本输入",
        "filled 与 outlined 文本框、数字 / 密码 / 文件 / 验证码等输入类型，"
        "以及自动补全与搜索栏。",
    )
    grid_section = page.section("文本框")
    grid = QtWidgets.QGridLayout()
    grid.setHorizontalSpacing(24)
    grid.setVerticalSpacing(16)
    error = text_fields.OutlinedTextField(
        "用户名", "bad name!", trailing_icon="error"
    )
    error.set_error(True, "用户名只能包含字母")
    disabled = text_fields.FilledTextField("禁用", "不可编辑")
    disabled.setEnabled(False)
    fields = [
        text_fields.FilledTextField("标签"),
        text_fields.OutlinedTextField("标签"),
        text_fields.FilledTextField(
            "邮箱",
            "someone@example.com",
            leading_icon="mail",
            supporting_text="用于接收通知",
        ),
        text_fields.OutlinedTextField(
            "邮箱",
            "someone@example.com",
            leading_icon="mail",
            supporting_text="用于接收通知",
        ),
        text_fields.FilledTextField("密码", "secret", password=True),
        error,
        text_fields.FilledTextField(
            "金额", "100", prefix="¥", suffix="元", max_length=8
        ),
        text_fields.OutlinedTextField(
            "简介",
            "多行文本框可以输入较长内容。",
            multiline=True,
            rows=3,
            max_length=100,
            supporting_text="最多 100 字",
        ),
        disabled,
        text_fields.OutlinedTextField("占位文字", placeholder="请输入内容"),
        text_fields.OutlinedTextField(
            "搜索关键词", "material", clearable=True, leading_icon="search"
        ),
        text_fields.FilledTextField(
            "邮箱（实时校验）",
            "not-an-email",
            validator=_validate_email,
            supporting_text="输入时即时校验",
        ),
        text_fields.FilledTextField("只读", "不可编辑但可复制", read_only=True),
        text_fields.TextArea(
            "备注（自动增高）",
            "随内容增高，\n最多 5 行后出现滚动条。",
            min_rows=2,
            max_rows=5,
        ),
    ]
    for index, field in enumerate(fields):
        grid.addWidget(field, index // 2, index % 2)
    grid_section.addLayout(grid)

    _build_more_inputs(page)

    auto_section = page.section(
        "自动补全与标签输入",
        "输入时按子串过滤候选并在下方列出（方向键 / 回车选择、Esc 收起）；"
        "标签输入框以回车或逗号确认，空文本时退格删除最后一个标签。",
    )
    auto_grid = QtWidgets.QGridLayout()
    auto_grid.setHorizontalSpacing(24)
    auto_grid.setVerticalSpacing(16)
    city = text_fields.AutocompleteTextField(
        "城市",
        [
            "北京",
            "上海",
            "广州",
            "深圳",
            "杭州",
            "南京",
            "成都",
            "武汉",
            "西安",
        ],
        supporting_text="试试输入“州”",
    )
    language = text_fields.AutocompleteTextField(
        "编程语言",
        ["Python", "Rust", "TypeScript", "Go", "Kotlin", "Swift", "Java", "C#"],
        variant=text_fields.TextFieldVariant.FILLED,
        leading_icon="code",
    )
    tags = text_fields.TagField(
        "收件人",
        ["alice@example.com"],
        suggestions=[
            "bob@example.com",
            "carol@example.com",
            "dave@example.com",
        ],
        max_tags=5,
    )
    auto_grid.addWidget(city, 0, 0)
    auto_grid.addWidget(language, 0, 1)
    auto_grid.addWidget(tags, 1, 0, 1, 2)
    auto_section.addLayout(auto_grid)
    _build_select_fields(page)

    search_section = page.section("搜索栏", "聚焦后在下方展开搜索视图。")
    bar = search.SearchBar("搜索邮件", trailing_icon="mic")
    search_section.addWidget(bar)
    page.finish()

    def attach_view() -> None:
        window = bar.window()
        if window is not None and window is not bar:
            view = search.SearchView(window, bar)
            view.set_suggestions(
                ["最近的会议", "来自 Alice 的邮件", "附件：报表.pdf"]
            )
            bar.submitted.connect(lambda _text: view.close_panel())
            page.search_view = view  # type: ignore[attr-defined]  # 持有引用

    page.attach_search_view = attach_view  # type: ignore[attr-defined]
    return page
