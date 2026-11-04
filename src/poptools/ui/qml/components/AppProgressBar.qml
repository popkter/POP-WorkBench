import QtQuick
import QtQuick.Controls
import "../theme"

ProgressBar {
    id: control
    property real phase: 0
    implicitHeight: Theme.space8
    background: Rectangle { radius: height / 2; color: Theme.glassMode ? "transparent" : Theme.surfaceContainerHigh
        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: Theme.surfaceContainerHigh; z: -0.5 } }
    contentItem: Item {
        clip: true
        Rectangle {
            id: fill
            height: parent.height; radius: height / 2; color: Theme.primary
            width: parent.width * (control.indeterminate ? 0.3 : control.visualPosition)
            x: control.indeterminate ? -width + control.phase * (parent.width + width) : 0
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius
                tintColor: Theme.primary; minimumTintOpacity: 0.96
            }
        }
    }
    NumberAnimation on phase {
        running: control.indeterminate && control.visible
        loops: Animation.Infinite; from: 0; to: 1; duration: 1100
    }
}
