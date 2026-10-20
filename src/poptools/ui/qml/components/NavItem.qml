import QtQuick
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    clip: true
    required property string label
    required property string iconName
    property string shortcutText: ""
    property bool selected: false
    property bool compact: false
    property bool dense: false
    property string actionText: ""
    property string actionIconName: "system_update"
    signal clicked()
    signal actionClicked()

    implicitHeight: compact ? Theme.navigationItemHeight : (dense ? Theme.controlHeightLarge : 52)

    Rectangle {
        anchors.fill: parent
        anchors.margins: root.compact ? Theme.navigationItemInset : 0
        radius: root.compact ? Theme.radiusSmall : Theme.radiusMedium
        color: root.selected ? Theme.navigationSelected
                             : (mouseArea.containsMouse ? Theme.navigationHover : "transparent")
    }

    RowLayout {
        z: 1
        anchors.fill: parent
        anchors.leftMargin: root.compact ? 0 : Theme.space16
        anchors.rightMargin: root.actionText.length > 0
                             ? (root.compact ? 0 : actionButton.width + Theme.pagePadding)
                             : (root.compact ? 0 : Theme.space12)
        spacing: root.compact ? 0 : Theme.space12

        Item { visible: root.compact; Layout.fillWidth: true }
        MaterialIcon {
            icon: root.iconName
            iconSize: root.compact ? Theme.navigationIconSize : 21
            color: root.selected ? (Theme.navigationActiveIcon)
                                 : (Theme.navigationIcon)
            Layout.preferredWidth: root.compact ? Theme.navigationIconSize : 24
            Layout.preferredHeight: root.compact ? Theme.navigationIconSize : 32
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
        }
        Text {
            visible: !root.compact
            text: root.label
            color: root.selected ? Theme.primary : Theme.textPrimary
            font.pixelSize: Theme.fontComponentTitle
            font.weight: root.selected ? Font.Bold : Font.Medium
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            elide: Text.ElideRight
        }
        Item { visible: root.compact; Layout.fillWidth: true }
    }

    Rectangle {
        id: actionButton
        z: 2
        visible: root.actionText.length > 0
        anchors.right: parent.right
        anchors.rightMargin: root.compact ? Theme.space4 : Theme.space12
        anchors.verticalCenter: parent.verticalCenter
        width: root.compact ? 28 : actionLabel.implicitWidth + 18
        height: root.compact ? 28 : 34
        radius: height / 2
        color: actionMouse.containsMouse
               ? Theme.primaryContainerHover : Theme.primaryContainer

        MaterialIcon {
            visible: root.compact
            anchors.centerIn: parent
            icon: root.actionIconName
            iconSize: 17
            color: Theme.primaryText
        }
        Text {
            id: actionLabel
            visible: !root.compact
            anchors.centerIn: parent
            text: root.actionText
            color: Theme.primaryText
            font.pixelSize: Theme.fontCaption
            font.weight: Font.DemiBold
        }
        HoverTips {
            visible: root.compact && actionMouse.containsMouse
            text: root.actionText
        }
        MouseArea {
            id: actionMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.actionClicked()
        }
    }

    HoverTips {
        visible: root.compact && mouseArea.containsMouse
        text: root.label + (root.shortcutText.length > 0 ? " (" + root.shortcutText + ")" : "")
    }

    MouseArea {
        id: mouseArea
        z: 0
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: root.clicked()
    }
}
