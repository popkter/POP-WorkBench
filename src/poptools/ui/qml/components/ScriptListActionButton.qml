import QtQuick
import QtQuick.Window
import "../theme"

PrimaryButton {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property real buttonSize: 26
    property color tint: _visualPalette.primary
    implicitWidth: buttonSize
    implicitHeight: buttonSize
    compact: true
    tonal: true
    glyphSize: 16
    radius: Theme.radiusTiny
    disabledOpacity: 0.4
    color: hovered ? _visualPalette.primaryContainerHover : _visualPalette.surfaceContainerLow
    foregroundColor: enabled ? tint : _visualPalette.textSecondary
    border.width: hovered || pressed ? 1 : 0
    border.color: pressed ? tint : _visualPalette.outline
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (enabled) clicked()
}
