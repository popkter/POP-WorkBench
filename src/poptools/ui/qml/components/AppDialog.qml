import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

Dialog {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control
    popupType: Popup.Item

    property bool compactLayout: false

    modal: true
    dim: true
    padding: compactLayout ? Theme.space20 : Theme.space24
    anchors.centerIn: Overlay.overlay

    Overlay.modal: Rectangle {
        color: _visualPalette.scrim
    }

    background: AppPopupSurface {
        cornerRadius: Theme.radiusCard
        fillColor: _visualPalette.surfaceContainerLow
        outlineColor: _visualPalette.outlineVariant
        dialogSurface: true
    }
}
