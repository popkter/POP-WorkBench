import json

import pytest
from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlProperty
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.paths import AppPaths, package_root
from poptools.viewmodels.settings_controller import SettingsController
from poptools.viewmodels.update_controller import UpdateController


@pytest.mark.parametrize("panel_width", [410, 520, 800])
def test_custom_parameters_share_a_frame_and_elide_long_labels(qapp, qtbot, panel_width):
    kinds = ["text", "file", "directory", "secret", "integer", "number",
             "choice", "boolean", "multiline"]
    parameters = [{
        "id": kind, "label": "Long parameter description " * 8,
        "kind": kind, "required": index % 2 == 0,
        "default": False if kind == "boolean" else "value",
        "options": ["value", "other"],
    } for index, kind in enumerate(kinds)]
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(('''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 800; height: 900; visible: true
    property var parameters: PARAMETERS
    CustomToolDetailPanel {
        objectName: "panel"
        anchors.fill: parent
        parentWindow: host
        androidBackend: null
        parameterValues: ({})
        actionsInTitleBar: true
        displayedTool: ({id: "test", title: "Test script", parameters: host.parameters,
                         executor: {kind: "powershell"}})
        controller: ({running: false, consoleText: "", statusText: ""})
    }
}
'''.replace("PARAMETERS", json.dumps(parameters))).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/InlineParametersHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        window.setWidth(panel_width)
        with qtbot.waitSignal(window.frameSwapped):
            window.update()

        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        items = {item.objectName(): item for item in visual_items(window.contentItem())}
        input_positions = []
        for kind in kinds:
            row = items["customParameterRow_" + kind]
            label_cell = items["customParameterLabelCell_" + kind]
            label = items["customParameterLabel_" + kind]
            field = items["customParameterInput_" + kind]
            assert field.width() == pytest.approx(3 * label_cell.width())
            assert field.x() >= label_cell.x() + label_cell.width()
            assert field.x() + field.width() == pytest.approx(row.width() - 1)
            assert label_cell.x() > 0 and field.y() > 0
            assert label.property("truncated")
            assert label.width() <= label_cell.width()
            assert label.y() + label.height() / 2 == pytest.approx(field.height() / 2)
            assert row.height() == (88 if kind == "multiline" else 42)
            assert field.height() == row.height() - 2
            control = field.property("item")
            if kind != "boolean":
                assert control.property("background") is None
            if kind == "text":
                label_rect = label_cell.mapRectToItem(window.contentItem(),
                                                     label_cell.boundingRect())
                QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                                 pos=label_rect.center().toPoint())
                qtbot.waitUntil(lambda current=row: current.property("inputFocused"))
                assert QQmlProperty.read(row, "border.width") == 2
            input_positions.append(field.x())
        assert max(input_positions) == pytest.approx(min(input_positions))
        checkbox = items["customParameterInput_boolean"].property("item")
        assert checkbox.property("text") == ""  # Its label appears once, in the left column.
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("panel_width", [410, 520, 800])
def test_detail_actions_and_console_fit_after_resize(qapp, qtbot, panel_width):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 800; height: 568; visible: true
    property string executionStatus: "Ready"
    CustomToolDetailPanel {
        objectName: "panel"
        anchors.fill: parent
        parentWindow: host
        androidBackend: null
        parameterValues: ({})
        displayedTool: ({id: "test", title: "Test script", editable: true,
                         parameters: [], executor: {kind: "powershell"}})
        controller: ({running: false, consoleText: "Output", statusText: host.executionStatus})
    }
}
''',
        QUrl.fromLocalFile(str(package_root() / "ui/qml/DesignHarness.qml")),
    )
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        panel = window.findChild(QObject, "panel")
        console = window.findChild(QObject, "customConsolePanel")
        actions = window.findChild(QObject, "customActionArea")
        buttons = [window.findChild(QObject, name) for name in (
            "customEditButton", "customDeleteButton", "customRunButton",
        )]
        window.setWidth(panel_width)

        def actions_fit():
            rectangles = [button.mapRectToItem(panel, button.boundingRect()) for button in buttons]
            return all(rect.left() >= 0 and rect.right() <= panel.width() + 0.5
                       and rect.bottom() <= console.y() for rect in rectangles) and not any(
                left.intersects(right)
                for index, left in enumerate(rectangles) for right in rectangles[index + 1:]
            )

        qtbot.waitUntil(actions_fit)
        assert panel.property("consoleExpanded") is True
        expanded_height = console.height()
        assert expanded_height > 100
        toggle = window.findChild(QObject, "customConsoleToggle")
        assert QMetaObject.invokeMethod(toggle, "clicked")
        qtbot.waitUntil(lambda: console.height() < expanded_height / 2)
        assert actions.y() > 0
        assert QMetaObject.invokeMethod(toggle, "clicked")
        qtbot.waitUntil(lambda: abs(console.height() - expanded_height) < 0.5)
        qtbot.waitUntil(actions_fit)

        def texts(item):
            yield item.property("text")
            for child in item.childItems():
                yield from texts(child)

        window.setProperty("executionStatus", "Failed (7)")
        qtbot.waitUntil(lambda: "Failed (7)" in list(texts(window.contentItem())))
        assert "\u2713 \u9000\u51fa\u7801 0" not in list(texts(window.contentItem()))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("page_width", [1290, 888, 644])
def test_settings_frequency_segments_fit_and_save(qapp, qtbot, tmp_path, page_width):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    settings = SettingsController(store, PythonEnvironment(paths, store))
    updates = UpdateController(store, auto_check_enabled=False)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("settingsBackend", settings)
    engine.rootContext().setContextProperty("updatesBackend", updates)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 1290; height: 800; visible: true
    SettingsPage {
        anchors.fill: parent; controller: settingsBackend; updateBackend: updatesBackend
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/SettingsHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        window.setWidth(page_width)
        segment = window.findChild(QObject, "updateFrequencyChoice")
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        items = {item.objectName(): item for item in visual_items(window.contentItem())}
        buttons = [items["updateFrequency_" + mode]
                   for mode in ("never", "daily", "weekly", "startup")]

        def segments_fit():
            rectangles = [button.mapRectToItem(segment, button.boundingRect())
                          for button in buttons]
            return all(rect.width() >= 60 and rect.left() >= 0
                       and rect.right() <= segment.width() for rect in rectangles) and all(
                left.right() <= right.left() + 0.5
                for left, right in zip(rectangles, rectangles[1:], strict=False))

        qtbot.waitUntil(segments_fit)
        assert QMetaObject.invokeMethod(buttons[-1], "clicked")
        assert store.update_check_frequency() == "startup"
        assert window.findChild(QObject, "runtimePluginsCard") is not None
        expected = (["Python", "Android 工具（ADB + scrcpy）", "PowerShell"]
                    if settings.pluginManager is not None
                    else ["Python", "adb-platform-tools", "scrcpy"])
        assert [item["name"] for item in settings.runtimePlugins] == expected
    finally:
        updates.shutdown()
        window.close()
        window.deleteLater()
        engine.deleteLater()
