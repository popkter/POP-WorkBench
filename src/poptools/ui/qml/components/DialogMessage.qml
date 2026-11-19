import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

DesktopScrollView {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property alias text: message.text
    property alias foregroundColor: message.color
    implicitHeight: Math.min(200, message.implicitHeight)
    contentWidth: availableWidth
    clip: true
    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
    ScrollBar.vertical.policy: ScrollBar.AsNeeded
    Text {
        id: message
        width: root.availableWidth
        textFormat: Text.PlainText
        color: _visualPalette.textSecondary
        font.pixelSize: Theme.fontBody
        wrapMode: Text.Wrap
    }
}
