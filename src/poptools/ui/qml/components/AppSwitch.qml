import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

Switch {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control
    spacing: Theme.space12
    font.pixelSize: Theme.fontBody
    indicator: Rectangle {
        x: control.leftPadding; y: (control.height - height) / 2
        width: 52; height: 28; radius: height / 2
        opacity: control.enabled ? 1 : 0.5
        color: control.checked ? _visualPalette.primary : _visualPalette.outline
        border.width: control.activeFocus ? 2 : 0
        border.color: _visualPalette.textPrimary
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; pressed: control.down
            tintColor: control.checked ? _visualPalette.primary : _visualPalette.surfaceContainerHigh
            minimumTintOpacity: 0.96
        }
        Rectangle {
            objectName: "switchThumb"
            width: 22; height: 22; radius: width / 2
            x: control.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            color: control.checked ? _visualPalette.primaryForeground : _visualPalette.glassMode ? _visualPalette.textPrimary : _visualPalette.primaryForeground
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius
                tintColor: parent.color; pressed: control.down
                minimumTintOpacity: 0.96
            }
            Behavior on x { NumberAnimation { duration: Theme.motionFast } }
        }
    }
    contentItem: Text {
        text: control.text; font: control.font
        leftPadding: control.indicator.width + control.spacing
        color: control.enabled ? _visualPalette.textPrimary : _visualPalette.textSecondary
        verticalAlignment: Text.AlignVCenter
    }
}
