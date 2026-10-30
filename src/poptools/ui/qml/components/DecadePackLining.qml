import QtQuick
import "../theme"

// Mechanical cover interior: inset window, diagonal brace, and outer control rail.
Item {
    id: root
    property bool searching: false
    DecadePackShell {
        anchors.fill: parent
        fillColor: "#181B20"
        edgeColor: "#62666D"
        transform: Scale { origin.x: root.width / 2; xScale: -1 }
    }
    Rectangle {
        x: 16; y: 28
        width: Math.max(1, parent.width - 72)
        height: parent.height - 56
        radius: 3
        color: "#0A0C0F"
        border.width: 3
        border.color: "#30343A"
        Rectangle {
            anchors.fill: parent; anchors.margins: 8
            color: "#101318"
            border.color: "#21252B"
            Rectangle {
                visible: !root.searching
                anchors.centerIn: parent
                width: parent.width * 0.4; height: parent.height * 0.52
                color: "#15191F"; border.color: "#383D45"
                rotation: -14
                Rectangle {
                    x: 4; y: 8; width: parent.width - 8; height: 7
                    color: Theme.primary
                }
            }
        }
    }
    Rectangle {
        visible: !root.searching
        x: 18; y: root.height * 0.45
        width: root.width - 74; height: 24
        color: "#24282E"; border.color: "#434850"
        rotation: -33
    }
    Rectangle {
        x: 16; y: 28
        width: Math.max(1, parent.width - 72); height: 54
        color: "#191E25"
        border.color: "#3C444F"
        radius: 1
        Rectangle {
            x: 4; y: 3; width: parent.width - 8; height: 1
            color: "#68717D"; opacity: 0.4
        }
        Repeater {
            model: 2
            Rectangle {
                required property int index
                x: index === 0 ? 1 : parent.width - 3
                y: 26; width: 2; height: 2
                color: "#67717D"
            }
        }
    }
    Rectangle {
        anchors.right: parent.right; anchors.rightMargin: 9
        y: 20; width: 38; height: parent.height - 40
        color: "#191E25"; border.color: "#3C444F"; radius: 1
        Rectangle {
            anchors.fill: parent; anchors.margins: 3
            color: "#0C0F13"; border.color: "#252C35"; radius: 1
        }
        Repeater {
            model: 2
            Rectangle {
                required property int index
                x: 16; y: index === 0 ? 8 : parent.height - 13
                width: 5; height: 5; radius: 2
                color: "#272D35"; border.color: "#59616C"
                Rectangle {
                    anchors.centerIn: parent
                    width: 3; height: 1; color: "#080B0F"; rotation: -35
                }
            }
        }
    }
}
