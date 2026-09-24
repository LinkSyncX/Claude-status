"""组件内置文字的国际化。

组件自身只包含少量文字：对话框的"确定 / 取消"、图标按钮的提示、选择器
的标题与校验提示、密码强度等级等。这些文字全部集中在 ``Strings`` 中，
默认为中文，另附英文 ``ENGLISH``。

- ``set_locale("en")`` 切换到内置语言；``set_locale("system")`` 按系统
  区域选择，未内置的语言回退到英文。
- ``set_strings(Strings(...))`` 整套替换；``update_strings(confirm="OK")``
  只覆盖部分条目；``register_locale("ja", Strings(...))`` 注册新语言。
- 组件在构造或绘制时调用 ``tr("confirm")`` 取字符串，因此切换语言后新建
  的组件立即生效；需要即时刷新的已有控件可监听 ``manager().strings_changed``。
"""

from __future__ import annotations

import dataclasses

from PySide6 import QtCore


@dataclasses.dataclass(frozen=True)
class Strings:
    """组件内置文字。字段名即 ``tr`` 使用的键。"""

    confirm: str = "确定"
    cancel: str = "取消"
    save: str = "保存"
    close: str = "关闭"
    back: str = "返回"
    more: str = "更多"
    menu: str = "菜单"
    clear: str = "清除"
    search: str = "搜索"
    expand: str = "展开"
    collapse: str = "收起"
    increase: str = "增加"
    decrease: str = "减少"
    scroll_left: str = "向左滚动"
    scroll_right: str = "向右滚动"
    no_data: str = "暂无数据"
    size: str = "大小"
    value: str = "数值"
    total: str = "总计"
    current_value: str = "当前值"
    target: str = "目标"
    previous_month: str = "上个月"
    next_month: str = "下个月"
    select_date: str = "选择日期"
    select_date_range: str = "选择日期范围"
    select_time: str = "选择时间"
    date: str = "日期"
    start_date: str = "起始日期"
    end_date: str = "结束日期"
    time: str = "时间"
    hour: str = "小时"
    minute: str = "分钟"
    keyboard_input: str = "键盘输入"
    switch_to_calendar: str = "切换到月历"
    switch_input_mode: str = "切换输入方式"
    invalid_date: str = "日期格式无效"
    invalid_time: str = "时间格式无效"
    out_of_range: str = "超出可选范围"
    # 日期格式使用 QLocale / QDate.toString 的格式串。
    date_format_long: str = "yyyy年M月d日"
    month_year_format: str = "yyyy年M月"
    date_title_format: str = "M月d日 ddd"
    date_short_format: str = "M月d日"
    select_color: str = "选择颜色"
    hex_code: str = "十六进制"
    invalid_hex: str = "请输入 6 位十六进制颜色"
    hue: str = "色相"
    chroma: str = "色度"
    tone: str = "色调"
    password: str = "密码"
    strength_weak: str = "弱"
    strength_fair: str = "一般"
    strength_strong: str = "强"
    strength_very_strong: str = "很强"
    tags: str = "标签"
    tag_placeholder: str = "输入后按回车或逗号添加"
    tag_rejected: str = "标签重复或已达上限"
    file: str = "文件"
    choose_file: str = "选择文件"
    save_to: str = "保存到"
    choose_folder: str = "选择文件夹"
    rows_per_page: str = "每页行数"
    first_page: str = "第一页"
    previous_page: str = "上一页"
    next_page: str = "下一页"
    last_page: str = "最后一页"
    select_all: str = "全选"
    # ``{start}`` ``{end}`` ``{total}`` 会被替换为实际数字。
    page_range: str = "{start}–{end} / 共 {total} 项"
    step_optional: str = "可选"
    dismiss: str = "忽略"
    browse_files: str = "浏览文件"
    drop_files_here: str = "拖放文件到这里"
    no_results: str = "没有匹配的结果"
    type_to_search: str = "输入以搜索命令"
    minimize: str = "最小化"
    maximize: str = "最大化"
    restore: str = "还原"
    pick_color: str = "选择颜色"

    def get(self, key: str) -> str:
        """按键名取文字。

        Raises:
            KeyError: 键名不存在。
        """
        if key not in STRING_KEYS:
            raise KeyError(f"未知的字符串键: {key!r}")
        return getattr(self, key)

    def replace(self, **overrides: str) -> Strings:
        """返回覆盖了部分条目的新实例。"""
        return dataclasses.replace(self, **overrides)


STRING_KEYS: tuple[str, ...] = tuple(
    field.name for field in dataclasses.fields(Strings)
)

