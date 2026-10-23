import QtQuick
import QtQuick.Shapes
import "../theme"

// Ride Booker silhouette: silver blade, magenta spine and angular crossguard.
Item {
    id: root
    objectName: "decadeSwordScrollHandle"
    property bool highlighted: false
    readonly property color accent: highlighted ? Theme.primaryHover : Theme.primary
    readonly property real bladeBottom: Math.max(12, height - 24)
    implicitWidth: 14
    implicitHeight: 72

    Shape {
        anchors.fill: parent
        ShapePath {
            strokeWidth: 0
            fillColor: root.highlighted ? "#FFFFFF" : "#CEC9D2"
            startX: 7; startY: 0
            PathLine { x: 11; y: 9 }
            PathLine { x: 10; y: root.bladeBottom }
            PathLine { x: 4; y: root.bladeBottom }
            PathLine { x: 3; y: 9 }
            PathLine { x: 7; y: 0 }
        }
        ShapePath {
            strokeWidth: 0
            fillColor: root.accent
            startX: 7; startY: 6
            PathLine { x: 8; y: 10 }
            PathLine { x: 8; y: root.bladeBottom }
            PathLine { x: 6; y: root.bladeBottom }
            PathLine { x: 6; y: 10 }
            PathLine { x: 7; y: 6 }
        }
        ShapePath {
            strokeWidth: 0
            fillColor: root.accent
            startX: 0; startY: root.bladeBottom - 2
            PathLine { x: 5; y: root.bladeBottom + 1 }
            PathLine { x: 9; y: root.bladeBottom + 1 }
            PathLine { x: 14; y: root.bladeBottom - 2 }
            PathLine { x: 14; y: root.bladeBottom + 5 }
            PathLine { x: 9; y: root.bladeBottom + 7 }
            PathLine { x: 5; y: root.bladeBottom + 7 }
            PathLine { x: 0; y: root.bladeBottom + 5 }
            PathLine { x: 0; y: root.bladeBottom - 2 }
        }
    }
    Rectangle {
        x: 5; y: root.bladeBottom + 7
        width: 4; height: 13
        color: "#24212A"
        border.width: 1
        border.color: "#827588"
        Repeater {
            model: 2
            Rectangle {
                required property int index
                x: 1; y: 4 + index * 4
                width: 2; height: 1
                color: "#CEC9D2"
            }
        }
    }
    Rectangle {
        x: 4; y: root.height - 4
        width: 6; height: 4
        color: root.accent
    }
}
