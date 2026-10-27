import math
import os
from pathlib import Path
from time import perf_counter

import pytest
from PySide6.QtCore import (
    Q_ARG,
    QEvent,
    QMetaObject,
    QObject,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QCursor, QFontDatabase, QMouseEvent, QRegion, QWindow
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.foreground_window import ForegroundWindow
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.system_tray import SystemTrayController
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.native_terminal import register_terminal_type, terminal_library_path
from poptools.paths import AppPaths, package_root, resource_path
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels import floating_launcher_controller as floating_module
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
    # Keep Qt activation tests independent of OS foreground-lock restrictions.
    # Native ownership and stale startup state are exercised explicitly below.
    monkeypatch.setattr(floating_module, "foreground_window", lambda: None)
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


def test_startup_without_click_recovers_missing_focus_notification(launcher, qtbot, monkeypatch):
    controller, _, settings, main = launcher
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda:
                        FloatingLauncherController._ordinary_window_active(controller))
    monkeypatch.setattr(controller._app, "platformName", lambda: "windows")
    monkeypatch.setattr(controller._app, "applicationState", lambda:
                        Qt.ApplicationState.ApplicationActive)
    monkeypatch.setattr(controller._app, "topLevelWindows", lambda: [main])
    monkeypatch.setattr(main, "isVisible", lambda: True)
    monkeypatch.setattr(main, "isActive", lambda: True)
    foreground = ForegroundWindow(int(main.winId()), os.getpid(), 0)
    monkeypatch.setattr(floating_module, "foreground_window", lambda: foreground)
    controller.reconcile()
    assert not controller.visible

    # No click, FocusOut or applicationStateChanged: Qt's startup activation is
    # stale, but Windows already reports another process in the foreground.
    foreground = ForegroundWindow(123, os.getpid() + 1, 123)
    qtbot.waitUntil(lambda: controller.visible, timeout=1000)

    # The reverse stale state must not leave the tip over the main window.
    monkeypatch.setattr(controller._app, "applicationState", lambda:
                        Qt.ApplicationState.ApplicationInactive)
    monkeypatch.setattr(main, "isActive", lambda: False)
    foreground = ForegroundWindow(int(main.winId()), os.getpid(), 0)
    qtbot.waitUntil(lambda: not controller.visible, timeout=1000)
    settings.saveFloatingLauncherEnabled(False)
    assert not controller._foreground_timer.isActive()
    foreground = ForegroundWindow(123, os.getpid() + 1, 123)
    settings.saveFloatingLauncherEnabled(True)
    assert controller.visible and controller._foreground_timer.isActive()
    controller.shutdown()
    assert not controller._foreground_timer.isActive()


def test_native_foreground_preserves_cards_and_owned_dialogs(launcher, monkeypatch):
    controller, _, _, main = launcher
    card = QWindow()
    card.setProperty("keepsFloatingLauncherVisible", True)
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda:
                        FloatingLauncherController._ordinary_window_active(controller))
    monkeypatch.setattr(controller._app, "platformName", lambda: "windows")
    monkeypatch.setattr(controller._app, "topLevelWindows", lambda: [main, card])
    for window in (main, card):
        monkeypatch.setattr(window, "isVisible", lambda: True)
    try:
        main_id, card_id = int(main.winId()), int(card.winId())
        for handle, owner, expected in (
            (main_id, main_id, False), (card_id, main_id, True),
            (123, card_id, True), (123, main_id, False), (123, 0, False),
        ):
            monkeypatch.setattr(
                floating_module, "foreground_window",
                lambda handle=handle, owner=owner: ForegroundWindow(handle, os.getpid(), owner),
            )
            controller.reconcile()
            assert controller.visible is expected
        controller.togglePinned()
        assert controller.visible
    finally:
        card.destroy()
        card.deleteLater()


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


@pytest.mark.parametrize("theme", ["light", "dark", "decade"])
def test_pin_and_script_focus_keep_pack_open(launcher, monkeypatch, theme):
    controller, _, settings, _ = launcher
    settings.saveThemeMode(theme)
    monkeypatch.setattr(controller, "_pointer_inside", lambda: False)
    monkeypatch.setattr(controller, "_script_window_active", lambda: False)
    controller.toggleExpanded()
    controller.togglePinned()
    controller.pointerChanged()
    controller._collapse_if_outside()
    assert controller.pinned and controller.expanded
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda: True)
    controller.reconcile()
    assert controller.visible and controller.expanded
    controller.collapse()  # Explicit collapse still works while pinned.
    assert not controller.expanded
    controller.toggleExpanded()
    controller.togglePinned()
    assert not controller.visible and not controller.expanded
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda: False)
    controller.reconcile()
    controller.toggleExpanded()
    monkeypatch.setattr(controller, "_script_window_active", lambda: True)
    controller.pointerChanged()
    controller._collapse_if_outside()
    assert controller.expanded and not controller._collapse_timer.isActive()
    monkeypatch.setattr(controller, "_script_window_active", lambda: False)
    controller._collapse_if_outside()
    assert not controller.expanded


def test_independent_all_scripts_filter_sort_and_updates(launcher, qtbot):
    controller, backend, _, _ = launcher
    beta = create_tool(backend, "Beta")
    alpha = create_tool(backend, "Alpha", kind="powershell")
    backend.setToolSearchQuery("Beta")
    controller.setToolSortMode("name")
    qtbot.waitUntil(lambda: controller.toolsModel.totalCount == 2)
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
    qtbot.waitUntil(lambda: controller.toolsModel.totalCount == 1)
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
        for delta in (QPoint(-120, 0), QPoint(-120, 200), QPoint(-180, -200),
                      QPoint(-120, 40), QPoint(-180, 40),
                      QPoint(-120, -40), QPoint(-180, -40), QPoint(0, 0)):
            send(QEvent.Type.MouseMove, delta)
            assert controller.dragging
            # Rapid moves before a render frame must not let the native mask
            # crop the preceding Tip texture at its old vertical offset.
            assert notch.mask().boundingRect() == QRect(0, 0, notch.width(), notch.height())
            assert notch.x() == initial.x()
            assert notch.y() + controller.drawerTipOffset == initial_tip_y + delta.y()
        send(QEvent.Type.MouseButtonRelease, QPoint(), pressed=False)
        assert not controller.dragging
        assert controller.expanded == expanded
        with qtbot.waitSignal(notch.frameSwapped):
            notch.update()
        qtbot.waitUntil(lambda: not controller._drawer_animating)
        if not expanded:
                assert notch.mask().boundingRect().width() == 40
                assert notch.mask().boundingRect().height() == 40
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
        assert panel.mask().boundingRect().width() == 40
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


def test_slide_does_not_reposition_or_rebuild_the_list_per_frame(launcher, qtbot, monkeypatch):
    controller, backend, _, _ = launcher
    create_tool(backend, "Animation sample")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
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


def test_main_window_run_state_refreshes_the_cached_floating_list(launcher, monkeypatch, qtbot):
    controller, backend, _, _ = launcher
    tool = create_tool(backend, "Run from main window")
    active = set()
    coordinator = backend.execution_coordinator
    monkeypatch.setattr(coordinator, "running", lambda tool_id: tool_id in active)
    model = controller.toolsModel
    active.add(tool.id)
    coordinator.runningChanged.emit(tool.id, True)
    qtbot.waitUntil(lambda: bool(model.data(model.index(0, 0), model.RunningRole)))
    assert model.data(model.index(0, 0), model.RunningRole)
    active.clear()
    coordinator.runningChanged.emit(tool.id, False)
    qtbot.waitUntil(lambda: not model.data(model.index(0, 0), model.RunningRole))
    assert not model.data(model.index(0, 0), model.RunningRole)


def test_floating_updates_coalesce_within_one_event_turn(launcher, qtbot, monkeypatch):
    controller, backend, _, _ = launcher
    create_tool(backend, "Coalesced")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
    updates = []
    original = controller.toolsModel.set_tools

    def update(*args, **kwargs):
        updates.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(controller.toolsModel, "set_tools", update)
    for _ in range(20):
        backend.customToolsChanged.emit()
    assert not updates
    qtbot.waitUntil(lambda: bool(updates))
    assert len(updates) == 1


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


