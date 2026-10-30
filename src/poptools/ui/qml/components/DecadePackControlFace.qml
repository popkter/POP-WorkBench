import QtQuick
import "../theme"

// Recessed hardware key: a dark socket, beveled cap, and a small active indicator.
Item {
    id: root
    property bool selected: false
    property bool hovered: false
    property bool pressed: false
    Rectangle {
        anchors.fill: parent
        radius: 1
        color: "#080A0D"
        border.color: "#30353D"
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: root.pressed ? 3 : 2
        radius: 1
        color: root.pressed ? "#101318" : root.selected ? "#251B25"
            : root.hovered ? "#292E35" : "#1A1E24"
        border.color: root.selected ? "#79516B" : root.hovered ? "#59616D" : "#3B424C"
    }
    Rectangle {
        x: 4; y: 3
        width: Math.max(0, parent.width - 8); height: 1
        color: root.pressed ? "#171B21" : "#59616B"
        opacity: 0.55
    }
    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 4
        width: 7; height: 1
        color: root.selected ? Theme.primary : "#080A0D"
    }
}
