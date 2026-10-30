import QtQuick
import "../theme"

Item {
    id: root
    DecadePackShell { anchors.fill: parent }
    Rectangle {
        x: parent.width * 0.87; y: 4
        width: Math.max(3, parent.width * 0.035); height: parent.height - 8
        color: "#35393F"
    }
    Rectangle {
        x: parent.width * 0.81; y: 4
        width: 2; height: parent.height - 8
        color: "#080A0D"
    }
    Item {
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: -parent.width * 0.04
        width: parent.width * 0.65
        height: width * 0.95
        Rectangle {
            anchors.fill: parent
            color: "#0A0C10"
            border.color: "#43474F"
            border.width: Math.max(1, root.width / 180)
        }
        Text {
            anchors.centerIn: parent
            text: "DCD"
            color: "#62666F"
            font.pixelSize: parent.width * 0.18
            font.weight: Font.Black
            font.italic: true
        }
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            y: parent.height * 0.1
            spacing: Math.max(1, root.width / 120)
            Repeater {
                model: 13
                Rectangle {
                    required property int index
                    width: Math.max(1, root.width / 150) * (index % 3 === 0 ? 3 : 1)
                    height: root.width * 0.055
                    color: index % 4 === 0 ? Theme.primary : "#D8CFD8"
                }
            }
        }
        Rectangle {
            anchors.centerIn: parent
            width: parent.width * 1.05
            height: parent.height * 0.18
            rotation: -37
            color: "#282C32"
            border.color: "#454A53"
        }
    }
    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: parent.height * 0.1
        text: "DECADE"
        color: "#D7C4D1"
        font.pixelSize: Math.max(7, parent.width * 0.045)
        font.letterSpacing: parent.width * 0.009
        font.weight: Font.Bold
    }
}
