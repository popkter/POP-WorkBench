import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root

    required property var controller
    property string victimTitle: ""
    property string requestedTitle: ""

    width: Math.min(560, parent ? parent.width - 24 : 560)
    height: Math.min(310, parent ? parent.height - 24 : 310)
    anchors.centerIn: Overlay.overlay
    modal: true
    closePolicy: Popup.NoAutoClose
    Connections {
        target: root.controller
        function onExecutionCapacityRequested(victimTitle, requestedTitle) {
            root.victimTitle = victimTitle
            root.requestedTitle = requestedTitle
            root.open()
        }
    }

    contentItem: ColumnLayout {
        spacing: Theme.space16

        DialogHeading {
            Layout.fillWidth: true
            title: "运行名额已用完"
            description: "停止一个正在运行的任务后可继续"
            iconName: "swap_horiz"
        }
        DialogMessage {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 32
            text: "是否停止最先运行的“" + root.victimTitle
                  + "”，并开始“" + root.requestedTitle + "”？"
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            Item { Layout.fillWidth: true }
            DialogActionButton {
                implicitWidth: 110
                implicitHeight: Theme.controlHeight
                text: "取消"
                iconName: "close"
                tonal: true
                onClicked: {
                    root.controller.cancelExecutionReplacement()
                    root.close()
                }
            }
            DialogActionButton {
                implicitWidth: 150
                implicitHeight: Theme.controlHeight
                text: "停止并运行"
                primaryAction: true
                iconName: "play_arrow"
                onClicked: {
                    root.controller.confirmExecutionReplacement()
                    root.close()
                }
            }
        }
    }
}
