import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

TextField {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: control
    property bool clearButtonEnabled: false
    property real baseRightPadding: Theme.space12
    implicitHeight: Theme.controlHeight
    font.pixelSize: Theme.fontBody
    color: enabled ? _visualPalette.textPrimary : _visualPalette.textSecondary
    placeholderTextColor: _visualPalette.textSecondary
    selectionColor: _visualPalette.glassMode ? _visualPalette.primary : _visualPalette.primaryContainer
    selectedTextColor: _visualPalette.glassMode ? _visualPalette.primaryForeground : _visualPalette.textPrimary
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
            color: clearButton.hovered ? _visualPalette.primaryContainerHover : "transparent"
        }
        contentItem: MaterialIcon {
            icon: "close"
            iconSize: 16
            color: clearButton.hovered ? _visualPalette.primary : _visualPalette.textSecondary
        }
        HoverHandler { cursorShape: Qt.PointingHandCursor }
        onClicked: {
            control.clear()
            control.forceActiveFocus()
        }
    }
    background: Rectangle {
        radius: Theme.radiusControl
        color: _visualPalette.glassMode ? "transparent" : control.enabled ? _visualPalette.inputDefault : _visualPalette.inputDisabled
        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; z: -0.5 }
        border.color: control.activeFocus ? _visualPalette.primary : _visualPalette.outline
        border.width: control.activeFocus ? 2 : 1
    }
}
