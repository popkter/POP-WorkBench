import QtQuick
import "../theme"

Rectangle {
    id: root
    property string cardTitle: ""
    property string cardIcon: "terminal"
    property rect packVisibleRect: Qt.rect(0, 0, 0, 0)
    property real packViewportTop: NaN
    property real packViewportBottom: NaN
    property rect packPort: Qt.rect(0, 0, 0, 0)
    property rect packPortOrigin: Qt.rect(0, 0, 0, 0)
    readonly property color accent: "#F12786"
    radius: Theme.radiusMedium
    color: "#101118"
    border.color: "#45434D"
    border.width: 1
    clip: true
    function attachTo(host) {
        parent = host
        x = 0; y = 0; rotation = 0; scale = 1
        width = Qt.binding(function() { return host.width })
        height = Qt.binding(function() { return host.height })
        visible = true
    }

    // One design coordinate system keeps the pack face and flying face identical.
    Item {
        width: 432
        height: root.height / scale
        scale: root.width > 0 ? root.width / width : 1
        transformOrigin: Item.TopLeft
        Rectangle {
            x: 0; width: 7; height: parent.height
            color: root.accent
        }
        Row {
            x: 18; y: 12; spacing: 3
            Repeater {
                model: 13
                Rectangle {
                    required property int index
                    width: index % 3 === 0 ? 5 : 2
                    height: 10
                    color: index % 4 === 0 ? root.accent : "#D9DAE1"
                }
            }
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 24
            y: 12; text: "READY"
            color: "#A9ABB8"; font.pixelSize: 11; font.letterSpacing: 2
        }
        Text {
            x: 18; y: 38; width: parent.width - 36
            text: root.cardTitle
            color: "#FFFFFF"; font.pixelSize: 22; font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        Rectangle {
            anchors.centerIn: parent
            width: 116; height: 116; radius: 20
            rotation: 45
            color: "#22131F"; border.color: root.accent; border.width: 2
        }
        MaterialIcon {
            anchors.centerIn: parent
            icon: root.cardIcon; iconSize: 54; color: "#FFFFFF"
        }
        Column {
            anchors.left: parent.left; anchors.right: parent.right
            anchors.margins: 28
            y: parent.height * 0.70
            spacing: 12
            Text {
                width: parent.width
                text: root.cardTitle
                color: "#FFFFFF"; font.pixelSize: 22; font.weight: Font.Bold
                elide: Text.ElideRight
            }
            Text {
                text: "SCRIPT / ACCESS"
                color: root.accent; font.pixelSize: 11; font.letterSpacing: 3
            }
            Rectangle { width: parent.width; height: 1; color: "#46404C" }
        }
    }
}
