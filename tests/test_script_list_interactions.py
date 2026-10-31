"""Mouse interactions use temporary scripts and never execute their commands."""

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.paths import package_root
from test_floating_launcher import create_tool, ids
from test_floating_launcher import launcher as launcher
from test_script_list import script_list as script_list
from test_script_list import visible_ids


def row_for(view, tool_id):
    return next(item for item in view.property("contentItem").childItems()
                if item.objectName() == "scriptRow_" + tool_id)


def visual_items(item):
    yield item
    for child in item.childItems():
        yield from visual_items(child)


def row_point(window, view, tool_id, x=18, fraction=0.5):
    row = row_for(view, tool_id)
    return row.mapToItem(window.contentItem(), x, row.height() * fraction).toPoint()


def drag(window, view, source, target, *, after=True):
    start = row_point(window, view, source)
    end = row_point(window, view, target, fraction=0.8 if after else 0.2)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window, start + QPoint(0, 12), delay=20)
    QTest.mouseMove(window, end, delay=20)
    assert view.property("reordering")
    assert window.findChild(QObject, "scriptDropIndicator").isVisible()
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)


@pytest.mark.gui
@pytest.mark.parametrize("after", [False, True])
def test_drag_reorders_persists_and_keeps_selection(script_list, qtbot, after):
    backend, engine, window, view, warnings = script_list
    tools = [create_tool(backend, f"Script {index}", kind="powershell") for index in range(8)]
    backend.setToolSortMode("custom")
    backend.selectTool(tools[2].id)
    qtbot.wait(50)
    selection_changes = []
    backend.selectedToolChanged.connect(lambda: selection_changes.append(True))
    drag(window, view, tools[0].id, tools[4].id, after=after)
    qtbot.wait(50)
    expected = [tool.id for tool in tools[1:]]
    expected.insert(3 + int(after), tools[0].id)
    assert ids(backend.toolsModel) == expected
    assert ConfigStore(backend.config_store.paths).tool_order() == expected
    assert backend.toolsModel.selectedToolId == tools[2].id
    assert not selection_changes  # Keep the current parameter form intact.
    assert not view.property("reordering")
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("filter_kind", ["search", "kind"])
def test_drag_uses_script_ids_with_hidden_rows(script_list, qtbot, filter_kind):
    backend, engine, window, view, warnings = script_list
    tools = [create_tool(backend, f"{index} {'visible' if index % 2 == 0 else 'hidden'}",
                         kind="powershell" if index % 2 == 0 else "python")
             for index in range(8)]
    backend.setToolSortMode("custom")
    if filter_kind == "search":
        backend.setToolSearchQuery("visible")
    else:
        window.findChild(QObject, "scriptListUnderTest").setProperty("kindFilter", "powershell")
    qtbot.wait(50)
    drag(window, view, tools[0].id, tools[4].id)
    qtbot.wait(50)
    expected = [tool.id for tool in tools[1:]]
    expected.insert(4, tools[0].id)
    assert backend.config_store.tool_order() == expected
    backend.setToolSearchQuery("")
    window.findChild(QObject, "scriptListUnderTest").setProperty("kindFilter", "all")
    qtbot.wait(50)
    assert ids(backend.toolsModel) == expected
    assert not warnings, warnings


@pytest.mark.gui
@pytest.mark.parametrize("filtered", [False, True])
def test_drag_auto_scroll_survives_source_delegate_removal(script_list, qtbot, filtered):
    backend, engine, window, view, warnings = script_list
    tools = [create_tool(backend, f"Script {index:02}",
                         kind="python" if filtered and index % 2 else "powershell")
             for index in range(35)]
    backend.setToolSortMode("custom")
    if filtered:
        window.findChild(QObject, "scriptListUnderTest").setProperty("kindFilter", "powershell")
    qtbot.wait(50)
    source = tools[2].id  # Row zero can remain alive as ListView.currentItem.
    start = row_point(window, view, source)
    end = view.mapToItem(window.contentItem(), 18, view.height() - 5).toPoint()
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window, end, delay=30)
    qtbot.waitUntil(lambda: view.property("contentY") > 400, timeout=3000)
    qtbot.waitUntil(lambda: all(item.objectName() != "scriptRow_" + source
                               for item in view.property("contentItem").childItems()))
    assert source not in visible_ids(view)
    assert view.property("reordering")
    anchor = view.property("dropTargetId")
    after = view.property("dropAfter")
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
    qtbot.wait(50)
    expected = [tool.id for tool in tools if tool.id != source]
    expected.insert(expected.index(anchor) + int(after), source)
    assert ids(backend.toolsModel) == expected
    assert not warnings, warnings


@pytest.mark.gui
def test_drag_cancel_and_sort_mode_visibility(script_list, qtbot):
    backend, engine, window, view, warnings = script_list
    tools = [create_tool(backend, f"Script {index}", kind="powershell") for index in range(8)]
    grip = window.findChild(QObject, "scriptReorderGrip")
    assert not grip.isVisible()
    backend.setToolSortMode("custom")
    qtbot.wait(50)
    assert grip.isVisible()
    start = row_point(window, view, tools[0].id)
    end = row_point(window, view, tools[3].id)
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(window, end, delay=20)
    assert view.property("reordering")
    QTest.keyClick(window, Qt.Key.Key_Escape)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=end)
    assert ids(backend.toolsModel) == [tool.id for tool in tools]
    assert not view.property("reordering")
    backend.setToolSortMode("name")
    qtbot.wait(30)
    assert not grip.isVisible()
    assert not warnings, warnings


