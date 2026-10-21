from pathlib import Path

import pytest
from PySide6.QtCore import Q_ARG, QEvent, QMetaObject, QObject, QPoint, QPointF, QRect, Qt, QUrl
from PySide6.QtGui import QCursor, QFontDatabase, QMouseEvent, QRegion, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.system_tray import SystemTrayController
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.native_terminal import register_terminal_type, terminal_library_path
from poptools.paths import AppPaths, package_root, resource_path
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.app_controller import AppController
from poptools.viewmodels.developer_console_controller import DeveloperConsoleController
from poptools.viewmodels.floating_launcher_controller import (
    FloatingLauncherController,
    edge_geometry,
)
from poptools.viewmodels.jira_feishu_controller import JiraFeishuController
from poptools.viewmodels.preset_controller import PresetController
from poptools.viewmodels.settings_controller import SettingsController
from poptools.viewmodels.tool_session_controller import ToolSessionController
from poptools.viewmodels.update_controller import UpdateController


@pytest.fixture
def launcher(qapp, tmp_path, monkeypatch):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    environment = PythonEnvironment(paths, store)
    coordinator = ExecutionCoordinator(ExecutionManager(paths, environment), 3)
    registry = ToolRegistry(resource_path("tools"), JsonToolRepository(paths))
    android = AndroidController(store)
    android.stopAutoRefresh()
    backend = AppController(registry, coordinator, store, android)
    settings = SettingsController(store, environment, coordinator)
    controller = FloatingLauncherController(qapp, backend, settings)
    main = QWindow()
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda: False)
    controller.attach_main_window(main)
    controller.reconcile()
    yield controller, backend, settings, main
    controller.shutdown()
    backend._analysis_timer.stop()
    backend._console_refresh_timer.stop()
    main.close()
    main.deleteLater()
    controller.deleteLater()
    settings.deleteLater()
    backend.deleteLater()
    android.deleteLater()
    coordinator.deleteLater()


def create_tool(backend, title, kind="python", command="print('hello')"):
    tool = backend.registry.create_custom(
        title=title, description="示例说明", kind=kind, command=command,
    )
    backend.reloadImportedScripts()
    return tool


def ids(model):
    return [model.data(model.index(i, 0), model.IdRole) for i in range(model.rowCount())]


@pytest.mark.parametrize("ratio", [0, 0.5, 1])
@pytest.mark.parametrize("available", [QRect(0, 0, 1920, 1040), QRect(-1280, -100, 1280, 720),
                                       QRect(50, 20, 300, 250)])
def test_geometry_keeps_both_windows_visible_and_adjacent(available, ratio):
    notch, panel = edge_geometry(available, (44, 108), (360, 480), ratio)
    assert available.contains(notch)
    assert available.contains(panel)
    assert notch.right() == available.right()
    assert panel.right() + 1 == notch.left()


@pytest.mark.parametrize("ratio", [0, 0.5, 1])
@pytest.mark.parametrize("available", [QRect(0, 0, 1920, 1040), QRect(-1280, -100, 1280, 720),
                                       QRect(50, 20, 300, 250)])
def test_drawer_tip_and_list_move_together_with_an_exact_input_mask(
    launcher, qapp, monkeypatch, available, ratio,
):
    controller, _, _, _ = launcher

    class Screen:
        def name(self):
            return "drawer-screen"

        def availableGeometry(self):
            return available

    screen = Screen()
    monkeypatch.setattr(qapp, "screens", lambda: [screen])
    monkeypatch.setattr(qapp, "primaryScreen", lambda: screen)
    controller._screen = screen
    controller._ratio = ratio
    drawer = QWindow()
    drawer.setFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
    controller.attachDrawerWindow(drawer, 24, 64, 360, 480)
    drawer.show()
    stable_geometry = drawer.geometry()
    collapsed_y = drawer.y() + controller.drawerTipOffset
    try:
        for progress in (0, 0.25, 1, 0.5, 0):
            controller.setDrawerProgress(progress)
            assert available.contains(drawer.geometry())
            assert drawer.geometry().right() == available.right()
            assert drawer.geometry() == stable_geometry
            body_width = drawer.width() - 24
            exposed_width = int(body_width * progress + 0.5)
            offset = body_width - exposed_width
            assert drawer.mask().boundingRect().width() == 24 + exposed_width
            tip = QPoint(offset + 12, controller.drawerTipOffset + 32)
            assert drawer.y() + controller.drawerTipOffset == collapsed_y
            assert drawer.mask().contains(tip)
            monkeypatch.setattr(QCursor, "pos", lambda point=tip: drawer.position() + point)
            assert controller._pointer_inside()
            if controller.drawerTipOffset:
                blank = QPoint(1, 1)
                assert not drawer.mask().contains(blank)
                monkeypatch.setattr(QCursor, "pos", lambda point=blank: drawer.position() + point)
                assert not controller._pointer_inside()
    finally:
        controller.shutdown()
        drawer.close()
        drawer.deleteLater()


