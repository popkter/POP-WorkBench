import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

Slider {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control
    implicitHeight: Theme.controlHeight
    background: Rectangle {
        x: control.leftPadding; y: (control.height - height) / 2
        width: control.availableWidth; height: Theme.space4; radius: height / 2
        color: _visualPalette.outlineVariant
        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.outlineVariant }
        Rectangle {
            width: control.visualPosition * parent.width; height: parent.height; radius: height / 2; color: _visualPalette.primary
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.primary
                minimumTintOpacity: 0.96
            }
        }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        width: 20; height: 20; radius: width / 2
        color: control.enabled ? _visualPalette.primary : _visualPalette.outline
        border.color: _visualPalette.textPrimary; border.width: control.activeFocus ? 2 : 0
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; pressed: control.pressed
            tintColor: control.enabled ? _visualPalette.primary : _visualPalette.surfaceContainerHigh
            minimumTintOpacity: 0.96
        }
    }
}