@pytest.mark.gui
def test_failed_drag_save_keeps_previous_order(script_list, qtbot, monkeypatch):
    backend, engine, window, view, warnings = script_list
    tools = [create_tool(backend, f"Script {index}", kind="powershell") for index in range(8)]
    backend.setToolSortMode("custom")
    qtbot.wait(50)
    failures = []
    view.reorderFailed.connect(lambda: failures.append(True))

    def fail_save(order):
        raise OSError("read-only settings")

    monkeypatch.setattr(backend.config_store, "set_tool_order", fail_save)
    drag(window, view, tools[0].id, tools[3].id)
    assert failures == [True]
    assert ids(backend.toolsModel) == [tool.id for tool in tools]
    assert not view.property("reordering")
    assert not warnings, warnings


@pytest.fixture
def custom_page(launcher, qtbot, monkeypatch):
    _, backend, _, _ = launcher
    runs, stops = [], []
    monkeypatch.setattr(backend, "runSelected", lambda values: runs.append(
        (backend.selectedTool["id"], dict(values))) or True)
    monkeypatch.setattr(backend, "stopExecution", lambda: stops.append(True))
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    required property var backend
    required property var android
    width: 1000; height: 700; visible: true
    property var values: ({})
    property var confirmations: []
    function resetParameters() {
        const values = {};
        for (const parameter of (backend.selectedTool.parameters || []))
            values[parameter.id] = parameter.default;
        host.values = values;
    }
    Connections {
        target: host.backend
        function onSelectedToolChanged() { host.resetParameters(); }
    }
    CustomScriptsPage {
        id: page
        anchors.fill: parent
        controller: host.backend
        androidBackend: host.android
        parentWindow: host
        parameterValues: host.values
        onConfirmRunRequested: function(values) {
            host.confirmations = host.confirmations.concat([JSON.parse(JSON.stringify(values))]);
        }
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/QuickRunHarness.qml")))
    window = component.createWithInitialProperties({
        "backend": backend, "android": backend.android_controller,
    })
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    assert QTest.qWaitForWindowExposed(window)
    view = window.findChild(QObject, "sharedScriptList")
    try:
        yield backend, engine, window, view, warnings, runs, stops
    finally:
        window.close()
        window.deleteLater()
        qtbot.wait(20)
        engine.deleteLater()


@pytest.mark.gui
def test_double_click_runs_clicked_script_once_with_its_defaults(custom_page, qtbot):
    backend, engine, window, view, warnings, runs, stops = custom_page
    a = create_tool(backend, "A", kind="powershell", command="echo ${message:alpha}")
    b = create_tool(backend, "B", kind="powershell", command="echo ${message:beta}")
    backend.setToolSortMode("name")
    backend.selectTool(a.id)
    qtbot.wait(50)
    point = row_point(window, view, b.id, x=100)
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(50)
    assert runs == [(b.id, {"message": "beta"})]
    assert not stops
    assert not warnings, warnings


@pytest.mark.gui
def test_double_click_preserves_edited_parameters(custom_page, qtbot):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tool = create_tool(backend, "A", kind="powershell", command="echo ${message:default}")
    backend.selectTool(tool.id)
    qtbot.wait(50)
    field = next(item for item in visual_items(window.contentItem())
                 if item.objectName() == "customParameterInput_message").property("item")
    field.setProperty("text", "edited value")
    point = row_point(window, view, tool.id, x=100)
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(50)
    assert runs == [(tool.id, {"message": "edited value"})]
    assert not stops
    assert not warnings, warnings


@pytest.mark.gui
def test_sort_and_drag_preserve_the_parameter_form(custom_page, qtbot):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tools = [create_tool(backend, f"Script {index}", kind="powershell",
                         command="echo ${message:default}") for index in range(8)]
    backend.selectTool(tools[2].id)
    qtbot.wait(50)
    field = next(item for item in visual_items(window.contentItem())
                 if item.objectName() == "customParameterInput_message").property("item")
    field.setProperty("text", "keep this edit")
    backend.setToolSortMode("custom")
    qtbot.wait(50)
    drag(window, view, tools[0].id, tools[4].id)
    qtbot.wait(50)
    assert backend.toolsModel.selectedToolId == tools[2].id
    assert window.property("values").toVariant() == {"message": "keep this edit"}
    assert field.property("text") == "keep this edit"
    assert not runs and not stops
    assert not warnings, warnings


@pytest.mark.gui
def test_double_click_respects_confirmation_and_never_stops_running_script(
    custom_page, qtbot, monkeypatch,
):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tool = create_tool(backend, "A", kind="powershell", command="echo ${message:default}")
    tool.presentation.confirm_before_run = True
    backend.registry.repository.save_tool(tool)
    backend.reloadImportedScripts()
    backend.selectTool(tool.id)
    qtbot.wait(50)
    point = row_point(window, view, tool.id, x=100)
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(50)
    assert window.property("confirmations").toVariant() == [{"message": "default"}]
    assert not runs
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tid: tid == tool.id)
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(50)
    assert not runs and not stops
    assert len(window.property("confirmations").toVariant()) == 1
    assert not warnings, warnings
