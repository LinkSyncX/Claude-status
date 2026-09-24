"""排版标度（md.sys.typescale）。

M3 定义了 display / headline / title / body / label 五个角色，每个角色
有 large / medium / small 三档，共 15 个样式。字号与行高单位为 sp，
在桌面端视为逻辑像素；字距（tracking）单位为 px。
"""

from __future__ import annotations

import dataclasses
import enum

FONT_FAMILY_BRAND = "Roboto"
FONT_FAMILY_PLAIN = "Roboto"
# 当 Roboto 不可用时依次尝试的系统字体。
FONT_FAMILY_FALLBACKS: tuple[str, ...] = (
    "Segoe UI",
    "Helvetica Neue",
    "Noto Sans",
    "Microsoft YaHei UI",
    "PingFang SC",
    "sans-serif",
)

WEIGHT_REGULAR = 400
WEIGHT_MEDIUM = 500
WEIGHT_BOLD = 700


class TypeRole(enum.Enum):
    """排版角色枚举，值为规范中的令牌名。"""

    DISPLAY_LARGE = "display-large"
    DISPLAY_MEDIUM = "display-medium"
    DISPLAY_SMALL = "display-small"
    HEADLINE_LARGE = "headline-large"
    HEADLINE_MEDIUM = "headline-medium"
    HEADLINE_SMALL = "headline-small"
    TITLE_LARGE = "title-large"
    TITLE_MEDIUM = "title-medium"
    TITLE_SMALL = "title-small"
    BODY_LARGE = "body-large"
    BODY_MEDIUM = "body-medium"
    BODY_SMALL = "body-small"
    LABEL_LARGE = "label-large"
    LABEL_MEDIUM = "label-medium"
    LABEL_SMALL = "label-small"


@dataclasses.dataclass(frozen=True)
class TypeStyle:
    """单个排版样式。

    Attributes:
        role: 对应的排版角色。
        family: 字体族名称。
        size: 字号（sp）。
        line_height: 行高（sp）。
        weight: 字重（CSS 数值，400 为常规、500 为中等）。
        tracking: 字距（px），可为负值。
    """

    role: TypeRole
    family: str
    size: float
    line_height: float
    weight: int
    tracking: float

    @property
    def name(self) -> str:
        """规范中的令牌名，例如 ``body-large``。"""
        return self.role.value

    def scaled(self, factor: float) -> TypeStyle:
        """返回按比例放大或缩小字号与行高的新样式。"""
        return dataclasses.replace(
            self,
            size=self.size * factor,
            line_height=self.line_height * factor,
        )


def _style(
    role: TypeRole,
    size: float,
    line_height: float,
    weight: int,
    tracking: float,
    family: str = FONT_FAMILY_BRAND,
) -> TypeStyle:
    return TypeStyle(role, family, size, line_height, weight, tracking)


DISPLAY_LARGE = _style(TypeRole.DISPLAY_LARGE, 57, 64, WEIGHT_REGULAR, -0.25)
DISPLAY_MEDIUM = _style(TypeRole.DISPLAY_MEDIUM, 45, 52, WEIGHT_REGULAR, 0)
DISPLAY_SMALL = _style(TypeRole.DISPLAY_SMALL, 36, 44, WEIGHT_REGULAR, 0)
HEADLINE_LARGE = _style(TypeRole.HEADLINE_LARGE, 32, 40, WEIGHT_REGULAR, 0)
HEADLINE_MEDIUM = _style(TypeRole.HEADLINE_MEDIUM, 28, 36, WEIGHT_REGULAR, 0)
HEADLINE_SMALL = _style(TypeRole.HEADLINE_SMALL, 24, 32, WEIGHT_REGULAR, 0)
TITLE_LARGE = _style(TypeRole.TITLE_LARGE, 22, 28, WEIGHT_REGULAR, 0)
TITLE_MEDIUM = _style(TypeRole.TITLE_MEDIUM, 16, 24, WEIGHT_MEDIUM, 0.15)
TITLE_SMALL = _style(TypeRole.TITLE_SMALL, 14, 20, WEIGHT_MEDIUM, 0.1)
BODY_LARGE = _style(TypeRole.BODY_LARGE, 16, 24, WEIGHT_REGULAR, 0.5)
BODY_MEDIUM = _style(TypeRole.BODY_MEDIUM, 14, 20, WEIGHT_REGULAR, 0.25)
BODY_SMALL = _style(TypeRole.BODY_SMALL, 12, 16, WEIGHT_REGULAR, 0.4)
LABEL_LARGE = _style(TypeRole.LABEL_LARGE, 14, 20, WEIGHT_MEDIUM, 0.1)
LABEL_MEDIUM = _style(TypeRole.LABEL_MEDIUM, 12, 16, WEIGHT_MEDIUM, 0.5)
LABEL_SMALL = _style(TypeRole.LABEL_SMALL, 11, 16, WEIGHT_MEDIUM, 0.5)

TYPE_SCALE: dict[TypeRole, TypeStyle] = {
    style.role: style
    for style in (
        DISPLAY_LARGE,
        DISPLAY_MEDIUM,
        DISPLAY_SMALL,
        HEADLINE_LARGE,
        HEADLINE_MEDIUM,
        HEADLINE_SMALL,
        TITLE_LARGE,
        TITLE_MEDIUM,
        TITLE_SMALL,
        BODY_LARGE,
        BODY_MEDIUM,
        BODY_SMALL,
        LABEL_LARGE,
        LABEL_MEDIUM,
        LABEL_SMALL,
    )
}


def style_for(role: TypeRole | str) -> TypeStyle:
    """按角色或令牌名查找排版样式。

    Args:
        role: ``TypeRole`` 成员，或形如 ``"body-large"`` 的令牌名。

    Raises:
        KeyError: 角色不存在。
    """
    if isinstance(role, str):
        try:
            role = TypeRole(role)
        except ValueError as exc:
            raise KeyError(f"未知的排版角色: {role!r}") from exc
    return TYPE_SCALE[role]