CHINESE = Strings()
ENGLISH = Strings(
    confirm="OK",
    cancel="Cancel",
    save="Save",
    close="Close",
    back="Back",
    more="More",
    menu="Menu",
    clear="Clear",
    search="Search",
    expand="Expand",
    collapse="Collapse",
    increase="Increase",
    decrease="Decrease",
    scroll_left="Scroll left",
    scroll_right="Scroll right",
    no_data="No data",
    size="Size",
    value="Value",
    total="Total",
    current_value="Current",
    target="Target",
    previous_month="Previous month",
    next_month="Next month",
    select_date="Select date",
    select_date_range="Select date range",
    select_time="Select time",
    date="Date",
    start_date="Start date",
    end_date="End date",
    time="Time",
    hour="Hour",
    minute="Minute",
    keyboard_input="Switch to keyboard input",
    switch_to_calendar="Switch to calendar",
    switch_input_mode="Switch input mode",
    invalid_date="Invalid date format",
    invalid_time="Invalid time format",
    out_of_range="Out of range",
    date_format_long="MMM d, yyyy",
    month_year_format="MMMM yyyy",
    date_title_format="ddd, MMM d",
    date_short_format="MMM d",
    select_color="Select color",
    hex_code="Hex",
    invalid_hex="Enter a 6-digit hex color",
    hue="Hue",
    chroma="Chroma",
    tone="Tone",
    password="Password",
    strength_weak="Weak",
    strength_fair="Fair",
    strength_strong="Strong",
    strength_very_strong="Very strong",
    tags="Tags",
    tag_placeholder="Press Enter or comma to add",
    tag_rejected="Duplicate tag or limit reached",
    file="File",
    choose_file="Choose file",
    save_to="Save to",
    choose_folder="Choose folder",
    rows_per_page="Rows per page",
    first_page="First page",
    previous_page="Previous page",
    next_page="Next page",
    last_page="Last page",
    select_all="Select all",
    page_range="{start}–{end} of {total}",
    step_optional="Optional",
    dismiss="Dismiss",
    browse_files="Browse files",
    drop_files_here="Drop files here",
    no_results="No matching results",
    type_to_search="Type to search commands",
    minimize="Minimize",
    maximize="Maximize",
    restore="Restore",
    pick_color="Pick a color",
)

_LOCALES: dict[str, Strings] = {"zh": CHINESE, "en": ENGLISH}
FALLBACK_LOCALE = "en"


class StringsManager(QtCore.QObject):
    """持有当前字符串并在切换时发出 ``strings_changed``。"""

    strings_changed = QtCore.Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self._strings = CHINESE
        self._locale = "zh"

    @property
    def strings(self) -> Strings:
        """当前字符串。"""
        return self._strings

    @property
    def locale(self) -> str:
        """当前语言名；自定义字符串时为 ``"custom"``。"""
        return self._locale

    def set_strings(self, strings: Strings, locale: str = "custom") -> None:
        """替换当前字符串。"""
        self._strings = strings
        self._locale = locale
        self.strings_changed.emit(strings)


_manager: StringsManager | None = None


def manager() -> StringsManager:
    """全局字符串管理器。"""
    global _manager  # pylint: disable=global-statement
    if _manager is None:
        _manager = StringsManager()
    return _manager


def current() -> Strings:
    """当前字符串集。"""
    return manager().strings


def tr(key: str) -> str:
    """取当前语言下的字符串，例如 ``tr("confirm")``。"""
    return current().get(key)


def set_strings(strings: Strings) -> None:
    """整套替换字符串。"""
    manager().set_strings(strings)


def update_strings(**overrides: str) -> None:
    """覆盖当前字符串中的部分条目。"""
    manager().set_strings(current().replace(**overrides))


def register_locale(name: str, strings: Strings) -> None:
    """注册（或替换）一种语言，``name`` 为 ISO 639 语言码。"""
    _LOCALES[_language_of(name)] = strings


def available_locales() -> list[str]:
    """已注册的语言名。"""
    return sorted(_LOCALES)


def _language_of(locale: str) -> str:
    """把 ``zh_CN`` / ``en-US`` 之类的区域名归一为语言码。"""
    return locale.replace("-", "_").split("_")[0].lower()


def resolve_locale(locale: str) -> str:
    """把区域名解析为已注册的语言名；``"system"`` 取系统区域。

    未注册的语言回退到 ``FALLBACK_LOCALE``。
    """
    if locale == "system":
        locale = QtCore.QLocale.system().name()
    language = _language_of(locale)
    return language if language in _LOCALES else FALLBACK_LOCALE


def set_locale(locale: str) -> str:
    """切换到内置 / 已注册的语言，返回实际生效的语言名。"""
    language = resolve_locale(locale)
    manager().set_strings(_LOCALES[language], language)
    return language


def current_locale() -> str:
    """当前语言名。"""
    return manager().locale
