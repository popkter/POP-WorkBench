from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPointF, Qt, QUrl, Signal
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from poptools.domain.models import AndroidDeviceMode, ParameterDefinition
from poptools.infrastructure.android_device_service import AndroidDevice, parse_adb_devices
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, package_root, resource_path
from poptools.runners.execution_coordinator import ExecutionCoordinator
from poptools.runners.execution_manager import ExecutionManager
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.app_controller import AppController


class Devices(QObject):
    devicesChanged = Signal()
    refreshingChanged = Signal()

    def __init__(self):
        super().__init__()
        self.devices = []
        self.refreshing = False

    def refresh(self):
        pass

    def set_devices(self, *serials):
        self.devices = [AndroidDevice(s, model="Phone_" + s) for s in serials]
        self.devicesChanged.emit()


class Processes(QObject):
    processesChanged = Signal()
    refreshingChanged = Signal()
    processes = []

    def refresh(self, serial):
        self.serial = serial


@pytest.fixture
def setup_devices(qapp, tmp_path):
    config = ConfigStore(AppPaths(tmp_path))
    devices = Devices()
    processes = Processes()
    controller = AndroidController(config, devices, processes)
    yield controller, devices, config
    controller.stopAutoRefresh()


def test_global_choice_persists_across_tools_and_script_deletion(setup_devices):
    controller, devices, config = setup_devices
    devices.set_devices("A", "B")
    assert controller.deviceForTool("one")["serial"] == ""
    controller.selectDeviceForTool("one", "A")
    controller.selectDeviceForTool("two", "B")
    assert controller.available_device_for_tool("one") == "B"
    assert controller.available_device_for_tool("two") == "B"
    devices.set_devices("A")
    assert controller.deviceForTool("one")["serial"] == "B"
    assert not controller.deviceForTool("one")["available"]
    assert controller.available_device_for_tool("one") == ""
    assert controller.available_device_for_tool("two") == ""
    restarted = AndroidController(config, devices, Processes())
    restarted.stopAutoRefresh()
    assert restarted.deviceForTool("one")["serial"] == "B"
    devices.set_devices("A", "B")
    assert restarted.available_device_for_tool("one") == "B"
    restarted.forget_tool("one")
    assert "one" not in config.android_tool_devices()
    assert restarted.available_device_for_tool("two") == "B"
    assert config.android_selected_device() == "B"


def test_single_device_auto_selection_is_shared_and_ignores_old_tool_choices(setup_devices):
    controller, devices, config = setup_devices
    raw = config.load_config()
    raw["android"]["tool_devices"] = {"other": "old"}
    config.save_config(raw)
    devices.set_devices("A")
    assert controller.available_device_for_tool("new") == "A"
    devices.set_devices("A", "B")
    assert controller.available_device_for_tool("other") == "A"
    controller.selectDeviceForTool("new", "offline")
    assert controller.available_device_for_tool("new") == "A"
    assert [d.serial for d in parse_adb_devices(
        "List of devices attached\nA device\nB offline\nC unauthorized\n"
    )] == ["A"]


def test_new_device_replaces_disconnected_selection_and_persists(setup_devices):
    controller, devices, config = setup_devices
    devices.set_devices("A")
    assert controller.available_device_for_tool("one") == "A"
    devices.set_devices()
    assert not controller.deviceForTool("one")["available"]
    devices.set_devices("B")
    assert controller.available_device_for_tool("one") == "B"
    assert config.android_selected_device() == "B"
    devices.set_devices("A", "B")
    assert controller.available_device_for_tool("one") == "B"


def test_new_device_does_not_replace_a_connected_selection(setup_devices):
    controller, devices, config = setup_devices
    devices.set_devices("A")
    assert controller.available_device_for_tool("one") == "A"
    devices.set_devices("B", "A")
    assert controller.available_device_for_tool("one") == "A"
    assert config.android_selected_device() == "A"