def test_preferences_default_malformed_and_persist(tmp_path):
    store = ConfigStore(AppPaths(tmp_path))
    assert store.floating_launcher_enabled()
    assert store.floating_launcher_position() == ("", 0.5)
    store.set_floating_launcher_enabled(False)
    store.set_floating_launcher_position("external", 0.8)
    restarted = ConfigStore(store.paths)
    assert not restarted.floating_launcher_enabled()
    assert restarted.floating_launcher_position() == ("external", 0.8)
    raw = store.load_config()
    raw["app"]["floating_launcher_position"] = {"screen": [], "vertical_ratio": "invalid"}
    store.save_config(raw)
    assert store.floating_launcher_position() == ("", 0.5)


def test_foreground_setting_and_shutdown_collapse(launcher, monkeypatch):
    controller, _, settings, _ = launcher
    assert controller.visible
    controller.toggleExpanded()
    assert controller.expanded
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda: True)
    controller.reconcile()
    assert not controller.visible and not controller.expanded
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda: False)
    controller.reconcile()
    assert controller.visible
    settings.saveFloatingLauncherEnabled(False)
    assert not controller.visible
    settings.saveFloatingLauncherEnabled(True)
    assert controller.visible
    controller.shutdown()
    assert not controller.visible and not controller.expanded


def test_mouse_leave_delay_menu_and_drag(launcher, qtbot, monkeypatch):
    controller, _, settings, _ = launcher
    monkeypatch.setattr(controller, "_pointer_inside", lambda: False)
    controller.toggleExpanded()
    controller.pointerChanged()
    qtbot.wait(100)
    assert controller.expanded
    controller.setMenuOpen(True)
    qtbot.wait(320)
    assert controller.expanded
    controller.setMenuOpen(False)
    qtbot.waitUntil(lambda: not controller.expanded)
    controller.toggleExpanded()
    controller.pointerChanged()
    monkeypatch.setattr(controller, "_pointer_inside", lambda: True)
    controller.pointerChanged()
    qtbot.wait(320)
    assert controller.expanded
    controller.beginDrag()
    assert not controller.expanded
    controller.toggleExpanded()
    assert not controller.expanded
    controller.dragTo(999999)
    controller.endDrag()
    assert settings.config_store.floating_launcher_position()[1] == 1


def test_independent_all_scripts_filter_sort_and_updates(launcher):
    controller, backend, _, _ = launcher
    beta = create_tool(backend, "Beta")
    alpha = create_tool(backend, "Alpha", kind="powershell")
    backend.setToolSearchQuery("Beta")
    controller.setToolSortMode("name")
    assert ids(controller.toolsModel) == [alpha.id, beta.id]
    assert ids(backend.toolsModel) == [beta.id]
    backend.navigate("preset")
    assert ids(controller.toolsModel) == [alpha.id, beta.id]
    controller.setToolSearchQuery("alpha")
    assert ids(controller.toolsModel) == [alpha.id]
    assert controller.toolsModel.countForKind("python") == 0
    controller.toggleExpanded()
    controller.collapse()
    controller.toggleExpanded()
    assert ids(controller.toolsModel) == [alpha.id]
    backend.registry.delete(alpha.id)
    backend.reloadImportedScripts()
    assert controller.toolsModel.count == 0
    assert controller.toolsModel.totalCount == 1


def test_settings_click_collapses_and_requests_navigation(launcher, qtbot):
    controller, _, _, _ = launcher
    controller.toggleExpanded()
    with qtbot.waitSignal(controller.settingsRequested):
        controller.openSettings()
    assert not controller.expanded


def test_saved_screen_geometry_changes_and_disconnection(launcher, qapp, monkeypatch):
    controller, _, settings, _ = launcher

    class Screen:
        def __init__(self, name, geometry):
            self._name, self.geometry = name, geometry

        def name(self):
            return self._name

        def availableGeometry(self):
            return self.geometry

    primary = Screen("primary", QRect(0, 0, 1920, 1040))
    external = Screen("external", QRect(-1280, 0, 1280, 720))
    screens = [primary, external]
    monkeypatch.setattr(qapp, "screens", lambda: screens)
    monkeypatch.setattr(qapp, "primaryScreen", lambda: primary)
    notch, panel = QWindow(), QWindow()
    controller.attachWindows(notch, panel, 44, 108, 360, 480)
    controller._screen = None
    controller._screen_name = "external"
    controller._ratio = 0.8
    controller.reposition()
    assert external.geometry.contains(notch.geometry())
    assert notch.geometry().right() == external.geometry.right()
    external.geometry = QRect(-1024, 100, 1024, 600)
    controller.reposition()
    assert external.geometry.contains(panel.geometry())
    screens.remove(external)
    controller._screen_removed(external)
    controller.reposition()
    assert primary.geometry.contains(notch.geometry())
    controller.endDrag()
    assert settings.config_store.floating_launcher_position() == ("primary", 0.8)


