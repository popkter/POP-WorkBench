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
                RowLayout {
                    id: pluginHeader
                    Layout.fillWidth: true
                    spacing: Theme.space8
                    Text {
                        Layout.preferredWidth: implicitWidth
                        Layout.maximumWidth: Math.max(0, pluginContent.width
                            - (installedBadge.visible ? installedBadge.implicitWidth + Theme.space8 : 0)
                            - (latestLabel.visible ? Math.min(latestLabel.implicitWidth,
                                140, pluginContent.width * 0.3) + Theme.space8 : 0)
                            - Theme.space8)
                        Layout.minimumWidth: 0
                        text: modelData.name + (modelData.version ? "  " + modelData.version : "")
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSupporting
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                    }
                    Rectangle {
                        id: installedBadge
                        visible: modelData.installed
                        implicitWidth: installedLabel.implicitWidth + Theme.space12
                        implicitHeight: installedLabel.implicitHeight + Theme.space4
                        radius: Theme.radiusTiny
                        color: Theme.successContainer
                        Text {
                            id: installedLabel
                            anchors.centerIn: parent
                            text: "已安装"
                            color: Theme.success
                            font.pixelSize: Theme.fontCaption
                        }
                    }
                    Text {
                        id: latestLabel
                        visible: !!modelData.latest
                        Layout.preferredWidth: implicitWidth
                        Layout.maximumWidth: Math.min(140, pluginContent.width * 0.3)
                        Layout.minimumWidth: 0
                        text: modelData.latest ? "最新 " + modelData.latest : ""
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontCaption
                        elide: Text.ElideRight
                    }
                    Item { Layout.fillWidth: true }
                }
                Text {
                    Layout.fillWidth: true
                    text: modelData.path || ""
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                    elide: Text.ElideMiddle
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: (modelData.status === "已安装" ? "" : modelData.status)
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
                        objectName: "configureRuntime_" + modelData.id
                        implicitWidth: 100
                        enabled: !modelData.busy
                        text: modelData.managed ? "应用管理" : "本地环境"
                        onClicked: runtimeDialog.configure(modelData)
                    }
                    PluginAction {
                        implicitWidth: 68; tonal: false
                        visible: modelData.managed && !modelData.installed; enabled: !modelData.busy
                        text: "安装"
                        onClicked: root.backend.operate(modelData.id, "install")
                    }
                    PluginAction {
                        implicitWidth: 88
                        visible: modelData.managed
                        enabled: !modelData.busy; tonal: true
                        text: "检查更新"
                        onClicked: root.backend.operate(modelData.id, "check")
                    }
                    PluginAction {
                        implicitWidth: 68; tonal: false
                        visible: modelData.managed && modelData.installed && modelData.canUpdate; enabled: !modelData.busy
                        text: "更新"
                        onClicked: root.backend.operate(modelData.id, "update")
                    }
                    PluginAction {
                        implicitWidth: 68
                        visible: modelData.managed && modelData.recorded; enabled: !modelData.busy; tonal: true
                        text: "修复"
                        onClicked: root.backend.operate(modelData.id, "repair")
                    }
                    PluginAction {
                        implicitWidth: 68
                        visible: modelData.managed && modelData.recorded; enabled: !modelData.busy; tonal: true
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
                        visible: modelData.managed && modelData.id === "android" && modelData.installed
                        enabled: !modelData.busy; tonal: true
                        text: "停止设备服务"
                        onClicked: root.backend.operate(modelData.id, "stop-server")
                    }
                }
            }
        }
    }
    RuntimeEnvironmentDialog { id: runtimeDialog; backend: root.backend }
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
