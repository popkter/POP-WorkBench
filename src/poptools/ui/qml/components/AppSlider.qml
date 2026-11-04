import QtQuick
import QtQuick.Controls
import "../theme"

Slider {
    id: control
    implicitHeight: Theme.controlHeight
    background: Rectangle {
        x: control.leftPadding; y: (control.height - height) / 2
        width: control.availableWidth; height: Theme.space4; radius: height / 2
        color: Theme.outlineVariant
        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: Theme.outlineVariant }
        Rectangle {
            width: control.visualPosition * parent.width; height: parent.height; radius: height / 2; color: Theme.primary
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius; tintColor: Theme.primary
                minimumTintOpacity: 0.96
            }
        }
    }
    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: (control.height - height) / 2
        width: 20; height: 20; radius: width / 2
        color: control.enabled ? Theme.primary : Theme.outline
        border.color: Theme.textPrimary; border.width: control.activeFocus ? 2 : 0
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; pressed: control.pressed
            tintColor: control.enabled ? Theme.primary : Theme.surfaceContainerHigh
            minimumTintOpacity: 0.96
        }
    }
}
