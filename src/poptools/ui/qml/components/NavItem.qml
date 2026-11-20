import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "../theme"

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    clip: true
    required property string label
    required property string iconName
    property string shortcutText: ""
    property bool selected: false
    property bool compact: false
    property bool dense: false
    signal clicked()

    implicitHeight: compact ? Theme.navigationItemHeight : (dense ? Theme.controlHeightLarge : 52)

    Rectangle {
        anchors.fill: parent
        anchors.margins: root.compact ? Theme.navigationItemInset : 0
        radius: root.compact ? Theme.radiusSmall : Theme.radiusMedium
        color: root.selected ? _visualPalette.navigationSelected
                             : (mouseArea.containsMouse ? _visualPalette.navigationHover : "transparent")
    }

    RowLayout {
        z: 1
        anchors.fill: parent
        anchors.leftMargin: root.compact ? 0 : Theme.space16
        anchors.rightMargin: root.compact ? 0 : Theme.space12
        spacing: root.compact ? 0 : Theme.space12

        Item { visible: root.compact; Layout.fillWidth: true }
        MaterialIcon {
            icon: root.iconName
            iconSize: root.compact ? _visualPalette.navigationIconSize : 21
            color: root.selected ? (_visualPalette.navigationActiveIcon)
                                 : (_visualPalette.navigationIcon)
            Layout.preferredWidth: root.compact ? _visualPalette.navigationIconSize : 24
            Layout.preferredHeight: root.compact ? _visualPalette.navigationIconSize : 32
            Layout.alignment: Qt.AlignHCenter | Qt.AlignVCenter
        }
        Text {
            visible: !root.compact
            text: root.label
            color: root.selected ? _visualPalette.primary : _visualPalette.textPrimary
            font.pixelSize: Theme.fontComponentTitle
            font.weight: root.selected ? Font.Bold : Font.Medium
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            elide: Text.ElideRight
        }
        Item { visible: root.compact; Layout.fillWidth: true }
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