def test_running_shortcuts_open_card_without_rerun_and_async_errors_are_visible(
    launcher, monkeypatch,
):
    controller, backend, _, _ = launcher
    tool = create_tool(backend, "运行测试")
    dialogs = []
    backend.recentToolDialogRequested.connect(dialogs.append)
    runs = []
    monkeypatch.setattr(backend, "runSelected", lambda values: runs.append(values))
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tool_id: True)
    controller.launchTool(tool.id)
    assert dialogs == [tool.id]
    assert not runs
    dialogs.clear()
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
        qtbot.waitUntil(lambda: not window.property("entryAnimationRunning"))

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
        editor = field.property("item")
        editor.setProperty("text", "from enter")
        editor.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert runs[-1] == (tool.id, {"path": "C:/work", "message": "from enter"})
        assert len(runs) == 2 and backend.running
        QTest.keyClick(window, Qt.Key.Key_Return)
        assert len(runs) == 2 and stops == [tool.id] and backend.running
        click("recentToolRunButton")
        editor.forceActiveFocus()
        QTest.keyClick(window, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
        assert len(runs) == 3 and backend.running
        click("recentToolRunButton")
        assert stops == [tool.id] * 3 and not backend.running
        click("customConsoleToggle")
        qtbot.waitUntil(lambda: console.height() == 42)
        click("customConsoleToggle")
        qtbot.waitUntil(lambda: console.height() >= 200)
        click("customConsoleClearButton")
        assert window.property("toolController").consoleText == ""
        assert not window.findChild(QObject, "recentToolMinimizeButton").isVisible()
        click("recentToolCloseButton")
        qtbot.waitUntil(lambda: not window.isVisible())
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("dark,size", [(False, (440, 680)), (True, (440, 680)),
                                      (True, (340, 440))])
def test_mechanical_card_entry_activation_and_close(launcher, qtbot, dark, size):
    _, backend, _, _ = launcher
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    tool = create_tool(backend, "Mechanical card", command="print('${message:Hello}')")
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
    Component.onCompleted: { Theme.darkMode = testDarkMode; Theme.decadeMode = true }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/CardMotionHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    occluder = QWindow()
    occluder.resize(200, 100)
    try:
        assert QMetaObject.invokeMethod(window, "showWithTool", Q_ARG("QVariant", tool.id))
        assert window.property("entryAnimationRunning")
        scale = window.property("cardUiScale")
        assert window.width() == math.floor(440 * scale + .5)
        assert window.height() == math.floor(680 * scale + .5)
        assert QTest.qWaitForWindowExposed(window)
        qtbot.waitUntil(lambda: not window.property("entryAnimationRunning"))
        window.resize(*size)
        # Exercise the real timeline, then inspect each visual stage deterministically.
        motion = window.findChild(QObject, "mechanicalCardMotion")
        entry = window.findChild(QObject, "mechanicalCardEntryAnimation")
        assert motion.property("progress") == 1
        position = window.position()
        session = window.property("toolController")
        backend.append_tool_console(tool.id, "Preserve existing output\n")
        # Decade starts with a collapsed console; expose its clear action before
        # checking that the activation scan leaves the real controls clickable.
        window.findChild(QObject, "customToolDetailPanel").setProperty("consoleExpanded", True)
        assert QMetaObject.invokeMethod(motion, "play")
        assert QMetaObject.invokeMethod(motion, "startPreparedEntry")
        assert QMetaObject.invokeMethod(entry, "pause")
        output_dir = Path("build/card-motion")
        output_dir.mkdir(parents=True, exist_ok=True)
        frame_prefix = f"{'dark' if dark else 'light'}-{size[0]}"
        frames = []
        for step, progress in enumerate((0.08, 0.28, 0.52, 0.72, 0.90)):
            motion.setProperty("progress", progress)
            qtbot.wait(20)
            frame = window.grabWindow()
            assert not frame.isNull()
            frames.append(frame)
            assert frame.save(str(output_dir / f"{frame_prefix}-{step}.png"))
            assert window.position() == position
        assert all(frames[index] != frames[index + 1] for index in range(len(frames) - 1))
        # Repeated clicks cannot cut off an in-flight card or replace its live form.
        assert QMetaObject.invokeMethod(window, "activateCard")
        assert window.property("entryAnimationRunning")
        assert not window.property("activationAnimationRunning")
        assert motion.property("progress") == .90
        assert QMetaObject.invokeMethod(entry, "resume")
        qtbot.waitUntil(lambda: not window.property("entryAnimationRunning"))
        assert QMetaObject.invokeMethod(window, "activateCard")
        assert not window.property("entryAnimationRunning")
        assert window.property("activationAnimationRunning")
        assert motion.property("progress") == 1
        assert window.property("toolController") is session
        assert session.consoleText == "Preserve existing output\n"
        assert window.position() == position
        activation = window.findChild(QObject, "mechanicalCardActivationAnimation")
        spin = window.findChild(QObject, "mechanicalCardSpin")
        assert spin.property("axis").x() == 0
        assert spin.property("axis").y() == 1
        assert QMetaObject.invokeMethod(activation, "pause")
        for angle in (0, 60, 180, 300, 360):
            motion.setProperty("spinAngle", angle)
            assert window.grabWindow().save(str(output_dir / f"{frame_prefix}-spin-{angle}.png"))
            assert window.position() == position
            assert window.property("toolController") is session
            assert motion.property("activationBack") == (90 < angle < 270)
        motion.setProperty("spinAngle", 150)
        assert QMetaObject.invokeMethod(window, "activateCard")
        assert motion.property("spinAngle") == 150  # Rapid clicks do not reset the rotation.
        motion.setProperty("spinAngle", 360)
        motion.setProperty("activationScan", .5)
        assert window.findChild(QObject, "mechanicalCardScan").opacity() > .8
        assert window.grabWindow().save(str(output_dir / f"{frame_prefix}-activation-scan.png"))
        assert QMetaObject.invokeMethod(activation, "resume")
        qtbot.waitUntil(lambda: not window.property("activationAnimationRunning"))
        assert motion.property("spinAngle") == 360
        assert motion.property("activationScan") == 1
        assert window.grabWindow().save(str(output_dir / f"{frame_prefix}-5.png"))
        # Native window activation scans only, preserving the form and the click.
        occluder.show()
        occluder.requestActivate()
        qtbot.waitUntil(occluder.isActive)
        window.requestActivate()
        qtbot.waitUntil(lambda: window.property("focusScanRunning"))
        assert not window.property("activationAnimationRunning")
        assert not window.property("entryAnimationRunning")
        focus_scan = window.findChild(QObject, "mechanicalCardFocusScanAnimation")
        assert QMetaObject.invokeMethod(focus_scan, "pause")
        motion.setProperty("focusScanProgress", .5)
        angle = motion.property("spinAngle")
        assert QMetaObject.invokeMethod(window, "showFocusFeedback")
        assert motion.property("focusScanProgress") == .5
        assert motion.property("spinAngle") == angle
        assert window.position() == position
        assert window.property("toolController") is session
        assert window.grabWindow().save(str(output_dir / f"{frame_prefix}-focus-scan.png"))
        clear = window.findChild(QObject, "customConsoleClearButton")
        clear_rect = clear.mapRectToItem(window.contentItem(), clear.boundingRect())
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=clear_rect.center().toPoint())
        assert session.consoleText == ""  # Scan overlay never eats the activating click.
        assert QMetaObject.invokeMethod(focus_scan, "resume")
        qtbot.waitUntil(lambda: not window.property("focusScanRunning"))
        title = window.findChild(QObject, "recentToolTitleDragArea")
        title_point = title.mapRectToItem(window.contentItem(), title.boundingRect()).center()
        face = motion.property("cardFace")
        face_parent = face.parentItem()
        parent_changes = []
        face.parentChanged.connect(lambda: parent_changes.append(True))
        engine.collectGarbage()
        QTest.mouseDClick(window, Qt.LeftButton, pos=title_point.toPoint())
        # QTest can process deferred events before returning from mouseDClick.
        qtbot.waitUntil(lambda: window.property("activationAnimationRunning"))
        assert QMetaObject.invokeMethod(activation, "pause")
        motion.setProperty("spinAngle", 150)
        QTest.mouseDClick(window, Qt.LeftButton, pos=title_point.toPoint())
        assert motion.property("spinAngle") == 150  # No restart on rapid double-clicks.
        assert QMetaObject.invokeMethod(activation, "resume")
        qtbot.waitUntil(lambda: not window.property("activationAnimationRunning"))
        assert motion.property("cardFace") is face
        assert face.parentItem() is face_parent
        assert not parent_changes  # Activation neither creates nor remounts a face.
        # Pending feedback must not revive a window that closed before dispatch.
        assert QMetaObject.invokeMethod(window, "queueTitleActivation")
        window.setProperty("closing", True)
        qtbot.wait(30)
        assert not window.property("activationAnimationRunning")
        window.setProperty("closing", False)
        # List activation keeps the deliberate spin+scan, with no second focus scan.
        occluder.requestActivate()
        qtbot.waitUntil(occluder.isActive)
        assert QMetaObject.invokeMethod(window, "activateCard")
        qtbot.wait(20)
        assert window.property("activationAnimationRunning")
        assert not window.property("focusScanRunning")
        # Minimized cards use the same activation path; a close stops all effects.
        window.showMinimized()
        assert QMetaObject.invokeMethod(window, "activateCard")
        qtbot.waitUntil(lambda: window.windowState() != Qt.WindowState.WindowMinimized)
        assert not window.property("entryAnimationRunning")
        window.close()
        assert not window.property("activationAnimationRunning")
        assert not warnings, warnings
    finally:
        occluder.close()
        occluder.deleteLater()
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("mode", ["light", "dark", "system"])
def test_card_theme_fades_and_live_theme_switch(launcher, qtbot, mode):
    _, backend, settings, _ = launcher
    assert settings.saveThemeMode(mode)
    tool = create_tool(backend, "Theme transition", command="print('${message:Hello}')")
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    engine.rootContext().setContextProperty("appController", backend)
    engine.rootContext().setContextProperty("settingsBackend", settings)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
