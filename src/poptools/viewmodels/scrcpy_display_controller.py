from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QCoreApplication, QObject, QTimer, Signal, Slot

from poptools.infrastructure.background_process import BackgroundProcess
from poptools.paths import bundled_adb_path, bundled_android_tools_dir, bundled_scrcpy_path

if TYPE_CHECKING:
    from poptools.runners.execution_coordinator import ExecutionCoordinator
    from poptools.viewmodels.android_controller import AndroidController


def parse_displays(output: str) -> list[dict[str, str]]:
    displays: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        match = re.search(r"--display-id[=\s]+(\d+)\b", line)
        if match:
            display_id = str(int(match[1]))
            detail = line[match.end():].strip().strip("() ")
            displays[display_id] = {
                "id": display_id,
                "label": f"屏幕 {display_id}" + (f" · {detail}" if detail else ""),
            }
    return sorted(displays.values(), key=lambda item: int(item["id"]))


class ScrcpyDisplayController(QObject):
    """Keep screen selection separate from projection and device discovery."""

    changed = Signal()

    def __init__(
        self, android: AndroidController, execution: ExecutionCoordinator,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.android = android
        self.execution = execution
        self._enabled = False
        self._serial = ""
        self._selections: dict[str, str] = {}
        self._displays: list[dict[str, str]] = []
        self._error = ""
        self._process: BackgroundProcess | None = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(10000)
        self._timer.timeout.connect(self._timeout)
        android.stateChanged.connect(self._device_changed)
        app = QCoreApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    @Property("QVariantList", notify=changed)
    def displays(self) -> list[dict[str, str]]:
        return self._displays

    @Property(str, notify=changed)
    def selectedId(self) -> str:
        return self._selections.get(self._serial, "0")

    @Property(bool, notify=changed)
    def loading(self) -> bool:
        return self._process is not None

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(bool, notify=changed)
    def deviceAvailable(self) -> bool:
        return bool(self._serial)

    @Property(str, notify=changed)
    def deviceSerial(self) -> str:
        return self._serial

    @Slot(bool)
    def setEnabled(self, enabled: bool) -> None:
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if enabled:
            self._device_changed()
            if self._serial and not self.loading and not self._displays:
                self.refresh()
        else:
            self._cancel()
            self.changed.emit()

    def _device_changed(self) -> None:
        state = self.android.selectedAndroidDevice
        serial = str(state["serial"]) if state.get("available") else ""
        if serial == self._serial:
            return
        old_serial = self._serial
        self._cancel()
        self._serial = serial
        self._displays = []
        self._error = ""
        # A disconnected target must not be restarted by a pending screen switch.
        if old_serial and self.execution._scrcpy_serial == old_serial:
            self.execution.stop(self.execution._scrcpy_tool_id)
        self.changed.emit()
        if self._enabled and serial:
            self.refresh()

    @Slot(str, result=bool)
    def selectDisplay(self, value: str) -> bool:
        value = value.strip()
        if not re.fullmatch(r"[0-9]+", value) or int(value) > 2147483647:
            self._error = "displayId 必须是非负整数。"
            self.changed.emit()
            return False
        if not self._serial:
            return False
        value = str(int(value))
        self._selections[self._serial] = value
        self._error = ""
        self.execution.switch_scrcpy_display(self._serial, int(value))
        self.changed.emit()
        return True

    @Slot()
    def refresh(self) -> None:
        if not self._enabled or not self._serial or self.loading:
            return
        if getattr(self.execution, "plugin_mutation_active", lambda: False)():
            self._error = "Android 工具正在变更，请稍后刷新。"
            self.changed.emit()
            return
        scrcpy = bundled_scrcpy_path()
        adb = bundled_adb_path()
        server = bundled_android_tools_dir() / "scrcpy-server"
        if not all(path.is_file() for path in (scrcpy, adb, server)):
            self._error = "请先安装 Android 工具插件；也可手动填写 displayId。"
            self.changed.emit()
            return
        process = BackgroundProcess(self)
        self._process = process
        self._error = ""
        self._displays = []
        output = bytearray()
        process.stdoutReady.connect(output.extend)
        process.stderrReady.connect(output.extend)
        process.errorOccurred.connect(lambda message: self._failed(process, message))
        process.finished.connect(lambda code: self._completed(process, code, output))
        environment = dict(os.environ)
        environment["ADB"] = str(adb)
        environment["SCRCPY_SERVER_PATH"] = str(server)
        environment["PATH"] = f"{scrcpy.parent}{os.pathsep}{environment.get('PATH', '')}"
        self._timer.start()
        process.start(str(scrcpy), ["--serial", self._serial, "--list-displays"],
                      cwd=scrcpy.parent, environment=environment)
        self.changed.emit()

    def _failed(self, process: BackgroundProcess, message: str) -> None:
        if process is self._process:
            self._error = message

    def _completed(self, process: BackgroundProcess, code: int, output: bytearray) -> None:
        process.deleteLater()
        if process is not self._process:
            return
        self._timer.stop()
        self._process = None
        text = output.decode("utf-8", "replace")
        self._displays = parse_displays(text) if code == 0 else []
        if not self._displays:
            self._error = self._error or (
                "未获取到屏幕列表，可手动输入 displayId。"
                + ("\n" + text[-1000:].strip() if text.strip() else "")
            )
        self.changed.emit()

    def _cancel(self) -> None:
        self._timer.stop()
        process = self._process
        self._process = None
        if process is not None:
            process.kill()

    def _timeout(self) -> None:
        self._cancel()
        self._error = "查询屏幕列表超时，可刷新重试或手动输入 displayId。"
        self.changed.emit()

    @Slot()
    def shutdown(self) -> None:
        self._enabled = False
        self._cancel()
        self.execution.stop(self.execution._scrcpy_tool_id)
