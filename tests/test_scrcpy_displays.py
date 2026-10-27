from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, Qt, QUrl, Signal
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.scrcpy_controller import ScrcpyController, _projection_arguments
from poptools.paths import package_root, resource_path
from poptools.runners.execution_coordinator import ExecutionCoordinator
from poptools.viewmodels.scrcpy_display_controller import ScrcpyDisplayController, parse_displays


class Android(QObject):
    stateChanged = Signal()

    def __init__(self):
        super().__init__()
        self.selectedAndroidDevice = {"serial": "A", "available": True}

    def select(self, serial):
        self.selectedAndroidDevice = {"serial": serial, "available": bool(serial)}
        self.stateChanged.emit()


class Process(QObject):
    stdoutReady = Signal(bytes)
    stderrReady = Signal(bytes)
    errorOccurred = Signal(str)
    finished = Signal(int)
    instances = []

    def __init__(self, parent=None):
        super().__init__(parent)
        self.killed = False
        self.terminated = False
        self.instances.append(self)

    def start(self, program, arguments, **kwargs):
        self.arguments = arguments
        return True

    def kill(self):
        self.killed = True

    def terminate(self):
        self.terminated = True


@pytest.fixture
def screens(qapp, tmp_path, monkeypatch):
    import poptools.viewmodels.scrcpy_display_controller as module

    for name in ("scrcpy.exe", "adb.exe", "scrcpy-server"):
        (tmp_path / name).touch()
    monkeypatch.setattr(module, "bundled_scrcpy_path", lambda: tmp_path / "scrcpy.exe")
    monkeypatch.setattr(module, "bundled_adb_path", lambda: tmp_path / "adb.exe")
    monkeypatch.setattr(module, "bundled_android_tools_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "BackgroundProcess", Process)
    android = Android()
    switches = []
    execution = SimpleNamespace(_scrcpy_serial="", _scrcpy_tool_id="", stop=lambda _: None,
                                switch_scrcpy_display=lambda *args: switches.append(args))
    controller = ScrcpyDisplayController(android, execution)
    controller.setEnabled(True)
    yield controller, android, switches
    controller.setEnabled(False)
    controller.deleteLater()


def test_display_parser_and_arguments():
    result = parse_displays('''[server] INFO: List of displays:
        --display-id=10    (1920x720)
        --display-id=0     (1080x2400)
        --display-id=2     (Cluster, 800x480)
        --display-id=10    (1920x720)
        unrelated version 4.0
    ''')
    assert [row["id"] for row in result] == ["0", "2", "10"]
    assert "Cluster" in result[1]["label"]
    assert "--display-id=10" in _projection_arguments("A", "test", display_id=10)
    assert "--display-id=0" in _projection_arguments("A", "test")


def test_query_selection_and_stale_results(screens):
    controller, android, switches = screens
    first = controller._process
    assert first.arguments == ["--serial", "A", "--list-displays"]
    first.stderrReady.emit(b"--display-id=0 (1080x2400)\n--display-id=9 (1920x720)")
    first.finished.emit(0)
    assert [row["id"] for row in controller.displays] == ["0", "9"]
    assert controller.selectDisplay("9")
    assert controller.selectedId == "9" and switches == [("A", 9)]
    controller.refresh()
    stale = controller._process
    android.select("B")
    current = controller._process
    stale.stdoutReady.emit(b"--display-id=99")
    stale.finished.emit(0)
    assert controller._process is current and controller.displays == []
    assert controller.selectedId == "0"
    android.select("A")
    assert controller.selectedId == "9"
    android.select("")
    assert not controller.deviceAvailable and not controller.loading


@pytest.mark.parametrize("value", ["", "-1", "1.5", "abc", "2147483648"])
def test_invalid_display_never_switches(screens, value):
    controller, _, switches = screens
    assert not controller.selectDisplay(value)
    assert controller.selectedId == "0" and not switches


def test_timeout_allows_manual_selection(screens):
    controller, _, switches = screens
    process = controller._process
    controller._timeout()
    assert process.killed and not controller.loading and "超时" in controller.error
    assert controller.selectDisplay("12")
    assert switches == [("A", 12)]


def test_disconnect_and_shutdown_cancel_pending_work(screens):
    controller, android, _ = screens
    stops = []
    controller.execution._scrcpy_serial = "A"
    controller.execution._scrcpy_tool_id = "cast"
    controller.execution.stop = stops.append
    process = controller._process
    android.select("")
    assert process.killed and stops == ["cast"]
    android.select("A")
    process = controller._process
    controller.shutdown()
    assert process.killed and not controller.loading
    assert stops == ["cast", "cast"]


def test_query_failure_keeps_manual_input_available(screens):
    controller, _, switches = screens
    process = controller._process
    process.stderrReady.emit(b"device offline")
    process.finished.emit(1)
    assert "device offline" in controller.error and not controller.loading
    assert controller.selectDisplay("3")
    assert switches == [("A", 3)]


def test_screen_restart_waits_and_stop_cancels(qapp):
    class Projection(QObject):
        output = Signal(str)
        started = Signal()
        runningChanged = Signal(bool)
        finished = Signal(int)
        active = False
        running = False

        def __init__(self):
            super().__init__()
            self.launches = []
            self.stops = 0

        def start(self, *args):
            self.launches.append(args)
            self.active = True
            return True

        def stop(self):
            self.stops += 1

    from poptools.domain.models import ToolDefinition

    projection = Projection()
    coordinator = ExecutionCoordinator(SimpleNamespace(python_environment=None, paths=None), 3,
                                       scrcpy=projection)
    tool = ToolDefinition(id="cast", title="Cast", section="preset",
                          executor={"kind": "internal", "command": "scrcpy"})
    assert not coordinator.switch_scrcpy_display("A", 3)
    assert projection.launches == []
    assert coordinator.start(tool, {"displayId": "0"}, "A")
    assert coordinator.running("cast")
    assert coordinator.switch_scrcpy_display("A", 3)
    assert projection.launches == [("A", 0)]
    assert coordinator.switch_scrcpy_display("A", 5)
    assert projection.stops == 1
    projection.active = False
    projection.finished.emit(0)
    assert projection.launches == [("A", 0), ("A", 5)]
    assert coordinator.switch_scrcpy_display("A", 8)
    coordinator.stop("cast")
    projection.active = False
    projection.finished.emit(0)
    assert len(projection.launches) == 2
    assert not coordinator.start(tool, {"displayId": "-1"}, "A")
    coordinator.deleteLater()


def test_old_stop_timer_does_not_kill_new_projection(qapp, monkeypatch):
    import poptools.infrastructure.scrcpy_controller as module

    callbacks = []
    monkeypatch.setattr(module.QTimer, "singleShot", lambda _, callback: callbacks.append(callback))
    controller = ScrcpyController()
    old = Process()
    new = Process()
    controller._process = old
    controller.stop()
    controller._process = new
    for callback in callbacks:
        callback()
    assert not new.terminated and not new.killed
    controller._process = None


@pytest.mark.gui
@pytest.mark.parametrize("titlebar", [False, True])
def test_selector_typing_waits_for_enter_and_dropdown_commits(screens, qtbot, titlebar):
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    controller, _, switches = screens
    process = controller._process
    process.stdoutReady.emit(b"--display-id=0 (1080x2400)\n--display-id=9 (1920x720)")
    process.finished.emit(0)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("screens", controller)
    component = QQmlComponent(engine)
    control = '''WindowTitleBar {
        objectName: "testTitleBar"
        width: parent.width; height: 40
        hostWindow: host
        presetActionsVisible: true
        presetToolController: testBackend
        QtObject {
            id: testBackend
            property var scrcpyDisplays: screens
            property bool running: false
        }
    }''' if titlebar else 'DisplaySelector { width: 190; backend: screens }'
    component.setData(('''import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 960; height: 300; visible: true
    property int titleBarHeight: 40
    property int captionControlWidth: 47
    property bool modernCaptionControls: true
    property rect titleBarActionsRect: Qt.rect(0, 0, 0, 0)
    CONTROL
}'''.replace("CONTROL", control)).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/DisplaySelectorHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        window.requestActivate()
        field = window.findChild(QQuickItem, "displayIdInput")
        if titlebar:
            rect = field.mapRectToItem(window.contentItem(), field.boundingRect())
            assert 0 <= rect.top() < rect.bottom() <= 40
            assert rect.right() < 960 - 3 * 47
            assert window.grabWindow().save(".tmp-display-titlebar.png")
        field.forceActiveFocus()
        field.setProperty("text", "12")
        assert not switches and controller.selectedId == "0"
        QTest.keyClick(window, Qt.Key_Return)
        assert switches == [("A", 12)]
        button = window.findChild(QObject, "displayListButton")
        if titlebar:
            rect = button.mapRectToItem(window.contentItem(), button.boundingRect())
            assert 0 <= rect.top() < rect.bottom() <= 40
            assert rect.right() < 960 - 3 * 47
        QTest.mouseClick(window, Qt.LeftButton,
                         pos=button.mapToScene(button.boundingRect().center()).toPoint())
        popup = window.findChild(QObject, "displaySelectorPopup")
        qtbot.waitUntil(lambda: popup.property("opened"))
        if titlebar:
            assert window.findChild(QObject, "testTitleBar").property("presetDevicePopupVisible")
        qtbot.wait(50)

        def descendants(item):
            yield item
            for child in item.childItems():
                yield from descendants(child)

        row = next(item for item in descendants(popup.property("contentItem"))
                   if item.property("text") == "屏幕 9 · 1920x720")
        QTest.mouseClick(window, Qt.LeftButton,
                         pos=row.mapToScene(row.boundingRect().center()).toPoint())
        assert switches[-1] == ("A", 9) and controller.selectedId == "9"
        assert field.property("text") == "9"
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
