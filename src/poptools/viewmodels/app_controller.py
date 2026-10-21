from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from pypinyin import lazy_pinyin
from PySide6.QtCore import (
    Property,
    QObject,
    QRect,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtWidgets import QFileDialog

from poptools.domain.adb_detection import AdbAnalysis, analyze_adb
from poptools.domain.models import (
    AndroidDeviceMode,
    ExecutorDefinition,
    ExecutorKind,
    ParameterKind,
    ToolDefinition,
    ToolSection,
)
from poptools.infrastructure.background_process import BackgroundProcess
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.custom_tool_transfer import (
    decode_custom_tool,
    encode_custom_tool,
)
from poptools.infrastructure.python_doctor import (
    PythonDoctor,
    PythonDoctorResult,
    pip_package_names,
)
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import package_root, resource_path
from poptools.runners import ExecutionCoordinator
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.scrcpy_display_controller import ScrcpyDisplayController
from poptools.viewmodels.tool_list_model import ToolListModel

SECTION_TITLES = {
    ToolSection.PRESET: "预设",
    ToolSection.CUSTOM: "客制",
}

CONSOLE_REFRESH_INTERVAL_MS = 50
CONSOLE_MAX_CHARS = 200_000
CONSOLE_RETAINED_CHARS = 150_000


def _local_path_from_url(url: str) -> str:
    dropped_url = QUrl(url)
    if not dropped_url.isLocalFile():
        return ""
    return dropped_url.toLocalFile()


def _file_picker_start_directory(value: str) -> str:
    raw_path = value.strip()
    if raw_path.startswith("file:"):
        raw_path = _local_path_from_url(raw_path)
    if raw_path:
        candidate = Path(raw_path).expanduser()
        if candidate.is_dir():
            return str(candidate)
        if candidate.is_file() or candidate.parent.is_dir():
            return str(candidate.parent)
    downloads = Path.home() / "Downloads"
    return str(downloads if downloads.is_dir() else Path.home())


class AppController(QObject):
    sectionChanged = Signal()
    sectionTitleChanged = Signal()
    selectedToolChanged = Signal()
    selectedToolDataChanged = Signal()
    consoleTextChanged = Signal()
    runningChanged = Signal()
    statusTextChanged = Signal()
    pythonDoctorWarning = Signal(str)
    pythonDoctorInstallSuggestion = Signal(str)
    pythonDependencyInstallFinished = Signal(bool, str)
    executionCapacityRequested = Signal(str, str)
    toolSortModeChanged = Signal()
    recentToolDialogRequested = Signal(str)
    customToolsChanged = Signal()
    toolConsoleChanged = Signal(str)
    toolStatusChanged = Signal(str)
    commandSaveFailed = Signal(str)

    def __init__(
        self,
        registry: ToolRegistry,
        execution_coordinator: ExecutionCoordinator,
        config_store: ConfigStore,
        android_controller: AndroidController,
        python_doctor: PythonDoctor | None = None,
    ) -> None:
        super().__init__()
        self.selectedToolChanged.connect(self.selectedToolDataChanged)
        self.registry = registry
        self.execution_coordinator = execution_coordinator
        self.execution = execution_coordinator.execution
        self.config_store = config_store
        self._section = ToolSection.CUSTOM
        self._selected: ToolDefinition | None = None
        self._section_selections: dict[str, str] = {
            ToolSection.CUSTOM.value: "",
            ToolSection.PRESET.value: "",
        }
        self._console_texts = {"": "14:20:15  泡泡工具箱 已就绪\n"}
        self._tool_statuses: dict[str, str] = {}
        self._pending_console_chunks: dict[str, list[str]] = {}
        self._console_refresh_timer = QTimer(self)
        self._console_refresh_timer.setSingleShot(True)
        self._console_refresh_timer.setInterval(CONSOLE_REFRESH_INTERVAL_MS)
        self._console_refresh_timer.timeout.connect(self._flush_console)
        self._status_text = "就绪"
        self._tool_sort_mode = config_store.tool_sort_mode()
        self._tools_model = ToolListModel()
        self._tools_ready = False
        self.android_controller = android_controller
        self._scrcpy_displays = ScrcpyDisplayController(
            android_controller, execution_coordinator, self
        )
        self._python_doctor = python_doctor or PythonDoctor()
        self._python_doctor_command = ""
        self._python_doctor_process: BackgroundProcess | None = None
        self._python_package_install: BackgroundProcess | None = None
        self._pending_import_tool: ToolDefinition | None = None
        self.execution_coordinator.output.connect(self._queue_console)
        self.execution_coordinator.started.connect(self._on_execution_started)
        self.execution_coordinator.runningChanged.connect(self._on_execution_running_changed)
        self.execution_coordinator.finished.connect(self._on_execution_finished)
        self.execution_coordinator.capacityRequested.connect(self.executionCapacityRequested)
        self._refresh(select_first=True)
        self._tools_ready = True
        self._analysis_timer = QTimer(self)
        self._analysis_timer.setInterval(2000)
        self._last_analysis: AdbAnalysis | None = None
        self._analysis_timer.timeout.connect(self._refresh_adb_analysis)
        self._analysis_timer.start()

    @Property(QObject, constant=True)
    def toolsModel(self) -> QObject:
        return self._tools_model

    @Property(bool, constant=True)
    def toolsReady(self) -> bool:
        return self._tools_ready

    @Property(str, notify=sectionChanged)
    def section(self) -> str:
        return self._section.value

    @Property(str, notify=sectionTitleChanged)
    def sectionTitle(self) -> str:
        return SECTION_TITLES[self._section]

    @Property("QVariantMap", notify=selectedToolDataChanged)
    def selectedTool(self) -> dict[str, Any]:
        return self.tool_data(self._selected)

    def tool_data(self, tool: ToolDefinition | None) -> dict[str, Any]:
        if tool is None:
            return {}
        data = tool.to_qml()
        analysis = self._analyze_tool(tool)
        data["parameters"] = [
            {**parameter, "kind": "text"}
            if parameter["kind"] == ParameterKind.ANDROID_DEVICE.value else parameter
            for parameter in data["parameters"]
            if parameter["kind"] != ParameterKind.ANDROID_DEVICE.value or not analysis.uses_adb
        ]
        data["uses_android_device"] = analysis.uses_adb
        data["requires_android_device"] = analysis.needs_device
        data["android_explicit_target"] = analysis.explicit_target
        data["android_detection_reason"] = analysis.reason
        data["workspace"] = (
            "scrcpy"
            if self.execution_coordinator.is_scrcpy(tool)
            else "preset"
            if tool.executor.kind == ExecutorKind.INTERNAL
            else "command"
        )
        return data

    @Slot(str, result=QObject)
    def createToolSession(self, tool_id: str) -> QObject | None:
        if self.registry.get(tool_id) is None:
            return None
        from poptools.viewmodels.tool_session_controller import ToolSessionController

        return ToolSessionController(self, tool_id)

    @Property(str, notify=consoleTextChanged)
    def consoleText(self) -> str:
        return self._console_texts.get("", "")

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        if self._selected is None:
            return False
        return self.execution_coordinator.running(self._selected.id)

    @Property(str, notify=statusTextChanged)
    def statusText(self) -> str:
        return self._status_text

    @Property(str, constant=True)
    def pythonEnvironmentDirectory(self) -> str:
        executable = self.execution.python_environment.executable()
        if not executable:
            return ""
        path = Path(executable)
        return str(path.parent.parent if path.parent.name.casefold() == "scripts" else path.parent)

    @Property(str, notify=toolSortModeChanged)
    def toolSortMode(self) -> str:
        return self._tool_sort_mode

    @Property(str, notify=toolSortModeChanged)
    def toolSortModeLabel(self) -> str:
        return {
            "added_time": "按添加时间",
            "name": "按名称",
            "usage": "按使用频率",
            "custom": "自定义排序",
        }[self._tool_sort_mode]

    @Property("QVariantList", constant=True)
    def recentTools(self) -> list[dict[str, str]]:
        return self._recent_tool_items()

    def getRecentTools(self) -> list[dict[str, str]]:
        """Return recent tools list for use by SystemTrayController (non-QML)."""
        return self._recent_tool_items()

    def _recent_tool_items(self) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for tool_id in self.config_store.recent_tools():
            tool = self.registry.get(tool_id)
            if tool is not None and tool.section == ToolSection.CUSTOM:
                result.append({
                    "toolId": tool.id,
                    "title": tool.title,
                    "iconName": tool.presentation.icon or "extension",
                })
        return result

    @Slot(str)
    def openRecentToolFromTray(self, tool_id: str) -> None:
        self.open_custom_tool_shortcut(tool_id)

    def open_custom_tool_shortcut(self, tool_id: str) -> bool | None:
        tool = self.registry.get(tool_id)
        if tool is None or tool.section != ToolSection.CUSTOM:
            return None
        self.selectTool(tool_id)
        if self._selected is None or self._selected.id != tool_id:
            return None

        parameters = self._selected.parameters
        if not parameters and not self._analyze_tool(self._selected).uses_adb:
            return self.runSelected({})

        self.recentToolDialogRequested.emit(tool_id)
        return None

    def getPresetTools(self) -> list[dict[str, str]]:
        """Return tray-accessible preset tools, excluding screen mirroring."""
        return [
            {
                "toolId": tool.id,
                "title": tool.title,
                "iconName": tool.presentation.icon or "extension",
            }
            for tool in self.registry.for_section(ToolSection.PRESET)
            if not self.execution_coordinator.is_scrcpy(tool)
        ]

    @Slot(str)
    def openPresetToolFromTray(self, tool_id: str) -> None:
        tool = self.registry.get(tool_id)
        if (
            tool is None
            or tool.section != ToolSection.PRESET
            or self.execution_coordinator.is_scrcpy(tool)
        ):
            return
        self.selectTool(tool_id)
        self.recentToolDialogRequested.emit(tool_id)

    @Slot(str)
    def navigate(self, section: str) -> None:
        target = ToolSection(section)
        if target == self._section:
            return
        if self._selected is not None and self._selected.section == self._section:
            self._section_selections[self._section.value] = self._selected.id
        self._section = target
        self.sectionChanged.emit()
        self.sectionTitleChanged.emit()
        remembered_id = self._section_selections.get(target.value, "")
        self._refresh(select_first=not remembered_id, select_id=remembered_id)

    @Slot(str)
    def selectTool(self, tool_id: str) -> None:
        tool = self.registry.get(tool_id)
        if tool is None:
            return
        previous_id = self._selected.id if self._selected is not None else ""
        previous = self.registry.get(previous_id) if previous_id else None
        if (
            previous is not None
            and self.execution_coordinator.is_scrcpy(previous)
            and not self.execution_coordinator.is_scrcpy(tool)
        ):
            self._hide_scrcpy_window()
        self._selected = tool
        if tool.section in (ToolSection.CUSTOM, ToolSection.PRESET):
            self._section_selections[tool.section.value] = tool.id
        self._tools_model.select(tool_id)
        self.selectedToolChanged.emit()
        self.consoleTextChanged.emit()
        self.runningChanged.emit()
        self._status_text = "运行中" if self.running else "就绪"
        self.statusTextChanged.emit()

    @Slot()
    def clearToolSelection(self) -> None:
        if self._selected is None:
            return
        if self.execution_coordinator.is_scrcpy(self._selected):
            self._hide_scrcpy_window()
        self._selected = None
        self._tools_model.select("")
        self.selectedToolChanged.emit()
        self.consoleTextChanged.emit()
        self.runningChanged.emit()
        self._status_text = "就绪"
        self.statusTextChanged.emit()

    @Slot(str, result=bool)
    def setToolSortMode(self, mode: str) -> bool:
        try:
            self.config_store.set_tool_sort_mode(mode)
        except (OSError, ValueError):
            return False
        if mode == self._tool_sort_mode:
            return True
        self._tool_sort_mode = mode
        self.toolSortModeChanged.emit()
        selected_id = self._selected.id if self._selected is not None else ""
        self._refresh(select_id=selected_id)
        return True

    @Slot(str)
    def setToolSearchQuery(self, query: str) -> None:
        self._tools_model.set_filter(query)

    @Slot(str, int, result=bool)
    def moveTool(self, tool_id: str, target_index: int) -> bool:
        if self._section != ToolSection.CUSTOM or self._tool_sort_mode != "custom":
            return False
        tools = self._sorted_tools(self.registry.for_section(self._section))
        source_index = next((i for i, tool in enumerate(tools) if tool.id == tool_id), -1)
        if source_index < 0 or not tools:
            return False
        target_index = max(0, min(target_index, len(tools) - 1))
        moved = tools.pop(source_index)
        tools.insert(target_index, moved)
        try:
            self.config_store.set_tool_order([tool.id for tool in tools])
        except OSError:
            return False
        self._refresh(select_id=tool_id)
        return True

    def attach_window(self, window: QWindow) -> None:
        self.execution_coordinator.attach_window(window)

    @Property(QObject, constant=True)
    def scrcpyDisplays(self) -> QObject:
        return self._scrcpy_displays

    @Slot("QVariantMap", result=bool)
    def runSelected(self, values: dict[str, Any]) -> bool:
        if self._selected is None:
            return False
        if self.execution_coordinator.is_scrcpy(self._selected):
            values = {**values, "displayId": self._scrcpy_displays.selectedId}
        return self.run_tool(self._selected.id, values)

    def set_tool_status(self, tool_id: str, status: str) -> None:
        self._tool_statuses[tool_id] = status
        self.toolStatusChanged.emit(tool_id)
        if self._selected is not None and self._selected.id == tool_id:
            self._status_text = status
            self.statusTextChanged.emit()

    def run_tool(self, tool_id: str, values: dict[str, Any]) -> bool:
        tool = self.registry.get(tool_id)
        if tool is None:
            return False
        analysis = self._analyze_tool(tool)
        selected_device = (
            self.android_controller.available_device_for_tool(tool.id)
            if analysis.uses_adb else ""
        )
        if analysis.needs_device and not selected_device:
            self.append_tool_console(
                tool.id, "请在当前脚本的“目标设备”中选择已连接的 Android 设备。\n",
            )
            self.set_tool_status(tool.id, "等待 Android 设备")
            return False

        run_values = dict(values)
        if self.execution_coordinator.is_scrcpy(tool):
            run_values.setdefault("displayId", self._scrcpy_displays.selectedId)
        run_values.pop("__android_device__", None)
        if selected_device:
            for parameter in tool.parameters:
                if parameter.kind == ParameterKind.ANDROID_DEVICE:
                    run_values[parameter.id] = selected_device
            run_values["__android_device__"] = selected_device
        self.set_tool_status(tool.id, "正在启动")
        started = self.execution_coordinator.start(
            tool,
            run_values,
            selected_device,
        )
        if not started:
            self.set_tool_status(tool.id, "就绪")
        return started

    @Slot()
    def stopExecution(self) -> None:
        if self._selected is None:
            return
        self.execution_coordinator.stop(self._selected.id)

    @Slot(int, int, int, int, bool)
    def updateScrcpyGeometry(self, x: int, y: int, width: int, height: int, visible: bool) -> None:
        self.execution_coordinator.set_scrcpy_geometry(QRect(x, y, width, height), visible)

    def _hide_scrcpy_window(self) -> None:
        self.execution_coordinator.set_scrcpy_geometry(QRect(), False)

    @Slot()
    def clearConsole(self) -> None:
        self._pending_console_chunks.pop("", None)
        if not self._pending_console_chunks:
            self._console_refresh_timer.stop()
        self._console_texts[""] = ""
        self.consoleTextChanged.emit()

    @Slot(str)
    def appendConsoleMessage(self, text: str) -> None:
        self._append_console(text)

    @Slot()
    def reloadImportedScripts(self) -> None:
        selected_id = self._selected.id if self._selected is not None else ""
        self.registry.reload()
        self._refresh(
            select_id=selected_id,
            select_first=self._section != ToolSection.CUSTOM and not bool(selected_id),
        )
        if self._selected is None and self._section != ToolSection.CUSTOM:
            self._refresh(select_first=True)

    @Slot(str, str, str, str, result=bool)
    @Slot(str, str, str, str, str, result=bool)
    @Slot(str, str, str, str, str, str, result=bool)
    def saveSelected(
        self, title: str, description: str, kind: str, command: str, icon: str = "",
        android_device_mode: str | None = None,
    ) -> bool:
        if (
            self._selected is None
            or (self._selected.section != ToolSection.CUSTOM and not self._selected.editable)
            or self.running
        ):
            self.commandSaveFailed.emit("当前脚本不可编辑或正在运行，请停止运行后重试。")
            return False
        try:
            self.registry.update_tool(
                self._selected.id,
                title=title,
                description=description,
                kind=ExecutorKind(kind),
                command=command,
                args=[],
                icon=icon or None,
                android_device_mode=android_device_mode,
            )
            selected_id = self._selected.id
            self._refresh(select_id=selected_id)
            self._append_console("工具修改已保存到本地配置。\n")
            if kind == ExecutorKind.PYTHON.value:
                self._run_python_doctor(command)
            return True
        except Exception as exc:
            self._append_console(f"保存失败：{exc}\n")
            self.commandSaveFailed.emit(f"保存失败：{exc}")
            return False

    @Slot(str, str, result=bool)
    def setParameterDefault(self, parameter_id: str, default: str) -> bool:
        if (
            self._selected is None
            or self.running
        ):
            return False
        try:
            selected_id = self._selected.id
            # Do not rebuild the parameter form: other fields may contain unsaved input.
            self._selected = self.registry.set_parameter_default(selected_id, parameter_id, default)
            self._append_console(f"已更新参数“{parameter_id}”的默认值。\n")
            return True
        except (KeyError, OSError, ValueError) as exc:
            self._append_console(f"默认值保存失败：{exc}\n")
            return False

    @Slot(str, result=str)
    def localPathFromUrl(self, url: str) -> str:
        """Convert a dropped local-file URL into the native path shown to users."""
        return _local_path_from_url(url)

    @Slot(str, result=str)
    def chooseParameterFile(self, current_path: str) -> str:
        selected_path, _ = QFileDialog.getOpenFileName(
            None,
            "选择文件",
            _file_picker_start_directory(current_path),
            "所有文件 (*)",
        )
        return selected_path

    @Slot(str, result=str)
    def chooseParameterDirectory(self, current_path: str) -> str:
        return QFileDialog.getExistingDirectory(
            None,
            "选择文件夹",
            _file_picker_start_directory(current_path),
        )

    @Slot(str, str, str, str, result=bool)
    @Slot(str, str, str, str, str, result=bool)
    @Slot(str, str, str, str, str, str, result=bool)
    def createCommand(
        self,
        title: str,
        description: str,
        kind: str,
        command: str,
        icon: str = "terminal",
        android_device_mode: str = "auto",
    ) -> bool:
        try:
            tool = self.registry.create_custom(
                title=title,
                description=description,
                kind=ExecutorKind(kind),
                command=command,
                icon=icon,
                android_device_mode=android_device_mode,
            )
            if self._section != ToolSection.CUSTOM:
                self._section = ToolSection.CUSTOM
                self.sectionChanged.emit()
                self.sectionTitleChanged.emit()
            self._refresh(select_id=tool.id)
            self._append_console("自定义命令已保存到客制。\n")
            if tool.executor.kind == ExecutorKind.PYTHON:
                self._run_python_doctor(command)
            return True
        except Exception as exc:
            self._append_console(f"新建失败：{exc}\n")
            self.commandSaveFailed.emit(f"新建失败：{exc}")
            return False

    @Slot(result=bool)
    def exportSelectedScriptToClipboard(self) -> bool:
        tool = self._selected
        if tool is None or tool.section != ToolSection.CUSTOM:
            return False
        try:
            QGuiApplication.clipboard().setText(encode_custom_tool(tool))
            self._append_console(f"已将客制脚本“{tool.title}”复制到剪贴板。\n")
            return True
        except Exception as exc:
            self._append_console(f"脚本分享失败：{exc}\n")
            return False

    @Slot(result="QVariantMap")
    def importScriptFromClipboard(self) -> dict[str, Any]:
        self._pending_import_tool = None
        try:
            tool = decode_custom_tool(QGuiApplication.clipboard().text())
        except Exception as exc:
            message = str(exc)
            self._append_console(f"脚本导入失败：{message}\n")
            return {"status": "error", "message": message}

        existing = self.registry.get(tool.id)
        if existing is not None:
            if existing.section != ToolSection.CUSTOM:
                message = "脚本 ID 与内置功能冲突，无法导入"
                self._append_console(f"脚本导入失败：{message}\n")
                return {"status": "error", "message": message}
            self._pending_import_tool = tool
            return {
                "status": "duplicate",
                "toolId": tool.id,
                "title": tool.title,
                "existingTitle": existing.title,
            }
        return self._finish_script_import(tool, replaced=False)

    @Slot(result="QVariantMap")
    def confirmScriptImportReplacement(self) -> dict[str, Any]:
        tool = self._pending_import_tool
        self._pending_import_tool = None
        if tool is None:
            return {"status": "error", "message": "没有等待替换的脚本"}
        if self.execution_coordinator.running(tool.id):
            message = "该脚本正在运行，请停止后再替换"
            self._append_console(f"脚本导入失败：{message}\n")
            return {"status": "error", "message": message}
        return self._finish_script_import(tool, replaced=True)

    @Slot()
    def cancelScriptImportReplacement(self) -> None:
        self._pending_import_tool = None

    def _finish_script_import(
        self, tool: ToolDefinition, *, replaced: bool
    ) -> dict[str, Any]:
        try:
            imported = self.registry.import_custom(tool)
            selected_id = self._selected.id if self._selected is not None else ""
            self._refresh(select_id=selected_id)
            action = "替换" if replaced else "导入"
            self._append_console(f"已{action}客制脚本“{imported.title}”。\n")
            return {
                "status": "replaced" if replaced else "imported",
                "toolId": imported.id,
                "title": imported.title,
            }
        except Exception as exc:
            message = str(exc)
            self._append_console(f"脚本导入失败：{message}\n")
            return {"status": "error", "message": message}

    @Slot(result=bool)
    def checkSelectedPythonDependencies(self) -> bool:
        if self._selected is None or self._selected.executor.kind != ExecutorKind.PYTHON:
            return False
        return self._run_python_doctor(self._selected.executor.command)

    def _run_python_doctor(self, command: str) -> bool:
        if getattr(self, "plugin_mutation_active", lambda: False)():
            self.pythonDoctorWarning.emit("插件正在变更，请等待操作完成后再检查依赖。")
            return False
        if self._python_doctor_process is not None:
            self._append_console("Python Doctor：正在检查依赖，请稍候。\n")
            return False
        self._python_doctor_command = command
        plan = self._python_doctor.prepare(command)
        if plan.immediate_result is not None:
            self._report_python_doctor_result(plan.immediate_result)
            return True
        executable = self.execution.python_environment.executable()
        if not executable:
            self._report_python_doctor_result(
                PythonDoctorResult(
                    checked_modules=plan.checked_modules,
                    environment_error="Python 插件不可用，请在设置的插件管理中安装或修复",
                )
            )
            return True
        if not plan.modules_to_check:
            self._report_python_doctor_result(
                PythonDoctorResult(checked_modules=plan.checked_modules),
                executable,
            )
            return True

        process = BackgroundProcess(self)
        self._python_doctor_process = process
        stdout = bytearray()
        stderr = bytearray()
        errors: list[str] = []
        timed_out = [False]
        timeout = QTimer(process)
        timeout.setSingleShot(True)

        def stop_on_timeout() -> None:
            timed_out[0] = True
            process.kill()

        def finish(exit_code: int) -> None:
            self._python_doctor_process = None
            timeout.stop()
            if timed_out[0]:
                result = PythonDoctorResult(
                    checked_modules=plan.checked_modules,
                    environment_error="依赖检查超时",
                )
            else:
                error_text = stderr.decode("utf-8", "replace")
                if errors:
                    error_text = "\n".join([error_text, *errors]).strip()
                result = self._python_doctor.complete_probe(
                    plan,
                    exit_code,
                    stdout.decode("utf-8", "replace"),
                    error_text,
                )
            self._report_python_doctor_result(result, executable)
            process.deleteLater()

        process.stdoutReady.connect(stdout.extend)
        process.stderrReady.connect(stderr.extend)
        process.errorOccurred.connect(errors.append)
        process.finished.connect(finish)
        timeout.timeout.connect(stop_on_timeout)
        self._append_console("Python Doctor：正在异步检查依赖…\n")
        started = process.start(
            executable,
            ["-c", self._python_doctor.probe_source(), *plan.modules_to_check],
        )
        timeout.start(20_000)
        return started

    def _report_python_doctor_result(
        self,
        result: PythonDoctorResult,
        executable: str | None = None,
    ) -> None:
        executable = executable or self.execution.python_environment.executable()
        if result.environment_error:
            message = f"Python Doctor 无法检查所选环境：{result.environment_error}"
            self._append_console(f"{message}\n")
            self.pythonDoctorWarning.emit(
                f"Python 环境无法完成检查。\n\n{result.environment_error}\n\n"
                "请确认应用专属 Python 环境已准备完成。"
            )
        elif result.missing_modules:
            modules = "、".join(result.missing_modules)
            package_names = " ".join(pip_package_names(result.missing_modules))
            install_command = f'"{executable}" -m pip install {package_names}'
            message = f"Python Doctor 发现缺失依赖：{modules}"
            self._append_console(f"{message}\n> {install_command}\n")
            self.pythonDoctorWarning.emit(
                f"当前 Python 环境缺少以下依赖模块：{modules}\n\n"
                "是否确认使用应用内 Python 环境安装？"
            )
            self.pythonDoctorInstallSuggestion.emit(package_names)
        elif result.syntax_error:
            message = f"Python Doctor 无法完成检查，脚本存在语法错误：{result.syntax_error}"
            self._append_console(f"{message}\n")
            self.pythonDoctorWarning.emit(
                f"脚本已创建，但 Python Doctor 无法完成依赖检查。\n\n{result.syntax_error}"
            )
        else:
            self._append_console("Python Doctor：未发现缺失依赖。\n")

    @Slot(str, result=bool)
    def installPythonDependencies(self, package_text: str) -> bool:
        """Install packages into the interpreter currently used by user scripts."""
        if getattr(self, "plugin_mutation_active", lambda: False)():
            self.pythonDependencyInstallFinished.emit(False, "插件正在变更，请稍后重试。")
            return False
        if self._python_package_install is not None:
            return False
        executable = self.execution.python_environment.executable()
        if not executable:
            message = "Python 插件不可用，请先在设置的插件管理中安装。"
            self._append_console(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False
        try:
            packages = shlex.split(package_text.strip(), posix=False)
        except ValueError as exc:
            message = f"包名格式无效：{exc}"
            self._append_console(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False
        packages = [package.strip().strip('"') for package in packages if package.strip()]
        if not packages or any(package.startswith("-") for package in packages):
            message = "请填写有效的 pip 包名，不要填写命令选项。"
            self._append_console(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False

        pip_ready, pip_error = self.execution.python_environment.ensure_pip()
        if not pip_ready:
            message = f"应用内 pip 不可用：{pip_error}"
            self._append_console(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False

        process = BackgroundProcess(self)
        errors: list[str] = []
        self._python_package_install = process

        def append_output(payload: bytes) -> None:
            text = payload.decode("utf-8", "replace")
            if text:
                self._append_console(text)

        def finish(exit_code: int) -> None:
            self._python_package_install = None
            process.deleteLater()
            if exit_code == 0:
                message = "依赖安装完成，正在重新检查 Python 脚本依赖…"
                self._append_console(f"{message}\n")
                self.pythonDependencyInstallFinished.emit(True, message)
                if self._python_doctor_command:
                    self._run_python_doctor(self._python_doctor_command)
            else:
                detail = "\n".join(errors).strip() or f"退出码 {exit_code}"
                message = f"安装失败：{detail}"
                self._append_console(f"Python 依赖安装失败：{message}\n")
                self.pythonDependencyInstallFinished.emit(False, message)

        process.stdoutReady.connect(append_output)
        process.stderrReady.connect(append_output)
        process.errorOccurred.connect(errors.append)
        process.finished.connect(finish)
        self._append_console(f"> {executable} -m pip install {' '.join(packages)}\n")
        started = process.start(executable, ["-m", "pip", "install", *packages])
        if not started:
            self._python_package_install = None
            process.deleteLater()
            return False
        return True

    @Slot(result=bool)
    def deleteSelected(self) -> bool:
        if self._selected is None or self._selected.section != ToolSection.CUSTOM or self.running:
            return False
        title = self._selected.title
        if not self.registry.delete(self._selected.id):
            return False
        self.android_controller.forget_tool(self._selected.id)
        self._selected = None
        self._refresh(select_first=False)
        self._append_console(f"已删除本地命令：{title}\n")
        return True

    def _refresh(
        self,
        *,
        select_first: bool = False,
        select_id: str = "",
        notify_selected: bool = True,
    ) -> None:
        tools = self._sorted_tools(self.registry.for_section(self._section))
        running_ids = {tool.id for tool in tools if self.execution_coordinator.running(tool.id)}
        if self._section == ToolSection.CUSTOM and running_ids:
            tools = sorted(tools, key=lambda tool: tool.id not in running_ids)
        target_id = select_id
        if not target_id and self._selected and self._selected.section == self._section:
            target_id = self._selected.id
        if select_first and tools:
            target_id = tools[0].id
        self._selected = self.registry.get(target_id) if target_id else None
        self._tools_model.set_tools(tools, target_id, running_ids)
        self.customToolsChanged.emit()
        if notify_selected:
            self.selectedToolChanged.emit()
        self.consoleTextChanged.emit()
        self.runningChanged.emit()
        self._status_text = "运行中" if self.running else "就绪"
        self.statusTextChanged.emit()

    def _sorted_tools(self, tools: list[ToolDefinition]) -> list[ToolDefinition]:
        if self._section != ToolSection.CUSTOM:
            return tools
        return self.sorted_custom_tools(tools)

    def sorted_custom_tools(self, tools: list[ToolDefinition]) -> list[ToolDefinition]:
        tool_ids = [tool.id for tool in tools]
        added_times = self.config_store.tool_added_times(tool_ids)
        if self._tool_sort_mode == "added_time":
            return sorted(tools, key=lambda tool: (-added_times[tool.id], tool.title.casefold()))
        if self._tool_sort_mode == "name":
            return sorted(tools, key=lambda tool: (self._name_sort_key(tool.title), tool.id))
        if self._tool_sort_mode == "usage":
            counts = self.config_store.tool_usage_counts()
            return sorted(
                tools,
                key=lambda tool: (-counts.get(tool.id, 0), tool.title.casefold(), tool.id),
            )
        order = {tool_id: index for index, tool_id in enumerate(self.config_store.tool_order())}
        return sorted(
            tools,
            key=lambda tool: (
                order.get(tool.id, len(order) + tool.presentation.order),
                tool.title.casefold(),
            ),
        )

    @staticmethod
    def _name_sort_key(title: str) -> str:
        """Compare Chinese and Latin names through one case-insensitive pinyin key."""
        return "".join(lazy_pinyin(title)).casefold()

    @staticmethod
    def _analyze_tool(tool: ToolDefinition) -> AdbAnalysis:
        def resolve(source: str) -> Path:
            path = Path(source)
            if path.is_absolute():
                return path
            candidate = Path(resource_path(source))
            return candidate if candidate.exists() else package_root() / source

        return analyze_adb(tool, resolve)

    def _refresh_adb_analysis(self) -> None:
        analysis = self._analyze_tool(self._selected) if self._selected else None
        if analysis != self._last_analysis:
            self._last_analysis = analysis
            self.selectedToolDataChanged.emit()

    @Slot(str, str, str, result=str)
    def previewAndroidDetection(self, kind: str, command: str, mode: str) -> str:
        try:
            tool = ToolDefinition(
                id="preview", section=ToolSection.CUSTOM, title="preview",
                executor=ExecutorDefinition(
                    kind=ExecutorKind(kind), command=command,
                    android_device_mode=AndroidDeviceMode(mode),
                ),
            )
            return self._analyze_tool(tool).reason
        except ValueError:
            return "请选择运行方式。"

    @Slot()
    def confirmExecutionReplacement(self) -> None:
        self.execution_coordinator.confirm_replacement()

    @Slot()
    def cancelExecutionReplacement(self) -> None:
        self.execution_coordinator.cancel_replacement()

    def _on_execution_started(self, tool_id: str) -> None:
        tool = self.registry.get(tool_id)
        if tool is not None:
            self._record_tool_usage(tool)
        self.set_tool_status(tool_id, "运行中")

    def _record_tool_usage(self, tool: ToolDefinition) -> None:
        if tool.section != ToolSection.CUSTOM:
            return
        self.config_store.record_tool_recent(tool.id)
        self.config_store.increment_tool_usage(tool.id)
        self.customToolsChanged.emit()
        if self._tool_sort_mode == "usage":
            selected_id = self._selected.id if self._selected is not None else ""
            self._refresh(select_id=selected_id, notify_selected=False)

    def _on_execution_running_changed(self, tool_id: str, running: bool) -> None:
        self.set_tool_status(tool_id, "运行中" if running else "就绪")
        tool = self.registry.get(tool_id)
        if tool is not None and tool.section == ToolSection.CUSTOM:
            selected_id = self._selected.id if self._selected is not None else ""
            # Running-state changes only reorder/update the tool list. Emitting
            # selectedToolChanged here makes QML recreate its parameter map while
            # edited text controls keep their old visual content, so a second run
            # sees empty/default values instead of the text still on screen.
            self._refresh(select_id=selected_id, notify_selected=False)
            return
        if self._selected is not None and self._selected.id == tool_id:
            self.runningChanged.emit()

    def _on_execution_finished(self, tool_id: str, exit_code: int) -> None:
        self._flush_console()
        self.set_tool_status(tool_id, "执行成功" if exit_code == 0 else f"执行失败 ({exit_code})")
        if self._selected is None or self._selected.id != tool_id:
            return
        self.runningChanged.emit()



    def _append_console(self, text: str) -> None:
        self._commit_console("", text)

    def append_tool_console(self, tool_id: str, text: str) -> None:
        self._commit_console("", text)
        if tool_id:
            self._commit_console(tool_id, text)

    def clear_tool_console(self, tool_id: str) -> None:
        self._pending_console_chunks.pop(tool_id, None)
        self._console_texts[tool_id] = ""
        self.toolConsoleChanged.emit(tool_id)

    def _queue_console(self, tool_id: str, text: str) -> None:
        """Coalesce high-volume process output before notifying the QML text view."""
        if not text:
            return
        for key in ("", tool_id) if tool_id else ("",):
            self._pending_console_chunks.setdefault(key, []).append(text)
        if not self._console_refresh_timer.isActive():
            self._console_refresh_timer.start()

    def _flush_console(self) -> None:
        if not self._pending_console_chunks:
            return
        pending = self._pending_console_chunks
        self._pending_console_chunks = {}
        for key, chunks in pending.items():
            self._store_console(key, "".join(chunks))
            if key:
                self.toolConsoleChanged.emit(key)
        self.consoleTextChanged.emit()

    def _commit_console(self, key: str, text: str) -> None:
        self._store_console(key, text)
        if key:
            self.toolConsoleChanged.emit(key)
        else:
            self.consoleTextChanged.emit()

    def _store_console(self, key: str, text: str) -> None:
        value = self._console_texts.get(key, "")
        value += text
        if len(value) > CONSOLE_MAX_CHARS:
            value = value[-CONSOLE_RETAINED_CHARS:]
        self._console_texts[key] = value
