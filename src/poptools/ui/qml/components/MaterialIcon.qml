import QtQuick
import QtQuick.Window
import "../theme"

Text {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property string icon: "circle"
    property int iconSize: 24
    text: icon
    color: _visualPalette.textPrimary
    font.family: "Material Icons Round"
    font.pixelSize: iconSize
    font.weight: Font.Normal
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering
}


