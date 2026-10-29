import QtQuick
import QtQuick.Controls
import "../theme"

TextField {
    id: control
    property bool clearButtonEnabled: false
    property real baseRightPadding: Theme.space12
    implicitHeight: Theme.controlHeight
    font.pixelSize: Theme.fontBody
    color: enabled ? Theme.textPrimary : Theme.textSecondary
    placeholderTextColor: Theme.textSecondary
    selectionColor: Theme.primaryContainer
    selectedTextColor: Theme.textPrimary
    selectByMouse: true
    leftPadding: Theme.space12
    rightPadding: clearButton.visible ? clearButton.width + 8 : baseRightPadding
    ToolButton {
        id: clearButton
        objectName: control.objectName + "ClearButton"
        anchors.right: parent.right
        anchors.rightMargin: 4
        anchors.verticalCenter: parent.verticalCenter
        width: Math.min(28, control.height - 4); height: width
        visible: control.clearButtonEnabled && control.length > 0
        enabled: !control.readOnly
        focusPolicy: Qt.NoFocus
        hoverEnabled: true
        Accessible.name: "清空输入"
        background: Rectangle {
            radius: Theme.radiusSmall
            color: clearButton.hovered ? Theme.primaryContainerHover : "transparent"
        }
        contentItem: MaterialIcon {
            icon: "close"
            iconSize: 16
            color: clearButton.hovered ? Theme.primary : Theme.textSecondary
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        onClicked: {
            control.clear()
            control.forceActiveFocus()
        }
    }
    background: Rectangle {
        radius: Theme.radiusControl
        color: control.enabled ? Theme.inputDefault : Theme.inputDisabled
        border.color: control.activeFocus ? Theme.primary : Theme.outline
        border.width: control.activeFocus ? 2 : 1
    }
}
