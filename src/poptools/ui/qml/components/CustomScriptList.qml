pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    required property var controller
    required property var listModel
    property string searchQuery: ""
    property string kindFilter: "all"
    property bool quickLaunch: false
    property string keyboardToolId: ""
    readonly property bool menuOpen: sortButton.menuOpen
    readonly property int visibleCount: {
        const count = listModel.count;
        return listModel.countForKind(kindFilter);
    }
    signal searchEdited(string query)
    signal toolActivated(string toolId)
    onKindFilterChanged: keyboardToolId = ""
    onSearchQueryChanged: keyboardToolId = ""
    Connections {
        target: root.listModel
        function onModelReset() { root.keyboardToolId = "" }
    }
    function closeMenus() {
        sortButton.closeMenu();
    }
    function navigateTo(toolId) {
        keyboardToolId = toolId;
        if (quickLaunch)
            listModel.select(toolId);
        else
            toolActivated(toolId);
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.space16
        spacing: Theme.space8

        AppTextField {
            id: searchField
            objectName: "scriptListSearch"
            FilePathDropArea {
                target: searchField
            }
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            leftPadding: 42
            rightPadding: 14
            placeholderText: "搜索名称、说明或标签..."
            text: root.searchQuery
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSupporting
            onTextChanged: if (root.searchQuery !== text)
                root.searchEdited(text)
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surfaceContainer
                border.color: searchField.activeFocus ? Theme.primary : "transparent"
                border.width: searchField.activeFocus ? 1 : 0
                MaterialIcon {
                    anchors.left: parent.left
                    anchors.leftMargin: 13
                    anchors.verticalCenter: parent.verticalCenter
                    icon: "search"
                    iconSize: 20
                    color: Theme.textSecondary
                }
            }
        }

        Flow {
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            spacing: 6
            Repeater {
                model: [
                    {
                        label: "全部",
                        value: "all"
                    },
                    {
                        label: "ADB",
                        value: "batch"
                    },
                    {
                        label: "PowerShell",
                        value: "powershell"
                    },
                    {
                        label: "Python",
                        value: "python"
                    },
                ]
                delegate: Rectangle {
                    id: filterChip
                    required property var modelData
                    width: filterChip.modelData.value === "powershell" ? 95 : filterChip.modelData.value === "python" ? 69 : filterChip.modelData.value === "all" ? 52 : 54
                    height: 28
                    radius: Theme.radiusSmall
                    color: root.kindFilter === modelData.value ? Theme.primaryContainer : Theme.surfaceContainerLow
                    border.color: root.kindFilter === modelData.value ? Theme.listSelected : Theme.outline
                    Text {
                        anchors.centerIn: parent
                        text: filterChip.modelData.label
                        color: root.kindFilter === filterChip.modelData.value ? Theme.primary : Theme.textSecondary
                        font.pixelSize: Theme.fontCaption
                    }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.kindFilter = filterChip.modelData.value
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 24
            Layout.topMargin: 3
            Text {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.leftMargin: 0
                text: "脚本名称"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
            }
            ToolSortButton {
                id: sortButton
                Layout.preferredWidth: 28
                Layout.preferredHeight: 24
                glyphSize: 20
                controller: root.controller
                objectName: "scriptListSort"
            }
        }

        ListView {
            id: scriptList
            objectName: "sharedScriptList"
            readonly property bool needsVerticalScroll: contentHeight > height + 0.5
            function selectAdjacent(direction) {
                const toolId = root.listModel.adjacentToolId(direction, root.kindFilter);
                if (toolId.length > 0)
                    root.navigateTo(toolId);
            }
            Keys.onUpPressed: selectAdjacent(-1)
            Keys.onDownPressed: selectAdjacent(1)
            Keys.onReturnPressed: root.toolActivated(root.keyboardToolId)
            Keys.onEnterPressed: root.toolActivated(root.keyboardToolId)
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            Layout.leftMargin: 0
            Layout.rightMargin: 0
            spacing: 0
            model: root.listModel
            boundsBehavior: Flickable.StopAtBounds
            Text {
                anchors.centerIn: parent
                visible: root.visibleCount === 0
                text: root.listModel.totalCount === 0 ? "暂无自定义脚本" : "没有匹配的脚本"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSupporting
            }

            ScrollBar.vertical: ScrollBar {
                id: scriptListScrollBar
                policy: scriptList.needsVerticalScroll ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
            }

            delegate: Rectangle {
                id: scriptRow
                required property string toolId
                required property string title
                required property string description
                required property string iconName
                required property string executorKind
                required property bool selected
                required property bool running
                required property int index
                objectName: "scriptRow_" + toolId
                onSelectedChanged: if (selected)
                    scriptList.positionViewAtIndex(index, ListView.Contain)
                width: scriptList.width - (scriptList.needsVerticalScroll ? scriptListScrollBar.width + Theme.space8 : 0)

                opacity: root.quickLaunch && running ? 0.6 : 1
                height: (root.kindFilter === "all" || root.kindFilter === executorKind) ? Theme.scriptRowHeight : 0
                visible: height > 0
                radius: Theme.radiusControl
                color: selected ? (Theme.listSelected) : (rowMouse.containsMouse ? Theme.surfaceContainer : (index % 2 === 0 ? (Theme.listAlternate) : "transparent"))
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space12
                    anchors.rightMargin: Theme.space8
                    spacing: 10
                    Rectangle {
                        Layout.preferredWidth: 26
                        Layout.preferredHeight: 26
                        radius: 5
                        color: scriptRow.executorKind === "python" ? Theme.tertiaryContainer : scriptRow.executorKind === "powershell" ? Theme.runtimeBadge : Theme.successContainer
                        MaterialIcon {
                            anchors.centerIn: parent
                            icon: scriptRow.iconName || (scriptRow.executorKind === "batch" ? "smartphone" : "terminal")
                            iconSize: 16
                            color: scriptRow.executorKind === "python" ? Theme.tertiary : scriptRow.executorKind === "powershell" ? Theme.runtimeBadgeText : Theme.success
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: scriptRow.title
                        color: scriptRow.selected ? Theme.primary : Theme.textPrimary
                        font.pixelSize: Theme.fontSupporting
                        font.weight: scriptRow.selected ? Font.Bold : Font.Normal
                        elide: Text.ElideRight
                    }
                    MaterialIcon {
                        icon: scriptRow.running ? "hourglass_top" : root.quickLaunch ? "play_arrow" : "chevron_right"
                        iconSize: 14
                        color: scriptRow.running ? Theme.primary : Theme.textSecondary
                        Layout.preferredWidth: 14
                    }
                }
                HoverTips {
                    parent: rowMouse
                    visible: rowMouse.containsMouse
                    text: scriptRow.title + (scriptRow.running ? "（运行中）" : "")
                }
                MouseArea {
                    id: rowMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: root.quickLaunch && scriptRow.running ? Qt.ForbiddenCursor : Qt.PointingHandCursor
                    onClicked: {
                        if (root.quickLaunch && scriptRow.running)
                            return;
                        root.toolActivated(scriptRow.toolId);
                        scriptList.forceActiveFocus();
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: root.visibleCount + " 个脚本"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
            }
            Text {
                text: root.quickLaunch ? "点击运行" : "紧凑 · ↑↓ 切换"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
            }
        }
    }
}
