from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, QRect, Signal, Slot
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QDialog, QFileDialog

from poptools.viewmodels.app_controller import _file_picker_start_directory

if TYPE_CHECKING:
    from poptools.viewmodels.app_controller import AppController


class ToolSessionController(QObject):
    """A fixed tool identity for one execution window; execution remains shared."""

    selectedToolChanged = Signal()
    selectedToolDataChanged = Signal()
    consoleTextChanged = Signal()
    runningChanged = Signal()
    statusTextChanged = Signal()

    def __init__(self, backend: AppController, tool_id: str) -> None:
        super().__init__(backend)
        self._backend = backend
        self._tool_id = tool_id
        self._tool = backend.registry.get(tool_id)
        self._window: QWindow | None = None
        self._disposed = False
        backend.customToolsChanged.connect(self._refresh_tool)
        backend.toolConsoleChanged.connect(self._on_console)
        backend.toolStatusChanged.connect(self._on_status)
        backend.runningChanged.connect(self.runningChanged)

    @Property(str, constant=True)
    def toolId(self) -> str:
        return self._tool_id

    @Property(dict, notify=selectedToolDataChanged)
    def selectedTool(self) -> dict[str, Any]:
        return self._backend.tool_data(self._tool)

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._backend.execution_coordinator.running(self._tool_id)

    @Property(str, notify=statusTextChanged)
    def statusText(self) -> str:
        return self._backend._tool_statuses.get(
            self._tool_id, "运行中" if self.running else "就绪",
        )

    @Property(str, notify=consoleTextChanged)
    def consoleText(self) -> str:
        return self._backend._console_texts.get(self._tool_id, "")

    @Slot(QObject)
    def attachWindow(self, window: QObject) -> None:
        if isinstance(window, QWindow):
            self._window = window

    @Slot("QVariantMap", result=bool)
    def runSelected(self, values: dict[str, Any]) -> bool:
        if self._backend.registry.get(self._tool_id) is None:
            self._backend.append_tool_console(self._tool_id, "脚本已删除，无法继续运行。\n")
            return False
        return self._backend.run_tool(self._tool_id, values)

    @Slot()
    def stopExecution(self) -> None:
        self._backend.execution_coordinator.stop(self._tool_id)

    @Slot()
    def clearConsole(self) -> None:
        self._backend.clear_tool_console(self._tool_id)

    @Slot(str, str, result=bool)
    def setParameterDefault(self, parameter_id: str, default: str) -> bool:
        if self.running:
            return False
        try:
            self._tool = self._backend.registry.set_parameter_default(
                self._tool_id, parameter_id, default,
            )
            if self._backend._selected is not None and self._backend._selected.id == self._tool_id:
                self._backend._selected = self._tool
            self._backend.append_tool_console(
                self._tool_id, f"已更新参数“{parameter_id}”的默认值。\n",
            )
            # Keep current forms intact so another field's unsaved input survives.
            return True
        except (KeyError, OSError, ValueError) as exc:
            self._backend.append_tool_console(self._tool_id, f"默认值保存失败：{exc}\n")
            return False

    @Slot(str, result=str)
    def localPathFromUrl(self, url: str) -> str:
        return self._backend.localPathFromUrl(url)

    def _choose_path(self, current_path: str, directory: bool) -> str:
        dialog = QFileDialog(
            None, "选择文件夹" if directory else "选择文件",
            _file_picker_start_directory(current_path),
        )
        dialog.setFileMode(QFileDialog.FileMode.Directory if directory
                           else QFileDialog.FileMode.ExistingFile)
        if directory:
            dialog.setOption(QFileDialog.Option.ShowDirsOnly, True)
        # Associate the native picker with its execution window, not the main window.
        if self._window is not None:
            dialog.winId()
            handle = dialog.windowHandle()
            if handle is not None:
                handle.setTransientParent(self._window)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected = dialog.selectedFiles()
                return selected[0] if selected else ""
            return ""
        finally:
            dialog.deleteLater()

    @Slot(str, result=str)
    def chooseParameterFile(self, current_path: str) -> str:
        return self._choose_path(current_path, False)

    @Slot(str, result=str)
    def chooseParameterDirectory(self, current_path: str) -> str:
        return self._choose_path(current_path, True)

    @Slot(int, int, int, int, bool)
    def updateScrcpyGeometry(self, x: int, y: int, width: int, height: int, visible: bool) -> None:
        self._backend.execution_coordinator.set_scrcpy_geometry(QRect(x, y, width, height), visible)

    def _refresh_tool(self) -> None:
        tool = self._backend.registry.get(self._tool_id)
        if tool is not None and tool != self._tool:
            self._tool = tool
            self.selectedToolDataChanged.emit()

    def _on_console(self, tool_id: str) -> None:
        if tool_id == self._tool_id:
            self.consoleTextChanged.emit()

    def _on_status(self, tool_id: str) -> None:
        if tool_id == self._tool_id:
            self.statusTextChanged.emit()
            self.runningChanged.emit()

    @Slot()
    def dispose(self) -> None:
        if not self._disposed:
            self._disposed = True
            self.deleteLater()
