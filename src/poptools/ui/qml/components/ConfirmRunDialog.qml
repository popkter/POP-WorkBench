import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root
    required property var controller
    required property var parentWindow
    property var pendingValues: ({})
    width: Math.min(Theme.dialogWidth, parentWindow.width - 24)
    height: Math.min(body.implicitHeight + topPadding + bottomPadding, parentWindow.height - 24)
    closePolicy: Popup.CloseOnEscape
    function openForRun(values) { pendingValues = Object.assign({}, values); open() }
    contentItem: ColumnLayout {
        id: body
        spacing: Theme.space16
        DialogHeading {
            Layout.fillWidth: true
            title: "运行“" + (root.controller.selectedTool.title || "当前脚本") + "”？"
            description: "运行前请确认目标设备与输入参数。"
            iconName: "play_arrow"
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.space8
            Item { Layout.fillWidth: true }
            DialogActionButton { text: "取消"; onClicked: root.close() }
            DialogActionButton {
                implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: "继续运行"; iconName: ""
                primaryAction: true
                onClicked: { root.close(); root.controller.runSelected(root.pendingValues) }
            }
        }
    }
}
