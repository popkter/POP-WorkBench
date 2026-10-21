"""Check the script form and resizable output remain separate during execution."""

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPoint, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.mark.parametrize("panel_width", [410, 520, 800])
def test_console_expands_resizes_and_restores_without_covering_form(qapp, qtbot, panel_width):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 800; height: 640; visible: true
    QtObject {
        id: backend
        objectName: "backend"
        property bool running: false
        property string consoleText: "Output"
        property string statusText: running ? "Running" : "Ready"
        function runSelected(values) { running = true }
        function stopExecution() { running = false }
        function clearConsole() { consoleText = "" }
    }
    CustomToolDetailPanel {
        objectName: "panel"
        anchors.fill: parent
        controller: backend
        parentWindow: host
        androidBackend: null
        parameterValues: ({})
        splitConsole: true
        actionsInTitleBar: true
        displayedTool: ({id: "test", title: "Script", executor: {kind: "powershell"},
            parameters: [{id: "message", label: "Message", kind: "multiline"}]})
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ConsoleSplitHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        window.setWidth(panel_width)
        panel = window.findChild(QObject, "panel")
        form = window.findChild(QObject, "customParameterPanel")
        area = window.findChild(QObject, "customParameterArea")
        console = window.findChild(QObject, "customConsolePanel")
        separator = window.findChild(QObject, "customConsoleResizeHandle")
        toggle = window.findChild(QObject, "customConsoleToggle")
        backend = window.findChild(QObject, "backend")

        def separate():
            return (form.y() == 0 and form.height() > 0 and area.height() >= 0
                    and form.y() + form.height() < console.y()
                    and console.y() + console.height() == pytest.approx(panel.height()))

        qtbot.waitUntil(separate)
        assert not panel.property("consoleExpanded")
        assert console.height() == 42
        collapsed_form_height = form.height()
        assert QMetaObject.invokeMethod(panel, "runSelectedTool")
        qtbot.waitUntil(lambda: panel.property("consoleExpanded") and console.height() > 140)
        assert backend.property("running")
        assert form.height() < collapsed_form_height
        assert separate()
        expanded_height = console.height()

        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        rect = separator.mapRectToItem(window.contentItem(), separator.boundingRect())
        start = rect.center().toPoint()
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(window, start - QPoint(0, 60), delay=30)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=start - QPoint(0, 60))
        qtbot.waitUntil(lambda: console.height() > expanded_height + 30)
        assert separate()
        resized_height = console.height()
        backend.setProperty("running", False)
        assert panel.property("consoleExpanded")

        assert QMetaObject.invokeMethod(toggle, "clicked")
        qtbot.waitUntil(lambda: console.height() == 42)
        assert form.height() == collapsed_form_height
        assert QMetaObject.invokeMethod(toggle, "clicked")
        qtbot.waitUntil(lambda: abs(console.height() - resized_height) < 0.5)

        window.setHeight(360)
        qtbot.waitUntil(separate)
        assert QMetaObject.invokeMethod(toggle, "clicked")
        assert not panel.property("consoleExpanded")
        backend.setProperty("running", True)
        qtbot.waitUntil(lambda: panel.property("consoleExpanded"))
        assert separate()
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
