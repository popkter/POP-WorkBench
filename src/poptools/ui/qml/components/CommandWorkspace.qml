import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ColumnLayout {
    id: root

    required property var controller
    required property var parentWindow
    required property var parameterValues
    property var androidController: null
    property bool scrcpySelected: false
    property bool actionsInTitleBar: false
    property bool overlaysVisible: false
    readonly property int parameterCount:
        (root.controller.selectedTool.parameters || []).length
    readonly property bool hasParameters: parameterCount > 0
    readonly property real parameterLabelHeight: 20
    readonly property real parameterInputHeight: 54
    readonly property real parameterLabelSpacing: 6
    readonly property real parameterItemSpacing: 13
    readonly property real parameterItemHeight:
        parameterLabelHeight + parameterLabelSpacing + parameterInputHeight
    readonly property real parameterFieldsHeight: parameterFlow.implicitHeight
    readonly property real parameterContentHeight: parameterFieldsHeight
        + (deviceSelector.visible ? deviceSelector.implicitHeight + spacing : 0)

    spacing: Theme.sectionSpacing

    DeviceSelector {
        id: deviceSelector
        Layout.fillWidth: true
        visible: !!root.controller.selectedTool.uses_android_device
            && !(root.scrcpySelected && root.actionsInTitleBar)
        enabled: !root.scrcpySelected || !root.controller.running
        controller: root.androidController
        toolId: root.controller.selectedTool.id || ""
        requiredDevice: !!root.controller.selectedTool.requires_android_device
        explicitTarget: !!root.controller.selectedTool.android_explicit_target
    }

    Loader {
        id: workspaceDisplayPicker
        Layout.preferredWidth: 190
        active: root.scrcpySelected && !root.actionsInTitleBar
        visible: active
        readonly property bool popupVisible: item ? item.popupVisible : false
        sourceComponent: DisplaySelector { backend: root.controller.scrcpyDisplays }
    }

    Rectangle {
        id: scrcpyHost
        property bool geometryReady: false
        property int stableGeometryFrames: 0
        property string lastGeometryKey: ""
        readonly property real nativeContentInset: Math.max(2, radius / 2)
        visible: root.scrcpySelected
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 180
        radius: Theme.radiusLarge
        color: Theme.consoleBackground
        clip: true

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            preventStealing: true
            onPressed: function(mouse) { mouse.accepted = true }
            onReleased: function(mouse) { mouse.accepted = true }
            onDoubleClicked: function(mouse) { mouse.accepted = true }
        }

        function geometrySnapshot() {
            const inset = nativeContentInset
            const point = mapToItem(null, inset, inset)
            return {
                x: Math.round(point.x),
                y: Math.round(point.y),
                width: Math.round(Math.max(0, width - inset * 2)),
                height: Math.round(Math.max(0, height - inset * 2))
            }
        }

        function hideUntilLayoutSettles() {
            geometryReady = false
            stableGeometryFrames = 0
            lastGeometryKey = ""
            root.controller.updateScrcpyGeometry(0, 0, 0, 0, false)
        }

        function syncGeometry() {
            const geometry = geometrySnapshot()
            const geometryKey = geometry.x + ":" + geometry.y + ":"
                              + geometry.width + ":" + geometry.height
            const validGeometry = geometry.width > 1 && geometry.height > 1

            if (!geometryReady) {
                if (validGeometry && geometryKey === lastGeometryKey)
                    stableGeometryFrames += 1
                else
                    stableGeometryFrames = 0
                lastGeometryKey = geometryKey
                geometryReady = validGeometry && stableGeometryFrames >= 2
            }

            const canShow = geometryReady && visible
                         && root.parentWindow.visible && !root.overlaysVisible
                         && !workspaceDisplayPicker.popupVisible
            root.controller.updateScrcpyGeometry(
                        geometry.x, geometry.y,
                        geometry.width, geometry.height, canShow)
        }

        Column {
            anchors.centerIn: parent
            spacing: Theme.space12
            MaterialIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                icon: root.controller.running ? "cast_connected" : "cast"
                iconSize: 54
                color: Theme.consoleMuted
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.controller.running
                      ? "正在连接设备并准备投屏…"
                      : "点击“开始投屏”，设备画面将在此处显示"
                color: Theme.consoleText
                font.pixelSize: Theme.fontBody
            }
        }

        Timer {
            interval: 16
            repeat: true
            running: scrcpyHost.visible
            onTriggered: scrcpyHost.syncGeometry()
        }
        onVisibleChanged: {
            if (visible)
                hideUntilLayoutSettles()
            else
                root.controller.updateScrcpyGeometry(0, 0, 0, 0, false)
        }
        Component.onCompleted: hideUntilLayoutSettles()
    }

    PrimaryButton {
        visible: root.scrcpySelected && !root.actionsInTitleBar
        Layout.alignment: Qt.AlignRight
        Layout.preferredWidth: 168
        Layout.preferredHeight: 40
        enabled: root.controller.running
                 || deviceSelector.deviceState.available
        text: root.controller.running ? "结束投屏" : "开始投屏"
        iconName: root.controller.running ? "stop" : "cast_connected"
        dangerStyle: root.controller.running
        onClicked: {
            if (root.controller.running)
                root.controller.stopExecution()
            else
                root.controller.runSelected({})
        }
    }

    DesktopScrollView {
        id: commandParameterScroll
        visible: !root.scrcpySelected
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ParameterForm {
            id: parameterFlow
            width: commandParameterScroll.availableWidth
            parameters: root.controller.selectedTool.parameters || []
            controller: root.controller
            parameterValues: root.parameterValues
            inlineLabels: false
        }
    }
}
