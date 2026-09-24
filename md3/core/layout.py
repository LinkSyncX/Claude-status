"""布局辅助：把 M3 间距令牌用于 Qt 布局。"""

from __future__ import annotations

from PySide6 import QtCore
from PySide6 import QtWidgets

from md3.tokens import spacing


def margins(insets: spacing.Insets | float) -> QtCore.QMargins:
    """把 ``Insets`` 或统一值转换为 ``QMargins``。"""
    if not isinstance(insets, spacing.Insets):
        insets = spacing.Insets.all(insets)
    return QtCore.QMargins(
        round(insets.left),
        round(insets.top),
        round(insets.right),
        round(insets.bottom),
    )


def hbox(
    parent: QtWidgets.QWidget | None = None,
    gap: float = spacing.SPACE_2,
    insets: spacing.Insets | float = 0.0,
) -> QtWidgets.QHBoxLayout:
    """创建使用 M3 间距的水平布局。"""
    layout = (
        QtWidgets.QHBoxLayout(parent) if parent else QtWidgets.QHBoxLayout()
    )
    layout.setSpacing(round(gap))
    layout.setContentsMargins(margins(insets))
    return layout


def vbox(
    parent: QtWidgets.QWidget | None = None,
    gap: float = spacing.SPACE_2,
    insets: spacing.Insets | float = 0.0,
) -> QtWidgets.QVBoxLayout:
    """创建使用 M3 间距的垂直布局。"""
    layout = (
        QtWidgets.QVBoxLayout(parent) if parent else QtWidgets.QVBoxLayout()
    )
    layout.setSpacing(round(gap))
    layout.setContentsMargins(margins(insets))
    return layout


def spacer(
    width: float = 0.0, height: float = 0.0, expanding: bool = False
) -> QtWidgets.QSpacerItem:
    """创建固定或可扩展的占位项。"""
    policy = (
        QtWidgets.QSizePolicy.Policy.Expanding
        if expanding
        else QtWidgets.QSizePolicy.Policy.Fixed
    )
    return QtWidgets.QSpacerItem(round(width), round(height), policy, policy)
