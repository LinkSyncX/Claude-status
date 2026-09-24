"""配色方案变体。"""

import enum


class Variant(enum.Enum):
    """决定各调色板色相与色度取法的配色变体。

    ``BASELINE`` 对应 material-color-utilities 早期的 ``CorePalette.of``
    算法，可精确复现 m3.material.io 文档中的基线配色；其余变体与
    ``DynamicScheme`` 保持一致。
    """

    BASELINE = "baseline"
    TONAL_SPOT = "tonal_spot"
    VIBRANT = "vibrant"
    EXPRESSIVE = "expressive"
    NEUTRAL = "neutral"
    MONOCHROME = "monochrome"
    FRUIT_SALAD = "fruit_salad"
    RAINBOW = "rainbow"
    CONTENT = "content"
