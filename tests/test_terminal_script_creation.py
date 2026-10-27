from __future__ import annotations

import sys

import pytest
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.native_terminal import register_terminal_type
from poptools.paths import package_root


@pytest.mark.gui
def test_terminal_selection_opens_prefilled_script_editor(qapp) -> None:
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