@pytest.mark.parametrize("expanded", [False, True])
def test_grip_drag_uses_screen_coordinates_after_leaving_window(
    launcher, qapp, qtbot, monkeypatch, expanded,
):
    controller, _, settings, _ = launcher
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        package_root() / "ui/qml/components/FloatingLauncher.qml"
    )))
    root = component.createWithInitialProperties({"controller": controller})
    assert root is not None, [e.toString() for e in component.errors()]
    notch = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    qtbot.waitUntil(notch.isVisible)
    assert QTest.qWaitForWindowExposed(notch)
    if expanded:
        controller.toggleExpanded()
        qtbot.waitUntil(lambda: notch.property("revealProgress") == 1)
    qtbot.wait(30)
    initial = notch.position()
    initial_tip_y = notch.y() + controller.drawerTipOffset
    tip = root.findChild(QObject, "floatingDrawerTip")
    grab = tip.mapRectToItem(notch.contentItem(), tip.boundingRect()).topLeft().toPoint()
    grab += QPoint(12, 10)
    pointer = initial + grab
    monkeypatch.setattr(QCursor, "pos", lambda: QPoint(pointer))

    def send(kind, delta, pressed=True):
        pointer.setX(initial.x() + grab.x() + delta.x())
        pointer.setY(initial.y() + grab.y() + delta.y())
        # Native window-move events can retain local coordinates from the previous
        # window geometry. Deliberately keep this frame fixed to reproduce that.
        local = QPointF(grab + delta)
        event = QMouseEvent(
            kind, local, local, QPointF(pointer),
            Qt.MouseButton.NoButton if kind == QEvent.Type.MouseMove else Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton if pressed else Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(notch, event)

    try:
        send(QEvent.Type.MouseButtonPress, QPoint())
        assert not controller.dragging  # A press alone is still a possible Tip click.
        for delta in (QPoint(-120, 0), QPoint(-120, 40), QPoint(-180, 40),
                      QPoint(-120, -40), QPoint(-180, -40), QPoint(0, 0)):
            send(QEvent.Type.MouseMove, delta)
            assert controller.dragging
            assert notch.x() == initial.x()
            assert notch.y() + controller.drawerTipOffset == initial_tip_y + delta.y()
        send(QEvent.Type.MouseButtonRelease, QPoint(), pressed=False)
        assert not controller.dragging
        assert controller.expanded == expanded
        saved = settings.config_store.floating_launcher_position()
        send(QEvent.Type.MouseMove, QPoint(-120, 60), pressed=False)
        assert notch.position() == initial
        assert settings.config_store.floating_launcher_position() == saved
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


def test_script_panel_ignores_repeated_clicks_and_slides_closed(launcher, qtbot, monkeypatch):
    controller, _, _, _ = launcher
    monkeypatch.setattr(controller, "_pointer_inside", lambda: True)
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        package_root() / "ui/qml/components/FloatingLauncher.qml"
    )))
    root = component.createWithInitialProperties({"controller": controller})
    assert root is not None, [error.toString() for error in component.errors()]
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    button = root.findChild(QObject, "floatingDragGrip")
    animation = root.findChild(QObject, "floatingPanelSlideAnimation")
    surface = root.findChild(QObject, "floatingDrawerSurface")
    animation.setProperty("duration", 400)
    visibility = []
    panel.visibleChanged.connect(visibility.append)

    def click():
        rect = button.mapRectToItem(panel.contentItem(), button.boundingRect())
        QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())

    try:
        assert QTest.qWaitForWindowExposed(panel)
        tip_width = root.findChild(QObject, "floatingDrawerTip").width()
        body_width = panel.width() - tip_width
        stable_geometry = panel.geometry()
        assert surface.x() == body_width
        assert root.findChild(QObject, "floatingScriptsButton") is None
        assert root.findChild(QObject, "floatingSettingsButton") is None
        assert len(root.findChildren(QQuickWindow)) == 1
        click()
        assert controller.expanded and animation.property("running")
        click()
        click()
        assert controller.expanded
        qtbot.waitUntil(lambda: 0.1 < panel.property("revealProgress") < 0.9)
        full_frame = QRegion(QRect(0, 0, panel.width(), panel.height()))
        assert panel.mask() == full_frame
        assert panel.geometry() == stable_geometry
        qtbot.waitUntil(lambda: not animation.property("running"))
        qtbot.waitUntil(lambda: not panel.property("pendingMaskSettlement"))
        assert button.isEnabled() and surface.x() == 0
        assert panel.geometry() == stable_geometry
        assert visibility == []  # The Tip and list share one persistent native window.

        click()
        assert not controller.expanded and panel.isVisible()
        assert not root.findChild(QObject, "floatingPanelSurface").isEnabled()
        qtbot.waitUntil(lambda: 0 < panel.property("revealProgress") < 1)
        assert panel.mask() == full_frame
        assert panel.isVisible()
        click()  # A second close click must not reopen the panel mid-transition.
        assert not controller.expanded
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 0)
        qtbot.waitUntil(lambda: not panel.property("pendingMaskSettlement"))
        assert panel.property("revealProgress") == 0
        assert panel.geometry() == stable_geometry
        assert surface.x() == body_width
        assert panel.mask().boundingRect().width() == tip_width
        assert visibility == []

        click()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        assert visibility == []
        assert panel.geometry() == stable_geometry
        assert surface.x() == 0
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


