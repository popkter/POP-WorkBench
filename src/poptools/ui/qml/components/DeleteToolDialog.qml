import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root
    required property var controller
    required property var parentWindow
    width: Math.min(Theme.dialogWidth, parentWindow.width - 24)
    height: Math.min(body.implicitHeight + topPadding + bottomPadding, parentWindow.height - 24)
    closePolicy: Popup.CloseOnEscape
    contentItem: ColumnLayout {
        id: body
        spacing: Theme.space16
        DialogHeading {
            Layout.fillWidth: true
            title: "删除脚本？"
            iconName: "delete_outline"
            destructive: true
            description: "“" + (root.controller.selectedTool.title || "当前脚本") + "”将从本地删除，删除前会自动备份。"
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.space8
            Item { Layout.fillWidth: true }
            DialogActionButton {
                text: "取消"
                onClicked: root.close()
            }
            DialogActionButton {
                text: "删除"
                destructive: true
                onClicked: { if (root.controller.deleteSelected()) root.close() }
            }
        }
    }
}
