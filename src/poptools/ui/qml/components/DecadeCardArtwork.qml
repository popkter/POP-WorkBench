import QtQuick
import "../theme"

Item {
    id: root
    objectName: "decadeCardArtwork"
    property bool backFace: false
    readonly property real motifSize: backFace ? Math.min(width * 0.44, height * 0.4) : width * 0.55
    readonly property real centerY: height * (backFace ? 0.5 : 0.67)
    Rectangle {
        x: (parent.width - width) / 2
        y: root.centerY - height / 2
        width: root.motifSize
        height: width
        rotation: 45
        radius: root.motifSize * 0.11
        color: root.backFace ? Theme.decadeCardBackFill : Theme.decadeCardArtworkFill
        border.width: root.backFace ? Theme.borderWidthMedium * root.width / 440 : Theme.borderWidthMedium
        border.color: root.backFace ? Theme.primary : Theme.decadeCardArtworkOutline
    }
    Image {
        x: (parent.width - width) / 2
        y: root.centerY - height / 2
        width: root.backFace ? root.motifSize * 0.62 : parent.width * 0.29
        height: width
        source: root.backFace ? "../../../resources/icons/decade-arrows-back.svg"
            : "../../../resources/icons/decade-arrows.svg"
        sourceSize: Qt.size(width, height)
        opacity: root.backFace ? 1 : 0.4
        smooth: true
    }
}
