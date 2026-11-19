import codecs
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import (
    Q_ARG,
    Q_RETURN_ARG,
    QCoreApplication,
    QEvent,
    QMetaObject,
    QObject,
    QPoint,
    Qt,
    QUrl,
)
from PySide6.QtGui import QColor, QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.conpty import ConPtySession
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


@pytest.mark.gui
@pytest.mark.parametrize("vertical", [False, True])
def test_drag_ungrouped_terminal_tabs_together_creates_group(terminal_workspace, qtbot, vertical):
    window, controller = terminal_workspace
    controller.setTerminalTabLayout("vertical" if vertical else "horizontal")
    first_id = controller.activeTerminalTabId
    controller.createTerminalTab()
    second_id = controller.activeTerminalTabId
    content = window.contentItem()
    strip = (find_item(content, "verticalTerminalTabs") if vertical
             else window.findChild(QObject, "titleBarTerminalTabs").property("item"))
    first = find_item(strip, "terminalTab_" + first_id)
    second = find_item(strip, "terminalTab_" + second_id)

    def bounds(item):
        return item.mapRectToItem(content, item.boundingRect())

    qtbot.waitUntil(lambda: strip.isVisible() and bounds(first) != bounds(second))
    step = QPoint(0, 13) if vertical else QPoint(13, 0)

    def drag(source, destination, direction):
        start = bounds(source).center().toPoint()
        QTest.mouseMove(window, start)
        QTest.mousePress(window, Qt.LeftButton, pos=start)
        QTest.mouseMove(window, start + direction, delay=15)
        QTest.mouseMove(window, destination)
        QTest.mouseRelease(window, Qt.LeftButton, pos=destination)

    edge = bounds(first).center().toPoint()
    if vertical:
        edge.setY(round(bounds(first).top()) + 3)
    else:
        edge.setX(round(bounds(first).left()) + 3)
    drag(second, edge, -step)
    assert [tab["tabId"] for tab in controller.terminalTabs] == [second_id, first_id]
    assert not controller.terminalTabGroups
    editor = strip.findChild(QObject, "terminalGroupEditor")
    assert not editor.property("visible")

    first = find_item(strip, "terminalTab_" + first_id)
    second = find_item(strip, "terminalTab_" + second_id)
    qtbot.waitUntil(lambda: bounds(second).center().toTuple() < bounds(first).center().toTuple())
    drag(first, bounds(second).center().toPoint(), -step)
    (group,) = controller.terminalTabGroups
    assert [tab["groupId"] for tab in controller.terminalTabs] == [group["groupId"]] * 2
    assert [tab["tabId"] for tab in controller.terminalTabs] == [second_id, first_id]
    assert controller.activeTerminalTabId == second_id
    qtbot.waitUntil(lambda: find_item(strip, "terminalGroup_" + group["groupId"]) is not None)
    qtbot.waitUntil(lambda: editor.property("opened"))
    assert editor.property("groupId") == group["groupId"]
    editor.findChild(QObject, "terminalGroupName").setProperty("text", "Build")
    QTest.keyClick(window, Qt.Key_Return)
    qtbot.waitUntil(lambda: not editor.property("visible"))
    assert controller.terminalTabGroups[0]["title"] == "Build"


