pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

Item {
    id: root
    required property var controller
    property string searchQuery: ""

    Component.onCompleted: controller.attachWindows(notch, panel, Theme.floatingNotchWidth, Theme.floatingGripHeight + Theme.controlHeight * 2 + Theme.space8, Theme.floatingPanelWidth, Theme.floatingPanelHeight)

    ApplicationWindow {
        id: notch
        objectName: "floatingNotchWindow"
        transientParent: null
        title: "泡泡工具箱快捷入口"
        width: Theme.floatingNotchWidth
        height: Theme.floatingGripHeight + Theme.controlHeight * 2 + Theme.space8
        visible: root.controller.visible
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
        color: "transparent"
        opacity: notchHover.hovered || panelHover.hovered || root.controller.dragging
            ? 1 : Theme.floatingIdleOpacity
        Behavior on opacity {
            NumberAnimation { duration: Theme.motionStandard }
        }

        Rectangle {
            anchors.fill: parent
            color: Theme.surfaceContainerLow
            topLeftRadius: Theme.radiusLarge
            bottomLeftRadius: Theme.radiusLarge
            border.width: 1
            border.color: Theme.outlineVariant

            Column {
                anchors.fill: parent
                anchors.bottomMargin: Theme.space8
                spacing: Theme.space4
                Item {
                    width: parent.width
                    height: Theme.floatingGripHeight
                    MaterialIcon {
                        anchors.centerIn: parent
                        icon: "drag_handle"
                        iconSize: Theme.iconSmall
                        color: Theme.textSecondary
                    }
                    MouseArea {
                        id: grip
                        objectName: "floatingDragGrip"
                        anchors.fill: parent
                        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                        preventStealing: true
                        onPressed: root.controller.beginDrag()
                        onPositionChanged: function (mouse) {
                            if (pressed)
                                root.controller.updateDrag();
                        }
                        onReleased: root.controller.endDrag()
                        onCanceled: root.controller.endDrag()
                    }
                }
                PrimaryButton {
                    id: settingsButton
                    objectName: "floatingSettingsButton"
                    x: Theme.space4
                    width: parent.width - Theme.space8
                    height: Theme.controlHeight - Theme.space4
                    radius: Theme.radiusMedium
                    text: "设置"
                    iconName: "settings"
                    compact: true
                    showHoverTips: false
                    tonal: true
                    border.width: 0
                    color: hovered ? Theme.primaryContainer : "transparent"
                    onClicked: root.controller.openSettings()
                }
                PrimaryButton {
                    id: scriptsButton
                    objectName: "floatingScriptsButton"
                    x: Theme.space4
                    width: parent.width - Theme.space8
                    height: Theme.controlHeight - Theme.space4
                    radius: Theme.radiusMedium
                    text: "自定义脚本"
                    iconName: "terminal"
                    compact: true
                    showHoverTips: false
                    tonal: true
                    border.width: 0
                    color: hovered || root.controller.expanded ? Theme.primaryContainer : "transparent"
                    onClicked: root.controller.toggleExpanded()
                }
            }
        }
        HoverHandler {
            id: notchHover
            onHoveredChanged: root.controller.pointerChanged()
        }
    }

    ApplicationWindow {
        id: panel
        objectName: "floatingScriptPanelWindow"
        transientParent: null
        title: "自定义脚本快捷运行"
        width: Theme.floatingPanelWidth
        height: Theme.floatingPanelHeight
        visible: root.controller.visible && root.controller.expanded
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "transparent"
        palette.text: Theme.textPrimary
        palette.windowText: Theme.textPrimary
        palette.highlight: Theme.primary
        palette.highlightedText: Theme.primaryForeground
        contentItem.clip: true

        onVisibleChanged: {
            if (visible)
                extendAnimation.restart();
            else
                scripts.closeMenus();
        }

        Rectangle {
            id: panelSurface
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            width: parent.width
            radius: Theme.radiusMedium
            color: Theme.surfaceContainerLow
            border.width: 1
            border.color: Theme.outlineVariant

            ColumnLayout {
                anchors.fill: parent
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: Theme.space12
                    Layout.leftMargin: Theme.space16
                    Layout.rightMargin: Theme.space8
                    Text {
                        Layout.fillWidth: true
                        text: "自定义脚本"
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontComponentTitle
                        font.weight: Font.DemiBold
                    }
                    PrimaryButton {
                        width: Theme.controlHeightSmall
                        height: Theme.controlHeightSmall
                        compact: true
                        showHoverTips: false
                        text: "收起"
                        iconName: "chevron_right"
                        tonal: true
                        border.width: 0
                        color: hovered ? Theme.surfaceContainer : "transparent"
                        onClicked: root.controller.collapse()
                    }
                }
                CustomScriptList {
                    id: scripts
                    objectName: "floatingScriptList"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    controller: root.controller
                    listModel: root.controller.toolsModel
                    quickLaunch: true
                    searchQuery: root.searchQuery
                    onSearchEdited: function (query) {
                        root.searchQuery = query;
                        root.controller.setToolSearchQuery(query);
                    }
                    onToolActivated: function (toolId) {
                        root.controller.launchTool(toolId);
                    }
                    onMenuOpenChanged: root.controller.setMenuOpen(menuOpen)
                }
            }
        }
        NumberAnimation {
            id: extendAnimation
            target: panelSurface
            property: "x"
            from: panel.width
            to: 0
            duration: Theme.motionStandard
            easing.type: Easing.OutCubic
        }
        HoverHandler {
            id: panelHover
            onHoveredChanged: root.controller.pointerChanged()
        }
        Shortcut {
            sequence: "Esc"
            context: Qt.WindowShortcut
            onActivated: root.controller.collapse()
        }
    }
}
