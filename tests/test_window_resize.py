"""Exercise client-drawn caption layout and real Windows non-client behavior."""

import ctypes
import sys
from ctypes import wintypes
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMargins, QObject, QSize, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.window_chrome import WindowChromeController, initial_window_size
from poptools.infrastructure.windows_integration import apply_windows_title_bar_theme
from poptools.paths import package_root


def caption_button(window, index):
    def find(item):
        if item.objectName() == f"captionButton{index}":
            return item
        for child in item.childItems():
            result = find(child)
            if result is not None:
                return result
        return None

    result = find(window.contentItem())
    assert result is not None
    return result


@pytest.fixture
def native_window(qapp):
    qml_dir = package_root() / "ui/qml"
    source = (qml_dir / "Main.qml").read_text(encoding="utf-8")
    header = source.split("    Binding {", 1)[0]
    closing = source.split("    onClosing: function (close) {", 1)[1]
    closing = "    onClosing: function (close) {" + closing.split(
        "    function resetParameters()", 1
    )[0]
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData((header + closing + """
    WindowTitleBar {
        objectName: "windowTitleBar"
        hostWindow: window
        width: parent.width
        height: window.titleBarContentInset
        visible: window.customTitleBar
        scriptActionsVisible: window.testScriptActions
        scriptSelected: window.testScriptSelected
        scriptEditable: true
        scriptRunning: window.testScriptRunning
        presetActionsVisible: window.testPresetActions
        recordingSelected: window.testRecordingSelected
        presetToolController: presetTestBackend
        recordingController: presetTestBackend
        androidBackend: window.testAndroidBackend
        selectedScript: window.testSelectedScript
        terminalController: window.testTerminalController
        terminalTabsVisible: window.testTerminalTabs
        onTerminalFocusRequested: window.testTerminalFocusRequests++
        onImportRequested: window.testAction = "import"
        onCreateRequested: window.testAction = "create"
        onShareRequested: window.testAction = "share"
        onEditRequested: window.testAction = "edit"
        onDeleteRequested: window.testAction = "delete"
        onRunRequested: window.testAction = "run"
    }
    property bool testScriptActions: false
    property bool testPresetActions: false
    property bool testRecordingSelected: false
    QtObject {
        id: presetTestBackend
        objectName: "presetTestBackend"
        property bool running: false
        property bool recording: false
        property bool exporting: false
        property string recordingOutputDirectory: "C:/recordings"
        property var selectedAndroidDevice: ({serial: "A", available: true, label: "Phone A"})
        property var androidDevices: []
        signal stateChanged()
        function runSelected(values) { window.testAction = "cast" }
        function stopExecution() { window.testAction = "stop-cast" }
        function startRecording(serial) { window.testAction = "record-" + serial }
        function stopRecording() { window.testAction = "stop-record" }
    }
    property var testAndroidBackend: null
    property var testSelectedScript: ({})
    property var testTerminalController: null
    property bool testTerminalTabs: false
    property int testTerminalFocusRequests: 0
    property bool testScriptSelected: true
    property bool testScriptRunning: false
    property string testAction: ""
    property bool testDarkMode: false
    onTestDarkModeChanged: Theme.darkMode = testDarkMode
    Component.onCompleted: Theme.darkMode = testDarkMode
    QtObject {
        id: trayController
        objectName: "tray"
        property bool available: false
        property bool quitting: false
        property int notifications: 0
        function notify_hidden() { notifications++ }
    }
}
""").encode(), QUrl.fromLocalFile(str(qml_dir / "NativeWindowHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    _window_chrome = WindowChromeController(window)
    assert QTest.qWaitForWindowExposed(window)
    tray = window.findChild(QObject, "tray")
    try:
        yield window, tray
    finally:
        tray.setProperty("quitting", True)
        window.close()
        window.deleteLater()
        engine.deleteLater()


def test_window_has_system_style_and_client_caption(native_window):
    window, _ = native_window
    assert not window.flags() & Qt.WindowType.FramelessWindowHint
    for flag in (
        Qt.WindowType.WindowSystemMenuHint,
        Qt.WindowType.WindowMinimizeButtonHint, Qt.WindowType.WindowMaximizeButtonHint,
        Qt.WindowType.WindowCloseButtonHint,
    ):
        assert window.flags() & flag
    assert window.minimumWidth() > 0 and window.minimumHeight() > 0
    assert window.frameGeometry().width() <= 1100
    assert window.frameGeometry().height() <= 740


@pytest.mark.parametrize("available,expected", [
    (QSize(2560, 1440), QSize(1100, 710)),
    (QSize(1366, 728), QSize(1100, 640)),
    (QSize(1280, 800), QSize(1088, 650)),
    (QSize(1024, 768), QSize(960, 640)),
])
def test_initial_size_accounts_for_native_frame_and_available_desktop(available, expected):
    assert initial_window_size(
        QSize(1100, 740), QSize(960, 640), available, QMargins(0, 30, 0, 0),
    ) == expected


def test_frame_metrics_keep_equal_chrome_bands_after_resize(native_window, qtbot):
    window, _ = native_window

    def bands_match():
        native_height = window.frameMargins().top()
        if window.property("customTitleBar"):
            title = window.findChild(QObject, "windowTitleBar")
            return (window.property("titleBarHeight") == 40
                    and window.property("titleBarContentInset") == 40
                    and title.property("height") == 40)
        return (window.property("nativeTitleBarHeight") == native_height
                and window.property("titleBarHeight") == max(40, native_height)
                and native_height + window.property("titleBarContentInset")
                == window.property("titleBarHeight"))

    qtbot.waitUntil(bands_match)
    window.showMaximized()
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowMaximized)
    qtbot.waitUntil(bands_match)
    window.showNormal()
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowNoState)
    window.resize(1000, 680)
    qtbot.waitUntil(bands_match)
    QTest.qWait(30)
    assert window.size() == QSize(1000, 680)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows title toolbar")
def test_title_toolbar_labels_clicks_and_hit_testing(native_window, qtbot):
    window, _ = native_window
    window.setProperty("testScriptActions", True)
    window.resize(960, 640)
    qtbot.waitUntil(lambda: window.property("titleBarActionsRect").width() > 0)
    user32 = ctypes.WinDLL("user32")
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    hwnd = int(window.winId())
    scale = window.devicePixelRatio()
    buttons = []
    for name, action in (("Import", "import"), ("Create", "create"), ("Share", "share"),
                         ("Edit", "edit"),
                         ("Delete", "delete"), ("Run", "run")):
        button = window.findChild(QObject, "titleBar" + name + "Script")
        buttons.append(button)
        assert not button.property("compact") and not button.property("showHoverTips")
        assert button.height() == 28 and button.width() > button.height()
        rect = button.mapRectToItem(window.contentItem(), button.boundingRect())
        assert rect.top() >= 0 and rect.bottom() <= 40
        assert rect.right() < window.width() - 3 * 47
        point = wintypes.POINT(round(rect.center().x() * scale), round(rect.center().y() * scale))
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        packed = (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)
        assert user32.SendMessageW(hwnd, 0x0084, 0, packed) == 1  # HTCLIENT, never HTCAPTION
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        assert window.property("testAction") == action
    window.setProperty("testScriptRunning", True)
    assert buttons[-1].property("text") == "停止运行"
    assert buttons[2].isEnabled()  # Sharing does not modify a running script.
    assert not buttons[3].isEnabled() and not buttons[4].isEnabled()
    window.setProperty("testScriptRunning", False)
    window.setProperty("testScriptSelected", False)
    assert all(not button.isEnabled() for button in buttons[2:])
    assert buttons[0].isEnabled() and buttons[1].isEnabled()
    window.setProperty("testScriptActions", False)
    qtbot.waitUntil(lambda: window.property("titleBarActionsRect").isEmpty())
    assert all(not button.isVisible() for button in buttons)


@pytest.mark.parametrize("recording", [False, True])
@pytest.mark.parametrize("window_width", [960, 1100])
def test_preset_title_actions_start_stop_and_availability(
    native_window, qtbot, recording, window_width,
):
    window, _ = native_window
    backend = window.findChild(QObject, "presetTestBackend")
    window.resize(window_width, 640)
    window.setProperty("testAndroidBackend", backend)
    window.setProperty("testRecordingSelected", recording)
    window.setProperty("testPresetActions", True)
    with qtbot.waitSignal(window.frameSwapped):
        window.update()
    button = terminal_title_item(window, "titleBarStartPreset")
    picker = terminal_title_item(window, "titleBarPresetDeviceSelector")
    for item in (button, picker):
        assert item.isVisible()
        rect = item.mapRectToItem(window.contentItem(), item.boundingRect())
        assert 0 <= rect.top() < rect.bottom() <= 40
        assert rect.right() < window_width - 3 * 47 - 32
        assert window.property("titleBarActionsRect").contains(rect.center())
    assert picker.property("compact")

    def click():
        rect = button.mapRectToItem(window.contentItem(), button.boundingRect())
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())

    click()
    assert window.property("testAction") == ("record-A" if recording else "cast")
    backend.setProperty("recording" if recording else "running", True)
    assert button.property("text") == ("结束记录" if recording else "结束投屏")
    assert not picker.isEnabled()
    backend.setProperty("selectedAndroidDevice", {"serial": "A", "available": False})
    backend.stateChanged.emit()
    assert button.isEnabled()  # A disconnected device must still allow stopping.
    click()
    assert window.property("testAction") == ("stop-record" if recording else "stop-cast")
    backend.setProperty("recording" if recording else "running", False)
    assert not button.isEnabled()
    backend.setProperty("selectedAndroidDevice", {"serial": "A", "available": True})
    backend.stateChanged.emit()
    assert button.isEnabled()
    if recording:
        backend.setProperty("recordingOutputDirectory", "")
        assert not button.isEnabled()
        backend.setProperty("recordingOutputDirectory", "C:/recordings")
        backend.setProperty("exporting", True)
        assert button.property("text") == "正在导出"
        assert not button.isEnabled() and not picker.isEnabled()
    window.setProperty("testPresetActions", False)
    qtbot.waitUntil(lambda: window.property("titleBarActionsRect").isEmpty())
    assert not button.isVisible() and not picker.isVisible()


