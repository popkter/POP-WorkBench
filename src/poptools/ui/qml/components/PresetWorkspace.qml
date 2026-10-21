import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ColumnLayout {
    id: root

    required property var toolController
    required property var utilities
    required property var androidBackend
    required property var jiraFeishuBackend
    property bool compact: false
    property bool actionsInTitleBar: false
    readonly property string workspaceCommand: toolController.selectedTool.executor
        ? toolController.selectedTool.executor.command : ""

    function openRecordingFolderDialog() {
        recordingWorkspace.openSaveDialog()
    }

    spacing: Theme.sectionSpacing

    StackLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        currentIndex: root.workspaceCommand === "recording" ? 1
                      : root.workspaceCommand === "jira_feishu" ? 2
                      : 0

        InteractiveColorPicker {
            Layout.fillWidth: true
            Layout.fillHeight: true
            utilities: root.utilities
        }

        RecordingWorkspace {
            id: recordingWorkspace
            actionsInTitleBar: root.actionsInTitleBar
            Layout.fillWidth: true
            Layout.fillHeight: true
            controller: root.utilities
            androidController: root.androidBackend
            toolId: root.toolController.selectedTool.id || ""
        }

        JiraFeishuWorkspace {
            Layout.fillWidth: true
            Layout.fillHeight: true
            controller: root.jiraFeishuBackend
            compact: root.compact
        }
    }
}
