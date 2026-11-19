import QtQuick
import QtQuick.Window
import "../theme"

PrimaryButton {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property bool primaryAction: false
    property bool destructive: false
    iconName: ""
    implicitWidth: compact ? Theme.controlHeight
                   : Math.max(88, labelMetrics.advanceWidth + Theme.space32
                              + (iconName.length > 0 ? glyphSize + contentSpacing : 0))
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusControl
    glyphSize: 18
    tonal: !primaryAction
    color: !enabled ? _visualPalette.surfaceContainerHigh
           : destructive ? (hovered ? Qt.darker(_visualPalette.errorContainer, 1.12) : _visualPalette.errorContainer)
           : primaryAction ? (hovered ? _visualPalette.primaryHover : _visualPalette.primary)
           : hovered ? _visualPalette.surfaceContainerHigh : _visualPalette.surfaceContainer
    border.color: activeFocus ? _visualPalette.primary
                  : destructive ? _visualPalette.errorColor
                  : primaryAction ? _visualPalette.primary : _visualPalette.outlineVariant
    border.width: activeFocus ? 2 : 1
    foregroundColor: !enabled ? _visualPalette.textSecondary
                     : destructive ? _visualPalette.errorColor
                     : primaryAction ? _visualPalette.primaryForeground : _visualPalette.textPrimary
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: text
    Accessible.onPressAction: if (enabled) clicked()
    Keys.onSpacePressed: if (enabled) clicked()
    Keys.onReturnPressed: if (enabled) clicked()
    Keys.onEnterPressed: if (enabled) clicked()

    TextMetrics {
        id: labelMetrics
        text: root.text
        font.pixelSize: root.labelFontSize
        font.weight: root.labelFontWeight
    }
}