@pytest.mark.gui
@pytest.mark.parametrize("vertical", [False, True])
def test_terminal_groups_selection_drag_and_collapse(terminal_workspace, qtbot, vertical):
    window, controller = terminal_workspace
    controller.setTerminalTabLayout("vertical" if vertical else "horizontal")
    first_id = controller.activeTerminalTabId
    controller.createTerminalTab()
    second_id = controller.activeTerminalTabId
    controller.createTerminalTab()
    third_id = controller.activeTerminalTabId
    content = window.contentItem()
    strip = (find_item(content, "verticalTerminalTabs") if vertical
             else window.findChild(QObject, "titleBarTerminalTabs").property("item"))
    qtbot.waitUntil(strip.isVisible)

    def item_for_tab(tab_id):
        return find_item(strip, "terminalTab_" + tab_id)

    def point(item):
        return item.mapRectToItem(content, item.boundingRect()).center().toPoint()

    def axis(item):
        position = point(item)
        return position.y() if vertical else position.x()

    def tab_items():
        return [item_for_tab(tab_id) for tab_id in (first_id, second_id, third_id)]

    first, second, third = tab_items()
    qtbot.waitUntil(lambda: len({point(first).toTuple(), point(second).toTuple(),
                               point(third).toTuple()}) == 3)
    QTest.mouseClick(window, Qt.LeftButton, Qt.ControlModifier, point(first))
    assert strip.property("selectedTabIds").toVariant() == [third_id, first_id]
    QTest.mouseClick(window, Qt.RightButton, pos=point(first))
    menu = strip.findChild(QObject, "terminalTabContextMenu")
    qtbot.waitUntil(lambda: menu.property("opened"))
    assert QMetaObject.invokeMethod(menu.findChild(QObject, "createTerminalGroup"), "triggered")
    menu.close()
    assert [tab["tabId"] for tab in controller.terminalTabs] == [first_id, third_id, second_id]
    group_id = controller.terminalTabGroups[0]["groupId"]
    editor = strip.findChild(QObject, "terminalGroupEditor")
    qtbot.waitUntil(lambda: editor.property("opened"))
    editor.findChild(QObject, "terminalGroupName").setProperty("text", "Build")
    QTest.keyClick(window, Qt.Key_Return)
    qtbot.waitUntil(lambda: not editor.property("visible"))
    assert controller.terminalTabGroups[0]["title"] == "Build"

    header = find_item(strip, "terminalGroup_" + group_id)
    first, second, third = tab_items()
    QTest.mouseClick(window, Qt.LeftButton, pos=point(header))
    qtbot.waitUntil(lambda: not first.isVisible() and not third.isVisible())
    assert controller.activeTerminalTabId == second_id
    QTest.mouseClick(window, Qt.LeftButton, pos=point(header))
    qtbot.waitUntil(lambda: first.isVisible() and third.isVisible()
                    and axis(header) < axis(first) < axis(third) < axis(second))

    if vertical:
        for tab_id in (first_id, third_id):
            item = item_for_tab(tab_id)
            indicator = find_item(strip, "terminalGroupIndicator_" + tab_id)
            selection = find_item(strip, "terminalTabSelection_" + tab_id)
            line_bounds = indicator.mapRectToItem(strip, indicator.boundingRect())
            QTest.mouseClick(window, Qt.LeftButton, pos=point(item))
            assert controller.activeTerminalTabId == tab_id
            assert selection.isVisible()
            assert indicator.mapRectToItem(strip, indicator.boundingRect()) == line_bounds
            assert line_bounds.right() < item.mapRectToItem(strip, item.boundingRect()).left()
            assert line_bounds.right() < selection.mapRectToItem(
                strip, selection.boundingRect(),
            ).left()

    start, destination = point(second), point(first)
    QTest.mouseMove(window, start)
    QTest.mousePress(window, Qt.LeftButton, pos=start)
    QTest.mouseMove(window, start - (QPoint(0, 13) if vertical else QPoint(13, 0)), delay=15)
    QTest.mouseMove(window, destination)
    assert strip.property("dragTabId") == second_id
    QTest.mouseRelease(window, Qt.LeftButton, pos=destination)
    qtbot.waitUntil(lambda: all(tab["groupId"] == group_id for tab in controller.terminalTabs))
    assert not editor.property("visible")

    controller.createTerminalTab()
    ungrouped_id = controller.activeTerminalTabId
    with qtbot.waitSignal(window.frameSwapped):
        window.update()
    ungrouped = item_for_tab(ungrouped_id)
    header = find_item(strip, "terminalGroup_" + group_id)
    qtbot.waitUntil(lambda: ungrouped is not None and ungrouped.isVisible()
                    and axis(header) < axis(ungrouped)
                    and axis(ungrouped) > max(map(axis, tab_items())))
    start = point(header)
    destination = point(ungrouped) + (QPoint(0, 10) if vertical else QPoint(20, 0))
    QTest.mouseMove(window, start)
    QTest.mousePress(window, Qt.LeftButton, pos=start)
    QTest.mouseMove(window, start + (QPoint(0, 13) if vertical else QPoint(13, 0)), delay=15)
    QTest.mouseMove(window, destination)
    assert strip.property("dragGroupId") == group_id
    QTest.mouseRelease(window, Qt.LeftButton, pos=destination)
    qtbot.waitUntil(lambda: controller.terminalTabs[0]["tabId"] == ungrouped_id)
    header = find_item(strip, "terminalGroup_" + group_id)
    ungrouped = item_for_tab(ungrouped_id)
    qtbot.waitUntil(lambda: axis(ungrouped) < axis(header))

    QTest.mouseClick(window, Qt.RightButton, pos=point(header))
    group_menu = strip.findChild(QObject, "terminalGroupContextMenu")
    qtbot.waitUntil(lambda: group_menu.property("opened"))
    assert QMetaObject.invokeMethod(
        group_menu.findChild(QObject, "confirmCloseTerminalGroup"), "triggered",
    )
    group_menu.close()
    confirmation = strip.findChild(QObject, "terminalGroupConfirmation")
    qtbot.waitUntil(lambda: confirmation.property("opened"))
    assert len(controller.terminalTabs) == 4
    button = confirmation.findChild(QObject, "executeTerminalGroupAction")
    assert QMetaObject.invokeMethod(button, "clicked")
    assert [tab["tabId"] for tab in controller.terminalTabs] == [ungrouped_id]
    assert not controller.terminalTabGroups
    assert find_item(strip, "savedTerminalGroupsButton") is None
    assert strip.findChild(QObject, "savedTerminalGroupMenu") is None
    qtbot.waitUntil(lambda: not confirmation.property("visible"))