def test_global_selection_follows_new_device_once_current_device_disconnects(setup_devices):
    controller, devices, config = setup_devices
    devices.set_devices("A", "B")
    controller.selectDeviceForTool("one", "A")
    devices.set_devices("B")
    assert controller.available_device_for_tool("one") == ""
    devices.set_devices("B", "C", "D")
    assert controller.available_device_for_tool("one") == "C"
    assert controller.available_device_for_tool("two") == "C"
    assert config.android_selected_device() == "C"
    assert config.android_tool_devices() == {}
    assert controller.available_device_for_tool("unselected") == "C"


class Manager(QObject):
    output = Signal(str)
    started = Signal()
    runningChanged = Signal(bool)
    finished = Signal(int)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.python_environment = SimpleNamespace()
        self.running = False
        self.calls = []

    def start(self, tool, values):
        self.calls.append((tool.id, dict(values)))
        self.running = True
        return True

    def stop(self):
        self.running = False
        self.finished.emit(0)


@pytest.fixture
def app_setup(setup_devices):
    android, devices, config = setup_devices
    managers = []

    def factory():
        manager = Manager(config.paths)
        managers.append(manager)
        return manager

    coordinator = ExecutionCoordinator(factory(), 3, manager_factory=factory)
    registry = ToolRegistry(resource_path("tools"), JsonToolRepository(config.paths))
    controller = AppController(registry, coordinator, config, android)
    yield controller, registry, coordinator, managers, android, devices
    controller._analysis_timer.stop()
    controller._console_refresh_timer.stop()


def add_script(registry, command="adb shell getprop", mode="auto"):
    return registry.create_custom(
        title="Script", description="", kind="powershell", command=command,
        android_device_mode=mode,
    )


def test_runs_are_isolated_and_queue_keeps_submitted_device(app_setup, qapp):
    app, registry, coordinator, managers, android, devices = app_setup
    devices.set_devices("A", "B")
    scripts = [add_script(registry) for _ in range(3)]
    for tool, serial in zip(scripts, ["A", "B", "A"], strict=True):
        android.selectDeviceForTool(tool.id, serial)
        app.selectTool(tool.id)
        app.runSelected({"device": "ordinary user parameter"})
    assert managers[0].calls[0][1] == {
        "device": "ordinary user parameter", "__android_device__": "A",
    }
    assert managers[1].calls[0][1]["__android_device__"] == "B"
    android.selectDeviceForTool(scripts[2].id, "B")
    coordinator.confirm_replacement()
    qapp.processEvents()
    assert managers[2].calls[0][1]["__android_device__"] == "A"
    assert android.available_device_for_tool(scripts[2].id) == "B"


def test_required_missing_blocks_but_host_explicit_and_ordinary_can_run(app_setup):
    app, registry, coordinator, managers, android, devices = app_setup
    required = add_script(registry)
    app.selectTool(required.id)
    assert not app.runSelected({})
    devices.set_devices("A", "B")
    assert not app.runSelected({})
    for command in ["adb devices", "adb -s external shell", "Write-Output hi"]:
        tool = add_script(registry, command)
        app.selectTool(tool.id)
        assert app.runSelected({"__android_device__": "stale"})
        assert "__android_device__" not in managers[-1].calls[0][1]
        coordinator.stop(tool.id)


def test_device_parameter_uses_its_actual_id_and_environment_is_local(app_setup, monkeypatch):
    app, registry, coordinator, managers, android, devices = app_setup
    tool = add_script(registry)
    tool.parameters = [ParameterDefinition(id="target", label="设备", kind="android_device")]
    devices.set_devices("A")
    app.selectTool(tool.id)
    assert app.runSelected({})
    values = managers[0].calls[0][1]
    assert values == {"target": "A", "__android_device__": "A"}
    monkeypatch.delenv("ANDROID_SERIAL", raising=False)
    manager = ExecutionManager(managers[0].paths)
    assert manager._build_environment(tool, values, manager.paths.outputs_dir).value(
        "ANDROID_SERIAL"
    ) == "A"
    assert not manager._build_environment(tool, {}, manager.paths.outputs_dir).contains(
        "ANDROID_SERIAL"
    )
    tool.executor.android_device_mode = AndroidDeviceMode.NONE
    assert app.selectedTool["parameters"][0]["kind"] == "text"
    assert not app.selectedTool["uses_android_device"]