@pytest.fixture
def terminal_title_window(native_window, tmp_path, monkeypatch, qtbot):
    from poptools.infrastructure.config_store import ConfigStore
    from poptools.infrastructure.python_environment import PythonEnvironment
    from poptools.paths import AppPaths
    from poptools.viewmodels.developer_console_controller import DeveloperConsoleController

    paths = AppPaths(tmp_path)
    controller = DeveloperConsoleController(PythonEnvironment(paths, ConfigStore(paths)))
    monkeypatch.setattr(controller, "_ensure_tab_started", lambda _tab: True)
    window, _ = native_window
    window.setProperty("testTerminalController", controller)
    window.setProperty("testTerminalTabs", True)
    qtbot.waitUntil(lambda: window.property("titleBarActionsRect").width() > 0)
    yield window, controller
    window.setProperty("testTerminalTabs", False)
    controller.shutdown()


def terminal_title_item(window, name):
    def find(item):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            result = find(child)
            if result is not None:
                return result
        return None

    result = find(window.contentItem())
    assert result is not None, name
    return result


@pytest.mark.skipif(sys.platform != "win32", reason="Windows device title toolbar")
@pytest.mark.parametrize("window_width", [960, 1100])
def test_device_picker_fits_caption_and_selects_devices(native_window, qtbot, tmp_path,
                                                      monkeypatch, window_width):
    from poptools.infrastructure.android_device_service import AndroidDevice, AndroidDeviceService
    from poptools.infrastructure.config_store import ConfigStore
    from poptools.paths import AppPaths
    from poptools.viewmodels.android_controller import AndroidController

    devices = AndroidDeviceService()
    monkeypatch.setattr(devices, "refresh", lambda: None)
    devices._set_devices([AndroidDevice("A", model="Phone_A"), AndroidDevice("B", model="Phone_B")])
    android = AndroidController(ConfigStore(AppPaths(tmp_path)), devices)
    window, _ = native_window
    window.resize(window_width, 640)
    window.setProperty("testAndroidBackend", android)
    window.setProperty("testSelectedScript", {
        "id": "test", "uses_android_device": True, "requires_android_device": True,
    })
    window.setProperty("testScriptActions", True)
    try:
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        picker = terminal_title_item(window, "titleBarDeviceSelector")
        assert picker.isVisible() and picker.property("compact")
        rect = picker.mapRectToItem(window.contentItem(), picker.boundingRect())
        run_button = window.findChild(QObject, "titleBarRunScript")
        run_rect = run_button.mapRectToItem(window.contentItem(), run_button.boundingRect())
        assert rect.left() >= run_rect.right()
        assert rect.right() <= window.width() - 3 * 47 - 30
        assert rect.height() == 28 and 0 <= rect.top() <= rect.bottom() <= 40
        user32 = ctypes.WinDLL("user32")
        user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
        user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                       ctypes.c_size_t, ctypes.c_ssize_t]
        user32.SendMessageW.restype = ctypes.c_ssize_t
        scale = window.devicePixelRatio()
        point = wintypes.POINT(round(rect.center().x() * scale), round(rect.center().y() * scale))
        user32.ClientToScreen(int(window.winId()), ctypes.byref(point))
        packed = (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)
        assert user32.SendMessageW(int(window.winId()), 0x0084, 0, packed) == 1
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        popup = picker.findChild(QObject, "toolDevicePopup")
        qtbot.waitUntil(lambda: popup.property("opened"))
        assert popup.property("width") == 240
        assert popup.property("y") >= 40
        assert 0 <= popup.property("x") <= window.width() - popup.property("width")
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        row = terminal_title_item(window, "deviceRow_B")
        row_rect = row.mapRectToItem(window.contentItem(), row.boundingRect())
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=row_rect.center().toPoint())
        assert android.available_device_for_tool("test") == "B"
        assert android.available_device_for_tool("another") == "B"
        qtbot.waitUntil(lambda: picker.findChild(QObject, "deviceSelectorLabel")
                        .property("text") == "Phone B")
        qtbot.waitUntil(lambda: not popup.property("opened"))
        window.setProperty("testSelectedScript", {"id": "ordinary"})
        assert picker.isVisible()
    finally:
        android.stopAutoRefresh()
        window.setProperty("testScriptActions", False)


