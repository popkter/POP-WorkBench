import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root
    required property var controller
    required property var parentWindow
    property bool cancelRequested: false
    width: Math.min(Theme.dialogWidth, Overlay.overlay.width - 24)
    height: Math.min(Math.max(321, body.implicitHeight + 48), Overlay.overlay.height - 24)
    closePolicy: controller.pluginInstalling ? Popup.NoAutoClose : Popup.CloseOnEscape

    function cancel() {
        if (!controller.pluginInstalling) { close(); return }
        if (!cancelRequested && controller.cancelPowerShellPluginInstall())
            cancelRequested = true
    }
    onOpened: cancelRequested = false
    onClosed: cancelRequested = false
    Connections {
        target: root.controller
        function onPluginInstallFinished(success, message) {
            if (root.cancelRequested) { root.cancelRequested = false; root.close() }
        }
    }
    contentItem: ColumnLayout {
        id: body
        spacing: Theme.space16
        DialogHeading {
            Layout.fillWidth: true
            title: root.controller.pluginInstalled ? "PowerShell 7" : "安装 PowerShell 7"
            description: "安装后可运行对应脚本"
            iconName: "terminal"
        }
        Rectangle {
            Layout.fillWidth: true; Layout.preferredHeight: Theme.controlHeightLarge
            radius: Theme.radiusControl; color: Theme.surfaceContainer; border.color: Theme.outlineVariant
            Text { anchors.left: parent.left; anchors.leftMargin: Theme.space16; anchors.verticalCenter: parent.verticalCenter; text: root.controller.pluginVersion; color: Theme.textPrimary; font.pixelSize: Theme.fontBody }
        }
        DialogMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 32
            text: root.controller.pluginInstallStatus || (root.controller.pluginInstalled ? "已安装" : "将下载应用专用的官方运行环境")
            foregroundColor: text.indexOf("失败") >= 0 ? Theme.errorColor : Theme.textSecondary
        }
        AppProgressBar {
            id: progressBar
            Layout.fillWidth: true; Layout.preferredHeight: 6
            visible: root.controller.pluginInstalling
            from: 0; to: 100; value: root.controller.pluginInstallProgress
        }
        Text {
            Layout.fillWidth: true
            text: root.controller.pluginDirectory
            color: Theme.textSecondary; font.pixelSize: Theme.fontCaption
            elide: Text.ElideMiddle
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.space8
            Item { Layout.fillWidth: true }
            DialogActionButton {
                implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: root.controller.pluginInstalling ? "取消安装" : "关闭"; iconName: ""; tonal: true
                enabled: !root.cancelRequested; onClicked: root.cancel()
            }
            DialogActionButton {
                implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: root.controller.pluginInstalling ? "安装中…" : root.controller.pluginInstalled ? "已安装" : "安装使用"; iconName: ""
                primaryAction: true
                enabled: !root.controller.pluginInstalling && !root.controller.pluginInstalled
                onClicked: root.controller.installPowerShellPlugin()
            }
        }
    }
}
