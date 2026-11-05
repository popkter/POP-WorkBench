from types import SimpleNamespace

import pytest
from PySide6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    Qt,
    QUrl,
)
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.native_terminal import register_terminal_type
from poptools.paths import AppPaths, package_root
from poptools.viewmodels.developer_console_controller import DeveloperConsoleController


def test_layout_preferences_preserve_running_sessions_and_persist(tmp_path):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    controller = DeveloperConsoleController(PythonEnvironment(paths, store))
    try:
        tab = controller._active_tab()
        session = object()
        tab.session = session
        tab.output = "running command output"
        before = controller.terminalTabs
        for layout in ("vertical", "horizontal", "invalid", "vertical"):
            controller.setTerminalTabLayout(layout)
            assert controller.terminalTabs == before
            assert tab.session is session
            assert tab.output == "running command output"
        controller.setTerminalSidebarWidth(260)
        assert store.terminal_tab_layout() == "vertical"
        assert store.terminal_sidebar_width() == 260
        restored = DeveloperConsoleController(PythonEnvironment(paths, ConfigStore(paths)))
        assert restored.terminalTabLayout == "vertical"
        assert restored.terminalSidebarWidth == 260
        restored.shutdown()
        controller.setTerminalSidebarWidth(900)
        assert controller.terminalSidebarWidth == 360
        controller.setTerminalSidebarWidth(0)
        assert controller.terminalSidebarWidth == 140
    finally:
        tab.session = None
        controller.shutdown()


def find_item(parent, name):
    if parent.objectName() == name:
        return parent
    for child in parent.childItems():
        found = find_item(child, name)
        if found is not None:
            return found
    return None


@pytest.fixture
def terminal_workspace(qapp, qtbot, tmp_path, monkeypatch, request):
    register_terminal_type()
    QFontDatabase.addApplicationFont(str(
        package_root() / "resources/fonts/MaterialIconsRound-Regular.otf"))
    paths = AppPaths(tmp_path)
    controller = DeveloperConsoleController(PythonEnvironment(paths, ConfigStore(paths)))
    monkeypatch.setattr(controller, "_ensure_tab_started", lambda tab: True)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", controller)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
