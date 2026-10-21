import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ColumnLayout {
    id: root
    required property var controller
    required property var androidController
    required property string toolId
    property string statusMessage: ""
    property bool statusError: false
    property bool actionsInTitleBar: false
    readonly property var deviceState: root.androidController
        ? root.androidController.selectedAndroidDevice
        : ({ serial: "", available: false, label: "未检测到 Android 设备" })
    spacing: Theme.space20

    DeviceSelector {
        id: deviceSelector
        visible: !root.actionsInTitleBar
        Layout.fillWidth: true
        controller: root.androidController
        toolId: root.toolId
        requiredDevice: true
        enabled: !root.controller.recording && !root.controller.exporting
    }

    function openSaveDialog() {
        root.controller.chooseRecordingDirectory()
    }

    Connections {
        target: root.controller
        function onRecordingError(message) {
            root.statusMessage = message
            root.statusError = true
        }
        function onRecordingSaved(folder) {
            root.statusMessage = "已保存到：" + folder
            root.statusError = false
        }
    }

    Item { Layout.fillHeight: true }
    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 190
        radius: Theme.radiusLarge
        color: Theme.surfaceContainerLow
        border.color: Theme.outlineVariant

        ColumnLayout {
            anchors.centerIn: parent
            spacing: Theme.space12
            MaterialIcon {
                Layout.alignment: Qt.AlignHCenter
                icon: root.controller.recording ? "radio_button_checked" : "videocam"
                iconSize: 54
                color: root.controller.recording ? Theme.errorColor : Theme.primary
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: root.controller.recording
                    ? "正在录制画面、系统声音、麦克风并截取日志…"
                    : "录制设备画面、系统声音和麦克风，同时保存 logcat 日志"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontComponentTitle
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: root.deviceState.label
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSupporting
            }
        }
    }
    Text {
        Layout.fillWidth: true
        text: root.controller.recording
              ? "点击“结束记录”后自动导出到所选目录，生成时间戳文件夹"
              : "需要 Android 11+；音频不可用时仅录制画面"
        color: Theme.textSecondary
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }
    AppTextField {
        id: recordingDirectoryField
        Layout.fillWidth: true
        Layout.leftMargin: Theme.space40
        Layout.rightMargin: Theme.space40
        Layout.preferredHeight: 40
        enabled: !root.controller.recording && !root.controller.exporting
        placeholderText: "请选择录制保存目录"
        color: Theme.textPrimary
        font.pixelSize: Theme.fontBody
        leftPadding: 13
        rightPadding: 45
        background: Rectangle {
            radius: Theme.radiusSmall
            color: Theme.surfaceContainerLow
            border.color: parent.activeFocus ? Theme.primary : "#A8CFFF"
            border.width: parent.activeFocus ? 2 : 1
        }
        Component.onCompleted: text = root.controller.recordingOutputDirectory
        onTextChanged: {
            if (text !== root.controller.recordingOutputDirectory)
                root.controller.setRecordingOutputDirectory(text)
        }
        FilePathDropArea { target: recordingDirectoryField }
        AppTextEditMenu { target: recordingDirectoryField }

        PrimaryButton {
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            width: 30
            height: 30
            compact: true
            text: "选择目录"
            iconName: "folder_open"
            glyphSize: 19
            tonal: true
            foregroundColor: Theme.primaryText
            border.width: 0
            radius: Theme.radiusControl
            z: 201
            color: hovered ? Theme.primaryContainerHover : Theme.primaryContainer
            onClicked: root.controller.chooseRecordingOutputDirectory()
        }
    }
    Connections {
        target: root.controller
        function onRecordingOutputDirectoryChanged() {
            if (recordingDirectoryField.activeFocus)
                return
            const p = root.controller.recordingOutputDirectory
            if (recordingDirectoryField.text !== p)
                recordingDirectoryField.text = p
        }
    }
    PrimaryButton {
        visible: !root.actionsInTitleBar
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: 168
        Layout.preferredHeight: 40
        enabled: !root.controller.exporting
                 && (root.controller.recording
                     || (root.deviceState.available
                         && root.controller.recordingOutputDirectory.length > 0))
        text: root.controller.exporting
              ? "正在导出"
              : (root.controller.recording ? "结束记录" : "开始记录")
        iconName: root.controller.exporting
                  ? "hourglass_top"
                  : (root.controller.recording ? "stop" : "fiber_manual_record")
        successStyle: root.controller.recording && !root.controller.exporting
        onClicked: {
            if (root.controller.recording)
                root.controller.stopRecording()
            else
                root.controller.startRecording(root.deviceState.serial)
        }
    }
    Text {
        Layout.fillWidth: true
        visible: root.statusMessage.length > 0
        text: root.statusMessage
        color: root.statusError ? Theme.errorColor : Theme.success
        horizontalAlignment: Text.AlignHCenter
        wrapMode: Text.WordWrap
    }
    Item { Layout.fillHeight: true }
}
