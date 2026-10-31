pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root
    objectName: "customScriptsPage"
    required property var controller
    required property var androidBackend
    required property var parentWindow
    required property var parameterValues
    property string searchQuery: ""
    property bool compact: false
    property bool compactHeight: false
    property bool overlaysVisible: false
    property bool deviceInTitleBar: false
    property string pendingRunToolId: ""
    property alias kindFilter: mainScriptList.kindFilter
    readonly property bool drawerVisible: false
    readonly property bool popupVisible: false
    color: "transparent"

    signal searchEdited(string query)
    function focusSearch() { mainScriptList.focusSearch(); }
    signal createRequested()
    signal importRequested()
    signal editRequested()
    signal deleteRequested()
    signal confirmRunRequested(var values)
    signal toastRequested(string message, bool error)

    function closeDrawerImmediately() {}
    function closeDrawer() {}
    function runSelectedTool() { detailPanel.runSelectedTool() }
    function selectTool(id) {
        if (controller.selectedTool.id !== id)
            controller.selectTool(id)
    }
    function requestQuickRun(id) {
        if (overlaysVisible)
            return
        selectTool(id)
        pendingRunToolId = id
        Qt.callLater(dispatchQuickRun)
    }
    function dispatchQuickRun() {
        const id = pendingRunToolId
        pendingRunToolId = ""
        // Allow the selected script's form/defaults to settle first. A double
        // click on a running script must never act as the Stop button.
        if (id && controller.selectedTool.id === id && !controller.running && !overlaysVisible)
            runSelectedTool()
    }
    function shareSelectedTool() {
        const success = root.controller.exportSelectedScriptToClipboard()
        root.toastRequested(success ? "脚本已复制到剪贴板" : "脚本分享失败", !success)
    }
    function handleToolAction(id, action) {
        if (overlaysVisible || controller.selectedTool.id !== id)
            return
        if (action === "edit") {
            if (controller.selectedTool.editable && !controller.running) editRequested()
        } else if (action === "delete") {
            if (!controller.running) deleteRequested()
        } else if (action === "share") {
            shareSelectedTool()
        } else if (action === "run") {
            runSelectedTool()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.scriptPanelGap

            Rectangle {
                objectName: "customScriptListPanel"
                Layout.preferredWidth: Math.max(Theme.scriptListMinimumWidth, Math.min(Theme.scriptListMaximumWidth, root.width * Theme.scriptListWidthRatio))
                Layout.minimumWidth: Theme.scriptListMinimumWidth
                Layout.maximumWidth: Theme.scriptListMaximumWidth
                Layout.fillHeight: true
                radius: Theme.radiusMedium
                color: Theme.surfaceContainerLow
                border.width: 0

                CustomScriptList {
                    id: mainScriptList
                    anchors.fill: parent
                    controller: root.controller
                    listModel: root.controller.toolsModel
                    searchQuery: root.searchQuery
                    onSearchEdited: function(query) { root.searchEdited(query) }
                    onToolActivated: function(toolId) { root.selectTool(toolId) }
                    onToolRunRequested: function(toolId) { root.requestQuickRun(toolId) }
                    onToolActionRequested: function(toolId, action) {
                        root.handleToolAction(toolId, action)
                    }
                    onReorderFailed: root.toastRequested("脚本排序保存失败，请重试。", true)
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true

                CustomToolDetailPanel {
                    id: detailPanel
                    anchors.fill: parent
                    controller: root.controller
                    androidBackend: root.androidBackend
                    parentWindow: root.parentWindow
                    parameterValues: root.parameterValues
                    displayedTool: root.controller.selectedTool
                    splitConsole: true
                    submitParametersOnEnter: true
                    actionsInTitleBar: true
                    deviceInTitleBar: root.deviceInTitleBar
                    onEditRequested: root.editRequested()
                    onDeleteRequested: root.deleteRequested()
                    onConfirmRunRequested: function(values) { root.confirmRunRequested(values) }
                    onToastRequested: function(message, error) { root.toastRequested(message, error) }
                }
            }
        }
    }
}
