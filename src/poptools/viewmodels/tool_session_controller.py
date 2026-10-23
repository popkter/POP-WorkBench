from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Property, QObject, QPoint, QRect, QRectF, Signal, Slot
from PySide6.QtGui import QRegion, QWindow
from PySide6.QtWidgets import QDialog, QFileDialog

from poptools.infrastructure.card_window_updates import card_window_updates
from poptools.infrastructure.window_placement import (
    card_flight_geometry,
    card_pack_mask,
    place_tool_window,
    set_card_flight_layer,
)
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
        self._tool_data = backend.tool_data(self._tool)
        self._window: QWindow | None = None
        self._disposed = False
        self._card_flight_layer = False
        backend.customToolsChanged.connect(self._refresh_tool)
        backend.toolConsoleChanged.connect(self._on_console)
        backend.toolStatusChanged.connect(self._on_status)
        backend.runningChanged.connect(self.runningChanged)

    @Property(str, constant=True)
    def toolId(self) -> str:
        return self._tool_id

    @Property(dict, notify=selectedToolDataChanged)
    def selectedTool(self) -> dict[str, Any]:
        return self._tool_data

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        return self._backend.execution_coordinator.running(self._tool_id)

    @Property(str, notify=statusTextChanged)
    def statusText(self) -> str:
        return self._backend.tool_status(self._tool_id)

    @Property(str, notify=consoleTextChanged)
    def consoleText(self) -> str:
        return self._backend.console_store.text(self._tool_id)

    @Slot(QObject)
    def attachWindow(self, window: QObject) -> None:
        if isinstance(window, QWindow):
            self._window = window

    @Slot()
    def placeWindow(self) -> None:
        if self._window is not None:
            place_tool_window(self._window)

    @Slot(QRectF, result="QVariantMap")
    @Slot(QRectF, bool, result="QVariantMap")
    def prepareCardFlight(self, source: QRectF, preserve_source: bool = False) -> dict[str, Any]:
        if self._window is None or source.isEmpty():
            return {}
        place_tool_window(self._window, source.center().toPoint())
        screen = self._window.screen()
        return card_flight_geometry(source, self._window.geometry(), screen.availableGeometry(),
                                    preserve_source)

    @Slot(QRectF, result="QVariantMap")
    @Slot(QRectF, bool, result="QVariantMap")
    def prepareCardReturn(self, source: QRectF, preserve_source: bool = False) -> dict[str, Any]:
        if self._window is None or self._window.screen() is None:
            return {}
        target = self._window.geometry()
        available = self._window.screen().availableGeometry()
        if not preserve_source:
            source = source.intersected(QRectF(available))
        if source.isEmpty():
            # Cards opened without a list origin fold into their current center.
            center = target.center()
            source = QRectF(center.x() - 20, center.y() - 20, 40, 40)
        return card_flight_geometry(source, target, available, preserve_source)

    @Slot(float, float, QRectF, QRectF)
    def moveCard(self, x: float, y: float, pack: QRectF, opening: QRectF) -> None:
        """Move a full render surface; keep occlusion anchored to the pack."""
        if self._window is not None:
            position = QPoint(round(x), round(y))
            mask = card_pack_mask(QRect(position, self._window.size()), pack, opening)
            if self._window.isVisible() and self._card_flight_layer:
                card_window_updates().schedule(self._window, position, mask)
                return
            if self._window.position() != position:
                self._window.setPosition(position)
            if self._window.mask() != mask:
                self._window.setMask(mask)

    @Slot(bool)
    def setCardFlightLayer(self, flying: bool) -> None:
        if self._window is not None and self._card_flight_layer != flying:
            if not flying:
                card_window_updates().finish(self._window)
            set_card_flight_layer(self._window, flying)
            self._card_flight_layer = flying
            if not flying:
                self._window.setMask(QRegion())

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
        saved = self._backend.update_tool_parameter_default(self._tool_id, parameter_id, default)
        if saved:
            self._refresh_tool()
        return saved

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
            self._tool_data = self._backend.tool_data(tool)
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
