import QtQuick
import QtQuick.Controls
import "../theme"

Dialog {
    id: control

    property bool compactLayout: false

    modal: true
    dim: true
    padding: compactLayout ? Theme.space20 : Theme.space24
    anchors.centerIn: Overlay.overlay

    Overlay.modal: Rectangle {
        color: Theme.scrim
    }

    background: AppPopupSurface {
        cornerRadius: Theme.radiusCard
        fillColor: Theme.surfaceContainerLow
        outlineColor: Theme.outlineVariant
        dialogSurface: true
    }
}