@pytest.mark.gui
@pytest.mark.parametrize("terminal_workspace", ["restore-groups"], indirect=True)
def test_restored_terminal_group_is_collapsed_in_sidebar(terminal_workspace, qtbot):
    window, controller = terminal_workspace
    (group,) = controller.terminalTabGroups
    sidebar = find_item(window.contentItem(), "verticalTerminalTabs")
    header = find_item(sidebar, "terminalGroup_" + group["groupId"])
    active = find_item(sidebar, "terminalTab_" + controller.activeTerminalTabId)
    qtbot.waitUntil(header.isVisible)
    assert header.property("text") == "Project"
    assert header.property("collapsedActive")
    assert not active.isVisible()
    position = header.mapRectToItem(window.contentItem(), header.boundingRect()).center().toPoint()
    QTest.mouseClick(window, Qt.LeftButton, pos=position)
    qtbot.waitUntil(active.isVisible)


@pytest.fixture
def terminal_workspace(qapp, qtbot, tmp_path, monkeypatch, request):
    register_terminal_type()
    QFontDatabase.addApplicationFont(str(
        package_root() / "resources/fonts/MaterialIconsRound-Regular.otf"))
    paths = AppPaths(tmp_path)
    controller = DeveloperConsoleController(PythonEnvironment(paths, ConfigStore(paths)))
    if getattr(request, "param", None) == "restore-groups":
        controller.setTerminalTabLayout("vertical")
        first_id = controller.activeTerminalTabId
        controller.createTerminalTab()
        group_id = controller.createTerminalGroup([first_id, controller.activeTerminalTabId])
        controller.editTerminalGroup(group_id, "Project", "blue")
        controller.shutdown()
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
@pytest.mark.parametrize("dark,glass", [(False, False), (True, False), (False, True), (True, True)])
def test_history_selection_contrasts_with_terminal_syntax(terminal_workspace, qtbot, dark, glass):
    window, controller = terminal_workspace
    window.setProperty("glass", glass)
    # Exercise both directions of the live theme binding before starting a shell.
    window.setProperty("dark", not dark)
    window.setProperty("dark", dark)
    background = "#30445E" if dark else "#E5F0FF"
    terminal = window.findChild(QObject, "terminalView")
    assert terminal.property("historySelectionColor").name().upper() == background
    qtbot.waitUntil(
        lambda: controller._terminal_syntax_colors["command"] == ("#8CC8FF" if dark else "#075FAF")
    )
    colors = controller._terminal_syntax_colors

    def luminance(color):
        channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                  for c in channels]
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))

    selected = luminance(background)
    for name in ("default", "command", "warning", "string", "semantic", "operator", "error"):
        foreground = luminance(colors[name])
        contrast = (max(selected, foreground) + 0.05) / (min(selected, foreground) + 0.05)
        assert contrast >= 4.5, (name, colors[name], background, contrast)


