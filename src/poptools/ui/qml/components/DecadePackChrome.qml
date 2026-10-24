import QtQuick
import "../theme"

// Decorative chassis only; collection/flight geometry and input stay in the host.
Item {
    id: root
    objectName: "decadePackChrome"
    Rectangle {
        anchors.fill: parent
        anchors.margins: 1
        radius: Theme.decadePackRadius
        color: "transparent"
        border.width: Theme.borderWidthThin
        border.color: Theme.decadePackRail
    }
    Rectangle {
        x: Theme.space16; y: 0
        width: 56; height: Theme.borderWidthMedium
        color: Theme.primary
    }
}
