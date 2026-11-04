from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.native_terminal import register_terminal_type
from poptools.paths import package_root


@pytest.mark.gui
def test_terminal_selection_opens_prefilled_script_editor(qapp, qtbot) -> None:
    register_terminal_type()
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"

ApplicationWindow {
    id: window
    width: 1000
    height: 800
    visible: true
    property string savedCommand: ""
    property string savedKind: ""
    property var terminalController: ({
        activeTerminalTabId: "test", terminalTabs: [], canCreateTerminalTab: true,
        running: false, terminalName: "PowerShell", powerShellHistoryListViewEnabled: false,
        configureTerminalSyntaxColors: function(colors) {}, terminalReady: function() {},
        terminalDetached: function() {}, ensureStarted: function() {},
        resizeTerminal: function(columns, rows) {}
    })
    TerminalPage {
        anchors.fill: parent
        parentWindow: window
        controller: window.terminalController
        onCreateScriptRequested: function(command, kind) { editor.openForCreate(command, kind) }
    }
    CommandEditorDialog {
        id: editor
        objectName: "editor"
        controller: ({createCommand: function(title, description, kind, command, icon) {
            window.savedCommand = command
            window.savedKind = kind
            return true
        }})
    }
    function submitEditor() { editor.submit() }
    function openBlankEditor() { editor.openForCreate() }
}
""",
        QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "TerminalScriptHarness.qml")),
    )
    window = component.create()
    assert window is not None, [error.toString() for error in component.errors()]
    try:
        QTest.qWait(50)
        terminal = next(
            child for child in window.findChildren(QObject)
            if child.metaObject().indexOfMethod("selectionText()") >= 0
        )
        # Native geometry is debounced; feeding before the first resize would
        # put the command through the initial one-column terminal buffer.
        qtbot.waitUntil(lambda: terminal.property("columns") > 40
                        and terminal.property("rows") > 10)
        action = window.findChild(QObject, "addSelectionToCustomScript")
        editor = window.findChild(QObject, "editor")
        assert action is not None and editor is not None
        assert not action.property("enabled")
        clipboard = QGuiApplication.clipboard()
        previous_clipboard = clipboard.text()
        clipboard.setText("keep clipboard")
        try:
            command = 'adb devices\nWrite-Output "hello 世界"'
            assert QMetaObject.invokeMethod(
                terminal, "feed", Qt.ConnectionType.DirectConnection,
                Q_ARG(str, "test"), Q_ARG(str, command.replace("\n", "\r\n")),
            )
            assert QMetaObject.invokeMethod(terminal, "selectAll")
            assert action.property("enabled")
            assert QMetaObject.invokeMethod(action, "triggered")
            assert editor.property("visible")
            assert not editor.property("editMode")
            assert QMetaObject.invokeMethod(window, "submitEditor")
            assert window.property("savedCommand").rstrip("\n") == command
            assert window.property("savedKind") == (
                "powershell" if sys.platform == "win32" else "bash"
            )
            assert clipboard.text() == "keep clipboard"
            assert QMetaObject.invokeMethod(window, "openBlankEditor")
            assert QMetaObject.invokeMethod(window, "submitEditor")
            assert window.property("savedCommand") == ""
            assert window.property("savedKind") == "powershell"
            assert QMetaObject.invokeMethod(terminal, "clearSelection")
            assert not action.property("enabled")
        finally:
            clipboard.setText(previous_clipboard)
    finally:
        window.deleteLater()
        QGuiApplication.processEvents()


@pytest.mark.gui
@pytest.mark.parametrize("surface_color", ["#263348", "#b2c4df"])
def test_terminal_transparent_viewport_preserves_shared_material(qapp, qtbot, surface_color):
    """Default terminal cells reveal the same surface as the surrounding padding."""
    register_terminal_type()
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import PopTools.Terminal 1.0
Window {
    width: 360; height: 240; visible: true
    Rectangle {
        id: material; objectName: "material"; anchors.fill: parent; color: "#263348"
        TerminalView {
            id: terminal; objectName: "terminal"
            anchors.fill: parent; anchors.margins: 12
            sessionId: "test"; fillColor: Qt.rgba(0.17, 0.19, 0.24, 0)
        }
    }
}
''', QUrl.fromLocalFile(
        str(package_root() / "ui/qml/TransparentTerminalHarness.qml")))
    window = component.create()
    assert window is not None, [error.toString() for error in component.errors()]
    try:
        material = window.findChild(QObject, "material")
        material.setProperty("color", QColor(surface_color))
        assert QTest.qWaitForWindowExposed(window)
        terminal = window.findChild(QObject, "terminal")
        qtbot.waitUntil(lambda: terminal.property("columns") > 20
                        and terminal.property("rows") > 5)
        assert QMetaObject.invokeMethod(
            terminal, "feed", Qt.ConnectionType.DirectConnection,
            Q_ARG(str, "test"), Q_ARG(str, "\x1b[41m \x1b[0m plain text"),
        )
        first = window.grabWindow()
        dpr = first.devicePixelRatio()
        def pixel(image, x, y):
            return image.pixelColor(round(x * dpr), round(y * dpr))
        assert pixel(first, 8, 100) == pixel(first, 50, 100) == QColor(surface_color)
        # Explicit ANSI background colors still cover the glass.
        ansi_background = pixel(first, 14, 14)
        assert ansi_background != QColor(surface_color)
        material.setProperty("color", QColor("#3f7560"))
        QTest.qWait(60)
        second = window.grabWindow()
        assert pixel(second, 50, 100) == QColor("#3f7560")
        assert pixel(second, 14, 14) == ansi_background
        # Switching back to an opaque normal terminal restores its own fill.
        terminal = window.findChild(QObject, "terminal")
        terminal.setProperty("fillColor", QColor("#2b313d"))
        QTest.qWait(60)
        assert pixel(window.grabWindow(), 50, 100) == QColor("#2b313d")
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()