def test_panel_animation_reverses_without_restarting_on_window_show(launcher, qtbot, monkeypatch):
    controller, _, _, _ = launcher
    monkeypatch.setattr(controller, "_pointer_inside", lambda: True)
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        package_root() / "ui/qml/components/FloatingLauncher.qml"
    )))
    root = component.createWithInitialProperties({"controller": controller})
    assert root is not None, [error.toString() for error in component.errors()]
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    animation = root.findChild(QObject, "floatingPanelSlideAnimation")
    animation.setProperty("duration", 400)
    try:
        controller.toggleExpanded()
        qtbot.waitUntil(lambda: 0.1 < panel.property("revealProgress") < 0.9)
        progress = panel.property("revealProgress")
        controller.collapse()
        assert panel.isVisible()
        assert panel.property("revealProgress") == pytest.approx(progress)
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 0)

        controller.toggleExpanded()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        # Windows can report another show while processing activation changes;
        # this must not replay the entrance animation for an already-open panel.
        panel.hide()
        panel.show()
        qtbot.wait(50)
        assert not animation.property("running")
        assert panel.property("revealProgress") == 1
        # A rapid foreground/background change must not reveal a leftover
        # closing frame when the launcher becomes available again.
        monkeypatch.setattr(controller, "_ordinary_window_active", lambda: True)
        controller.reconcile()
        assert not panel.isVisible() and panel.property("revealProgress") == 0
        monkeypatch.setattr(controller, "_ordinary_window_active", lambda: False)
        controller.reconcile()
        assert not controller.expanded and panel.isVisible()
        assert panel.mask().boundingRect().width() == 24
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


def test_slide_does_not_reposition_or_rebuild_the_list_per_frame(launcher, qtbot, monkeypatch):
    controller, backend, _, _ = launcher
    create_tool(backend, "Animation sample")
    monkeypatch.setattr(controller, "_pointer_inside", lambda: True)
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        package_root() / "ui/qml/components/FloatingLauncher.qml"
    )))
    root = component.createWithInitialProperties({"controller": controller})
    assert root is not None, [error.toString() for error in component.errors()]
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    animation = root.findChild(QObject, "floatingPanelSlideAnimation")
    animation.setProperty("duration", 400)
    reposition_calls, resets = [], []
    reposition = controller.reposition

    def track_reposition(*args):
        reposition_calls.append(panel.property("revealProgress"))
        reposition(*args)

    monkeypatch.setattr(controller, "reposition", track_reposition)
    controller.toolsModel.modelReset.connect(lambda: resets.append(True))
    try:
        assert QTest.qWaitForWindowExposed(panel)
        for expanded in (True, False, True, False):
            reposition_calls.clear()
            controller.toggleExpanded()
            qtbot.waitUntil(lambda: 0.1 < panel.property("revealProgress") < 0.9)
            boundary_calls = len(reposition_calls)
            qtbot.wait(60)
            assert len(reposition_calls) == boundary_calls
            qtbot.waitUntil(lambda: not animation.property("running"))
            qtbot.waitUntil(lambda: not panel.property("pendingMaskSettlement"))
            assert panel.property("revealProgress") == (1 if expanded else 0)
            assert len(reposition_calls) <= 3  # Start/end only, independent of frame count.
        assert not resets
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


