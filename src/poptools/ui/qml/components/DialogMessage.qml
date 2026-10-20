import QtQuick
import QtQuick.Controls
import "../theme"

DesktopScrollView {
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
        color: Theme.textSecondary
        font.pixelSize: Theme.fontBody
        wrapMode: Text.Wrap
    }
}
