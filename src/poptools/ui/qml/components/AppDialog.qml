import QtQuick
import QtQuick.Controls
import "../theme"

Dialog {
    id: control

    modal: true
    dim: true
    padding: Theme.space24
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
