import pytest
from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("dialog_type,setup,action,expected", [
    ("DeleteToolDialog", "dialog.open()", "删除", "delete"),
    ("ConfirmRunDialog", "dialog.openForRun({path: 'kept'})", "继续运行", "run"),
    ("CustomScriptImportDialog", "dialog.openForReplacement({title: host.longText, "
     "existingTitle: host.longText})", "确认替换", "replace"),
    ("CustomScriptImportDialog", "dialog.openForError(host.longText)", "关闭", ""),
    ("ExecutionCapacityDialog", "backend.executionCapacityRequested(host.longText, "
     "host.longText)", "停止并运行", "capacity"),
    ("PowerShellPluginDialog", "dialog.open()", "安装使用", "powershell"),
    ("PowerShellPluginDialog", "backend.pluginInstalling = true; "
     "backend.pluginInstallStatus = host.longText; dialog.open()", "取消安装", "cancel-install"),
    ("PythonDoctorDialog", "dialog.message = host.longText; "
     "dialog.packageNames = host.longText; dialog.open()", "确认安装", "python"),
    ("UpdateDialog", "dialog.open()", "立即更新", "download"),
    ("UpdateDialog", "backend.state = 'downloading'; dialog.open()", "取消下载", "cancel"),
    ("UpdateDialog", "backend.state = 'downloaded'; dialog.open()", "安装并重启", "restart"),
    ("UpdateDialog", "backend.state = 'error'; backend.status = host.longText; "
     "dialog.open()", "重试", "retry"),
])
def test_dialog_long_content_keeps_actions_visible_and_functional(
    qapp, qtbot, dark, dialog_type, setup, action, expected,
):
    """Small-window footers remain usable, including busy and error states."""
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    component = QQmlComponent(engine)
    parent_property = "" if dialog_type == "ExecutionCapacityDialog" else "parentWindow: host"
    source = '''
import QtQuick
import QtQuick.Controls
import "components"
import "theme"
ApplicationWindow {
    id: host
    width: 600; height: 480; visible: true
    property string longText: "Very long script name, description or error message. ".repeat(70)
    property string operation: ""
    Binding { target: Theme; property: "darkMode"; value: DARK }
    QtObject {
        id: backend
        property var selectedTool: ({title: host.longText})
        property bool pluginInstalled: false
        property bool pluginInstalling: false
        property string pluginInstallStatus: ""
        property real pluginInstallProgress: 30
        property string pluginVersion: "PowerShell 7.5"
        property string pluginDirectory: "C:/test/runtime"
        property string pythonEnvironmentDirectory: "C:/test/python"
        property string state: "available"
        property string currentVersion: "1.0"
        property string availableVersion: "2.0"
        property string releaseName: "Release notes"
        property string releaseNotes: host.longText
        property string releasePageUrl: ""
        property string status: "Downloading or installing an update"
        property real downloadProgress: 40
        property string totalSize: "10 MB"
        property string downloadedSize: "4 MB"
        signal executionCapacityRequested(string victimTitle, string requestedTitle)
        signal pluginInstallFinished(bool success, string message)
        function deleteSelected() { host.operation = "delete"; return true }
        function runSelected(values) { if (values.path === "kept") host.operation = "run" }
        function cancelScriptImportReplacement() {}
        function confirmScriptImportReplacement() {
            host.operation = "replace"; return {status: "ok", title: "Replaced"}
        }
        function cancelExecutionReplacement() {}
        function confirmExecutionReplacement() { host.operation = "capacity" }
        function installPowerShellPlugin() { host.operation = "powershell" }
        function cancelPowerShellPluginInstall() {
            host.operation = "cancel-install"; return true
        }
        function installPythonDependencies(packages) {
            if (packages === host.longText) host.operation = "python"; return true
        }
        function downloadUpdate() { host.operation = "download" }
        function cancelDownload() { host.operation = "cancel" }
        function skipVersion() {}
        function installLater() { return true }
        function installAndRestart() { host.operation = "restart" }
        function retryUpdate() { host.operation = "retry" }
    }
    DIALOG_TYPE { id: dialog; objectName: "dialog"; controller: backend; PARENT_PROPERTY }
    function openDialog() { SETUP }
}
'''
    source = (source.replace("DARK", str(dark).lower()).replace("DIALOG_TYPE", dialog_type)
              .replace("PARENT_PROPERTY", parent_property).replace("SETUP", setup))
    component.setData(source.encode(), QUrl.fromLocalFile(
        str(package_root() / "ui/qml/DialogLayoutHarness.qml")))
    window = component.create()
    assert window is not None, [e.toString() for e in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        assert QMetaObject.invokeMethod(window, "openDialog")
        dialog = window.findChild(QObject, "dialog")
        qtbot.waitUntil(lambda: dialog.property("opened"))
        qtbot.wait(50)
        content = dialog.property("contentItem")

        def descendants(item):
            yield item
            for child in item.childItems():
                yield from descendants(child)

        buttons = [item for item in descendants(content)
                   if item.property("primaryAction") is not None and item.isVisible()]
        assert buttons
        for button in buttons:
            rect = button.mapRectToItem(content, button.boundingRect())
            assert rect.left() >= -1 and rect.right() <= content.width() + 1
            assert rect.top() >= 0 and rect.bottom() <= content.height() + 1
        button = next(b for b in buttons if b.property("text") == action)
        if dark:
            button.forceActiveFocus()
            QTest.keyClick(window, Qt.Key.Key_Space)
        else:
            rect = button.mapRectToItem(window.contentItem(), button.boundingRect())
            QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=rect.center().toPoint())
        assert window.property("operation") == expected
        if dialog_type == "PythonDoctorDialog":
            assert dialog.property("installing")
            assert not button.isEnabled()
        assert not warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
