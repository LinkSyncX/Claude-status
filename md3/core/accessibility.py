"""无障碍：为自绘组件提供 ``QAccessible`` 角色、名称与状态。

Qt 只为原生控件内置了无障碍接口，自绘的 ``QWidget`` 在屏幕阅读器眼中
只是一个 "client" 区域。本模块注册一个接口工厂：凡是实现了
``accessible_role()`` 的组件都会得到 :class:`MaterialAccessible`，它把
组件自述的角色、名称、描述、取值与状态（选中 / 按下 / 展开 …）转交给
辅助技术。组件状态变化时调用 :func:`notify_state_changed` 或
:func:`notify_value_changed` 广播。

组件可实现的协议（均可选，见 :class:`AccessibleWidget`）::

    def accessible_role(self) -> QtGui.QAccessible.Role
    def accessible_name(self) -> str
    def accessible_description(self) -> str
    def accessible_value(self) -> str
    def accessible_state(self, state: QtGui.QAccessible.State) -> None
"""

from __future__ import annotations

from typing import Protocol
from typing import override
from typing import runtime_checkable

from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

Role = QtGui.QAccessible.Role
State = QtGui.QAccessible.State
Text = QtGui.QAccessible.Text


@runtime_checkable
class AccessibleWidget(Protocol):
    """自述无障碍角色的组件协议。"""

    def accessible_role(self) -> QtGui.QAccessible.Role:
        """组件的无障碍角色。"""


class MaterialAccessible(QtWidgets.QAccessibleWidget):
    """把组件自述的无障碍信息转交给 Qt 的接口实现。"""

    def __init__(self, widget: QtWidgets.QWidget) -> None:
        role = widget.accessible_role()  # type: ignore[attr-defined]
        super().__init__(widget, role, "")
        self._target = widget

    @override
    def text(self, kind: QtGui.QAccessible.Text) -> str:
        widget = self._target
        if kind == Text.Name:
            name = widget.accessibleName()
            if not name:
                name = _call(widget, "accessible_name", "")
            return name
        if kind == Text.Description:
            description = widget.accessibleDescription()
            if not description:
                description = _call(widget, "accessible_description", "")
            return description
        if kind == Text.Value:
            return _call(widget, "accessible_value", "")
        return super().text(kind)

    @override
    def state(self) -> QtGui.QAccessible.State:
        state = super().state()
        hook = getattr(self._target, "accessible_state", None)
        if callable(hook):
            hook(state)
        return state


def _call(widget: QtWidgets.QWidget, name: str, default: str) -> str:
    hook = getattr(widget, name, None)
    if callable(hook):
        value = hook()
        return "" if value is None else str(value)
    return default


def _factory(
    classname: str, obj: QtCore.QObject
) -> QtGui.QAccessibleInterface | None:
    del classname
    if isinstance(obj, QtWidgets.QWidget) and isinstance(obj, AccessibleWidget):
        return MaterialAccessible(obj)
    return None


_installed = False


def install() -> None:
    """注册接口工厂（幂等）。"""
    global _installed  # pylint: disable=global-statement
    if _installed:
        return
    _installed = True
    QtGui.QAccessible.installFactory(_factory)


def installed() -> bool:
    """是否已注册接口工厂。"""
    return _installed


def is_active() -> bool:
    """是否有辅助技术在监听（无监听时可跳过通知的构造开销）。"""
    return QtGui.QAccessible.isActive()


def notify_state_changed(widget: QtWidgets.QWidget, **flags: bool) -> None:
    """广播状态变化，``flags`` 为发生变化的状态位，如 ``checked=True``。"""
    if not _installed or not widget.isVisible():
        return
    changed = State()
    for name, value in flags.items():
        if value:
            setattr(changed, name, True)
    event = QtGui.QAccessibleStateChangeEvent(widget, changed)
    QtGui.QAccessible.updateAccessibility(event)


def notify_value_changed(widget: QtWidgets.QWidget, value: object) -> None:
    """广播取值变化（滑块、进度等）。"""
    if not _installed or not widget.isVisible():
        return
    event = QtGui.QAccessibleValueChangeEvent(widget, value)
    QtGui.QAccessible.updateAccessibility(event)


def notify_name_changed(widget: QtWidgets.QWidget) -> None:
    """广播名称变化。"""
    if not _installed or not widget.isVisible():
        return
    event = QtGui.QAccessibleEvent(widget, QtGui.QAccessible.Event.NameChanged)
    QtGui.QAccessible.updateAccessibility(event)


def interface_for(
    widget: QtWidgets.QWidget,
) -> QtGui.QAccessibleInterface | None:
    """查询组件当前的无障碍接口（测试与调试用）。"""
    return QtGui.QAccessible.queryAccessibleInterface(widget)
