import QtQuick
import "../theme"

PrimaryButton {
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
    color: !enabled ? Theme.surfaceContainerHigh
           : destructive ? (hovered ? Qt.darker(Theme.errorContainer, 1.12) : Theme.errorContainer)
           : primaryAction ? (hovered ? Theme.primaryHover : Theme.primary)
           : hovered ? Theme.surfaceContainerHigh : Theme.surfaceContainer
    border.color: activeFocus ? Theme.primary
                  : destructive ? Theme.errorColor
                  : primaryAction ? Theme.primary : Theme.outlineVariant
    border.width: activeFocus ? 2 : 1
    foregroundColor: !enabled ? Theme.textSecondary
                     : destructive ? Theme.errorColor
                     : primaryAction ? Theme.primaryForeground : Theme.textPrimary
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
