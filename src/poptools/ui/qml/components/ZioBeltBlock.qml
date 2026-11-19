import QtQuick
import QtQuick.Window
import QtQuick.Shapes
import "../theme"

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property bool highlighted: false
    property bool ribs: false
    property real bevel: 6
    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeWidth: 1
            strokeColor: root.highlighted ? _visualPalette.primaryText : LauncherStyle.decadePackRail
            fillColor: root.highlighted ? _visualPalette.primaryContainerHover : LauncherStyle.decadeCardBackFill
            startX: 1; startY: root.bevel
            PathLine { x: root.bevel; y: 1 }
            PathLine { x: root.width - root.bevel; y: 1 }
            PathLine { x: root.width - 1; y: root.bevel }
            PathLine { x: root.width - 1; y: root.height - root.bevel }
            PathLine { x: root.width - root.bevel; y: root.height - 1 }
            PathLine { x: root.bevel; y: root.height - 1 }
            PathLine { x: 1; y: root.height - root.bevel }
            PathLine { x: 1; y: root.bevel }
        }
    }
    Rectangle {
        x: 7; y: 4; width: parent.width - 14; height: 1
        color: _visualPalette.primaryText; opacity: 0.22
    }
    Rectangle {
        x: 7; y: parent.height - 5; width: parent.width - 14; height: 1
        color: _visualPalette.primary; opacity: 0.3
    }
    Row {
        visible: root.ribs
        anchors.centerIn: parent
        spacing: 3
        Repeater {
            model: 3
            Rectangle {
                width: 2; height: root.height * 0.42
                color: _visualPalette.primary; opacity: 0.4
            }
        }
    }
}
