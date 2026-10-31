import QtQuick
import QtQuick.Controls
import "../theme"

ComboBox {
    id: control

    implicitHeight: 44
    leftPadding: Theme.space16
    rightPadding: Theme.space40
    font.pixelSize: Theme.fontBody

    contentItem: Text {
        text: control.displayText
        color: control.enabled ? Theme.textPrimary : Theme.textSecondary
        font: control.font
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: MaterialIcon {
        x: control.width - width - Theme.space16
        y: (control.height - height) / 2
        icon: control.popup.visible ? "expand_less" : "expand_more"
        iconSize: 20
        color: control.enabled ? Theme.textSecondary : Theme.outline
    }

    background: Rectangle {
        radius: Theme.radiusMedium
        color: control.enabled ? Theme.popupSurface
               : (Theme.inputDisabled || Theme.surfaceContainerLow)
        border.color: control.activeFocus ? (Theme.borderColorFocused || Theme.primary)
                    : control.enabled ? (Theme.borderColorDefault || Theme.outline)
                    : Theme.outline
        border.width: control.activeFocus ? 2 : 1
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
                   ? Theme.primaryText : Theme.textPrimary
            font: control.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        background: Rectangle {
            radius: Theme.radiusSmall
            color: control.currentIndex === index
                   ? Theme.popupSelected
                   : (parent.highlighted ? Theme.popupHover : "transparent")
        }
    }

    popup: Popup {
        y: control.height + Theme.space8
        width: Math.max(control.width, 160)
        padding: 6
        implicitHeight: Math.min(contentItem.implicitHeight + topPadding + bottomPadding, 280)
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
