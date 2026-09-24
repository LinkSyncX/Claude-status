"""对话框。"""

from md3.components.dialogs.dialog import BasicDialog
from md3.components.dialogs.dialog import FullScreenDialog
from md3.components.dialogs.dialog import ListDialog
from md3.components.dialogs.dialog import ProgressDialog
from md3.components.dialogs.dialog import alert
from md3.components.dialogs.dialog import choose
from md3.components.dialogs.dialog import choose_many
from md3.components.dialogs.dialog import confirm
from md3.components.dialogs.dialog import prompt

__all__ = [
    "BasicDialog",
    "FullScreenDialog",
    "ListDialog",
    "ProgressDialog",
    "alert",
    "choose",
    "choose_many",
    "confirm",
    "prompt",
]
