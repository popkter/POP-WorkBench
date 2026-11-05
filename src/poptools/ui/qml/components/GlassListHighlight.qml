import QtQuick
import "../theme"

GlassSurface {
    id: root
    property bool selected: false
    property bool hovered: false
    property color hoverColor: Theme.textPrimary
    property bool outlineVisible: selected
    visible: Theme.glassMode && (selected || hovered)
    tintColor: selected ? Theme.primary : hoverColor
    tintStrength: selected ? 0.18 : 0.04
    minimumTintOpacity: 0.04
    pointerReactive: true

    Rectangle {
        anchors.fill: parent
        visible: root.outlineVisible
        radius: root.cornerRadius
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(Theme.primary.r, Theme.primary.g, Theme.primary.b, 0.42)
    }
}
