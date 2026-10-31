import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

import pytest
from PySide6.QtCore import (
    QDateTime,
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
from PySide6.QtGui import (
    QCursor,
    QFontDatabase,
    QInputDevice,
    QPointingDevice,
    QWheelEvent,
    QWindow,
)
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.system_tray import SystemTrayController
from poptools.infrastructure.theme_catalog import ThemeCatalog
from poptools.native_terminal import register_terminal_type, terminal_library_path
from poptools.paths import package_root, resource_path
from poptools.viewmodels.developer_console_controller import DeveloperConsoleController
from poptools.viewmodels.floating_launcher_controller import dock_geometry
from poptools.viewmodels.jira_feishu_controller import JiraFeishuController
from poptools.viewmodels.preset_controller import PresetController
from poptools.viewmodels.update_controller import UpdateController
from test_floating_launcher import create_tool, ids
from test_floating_launcher import launcher as launcher


@pytest.mark.parametrize("available", [QRect(0, 0, 1920, 1040),
                                       QRect(-1280, -400, 1280, 720), QRect(40, 20, 280, 180)])
def test_dock_geometry_respects_work_area_and_bottom_margin(available):
    dock = dock_geometry(available, (960, 208))
    assert available.contains(dock)
    assert abs(dock.center().x() - available.center().x()) <= 1
    assert available.bottom() - dock.bottom() == 16


def test_zio_theme_config_and_independent_position_persist(launcher):
    _, _, settings, _ = launcher
    store = settings.config_store
    catalog = ThemeCatalog(package_root() / "ui/qml/theme/configs")
    catalog.refresh()
    assert catalog.contains("zio")
    assert settings.saveThemeMode("zio")
    assert settings.darkTheme
    store.set_floating_launcher_position("sidebar", 0.7)
    store.set_floating_dock_screen("dock")
    reopened = ConfigStore(store.paths)
    assert reopened.theme_mode() == "zio"
    assert reopened.floating_launcher_position() == ("sidebar", 0.7)
    assert reopened.floating_dock_screen() == "dock"


def test_dock_drag_and_screen_removal_preserve_sidebar_position(launcher, qapp, monkeypatch):
    controller, _, settings, _ = launcher
    sidebar = settings.config_store.floating_launcher_position()

    class Screen:
        def __init__(self, name, bounds):
            self._name, self._bounds = name, bounds

        def name(self):
            return self._name

        def availableGeometry(self):
            return self._bounds

    primary = Screen("primary", QRect(0, 0, 1920, 1040))
    secondary = Screen("secondary", QRect(-1280, -400, 1280, 720))
    screens = [primary, secondary]
    monkeypatch.setattr(qapp, "screens", lambda: screens)
    monkeypatch.setattr(qapp, "primaryScreen", lambda: primary)
    monkeypatch.setattr(qapp, "screenAt", lambda point: secondary)
    monkeypatch.setattr(QCursor, "pos", lambda: QPoint(-500, 200))
    panel = QWindow()
    controller._screen = primary
    try:
        controller.attachDockWindow(panel, 800, 208)
        controller.beginDrag()
        controller.endDrag()
        assert secondary.availableGeometry().contains(panel.geometry())
        assert settings.config_store.floating_dock_screen() == "secondary"
        assert settings.config_store.floating_launcher_position() == sidebar
        screens.remove(secondary)
        controller._screen_removed(secondary)
        controller.reposition()
        assert primary.availableGeometry().contains(panel.geometry())
    finally:
        panel.close()


@pytest.fixture
def zio_app(launcher, qapp, qtbot):
    if not terminal_library_path().exists():
        pytest.skip("Full application requires the built native terminal")
    register_terminal_type()
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    controller, backend, settings, _ = launcher
    settings.markUserGuideSeen()
    settings.saveThemeMode("zio")
    preset = PresetController()
    jira = JiraFeishuController(settings.config_store.paths.data_dir)
    terminal = DeveloperConsoleController(settings.python_environment)
    update = UpdateController(settings.config_store, auto_check_enabled=False)
    quit_policy = qapp.quitOnLastWindowClosed()
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
    controller.togglePinned()
    controller.toggleExpanded()
    dock = window.findChild(QQuickWindow, "zioDockWindow")
    qtbot.waitUntil(lambda: dock.isVisible() and dock.property("revealProgress") == 1)
    try:
        yield window, controller, backend, settings, dock, warnings
    finally:
        QMetaObject.invokeMethod(window, "closeRecentToolWindows")
        qtbot.wait(100)
        controller.shutdown()
        terminal.shutdown()
        jira.shutdown()
        tray._quitting = True
        window.close()
        engine.deleteLater()
        qapp.processEvents()
        qapp.setQuitOnLastWindowClosed(quit_policy)


def visible_cards(qapp):
    return {w.property("toolId"): w for w in qapp.topLevelWindows()
            if w.objectName() == "recentToolWindow" and w.isVisible()}


def settled(card):
    return not any(card.property(prop) for prop in (
        "entryAnimationRunning", "recycleAnimationRunning", "returnPending", "handoffBlocked"))


@pytest.mark.gui
def test_zio_compact_footer_round_dials_and_sort_cycle(zio_app, qapp, qtbot):
    window, controller, backend, _, dock, warnings = zio_app
    for index in range(4):
        create_tool(backend, f"Compact {index}")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 4)
    qtbot.wait(100)
    view = window.findChild(QObject, "zioDockCards")
    search = window.findChild(QObject, "zioDockSearch")
    clear = search.findChild(QObject, "zioDockSearchClearButton")
    assert not clear.isVisible()
    search.setProperty("text", "Compact 0")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
    assert clear.isVisible()
    point = clear.mapToItem(dock.contentItem(), clear.boundingRect().center()).toPoint()
    QTest.mouseClick(dock, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: controller.toolsModel.count == 4)
    assert search.property("text") == "" and not clear.isVisible()
    assert search.hasActiveFocus()
    actions = window.findChild(QObject, "zioDockActions")
    buckle = window.findChild(QObject, "zioDockBuckle")
    base = window.findChild(QObject, "zioDockBase")
    assert dock.height() == 176
    search_rect = search.mapRectToItem(
        dock.contentItem(), QRectF(0, 0, search.width(), search.height()),
    )
    actions_rect = actions.mapRectToItem(dock.contentItem(), actions.boundingRect())
    assert search_rect.top() > view.y() + view.height()
    assert search_rect.center().y() == actions_rect.center().y()
    assert search_rect.right() < buckle.x()
    assert actions_rect.left() > buckle.x() + buckle.width()
    assert base.y() == 132 and base.height() == 40
    search_block = window.findChild(QObject, "zioSearchBeltBlock")
    assert search.parentItem() is search_block
    assert actions.parentItem() is base
    assert buckle.width() == buckle.height() == 48
    assert window.findChild(QObject, "zioDockButtonDial") is not None
    assert window.findChild(QObject, "zioDockBrandDial") is not None
    assert not dock.mask().contains(QPoint(20, 20))
    controls = [window.findChild(QObject, "zioDock" + name)
                for name in ("Sort", "Pin", "Recall", "Collapse")]
    assert len({round(button.width()) for button in controls}) == 4
    assert len({button.height() for button in controls}) == 3
    for button in controls:
        assert not button.property("showHoverTips")
        assert button.width() > button.height()
        bounds = button.mapRectToItem(base, button.boundingRect())
        assert base.boundingRect().contains(bounds)

    before = set(qapp.topLevelWindows())
    sort = window.findChild(QObject, "zioDockSort")
    assert controller.setToolSortMode("added_time")
    for mode, icon in (("name", "sort_by_alpha"), ("usage", "trending_up"),
                       ("custom", "drag_indicator"), ("added_time", "schedule")):
        point = sort.mapToItem(dock.contentItem(), sort.boundingRect().center()).toPoint()
        QTest.mouseClick(dock, Qt.MouseButton.LeftButton, pos=point)
        qtbot.waitUntil(lambda expected=mode: controller.toolSortMode == expected)
        assert sort.property("iconName") == icon
        assert not sort.property("menuOpen")
        assert not controller._menu_open
        assert not any(w.isVisible() for w in set(qapp.topLevelWindows()) - before)

    def items(item):
        yield item
        for child in item.childItems():
            yield from items(child)

    qtbot.waitUntil(lambda: len([item for item in items(dock.contentItem())
        if item.objectName().startswith("deckCard_") and item.isVisible()]) == 4)
    qtbot.wait(50)
    assert dock.grabWindow().save("build/zio-dock-compact.png")
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.skipif(sys.platform != "win32", reason="Checks native Windows stacking order")
def test_zio_new_card_stays_above_an_older_card_when_its_scan_finishes(zio_app, qapp, qtbot):
    _, controller, backend, _, _, warnings = zio_app
    tools = [create_tool(backend, f"Layer {index}") for index in range(2)]
    qtbot.waitUntil(lambda: controller.toolsModel.count == 2)
    get_window = ctypes.WinDLL("user32", use_last_error=True).GetWindow
    get_window.argtypes = [wintypes.HWND, wintypes.UINT]
    get_window.restype = wintypes.HWND

    def is_above(front, back):
        handle = int(front.winId())
        while handle:
            if handle == int(back.winId()):
                return True
            handle = get_window(handle, 2)  # GW_HWNDNEXT: walk down the native Z order.
        return False

    def open_paused(tool):
        backend.recentToolDialogRequested.emit(tool.id)
        qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
        card = visible_cards(qapp)[tool.id]
        entry = card.findChild(QObject, "mechanicalCardEntryAnimation")
        qtbot.waitUntil(lambda: entry.property("running"))
        assert QMetaObject.invokeMethod(entry, "pause")
        return card, card.findChild(QObject, "mechanicalCardMotion")

    older, older_motion = open_paused(tools[0])
    qtbot.waitUntil(lambda: older_motion.property("contentReady"), timeout=7000)
    older_motion.setProperty("progress", 0.7)
    assert 0 < older_motion.property("scan") < 1
    newer, newer_motion = open_paused(tools[1])
    native_ids = older.winId(), newer.winId()
    newer_motion.setProperty("progress", 0.2)
    qtbot.wait(40)
    assert is_above(newer, older)
    qtbot.waitUntil(lambda: newer_motion.property("contentReady"), timeout=7000)
    newer_motion.setProperty("progress", 0.7)
    qtbot.wait(40)
    assert is_above(newer, older)
    # Dock requests can also raise a card while its original entry is still in progress.
    backend.recentToolDialogRequested.emit(tools[0].id)
    qtbot.wait(40)
    assert is_above(older, newer)
    assert older.property("entryAnimationRunning")
    assert older_motion.property("progress") == 0.7
    backend.recentToolDialogRequested.emit(tools[1].id)
    qtbot.wait(40)
    assert is_above(newer, older)
    assert newer_motion.property("progress") == 0.7
    assert len(visible_cards(qapp)) == 2
    assert QMetaObject.invokeMethod(older_motion, "finish")
    qtbot.wait(40)
    assert not older.property("entryAnimationRunning")
    assert newer.property("entryAnimationRunning")
    assert is_above(newer, older)
    assert QMetaObject.invokeMethod(newer_motion, "finish")
    qtbot.wait(40)
    assert is_above(newer, older)
    assert (older.winId(), newer.winId()) == native_ids
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_idle_dial_fades_on_hover_and_tracks_local_time(zio_app, qtbot):
    window, controller, _, _, dock, warnings = zio_app
    buckle = window.findChild(QObject, "zioDockBuckle")
    dial = window.findChild(QObject, "zioDockButtonDial")
    controller.collapse()
    QTest.mouseMove(dock, QPoint(10, 10))
    qtbot.waitUntil(lambda: dock.property("revealProgress") == 0)
    qtbot.waitUntil(lambda: buckle.opacity() == pytest.approx(0.55))
    point = buckle.mapToItem(dock.contentItem(), QPointF(24, 24)).toPoint()
    QTest.mouseMove(dock, point)
    qtbot.waitUntil(lambda: buckle.opacity() == 1)
    QTest.mouseMove(dock, QPoint(10, 10))
    qtbot.waitUntil(lambda: buckle.opacity() == pytest.approx(0.55))

    assert abs(dial.property("currentTime").msecsTo(QDateTime.currentDateTime())) < 1500
    before = dial.property("currentTime")
    qtbot.waitUntil(lambda: dial.property("currentTime") != before, timeout=2000)
    dial.setProperty("followClock", False)
    dial.setProperty("currentTime",
                     QDateTime.fromString("2026-10-29T15:24:30", Qt.DateFormat.ISODate))
    assert dial.property("hourAngle") == pytest.approx(102.25)
    assert dial.property("minuteAngle") == 147
    assert dial.property("secondAngle") == 180
    assert dock.grabWindow().save("build/zio-dock-idle.png")
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_entry_has_no_rotation_and_only_one_scan(zio_app, qapp, qtbot):
    window, controller, backend, _, _, warnings = zio_app
    tool = create_tool(backend, "Scan once")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
    backend.recentToolDialogRequested.emit(tool.id)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    card = visible_cards(qapp)[tool.id]
    motion = card.findChild(QObject, "mechanicalCardMotion")
    samples = []
    timer = QTimer()
    timer.setInterval(8)
    timer.timeout.connect(lambda: samples.append((motion.property("scan"),
        motion.property("displayedSpinAngle"), motion.property("flightTilt"),
        card.property("focusScanRunning"))))
    timer.start()
    try:
        qtbot.waitUntil(lambda: settled(card), timeout=7000)
        qtbot.wait(100)
    finally:
        timer.stop()
    assert samples
    assert all(angle == tilt == 0 and not focusing for _, angle, tilt, focusing in samples)
    scans = [sample[0] for sample in samples]
    assert all(left <= right for left, right in zip(scans, scans[1:], strict=False))
    assert any(0 < value < 1 for value in scans)
    assert scans[-1] == 1
    assert not motion.property("entrySpinEnabled")
    phone = card.findChild(QObject, "deviceSelectorPhoneIcon")
    assert phone is not None and phone.isVisible()
    assert card.findChild(QObject, "deviceSelectorPhoneFrame") is not None
    assert card.findChild(QObject, "zioDeviceWatch") is None
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_scroll_direction_and_complete_end_cards_after_model_changes(zio_app, qapp, qtbot):
    window, controller, backend, _, dock, warnings = zio_app
    for index in range(22):
        create_tool(backend, f"Edge {index:02}")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 22)
    view = window.findChild(QObject, "zioDockCards")

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    def check_endpoint(last):
        assert QMetaObject.invokeMethod(view, "stopScrolling")
        method = "positionViewAtEnd" if last else "positionViewAtBeginning"
        assert QMetaObject.invokeMethod(view, method)
        qtbot.wait(40)
        tid = ids(controller.toolsModel)[-1 if last else 0]
        host = next(item for item in visual_items(dock.contentItem())
                    if item.objectName() == "zioMiniCard_" + tid)
        rect = host.mapRectToItem(view, host.boundingRect())
        assert rect.left() >= 7
        assert rect.right() <= view.width() - 7
        for item in visual_items(dock.contentItem()):
            if not item.objectName().startswith("zioMiniCard_"):
                continue
            bounds = item.mapRectToItem(view, item.boundingRect())
            if bounds.right() > 0 and bounds.left() < view.width():
                assert bounds.left() >= 0 and bounds.right() <= view.width()

    def wheel(delta):
        position = view.mapToItem(dock.contentItem(), QPointF(view.width() / 2, 70))
        global_position = dock.mapToGlobal(position.toPoint())
        event = QWheelEvent(position, QPointF(global_position), QPoint(), QPoint(0, delta),
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                            Qt.ScrollPhase.ScrollUpdate, False)
        qapp.sendEvent(dock, event)
        qapp.processEvents()

    check_endpoint(False)
    initial = view.property("contentX")
    wheel(-120)
    qtbot.waitUntil(lambda: not view.property("scrollAnimating"))
    assert view.property("contentX") > initial
    wheel(120)
    qtbot.waitUntil(lambda: not view.property("scrollAnimating"))
    assert abs(view.property("contentX") - initial) <= 1
    check_endpoint(True)
    # Removing items before the viewport changes ListView.originX; zero is not its boundary.
    controller.toolsModel.set_excluded_ids(set(ids(controller.toolsModel)[:3]))
    qtbot.wait(60)
    check_endpoint(False)
    wheel(12000)
    check_endpoint(True)
    wheel(-12000)
    check_endpoint(False)
    search = window.findChild(QObject, "zioDockSearch")
    search.setProperty("text", "Edge 1")
    qtbot.wait(60)
    check_endpoint(False)
    search.setProperty("text", "")
    qtbot.wait(60)
    check_endpoint(True)
    assert dock.grabWindow().save("build/zio-dock-last-card.png")
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("notch", [120, 15])
@pytest.mark.parametrize("inverted", [False, True])
@pytest.mark.parametrize("axis", ["vertical", "horizontal"])
def test_zio_slow_notches_and_pixel_snapping_never_reverse_direction(
    zio_app, qapp, qtbot, notch, inverted, axis,
):
    window, controller, backend, _, dock, warnings = zio_app
    for index in range(24):
        create_tool(backend, f"Wheel {index:02}")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 24)
    view = window.findChild(QObject, "zioDockCards")
    qtbot.wait(80)
    origin = view.property("minimumContentX")
    view.setProperty("contentX", origin + 6 * 84)

    touchpad = QPointingDevice("Test touchpad", 42, QInputDevice.DeviceType.TouchPad,
        QPointingDevice.PointerType.Finger,
        QInputDevice.Capability.Position | QInputDevice.Capability.PixelScroll, 2, 0)

    def wheel(angle=0, pixels=0):
        position = view.mapToItem(dock.contentItem(), QPointF(view.width() / 2, 70))
        global_position = dock.mapToGlobal(position.toPoint())
        polarity = -1 if inverted else 1

        def delta(value):
            return (QPoint(0, value * polarity) if axis == "vertical"
                    else QPoint(value * polarity, 0))

        event = QWheelEvent(position, QPointF(global_position), delta(pixels),
                            delta(angle or pixels), Qt.MouseButton.NoButton,
                            Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.ScrollUpdate, inverted,
                            device=touchpad if pixels else QPointingDevice.primaryPointingDevice())
        qapp.sendEvent(dock, event)
        qapp.processEvents()

    # Up/left reveals earlier slots; down/right reveals later slots.
    for index in range(3):
        tid = ids(controller.toolsModel)[7 + index]
        face = window.findChild(QObject, "deckCard_" + tid)
        host = face.parentItem()
        assert host.objectName() == "zioMiniCard_" + tid
        card_x = host.mapToItem(view, QPointF()).x()
        title = face.property("cardTitle")
        before = view.property("contentX")
        wheel(angle=notch)
        expected = origin + (5 - index) * 84
        assert view.property("scrollAnimating")
        qtbot.wait(50)
        assert expected < view.property("contentX") < before
        assert host.mapToItem(view, QPointF()).x() == pytest.approx(
            card_x - (view.property("contentX") - before), abs=0.01)
        assert face.parentItem() is host and face.property("cardTitle") == title
        if index == 0 and notch == 120 and not inverted:
            assert dock.grabWindow().save("build/zio-dock-scrolling.png")
        qtbot.waitUntil(lambda: not view.property("scrollAnimating"))
        assert view.property("contentX") == expected
    # Rapid notches use the same direction and distance as isolated notches.
    for index in range(3):
        wheel(angle=-notch)
        assert view.property("scrollTarget") == origin + (4 + index) * 84
    qtbot.waitUntil(lambda: not view.property("scrollAnimating"))
    assert view.property("contentX") == origin + 6 * 84

    # An off-grid starting position must not make a following notch snap backwards.
    for angle in (notch, -notch):
        view.setProperty("contentX", origin + 6 * 84 + 20)
        before = view.property("contentX")
        wheel(angle=angle)
        qtbot.waitUntil(lambda: not view.property("scrollAnimating"))
        after = view.property("contentX")
        assert after < before if angle > 0 else after > before
        assert abs((after - origin) % 84) < 0.01
        qtbot.wait(100)
        assert view.property("contentX") == after

    # A smooth swipe keeps moving in its original direction when the idle snap runs.
    view.setProperty("contentX", origin + 6 * 84)
    wheel(pixels=10)
    immediate = view.property("contentX")
    assert immediate == origin + 6 * 84 - 10
    qtbot.wait(380)
    assert view.property("contentX") < immediate
    wheel(pixels=-10)
    immediate = view.property("contentX")
    qtbot.wait(380)
    assert view.property("contentX") > immediate
    # Reverse an unfinished run immediately instead of following its queued target.
    view.setProperty("contentX", origin + 6 * 84)
    wheel(angle=-notch)
    wheel(angle=-notch)
    wheel(angle=-notch)
    qtbot.wait(50)
    before = view.property("contentX")
    wheel(angle=notch)
    assert view.property("scrollTarget") < before
    qtbot.wait(50)
    assert view.property("contentX") < before
    qtbot.waitUntil(lambda: not view.property("scrollAnimating"))
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_multiple_cards_keep_slot_positions_and_restore_parameters(
    zio_app, qapp, qtbot, monkeypatch,
):
    window, controller, backend, settings, dock, warnings = zio_app
    tools = [create_tool(backend, f"Royal {index}", command="print('${message:hello}')")
             for index in range(4)]
    qtbot.waitUntil(lambda: controller.toolsModel.count == 4)

    def open_card(tool):
        backend.recentToolDialogRequested.emit(tool.id)
        qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
        qtbot.waitUntil(lambda: settled(visible_cards(qapp)[tool.id]), timeout=7000)
        return visible_cards(qapp)[tool.id]

    first = open_card(tools[0])
    assert first.property("toolController").selectedTool["title"] == "Royal 0"
    assert set(ids(controller.toolsModel)) == {tool.id for tool in tools}
    origin = first.property("launchOrigin")
    assert abs(first.geometry().center().x() - origin.center().x()) <= 2
    assert first.geometry().bottom() < dock.y() - 15
    assert not first.flags() & Qt.WindowType.WindowStaysOnTopHint
    assert first.findChild(QObject, "mechanicalCardMotion").property("accent").name() == "#d9ae48"
    first.setProperty("parameterValues", {"message": "remember me"})
    running = {tools[0].id}
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tid: tid in running)
    stops = []
    monkeypatch.setattr(backend.execution_coordinator, "stop", stops.append)
    backend.append_tool_console(tools[0].id, "background output\n")
    backend.recentToolDialogRequested.emit(tools[1].id)
    qtbot.waitUntil(lambda: len(visible_cards(qapp)) == 2, timeout=7000)
    assert not first.property("outgoing")
    backend.recentToolDialogRequested.emit(tools[2].id)
    backend.recentToolDialogRequested.emit(tools[3].id)
    qtbot.waitUntil(lambda: len(visible_cards(qapp)) == 4, timeout=7000)
    qtbot.waitUntil(lambda: all(settled(card) for card in visible_cards(qapp).values()),
                    timeout=7000)
    positions = []
    for card in visible_cards(qapp).values():
        source = card.property("launchOrigin")
        assert abs(card.geometry().center().x() - source.center().x()) <= 2
        assert card.geometry().bottom() < dock.y() - 15
        assert not card.flags() & Qt.WindowType.WindowStaysOnTopHint
        positions.append(card.x())
    assert len(set(positions)) == 4

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    # Borrowed slots retain their script identity, with an undimmed running indicator.
    controller.refreshTools()
    qtbot.wait(80)
    previews = {item.objectName().removeprefix("zioBorrowedMiniCard_"): item
                for item in visual_items(dock.contentItem())
                if item.objectName().startswith("zioBorrowedMiniCard_")}
    for index, tool in enumerate(tools):
        preview = previews[tool.id]
        assert preview.property("active")
        face = preview.property("item")
        assert face.property("cardTitle") == f"Royal {index}"
        assert face.property("cardIcon") == "terminal"
        assert 0.4 < preview.opacity() < 0.8
    assert all(item.property("text") != "已出列" for item in visual_items(dock.contentItem()))
    indicator = next(item for item in visual_items(dock.contentItem())
                     if item.objectName() == "zioRunningIndicator_" + tools[0].id)
    assert indicator.isVisible() and indicator.opacity() == 1
    assert indicator.property("color").green() > indicator.property("color").red()
    assert dock.grabWindow().save("build/zio-dock-borrowed-previews.png")

    # Clicking the dim slot focuses the existing window and flashes without another sweep.
    preview = previews[tools[0].id]
    point = preview.mapToItem(dock.contentItem(), preview.boundingRect().center()).toPoint()
    QTest.mouseClick(dock, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: first.isActive())
    assert visible_cards(qapp)[tools[0].id] is first
    assert len(visible_cards(qapp)) == 4
    assert first.property("focusScanRunning")
    qtbot.wait(80)
    flash = first.findChild(QObject, "zioCardFocusFlash")
    assert 0 < flash.opacity() <= 0.07
    assert first.findChild(QObject, "mechanicalCardScan").opacity() == 0
    assert first.property("parameterValues")["message"] == "remember me"
    qtbot.waitUntil(lambda: not first.property("focusScanRunning"))
    QMetaObject.invokeMethod(first, "closeCardAnimated")
    qtbot.waitUntil(lambda: tools[0].id not in visible_cards(qapp), timeout=7000)
    assert not stops
    restored = open_card(tools[0])
    assert restored.property("parameterValues").toVariant()["message"] == "remember me"
    assert restored.property("toolController").running
    assert restored.property("toolController").consoleText == "background output\n"
    assert window.property("chromeBackgroundColor").name() == "#191813"
    Path("build").mkdir(exist_ok=True)
    assert dock.grabWindow().save("build/zio-dock.png")
    assert restored.grabWindow().save("build/zio-card.png")
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_hover_click_search_and_deleted_card(zio_app, qapp, qtbot):
    window, controller, backend, _, dock, warnings = zio_app
    for index in range(12):
        create_tool(backend, f"Hover {index}")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 12)
    qtbot.wait(200)

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    hosts = [item for item in visual_items(dock.contentItem())
             if item.objectName().startswith("zioMiniCard_") and item.isVisible()]
    assert len(hosts) >= 2
    target, neighbour = hosts[:2]
    before = neighbour.y()
    point = target.mapToItem(dock.contentItem(), QPointF(36, 70)).toPoint()
    QTest.mouseMove(dock, point)
    qtbot.waitUntil(lambda: target.y() == 0)
    assert neighbour.y() == before
    assert target.width() == 72 and target.height() == 104
    tid = target.objectName().removeprefix("zioMiniCard_")
    QTest.mouseClick(dock, Qt.MouseButton.LeftButton, pos=point)
    qtbot.waitUntil(lambda: tid in visible_cards(qapp), timeout=7000)
    qtbot.waitUntil(lambda: settled(visible_cards(qapp)[tid]), timeout=7000)
    search = window.findChild(QObject, "zioDockSearch")
    search.setProperty("text", "does not match")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 0)
    QMetaObject.invokeMethod(visible_cards(qapp)[tid], "closeCardAnimated")
    qtbot.waitUntil(lambda: not visible_cards(qapp), timeout=7000)
    assert controller.toolsModel.count == 12
    assert controller.openCardCount == 0
    backend.recentToolDialogRequested.emit(tid)
    qtbot.waitUntil(lambda: tid in visible_cards(qapp), timeout=7000)
    backend.registry.delete(tid)
    backend.reloadImportedScripts()
    qtbot.waitUntil(lambda: not visible_cards(qapp), timeout=7000)
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_cancellation_and_theme_switch_during_entry(zio_app, qapp, qtbot):
    window, controller, backend, settings, _, warnings = zio_app
    tool = create_tool(backend, "Cancel")
    qtbot.waitUntil(lambda: controller.toolsModel.count == 1)
    backend.recentToolDialogRequested.emit(tool.id)
    QMetaObject.invokeMethod(window, "closeRecentToolWindows")
    qtbot.wait(250)
    assert not visible_cards(qapp)
    backend.recentToolDialogRequested.emit(tool.id)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    card = visible_cards(qapp)[tool.id]
    assert card.property("entryAnimationRunning")
    settings.saveThemeMode("decade")
    qtbot.waitUntil(lambda: not card.property("entryAnimationRunning"))
    assert not card.property("handoffBlocked")
    settings.saveThemeMode("zio")
    QMetaObject.invokeMethod(card, "closeCardAnimated")
    settings.saveThemeMode("light")
    qtbot.waitUntil(lambda: not visible_cards(qapp), timeout=7000)
    assert controller.openCardCount == 0
    assert not warnings, warnings


