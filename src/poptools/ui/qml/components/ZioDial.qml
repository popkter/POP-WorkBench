import QtQuick
import QtQuick.Shapes
import "../theme"

// Shared ZIO dial, with hands following the computer's local time.
Item {
    id: root
    property bool highlighted: false
    property date currentTime: new Date()
    property bool followClock: true
    readonly property real hourAngle: (currentTime.getHours() % 12
        + currentTime.getMinutes() / 60 + currentTime.getSeconds() / 3600) * 30
    readonly property real minuteAngle: (currentTime.getMinutes() + currentTime.getSeconds() / 60) * 6
    readonly property real secondAngle: currentTime.getSeconds() * 6
    property color accent: Theme.zioPalette.primary || "#D9AE48"
    property color faceColor: Theme.zioPalette.decadeCardBackFill || "#211C11"
    implicitWidth: 48
    implicitHeight: 48
    readonly property real diameter: Math.min(width, height)
    onVisibleChanged: if (visible && followClock) currentTime = new Date()
    Timer {
        interval: 1000; repeat: true
        running: root.visible && root.followClock
        onTriggered: root.currentTime = new Date()
    }
    Rectangle {
        anchors.centerIn: parent
        width: root.diameter; height: width; radius: width / 2
        gradient: Gradient {
            GradientStop { position: 0; color: Qt.lighter(root.accent, root.highlighted ? 1.65 : 1.3) }
            GradientStop { position: 0.5; color: Qt.darker(root.accent, 1.6) }
            GradientStop { position: 1; color: root.accent }
        }
        Rectangle {
            anchors.fill: parent
            anchors.margins: parent.width * 0.07
            radius: width / 2
            color: root.highlighted ? Qt.lighter(root.faceColor, 1.7) : root.faceColor
            border.color: Qt.lighter(root.accent, 1.35)
            border.width: Math.max(0.6, root.diameter * 0.018)
            Repeater {
                model: 12
                Item {
                    required property int index
                    anchors.fill: parent
                    rotation: index * 30
                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: root.diameter * 0.045
                        width: root.diameter * (parent.index % 3 === 0 ? 0.045 : 0.025)
                        height: root.diameter * (parent.index % 3 === 0 ? 0.11 : 0.065)
                        color: Qt.lighter(root.accent, 1.25)
                    }
                }
            }
            Item {
                anchors.centerIn: parent
                width: 100; height: 100
                scale: root.diameter / 130
                Shape {
                    anchors.fill: parent
                    opacity: 0.4
                    preferredRendererType: Shape.CurveRenderer
                    ShapePath {
                        strokeColor: Qt.lighter(root.accent, 1.3)
                        strokeWidth: 1.5
                        fillColor: root.accent
                        startX: 15; startY: 28
                        PathLine { x: 43; y: 37 }
                        PathLine { x: 48; y: 57 }
                        PathLine { x: 22; y: 48 }
                        PathLine { x: 15; y: 28 }
                    }
                    ShapePath {
                        strokeColor: Qt.lighter(root.accent, 1.3)
                        strokeWidth: 1.5
                        fillColor: root.accent
                        startX: 85; startY: 28
                        PathLine { x: 57; y: 37 }
                        PathLine { x: 52; y: 57 }
                        PathLine { x: 78; y: 48 }
                        PathLine { x: 85; y: 28 }
                    }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 61
                    text: "ZI-O"
                    color: Qt.lighter(root.accent, 1.5)
                    font.pixelSize: 19
                    font.weight: Font.Bold
                    font.letterSpacing: 1
                }
            }
            Item {
                anchors.fill: parent
                rotation: root.hourAngle
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: parent.height * 0.25
                    width: Math.max(1.5, root.diameter * 0.055)
                    height: parent.height * 0.25
                    radius: width / 2
                    color: Qt.lighter(root.accent, 1.65)
                }
            }
            Item {
                anchors.fill: parent
                rotation: root.minuteAngle
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: parent.height * 0.13
                    width: Math.max(1, root.diameter * 0.035)
                    height: parent.height * 0.37
                    radius: width / 2
                    color: Qt.lighter(root.accent, 1.65)
                }
            }
            Item {
                anchors.fill: parent
                rotation: root.secondAngle
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: parent.height * 0.13
                    width: Math.max(0.6, root.diameter * 0.015)
                    height: parent.height * 0.47
                    color: root.accent
                }
            }
            Rectangle {
                anchors.centerIn: parent
                width: root.diameter * 0.09; height: width; radius: width / 2
                color: Qt.lighter(root.accent, 1.8)
            }
        }
    }
}
