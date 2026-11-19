import QtQuick
import QtQuick.Window
import "../theme"

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    objectName: "decadeCardArtwork"
    property bool backFace: false
    property string iconName: "terminal"
    readonly property real motifSize: backFace ? Math.min(width * 0.44, height * 0.4) : width * 0.55
    readonly property real centerY: height / 2
    Item {
        anchors.fill: parent
        visible: !LauncherStyle.zio
        Rectangle {
            x: (parent.width - width) / 2
            y: root.centerY - height / 2
            width: root.motifSize
            height: width
            rotation: 45
            radius: root.motifSize * 0.11
            color: root.backFace ? LauncherStyle.decadeCardBackFill : LauncherStyle.decadeCardArtworkFill
            border.width: root.backFace ? Theme.borderWidthMedium * root.width / 440 : Theme.borderWidthMedium
            border.color: root.backFace ? _visualPalette.primary : LauncherStyle.decadeCardArtworkOutline
        }
        MaterialIcon {
            objectName: "decadeCardArtworkIcon"
            x: (parent.width - width) / 2
            y: root.centerY - height / 2
            width: root.backFace ? root.motifSize * 0.62 : parent.width * 0.29
            height: width
            icon: root.iconName || "terminal"
            iconSize: width
            color: root.backFace ? _visualPalette.textPrimary : LauncherStyle.decadeCardArtworkIcon
            opacity: root.backFace ? 1 : 0.4
        }
    }
    Loader {
        anchors.fill: parent
        active: LauncherStyle.zio
        sourceComponent: ZioCardArtwork {
            backFace: root.backFace
            iconName: root.iconName
        }
    }
}