@pytest.mark.gui
def test_zio_native_mask_and_theme_swaps(zio_app, qapp, qtbot):
    window, controller, backend, settings, dock, warnings = zio_app
    tools = [create_tool(backend, f"Swap {index}") for index in range(3)]
    qtbot.waitUntil(lambda: controller.toolsModel.count == 3)
    controller.collapse()
    qtbot.waitUntil(lambda: dock.property("revealProgress") == 0)
    button_rect = QRect((dock.width() - 48) // 2, dock.height() - 48, 48, 48)
    assert dock.mask().boundingRect() == button_rect
    assert dock.mask().contains(button_rect.center())
    assert not dock.mask().contains(button_rect.topLeft())
    assert not dock.mask().contains(QPoint(5, 5))
    assert settings.saveThemeMode("decade")
    for tool in tools:
        backend.recentToolDialogRequested.emit(tool.id)
    qtbot.waitUntil(lambda: len(visible_cards(qapp)) == 3, timeout=7000)
    qtbot.waitUntil(lambda: all(not w.property("entryAnimationRunning")
                              for w in visible_cards(qapp).values()), timeout=7000)
    settings.saveThemeMode("zio")
    qtbot.waitUntil(lambda: all(w.geometry().bottom() < controller._panel.y() - 15
                              for w in visible_cards(qapp).values()))
    assert set(visible_cards(qapp)) == {tool.id for tool in tools}
    settings.saveThemeMode("light")
    qtbot.wait(100)
    assert window.findChild(QQuickWindow, "zioDockWindow") is None
    assert all(not card.property("handoffBlocked") for card in visible_cards(qapp).values())
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("theme", ["light", "dark", "decade", "zio"])
def test_unified_click_focus_reuse_and_collapsed_return(zio_app, qapp, qtbot, monkeypatch, theme):
    from poptools.viewmodels.floating_launcher_controller import FloatingLauncherController

    window, controller, backend, settings, _, warnings = zio_app
    settings.saveThemeMode(theme)
    tool = create_tool(backend, "Unified parameterless")
    qtbot.waitUntil(lambda: tool.id in ids(controller.toolsModel))
    panel = controller._panel
    qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
    executions = []
    monkeypatch.setattr(backend, "open_custom_tool_shortcut",
                        lambda tid: pytest.fail("Floating clicks cannot execute shortcuts"))
    monkeypatch.setattr(backend, "run_tool", lambda *args: executions.append(args))
    panel.requestActivate()
    qtbot.waitUntil(panel.isActive)
    monkeypatch.setattr(controller, "_ordinary_window_active", lambda:
                        FloatingLauncherController._ordinary_window_active(controller))
    controller.togglePinned()
    inside = True
    monkeypatch.setattr(controller, "_pointer_inside", lambda: inside)

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    def click_slot(double=False):
        prefix = "zioSlot_" if theme == "zio" else "scriptRow_"
        row = next(item for item in visual_items(panel.contentItem())
                   if item.objectName() == prefix + tool.id)
        point = row.mapToItem(panel.contentItem(), QPointF(row.width() / 2, 22)).toPoint()
        action = QTest.mouseDClick if double else QTest.mouseClick
        action(panel, Qt.MouseButton.LeftButton, pos=point)
        if double:
            QTest.mouseRelease(panel, Qt.MouseButton.LeftButton, pos=point)

    click_slot(double=True)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    card = visible_cards(qapp)[tool.id]
    def flight_above_pack(flying=True):
        if sys.platform != "win32" or theme not in ("decade", "zio"):
            return
        api = ctypes.WinDLL("user32", use_last_error=True)
        api.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        api.GetWindowLongW.restype = wintypes.LONG
        api.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        api.GetWindow.restype = wintypes.HWND
        assert bool(api.GetWindowLongW(int(card.winId()), -20) & 0x8) == flying
        if not flying:
            return
        handle = int(card.winId())
        while handle and handle != int(panel.winId()):
            handle = api.GetWindow(handle, 2)
        assert handle == int(panel.winId())
    flight_above_pack()
    qtbot.waitUntil(lambda: not card.property("entryAnimationRunning"), timeout=7000)
    flight_above_pack(False)
    qtbot.waitUntil(lambda: controller.isCardOpen(tool.id))
    assert controller.expanded
    assert controller.visible and panel.isVisible()
    assert tool.id in ids(controller.toolsModel)
    assert not card.flags() & Qt.WindowStaysOnTopHint
    assert card.transientParent() is None
    assert not executions
    assert len(visible_cards(qapp)) == 1

    # The same retained list entry restores the original minimized card.
    native_id = card.winId()
    card.showMinimized()
    panel.requestActivate()
    qtbot.waitUntil(panel.isActive)
    if not controller.expanded:
        controller.toggleExpanded()
    qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
    click_slot()
    qtbot.waitUntil(lambda: card.isActive() and card.visibility() != QWindow.Minimized)
    assert visible_cards(qapp)[tool.id] is card and card.winId() == native_id
    assert len(visible_cards(qapp)) == 1 and not executions
    assert controller.expanded
    if theme in ("decade", "zio"):
        assert not any(item.property("text") == "已打开"
                       for item in visual_items(panel.contentItem()))
    inside = False
    controller.pointerChanged()
    qtbot.wait(200)
    assert controller.expanded
    # Moving away after automatic card activation is not a window switch.
    # Explicitly activating a different window still dismisses the launcher.
    other_window = QWindow()
    try:
        other_window.show()
        other_window.requestActivate()
        qtbot.waitUntil(other_window.isActive)
        qtbot.waitUntil(lambda: not controller.expanded)
    finally:
        other_window.close()
        other_window.deleteLater()

    # Closing a normal card must not expand or activate the floating entry.
    qtbot.waitUntil(lambda: not card.property("activationAnimationRunning"), timeout=7000)
    QMetaObject.invokeMethod(card, "closeCardAnimated")
    flight_above_pack()
    qtbot.waitUntil(lambda: not visible_cards(qapp), timeout=7000)
    assert not controller.expanded and controller.visible
    assert not controller.isCardOpen(tool.id)
    assert tool.id in ids(controller.toolsModel)
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("theme", ["light", "dark", "decade", "zio"])
def test_repeated_requests_during_return_open_one_replacement(zio_app, qapp, qtbot, theme):
    _, controller, backend, settings, _, warnings = zio_app
    settings.saveThemeMode(theme)
    tool = create_tool(backend, "Queued return")
    qtbot.waitUntil(lambda: tool.id in ids(controller.toolsModel))
    backend.recentToolDialogRequested.emit(tool.id)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    first = visible_cards(qapp)[tool.id]
    qtbot.waitUntil(lambda: settled(first), timeout=7000)
    QMetaObject.invokeMethod(first, "closeCardAnimated")
    backend.recentToolDialogRequested.emit(tool.id)
    backend.recentToolDialogRequested.emit(tool.id)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp)
                    and visible_cards(qapp)[tool.id] is not first, timeout=10000)
    replacement = visible_cards(qapp)[tool.id]
    qtbot.waitUntil(lambda: settled(replacement), timeout=7000)
    assert len(visible_cards(qapp)) == 1
    assert controller.isCardOpen(tool.id)
    assert tool.id in ids(controller.toolsModel)
    assert not controller.returningCardIds
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("theme", ["decade", "zio"])
def test_async_floating_creation_cancels_after_user_switches_focus(
    zio_app, qapp, qtbot, monkeypatch, theme,
):
    window, controller, backend, settings, _, warnings = zio_app
    settings.saveThemeMode(theme)
    tool = create_tool(backend, "Async cancellation")
    qtbot.waitUntil(lambda: tool.id in ids(controller.toolsModel))
    owner = (1, 10)
    monkeypatch.setattr(controller, "_foreground_identity", lambda: owner)
    controller.launchTool(tool.id)
    owner = (2, 20)
    qtbot.waitUntil(lambda: not window.property("pendingToolWindows").toVariant(), timeout=7000)
    assert not visible_cards(qapp)
    assert not controller.isCardOpen(tool.id)
    assert tool.id in ids(controller.toolsModel)
    # The canceled request must not leave a borrowed face or stuck pending ID.
    owner = (1, 10)
    controller.launchTool(tool.id)
    qtbot.waitUntil(lambda: tool.id in visible_cards(qapp), timeout=7000)
    qtbot.waitUntil(lambda: settled(visible_cards(qapp)[tool.id]), timeout=7000)
    assert controller.isCardOpen(tool.id)
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("theme", ["light", "dark", "decade", "zio"])
def test_ctrl_f_searches_main_and_floating_windows(zio_app, qtbot, theme):
    window, controller, backend, settings, _, warnings = zio_app
    settings.saveThemeMode(theme)
    create_tool(backend, "Find this script")
    window.showNormal()
    window.requestActivate()
    qtbot.waitUntil(window.isActive)
    QMetaObject.invokeMethod(window, "openCustomScriptsPage")
    qtbot.waitUntil(lambda: not controller.visible)
    page = window.findChild(QObject, "customScriptsPage")
    search = page.findChild(QObject, "scriptListSearch")
    search.setProperty("text", "Find")
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(search.hasActiveFocus)
    assert search.property("selectedText") == "Find"
    QMetaObject.invokeMethod(window, "openPresetFunctionsPage")
    preset_search = window.findChild(QObject, "presetListSearch")
    QTest.keyClick(window, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(preset_search.hasActiveFocus)
    assert not controller.visible
    window.hide()
    qtbot.waitUntil(lambda: controller.visible)
    panel = controller._panel
    controller.collapse()
    qtbot.waitUntil(lambda: panel.property("revealProgress") == 0)
    panel.requestActivate()
    qtbot.waitUntil(panel.isActive)
    QTest.keyClick(panel, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    name = ("zioDockSearch" if theme == "zio" else
            "floatingTitleSearch" if theme == "decade" else "scriptListSearch")
    floating_search = panel.findChild(QObject, name)
    qtbot.waitUntil(lambda: controller.expanded and floating_search.hasActiveFocus())
    floating_search.setProperty("text", "Find")
    QTest.keyClick(panel, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert floating_search.property("selectedText") == "Find"
    assert not warnings, warnings