RecentToolDialog {
    deviceController: null
    presetUtilities: null
    jiraFeishuBackend: null
    Binding { target: Theme; property: "darkMode"; value: settingsBackend.darkTheme }
    Binding { target: Theme; property: "decadeMode"; value: settingsBackend.themeMode === "decade" }
    readonly property color themeAccent: Theme.primary
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ThemeCardHarness.qml")))
    window = component.create()
    assert window, component.errors()
    try:
        window.setProperty("launchOrigin", QRectF(800, 400, 280, 40))
        QMetaObject.invokeMethod(window, "showWithTool", Q_ARG("QVariant", tool.id))
        scale = window.property("cardUiScale")
        assert window.width() == math.floor(440 * scale + .5)
        assert window.height() == math.floor(680 * scale + .5)
        qtbot.waitUntil(lambda: window.findChild(
            QObject, "recentToolFormLoader").property("item") is not None)
        form = window.findChild(QObject, "recentToolFormLoader").property("item")
        assert form.width() == pytest.approx(window.width() / scale)
        assert form.height() == pytest.approx(window.height() / scale)
        displayed = form.mapRectToItem(window.contentItem(), form.boundingRect())
        assert displayed.width() == window.width()
        motion = window.findChild(QObject, "mechanicalCardMotion")
        fade_in = window.findChild(QObject, "cardFadeInAnimation")
        fade_out = window.findChild(QObject, "cardFadeOutAnimation")
        assert not motion.property("desktopFlight")
        qtbot.waitUntil(lambda: fade_in.property("running"))
        QMetaObject.invokeMethod(fade_in, "pause")
        motion.setProperty("fadeOpacity", .4)
        position, handle = window.position(), window.winId()
        session = window.property("toolController")
        backend.append_tool_console(tool.id, "Keep this output\n")
        assert not window.findChild(QObject, "mechanicalCardBack").isVisible()
        assert not window.findChild(QObject, "mechanicalCardScan").isVisible()
        assert window.findChild(QObject, "movingScriptCard").opacity() == .4
        # Closing during fade-in starts at the current alpha; reopening cancels close.
        QMetaObject.invokeMethod(window, "closeCardAnimated")
        assert fade_out.property("running")
        QMetaObject.invokeMethod(fade_out, "pause")
        assert motion.property("fadeOpacity") == .4
        QMetaObject.invokeMethod(window, "activateCard")
        assert motion.property("fadeOpacity") == 1
        assert not window.property("activationAnimationRunning")
        QMetaObject.invokeMethod(window, "showFocusFeedback")
        assert not window.property("focusScanRunning")
        assert settings.saveThemeMode("decade")
        assert settings.darkTheme
        assert ConfigStore(settings.config_store.paths).theme_mode() == "decade"
        assert window.property("themeAccent").name() == "#f12786"
        QMetaObject.invokeMethod(window, "activateCard")
        assert window.property("activationAnimationRunning")
        assert settings.saveThemeMode(mode)
        assert not window.property("activationAnimationRunning")
        assert motion.property("spinAngle") == 0
        assert motion.property("fadeOpacity") == 1
        assert window.property("toolController") is session
        assert session.consoleText == "Keep this output\n"
        assert window.position() == position and window.winId() == handle
        dismissed = []
        window.dismissed.connect(dismissed.append)
        QMetaObject.invokeMethod(window, "closeCardAnimated")
        assert fade_out.property("running")
        qtbot.waitUntil(lambda: not window.isVisible())
        assert dismissed == [tool.id]
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


def test_card_origin_is_scoped_to_the_clicked_script(launcher):
    controller, backend, _, _ = launcher
    tool = create_tool(backend, "Flight", command="print('${message}')")
    origins = []
    backend.recentToolDialogRequested.connect(
        lambda tool_id: origins.append(controller.cardLaunchOrigin(tool_id)))
    origin = QRectF(-330.5, 410.25, 280, 40)
    controller.launchToolFrom(tool.id, origin)
    controller.launchTool(tool.id)
    assert origins == [origin, QRectF()]
    assert controller.cardLaunchOrigin(tool.id).isEmpty()


def test_decade_pack_tracks_open_cards_across_refresh_filter_and_theme(launcher, monkeypatch):
    controller, backend, settings, _ = launcher
    alpha = create_tool(backend, "Pack Alpha")
    beta = create_tool(backend, "Pack Beta")
    controller.refreshTools()
    settings.saveThemeMode("decade")
    requested = []
    backend.recentToolDialogRequested.connect(requested.append)
    monkeypatch.setattr(backend, "open_custom_tool_shortcut",
                        lambda _: pytest.fail("Drawing a card must not execute the script"))
    controller.launchTool(alpha.id)  # A parameterless card still opens the live form.
    assert requested == [alpha.id]
    controller.setCardOpen(alpha.id, True)
    controller.setCardOpen(beta.id, True)
    controller.refreshTools()
    assert controller.toolsModel.count == 0
    settings.saveThemeMode("light")
    assert set(ids(controller.toolsModel)) == {alpha.id, beta.id}
    settings.saveThemeMode("decade")
    assert controller.toolsModel.count == 0
    assert controller.beginCardReturn(alpha.id)
    assert controller.beginCardReturn(beta.id)
    assert set(controller.returningCardIds) == {alpha.id, beta.id}
    controller.setToolSearchQuery("Alpha")
    assert ids(controller.toolsModel) == []  # Return preparation never adds a blank row.
    controller.setCardOpen(alpha.id, False)
    assert controller.returningCardIds == [beta.id]
    controller.setCardOpen(beta.id, False)
    controller.setToolSearchQuery("")
    assert set(ids(controller.toolsModel)) == {alpha.id, beta.id}
    assert controller.openCardCount == 0 and not controller.returningCardIds


def test_decade_pack_dispatches_after_mouse_event_without_raising_the_face(
    launcher, qtbot, monkeypatch,
):
    controller, backend, settings, _ = launcher
    monkeypatch.setattr(controller, "_pointer_inside", lambda: True)
    tools = [create_tool(backend, f"Concurrent {i}") for i in range(3)]
    settings.saveThemeMode("decade")
    controller.refreshTools()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", controller)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Item {
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
    FloatingLauncher { controller: backend }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ConcurrentPackHarness.qml")))
    root = component.create()
    assert root, component.errors()
    scripts = root.findChild(QObject, "floatingScriptList")
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    requested = []
    backend.recentToolDialogRequested.connect(requested.append)

    def launch(tool):
        assert QMetaObject.invokeMethod(scripts, "activateTool", Q_ARG("QVariant", tool.id),
                                       Q_ARG("QVariant", None))

    dispatched_origins = []
    backend.recentToolDialogRequested.connect(
        lambda tool_id: dispatched_origins.append(controller.cardLaunchOrigin(tool_id)))
    try:
        controller.toggleExpanded()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        ports = []
        list_origins = []
        for tool in tools:
            face = root.findChild(QObject, "deckCard_" + tool.id)
            host = face.parentItem()
            origin = face.mapToGlobal(QPointF())
            size = face.size()
            inset = 4 * face.width() / 432
            inset_y = 4 * face.height() / 672
            list_origins.append(QRectF(origin.x() - inset, origin.y() - inset_y,
                                      face.width() + 2 * inset, face.height() + 2 * inset_y))
            launch(tool)
            launch(tool)  # Coalesce repeated clicks before the safe dispatch.
            assert requested == []  # No native window creation inside MouseArea dispatch.
            assert face.parentItem() is host  # No full-card overlay in the pack.
            assert face.mapToGlobal(QPointF()) == origin and face.size() == size
            port = face.property("packPort")
            assert port.width() == 1 and port.height() > 0
            ports.append(port)
        assert all(port == ports[0] for port in ports)
        assert scripts.property("pendingLaunchCount") == 3
        qtbot.waitUntil(lambda: len(requested) == 3)
        assert requested == [tool.id for tool in tools]
        origins = dispatched_origins
        assert origins == list_origins  # Every flight starts at its real row, not at the port.
        assert len({origin.y() for origin in origins}) == len(tools)
        assert scripts.property("pendingLaunchCount") == 0
        launch(tools[0])
        recall = root.findChild(QObject, "floatingRecallAllButton")
        assert recall.isEnabled()
        QMetaObject.invokeMethod(recall, "clicked")
        assert scripts.property("pendingLaunchCount") == 0
        qtbot.wait(40)
        assert len(requested) == 3  # Recall cancels work that has not opened yet.
        # Cards align exactly; elevation comes from their shadow and stacking order.
        faces = [root.findChild(QObject, "deckCard_" + tool.id) for tool in tools]
        assert len({face.mapToGlobal(QPointF()).x() for face in faces}) == 1
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("source_x,source_y,clip_offset", [
    (1000, 200, 0), (-1200, -350, 25), (850, 620, 60),
])
def test_card_render_buffer_stays_complete_during_departure_and_return(
    qapp, qtbot, source_x, source_y, clip_offset,
):
    from poptools.infrastructure.window_placement import card_pack_mask

    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Window
import QtQuick.Effects
import "components"
import "theme"
Window {
    width: 440; height: 680; color: "transparent"
    flags: Qt.FramelessWindowHint
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
    MechanicalCardFace {
        id: face; visible: false
        objectName: "departureTestFace"
    }
    MechanicalCardMotion {
        id: motion; anchors.fill: parent; cardFace: face
        cardTitle: "Direct departure"
    }
    Rectangle {
        id: form; parent: motion.surface; anchors.fill: parent
        anchors.margins: 4; color: "#19191F"; radius: 8
    }
    MultiEffect {
        parent: motion.surface; anchors.fill: parent; source: form
        shadowEnabled: true; shadowBlur: 0.7; blurMax: 24
        shadowOpacity: 0.72; shadowVerticalOffset: 6
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/DepartureMaskHarness.qml")))
    window = component.create()
    assert window, component.errors()
    motion = window.findChild(QObject, "mechanicalCardMotion")
    face = window.findChild(QObject, "departureTestFace")
    positions = []
    motion.positionRequested.connect(lambda x, y, pack, opening: positions.append(QPointF(x, y)))
    face.setProperty("packVisibleRect", QRectF(source_x, source_y + clip_offset, 300, 60))
    geometry = {"x": 0, "y": 0, "width": 1500, "height": 1000,
                "sourceX": source_x, "sourceY": source_y, "sourceWidth": 300,
                "sourceHeight": 680 * 300 / 440, "targetX": 32, "targetY": 32,
                "targetWidth": 440, "targetHeight": 680, "preserveSource": True}
    try:
        QMetaObject.invokeMethod(motion, "prepareFlight", Q_ARG("QVariant", geometry))
        packed_surface = QRect(round(source_x + (300 - 440) / 2),
                               round(source_y + (geometry["sourceHeight"] - 680) / 2), 440, 680)
        window.setMask(card_pack_mask(
            packed_surface, QRectF(source_x, source_y, 300, geometry["sourceHeight"]),
            face.property("packVisibleRect"),
        ))
        window.show()
        assert QTest.qWaitForWindowExposed(window)
        qtbot.wait(60)
        first = window.grabWindow()
        # The native pack mask hides the body on screen, but the backing surface
        # must already contain it before the very first window movement.
        ratio = first.devicePixelRatio()
        assert first.pixelColor(round(220 * ratio), round(300 * ratio)).alpha() > 200
        assert first.save("build/direct-departure-first.png")
        window.setMask(QRegion())
        dock_position = QPointF(positions[-1])
        for tick in (.005, .025, .05, .075, .10, .15, .25, .5, 1):
            motion.setProperty("progress", tick * motion.property("travelDuration")
                               / motion.property("flightDuration"))
            qtbot.wait(20)
            if tick == .005:
                # Even when landing is to the right/below, first pull up-left
                # from the original row. No teleport to a full-card overlay.
                assert positions[-1].x() < dock_position.x()
                assert positions[-1].y() < dock_position.y()
                surface = QRect(positions[-1].toPoint(), window.size())
                mask = card_pack_mask(surface, QRectF(source_x, source_y, 300,
                                     geometry["sourceHeight"]), face.property("packVisibleRect"))
                assert not mask.isEmpty()
                assert not mask.contains(QPoint(220, 340))  # Body still in sleeve.
            departing = window.grabWindow()
            # Every interior region stays opaque, including the right-hand body
            # that the former union mask cut into an L shape at early flight ticks.
            for fx in (.12, .35, .65, .88):
                for fy in (.10, .25, .5, .75, .90):
                    point = face.mapToItem(window.contentItem(), QPointF(face.width() * fx,
                                                                        face.height() * fy))
                    assert departing.pixelColor(round(point.x() * ratio),
                                                round(point.y() * ratio)).alpha() > 200, tick
            assert departing.save(f"build/direct-departure-moving-{tick}.png")
        # Returning must not shorten the card while it is still in open space.
        # Test the whole surface even at late ticks; occlusion is spatial/native.
        QMetaObject.invokeMethod(motion, "recycle", Q_ARG("QVariant", geometry))
        animation = window.findChild(QObject, "mechanicalCardRecycleAnimation")
        animation.setProperty("paused", True)
        motion.setProperty("returnScan", 0)
        for tick in (0, .45, .6, .75, .85, 1):
            motion.setProperty("returnProgress", tick)
            qtbot.wait(20)
            if tick == 1:
                assert positions[-1] == dock_position
            returning = window.grabWindow()
            for fx in (.12, .5, .88):
                for fy in (.12, .5, .88):
                    point = face.mapToItem(window.contentItem(), QPointF(face.width() * fx,
                                                                        face.height() * fy))
                    assert returning.pixelColor(round(point.x() * ratio),
                                                 round(point.y() * ratio)).alpha() > 200, tick
            assert returning.save(f"build/card-return-full-{tick}.png")
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("row_y", [200, 500, 800])
@pytest.mark.parametrize("offset", [QPoint(0, 0), QPoint(-1920, -400)])
@pytest.mark.parametrize("uses_port,compact_face", [(False, False), (True, False), (True, True)])
def test_all_pack_rows_clear_sleeve_before_turning_or_growing(
    qapp, row_y, offset, uses_port, compact_face,
):
    from poptools.infrastructure.window_placement import card_flight_geometry

    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
MechanicalCardMotion {
    width: 293; height: 453; designScale: 2/3
    cardFace: MechanicalCardFace {}
    Component.onCompleted: Theme.decadeMode = true
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/AllRowExtraction.qml")))
    motion = component.create()
    assert motion, component.errors()
    source = QRectF(1400, row_y, 210, 453 * 210 / 293).translated(offset)
    if compact_face:
        source.setHeight(source.height() * .75)
    available = QRect(0, 0, 1920, 1040).translated(offset)
    # Even a destination on the right cannot pull a low card sideways first.
    target = QRect(1450, 450, 293, 453).translated(offset)
    face = motion.property("cardFace")
    face.setProperty("packViewportTop", 200 + offset.y())
    face.setProperty("packViewportBottom", 900 + offset.y())
    face.setProperty("packVisibleRect", QRectF(source.x(), source.y(), 210, 50))
    if uses_port:
        face.setProperty("packPort", QRectF(source.x() - 24, 200 + offset.y(), 1, 700))
        face.setProperty("packPortOrigin", QRectF(source.x() - 24, 350 + offset.y(),
                                                 200, 453 * 200 / 293))
    positions = []
    motion.positionRequested.connect(
        lambda x, y, pack, opening: positions.append((QPointF(x, y), pack, opening)))
    geometry = card_flight_geometry(source, target, available, True)
    try:
        QMetaObject.invokeMethod(motion, "prepareFlight", Q_ARG("QVariant", geometry))
        card = motion.findChild(QObject, "movingScriptCard")
        sampled = {}
        previous_y = source.center().y()
        for distance in (.01, .1, .18, .3, .5, .65, .9, 1):
            tick = 1 - (1 - distance) ** (1 / 3)
            motion.setProperty("progress", tick * motion.property("travelDuration")
                               / motion.property("flightDuration"))
            point, pack, opening = positions[-1]
            sampled[distance] = point
            bounds = card.mapRectToItem(motion, card.boundingRect()).translated(point)
            if distance <= .5:
                if uses_port:
                    gate = face.property("packPortOrigin")
                    alignment = min(1, distance / .2)
                    expected_width = source.width() + (gate.width() - source.width()) * alignment
                    expected_height = (source.height()
                                       + (gate.height() - source.height()) * alignment)
                    assert bounds.width() == pytest.approx(expected_width, abs=.5)
                    assert bounds.height() == pytest.approx(expected_height, abs=.5)
                    if distance <= .2:
                        assert bounds.center().x() == pytest.approx(source.center().x())
                    else:
                        assert bounds.center().y() == pytest.approx(gate.center().y())
                    assert opening.width() > 1  # The face remains visible inside the list.
                elif bounds.left() < source.left() - .5:
                    assert bounds.bottom() <= face.property("packViewportBottom")
                elif source.bottom() > face.property("packViewportBottom"):
                    assert bounds.center().x() == pytest.approx(source.center().x())
                if not uses_port:
                    assert bounds.width() == pytest.approx(source.width(), abs=.5)
                    assert bounds.height() == pytest.approx(source.height(), abs=.5)
                if not uses_port:
                    assert bounds.center().y() < previous_y
                previous_y = bounds.center().y()
                assert motion.property("flightTilt") == 0
            if distance == .5:
                assert bounds.right() < source.left() - 10
                assert available.contains(bounds.toAlignedRect())
            if distance > .5:
                assert pack.isEmpty() and opening.isEmpty()  # Fully clear; never cut again.
                assert available.contains(bounds.toAlignedRect())
        QMetaObject.invokeMethod(motion, "recycle", Q_ARG("QVariant", geometry))
        animation = motion.findChild(QObject, "mechanicalCardRecycleAnimation")
        animation.setProperty("paused", True)
        motion.setProperty("returnScan", 0)
        for distance, departure in sampled.items():
            tick = math.acos(1 - 2 * distance) / math.pi
            motion.setProperty("returnProgress", 1 - tick)
            point = positions[-1][0]
            assert point.x() == pytest.approx(departure.x(), abs=1)
            assert point.y() == pytest.approx(departure.y(), abs=1)
    finally:
        QMetaObject.invokeMethod(motion, "finish")
        motion.deleteLater()
        engine.deleteLater()


def test_loading_one_card_never_holds_another_card_animation(qapp, qtbot):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Window {
    width: 880; height: 680; color: "transparent"
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
    MechanicalCardMotion {
        id: waiting; objectName: "waitingCard"; width: 440; height: 680
        contentReady: false
    }
    MechanicalCardMotion {
        id: ready; objectName: "readyCard"; x: 440; width: 440; height: 680
    }
    Rectangle { parent: waiting.surface; anchors.fill: parent; color: "#171e28" }
    Rectangle { parent: ready.surface; anchors.fill: parent; color: "#171e28" }
    function begin() {
        waiting.play(); waiting.startPreparedEntry()
        ready.play(); ready.startPreparedEntry()
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/IndependentCardLoading.qml")))
    window = component.create()
    assert window, component.errors()
    waiting = window.findChild(QObject, "waitingCard")
    ready = window.findChild(QObject, "readyCard")
    try:
        window.show()
        QMetaObject.invokeMethod(window, "begin")
        face = waiting.property("cardFace")
        qtbot.waitUntil(lambda: not ready.property("entering"))
        assert ready.property("progress") == 1
        assert waiting.property("waitingForContent")
        assert waiting.property("scan") == 0
        assert waiting.property("entering") and face.isVisible()
        assert waiting.property("progress") == pytest.approx(360 / 660)
        waiting.setProperty("contentReady", True)
        qtbot.waitUntil(lambda: not waiting.property("entering"))
        assert waiting.property("cardFace") is face
        assert waiting.property("scan") == 1
        # Closing before asynchronous loading completes must still cover the form.
        waiting.setProperty("contentReady", False)
        QMetaObject.invokeMethod(waiting, "finish")
        assert waiting.property("scan") == 0
        assert face.isVisible()
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("manual_first", [False, True])
def test_recall_queue_overlaps_flights_and_skips_closed_cards(qapp, qtbot, manual_first):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Item {
    id: root
    Component.onCompleted: Theme.decadeMode = true
    CardRecallQueue { id: queue; objectName: "recallQueue" }
    component TestCard: QtObject {
        property bool visible: true
        property bool customScriptMode: true
        property bool recallQueued: false
        property bool returnPending: false
        property bool recycleAnimationRunning: false
        property int closes: 0
        signal dismissed()
        function closeCardAnimated() { closes++; recycleAnimationRunning = true }
        function complete() { visible = false; dismissed() }
    }
    TestCard { id: a; objectName: "a"; onDismissed: queue.completed(a) }
    TestCard { id: b; objectName: "b"; onDismissed: queue.completed(b) }
    TestCard { id: c; objectName: "c"; onDismissed: queue.completed(c) }
    function recallAll() { queue.recall([a, b, c]) }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/RecallQueueHarness.qml")))
    root = component.create()
    assert root, component.errors()
    queue = root.findChild(QObject, "recallQueue")
    a, b, c = [root.findChild(QObject, name) for name in ("a", "b", "c")]
    first, second = (b, a) if manual_first else (a, b)
    try:
        if manual_first:
            QMetaObject.invokeMethod(b, "closeCardAnimated")
        for _ in range(3):
            QMetaObject.invokeMethod(root, "recallAll")
        assert queue.property("launchingCard") is first
        assert first.property("closes") == 1
        assert second.property("closes") == 0
        # A queued window closed by its native close event must not block the rest.
        QMetaObject.invokeMethod(c, "complete")
        qtbot.wait(10)
        assert queue.property("launchingCard") is first
        # The next flight starts while the first card is still visible/in flight.
        qtbot.waitUntil(lambda: second.property("closes") == 1)
        assert first.property("visible") and first.property("recycleAnimationRunning")
        assert len(queue.property("activeCards").toVariant()) == 2
        QMetaObject.invokeMethod(first, "complete")
        assert second.property("closes") == 1
        assert c.property("closes") == 0
        QMetaObject.invokeMethod(second, "complete")
        qtbot.wait(10)
        assert not queue.property("running")
        assert not any(card.property("recallQueued") for card in (a, b, c))
    finally:
        root.deleteLater()
        engine.deleteLater()


def test_recall_queue_starts_all_cards_without_waiting_for_earlier_landings(qapp, qtbot):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Item {
    id: root
    property var cards: []
    CardRecallQueue { id: queue; objectName: "queue" }
    Component {
        id: factory
        QtObject {
            id: card
            property bool visible: true
            property bool customScriptMode: true
            property bool recallQueued: false
            property bool returnPending: false
            property bool recycleAnimationRunning: false
            function closeCardAnimated() { recycleAnimationRunning = true }
            function complete() { visible = false; queue.completed(card) }
        }
    }
    Component.onCompleted: {
        Theme.decadeMode = true
        for (let i = 0; i < 10; i++) cards.push(factory.createObject(root))
        queue.recall(cards)
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/UnlimitedRecallHarness.qml")))
    root = component.create()
    assert root, component.errors()
    queue = root.findChild(QObject, "queue")
    try:
        qtbot.waitUntil(lambda: len(queue.property("activeCards").toVariant()) == 10)
        cards = queue.property("activeCards").toVariant()
        assert all(card.property("visible") and card.property("recycleAnimationRunning")
                   for card in cards)
        for card in cards:
            QMetaObject.invokeMethod(card, "complete")
        assert not queue.property("running")
    finally:
        root.deleteLater()
        engine.deleteLater()


def test_swapping_pack_presentations_preserves_borrowed_and_docked_faces(launcher, qtbot):
    controller, backend, settings, _ = launcher
    tools = [create_tool(backend, f"Theme card {i}") for i in range(3)]
    settings.saveThemeMode("decade")
    controller.refreshTools()
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    engine.rootContext().setContextProperty("backend", controller)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Item {
    property string mode: "decade"
    Binding { target: Theme; property: "decadeMode"; value: mode === "decade" }
    Binding { target: Theme; property: "darkMode"; value: mode !== "light" }
    FloatingLauncher { id: pack; controller: backend }
    Window {
        objectName: "borrowedFaceWindow"
        width: 440; height: 680
        Item { id: host; anchors.fill: parent }
    }
    function borrow(id) {
        const face = pack.takeCardFace(id)
        face.attachTo(host)
        backend.setCardOpen(id, true)
    }
    function dock(id) {
        const face = pack.takeCardFace(id)
        pack.dockCardFace(id, face, function() {})
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/PresentationSwapHarness.qml")))
    root = component.create()
    assert root, component.errors()
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    scripts = root.findChild(QObject, "floatingScriptList")
    try:
        controller.togglePinned()
        controller.toggleExpanded()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        faces = {tool.id: root.findChild(QObject, "deckCard_" + tool.id) for tool in tools}
        assert all(faces.values())
        QMetaObject.invokeMethod(root, "borrow", Q_ARG("QVariant", tools[0].id))
        borrowed_window = root.findChild(QQuickWindow, "borrowedFaceWindow")
        search = root.findChild(QObject, "scriptListSearch")
        search.setProperty("text", "Theme")
        scripts.setProperty("kindFilter", "python")
        expected_filter = "python"
        for mode in ("light", "dark", "decade", "light", "decade"):
            settings.saveThemeMode(mode)
            root.setProperty("mode", mode)
            qtbot.wait(30)
            expected_height = 480
            available_height = panel.screen().availableGeometry().height()
            assert panel.height() == min(expected_height, available_height)
            view = scripts.findChild(QObject, "sharedScriptList")
            expected_heading = "DECADE / 脚本卡包" if mode == "decade" else "脚本名称"
            assert view.property("headingText") == expected_heading
            if mode == "decade":
                expected_filter = "all"
            assert scripts.property("kindFilter") == expected_filter
            assert search.isVisible() == (mode != "decade")
            assert root.findChild(QObject, "floatingTitleSearch").isVisible() == (mode == "decade")
            assert search.property("text") == "Theme"
            assert scripts.property("visibleCount") == (2 if mode == "decade" else 3)
            for tool_id, original in faces.items():
                assert root.findChild(QObject, "deckCard_" + tool_id) is original
            assert faces[tools[0].id].window() is borrowed_window
        title_search = root.findChild(QObject, "floatingTitleSearch")
        title_search.setProperty("text", "Theme card 1")
        qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
        assert scripts.property("searchQuery") == "Theme card 1"
        title_search.setProperty("text", "")
        qtbot.waitUntil(lambda: controller.toolsModel.count == 2)
        QMetaObject.invokeMethod(root, "dock", Q_ARG("QVariant", tools[0].id))
        assert faces[tools[0].id].window() is panel
        assert controller.openCardCount == 0 and controller.toolsModel.count == 3
        requested = []
        backend.recentToolDialogRequested.connect(requested.append)
        QMetaObject.invokeMethod(scripts, "activateTool", Q_ARG("QVariant", tools[0].id),
                                 Q_ARG("QVariant", None))
        assert scripts.property("pendingLaunchCount") == 1
        settings.saveThemeMode("light")
        root.setProperty("mode", "light")
        qtbot.wait(30)
        assert requested == []  # Retiring the deck cancels its deferred requests.
        settings.saveThemeMode("decade")
        root.setProperty("mode", "decade")
        qtbot.wait(30)
        assert root.findChild(QObject, "deckCard_" + tools[0].id) is faces[tools[0].id]
        assert faces[tools[0].id].window() is panel
        assert not warnings, warnings
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


def test_decade_pack_last_card_stays_rendered_at_scroll_end(launcher, qtbot):
    controller, backend, settings, _ = launcher
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    for index in range(18):
        create_tool(backend, f"Stack {index:02}", kind="python" if index % 2 else "powershell")
    settings.saveThemeMode("decade")
    controller.refreshTools()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", controller)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
Item {
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
    FloatingLauncher { controller: backend }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/StackScrollHarness.qml")))
    root = component.create()
    assert root, component.errors()
    panel = root.findChild(QQuickWindow, "floatingScriptPanelWindow")
    scripts = root.findChild(QObject, "floatingScriptList")

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    try:
        # Scroll/render assertions should not race the unrelated focus-loss timer.
        controller.togglePinned()
        controller.toggleExpanded()
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
        script_list = scripts.findChild(QObject, "sharedScriptList")
        for kind in ("all", "python", "powershell", "all"):
            scripts.setProperty("kindFilter", kind)
            QMetaObject.invokeMethod(script_list, "forceLayout")
            QMetaObject.invokeMethod(script_list, "positionViewAtEnd")
            qtbot.wait(50)  # Let the newly instantiated last delegate report its full height.
            QMetaObject.invokeMethod(script_list, "forceLayout")
            QMetaObject.invokeMethod(script_list, "positionViewAtEnd")
            qtbot.wait(200)
            last_id = controller.toolsModel.lastToolId(kind)
            face = next((item for item in visual_items(script_list)
                         if item.objectName() == "deckCard_" + last_id), None)
            assert face is not None, (kind, script_list.property("contentY"),
                script_list.property("contentHeight"),
                [item.objectName() for item in visual_items(script_list)
                 if item.objectName().startswith("scriptRow_")])
            assert face.isVisible()
            bounds = face.mapRectToItem(script_list, face.boundingRect())
            assert bounds.top() >= -1
            assert bounds.bottom() == pytest.approx(script_list.height(), abs=1)
            assert panel.grabWindow().save(f"build/stack-bottom-{kind}.png")
        scroll_bar = script_list.findChild(QObject, "scriptListScrollBar")
        assert scroll_bar.isVisible()
        handle = scroll_bar.property("contentItem")
        assert handle.objectName() == "decadeSwordScrollHandle"
        start_y = script_list.property("contentY")
        start = handle.mapToItem(panel.contentItem(), handle.boundingRect().center()).toPoint()
        end = start - QPoint(0, 70)
        QTest.mousePress(panel, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(panel, end)
        QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=end)
        assert script_list.property("contentY") < start_y
        assert controller.toolsModel.count == 18
    finally:
        controller.shutdown()
        root.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("interrupt", ["none", "activate", "close", "recycle", "reopen"])
def test_card_flies_from_row_to_window_and_can_be_reactivated(
    launcher, qapp, qtbot, monkeypatch, interrupt,
):
    _, backend, _, _ = launcher
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    tool = create_tool(backend, "Card flight", command="print('${message:Hello}')")
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    engine.rootContext().setContextProperty("appController", backend)
    engine.rootContext().setContextProperty("androidBackend", backend.android_controller)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
RecentToolDialog {
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
    deviceController: androidBackend
    presetUtilities: null
    jiraFeishuBackend: null
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/CardFlightHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    assert window.flags() & Qt.NoDropShadowWindowHint
    available = qapp.primaryScreen().availableGeometry()
    source = QRectF(available.right() - 300, available.center().y(), 280, 40)
    try:
        window.setProperty("launchOrigin", source)
        assert QMetaObject.invokeMethod(window, "showWithTool", Q_ARG("QVariant", tool.id))
        assert window.isVisible()
        native_id = window.winId()
        motion = window.findChild(QObject, "mechanicalCardMotion")
        live_content = window.findChild(QObject, "liveScriptCardContent")
        session = window.property("toolController")
        geometry = motion.property("flightGeometry")
        destination = QRect(geometry["x"] + geometry["targetX"],
                            geometry["y"] + geometry["targetY"],
                            geometry["targetWidth"], geometry["targetHeight"])
        assert destination.topLeft() == available.topLeft() + QPoint(32, 32)
        assert window.property("cardPlacementRect").toAlignedRect() == destination
        assert motion.property("scanDuration") == 300
        assert QTest.qWaitForWindowExposed(window)
        animation = window.findChild(QObject, "mechanicalCardEntryAnimation")
        qtbot.waitUntil(lambda: animation.property("running"))
        assert QMetaObject.invokeMethod(animation, "pause")
        card = window.findChild(QObject, "movingScriptCard")
        output_dir = Path("build/card-flight")
        output_dir.mkdir(parents=True, exist_ok=True)
        for index, travel in enumerate((0, .20, .45, .70, 1)):
            motion.setProperty("progress", travel * motion.property("travelDuration")
                               / motion.property("flightDuration"))
            qtbot.wait(20)
            card_rect = card.mapRectToItem(window.contentItem(), card.boundingRect())
            global_rect = card_rect.translated(window.x(), window.y())
            if travel == 0:
                assert global_rect.center().x() == pytest.approx(source.center().x(), abs=1)
                assert global_rect.y() == pytest.approx(source.y(), abs=1)
                assert global_rect.height() == pytest.approx(source.height(), abs=1)
            elif travel == 1:
                assert window.geometry() == destination
            else:
                assert global_rect.center().x() < source.center().x()
                assert global_rect.height() > source.height()
            assert available.adjusted(-1, -1, 1, 1).contains(global_rect.toAlignedRect())
            assert window.size() == destination.size()
            assert window.property("cardPlacementRect").toAlignedRect() == destination
            assert window.winId() == native_id and window.isVisible()
            assert window.grabWindow().save(str(output_dir / f"flight-{index}.png"))
        if interrupt == "close":
            from poptools.viewmodels import tool_session_controller as session_module

            restores = []
            restore_layer = session_module.set_card_flight_layer

            def observe_layer_restore(target, flying):
                if not flying:
                    restores.append(target.isVisible())
                restore_layer(target, flying)

            monkeypatch.setattr(session_module, "set_card_flight_layer", observe_layer_restore)
            dismissed = []
            window.dismissed.connect(dismissed.append)
            assert QMetaObject.invokeMethod(window, "dismissCard")
            assert dismissed == [tool.id]
            assert not window.isVisible()
            assert not window.property("entryAnimationRunning")
            assert restores == [False]  # Never unmask a closing visible surface.
            assert not warnings, warnings
            return
        if interrupt in ("recycle", "reopen"):
            dismissed = []
            window.dismissed.connect(dismissed.append)
            # Return from the card's current (possibly manually moved) position.
            assert QMetaObject.invokeMethod(motion, "finish")
            window.setPosition(destination.topLeft() + QPoint(20, 16))
            return_start = window.geometry()
            assert QMetaObject.invokeMethod(window, "closeCardAnimated")
            assert window.isVisible() and not dismissed
            assert window.property("recycleAnimationRunning")
            recycle = window.findChild(QObject, "mechanicalCardRecycleAnimation")
            assert QMetaObject.invokeMethod(recycle, "pause")
            motion.setProperty("returnScan", 0)
            for progress in (0, .35, .65, 1):
                motion.setProperty("returnProgress", progress)
                qtbot.wait(1)  # Commit the coalesced native-window flight tick.
                rect = card.mapRectToItem(window.contentItem(), card.boundingRect())
                rect = rect.translated(window.x(), window.y())
                assert window.winId() == native_id and window.isVisible()
                assert window.size() == return_start.size()
                assert window.findChild(QObject, "liveScriptCardContent") is live_content
                if progress == 0:
                    assert window.geometry() == return_start
                elif progress == 1:
                    assert rect.center().x() == pytest.approx(source.center().x(), abs=1)
                    assert rect.center().y() == pytest.approx(source.center().y(), abs=1)
                    assert rect.height() == pytest.approx(source.height(), abs=1)
                assert window.grabWindow().save(str(output_dir / f"recycle-{progress}.png"))
            if interrupt == "reopen":
                assert QMetaObject.invokeMethod(window, "activateCard")
                assert window.geometry() == return_start
                assert window.property("activationAnimationRunning")
                assert not window.property("recycleAnimationRunning")
                qtbot.waitUntil(lambda: not window.property("activationAnimationRunning"))
                assert window.isVisible() and not dismissed
            else:
                assert QMetaObject.invokeMethod(window, "closeCardAnimated")
                assert recycle.property("paused")  # A second close never restarts return.
                assert QMetaObject.invokeMethod(recycle, "resume")
                qtbot.waitUntil(lambda: not window.isVisible())
                assert dismissed == [tool.id]
                assert not window.property("recycleAnimationRunning")
            assert not warnings, warnings
            return
        if interrupt == "activate":
            assert QMetaObject.invokeMethod(window, "activateCard")
            assert window.property("entryAnimationRunning")
            assert not window.property("activationAnimationRunning")
            assert QMetaObject.invokeMethod(animation, "resume")
            qtbot.waitUntil(lambda: not window.property("entryAnimationRunning"))
            assert QMetaObject.invokeMethod(window, "activateCard")
            assert window.property("activationAnimationRunning")
        else:
            qtbot.waitUntil(lambda: motion.property("contentReady"))
            face = window.findChild(QObject, "mechanicalCardBack")
            scan = window.findChild(QObject, "mechanicalCardScan")
            # A pack entry lands first, turns once in place with its face still
            # opaque, then reveals the live form. No scan may overlap the turn.
            assert motion.property("entrySpinDuration") == 420
            for turn, angle in ((0, 0), (.5, 180), (1, 360)):
                elapsed = (motion.property("travelDuration")
                           + motion.property("entrySpinDuration") * turn)
                motion.setProperty("progress", elapsed / motion.property("flightDuration"))
                assert motion.property("displayedSpinAngle") == pytest.approx(angle)
                assert motion.property("scan") == 0
                assert window.geometry() == destination
                assert motion.property("activationBack") == (turn == .5)
                left = face.mapToItem(window.contentItem(), QPointF(0, face.height() / 2))
                right = face.mapToItem(window.contentItem(), QPointF(
                    face.width(), face.height() / 2))
                # At half a turn the real face is reversed. A second 180-degree
                # compensation used to flip it back early, appearing to turn twice.
                assert (right.x() < left.x()) == (turn == .5)
            for progress in (0, .25, .5, .75, 1):
                motion.setProperty("progress", (motion.property("scanStartDuration")
                                                + motion.property("scanDuration") * progress)
                                   / motion.property("flightDuration"))
                frame = window.grabWindow()
                assert window.findChild(QObject, "mechanicalCardBack") is face
                assert window.findChild(QObject, "liveScriptCardContent") is live_content
                assert window.winId() == native_id and window.isVisible()
                assert window.geometry() == destination
                scale = frame.devicePixelRatio()
                # No part of the opaque card becomes desktop during the scan.
                for height_fraction in (.1, .4, .6, .9):
                    assert frame.pixelColor(round(window.width() / 2 * scale),
                        round(window.height() * height_fraction * scale)).alpha() >= 250
                if progress == .5:
                    assert scan.isVisible() and scan.opacity() > .7
                    # Check the broad glow on both sides of the centered card
                    # artwork. Its bright icon can overwhelm the translucent
                    # pink at the center, depending on DPI and font rendering.
                    for width_fraction in (.15, .85):
                        for band_fraction in (.43, .53, .67):
                            light = scan.mapToItem(window.contentItem(), QPointF(
                                scan.width() * width_fraction, scan.height() * band_fraction))
                            color = frame.pixelColor(round(light.x() * scale),
                                                     round(light.y() * scale))
                            assert color.red() > color.green() + 20
                            assert color.blue() > color.green() + 10
                assert frame.save(str(output_dir / f"continuous-reveal-{progress}.png"))
                if progress == 1:
                    revealed_frame = frame
            assert QMetaObject.invokeMethod(animation, "resume")
        qtbot.waitUntil(lambda: not window.property("entryAnimationRunning"))
        assert window.property("toolController") is session
        assert window.findChild(QObject, "liveScriptCardContent") is live_content
        assert window.winId() == native_id and window.isVisible()
        assert window.geometry() == destination
        if interrupt == "none":
            assert window.grabWindow() == revealed_frame
        assert not [w for w in qapp.topLevelWindows() if w.objectName() == "cardFlightWindow"]
        assert not warnings, warnings
    finally:
        QMetaObject.invokeMethod(window, "dismissCard")
        window.deleteLater()
        engine.deleteLater()


def test_flight_rotation_fits_small_desktop_surface(qapp):
    from poptools.infrastructure.window_placement import card_flight_geometry

    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
MechanicalCardMotion { Component.onCompleted: Theme.decadeMode = true }
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/SmallCardHarness.qml")))
    geometry = card_flight_geometry(QRectF(-160, 120, 150, 40), QRect(-288, 12, 276, 226),
                                    QRect(-300, 0, 300, 250))
    motion = component.createWithInitialProperties({"width": 276, "height": 226})
    assert motion is not None, [error.toString() for error in component.errors()]
    positions = []
    motion.positionRequested.connect(lambda x, y: positions.append(QPointF(x, y)))
    try:
        assert QMetaObject.invokeMethod(motion, "prepareFlight", Q_ARG("QVariant", geometry))
        card = motion.findChild(QObject, "movingScriptCard")
        for progress in (0, .15, .35, .55, .75, .95, 1):
            motion.setProperty("progress", progress * motion.property("travelDuration")
                               / motion.property("flightDuration"))
            bounds = card.mapRectToItem(motion, card.boundingRect())
            assert bounds.left() >= -0.01 and bounds.top() >= -0.01
            assert bounds.right() <= motion.width() + .01
            assert bounds.bottom() <= motion.height() + .01
            global_bounds = bounds.translated(positions[-1])
            assert QRectF(-300.01, -.01, 300.02, 250.02).contains(global_bounds)
    finally:
        motion.deleteLater()
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


@pytest.mark.parametrize("parameter_count", [0, 3, 18])
def test_decade_card_live_usage_and_compact_controls(launcher, qtbot, monkeypatch, parameter_count):
    _, backend, _, _ = launcher
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    parameters = " ".join(f"${{value{i}:Default {i}}}" for i in range(parameter_count))
    tool = backend.registry.create_custom(
        title="批量文件整理与归档", description="", kind="python",
        command=f"print('{parameters}')", icon="folder",
    )
    backend.reloadImportedScripts()
    other = create_tool(backend, "Other card")
    config = backend.config_store.load_config()
    config["custom_tools"]["usage_count"] = {tool.id: 37}
    backend.config_store.save_config(config)
    running = [False]
    starts = []

    def start(selected, values, serial):
        starts.append((selected.id, dict(values)))
        running[0] = True
        backend.execution_coordinator.started.emit(selected.id)
        backend.runningChanged.emit()
        return True

    def stop(_tool_id):
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
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
import "theme"
RecentToolDialog {
    deviceController: androidBackend
    presetUtilities: null
    jiraFeishuBackend: null
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/DecadeDesignHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QMetaObject.invokeMethod(window, "showWithTool", Q_ARG("QVariant", tool.id))
        assert QTest.qWaitForWindowExposed(window)
        qtbot.waitUntil(lambda: not window.property("entryAnimationRunning"))
        assert (window.width(), window.height()) == (314, 486)
        content = window.findChild(QObject, "recentToolFormLoader").property("item")
        art = content.findChild(QObject, "decadeCardArtwork")
        glyph = art.findChild(QObject, "decadeCardArtworkIcon")
        assert not art.property("backFace")
        assert glyph.property("icon") == "folder"
        bounds = glyph.mapRectToItem(window.contentItem(), glyph.boundingRect())
        assert bounds.center().x() == pytest.approx(window.width() / 2)
        assert bounds.center().y() == pytest.approx(window.height() / 2)
        panel = window.findChild(QObject, "customToolDetailPanel")
        counter = window.findChild(QObject, "decadeUsageCounter")
        session = window.property("toolController")
        assert panel.property("decadeCardLayout")
        assert not panel.property("consoleExpanded")
        assert counter.property("usageCount") == session.usageCount == 37
        assert counter.property("unit") == 10 and counter.property("filledCount") == 3
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        counter_items = {item.objectName(): item for item in visual_items(counter)}
        for index in range(10):
            block = counter_items[f"decadeUsageBlock_{index}"]
            bounds = block.mapRectToItem(window.contentItem(), block.boundingRect())
            assert bounds.width() == pytest.approx(bounds.height())
            assert bounds.width() == pytest.approx(17 * 5 / 7)
        camera = window.findChild(QObject, "decadeDeviceCamera")
        assert camera.isVisible() and camera.property("source").toString().endswith("decade-camera.svg")
        buttons = [window.findChild(QObject, name) for name in (
            "recentToolRunButton", "recentToolDeviceSelector", "recentToolCloseButton",
        )]
        assert len({round(button.width(), 2) for button in buttons}) == 1
        assert not window.findChild(QObject, "deviceSelectorLabel").isVisible()
        if parameter_count:
            items = {item.objectName(): item for item in visual_items(window.contentItem())}
            editor = items["customParameterInput_value0"].property("item")
            editor.setProperty("text", "Edited value")
        assert QMetaObject.invokeMethod(buttons[0], "clicked")
        qtbot.waitUntil(lambda: panel.property("consoleExpanded"))
        assert counter.property("usageCount") == session.usageCount == 38
        assert ConfigStore(backend.config_store.paths).tool_usage_counts()[tool.id] == 38
        if parameter_count:
            assert starts[-1][1]["value0"] == "Edited value"
        # A different script starting must not change this card's readout.
        backend.execution_coordinator.started.emit(other.id)
        assert counter.property("usageCount") == 38
        assert QMetaObject.invokeMethod(buttons[0], "clicked")
        assert not session.running
        backend.append_tool_console(tool.id, "Actual output\n")
        qtbot.waitUntil(lambda: window.findChild(QObject, "customConsoleText").property("text") == "Actual output\n")
        qtbot.waitUntil(lambda: panel.property("consoleReveal") == 1)
        console = window.findChild(QObject, "customConsolePanel")
        bounds = console.mapRectToItem(window.contentItem(), console.boundingRect())
        assert bounds.bottom() <= window.height()
        area = window.findChild(QObject, "customParameterArea")
        if parameter_count == 18:
            assert area.property("contentHeight") > area.height()
        output_dir = Path("build/decade-design")
        output_dir.mkdir(parents=True, exist_ok=True)
        assert window.grabWindow().save(str(output_dir / f"card-{parameter_count}-expanded.png"))
        toggle = window.findChild(QObject, "customConsoleToggle")
        assert QMetaObject.invokeMethod(toggle, "clicked")
        qtbot.waitUntil(lambda: panel.property("consoleReveal") == 0)
        assert window.grabWindow().save(str(output_dir / f"card-{parameter_count}-collapsed.png"))
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("count,unit,filled", [
    (0, 1, 0), (9, 1, 9), (10, 10, 1), (99, 10, 9),
    (100, 100, 1), (999, 100, 9), (1000, 1000, 1), (10000, 10000, 1),
])
def test_decade_usage_counter_changes_scale_at_powers_of_ten(qapp, count, unit, filled):
    engine = QQmlEngine()
    component = QQmlComponent(engine, QUrl.fromLocalFile(str(
        package_root() / "ui/qml/components/DecadeUsageCounter.qml")))
    counter = component.createWithInitialProperties({"count": count, "width": 408})
    assert counter is not None, [error.toString() for error in component.errors()]
    try:
        assert counter.property("unit") == unit
        assert counter.property("filledCount") == filled
    finally:
        counter.deleteLater()
        engine.deleteLater()


def test_decade_card_back_centers_bright_artwork_and_scales_with_pack(qapp, qtbot):
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Window
import "components"
import "theme"
Window {
    width: 600; height: 530; visible: true; color: "#F5F6FA"
    Component.onCompleted: { Theme.darkMode = true; Theme.decadeMode = true }
    MechanicalCardFace {
        objectName: "smallBack"
        x: 18; y: 20; width: 220; height: 342
        cardTitle: "Small card back"
        cardIcon: "folder"
    }
    MechanicalCardFace {
        objectName: "largeBack"
        x: 260; y: 20; width: 314; height: 486
        cardTitle: "Large card back"
        cardIcon: "terminal"
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/DecadeBackHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        small = window.findChild(QObject, "smallBack")
        large = window.findChild(QObject, "largeBack")
        for back in (small, large):
            art = back.findChild(QObject, "decadeCardArtwork")
            assert art.property("backFace")
            glyph = art.findChild(QObject, "decadeCardArtworkIcon")
            assert glyph.property("icon") == back.property("cardIcon")
            glyph_bounds = glyph.mapRectToItem(back, glyph.boundingRect())
            assert glyph_bounds.center() == back.boundingRect().center()
            assert art.property("centerY") == back.height() / 2
            assert art.property("motifSize") < back.width() / 2
            divider = back.findChild(QObject, "decadeCardBackTitleDivider")
            bounds = divider.mapRectToItem(back, divider.boundingRect())
            assert 0 < bounds.left() < bounds.right() < back.width()
            assert bounds.top() < back.height() / 4
            assert back.property("radius") < 6
        assert small.findChild(QObject, "decadeCardArtwork").property("motifSize") < \
            large.findChild(QObject, "decadeCardArtwork").property("motifSize")
        small.setProperty("cardIcon", "settings")
        assert small.findChild(QObject, "decadeCardArtworkIcon").property("icon") == "settings"
        output_dir = Path("build/decade-design")
        output_dir.mkdir(parents=True, exist_ok=True)
        assert window.grabWindow().save(str(output_dir / "card-back-sizes.png"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


def test_session_reuses_tool_data_until_the_script_changes(launcher, monkeypatch):
    _, backend, _, _ = launcher
    tool = create_tool(backend, "Cached metadata", command="print('${value:before}')")
    conversions = []
    original = backend.tool_data
    def convert(value):
        conversions.append(value.id if value else "")
        return original(value)
    monkeypatch.setattr(backend, "tool_data", convert)
    session = backend.createToolSession(tool.id)
    try:
        for _ in range(200):
            assert session.selectedTool["id"] == tool.id
        assert conversions.count(tool.id) == 1
        assert session.setParameterDefault("value", "after")
        assert session.selectedTool["parameters"][0]["default"] == "after"
        count = conversions.count(tool.id)
        for _ in range(200):
            assert session.selectedTool["parameters"][0]["default"] == "after"
        assert conversions.count(tool.id) == count
    finally:
        session.dispose()


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
        assert panel.mask().boundingRect().width() == 40
        assert panel.mask().boundingRect().height() == 40
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
        # Mouse coordinates come from the actual delegate before drawer collapse.
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        row = next(item for item in visual_items(panel.contentItem())
                   if item.objectName().startswith("scriptRow_") and item.isVisible())
        point = row.mapToGlobal(QPointF(0, 0))
        expected_origin = QRectF(point.x(), point.y(), row.width(), row.height())
        origins = []
        monkeypatch.setattr(backend, "open_custom_tool_shortcut",
                            lambda tool_id: origins.append(controller.cardLaunchOrigin(tool_id)))
        rect = row.mapRectToItem(panel.contentItem(), row.boundingRect())
        QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        assert origins == [expected_origin]
        assert controller.expanded
        qtbot.wait(250)
        assert controller.expanded  # Launching no longer schedules a collapse.
        qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
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


@pytest.mark.parametrize("multiple", [False, True, "burst", "bottom"])
def test_main_window_settings_navigation_and_close_to_tray(
    launcher, qapp, qtbot, monkeypatch, multiple,
):
    if not terminal_library_path().exists():
        pytest.skip("Full application requires the built native terminal")
    register_terminal_type()
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    controller, backend, settings, _ = launcher
    settings.markUserGuideSeen()
    settings.saveThemeMode("decade")
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

        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        for mode in ("light", "dark", "decade"):
            choice = next(item for item in visual_items(window.contentItem())
                          if item.objectName() == "themeChoice_" + mode)
            assert choice.isVisible()
            rect = choice.mapRectToItem(window.contentItem(), choice.boundingRect())
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
            assert settings.themeMode == mode
        assert window.property("chromeBackgroundColor").name() == "#19191f"
        assert window.grabWindow().save("build/floating-settings.png")
        if tray.available:
            assert not window.close()
            qtbot.waitUntil(lambda: not window.isVisible() and controller.visible)
        if multiple:
            window.hide()
            monkeypatch.setattr(controller, "_ordinary_window_active", lambda:
                                FloatingLauncherController._ordinary_window_active(controller))
            controller.reconcile()
            if multiple == "bottom":
                tools = [create_tool(backend, f"Bottom {i:02}", command="print('${value:A}')")
                         for i in range(18)]
                controller.setToolSortMode("name")
                controller.togglePinned()
                controller.toggleExpanded()
                pack = window.findChild(QObject, "floatingScriptList")
                view = pack.findChild(QObject, "sharedScriptList")
                panel = window.findChild(QQuickWindow, "floatingScriptPanelWindow")
                qtbot.wait(250)
                QMetaObject.invokeMethod(view, "positionViewAtEnd")
                qtbot.wait(150)
                QMetaObject.invokeMethod(view, "forceLayout")
                QMetaObject.invokeMethod(view, "positionViewAtEnd")
                qtbot.wait(150)
                opened_ids = set()
                for attempt in range(5):
                    tid = controller.toolsModel.lastToolId("all")
                    face = window.findChild(QObject, "deckCard_" + tid)
                    assert face is not None
                    bounds = face.mapRectToItem(view, face.boundingRect())
                    assert bounds.top() >= -1 and bounds.bottom() <= view.height() + 1
                    if attempt == 0:
                        assert panel.grabWindow().save("build/decade-bottom-complete.png")
                    samples = []
                    sampler = QTimer(window)
                    sampler.setInterval(8)
                    sampler.timeout.connect(lambda samples=samples: samples.append(
                        view.property("contentY") - view.property("bottomRevealOffset")))
                    sampler.start()
                    point = face.mapToItem(panel.contentItem(), face.boundingRect().center())
                    QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point.toPoint())
                    qtbot.waitUntil(lambda tid=tid: any(card.objectName() == "recentToolWindow"
                        and card.property("toolId") == tid and card.isVisible()
                        for card in qapp.topLevelWindows()), timeout=7000)
                    qtbot.waitUntil(lambda tid=tid: tid not in ids(controller.toolsModel))
                    opened_ids.add(tid)
                    qtbot.wait(300)
                    sampler.stop()
                    sampler.deleteLater()
                    assert len({round(value, 1) for value in samples}) >= 3
                    assert view.property("atYEnd")
                    assert controller.toolsModel.count == 17 - attempt
                    expected_last = tools[16 - attempt].id
                    assert controller.toolsModel.lastToolId("all") == expected_last
                assert controller.openCardCount == len(opened_ids)
                assert not warnings, warnings
                return
            if multiple == "burst":
                tools = [create_tool(backend, f"Burst {i}",
                                     command="print('${one:A}', '${two:B}', '${three:C}')")
                         for i in range(10)]
                controller.togglePinned()
                controller.toggleExpanded()
                controller.setToolSortMode("name")
                pack = window.findChild(QObject, "floatingScriptList")
                qtbot.wait(250)
                def cards():
                    return [card for card in qapp.topLevelWindows()
                            if card.objectName() == "recentToolWindow" and card.isVisible()]
                view = pack.findChild(QObject, "sharedScriptList")
                scroll_bar = view.findChild(QObject, "scriptListScrollBar")
                gutter = view.property("scrollGutter")
                beats, overlap, return_overlap, recall_scroll_bars = [], [], [], []
                heartbeat = QTimer()
                heartbeat.setInterval(16)
                def sample():
                    beats.append(perf_counter())
                    current = cards()
                    overlap.append(sum(card.property("entryAnimationRunning") for card in current))
                    return_overlap.append(sum(card.property("recycleAnimationRunning")
                                              for card in current))
                    if pack.property("continuousRecall"):
                        recall_scroll_bars.append((scroll_bar.isVisible(),
                                                   view.property("scrollGutter"),
                                                   view.property("needsVerticalScroll")))
                heartbeat.timeout.connect(sample)
                heartbeat.start()
                try:
                    for index, tool in enumerate(tools):
                        QTimer.singleShot(index * 130,
                            lambda tid=tool.id: QMetaObject.invokeMethod(
                                pack, "activateTool", Q_ARG("QVariant", tid),
                                Q_ARG("QVariant", None)))
                    qtbot.waitUntil(lambda: len(cards()) == 10, timeout=10000)
                    qtbot.waitUntil(lambda: all(not card.property("entryAnimationRunning")
                                               for card in cards()), timeout=10000)
                    assert max(overlap) >= 2
                    assert all(card.findChild(QObject, "recentToolFormLoader").property("item")
                               is not None for card in cards())
                    before_cleanup = backend.findChildren(ToolSessionController)
                    assert len(before_cleanup) == 10
                    recall = window.findChild(QObject, "floatingRecallAllButton")
                    QMetaObject.invokeMethod(recall, "clicked")
                    qtbot.waitUntil(lambda: not cards(), timeout=10000)
                    qtbot.waitUntil(lambda: not backend.findChildren(ToolSessionController),
                                    timeout=10000)
                    assert controller.openCardCount == 0
                    assert set(ids(controller.toolsModel)) == {tool.id for tool in tools}
                    assert max(return_overlap) >= 2
                    assert recall_scroll_bars
                    assert not any(shown for shown, _, _ in recall_scroll_bars)
                    assert any(needed for _, _, needed in recall_scroll_bars)
                    assert all(width == gutter for _, width, _ in recall_scroll_bars)
                    qtbot.waitUntil(scroll_bar.isVisible)
                    gaps = sorted((b - a) * 1000 for a, b in zip(beats, beats[1:], strict=False))
                    print(f"10-card GUI heartbeat: p95={gaps[int(len(gaps) * .95)]:.1f} ms, "
                          f"max={max(gaps):.1f} ms")
                    # Closing/recalling during shell incubation must not open a late window.
                    backend.recentToolDialogRequested.emit(tools[0].id)
                    QMetaObject.invokeMethod(window, "closeRecentToolWindows")
                    qtbot.wait(250)
                    assert not cards()
                    qtbot.waitUntil(lambda: not backend.findChildren(ToolSessionController))
                    assert not warnings, warnings
                finally:
                    heartbeat.stop()
                return
            alpha = create_tool(backend, "Window A", command="print('${message:Alpha}')")
            beta = create_tool(backend, "Window B", command="print('${message:Beta}')")

            def tool_windows():
                return {w.property("toolId"): w for w in qapp.topLevelWindows()
                        if w.objectName() == "recentToolWindow" and w.isVisible()}

            def set_message(target, text):
                qtbot.waitUntil(lambda: target.findChild(
                    QObject, "recentToolFormLoader").property("item") is not None)
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

            controller.refreshTools()
            controller.toggleExpanded()
            panel = window.findChild(QQuickWindow, "floatingScriptPanelWindow")
            qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
            rows = [item for item in visual_items(panel.contentItem())
                    if item.objectName().startswith("scriptRow_")]
            assert len(rows) == 2
            rows.sort(key=lambda item: item.y())
            assert rows[1].z() > rows[0].z()
            face = next(item for item in visual_items(rows[0])
                        if item.objectName() == "deckCard_" + rows[0].property("toolId"))
            assert face.height() > rows[0].height()
            assert panel.grabWindow().save("build/decade-card-pack.png")
            row = next(item for item in rows if item.property("toolId") == alpha.id)
            original_face = next(item for item in visual_items(row)
                                 if item.objectName() == "deckCard_" + alpha.id)
            point = row.mapToItem(panel.contentItem(), QPointF(row.width() / 2, 35))
            QTest.mouseClick(panel, Qt.MouseButton.LeftButton, pos=point.toPoint())
            assert not any(w.objectName() == "cardFlightWindow" for w in qapp.topLevelWindows())
            qtbot.waitUntil(lambda: alpha.id in tool_windows())
            first = tool_windows()[alpha.id]
            assert first.property("cardFace") is original_face
            assert original_face.window() is first
            assert first.property("launchOrigin").height() > 300
            qtbot.waitUntil(lambda: not first.property("entryAnimationRunning"))
            assert alpha.id not in ids(controller.toolsModel)
            assert controller.openCardCount == 1
            assert not first.findChild(QObject, "recentToolMinimizeButton").isVisible()
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
            qtbot.waitUntil(lambda: controller.openCardCount == 2)
            assert controller.toolsModel.count == 0
            settings.saveThemeMode("light")
            assert set(ids(controller.toolsModel)) == {alpha.id, beta.id}
            settings.saveThemeMode("decade")
            assert controller.toolsModel.count == 0
            assert session_a.selectedTool["id"] == alpha.id
            assert session_b.selectedTool["id"] == beta.id
            # Reopening a tool activates its existing window without resetting its form.
            controller.launchTool(alpha.id)
            qtbot.waitUntil(first.isActive)
            assert first.property("activationAnimationRunning")
            assert not first.property("entryAnimationRunning")
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
            controller.launchTool(alpha.id)
            assert first.property("activationAnimationRunning")
            assert not first.property("entryAnimationRunning")
            assert len(tool_windows()) == 2
            assert runs == [(alpha.id, values_a), (beta.id, values_b)]
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
            controller.collapse()
            QMetaObject.invokeMethod(first, "closeCardAnimated")
            assert alpha.id in controller.returningCardIds
            assert first.isVisible()
            qtbot.waitUntil(lambda: first.property("recycleAnimationRunning"))
            assert alpha.id not in ids(controller.toolsModel)  # No empty return slot.
            assert first.property("cardFace") is original_face
            assert original_face.window() is first
            landing = first.findChild(QObject, "mechanicalCardMotion").property("flightGeometry")
            landing_scale = landing["sourceWidth"] / first.width()
            inset = 4 * first.property("cardUiScale") * landing_scale
            expected_origin = QPointF(landing["x"] + landing["sourceX"] + inset,
                                      landing["y"] + landing["sourceY"] + inset)
            expected_width = landing["sourceWidth"] - 2 * inset
            qtbot.waitUntil(lambda: len(tool_windows()) == 1)
            assert alpha.id in ids(controller.toolsModel)
            assert beta.id not in ids(controller.toolsModel)
            assert not controller.returningCardIds
            assert original_face.window() is panel  # The item is docked, not recreated.
            docked_origin = original_face.mapToGlobal(QPointF(0, 0))
            assert abs(docked_origin.x() - expected_origin.x()) <= 1
            assert abs(docked_origin.y() - expected_origin.y()) <= 1
            assert abs(original_face.width() - expected_width) <= 1
            assert original_face.parentItem().width() == original_face.width()
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
            # All themes expose the same controls; bulk close preserves running jobs.
            for mode in ("decade", "light", "dark"):
                settings.saveThemeMode(mode)
                backend.recentToolDialogRequested.emit(alpha.id)
                backend.recentToolDialogRequested.emit(beta.id)
                qtbot.waitUntil(lambda: len(tool_windows()) == 2)
                qtbot.waitUntil(lambda: controller.openCardCount == 2)
                pin = window.findChild(QObject, "floatingPinButton")
                recall = window.findChild(QObject, "floatingRecallAllButton")
                assert not pin.property("showHoverTips")
                assert not recall.property("showHoverTips")
                if not controller.pinned:
                    QMetaObject.invokeMethod(pin, "clicked")
                if not controller.expanded:
                    controller.toggleExpanded()
                qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
                assert recall.isEnabled()
                QMetaObject.invokeMethod(recall, "clicked")
                if mode == "decade":
                    assert len(controller.returningCardIds) == 1
                    first_return = controller.returningCardIds[0]
                    # Repeated clicks must not restart the cadence or launch the next card early.
                    QMetaObject.invokeMethod(recall, "clicked")
                    for card_window in tool_windows().values():
                        assert card_window.property("recallQueued")
                        QMetaObject.invokeMethod(card_window, "activateCard")
                    qtbot.wait(20)  # Less than the configured 50 ms recall cadence.
                    assert controller.returningCardIds == [first_return]
                    assert len(tool_windows()) == 2
                    samples = []
                    landings, checked = {}, set()
                    while tool_windows():
                        samples.append(tuple(controller.returningCardIds))
                        current = tool_windows()
                        for tid, card_window in current.items():
                            face = card_window.property("cardFace")
                            if card_window.property("recycleAnimationRunning") and face:
                                motion = card_window.findChild(QObject, "mechanicalCardMotion")
                                g = motion.property("flightGeometry")
                                scale = g["sourceWidth"] / card_window.width()
                                inset = 4 * card_window.property("cardUiScale") * scale
                                landings[tid] = (face, QPointF(g["x"] + g["sourceX"] + inset,
                                                              g["y"] + g["sourceY"] + inset))
                        for tid, (face, expected) in landings.items():
                            if tid not in current and tid not in checked:
                                assert face.window() is panel
                                actual = face.mapToGlobal(QPointF(0, 0))
                                assert abs(actual.x() - expected.x()) <= 1
                                assert abs(actual.y() - expected.y()) <= 1
                                checked.add(tid)
                        qtbot.wait(10)
                        assert len(samples) < 300
                    assert max(map(len, samples)) == 2  # Flights overlap before either lands.
                    assert {tid for batch in samples for tid in batch} == {alpha.id, beta.id}
                qtbot.waitUntil(lambda: not tool_windows())
                qtbot.waitUntil(lambda: not backend.findChildren(ToolSessionController))
                assert controller.openCardCount == 0
                assert set(ids(controller.toolsModel)) == {alpha.id, beta.id}
                assert controller.expanded and controller.pinned
                assert not recall.isEnabled()
                assert stops == [alpha.id] and beta.id in active
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