def test_main_window_run_state_refreshes_the_cached_floating_list(launcher, monkeypatch):
    controller, backend, _, _ = launcher
    tool = create_tool(backend, "Run from main window")
    active = set()
    coordinator = backend.execution_coordinator
    monkeypatch.setattr(coordinator, "running", lambda tool_id: tool_id in active)
    model = controller.toolsModel
    active.add(tool.id)
    coordinator.runningChanged.emit(tool.id, True)
    assert model.data(model.index(0, 0), model.RunningRole)
    active.clear()
    coordinator.runningChanged.emit(tool.id, False)
    assert not model.data(model.index(0, 0), model.RunningRole)


@pytest.mark.parametrize("command", [
    "print('hello')", "print('${文本}')", "import os; os.system('adb devices')",
])
def test_shortcut_launch_and_failure_feedback(launcher, monkeypatch, command):
    controller, backend, _, _ = launcher
    tool = create_tool(backend, "运行测试", command=command)
    runs = []
    dialogs = []
    backend.recentToolDialogRequested.connect(dialogs.append)
    monkeypatch.setattr(backend, "runSelected", lambda values: runs.append(values) or True)
    controller.launchTool(tool.id)
    needs_dialog = bool(tool.parameters or backend._analyze_tool(tool).uses_adb)
    assert dialogs == ([tool.id] if needs_dialog else [])
    assert runs == ([] if needs_dialog else [{}])
    if not needs_dialog:
        backend.execution_coordinator.finished.emit(tool.id, 0)
        dialogs.clear()
        monkeypatch.setattr(backend, "runSelected", lambda values: False)
        controller.launchTool(tool.id)
        assert dialogs == [tool.id]


def test_running_shortcuts_are_blocked_and_async_launch_errors_are_visible(launcher, monkeypatch):
    controller, backend, _, _ = launcher
    tool = create_tool(backend, "运行测试")
    dialogs = []
    backend.recentToolDialogRequested.connect(dialogs.append)
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tool_id: True)
    controller.launchTool(tool.id)
    assert not dialogs
    controller.refreshTools()
    assert controller.toolsModel.data(controller.toolsModel.index(0, 0),
                                     controller.toolsModel.RunningRole)
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tool_id: False)
    monkeypatch.setattr(backend, "runSelected", lambda values: True)
    controller.launchTool(tool.id)
    backend.execution_coordinator.finished.emit(tool.id, -1)
    assert dialogs == [tool.id]


@pytest.mark.parametrize("dark,window_width", [(False, 440), (True, 480)])
def test_recent_script_window_uses_shared_form_and_console(launcher, qapp, qtbot, monkeypatch,
                                                         dark, window_width):
    _, backend, _, _ = launcher
    tool = create_tool(backend, "Script execution", kind="powershell",
                       command="Write-Output ${path@dir:C:/work} ${message}")
    backend.selectTool(tool.id)
    running = [False]
    runs, stops = [], []

    def start(tool, values, serial):
        runs.append((tool.id, dict(values)))
        running[0] = True
        backend.runningChanged.emit()
        return True

    def stop(tool_id):
        stops.append(tool_id)
        running[0] = False
        backend.runningChanged.emit()

    monkeypatch.setattr(backend.execution_coordinator, "start", start)
    monkeypatch.setattr(backend.execution_coordinator, "stop", stop)
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda _tool_id: running[0])
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    engine.rootContext().setContextProperty("appController", backend)
    engine.rootContext().setContextProperty("androidBackend", backend.android_controller)
    engine.rootContext().setContextProperty("testDarkMode", dark)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
RecentToolDialog {
    deviceController: androidBackend
    presetUtilities: null
    jiraFeishuBackend: null
    Component.onCompleted: Theme.darkMode = testDarkMode
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/RecentScriptHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        window.setWidth(window_width)
        assert QMetaObject.invokeMethod(window, "showWithTool", Q_ARG("QVariant", tool.id))
        assert QTest.qWaitForWindowExposed(window)

        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        def click(name):
            item = next(item for item in visual_items(window.contentItem())
                        if item.objectName() == name)
            rect = item.mapRectToItem(window.contentItem(), item.boundingRect())
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())

        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        items = {item.objectName(): item for item in visual_items(window.contentItem())}
        panel = items["customToolDetailPanel"]
        console = items["customConsolePanel"]
        assert panel.isVisible() and panel.property("actionsInTitleBar")
        assert panel.property("deviceInTitleBar")
        assert panel.property("compactLayout")
        assert panel.width() >= window.width() - 8
        assert panel.property("color").name() == ("#171e28" if dark else "#ffffff")
        assert items["recentToolDeviceSelector"].property("compact")
        assert console.height() >= 200
        assert console.width() >= panel.width() - 16
        for name in ("recentToolRunButton", "recentToolDeviceSelector",
                     "customConsoleCopyButton", "customConsoleClearButton", "customConsoleToggle"):
            item = items[name]
            rect = item.mapRectToItem(window.contentItem(), item.boundingRect())
            assert 0 <= rect.left() < rect.right() <= window.width()
        field = items["customParameterInput_message"]
        assert field.mapRectToItem(panel, field.boundingRect()).bottom() < console.y()
        field.property("item").setProperty("text", "updated")
        click("recentToolRunButton")
        assert runs == [(tool.id, {"path": "C:/work", "message": "updated"})]
        assert backend.running
        click("recentToolRunButton")
        assert stops == [tool.id] and not backend.running
        click("customConsoleToggle")
        qtbot.waitUntil(lambda: console.height() == 42)
        click("customConsoleToggle")
        qtbot.waitUntil(lambda: console.height() >= 200)
        click("customConsoleClearButton")
        assert window.property("toolController").consoleText == ""
        click("recentToolMinimizeButton")
        qtbot.waitUntil(lambda: window.windowState() == Qt.WindowState.WindowMinimized)
        window.showNormal()
        assert QTest.qWaitForWindowExposed(window)
        click("recentToolCloseButton")
        qtbot.waitUntil(lambda: not window.isVisible())
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