import "theme"
ApplicationWindow {
    id: host; width: 1000; height: 640; visible: true
    property bool dark: false
    property bool glass: false
    readonly property bool glassBackgroundReady: glass
    readonly property bool systemBackdropTinted: glass
    property bool customCaption: true
    property int titleBarHeight: 40
    property int captionControlWidth: 47
    property bool modernCaptionControls: true
    property int captionHovered: -1
    property int captionPressed: -1
    property rect titleBarActionsRect
    property var chromeController: null
    onDarkChanged: Theme.darkMode = dark
    onGlassChanged: Theme.glassMode = glass
    Component.onCompleted: { Theme.darkMode = dark; Theme.glassMode = false }
    color: Theme.chromeBackground
    WindowTitleBar {
        objectName: "title"; width: parent.width; height: 40
        visible: host.customCaption; hostWindow: host
        terminalController: backend; terminalTabsVisible: true
    }
    DeveloperConsole {
        objectName: "console"; x: 40; y: 40
        width: parent.width - x; height: parent.height - y
        parentWindow: host; controller: backend; tabsInTitleBar: host.customCaption
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/TerminalLayoutHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        yield window, controller
    finally:
        for tab in controller._tabs:
            tab.session = None
        controller.shutdown()
        window.close()
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        engine.deleteLater()


@pytest.mark.gui
@pytest.mark.parametrize("custom_caption", [False, True])
def test_layout_switch_resize_shortcuts_and_session_continuity(
    terminal_workspace, qtbot, custom_caption, tmp_path,
):
    window, controller = terminal_workspace
    window.setProperty("customCaption", custom_caption)
    terminal = window.findChild(QObject, "terminalView")
    qtbot.waitUntil(lambda: terminal.property("columns") > 40)
    for _ in range(2):
        controller.createTerminalTab()
    active = controller.activeTerminalTabId
    QMetaObject.invokeMethod(terminal, "feed", Qt.ConnectionType.DirectConnection,
                             Q_ARG(str, active), Q_ARG(str, "retained output\r\n"))
    resets = QSignalSpy(controller.terminalResetRequested)
    sizes = []
    session = SimpleNamespace(resize=lambda c, r: sizes.append((c, r)))
    controller._active_tab().session = session
    toggle = window.findChild(QObject, "terminalTabLayoutToggle")
    QMetaObject.invokeMethod(toggle, "triggered")
    sidebar = find_item(window.contentItem(), "verticalTerminalTabs")
    qtbot.waitUntil(sidebar.isVisible)
    title_tabs = window.findChild(QObject, "titleBarTerminalTabs")
    assert not title_tabs.property("active")
    assert window.property("titleBarActionsRect").width() == 0
    assert controller.activeTerminalTabId == active
    assert controller._active_tab().session is session
    assert window.findChild(QObject, "terminalView") is terminal
    assert resets.count() == 0
    first = find_item(sidebar, "terminalTab_" + controller.terminalTabs[0]["tabId"])
    second = find_item(sidebar, "terminalTab_" + controller.terminalTabs[1]["tabId"])
    qtbot.waitUntil(lambda: first.width() > 0 and first.y() < second.y())
    assert first.x() == second.x() == 0
    bounds = first.mapRectToItem(sidebar, first.boundingRect())
    assert bounds.left() >= 6 and bounds.right() <= sidebar.width() - 6
    assert window.findChild(QObject, "terminalSidebarSurface").property("radius") > 0
    assert window.findChild(QObject, "terminalContentSurface").property("radius") > 0
    qtbot.waitUntil(lambda: bool(sizes))
    divider = find_item(window.contentItem(), "terminalSidebarDivider")
    point = divider.mapRectToItem(window.contentItem(), divider.boundingRect()).center().toPoint()
    QTest.mousePress(window, Qt.LeftButton, pos=point)
    QTest.mouseMove(window, point + type(point)(60, 0))
    grip = window.findChild(QObject, "terminalSidebarGrip")
    assert grip.isVisible()
    assert grip.height() == 40 and grip.width() == 4
    assert not divider.inherits("QQuickRectangle")
    assert abs(grip.y() + grip.height() / 2 - divider.height() / 2) < 2
    with qtbot.waitSignal(window.frameSwapped):
        window.update()
    assert window.grabWindow().save(str(tmp_path / "vertical-terminal-dragging.png"))
    QTest.mouseRelease(window, Qt.LeftButton, pos=point + type(point)(60, 0))
    qtbot.waitUntil(lambda: controller.terminalSidebarWidth > 230)
    QTest.mouseMove(window, point + type(point)(200, 0))
    qtbot.waitUntil(lambda: not grip.isVisible())
    before = len(controller.terminalTabs)
    QTest.keyClick(window, Qt.Key_T, Qt.ControlModifier | Qt.ShiftModifier)
    qtbot.waitUntil(lambda: len(controller.terminalTabs) == before + 1)
    QTest.keyClick(window, Qt.Key_Tab, Qt.ControlModifier | Qt.ShiftModifier)
    assert controller.activeTerminalTabId == active
    QMetaObject.invokeMethod(toggle, "triggered")
    qtbot.waitUntil(lambda: not sidebar.isVisible())
    assert controller._active_tab().session is session
    assert resets.count() == 0
    assert QMetaObject.invokeMethod(terminal, "selectAll")
    assert "retained output" in QMetaObject.invokeMethod(
        terminal, "selectionText", Qt.DirectConnection, Q_RETURN_ARG(str))
    window.setProperty("dark", True)
    assert terminal.property("fillColor").lightnessF() < 0.5
    assert terminal.property("foregroundColor").lightnessF() > 0.8
    window.setProperty("dark", False)
    assert terminal.property("fillColor").lightnessF() > 0.8
    assert terminal.property("foregroundColor").lightnessF() < 0.5
    assert controller._active_tab().session is session
    assert resets.count() == 0


@pytest.mark.gui
@pytest.mark.parametrize("dark,glass", [(False, False), (True, False), (False, True), (True, True)])
def test_vertical_tabs_rename_close_scroll_and_empty_layout(
    terminal_workspace, qtbot, tmp_path, dark, glass,
):
    window, controller = terminal_workspace
    window.setProperty("dark", dark)
    window.setProperty("glass", glass)
    terminal = window.findChild(QObject, "terminalView")
    assert (terminal.property("fillColor").lightnessF() < 0.5) == dark
    assert (terminal.property("foregroundColor").lightnessF() > 0.8) == dark
    controller.setTerminalTabLayout("vertical")
    for index in range(20):
        controller.createTerminalTab()
        controller.renameTerminalTab(
            controller.activeTerminalTabId, f"项目 {index + 1} · PowerShell")
    sidebar = find_item(window.contentItem(), "verticalTerminalTabs")
    flick = find_item(sidebar, "terminalTabFlick")
    qtbot.waitUntil(lambda: flick.property("contentY") > 0)
    active = controller.activeTerminalTabId

    def active_visible():
        item = find_item(sidebar, "terminalTab_" + active)
        rect = item.mapRectToItem(flick, item.boundingRect())
        return rect.top() >= 0 and rect.bottom() <= flick.height() + 0.5

    qtbot.waitUntil(active_visible)
    tab = find_item(sidebar, "terminalTab_" + active)
    first_id = controller.terminalTabs[0]["tabId"]
    first_tab = find_item(sidebar, "terminalTab_" + first_id)
    controller.activateTerminalTab(first_id)
    qtbot.waitUntil(lambda: flick.property("contentY") == 0)
    first_point = first_tab.mapRectToItem(
        window.contentItem(), first_tab.boundingRect()).center().toPoint()
    QTest.mouseMove(window, first_point)
    QTest.mouseClick(window, Qt.LeftButton, pos=first_point)
    assert find_item(sidebar, "terminalTab_" + active) is tab
    assert find_item(sidebar, "terminalTab_" + first_id) is first_tab
    assert first_tab.property("selected") and not tab.property("selected")
    selected_glass = find_item(sidebar, "terminalTabGlass_" + first_id)
    previous_glass = find_item(sidebar, "terminalTabGlass_" + active)
    assert selected_glass.isVisible() == glass
    if glass:
        assert first_tab.property("color").alpha() == 0
        assert selected_glass.property("tintStrength") < 0.3
    for _ in range(3):
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        assert tab.property("color").alpha() == 0
        assert not previous_glass.isVisible()
    add_button = find_item(sidebar, "terminalTabAddButton")
    add_point = add_button.mapRectToItem(
        window.contentItem(), add_button.boundingRect()).center().toPoint()
    QTest.mouseMove(window, add_point)
    qtbot.waitUntil(lambda: add_button.property("hovered"))
    assert (add_button.property("color").lightnessF() < 0.6) == dark
    assert (add_button.property("contentColor").lightnessF() > 0.8) == dark
    controller.activateTerminalTab(active)
    qtbot.waitUntil(active_visible)
    point = tab.mapRectToItem(window.contentItem(), tab.boundingRect()).center().toPoint()
    QTest.mouseClick(window, Qt.LeftButton, pos=point)
    QTest.mouseClick(window, Qt.LeftButton, pos=point)
    field = find_item(sidebar, "terminalTabRename_" + active)
    qtbot.waitUntil(lambda: field.isVisible() and field.hasActiveFocus())
    field.setProperty("text", "设备日志 · 长时间运行的任务")
    QTest.keyClick(window, Qt.Key_Return)
    assert controller.terminalTabs[-1]["title"] == "设备日志 · 长时间运行的任务"
    with qtbot.waitSignal(window.frameSwapped):
        window.update()
    screenshot = tmp_path / f"vertical-terminal-{'dark' if dark else 'light'}.png"
    assert window.grabWindow().save(str(screenshot))
    QTest.mouseClick(window, Qt.RightButton, pos=point)
    tab_menu = sidebar.findChild(QObject, "terminalTabContextMenu")
    qtbot.waitUntil(lambda: tab_menu.property("opened"))
    tab_toggle = sidebar.findChild(QObject, "toggleTerminalTabLayout")
    assert tab_toggle.property("text") == "使用水平标签栏"
    QMetaObject.invokeMethod(tab_menu, "close")
    QTest.mouseClick(window, Qt.MiddleButton, pos=point)
    assert len(controller.terminalTabs) == 20
    controller.activateTerminalTab(controller.terminalTabs[0]["tabId"])
    qtbot.waitUntil(lambda: flick.property("contentY") == 0)
    while controller.terminalTabs:
        controller.closeTerminalTab(controller.activeTerminalTabId)
    assert sidebar.isVisible()
    # Empty terminals still expose the layout switch through the body menu.
    console = find_item(window.contentItem(), "console")
    point = console.mapToItem(window.contentItem(), console.width() - 100, 100).toPoint()
    QTest.mouseClick(window, Qt.RightButton, pos=point)
    menu = window.findChild(QObject, "terminalContextMenu")
    qtbot.waitUntil(lambda: menu.property("opened"))
    toggle = window.findChild(QObject, "terminalTabLayoutToggle")
    point = toggle.mapRectToItem(window.contentItem(), toggle.boundingRect()).center().toPoint()
    QTest.mouseClick(window, Qt.LeftButton, pos=point)
    qtbot.waitUntil(lambda: not sidebar.isVisible())
    title = find_item(window.contentItem(), "title")
    add = find_item(title, "terminalTabAddButton")
    assert add.x() == 0
    point = add.mapRectToItem(window.contentItem(), add.boundingRect()).center().toPoint()
    QTest.mouseClick(window, Qt.LeftButton, pos=point)
    assert len(controller.terminalTabs) == 1
