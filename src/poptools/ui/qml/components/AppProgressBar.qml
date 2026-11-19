import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

ProgressBar {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control
    property real phase: 0
    implicitHeight: Theme.space8
    background: Rectangle { radius: height / 2; color: _visualPalette.glassMode ? "transparent" : _visualPalette.surfaceContainerHigh
        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.surfaceContainerHigh; z: -0.5 } }
    contentItem: Item {
        clip: true
        Rectangle {
            id: fill
            height: parent.height; radius: height / 2; color: _visualPalette.primary
            width: parent.width * (control.indeterminate ? 0.3 : control.visualPosition)
            x: control.indeterminate ? -width + control.phase * (parent.width + width) : 0
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius
                tintColor: _visualPalette.primary; minimumTintOpacity: 0.96
            }
        }
    }
    NumberAnimation on phase {
        running: control.indeterminate && control.visible
        loops: Animation.Infinite; from: 0; to: 1; duration: 1100
    }
}
