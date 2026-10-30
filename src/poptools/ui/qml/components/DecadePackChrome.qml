import QtQuick
import "../theme"

// The inner case stays still while the cover opens around its right-hand spine.
Item {
    id: root
    objectName: "decadePackChrome"
    DecadePackShell { anchors.fill: parent; fillColor: "#181A1E" }
    Rectangle {
        anchors.right: parent.right
        anchors.rightMargin: 7
        y: 4
        width: 5; height: Math.max(0, parent.height - 8)
        color: "#08090B"
    }
    Rectangle {
        x: 6
        y: 8; width: 3; height: Math.max(0, parent.height - 44)
        color: "#3B3E44"
    }
    Rectangle {
        x: 12; y: 24
        width: Math.max(0, parent.width - 26)
        height: Math.max(0, parent.height - 48)
        radius: 3
        color: Theme.decadePackSurface
        border.width: 1
        border.color: "#393C42"
    }
    Row {
        x: 18; y: 10; spacing: 3
        Repeater {
            model: 9
            Rectangle {
                required property int index
                width: index % 3 === 0 ? 3 : 1
                height: 6
                color: index % 3 === 0 ? Theme.primary : "#DDD2DC"
            }
        }
    }
    Text {
        anchors.right: parent.right
        anchors.rightMargin: 22
        y: 8
        text: "RIDE BOOKER"
        color: "#AB9AAA"
        font.pixelSize: 6
        font.letterSpacing: 2
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 8
        text: "DECADE"
        color: "#C4B5C0"
        font.pixelSize: 6
        font.letterSpacing: 2
        font.weight: Font.DemiBold
    }
}
