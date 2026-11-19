import QtQuick
import QtQuick.Window
import "../theme"

GlassSurface {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property bool selected: false
    property bool hovered: false
    property color hoverColor: _visualPalette.textPrimary
    property bool outlineVisible: selected
    overlay: true
    visible: _visualPalette.glassMode && (selected || hovered)
    tintColor: selected ? _visualPalette.primary : hoverColor
    tintStrength: selected ? 0.18 : 0.04
    minimumTintOpacity: 0.04
    pointerReactive: true

    Rectangle {
        anchors.fill: parent
        visible: root.outlineVisible
        radius: root.cornerRadius
        color: "transparent"
        border.width: 1
        border.color: Qt.rgba(_visualPalette.primary.r, _visualPalette.primary.g, _visualPalette.primary.b, 0.42)
    }
}