def test_edit_mode_preserved_and_deleted_tool_keeps_global_device(app_setup):
    app, registry, coordinator, managers, android, devices = app_setup
    tool = add_script(registry, "dynamic_command", "use")
    app.selectTool(tool.id)
    assert app.saveSelected("Renamed", "", "powershell", "dynamic_command", "terminal")
    assert registry.get(tool.id).executor.android_device_mode == "use"
    assert app.saveSelected("Renamed", "", "powershell", "adb shell", "terminal", "none")
    assert not app.selectedTool["uses_android_device"]
    devices.set_devices("A")
    android.selectDeviceForTool(tool.id, "A")
    assert app.deleteSelected()
    assert tool.id not in android.config_store.android_tool_devices()
    assert android.config_store.android_selected_device() == "A"
    assert android.available_device_for_tool("another") == "A"


def test_tray_adb_script_without_parameters_opens_local_device_picker(app_setup):
    app, registry, coordinator, managers, android, devices = app_setup
    tool = add_script(registry)
    requested = []
    app.recentToolDialogRequested.connect(requested.append)
    app.openRecentToolFromTray(tool.id)
    assert requested == [tool.id]
    assert not managers[0].calls


def test_external_analysis_refresh_does_not_reset_parameter_form(app_setup, tmp_path):
    app, registry, coordinator, managers, android, devices = app_setup
    source = tmp_path / "source.ps1"
    source.write_text("Write-Output hi", encoding="utf-8")
    tool = add_script(registry, f'& "{source}"')
    app.selectTool(tool.id)
    app._refresh_adb_analysis()
    selection_events = []
    data_events = []
    app.selectedToolChanged.connect(lambda: selection_events.append(True))
    app.selectedToolDataChanged.connect(lambda: data_events.append(True))
    source.write_text("adb shell", encoding="utf-8")
    app._refresh_adb_analysis()
    assert app.selectedTool["requires_android_device"]
    assert data_events and not selection_events


@pytest.mark.gui
def test_device_dropdown_selects_globally_and_shows_disconnect(setup_devices, qapp):
    android, devices, config = setup_devices
    devices.set_devices("A", "B")
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("androidBackend", android)
    component = QQmlComponent(engine)
    warnings = []
    engine.warnings.connect(lambda items: warnings.extend(i.toString() for i in items))
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 560; height: 450; visible: true
    DeviceSelector {
        objectName: "firstSelector"
        x: 20; y: 20; width: 520
        controller: androidBackend; toolId: "first"; requiredDevice: true
    }
    DeviceSelector {
        objectName: "secondSelector"
        x: 20; y: 320; width: 520
        controller: androidBackend; toolId: "second"
    }
}''', QUrl.fromLocalFile(str(package_root() / "ui/qml/DeviceHarness.qml")))
    window = component.create()
    assert isinstance(window, QWindow), [e.toString() for e in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        selector = window.findChild(QQuickItem, "firstSelector")
        assert selector is not None
        QTest.mouseClick(window, Qt.LeftButton,
                         pos=selector.mapToScene(QPointF(100, 40)).toPoint())
        QTest.qWait(150)
        popup = selector.findChild(QObject, "toolDevicePopup")
        assert popup is not None and popup.property("opened")
        content = popup.property("contentItem")

        def find_visual(item, name):
            if item.objectName() == name:
                return item
            for child in item.childItems():
                found = find_visual(child, name)
                if found is not None:
                    return found
            return None

        row = find_visual(content, "deviceRow_B")
        assert row is not None
        QTest.mouseClick(window, Qt.LeftButton,
                         pos=row.mapToScene(QPointF(100, 24)).toPoint())
        qapp.processEvents()
        assert android.available_device_for_tool("first") == "B"
        assert android.available_device_for_tool("second") == "B"
        devices.set_devices("A")
        qapp.processEvents()
        assert not android.deviceForTool("first")["available"]
        devices.set_devices()
        QMetaObject.invokeMethod(selector, "openDeviceMenu")
        QTest.qWait(150)
        assert popup.property("opened")
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
