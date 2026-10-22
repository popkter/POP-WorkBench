import pytest
from PySide6.QtCore import QCoreApplication, QEvent, Qt, QUrl
from PySide6.QtGui import QInputMethodEvent, QKeyEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.fixture
def form(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 700; height: 800; visible: true
    property int executions: 0
    property int stops: 0
    property int confirmations: 0
    property var submitted: ({})
    property var values: ({})
    property alias running: backend.running
    property alias confirm: backend.confirm
    property alias enterEnabled: panel.submitParametersOnEnter
    QtObject {
        id: backend
        property bool running: false
        property bool confirm: false
        property string consoleText: ""
        property string statusText: ""
        function runSelected(values) {
            host.executions++
            host.submitted = JSON.parse(JSON.stringify(values))
        }
        function stopExecution() { host.stops++ }
    }
    CustomToolDetailPanel {
        id: panel
        anchors.fill: parent
        parentWindow: host
        androidBackend: null
        controller: backend
        parameterValues: host.values
        submitParametersOnEnter: true
        displayedTool: ({id: "custom.test", parameters: [
            {id: "input", label: "Input", kind: "text", default: ""}
        ], presentation: {confirm_before_run: backend.confirm}})
        onConfirmRunRequested: values => host.confirmations++
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/SubmitHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    assert QTest.qWaitForWindowExposed(window)

    def descendants(item):
        yield item
        for child in item.childItems():
            yield from descendants(child)

    field = next(item for item in descendants(window.contentItem())
                 if item.objectName() == "customParameterInput_input")
    yield window, field
    window.close()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def editor_for(field, kind):
    field.setProperty("parameter", {"id": "input", "label": "Input", "kind": kind})
    editor = field.property("item")
    editor.forceActiveFocus()
    return editor


@pytest.mark.parametrize("kind", ["text", "secret", "integer", "number", "file",
                                  "directory", "multiline"])
@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Enter])
def test_enter_submits_latest_parameter(form, kind, key):
    window, field = form
    editor = editor_for(field, kind)
    value = "12" if kind in ("integer", "number") else "latest value"
    editor.setProperty("text", value)
    modifiers = (Qt.KeyboardModifier.KeypadModifier if key == Qt.Key.Key_Enter
                 else Qt.KeyboardModifier.NoModifier)
    QTest.keyClick(window, key, modifiers)
    assert window.property("executions") == 1
    assert window.property("submitted").toVariant() == {"input": value}
    assert editor.property("text") == value


def test_multiline_shift_enter_and_disabled_submission(form):
    window, field = form
    editor = editor_for(field, "multiline")
    QTest.keyClick(window, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert editor.property("text") == "\n"
    assert window.property("executions") == 0
    window.setProperty("enterEnabled", False)
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert editor.property("text") == "\n\n"
    assert window.property("executions") == 0


def test_running_repeat_and_ime_do_not_submit(form):
    window, field = form
    editor = editor_for(field, "text")
    window.setProperty("running", True)
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert window.property("stops") == 0
    window.setProperty("running", False)
    repeat = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return,
                       Qt.KeyboardModifier.NoModifier, "\r", True)
    QCoreApplication.sendEvent(window, repeat)
    preedit = QInputMethodEvent("pin", [])
    QCoreApplication.sendEvent(editor, preedit)
    assert editor.property("inputMethodComposing")
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert window.property("executions") == 0


@pytest.mark.parametrize("kind", ["choice", "radio", "boolean"])
def test_non_text_controls_do_not_submit(form, kind):
    window, field = form
    editor_for(field, kind)
    QTest.keyClick(window, Qt.Key.Key_Return)
    QTest.keyClick(window, Qt.Key.Key_Enter)
    assert window.property("executions") == 0


def test_enter_uses_existing_confirmation_and_mouse_action(form):
    window, field = form
    editor_for(field, "text")
    window.setProperty("confirm", True)
    QTest.keyClick(window, Qt.Key.Key_Return)
    assert window.property("confirmations") == 1
    assert window.property("executions") == 0
    window.setProperty("confirm", False)
    button = window.findChild(type(field), "customRunButton")
    assert button is not None
    point = button.mapToScene(button.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
    assert window.property("executions") == 1
