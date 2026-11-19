import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

MenuItem {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control

    property bool destructive: false

    implicitHeight: Theme.menuItemHeight
    leftPadding: Theme.space12
    rightPadding: Theme.space12

    contentItem: Text {
        text: control.text
        color: control.destructive ? _visualPalette.errorColor
              : control.enabled ? _visualPalette.textPrimary : _visualPalette.textSecondary
        opacity: control.enabled ? 1 : 0.48
        font.pixelSize: Theme.fontSupporting
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: control.highlighted ? _visualPalette.popupHover : "transparent"
    }
}
