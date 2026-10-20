import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root

    required property var controller
    required property var parentWindow
    property bool replacementMode: false
    property string incomingTitle: ""
    property string existingTitle: ""
    property string errorMessage: ""
    signal scriptReplaced(string title)

    width: Math.min(Theme.dialogWidth, parentWindow.width - 24)
    height: Math.min(body.implicitHeight + topPadding + bottomPadding, parentWindow.height - 24)
    anchors.centerIn: Overlay.overlay
    modal: true
    closePolicy: Popup.CloseOnEscape
    function openForReplacement(result) {
        replacementMode = true
        incomingTitle = result.title || "导入的脚本"
        existingTitle = result.existingTitle || "现有脚本"
        errorMessage = ""
        open()
    }

    function openForError(message) {
        replacementMode = false
        incomingTitle = ""
        existingTitle = ""
        errorMessage = message
        open()
    }

    onClosed: root.controller.cancelScriptImportReplacement()

    contentItem: ColumnLayout {
        id: body
        spacing: Theme.space16

        DialogHeading {
            Layout.fillWidth: true
            title: root.replacementMode ? "替换现有脚本？" : "无法导入脚本"
            description: root.replacementMode ? "导入的脚本与本地脚本使用相同 ID" : "请检查脚本文件后重试"
            iconName: root.replacementMode ? "swap_horiz" : "error_outline"
            destructive: !root.replacementMode
        }
        DialogMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 32
            text: root.replacementMode
                  ? "导入的“" + root.incomingTitle + "”与现有脚本“"
                    + root.existingTitle + "”使用相同 ID。是否替换现有脚本？"
                  : root.errorMessage
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            Item { Layout.fillWidth: true }

            DialogActionButton {
                implicitHeight: Theme.controlHeight
                radius: Theme.radiusControl
                text: root.replacementMode ? "取消" : "关闭"
                iconName: ""
                tonal: true
                onClicked: root.close()
            }
            DialogActionButton {
                visible: root.replacementMode
                implicitHeight: Theme.controlHeight
                radius: Theme.radiusControl
                text: "确认替换"
                primaryAction: true
                iconName: ""
                onClicked: {
                    var result = root.controller.confirmScriptImportReplacement()
                    if (result.status === "error") {
                        root.openForError(result.message || "替换脚本失败")
                        return
                    }
                    root.scriptReplaced(result.title)
                    root.close()
                }
            }
        }
    }
}
