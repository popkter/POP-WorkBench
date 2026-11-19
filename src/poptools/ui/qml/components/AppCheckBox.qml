import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

CheckBox {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control
    spacing: Theme.space8
    padding: Theme.space4
    font.pixelSize: Theme.fontBody
    implicitHeight: Math.max(Theme.controlHeight, contentItem.implicitHeight + topPadding + bottomPadding)
    indicator: Rectangle {
        x: control.leftPadding
        y: (control.height - height) / 2
        width: 22; height: 22; radius: Theme.radiusTiny
        opacity: control.enabled ? 1 : 0.5
        color: control.checked ? _visualPalette.primary : _visualPalette.inputDefault
        border.color: control.activeFocus ? _visualPalette.primary : _visualPalette.outline
        border.width: control.activeFocus ? 2 : 1
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; pressed: control.down
            tintColor: control.checked ? _visualPalette.primary : _visualPalette.surfaceContainerLow
            minimumTintOpacity: 0.96
        }
        MaterialIcon {
            anchors.centerIn: parent; icon: "check"; iconSize: 18
            visible: control.checked; color: _visualPalette.primaryForeground
        }
    }
    contentItem: Text {
        text: control.text; font: control.font
        leftPadding: control.indicator.width + control.spacing
        color: control.enabled ? _visualPalette.textPrimary : _visualPalette.textSecondary
        verticalAlignment: Text.AlignVCenter; wrapMode: Text.Wrap
    }
}
