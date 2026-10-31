"""Exercise the real virtualized script list with isolated script data."""

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QWheelEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlExpression
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.paths import package_root
from test_floating_launcher import create_tool, ids
from test_floating_launcher import launcher as launcher


def evaluate(engine, target, expression):
    script = QQmlExpression(QQmlEngine.contextForObject(target), target, expression)
    result = script.evaluate()
    assert not script.hasError(), script.error().toString()
    return result


@pytest.fixture
def script_list(launcher, qtbot):
    _, backend, _, _ = launcher
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    required property var backend
    width: 360; height: 420; visible: true
    CustomScriptList {
        objectName: "scriptListUnderTest"
        anchors.fill: parent
        controller: backend
        listModel: backend.toolsModel
        onToolActivated: function(id) { backend.selectTool(id) }
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ScriptListHarness.qml")))
    window = component.createWithInitialProperties({"backend": backend})
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    view = window.findChild(QObject, "sharedScriptList")
    qtbot.waitUntil(lambda: view.height() > 0)
    assert QTest.qWaitForWindowExposed(window)
    try:
        yield backend, engine, window, view, warnings
    finally:
        window.close()
        window.deleteLater()
        qtbot.wait(20)
        engine.deleteLater()


def visible_ids(view):
    return [item.property("toolId") for item in view.property("contentItem").childItems()
            if item.objectName().startswith("scriptRow_") and item.isVisible()
            and item.mapToItem(view, 0, 0).y() < view.height()
            and item.mapToItem(view, 0, item.height()).y() > 0]


@pytest.mark.gui
@pytest.mark.parametrize("mode", ["name", "usage", "custom"])
def test_create_sort_and_scroll_keeps_all_rows(script_list, qtbot, mode):
    backend, engine, window, view, warnings = script_list
    for index in range(40):
        create_tool(backend, f"Script {index:02}", kind="powershell")
    assert backend.createCommand("Script 99 new", "", "powershell", "Write-Output hello")
    qtbot.wait(80)
    assert backend.setToolSortMode(mode)
    qtbot.wait(80)
    expected = ids(backend.toolsModel)
    assert len(expected) == 41
    seen = set()
    for index in range(0, len(expected), 3):
        evaluate(engine, view, f"positionViewAtIndex({index}, ListView.Beginning)")
        qtbot.wait(30)
        actual = visible_ids(view)
        assert expected[index] in actual
        seen.update(actual)
    assert seen == set(expected)
    assert ids(backend.toolsModel) == expected
    assert not warnings, warnings


@pytest.mark.gui
def test_enter_activates_mouse_selection_after_keyboard_navigation(script_list, qtbot):
    backend, engine, window, view, warnings = script_list
    a = create_tool(backend, "A", kind="powershell")
    b = create_tool(backend, "B", kind="powershell")
    backend.setToolSortMode("name")
    backend.selectTool(a.id)
    qtbot.wait(30)
    evaluate(engine, view, "selectAdjacent(1)")
    assert backend.selectedTool["id"] == b.id
    qtbot.wait(30)
    row = next(item for item in view.property("contentItem").childItems()
               if item.objectName() == "scriptRow_" + a.id)
    point = row.mapToItem(window.contentItem(), row.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
    assert backend.selectedTool["id"] == a.id
    activated = []
    view.toolActivated.connect(activated.append)
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert activated == [a.id]
    assert not warnings, warnings


def test_launcher_refresh_preserves_keyboard_selection(launcher):
    controller, backend, _, _ = launcher
    a = create_tool(backend, "A", kind="powershell")
    b = create_tool(backend, "B", kind="powershell")
    controller.refreshTools()
    controller.toolsModel.select(a.id)
    controller.refreshTools()
    assert controller.toolsModel.selectedToolId == a.id
    assert backend.registry.delete(a.id)
    backend.reloadImportedScripts()
    controller.refreshTools()
    assert controller.toolsModel.selectedToolId == ""
    assert controller.toolsModel.adjacentToolId(1, "all") == b.id


@pytest.mark.gui
@pytest.mark.parametrize("mode", ["added_time", "name", "usage", "custom"])
def test_wheel_reaches_every_script_in_both_directions(script_list, qapp, qtbot, mode):
    backend, engine, window, view, warnings = script_list
    for index in range(35):
        create_tool(backend, f"Script {index:02}", kind="powershell")
    assert backend.createCommand("Script 99 new", "", "powershell", "Write-Output hello")
    backend.setToolSortMode(mode)
    qtbot.wait(50)
    expected = set(ids(backend.toolsModel))
    evaluate(engine, view, "positionViewAtBeginning()")
    qtbot.wait(30)
    point = view.mapToItem(window.contentItem(), view.boundingRect().center())
    for direction in (-1, 1):
        seen = set(visible_ids(view))
        for step in range(20):
            event = QWheelEvent(point, window.mapToGlobal(point), QPoint(),
                                QPoint(0, direction * 120), Qt.MouseButton.NoButton,
                                Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            # Flickable uses event time to distinguish successive wheel ticks.
            event.setTimestamp(1000 + (step + (20 if direction > 0 else 0)) * 200)
            qapp.sendEvent(window, event)
            qtbot.wait(80)
            seen.update(visible_ids(view))
        assert seen == expected
    assert ids(backend.toolsModel) and backend.toolsModel.count == len(expected)
    assert not warnings, warnings


@pytest.mark.gui
def test_refresh_search_edit_delete_and_reorder_keep_visible_data_consistent(
    script_list, qtbot, monkeypatch,
):
    backend, engine, _, view, warnings = script_list
    for index in range(25):
        create_tool(backend, f"Script {index:02}", kind="powershell")
    backend.setToolSortMode("usage")
    qtbot.wait(30)
    expected = ids(backend.toolsModel)
    selected = expected[-1]
    backend.selectTool(selected)
    backend._record_tool_usage(backend.registry.get(selected))
    qtbot.wait(30)
    assert ids(backend.toolsModel)[0] == selected
    assert selected in visible_ids(view)

    # A different running script is pinned without changing the selection.
    running = expected[-2]
    active = {running}
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tid: tid in active)
    backend.execution_coordinator.runningChanged.emit(running, True)
    qtbot.wait(30)
    assert ids(backend.toolsModel)[0] == running
    assert backend.toolsModel.selectedToolId == selected
    assert set(ids(backend.toolsModel)) == set(expected)
    active.clear()
    backend.execution_coordinator.runningChanged.emit(running, False)

    assert backend.saveSelected("Renamed", "", "powershell", "Write-Output hello")
    backend.setToolSortMode("name")
    backend.setToolSearchQuery("no match")
    qtbot.wait(30)
    assert backend.toolsModel.count == 0
    assert backend.toolsModel.totalCount == len(expected)
    backend.setToolSearchQuery("Renamed")
    qtbot.wait(30)
    assert visible_ids(view) == [selected]
    backend.setToolSearchQuery("")
    backend.setToolSortMode("custom")
    assert backend.moveTool(selected, 0)
    qtbot.wait(30)
    assert ids(backend.toolsModel)[0] == selected
    assert selected in visible_ids(view)
    assert backend.deleteSelected()
    qtbot.wait(30)
    assert set(ids(backend.toolsModel)) == set(expected) - {selected}
    assert selected not in visible_ids(view)
    assert backend.toolsModel.selectedToolId == ""
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("hidden_by", ["search", "kind"])
def test_enter_does_not_activate_a_filtered_out_selection(script_list, qtbot, hidden_by):
    backend, engine, window, view, warnings = script_list
    tool = create_tool(backend, "Selected", kind="powershell")
    backend.selectTool(tool.id)
    qtbot.wait(30)
    if hidden_by == "search":
        backend.setToolSearchQuery("no match")
    else:
        window.findChild(QObject, "scriptListUnderTest").setProperty("kindFilter", "python")
    qtbot.wait(30)
    activated = []
    view.toolActivated.connect(activated.append)
    evaluate(engine, view, "forceActiveFocus()")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert not activated
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("matches", [1, 20])
def test_kind_filter_after_scrolling_still_shows_matching_rows(script_list, qtbot, matches):
    backend, engine, window, view, warnings = script_list
    tools = [create_tool(backend, f"Script {index:02}",
                         kind="python" if index < matches else "powershell")
             for index in range(40)]
    backend.setToolSortMode("name")
    qtbot.wait(50)
    evaluate(engine, view, "positionViewAtEnd()")
    qtbot.wait(50)
    scripts = window.findChild(QObject, "scriptListUnderTest")
    scripts.setProperty("kindFilter", "python")
    qtbot.wait(80)
    assert scripts.property("visibleCount") == matches
    actual = visible_ids(view)
    assert actual
    assert set(actual) <= {tool.id for tool in tools[:matches]}
    assert view.property("contentY") <= view.property("originY") + view.property("contentHeight")
    assert not warnings, warnings


@pytest.mark.gui
def test_select_offscreen_script_reveals_it(script_list, qtbot):
    backend, engine, _, view, warnings = script_list
    for index in range(30):
        create_tool(backend, f"Script {index:02}", kind="powershell")
    backend.setToolSortMode("name")
    qtbot.wait(50)
    expected = ids(backend.toolsModel)
    evaluate(engine, view, "positionViewAtBeginning()")
    qtbot.wait(30)
    backend.selectTool(expected[-1])
    qtbot.wait(50)
    assert expected[-1] in visible_ids(view)
    assert not warnings, warnings


@pytest.mark.gui
def test_keyboard_navigation_reveals_offscreen_selection(script_list, qtbot):
    backend, engine, _, view, warnings = script_list
    for index in range(25):
        create_tool(backend, f"Script {index:02}", kind="powershell")
    backend.setToolSortMode("name")
    qtbot.wait(50)
    expected = ids(backend.toolsModel)
    backend.selectTool(expected[0])
    qtbot.wait(30)
    for tool_id in expected[1:]:
        evaluate(engine, view, "selectAdjacent(1)")
        qtbot.wait(20)
        assert backend.selectedTool["id"] == tool_id
        assert tool_id in visible_ids(view)
    assert not warnings, warnings
