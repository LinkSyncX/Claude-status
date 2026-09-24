"""后台任务：在工作线程中执行函数，完成后在主线程回调。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6 import QtCore


class _Worker(QtCore.QThread):
    succeeded = QtCore.Signal(object)
    failed = QtCore.Signal(object)

    def __init__(self, function: Callable[[], Any]) -> None:
        super().__init__()
        self._function = function

    def run(self) -> None:  # noqa: D102
        try:
            result = self._function()
        except Exception as exc:  # pylint: disable=broad-except
            self.failed.emit(exc)
            return
        self.succeeded.emit(result)


class Task(QtCore.QObject):
    """在工作线程中运行 ``function``。

    结果通过本对象（位于主线程）的槽转发，因此 ``on_success`` /
    ``on_failure`` 总在主线程执行，可以安全地操作界面。

    Args:
        function: 要执行的函数（不能操作界面）。
        on_success: 成功回调，参数为返回值。
        on_failure: 失败回调，参数为异常。
        parent: 父对象。
    """

    _running: set[Task] = set()

    def __init__(
        self,
        function: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        on_failure: Callable[[BaseException], None] | None = None,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_success = on_success
        self._on_failure = on_failure
        self._worker = _Worker(function)
        self._worker.succeeded.connect(self._handle_success)
        self._worker.failed.connect(self._handle_failure)
        self._worker.finished.connect(self._cleanup)

    def start(self) -> Task:
        """开始执行。"""
        Task._running.add(self)
        self._worker.start()
        return self

    @QtCore.Slot(object)
    def _handle_success(self, result: Any) -> None:
        if self._on_success is not None:
            self._on_success(result)

    @QtCore.Slot(object)
    def _handle_failure(self, error: BaseException) -> None:
        if self._on_failure is not None:
            self._on_failure(error)

    @QtCore.Slot()
    def _cleanup(self) -> None:
        Task._running.discard(self)
        self._worker.deleteLater()
        self.deleteLater()

    @classmethod
    def wait_all(cls, timeout_ms: int = 5000) -> None:
        """等待所有进行中的任务结束（退出程序前调用）。"""
        for task in list(cls._running):
            task._worker.wait(timeout_ms)  # pylint: disable=protected-access


def run(
    function: Callable[[], Any],
    on_success: Callable[[Any], None] | None = None,
    on_failure: Callable[[BaseException], None] | None = None,
    parent: QtCore.QObject | None = None,
) -> Task:
    """创建并启动任务。"""
    return Task(function, on_success, on_failure, parent).start()
