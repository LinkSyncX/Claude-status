"""提示：纯文字与富提示，可指定方位。"""

from md3.components.tooltips.tooltip import Placement
from md3.components.tooltips.tooltip import PlainTooltip
from md3.components.tooltips.tooltip import RichTooltip
from md3.components.tooltips.tooltip import install_plain
from md3.components.tooltips.tooltip import install_rich
from md3.components.tooltips.tooltip import position_for

__all__ = [
    "Placement",
    "PlainTooltip",
    "RichTooltip",
    "install_plain",
    "install_rich",
    "position_for",
]