def test_title_terminal_tabs_add_switch_rename_and_close(terminal_title_window, qtbot):
    window, controller = terminal_title_window

    def click(name, button=Qt.MouseButton.LeftButton):
        # Clicking a rebuilt delegate requires its layout to reach a rendered frame.
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        item = terminal_title_item(window, name)
        rect = item.mapRectToItem(window.contentItem(), item.boundingRect())
        assert 0 <= rect.top() < rect.bottom() <= window.property("titleBarHeight")
        QTest.mouseClick(window, button, pos=rect.center().toPoint())

    first_id = controller.activeTerminalTabId
    first_tab = terminal_title_item(window, "terminalTab_" + first_id)
    first_rect = first_tab.mapRectToItem(window.contentItem(), first_tab.boundingRect())
    caption_height = window.property("titleBarHeight")
    assert first_rect.left() == pytest.approx(caption_height)
    assert 0 < first_rect.top() < first_rect.bottom() < caption_height
    assert first_rect.center().y() == pytest.approx(caption_height / 2)
    assert first_tab.property("radius") > 0
    click("terminalTabAddButton")
    assert len(controller.terminalTabs) == 2
    second_id = controller.activeTerminalTabId
    click("terminalTab_" + first_id)
    assert controller.activeTerminalTabId == first_id
    # Double press opens an inline editor in the caption client area.
    click("terminalTab_" + first_id)
    editor = terminal_title_item(window, "terminalTabRename_" + first_id)
    qtbot.waitUntil(lambda: editor.isVisible() and editor.hasActiveFocus())
    editor.setProperty("text", "Build logs")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert controller.terminalTabs[0]["title"] == "Build logs"
    assert not terminal_title_item(window, "terminalTabRename_" + first_id).isVisible()
    click("terminalTab_" + second_id, Qt.MouseButton.MiddleButton)
    assert len(controller.terminalTabs) == 1
    click("terminalTab_" + first_id, Qt.MouseButton.MiddleButton)
    assert controller.terminalTabs == []
    click("terminalTabAddButton")
    assert len(controller.terminalTabs) == 1
    assert window.property("testTerminalFocusRequests") >= 6
    surviving_id = controller.activeTerminalTabId
    QTest.keyClick(window, Qt.Key.Key_T, Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert len(controller.terminalTabs) == 2
    QTest.keyClick(window, Qt.Key.Key_Tab, Qt.KeyboardModifier.ControlModifier)
    assert controller.activeTerminalTabId == surviving_id
    click("terminalTabClose_" + surviving_id)
    assert len(controller.terminalTabs) == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows title tab hit testing")
def test_title_terminal_overflow_preserves_drag_and_caption_controls(terminal_title_window, qtbot):
    window, controller = terminal_title_window
    user32 = ctypes.WinDLL("user32")
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                   ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    scale = window.devicePixelRatio()

    def hit(x, y):
        point = wintypes.POINT(round(x * scale), round(y * scale))
        user32.ClientToScreen(int(window.winId()), ctypes.byref(point))
        packed = (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)
        return user32.SendMessageW(int(window.winId()), 0x0084, 0, packed)

    # A short tab list leaves the rest of the title bar available for dragging.
    actions = window.property("titleBarActionsRect")
    assert hit(actions.center().x(), 20) == 1  # HTCLIENT
    assert hit(actions.right() + 20, 20) == 2  # HTCAPTION
    backward = terminal_title_item(window, "terminalTabsScrollBackward")
    forward = terminal_title_item(window, "terminalTabsScrollForward")
    assert not backward.isVisible() and not forward.isVisible()
    for _ in range(12):
        controller.createTerminalTab()
    window.resize(960, 640)
    flick = terminal_title_item(window, "terminalTabFlick")
    qtbot.waitUntil(lambda: flick.property("contentX") > 0)
    assert flick.property("contentWidth") > flick.width()

    def active_tab_is_visible():
        tab = terminal_title_item(window, "terminalTab_" + controller.activeTerminalTabId)
        rect = tab.mapRectToItem(flick, tab.boundingRect())
        return rect.left() >= -0.5 and rect.right() <= flick.width() + 0.5

    qtbot.waitUntil(active_tab_is_visible)
    assert backward.isVisible() and forward.isVisible()
    assert backward.isEnabled() and not forward.isEnabled()
    assert not any(child.inherits("QQuickScrollBar") for child in flick.findChildren(QObject))

    def click_bumper(button):
        rect = button.mapRectToItem(window.contentItem(), button.boundingRect())
        assert hit(rect.center().x(), rect.center().y()) == 1
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())

    selected_id = controller.activeTerminalTabId
    end_offset = flick.property("contentX")
    click_bumper(backward)
    qtbot.waitUntil(lambda: flick.property("contentX") < end_offset)
    assert forward.isEnabled()
    assert controller.activeTerminalTabId == selected_id
    click_bumper(forward)
    qtbot.waitUntil(lambda: abs(flick.property("contentX") - end_offset) < 0.5)
    assert not forward.isEnabled()
    # Holding a bumper continues scrolling without selecting or closing tabs.
    rect = backward.mapRectToItem(window.contentItem(), backward.boundingRect())
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
    try:
        qtbot.waitUntil(lambda: end_offset - flick.property("contentX") >= 100)
    finally:
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
    assert controller.activeTerminalTabId == selected_id
    add = terminal_title_item(window, "terminalTabAddButton")
    add_rect = add.mapRectToItem(window.contentItem(), add.boundingRect())
    assert hit(add_rect.center().x(), add_rect.center().y()) == 1
    assert hit(window.width() - 3 * 47 - 32, 20) == 2
    assert hit(window.width() - 24, 20) == 20  # HTCLOSE
    controller.activateTerminalTab(controller.terminalTabs[0]["tabId"])
    qtbot.waitUntil(lambda: flick.property("contentX") == 0)
    qtbot.waitUntil(active_tab_is_visible)
    assert not backward.isEnabled() and forward.isEnabled()
    window.showMaximized()
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowMaximized)
    add_rect = add.mapRectToItem(window.contentItem(), add.boundingRect())
    assert hit(add_rect.center().x(), add_rect.center().y()) == 1
    controller.closeOtherTerminalTabs(controller.activeTerminalTabId)
    qtbot.waitUntil(lambda: not backward.isVisible() and not forward.isVisible())
    qtbot.waitUntil(lambda: flick.property("contentX") == 0)
    qtbot.waitUntil(active_tab_is_visible)
    window.setProperty("testTerminalTabs", False)
    qtbot.waitUntil(lambda: window.property("titleBarActionsRect").isEmpty())


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native frame")
def test_windows_frame_and_system_commands(native_window, qtbot):
    window, tray = native_window
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    hwnd = ctypes.c_void_p(int(window.winId()))
    style = user32.GetWindowLongPtrW(hwnd, -16)
    for expected in (0x00C00000, 0x00080000, 0x00040000, 0x00020000, 0x00010000):
        assert style & expected == expected  # caption, menu, resize, minimize, maximize
    for command, state in (
        (0xF020, Qt.WindowState.WindowMinimized),
        (0xF120, Qt.WindowState.WindowNoState),
        (0xF030, Qt.WindowState.WindowMaximized),
        (0xF120, Qt.WindowState.WindowNoState),
    ):
        user32.SendMessageW(hwnd, 0x0112, command, 0)  # WM_SYSCOMMAND
        qtbot.waitUntil(lambda expected=state: window.windowState() == expected)
        style = user32.GetWindowLongPtrW(hwnd, -16)
        assert bool(style & 0x01000000) == (state == Qt.WindowState.WindowMaximized)
    tray.setProperty("available", True)
    user32.SendMessageW(hwnd, 0x0112, 0xF060, 0)  # SC_CLOSE keeps close-to-tray behavior
    qtbot.waitUntil(lambda: not window.isVisible())
    assert tray.property("notifications") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows caption hit testing")