def test_capacity_confirmation_raises_main_window(launcher, monkeypatch):
    controller, backend, _, main = launcher
    tool = create_tool(backend, "容量测试")
    dialogs = []
    backend.recentToolDialogRequested.connect(dialogs.append)

    def run(values):
        backend.execution_coordinator.capacityRequested.emit("旧任务", tool.title)
        return False

    monkeypatch.setattr(backend, "runSelected", run)
    controller.launchTool(tool.id)
    assert main.isVisible()
    assert not dialogs


def test_independent_sessions_execute_concurrently_and_keep_separate_output(launcher, qtbot):
    _, backend, _, _ = launcher
    alpha = create_tool(backend, "Concurrent A", command=(
        "import time\nprint('alpha-${value:A}', flush=True)\ntime.sleep(0.3)\n"
        "print('alpha finished', flush=True)"
    ))
    beta = create_tool(backend, "Concurrent B", command=(
        "import time\nprint('beta-${value:B}', flush=True)\ntime.sleep(0.3)\n"
        "print('beta finished', flush=True)"
    ))
    session_a = backend.createToolSession(alpha.id)
    session_b = backend.createToolSession(beta.id)
    backend.selectTool(beta.id)
    try:
        assert session_a.runSelected({"value": "first"})
        assert session_b.runSelected({"value": "second"})
        qtbot.waitUntil(lambda: session_a.statusText == session_b.statusText == "执行成功",
                        timeout=10000)
        assert "alpha-first" in session_a.consoleText
        assert "alpha finished" in session_a.consoleText and "beta" not in session_a.consoleText
        assert "beta-second" in session_b.consoleText
        assert "beta finished" in session_b.consoleText and "alpha" not in session_b.consoleText
        counts = backend.config_store.tool_usage_counts()
        assert counts[alpha.id] == counts[beta.id] == 1
        assert backend.selectedTool["id"] == beta.id
    finally:
        if session_a.running:
            session_a.stopExecution()
        if session_b.running:
            session_b.stopExecution()


