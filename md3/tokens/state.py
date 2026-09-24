"""交互状态令牌（md.sys.state）。

状态层是覆盖在容器之上、使用内容色着色的半透明图层；禁用态则分别降低
容器与内容的不透明度。
"""

import enum


class InteractionState(enum.Flag):
    """组件当前可能同时处于的交互状态。"""

    NONE = 0
    HOVERED = enum.auto()
    FOCUSED = enum.auto()
    PRESSED = enum.auto()
    DRAGGED = enum.auto()
    DISABLED = enum.auto()


HOVER_STATE_LAYER_OPACITY = 0.08
FOCUS_STATE_LAYER_OPACITY = 0.10
PRESSED_STATE_LAYER_OPACITY = 0.10
DRAGGED_STATE_LAYER_OPACITY = 0.16

DISABLED_CONTAINER_OPACITY = 0.12
DISABLED_CONTENT_OPACITY = 0.38
DISABLED_OUTLINE_OPACITY = 0.12

# 键盘焦点指示环。
FOCUS_RING_WIDTH = 3.0
FOCUS_RING_OFFSET = 2.0

# 无障碍最小触控目标（dp）。
MIN_TOUCH_TARGET = 48.0


def state_layer_opacity(state: InteractionState) -> float:
    """返回组合状态下应绘制的状态层不透明度。

    多个状态同时存在时取规范中优先级最高者：dragged > pressed >
    focused > hovered。
    """
    if InteractionState.DISABLED in state:
        return 0.0
    if InteractionState.DRAGGED in state:
        return DRAGGED_STATE_LAYER_OPACITY
    if InteractionState.PRESSED in state:
        return PRESSED_STATE_LAYER_OPACITY
    if InteractionState.FOCUSED in state:
        return FOCUS_STATE_LAYER_OPACITY
    if InteractionState.HOVERED in state:
        return HOVER_STATE_LAYER_OPACITY
    return 0.0
