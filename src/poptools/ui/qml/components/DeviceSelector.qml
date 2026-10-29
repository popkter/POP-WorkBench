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
    property bool iconOnly: false
    property bool showHoverTips: true
    property bool inlineMode: false
    property bool inlineExpanded: false
    readonly property bool popupVisible: inlineMode ? inlineExpanded : devicePopup.opened
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
    onToolIdChanged: closeDeviceMenu()
    onVisibleChanged: { if (!visible) closeDeviceMenu() }
    onInlineModeChanged: closeDeviceMenu()

    function closeDeviceMenu() {
        inlineExpanded = false
        devicePopup.close()
    }

    function positionDeviceMenu() {
        const point = selector.mapToItem(Overlay.overlay, 0, selector.height)
        const desiredX = root.compact ? point.x + selector.width - devicePopup.width : point.x
        devicePopup.x = Math.max(8, Math.min(desiredX,
                              Overlay.overlay.width - devicePopup.width - 8))
        devicePopup.y = point.y + 6 + devicePopup.height <= Overlay.overlay.height - 8
            ? point.y + 6 : Math.max(8, point.y - selector.height - devicePopup.height - 6)
    }
    function openDeviceMenu() {
        if (root.inlineMode && root.inlineExpanded) {
            closeDeviceMenu()
            return
        }
        if (!root.controller) return
        root.controller.refreshAndroidDevices()
        if (!root.visible || root.deviceState.pluginMissing) return
        if (root.inlineMode) {
            inlineExpanded = true
            return
        }
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
        height: root.iconOnly ? Theme.decadeCardActionSize : root.compact ? Theme.captionActionHeight : 41
        radius: root.iconOnly ? Theme.radiusSmall : root.compact ? Theme.radiusTiny : Theme.radiusConsole
        color: root.iconOnly ? (selectorMouse.containsMouse || root.popupVisible ? Theme.primaryContainer : Theme.decadeCardActionFill) : root.compact
            ? (selectorMouse.containsMouse || root.popupVisible ? Theme.navigationHover : "transparent")
            : selectorMouse.containsMouse ? Theme.surfaceContainer : Theme.surfaceContainerLow
        border.width: root.iconOnly ? Theme.borderWidthThin : root.compact ? 0 : 1
        border.color: root.iconOnly ? Theme.decadeCardActionBorder : Theme.outlineVariant
        activeFocusOnTab: true
        Accessible.role: Accessible.ComboBox
        Accessible.name: "目标设备：" + root.deviceState.label
        Accessible.onPressAction: root.openDeviceMenu()
        Keys.onSpacePressed: root.openDeviceMenu()
        Keys.onReturnPressed: root.openDeviceMenu()
        RowLayout {
            visible: !root.iconOnly
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
                icon: root.popupVisible ? "expand_less" : "expand_more"
                iconSize: root.compact ? 14 : 18
                color: root.compact ? Theme.chromeForeground : Theme.textSecondary
            }
        }
        Image {
            objectName: "decadeDeviceCamera"
            visible: root.iconOnly && !Theme.zioMode
            anchors.centerIn: parent
            width: 27; height: 29
            source: "../../../resources/icons/decade-camera.svg"
            sourceSize: Qt.size(width, height)
            smooth: true
        }
        ZioDial {
            objectName: "zioDeviceDial"
            visible: root.iconOnly && Theme.zioMode
            anchors.centerIn: parent
            width: 27; height: 27
            highlighted: selectorMouse.containsMouse || root.popupVisible
        }
        MouseArea {
            id: selectorMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.openDeviceMenu()
        }
        HoverTips {
            visible: root.showHoverTips && root.compact && selectorMouse.containsMouse && !root.popupVisible
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
        contentItem: AndroidDevicePicker {
            controller: root.controller
            deviceState: root.deviceState
            explicitTarget: root.compact && root.explicitTarget
            onDeviceSelected: root.closeDeviceMenu()
        }
    }
}
