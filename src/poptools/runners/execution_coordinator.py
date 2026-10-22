from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRect, QTimer, Signal
from PySide6.QtGui import QWindow

from poptools.domain.models import ExecutorKind, ToolDefinition
from poptools.infrastructure.scrcpy_controller import ScrcpyController
from poptools.runners.execution_manager import ExecutionManager


class ExecutionCoordinator(QObject):
    """Own all execution sessions, capacity policy, and reserved preset sessions."""

    output = Signal(str, str)
    started = Signal(str)
    runningChanged = Signal(str, bool)
    finished = Signal(str, int)
    capacityRequested = Signal(str, str)

    def __init__(
        self,
        execution: ExecutionManager,
        max_parallel: int,
        scrcpy: ScrcpyController | None = None,
        manager_factory: Callable[[], ExecutionManager] | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.execution = execution
        self.python_environment = execution.python_environment
        self.paths = execution.paths
        self._ordinary_limit = max(1, max_parallel - 1)
        self._scrcpy = scrcpy or ScrcpyController(self)
        self._manager_factory = manager_factory or (
            lambda: ExecutionManager(self.paths, self.python_environment)
        )
        self._executions: dict[str, ExecutionManager] = {}
        self._titles: dict[str, str] = {}
        self._execution_order: dict[str, int] = {}
        self._execution_counter = 0
        self._execution_used = False
        self._pending: tuple[ToolDefinition, dict[str, Any], str] | None = None
        self._scrcpy_tool_id = ""
        self._scrcpy_serial = ""
        self._scrcpy_display_id = 0
        self._scrcpy_restart: tuple[str, int] | None = None

        self._scrcpy.output.connect(self._on_scrcpy_output)
        self._scrcpy.started.connect(self._on_scrcpy_started)
        self._scrcpy.runningChanged.connect(self._on_scrcpy_running_changed)
        self._scrcpy.finished.connect(self._on_scrcpy_finished)

    @staticmethod
    def is_scrcpy(tool: ToolDefinition) -> bool:
        return (
            tool.executor.kind == ExecutorKind.INTERNAL
            and tool.executor.command.casefold() == "scrcpy"
        )

    def running(self, tool_id: str) -> bool:
        if tool_id and tool_id == self._scrcpy_tool_id:
            return self._scrcpy.active
        manager = self._executions.get(tool_id)
        return manager.running if manager is not None else False

    def set_ordinary_limit(self, limit: int) -> None:
        self._ordinary_limit = max(1, min(limit, 5))

    def plugin_usage_reason(self, plugin: str) -> str:
        if any(worker.active for worker in self._executions.values()):
            return "请先结束正在运行的脚本，脚本可能调用插件工具"
        if plugin == "android" and self._scrcpy.active:
            return "请先结束正在运行或启动中的投屏任务"
        return ""

    def start(self, tool: ToolDefinition, values: dict[str, Any], device_serial: str = "") -> bool:
        if getattr(self, "plugin_mutation_active", lambda: False)():
            self.output.emit(tool.id, "插件正在变更，请等待操作完成后再运行。\n")
            return False
        if self.is_scrcpy(tool):
            if self._scrcpy.active:
                self.output.emit(tool.id, "投屏正在运行，请先停止。\n")
                return False
            self._scrcpy_tool_id = tool.id
            try:
                raw_display = str(values.get("displayId", 0))
                if not raw_display.isascii() or not raw_display.isdecimal():
                    raise ValueError
                display_id = int(raw_display)
                if display_id > 2147483647:
                    raise ValueError
            except (ValueError, TypeError):
                self._scrcpy_tool_id = ""
                self.output.emit(tool.id, "displayId 必须是非负整数。\n")
                return False
            self._scrcpy_serial = device_serial
            self._scrcpy_display_id = display_id
            accepted = self._scrcpy.start(device_serial, display_id)
            if not accepted:
                self._scrcpy_tool_id = ""
            else:
                self.runningChanged.emit(tool.id, True)
            return accepted
        return self._start_ordinary(tool, values)

    def stop(self, tool_id: str) -> None:
        if tool_id and tool_id == self._scrcpy_tool_id:
            self._scrcpy_restart = None
            self._scrcpy.stop()
            return
        manager = self._executions.get(tool_id)
        if manager is not None:
            manager.stop()

    def switch_scrcpy_display(self, serial: str, display_id: int) -> bool:
        if not isinstance(display_id, int) or not 0 <= display_id <= 2147483647:
            return False
        if (not self._scrcpy.active or serial != self._scrcpy_serial
                or getattr(self, "plugin_mutation_active", lambda: False)()):
            return False
        if self._scrcpy_restart is not None:
            self._scrcpy_restart = (serial, display_id)
            return True
        if display_id == self._scrcpy_display_id:
            return True
        self._scrcpy_restart = (serial, display_id)
        self.output.emit(self._scrcpy_tool_id, f"正在切换到屏幕 {display_id}…\n")
        self._scrcpy.stop()
        return True

    def confirm_replacement(self) -> None:
        pending = self._pending
        if pending is None:
            return
        tool, values, victim_id = pending
        manager = self._executions.get(victim_id)
        if manager is None:
            self._pending = None
            self._start_ordinary(tool, values, enforce_capacity=False)
            return
        victim_title = self._titles.get(victim_id, victim_id)
        self.output.emit(tool.id, f"正在停止最早运行的功能“{victim_title}”…\n")
        manager.stop()

    def cancel_replacement(self) -> None:
        self._pending = None

    def attach_window(self, window: QWindow) -> None:
        self._scrcpy.attach_window(window)

    def set_scrcpy_geometry(self, rect: QRect, visible: bool) -> None:
        self._scrcpy.set_geometry(rect, visible)

    def _start_ordinary(
        self,
        tool: ToolDefinition,
        values: dict[str, Any],
        *,
        enforce_capacity: bool = True,
    ) -> bool:
        current = self._executions.get(tool.id)
        if self._pending is not None:
            self.output.emit(tool.id, "请先处理当前的运行名额确认。\n")
            return False
        if current is not None:
            self.output.emit(tool.id, f"“{tool.title}”正在运行，请先停止该功能。\n")
            return False

        running_ids = list(self._executions)
        if enforce_capacity and len(running_ids) >= self._ordinary_limit:
            victim_id = min(running_ids, key=lambda key: self._execution_order.get(key, 0))
            self._pending = (tool, dict(values), victim_id)
            self.capacityRequested.emit(self._titles.get(victim_id, victim_id), tool.title)
            return False

        if not self._execution_used:
            manager = self.execution
            self._execution_used = True
        else:
            manager = self._manager_factory()
        manager.setParent(self)
        manager.output.connect(lambda text, tool_id=tool.id: self.output.emit(tool_id, text))
        manager.started.connect(lambda tool_id=tool.id: self.started.emit(tool_id))
        manager.runningChanged.connect(
            lambda running, tool_id=tool.id: self.runningChanged.emit(tool_id, running)
        )
        manager.finished.connect(
            lambda exit_code, tool_id=tool.id, owner=manager: self._on_execution_finished(
                tool_id, owner, exit_code
            )
        )
        self._executions[tool.id] = manager
        self._titles[tool.id] = tool.title
        self._execution_counter += 1
        self._execution_order[tool.id] = self._execution_counter
        accepted = manager.start(tool, values)
        if not accepted:
            self._remove_manager(tool.id, manager)
        return accepted

    def _on_execution_finished(
        self, tool_id: str, manager: ExecutionManager, exit_code: int
    ) -> None:
        self._remove_manager(tool_id, manager)
        pending = self._pending
        if pending is not None and pending[2] == tool_id:
            pending_tool, pending_values, _ = pending
            self._pending = None
            QTimer.singleShot(
                0,
                lambda: self._start_ordinary(
                    pending_tool, pending_values, enforce_capacity=False
                ),
            )
        self.finished.emit(tool_id, exit_code)

    def _remove_manager(self, tool_id: str, manager: ExecutionManager) -> None:
        if self._executions.get(tool_id) is manager:
            self._executions.pop(tool_id, None)
        self._titles.pop(tool_id, None)
        self._execution_order.pop(tool_id, None)
        if manager is not self.execution:
            manager.deleteLater()

    def _on_scrcpy_output(self, text: str) -> None:
        self.output.emit(self._scrcpy_tool_id, text)

    def _on_scrcpy_started(self) -> None:
        self.started.emit(self._scrcpy_tool_id)

    def _on_scrcpy_running_changed(self, running: bool) -> None:
        self.runningChanged.emit(self._scrcpy_tool_id, running)

    def _on_scrcpy_finished(self, exit_code: int) -> None:
        tool_id = self._scrcpy_tool_id
        pending = self._scrcpy_restart
        self._scrcpy_restart = None
        if pending is not None:
            self._scrcpy_serial, self._scrcpy_display_id = pending
            if self._scrcpy.start(*pending):
                self.runningChanged.emit(tool_id, True)
                return
            exit_code = -1
            self.output.emit(tool_id, "切换屏幕失败，请检查设备连接和 displayId。\n")
        self._scrcpy_tool_id = ""
        self.finished.emit(tool_id, exit_code)
