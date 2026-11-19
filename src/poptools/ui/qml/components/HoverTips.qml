import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

ToolTip {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    popupType: Popup.Item

    property int maximumWidth: 360

    delay: 450
    timeout: -1
    margins: Theme.space8
    horizontalPadding: Theme.space12
    verticalPadding: Theme.space8
    implicitWidth: Math.min(maximumWidth,
                            contentItem.implicitWidth + leftPadding + rightPadding)
    closePolicy: Popup.NoAutoClose

    x: parent ? Math.round((parent.width - width) / 2) : 0
    y: parent && parent.mapToItem(null, 0, 0).y < height + Theme.space8
       ? parent.height + Theme.space8
       : -height - Theme.space8

    contentItem: Text {
        text: root.text
        color: _visualPalette.textPrimary
        font.pixelSize: Theme.fontCaption
        font.weight: Font.Medium
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: AppPopupSurface {
        tooltipSurface: true
        minimumOpacity: Theme.glassMaterial.tooltipOpacity === undefined
            ? 0.97 : Theme.glassMaterial.tooltipOpacity
        fillColor: _visualPalette.popupSurface
        outlineColor: _visualPalette.outline
        cornerRadius: Theme.radiusSmall
    }

    enter: Transition {
        NumberAnimation {
            property: "opacity"
            from: 0
            to: 1
            duration: 120
            easing.type: Easing.OutCubic
        }
    }

    exit: Transition {
        NumberAnimation {
            property: "opacity"
            from: 1
            to: 0
            duration: 80
            easing.type: Easing.InCubic
        }
    }
}
