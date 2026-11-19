import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

MenuSeparator {
    readonly property var _visualPalette: Theme.paletteFor(this)

    implicitHeight: 9
    contentItem: Rectangle {
        y: 4
        height: 1
        color: _visualPalette.outlineVariant
    }
}