@pytest.mark.gui
def test_real_powershell_history_repaints_when_theme_changes(terminal_workspace, qtbot, tmp_path):
    shell = shutil.which("pwsh")
    if sys.platform != "win32" or not shell:
        pytest.skip("Requires Windows ConPTY and PowerShell 7")

    window, controller = terminal_workspace
    terminal = window.findChild(QObject, "terminalView")
    session_id = controller.activeTerminalTabId
    profile = package_root() / "resources/tools/powershell-terminal-profile.ps1"
    quoted_profile = str(profile).replace("'", "''")
    startup = tmp_path / "start.ps1"
    startup.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f". '{quoted_profile}'\n"
        "Set-PSReadLineOption -HistorySaveStyle SaveNothing\n"
        "Set-PSReadLineOption -HistorySavePath (Join-Path $PSScriptRoot 'history.txt')\n"
        "function global:prompt { 'POPTOOLS-TEST> ' }\n",
        encoding="utf-8",
    )
    session = ConPtySession()
    output = bytearray()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")

    def receive(data):
        output.extend(data)
        terminal.feed(session_id, decoder.decode(data))

    session.outputReceived.connect(receive)
    session.start_process(
        Path(shell), ["-NoLogo", "-NoProfile", "-NoExit", "-ExecutionPolicy", "Bypass",
                      "-File", str(startup)],
        tmp_path, {**os.environ, "POPTOOLS_PS_HISTORY_LIST_VIEW": "1",
                   "POPTOOLS_PS_COLOR_COMMAND": "#075FAF"}, columns=70, rows=20,
    )
    try:
        try:
            qtbot.waitUntil(lambda: b"POPTOOLS-TEST>" in output, timeout=8000)
        except Exception as exc:
            raise AssertionError(repr(bytes(output)[-2000:])) from exc
        for command in (b"Write-Output PopToolsAlpha", b"Write-Output PopToolsBeta"):
            start = len(output)
            assert session.write(command + b"\r")
            qtbot.waitUntil(lambda start=start: b"POPTOOLS-TEST>" in output[start:])
        assert session.write(b"Write-O")
        try:
            qtbot.waitUntil(lambda: b"History" in output)
            assert session.write(b"\x1b[B")
            qtbot.waitUntil(lambda: b"48;2;48;68;95" in output, timeout=4000)
        except Exception as exc:
            raise AssertionError(repr(bytes(output)[-2000:])) from exc

        for dark, name in ((False, "#E5F0FF"), (True, "#30445E"), (False, "#E5F0FF")):
            window.setProperty("dark", dark)
            expected = QColor(name)

            def has_highlight(expected=expected):
                frame = window.grabWindow()
                return any(frame.pixelColor(x, y) == expected
                           for y in range(50, 250, 2) for x in range(500, 800, 12))

            qtbot.waitUntil(has_highlight, timeout=4000)
    finally:
        session.stop_process()
        session.wait(5000)
        session.dispose()


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
    qtbot.waitUntil(lambda: first.width() > 0 and
                    first.mapRectToItem(sidebar, first.boundingRect()).top() <
                    second.mapRectToItem(sidebar, second.boundingRect()).top())
    assert (first.mapRectToItem(sidebar, first.boundingRect()).left() ==
            second.mapRectToItem(sidebar, second.boundingRect()).left())
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