@pytest.mark.parametrize("dark", [False, True])
def test_qml_windows_search_theme_sort_menu_escape_and_render(
    launcher, qapp, qtbot, dark, monkeypatch,
):
    controller, backend, settings, main = launcher
    for index in range(18):
        create_tool(backend, f"测试脚本 {index:02} · 很长的脚本名称用于验证省略",
                    kind="powershell" if index % 2 else "python")
    settings.saveThemeMode("dark" if dark else "light")
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Item {
    required property var backend
    required property bool dark
    Binding { target: Theme; property: "darkMode"; value: dark }
    FloatingLauncher { controller: backend }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/FloatingTestHarness.qml")))
    root = component.createWithInitialProperties({"backend": controller, "dark": dark})
    assert root is not None, [e.toString() for e in component.errors()]
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    try:
        controller.reconcile()
        qtbot.waitUntil(panel.isVisible)
        assert panel.mask().boundingRect().width() == 24
        assert panel.mask().boundingRect().height() == 64
        assert root.findChild(QObject, "floatingScriptsTip") is None
        assert root.findChild(QObject, "floatingSettingsTip") is None
        tip = root.findChild(QObject, "floatingDragGrip")
        assert QTest.qWaitForWindowExposed(panel)
        with qtbot.waitSignal(panel.frameSwapped):
            panel.update()
        rect = tip.mapRectToItem(panel.contentItem(), tip.boundingRect())
        QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        assert controller._is_launcher_window(panel)
        script_list = root.findChild(QObject, "floatingScriptList")
        assert script_list.property("visibleCount") == 18
        search = root.findChild(QObject, "scriptListSearch")
        search.setProperty("text", "脚本 01")
        qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
        assert script_list.property("visibleCount") == 1
        search.setProperty("text", "")
        sort_button = root.findChild(QObject, "scriptListSort")
        assert QMetaObject.invokeMethod(sort_button, "openMenu")
        qtbot.waitUntil(lambda: sort_button.property("menuOpen"))
        assert controller._menu_open
        controller.collapse()
        qtbot.waitUntil(lambda: not sort_button.property("menuOpen"))
        controller.toggleExpanded()
        qtbot.wait(220)
        panel.requestActivate()
        qtbot.waitUntil(panel.isActive)
        QTest.keyClick(panel, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not controller.expanded)
        controller.toggleExpanded()
        qtbot.wait(220)
        output = Path("build") / f"floating-launcher-{'dark' if dark else 'light'}.png"
        output.parent.mkdir(exist_ok=True)
        assert panel.grabWindow().save(str(output))
        controller.collapse()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 0)
        assert panel.grabWindow().save(str(output.with_name(f"floating-notch-{dark}.png")))
        controller.toggleExpanded()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        # Exercise real native activation after the deterministic controller checks.
        monkeypatch.setattr(controller, "_ordinary_window_active", lambda:
                            FloatingLauncherController._ordinary_window_active(controller))
        panel.requestActivate()
        qtbot.waitUntil(panel.isActive)
        controller.reconcile()
        assert controller.visible and controller.expanded
        main.showNormal()
        main.requestActivate()
        qtbot.waitUntil(main.isActive)
        qtbot.waitUntil(lambda: not controller.visible and not panel.isVisible())
        main.hide()
        qtbot.waitUntil(lambda: controller.visible)
        assert not warnings, warnings
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("multiple", [False, True])
def test_main_window_settings_navigation_and_close_to_tray(
    launcher, qapp, qtbot, monkeypatch, multiple,
):
    if not terminal_library_path().exists():
        pytest.skip("Full application requires the built native terminal")
    register_terminal_type()
    controller, backend, settings, _ = launcher
    settings.markUserGuideSeen()
    preset = PresetController()
    jira = JiraFeishuController(settings.config_store.paths.data_dir)
    terminal = DeveloperConsoleController(settings.python_environment)
    update = UpdateController(settings.config_store, auto_check_enabled=False)
    previous_quit_policy = qapp.quitOnLastWindowClosed()
    tray = SystemTrayController(qapp)
    tray.set_app_controller(backend)
    engine = QQmlApplicationEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    for name, value in {
        "appController": backend, "settingsController": settings, "presetController": preset,
        "jiraFeishuController": jira, "developerConsoleController": terminal,
        "androidController": backend.android_controller, "trayController": tray,
        "updateController": update, "floatingController": controller,
    }.items():
        engine.rootContext().setContextProperty(name, value)
    engine.load(QUrl.fromLocalFile(str(package_root() / "ui/qml/Main.qml")))
    assert engine.rootObjects(), warnings
    window = engine.rootObjects()[0]
    tray.attach_window(window)
    controller.attach_main_window(window)
    try:
        window.hide()
        controller.reconcile()
        controller.openSettings()
        qtbot.waitUntil(window.isVisible)
        assert window.property("settingsSelected")
        toggle = window.findChild(QObject, "floatingLauncherToggle")
        assert toggle is not None and toggle.property("checked")
        settings.saveFloatingLauncherEnabled(False)
        assert not toggle.property("checked") and not controller.visible
        settings.saveFloatingLauncherEnabled(True)
        window.resize(960, 720)
        qtbot.wait(150)
        assert window.grabWindow().save("build/floating-settings.png")
        if tray.available:
            assert not window.close()
            qtbot.waitUntil(lambda: not window.isVisible() and controller.visible)
        if multiple:
            window.hide()
            monkeypatch.setattr(controller, "_ordinary_window_active", lambda:
                                FloatingLauncherController._ordinary_window_active(controller))
            controller.reconcile()
            alpha = create_tool(backend, "Window A", command="print('${message:Alpha}')")
            beta = create_tool(backend, "Window B", command="print('${message:Beta}')")

            def tool_windows():
                return {w.property("toolId"): w for w in qapp.topLevelWindows()
                        if w.objectName() == "recentToolWindow" and w.isVisible()}

            def set_message(target, text):
                def descendants(item):
                    yield item
                    for child in item.childItems():
                        yield from descendants(child)

                field = next(item for item in descendants(target.contentItem())
                             if item.objectName() == "customParameterInput_message")
                field.property("item").setProperty("text", text)

            def parameter_values(target):
                values = target.property("parameterValues")
                return values.toVariant() if hasattr(values, "toVariant") else values

            controller.launchTool(alpha.id)
            qtbot.waitUntil(lambda: alpha.id in tool_windows())
            first = tool_windows()[alpha.id]
            qtbot.waitUntil(first.isActive)
            window.show()
            first.requestActivate()
            qtbot.waitUntil(first.isActive)
            controller.reconcile()
            assert controller.visible and window.isVisible()
            set_message(first, "draft A")
            session_a = first.property("toolController")
            first_position = first.position()
            controller.launchTool(beta.id)
            qtbot.waitUntil(lambda: beta.id in tool_windows())
            second = tool_windows()[beta.id]
            qtbot.waitUntil(second.isActive)
            second_position = second.position()
            assert second_position != first_position
            assert first.position() == first_position
            assert second.screen().availableGeometry().contains(second.geometry())
            controller.reconcile()
            assert first.isVisible() and controller.visible
            set_message(second, "draft B")
            session_b = second.property("toolController")
            assert session_a.selectedTool["id"] == alpha.id
            assert session_b.selectedTool["id"] == beta.id
            # Reopening a tool activates its existing window without resetting its form.
            backend.recentToolDialogRequested.emit(alpha.id)
            qtbot.waitUntil(first.isActive)
            assert len(tool_windows()) == 2
            assert first.position() == first_position
            assert second.position() == second_position
            values_a = parameter_values(first)
            values_b = parameter_values(second)
            assert values_a == {"message": "draft A"}
            assert values_b == {"message": "draft B"}

            active, runs, stops = set(), [], []
            coordinator = backend.execution_coordinator

            def start(tool, values, serial):
                active.add(tool.id)
                runs.append((tool.id, values))
                coordinator.started.emit(tool.id)
                coordinator.runningChanged.emit(tool.id, True)
                return True

            def stop(tool_id):
                active.discard(tool_id)
                stops.append(tool_id)
                coordinator.runningChanged.emit(tool_id, False)
                coordinator.finished.emit(tool_id, 0)

            monkeypatch.setattr(coordinator, "start", start)
            monkeypatch.setattr(coordinator, "stop", stop)
            monkeypatch.setattr(coordinator, "running", lambda tool_id: tool_id in active)
            backend.selectTool(beta.id)
            backend.setToolSortMode("usage")
            assert session_a.runSelected(values_a)
            assert backend.selectedTool["id"] == beta.id
            assert session_b.runSelected(values_b)
            assert runs == [(alpha.id, values_a), (beta.id, values_b)]
            assert session_a.running and session_b.running
            coordinator.output.emit(alpha.id, "only A\n")
            coordinator.output.emit(beta.id, "only B\n")
            backend._flush_console()
            assert session_a.consoleText == "only A\n"
            assert session_b.consoleText == "only B\n"
            qtbot.wait(80)
            assert first.grabWindow().save("build/multi-script-window-a.png")
            assert second.grabWindow().save("build/multi-script-window-b.png")
            session_a.stopExecution()
            assert stops == [alpha.id] and session_b.running
            assert session_a.statusText == "执行成功" and session_b.statusText == "运行中"
            assert session_a.setParameterDefault("message", "new default A")
            assert backend.registry.get(alpha.id).parameters[0].default == "new default A"
            assert backend.registry.get(beta.id).parameters[0].default == "Beta"
            session_a.clearConsole()
            assert session_a.consoleText == "" and session_b.consoleText == "only B\n"
            assert "only A" in backend.consoleText and "only B" in backend.consoleText
            first.close()
            qtbot.waitUntil(lambda: len(tool_windows()) == 1)
            qtbot.waitUntil(lambda: len(backend.findChildren(ToolSessionController)) == 1)
            assert second.isVisible() and session_b.running
            second.close()
            qtbot.waitUntil(lambda: not tool_windows())
            qtbot.waitUntil(lambda: not backend.findChildren(ToolSessionController))
            assert stops == [alpha.id]  # Closing a window does not stop another task.
            backend.recentToolDialogRequested.emit(beta.id)
            qtbot.waitUntil(lambda: beta.id in tool_windows())
            reopened = tool_windows()[beta.id]
            assert reopened.property("toolController").consoleText == "only B\n"
            assert reopened.property("toolController").running
        assert not warnings, warnings
    finally:
        QMetaObject.invokeMethod(window, "closeRecentToolWindows")
        controller.shutdown()
        tray._quitting = True
        tray._tray.hide()
        window.close()
        terminal.shutdown()
        jira.shutdown()
        update.shutdown()
        engine.deleteLater()
        tray.deleteLater()
        qapp.setQuitOnLastWindowClosed(previous_quit_policy)
