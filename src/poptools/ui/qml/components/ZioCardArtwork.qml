import QtQuick
import QtQuick.Shapes
import "../theme"

Item {
    id: root
    property bool backFace: false
    property string iconName: "terminal"
    readonly property real unit: width / 440
    opacity: backFace ? 1 : 0.24

    // Layered armour rails surround the clock and the engraved royal panels.
    Repeater {
        model: 3
        Rectangle {
            required property int index
            anchors.fill: parent
            anchors.margins: (9 + index * 7) * root.unit
            radius: (12 - index * 2) * root.unit
            color: "transparent"
            border.width: (index === 1 ? 3 : 1) * root.unit
            border.color: index === 1 ? Theme.primary : Theme.outline
        }
    }
    Item {
        id: clock
        width: root.width * 0.55
        height: width
        anchors.centerIn: parent
        Rectangle {
            anchors.fill: parent
            radius: width / 2
            color: Theme.decadeCardBackFill
            border.width: 4 * root.unit
            border.color: Theme.primary
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: 13 * root.unit
            radius: width / 2
            color: "transparent"
            border.width: root.unit
            border.color: Theme.primaryText
        }
        Repeater {
            model: 60
            Item {
                required property int index
                anchors.fill: parent
                rotation: index * 6
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 7 * root.unit
                    width: (parent.index % 5 === 0 ? 4 : 1.5) * root.unit
                    height: (parent.index % 5 === 0 ? 18 : 8) * root.unit
                    color: Theme.primaryText
                }
            }
        }
        MaterialIcon {
            anchors.centerIn: parent
            icon: root.iconName || "terminal"
            iconSize: clock.width * 0.35
            color: Theme.primaryText
        }
        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height * 0.2
            width: 3 * root.unit
            height: parent.height * 0.23
            color: Theme.primary
            rotation: -30
            transformOrigin: Item.Bottom
        }
    }
    Item {
        anchors.horizontalCenter: parent.horizontalCenter
        y: root.height * 0.13
        width: 100
        height: 60
        scale: root.width / 270
        transformOrigin: Item.Top
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Theme.primaryText
                strokeWidth: 2
                fillColor: Theme.primary
                startX: 8; startY: 48
                PathLine { x: 0; y: 14 }
                PathLine { x: 26; y: 30 }
                PathLine { x: 50; y: 0 }
                PathLine { x: 74; y: 30 }
                PathLine { x: 100; y: 14 }
                PathLine { x: 92; y: 48 }
                PathLine { x: 8; y: 48 }
            }
        }
        Rectangle { x: 10; y: 53; width: 80; height: 5; color: Theme.primaryText }
    }
    Repeater {
        model: 10
        Rectangle {
            required property int index
            x: index < 5 ? root.width * 0.07 : root.width * 0.83
            y: root.height * (0.27 + (index % 5) * 0.11)
            width: root.width * 0.10
            height: root.height * 0.075
            radius: 3 * root.unit
            color: Theme.primaryContainer
            border.color: Theme.primary
            border.width: root.unit
            Rectangle {
                anchors.centerIn: parent
                width: parent.width * 0.4
                height: width
                rotation: 45
                color: "transparent"
                border.color: Theme.primaryText
                border.width: root.unit
            }
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height * 0.78
        text: "GRAND ZI-O"
        color: Theme.primaryText
        font.pixelSize: 19 * root.unit
        font.letterSpacing: 5 * root.unit
        font.weight: Font.DemiBold
    }
}
