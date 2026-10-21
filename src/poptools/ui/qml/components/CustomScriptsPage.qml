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
    property alias kindFilter: mainScriptList.kindFilter
    readonly property bool drawerVisible: false
    readonly property bool popupVisible: false
    color: Theme.workspaceBackground

    signal searchEdited(string query)
    signal createRequested()
    signal importRequested()
    signal editRequested()
    signal deleteRequested()
    signal confirmRunRequested(var values)
    signal toastRequested(string message, bool error)

    function closeDrawerImmediately() {}
    function closeDrawer() {}
    function runSelectedTool() { detailPanel.runSelectedTool() }
    function shareSelectedTool() {
        const success = root.controller.exportSelectedScriptToClipboard()
        root.toastRequested(success ? "脚本已复制到剪贴板" : "脚本分享失败", !success)
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
                border.color: Theme.outlineVariant
                border.width: 1

                CustomScriptList {
                    id: mainScriptList
                    anchors.fill: parent
                    controller: root.controller
                    listModel: root.controller.toolsModel
                    searchQuery: root.searchQuery
                    onSearchEdited: function(query) { root.searchEdited(query) }
                    onToolActivated: function(toolId) { root.controller.selectTool(toolId) }
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
