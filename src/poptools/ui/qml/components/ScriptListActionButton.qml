import QtQuick
import "../theme"

PrimaryButton {
    id: root
    property real buttonSize: 26
    property color tint: Theme.primary
    implicitWidth: buttonSize
    implicitHeight: buttonSize
    compact: true
    tonal: true
    glyphSize: 16
    radius: Theme.radiusTiny
    disabledOpacity: 0.4
    color: hovered ? Theme.primaryContainerHover : Theme.surfaceContainerLow
    foregroundColor: enabled ? tint : Theme.textSecondary
    border.width: hovered || pressed ? 1 : 0
    border.color: pressed ? tint : Theme.outline
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (enabled) clicked()
}
