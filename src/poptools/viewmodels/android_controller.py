from __future__ import annotations

import sys

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from poptools.infrastructure.android_device_service import (
    AndroidDeviceService,
    AndroidProcessService,
)
from poptools.infrastructure.config_store import ConfigStore
from poptools.paths import bundled_adb_path


class AndroidController(QObject):
    """Share Android discovery and one selected device across the application."""

    stateChanged = Signal()
    pluginManagementRequested = Signal()

    def __init__(
        self,
        config_store: ConfigStore,
        device_service: AndroidDeviceService | None = None,
        process_service: AndroidProcessService | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_store = config_store
        self._device_service = device_service or AndroidDeviceService(self)
        self._managed_discovery = device_service is None and sys.platform == "win32"
        self._process_service = process_service or AndroidProcessService(self)
        self._selected_device_serial = config_store.android_selected_device()
        self._known_device_serials = {device.serial for device in self._device_service.devices}
        self._manual_device_refreshing = False
        self._device_service.devicesChanged.connect(self._on_devices_changed)
        self._device_service.refreshingChanged.connect(self._on_device_refreshing_changed)
        self._process_service.processesChanged.connect(self.stateChanged)
        self._process_service.refreshingChanged.connect(self.stateChanged)
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(5000)
        self._refresh_timer.timeout.connect(self._refresh_android_devices_silently)
        self.refreshPluginAvailability()
        self._on_devices_changed()
        # The service already starts work asynchronously. Calling it directly avoids
        # leaving a context-free singleShot callback behind when a short-lived
        # controller is destroyed (notably in tests and settings-only processes).
        self._refresh_android_devices_silently()

    @Property("QVariantList", notify=stateChanged)
    def androidDevices(self) -> list[dict[str, str]]:
        return [device.to_qml() for device in self._device_service.devices]

    @Property("QVariantList", notify=stateChanged)
    def androidProcesses(self) -> list[dict[str, str]]:
        return self._process_service.processes

    @Property("QVariantMap", notify=stateChanged)
    def selectedAndroidDevice(self) -> dict[str, object]:
        if self._managed_discovery and not bundled_adb_path().is_file():
            return {"serial": "", "available": False, "pluginMissing": True,
                    "label": "请先安装 Android 工具插件"}
        serial = self._selected_device_serial
        devices = self._device_service.devices
        device = next((d for d in devices if d.serial == serial), None)
        return {
            "serial": serial,
            "available": device is not None,
            "name": (device.model.replace("_", " ") or device.product or device.serial)
                if device else serial,
            "label": device.label if device else f"{serial} · 不可用" if serial
            else "请选择 Android 设备" if devices else "未检测到 Android 设备",
        }

    @Slot(str, result="QVariantMap")
    def deviceForTool(self, tool_id: str) -> dict[str, object]:
        # Keep existing execution/dialog callers on the same global selection.
        return self.selectedAndroidDevice

    def available_device_for_tool(self, tool_id: str) -> str:
        state = self.deviceForTool(tool_id)
        return str(state["serial"]) if state["available"] else ""

    @Property(bool, notify=stateChanged)
    def androidDeviceRefreshing(self) -> bool:
        return self._manual_device_refreshing and self._device_service.refreshing

    @Slot()
    def refreshAndroidDevices(self) -> None:
        """Refresh from an explicit user action and expose its progress to QML."""
        if not getattr(self, "resume_plugin_discovery", lambda: True)():
            return
        if not getattr(self, "plugin_discovery_allowed", lambda: True)():
            self.pluginManagementRequested.emit()
            return
        if self._managed_discovery and not bundled_adb_path().is_file():
            self.pluginManagementRequested.emit()
            return
        already_refreshing = self._device_service.refreshing
        self._manual_device_refreshing = True
        self._device_service.refresh()
        if not self._device_service.refreshing:
            self._manual_device_refreshing = False
        elif already_refreshing:
            self.stateChanged.emit()

    @Slot(str)
    def refreshAndroidProcesses(self, serial: str) -> None:
        self._process_service.refresh(serial)

    @Slot(str)
    def selectAndroidDevice(self, serial: str) -> None:
        available = {device.serial for device in self._device_service.devices}
        if serial not in available or serial == self._selected_device_serial:
            return
        self._selected_device_serial = serial
        self.config_store.set_android_selected_device(serial)
        self.stateChanged.emit()

    @Slot(str, str)
    def selectDeviceForTool(self, tool_id: str, serial: str) -> None:
        self.selectAndroidDevice(serial)

    def forget_tool(self, tool_id: str) -> None:
        # Deleting a script must not clear the application's selected device.
        if tool_id in self.config_store.android_tool_devices():
            self.config_store.set_android_tool_device(tool_id, "")

    def stopAutoRefresh(self) -> None:
        self._refresh_timer.stop()

    def _refresh_android_devices_silently(self) -> None:
        """Poll devices without publishing a transient scanning state to the UI."""
        if not getattr(self, "plugin_discovery_allowed", lambda: True)():
            return
        if self._managed_discovery and not bundled_adb_path().is_file():
            return
        self._device_service.refresh()

    def refreshPluginAvailability(self):
        if not getattr(self, "plugin_discovery_allowed", lambda: True)():
            self._refresh_timer.stop()
            return
        if self._managed_discovery and not bundled_adb_path().is_file():
            self._refresh_timer.stop()
            self._device_service._set_devices([])
        elif not self._refresh_timer.isActive():
            self._refresh_timer.start()
        self.stateChanged.emit()

    def _on_device_refreshing_changed(self) -> None:
        if not self._manual_device_refreshing:
            return
        if not self._device_service.refreshing:
            self._manual_device_refreshing = False
        self.stateChanged.emit()

    def _on_devices_changed(self) -> None:
        devices = self._device_service.devices
        available = {device.serial for device in devices}
        newly_connected = [device.serial for device in devices
                           if device.serial not in self._known_device_serials]
        self._known_device_serials = available
        replacement = ""
        if not self._selected_device_serial and len(devices) == 1:
            replacement = devices[0].serial
        elif (self._selected_device_serial and self._selected_device_serial not in available
              and newly_connected):
            replacement = newly_connected[0]
        if replacement:
            self._selected_device_serial = replacement
            self.config_store.set_android_selected_device(replacement)
        self.stateChanged.emit()
