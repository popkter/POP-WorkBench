import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Column {
    id: root
    objectName: "toolDeviceSelector"
    required property var controller
    required property string toolId
    property bool requiredDevice: false
    property bool explicitTarget: false
    property bool compact: false
    readonly property bool popupVisible: devicePopup.opened
    property int stateRevision: 0
    readonly property var deviceState: {
        const revision = stateRevision
        return visible && controller
            ? controller.selectedAndroidDevice
            : ({ serial: "", available: false, label: "未检测到 Android 设备" })
    }
    spacing: 6
    Connections {
        target: root.controller
        function onStateChanged() { root.stateRevision += 1 }
    }
    onToolIdChanged: devicePopup.close()
    onVisibleChanged: { if (!visible) devicePopup.close() }

    function positionDeviceMenu() {
        const point = selector.mapToItem(Overlay.overlay, 0, selector.height)
        const desiredX = root.compact ? point.x + selector.width - devicePopup.width : point.x
        devicePopup.x = Math.max(8, Math.min(desiredX,
                              Overlay.overlay.width - devicePopup.width - 8))
        devicePopup.y = point.y + 6 + devicePopup.height <= Overlay.overlay.height - 8
            ? point.y + 6 : Math.max(8, point.y - selector.height - devicePopup.height - 6)
    }
    function openDeviceMenu() {
        if (!root.controller) return
        root.controller.refreshAndroidDevices()
        if (!root.visible || root.deviceState.pluginMissing) return
        positionDeviceMenu()
        devicePopup.open()
        Qt.callLater(positionDeviceMenu)
    }

    Text {
        visible: !root.compact
        text: "目标设备" + (root.requiredDevice ? " *" : "")
        color: Theme.textPrimary
        font.pixelSize: Theme.fontCaption
        font.weight: Font.DemiBold
    }
    Rectangle {
        id: selector
        width: parent.width
        height: root.compact ? Theme.captionActionHeight : 41
        radius: root.compact ? Theme.radiusTiny : Theme.radiusConsole
        color: root.compact
            ? (selectorMouse.containsMouse || devicePopup.opened ? Theme.navigationHover : "transparent")
            : selectorMouse.containsMouse ? Theme.surfaceContainer : Theme.surfaceContainerLow
        border.width: root.compact ? 0 : 1
        border.color: Theme.outlineVariant
        activeFocusOnTab: true
        Accessible.role: Accessible.ComboBox
        Accessible.name: "目标设备：" + root.deviceState.label
        Accessible.onPressAction: root.openDeviceMenu()
        Keys.onSpacePressed: root.openDeviceMenu()
        Keys.onReturnPressed: root.openDeviceMenu()
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: root.compact ? 8 : 13
            anchors.rightMargin: root.compact ? 6 : 10
            spacing: root.compact ? 6 : 10
            MaterialIcon {
                icon: "smartphone"; iconSize: root.compact ? 16 : 19
                color: root.deviceState.available ? Theme.success : Theme.textSecondary
            }
            Text {
                objectName: "deviceSelectorLabel"
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: !root.compact ? root.deviceState.label
                    : !root.deviceState.serial
                      ? (root.deviceState.pluginMissing ? "安装 Android 插件" : "选择设备")
                      : root.deviceState.available
                        ? (root.deviceState.name || root.deviceState.label) : root.deviceState.label
                color: root.compact ? Theme.chromeForeground : Theme.textPrimary
                font.pixelSize: Theme.fontSupporting
                elide: root.compact ? Text.ElideRight : Text.ElideMiddle
            }
            Text {
                visible: !root.compact
                text: root.deviceState.available ? "已连接"
                    : root.deviceState.serial ? "不可用" : "未选择"
                color: root.deviceState.available ? Theme.success : Theme.textSecondary
                font.pixelSize: Theme.fontSmall
            }
            MaterialIcon {
                icon: devicePopup.opened ? "expand_less" : "expand_more"
                iconSize: root.compact ? 14 : 18
                color: root.compact ? Theme.chromeForeground : Theme.textSecondary
            }
        }
        MouseArea {
            id: selectorMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.openDeviceMenu()
        }
        HoverTips {
            visible: root.compact && selectorMouse.containsMouse && !devicePopup.opened
            text: root.deviceState.label
        }
    }
    Text {
        width: parent.width
        visible: !root.compact
            && (root.explicitTarget || (root.requiredDevice && !root.deviceState.available))
        text: root.explicitTarget
            ? "脚本已指定目标，界面选择仅作用于未指定目标的调用。"
            : root.deviceState.serial ? "原设备不可用，请重新连接或选择其他设备。"
            : "运行前请选择已连接的 Android 设备。"
        color: Theme.textSecondary
        font.pixelSize: Theme.fontSmall
        wrapMode: Text.WordWrap
    }

    Popup {
        id: devicePopup
        objectName: "toolDevicePopup"
        parent: Overlay.overlay
        width: Math.min(root.compact ? 240 : root.width,
            Overlay.overlay ? Overlay.overlay.width - 16 : root.width)
        padding: Theme.space8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: AppPopupSurface {
            fillColor: Theme.surfaceContainerLow
            outlineColor: Theme.outlineVariant
            cornerRadius: Theme.radiusMedium
        }
        onHeightChanged: { if (opened) root.positionDeviceMenu() }
        contentItem: ColumnLayout {
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
                visible: root.compact && root.explicitTarget
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
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(count, 4) * 52
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
                            devicePopup.close()
                        }
                    }
                }
            }
        }
    }
}
