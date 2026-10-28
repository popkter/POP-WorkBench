import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

// Shared choices for the regular popup and the Decade card's inline section.
ColumnLayout {
    id: root
    required property var controller
    required property var deviceState
    property bool explicitTarget: false
    property bool showHoverTips: true
    property real maximumListHeight: 208
    signal deviceSelected()
    spacing: Theme.space4
    RowLayout {
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space4
        spacing: Theme.space8
        Text {
            Layout.fillWidth: true
            text: "Android 设备"
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSupporting
            font.weight: Font.DemiBold
        }
        PrimaryButton {
            objectName: "devicePopupRefresh"
            text: "刷新设备"
            iconName: "refresh"
            compact: true
            showHoverTips: root.showHoverTips
            Layout.preferredWidth: 28
            Layout.preferredHeight: 28
            glyphSize: 18
            radius: Theme.radiusTiny
            color: hovered ? Theme.surfaceContainerHigh : "transparent"
            foregroundColor: Theme.textSecondary
            border.width: 0
            enabled: root.controller && !root.controller.androidDeviceRefreshing
            iconSpinning: root.controller && root.controller.androidDeviceRefreshing
            Accessible.role: Accessible.Button
            Accessible.name: text
            Accessible.onPressAction: if (enabled) clicked()
            onClicked: root.controller.refreshAndroidDevices()
        }
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        color: Theme.outlineVariant
    }
    Text {
        Layout.fillWidth: true
        visible: root.explicitTarget
        text: "脚本已指定目标，界面选择仅作用于未指定目标的调用。"
        color: Theme.textSecondary
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 64
        visible: deviceList.count === 0
        radius: Theme.radiusSmall
        color: Theme.surfaceContainer
        RowLayout {
            anchors.fill: parent
            anchors.margins: Theme.space12
            spacing: Theme.space12
            MaterialIcon {
                icon: "smartphone"
                iconSize: 24
                color: Theme.textSecondary
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Theme.space4
                Text {
                    Layout.fillWidth: true
                    text: root.controller && root.controller.androidDeviceRefreshing
                        ? "正在查找设备…" : "未连接设备"
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSupporting
                    elide: Text.ElideRight
                }
                Text {
                    Layout.fillWidth: true
                    text: "检查连接与 USB 调试授权"
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSmall
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
    ListView {
        id: deviceList
        objectName: "androidDeviceChoicesList"
        Layout.fillWidth: true
        Layout.preferredHeight: Math.min(count * 52, root.maximumListHeight)
        clip: true
        model: root.controller ? root.controller.androidDevices : []
        ScrollBar.vertical: ScrollBar { }
        delegate: Rectangle {
            id: deviceRow
            required property var modelData
            objectName: "deviceRow_" + modelData.serial
            width: deviceList.width
            height: 52
            radius: Theme.radiusSmall
            color: modelData.serial === root.deviceState.serial
                ? Theme.primaryContainer
                : rowMouse.containsMouse ? Theme.surfaceContainerHigh : "transparent"
            RowLayout {
                anchors.fill: parent
                anchors.margins: Theme.space8
                spacing: Theme.space8
                MaterialIcon {
                    icon: "smartphone"
                    iconSize: 18
                    color: deviceRow.modelData.serial === root.deviceState.serial
                        ? Theme.primary : Theme.textSecondary
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: 2
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        text: deviceRow.modelData.model
                            ? deviceRow.modelData.model.replace(/_/g, " ")
                            : deviceRow.modelData.serial
                        elide: Text.ElideRight
                        color: deviceRow.modelData.serial === root.deviceState.serial
                            ? Theme.primary : Theme.textPrimary
                        font.pixelSize: Theme.fontSupporting
                    }
                    Text {
                        Layout.fillWidth: true
                        Layout.minimumWidth: 0
                        visible: !!deviceRow.modelData.model
                        text: deviceRow.modelData.serial
                        elide: Text.ElideMiddle
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSmall
                    }
                }
                MaterialIcon {
                    visible: modelData.serial === root.deviceState.serial
                    icon: "check"; iconSize: 18; color: Theme.primary
                }
            }
            MouseArea {
                id: rowMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: {
                    root.controller.selectAndroidDevice(modelData.serial)
                    root.deviceSelected()
                }
            }
        }
    }
}
