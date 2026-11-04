import QtQuick
import QtQuick.Controls
import "../theme"

Switch {
    id: control
    spacing: Theme.space12
    font.pixelSize: Theme.fontBody
    indicator: Rectangle {
        x: control.leftPadding; y: (control.height - height) / 2
        width: 52; height: 28; radius: height / 2
        opacity: control.enabled ? 1 : 0.5
        color: control.checked ? Theme.primary : Theme.outline
        border.width: control.activeFocus ? 2 : 0
        border.color: Theme.textPrimary
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; pressed: control.down
            tintColor: control.checked ? Theme.primary : Theme.surfaceContainerHigh
            minimumTintOpacity: 0.96
        }
        Rectangle {
            width: 22; height: 22; radius: width / 2
            x: control.checked ? parent.width - width - 3 : 3
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.primaryForeground
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius
                tintColor: Theme.primaryForeground; pressed: control.down
                minimumTintOpacity: 0.96
            }
            Behavior on x { NumberAnimation { duration: Theme.motionFast } }
        }
    }
    contentItem: Text {
        text: control.text; font: control.font
        leftPadding: control.indicator.width + control.spacing
        color: control.enabled ? Theme.textPrimary : Theme.textSecondary
        verticalAlignment: Text.AlignVCenter
    }
}
