import QtQuick
import QtQuick.Layouts
import "../theme"

RowLayout {
    id: root
    property string title: ""
    property string description: ""
    property string iconName: "info"
    property bool destructive: false
    spacing: Theme.space12

    Rectangle {
        Layout.alignment: Qt.AlignTop
        Layout.preferredWidth: Theme.controlHeight
        Layout.preferredHeight: Theme.controlHeight
        radius: Theme.radiusMedium
        color: root.destructive ? Theme.errorContainer : Theme.primaryContainer
        MaterialIcon {
            anchors.centerIn: parent
            icon: root.iconName
            iconSize: 22
            color: root.destructive ? Theme.errorColor : Theme.primaryText
        }
    }
    ColumnLayout {
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        spacing: Theme.space4
        Text {
            id: titleText
            Layout.fillWidth: true
            text: root.title
            textFormat: Text.PlainText
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSectionTitle
            font.weight: Font.DemiBold
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            HoverTips { visible: titleMouse.containsMouse && titleText.truncated; text: root.title }
            MouseArea { id: titleMouse; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
        Text {
            id: descriptionText
            Layout.fillWidth: true
            visible: root.description.length > 0
            text: root.description
            textFormat: Text.PlainText
            color: Theme.textSecondary
            font.pixelSize: Theme.fontSupporting
            wrapMode: Text.Wrap
            maximumLineCount: 3
            elide: Text.ElideRight
            HoverTips { visible: descriptionMouse.containsMouse && descriptionText.truncated; text: root.description }
            MouseArea { id: descriptionMouse; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
        }
    }
}