def test_caption_hit_targets_states_and_mouse_commands(native_window, qtbot):
    window, tray = native_window
    user32 = ctypes.WinDLL("user32")
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                    ctypes.c_size_t, ctypes.c_ssize_t]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    hwnd = int(window.winId())
    scale = window.devicePixelRatio()

    def send(code, hit=0, position=0):
        return user32.SendMessageW(hwnd, code, hit, position)

    def at(x, y):
        point = wintypes.POINT(round(x * scale), round(y * scale))
        user32.ClientToScreen(hwnd, ctypes.byref(point))
        return (point.x & 0xFFFF) | ((point.y & 0xFFFF) << 16)

    for index, hit in enumerate((8, 9, 20)):
        x = window.width() - (2.5 - index) * 47
        for y in (5, 20, 39):
            position = at(x, y)
            assert send(0x0084, 0, position) == hit
        send(0x00A0, hit, position)
        assert window.property("captionHovered") == index
        button = caption_button(window, index)
        assert button.property("width") == 47
        assert button.property("height") == 40
        send(0x00A1, hit, position)
        assert window.property("captionPressed") == index
        # SetCapture switches to client mouse input. Its synthetic NC leave
        # must not erase the pressed visual before the next mouse movement.
        send(0x02A2)
        assert button.property("pressed")
        send(0x0200, 1, (round(150 * scale) << 16) | round(300 * scale))
        assert not button.property("pressed")
        send(0x0200, 1, (round(20 * scale) << 16) | round(x * scale))
        assert button.property("pressed")
        # Dragging outside and releasing must cancel, rather than close/minimize.
        send(0x00A2, 1, at(300, 150))
        assert window.property("captionPressed") == -1
        assert window.isVisible() and window.windowState() == Qt.WindowState.WindowNoState
    assert send(0x0084, 0, at(100, 20)) == 2  # title drag region
    assert send(0x0084, 0, at(100, 100)) == 1  # ordinary client content
    assert send(0x0084, 0, at(0, 100)) == 10  # left native resize border
    send(0x00A3, 2, at(100, 20))  # Native title-bar double-click.
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowMaximized)
    send(0x00A3, 2, at(100, 20))
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowNoState)
    # Native caption click maximizes and changes the glyph to restore.
    send(0x00A1, 9, at(window.width() - 70, 20))
    send(0x00A2, 9, at(window.width() - 70, 20))
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowMaximized)
    assert not caption_button(window, 1).property("restored")
    window.showNormal()
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowNoState)
    tray.setProperty("available", True)
    send(0x00A1, 20, at(window.width() - 24, 20))
    send(0x00A2, 20, at(window.width() - 24, 20))
    qtbot.waitUntil(lambda: not window.isVisible())
    assert tray.property("notifications") == 1


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DWM frame geometry")
def test_dwm_has_a_real_border_and_maximized_client_fits_work_area(native_window, qtbot):
    window, _ = native_window
    user32 = ctypes.WinDLL("user32")
    hwnd = int(window.winId())
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    rect = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    assert origin.x - rect.left == origin.y - rect.top == 1
    assert not user32.GetWindowLongPtrW(hwnd, -20) & 0x00080000  # No WS_EX_LAYERED.
    client = wintypes.RECT()
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect(hwnd, ctypes.byref(client))
    scale = window.devicePixelRatio()
    assert abs(client.right - round(window.width() * scale)) <= 1
    assert abs(client.bottom - round(window.height() * scale)) <= 1
    window.showMaximized()
    qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowMaximized)
    client = wintypes.RECT()
    origin = wintypes.POINT(0, 0)
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect(hwnd, ctypes.byref(client))
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    from poptools.infrastructure.windows_frame import _MonitorInfo

    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)]
    monitor = _MonitorInfo(size=ctypes.sizeof(_MonitorInfo))
    assert user32.GetMonitorInfoW(user32.MonitorFromWindow(hwnd, 2), ctypes.byref(monitor))
    assert client.right == monitor.work.right - monitor.work.left
    assert client.bottom == monitor.work.bottom - monitor.work.top
    assert origin.x == monitor.work.left and origin.y == monitor.work.top


