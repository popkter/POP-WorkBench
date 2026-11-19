import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

ComboBox {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control

    implicitHeight: 44
    leftPadding: Theme.space16
    rightPadding: Theme.space40
    font.pixelSize: Theme.fontBody

    function popupAnchorRect() {
        // Floating cards scale their content. Popup geometry is in overlay
        // coordinates, so use the transformed field bounds rather than width.
        let item = control
        let geometryRevision = 0
        while (item) {
            geometryRevision += item.x + item.y + item.width + item.height + item.scale
            item = item.parent
        }
        return control.mapToItem(Overlay.overlay, 0, 0, control.width, control.height)
    }

    contentItem: Text {
        text: control.displayText
        color: control.enabled ? _visualPalette.textPrimary : _visualPalette.textSecondary
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: MaterialIcon {
        x: control.width - width - Theme.space16
        y: (control.height - height) / 2
        icon: control.popup.visible ? "expand_less" : "expand_more"
        iconSize: 20
        color: control.enabled ? _visualPalette.textSecondary : _visualPalette.outline
    }

    background: Rectangle {
        radius: Theme.radiusMedium
        color: _visualPalette.glassMode ? "transparent" : control.enabled ? _visualPalette.popupSurface
               : (_visualPalette.inputDisabled || _visualPalette.surfaceContainerLow)
        border.color: control.activeFocus ? (_visualPalette.borderColorFocused || _visualPalette.primary)
                    : control.enabled ? (_visualPalette.borderColorDefault || _visualPalette.outline)
                    : _visualPalette.outline
        border.width: control.activeFocus ? 2 : 1
        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; z: -0.5; pressed: control.down }
    }

    delegate: ItemDelegate {
        width: control.popup.width - control.popup.leftPadding - control.popup.rightPadding
        height: 48
        highlighted: control.highlightedIndex === index

        contentItem: Text {
            leftPadding: Theme.space12
            rightPadding: Theme.space12
            text: control.textAt(index)
            color: control.currentIndex === index
                   ? _visualPalette.primaryText : _visualPalette.textPrimary
            font: control.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: Theme.radiusSmall
            color: control.currentIndex === index
                   ? _visualPalette.popupSelected
                   : (parent.highlighted ? _visualPalette.popupHover : "transparent")
        }
    }

    popup: Popup {
        parent: Overlay.overlay
        margins: 8
        readonly property rect anchorRect: control.popupAnchorRect()
        readonly property real spaceBelow: Math.max(0, parent.height - margins - anchorRect.bottom - Theme.space8)
        readonly property real spaceAbove: Math.max(0, anchorRect.y - margins - Theme.space8)
        x: Math.max(margins, Math.min(anchorRect.x, parent.width - margins - width))
        y: spaceBelow >= height || spaceBelow >= spaceAbove
            ? anchorRect.bottom + Theme.space8 : anchorRect.y - Theme.space8 - height
        width: Math.min(Math.max(anchorRect.width, 160), Math.max(0, parent.width - margins * 2))
        padding: 6
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 280)
        height: Math.min(implicitHeight, Math.max(spaceAbove, spaceBelow))
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: control.popup.visible ? control.delegateModel : null
            currentIndex: control.highlightedIndex
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator { }
        }

        background: AppPopupSurface { }
    }
}
