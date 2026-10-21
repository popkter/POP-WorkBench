import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ColumnLayout {
    id: root
    required property var backend
    spacing: Theme.space8

    component PluginAction: PrimaryButton {
        height: 30
        iconName: ""
        tonal: true
        radius: Theme.radiusControl
        border.width: 0
        labelFontSize: Theme.fontSupporting
        labelFontWeight: Font.Normal
        foregroundColor: tonal ? Theme.primaryText : Theme.primaryForeground
        color: tonal ? (hovered ? Theme.primaryContainerHover : Theme.runtimeBadge)
            : (hovered ? Theme.primaryHover : Theme.primary)
    }
    Repeater {
        model: root.backend ? root.backend.plugins : []
        delegate: Rectangle {
            required property var modelData
            Layout.fillWidth: true
            implicitHeight: pluginContent.implicitHeight + Theme.space24
            radius: Theme.radiusSmall
            color: Theme.surfaceContainerLow
            border.width: 1
            border.color: Theme.inputBorder

            ColumnLayout {
                id: pluginContent
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Theme.space12
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: modelData.name + (modelData.version ? "  " + modelData.version : "")
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSupporting
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    text: modelData.status + (modelData.latest ? " · 最新 " + modelData.latest : "")
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.Wrap
                }
                AppProgressBar {
                    Layout.fillWidth: true
                    visible: modelData.busy
                    value: modelData.progress / 100
                    indeterminate: modelData.progress === 0
                }
                Flow {
                    Layout.fillWidth: true
                    spacing: Theme.space8
                    PluginAction {
                        implicitWidth: 68; tonal: false
                        visible: !modelData.installed; enabled: !modelData.busy
                        text: "安装"
                        onClicked: root.backend.operate(modelData.id, "install")
                    }
                    PluginAction {
                        implicitWidth: 88
                        enabled: !modelData.busy; tonal: true
                        text: "检查更新"
                        onClicked: root.backend.operate(modelData.id, "check")
                    }
                    PluginAction {
                        implicitWidth: 68; tonal: false
                        visible: modelData.installed && modelData.canUpdate; enabled: !modelData.busy
                        text: "更新"
                        onClicked: root.backend.operate(modelData.id, "update")
                    }
                    PluginAction {
                        implicitWidth: 68
                        visible: modelData.recorded; enabled: !modelData.busy; tonal: true
                        text: "修复"
                        onClicked: root.backend.operate(modelData.id, "repair")
                    }
                    PluginAction {
                        implicitWidth: 68
                        visible: modelData.recorded; enabled: !modelData.busy; tonal: true
                        text: "卸载"
                        onClicked: { confirm.pluginId = modelData.id; confirm.pluginName = modelData.name; confirm.open() }
                    }
                    PluginAction {
                        implicitWidth: 68
                        visible: modelData.busy; tonal: true
                        text: "取消"
                        onClicked: root.backend.cancel(modelData.id)
                    }
                    PluginAction {
                        implicitWidth: 112
                        visible: modelData.id === "android" && modelData.installed
                        enabled: !modelData.busy; tonal: true
                        text: "停止设备服务"
                        onClicked: root.backend.operate(modelData.id, "stop-server")
                    }
                }
            }
        }
    }
    AppDialog {
        id: confirm
        objectName: "pluginUninstallDialog"
        property string pluginId: ""
        property string pluginName: ""
        parent: Overlay.overlay
        compactLayout: true
        width: Math.min(Theme.compactDialogWidth, parent.width - Theme.space24)
        height: Math.min(confirmBody.implicitHeight + topPadding + bottomPadding,
                         parent.height - Theme.space24)
        closePolicy: Popup.CloseOnEscape
        contentItem: ColumnLayout {
            id: confirmBody
            spacing: Theme.space12
            DialogHeading {
                Layout.fillWidth: true
                title: "卸载 " + confirm.pluginName + "？"
                iconName: "delete_outline"
                destructive: true
            }
            Text {
                Layout.fillWidth: true
                text: "卸载后相关功能将不可用。" + (confirm.pluginId === "python" ? "Python 环境及已安装依赖也会删除。" : "") + "用户脚本、配置和输出文件会保留。"
                color: Theme.textSecondary; font.pixelSize: Theme.fontBody
                wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.fillWidth: true; spacing: Theme.space8
                Item { Layout.fillWidth: true }
                DialogActionButton {
                    text: "取消"
                    onClicked: confirm.reject()
                }
                DialogActionButton {
                    objectName: "confirmPluginUninstall"
                    text: "卸载"; iconName: "delete_outline"
                    destructive: true
                    onClicked: confirm.accept()
                }
            }
        }
        onAccepted: root.backend.operate(pluginId, "uninstall")
    }
}