@pytest.mark.parametrize("dark_mode", [False, True])
def test_caption_paints_pressed_hover_inactive_and_disabled_states(native_window, dark_mode, qtbot):
    window, _ = native_window
    window.setProperty("testDarkMode", dark_mode)
    close = caption_button(window, 2)
    background = close.findChild(QObject, "captionBackground")
    window.setProperty("captionHovered", 2)
    assert background.property("color").name() == "#c42b1c"
    assert close.property("foreground").name() == "#ffffff"
    window.setProperty("captionPressed", 2)
    assert background.property("color").alpha() == 229
    assert background.property("color").name() == "#c32b1b"
    window.setProperty("captionHovered", -1)
    assert background.property("color").alpha() == 0
    window.hide()
    qtbot.waitUntil(lambda: not window.isActive())
    assert close.property("foreground").alpha() == 96
    close.setProperty("enabled", False)
    assert close.property("foreground").alpha() == 51


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DWM theme")
@pytest.mark.parametrize("dark_mode", [False, True])
def test_native_title_bar_theme(native_window, dark_mode, monkeypatch):
    window, _ = native_window
    if sys.getwindowsversion().build < 22000:
        pytest.skip("DWM dark title bar attribute requires Windows 11")
    window.setProperty("testDarkMode", dark_mode)
    background = window.property("chromeBackgroundColor")
    foreground = window.property("chromeForegroundColor")
    assert window.property("color") == background
    assert background.name() == ("#2b2d30" if dark_mode else "#f7f8fa")
    hwnd = int(window.winId())
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    native_set_attribute = dwmapi.DwmSetWindowAttribute
    native_set_attribute.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
    ]
    native_set_attribute.restype = ctypes.c_long
    applied = {}

    def record_attribute(handle, attribute, value, size):
        result = native_set_attribute(handle, attribute, value, size)
        applied[attribute] = (
            ctypes.cast(value, ctypes.POINTER(ctypes.c_uint)).contents.value, result,
        )
        return result

    # Caption colors support setting but cannot be queried with DwmGetWindowAttribute.
    # Record the values while still applying them to the real native window.
    with monkeypatch.context() as patch:
        patch.setattr(ctypes, "WinDLL", lambda *args, **kwargs: SimpleNamespace(
            DwmSetWindowAttribute=record_attribute,
        ))
        apply_windows_title_bar_theme(
            hwnd, dark_mode=dark_mode, background_color=background, foreground_color=foreground,
        )
    dwmapi.DwmGetWindowAttribute.argtypes = [
        ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint,
    ]
    dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long
    enabled = ctypes.c_int()
    assert dwmapi.DwmGetWindowAttribute(
        ctypes.c_void_p(hwnd), 20, ctypes.byref(enabled), ctypes.sizeof(enabled),
    ) == 0
    assert bool(enabled.value) == dark_mode
    assert applied[33] == (2, 0)  # DWM rounds all four corners of a restored window.
    for attribute, color in ((34, background), (35, background), (36, foreground)):
        expected = color.red() | (color.green() << 8) | (color.blue() << 16)
        assert applied[attribute] == (expected, 0)


@pytest.mark.parametrize("available,quitting,hidden", [
    (False, False, 0), (True, False, 1), (True, True, 0),
])
def test_native_close_preserves_tray_behavior(native_window, available, quitting, hidden):
    window, tray = native_window
    tray.setProperty("available", available)
    tray.setProperty("quitting", quitting)
    assert window.close() == (not hidden)
    assert not window.isVisible()
    assert tray.property("notifications") == hidden
