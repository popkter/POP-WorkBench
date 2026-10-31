pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root

    required property var controller
    required property var parentWindow
    required property var parameterValues
    required property var presetUtilities
    required property var androidBackend
    required property var jiraFeishuBackend
    property var videoBackend: null
    property string searchQuery: ""
    property bool compact: false
    property bool overlaysVisible: false
    property bool actionsInTitleBar: false
    property real toolListWidth: 288

    signal searchEdited(string query)
    function focusSearch() {
        presetSearch.forceActiveFocus();
        presetSearch.selectAll();
    }

    color: "transparent"

    readonly property string selectedPresetCommand:
        root.controller.selectedTool && root.controller.selectedTool.executor
            ? root.controller.selectedTool.executor.command : ""

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.scriptPanelGap

            Rectangle {
                objectName: "presetListPanel"
                Layout.preferredWidth: root.toolListWidth
                Layout.minimumWidth: 250
                Layout.maximumWidth: Math.max(250, root.width * 0.46)
                Layout.fillHeight: true
                radius: Theme.radiusMedium
                color: Theme.surfaceContainerLow
                border.width: 0
                clip: true

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space16
                    spacing: Theme.space8

                    AppTextField {
                        id: presetSearch
                        objectName: "presetListSearch"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        leftPadding: 40
                        baseRightPadding: 14
                        clearButtonEnabled: true
                        placeholderText: "搜索预设名称或描述..."
                        text: root.searchQuery
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSupporting
                        onTextChanged: if (root.searchQuery !== text) root.searchEdited(text)
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: Theme.surfaceContainer
                            border.color: presetSearch.activeFocus ? Theme.primary : "transparent"
                            border.width: presetSearch.activeFocus ? 1 : 0
                            MaterialIcon {
                                anchors.left: parent.left
                                anchors.leftMargin: 13
                                anchors.verticalCenter: parent.verticalCenter
                                icon: "search"
                                iconSize: 19
                                color: Theme.textSecondary
                            }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        Layout.leftMargin: Theme.space8
                        text: "其他预设"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontBody
                        font.weight: Font.DemiBold
                    }

                    ListView {
                        id: toolList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: root.controller.toolsModel
                        spacing: Theme.space4
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

                        delegate: Rectangle {
                            id: toolRow
                            required property string toolId
                            required property string title
                            required property string description
                            required property string iconName
                            required property bool selected
                            width: toolList.width - 8
                            height: 56
                            radius: Theme.radiusSmall
                            color: selected ? Theme.primaryContainer
                                : (toolMouse.containsMouse ? Theme.surfaceContainer : "transparent")

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Theme.space8
                                anchors.rightMargin: Theme.space8
                                spacing: Theme.space12
                                Rectangle {
                                    Layout.preferredWidth: 30
                                    Layout.preferredHeight: 30
                                    radius: Theme.radiusSmall
                                    color: Theme.surface
                                    MaterialIcon { anchors.centerIn: parent; icon: toolRow.iconName || "terminal"; iconSize: 19; color: toolRow.selected ? Theme.primary : Theme.secondary }
                                }
                                ColumnLayout {
                                    Layout.fillWidth: true
                                    spacing: 1
                                    Text { Layout.fillWidth: true; text: toolRow.title; color: toolRow.selected ? Theme.primary : Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: toolRow.selected ? Font.Bold : Font.Normal; elide: Text.ElideRight }
                                    Text { Layout.fillWidth: true; text: toolRow.description; color: Theme.textSecondary; font.pixelSize: Theme.fontMicro; elide: Text.ElideRight }
                                }
                                MaterialIcon { icon: "chevron_right"; iconSize: 18; color: toolRow.selected ? Theme.primary : Theme.textSecondary }
                            }

                            MouseArea {
                                id: toolMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: root.controller.selectTool(toolRow.toolId)
                            }
                        }
                    }
                }
            }

            Loader {
                id: detailWorkspaceLoader
                Layout.fillWidth: true
                Layout.fillHeight: true
                sourceComponent: dedicatedWorkspace
            }
        }
    }

    Component {
        id: dedicatedWorkspace
        Item {
            anchors.fill: parent

            CommandWorkspace {
                anchors.fill: parent
                visible: root.selectedPresetCommand === "scrcpy"
                controller: root.controller
                parentWindow: root.parentWindow
                parameterValues: root.parameterValues
                androidController: root.androidBackend
                scrcpySelected: true
                actionsInTitleBar: root.actionsInTitleBar
                overlaysVisible: root.overlaysVisible
            }

            PresetWorkspace {
                anchors.fill: parent
                visible: root.selectedPresetCommand !== "scrcpy"
                toolController: root.controller
                utilities: root.presetUtilities
                androidBackend: root.androidBackend
                jiraFeishuBackend: root.jiraFeishuBackend
                videoBackend: root.videoBackend
                shortcutsEnabled: !root.overlaysVisible
                compact: root.compact
                actionsInTitleBar: root.actionsInTitleBar
            }
        }
    }
}
