import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: toggle

    property bool checked: false
    signal toggled(bool value)

    implicitWidth: 52
    implicitHeight: 28
    Layout.preferredWidth: 52
    Layout.preferredHeight: 28
    radius: height / 2
    color: checked ? _visualPalette.primary : _visualPalette.outline

    Rectangle {
        width: 22
        height: 22
        radius: 11
        x: toggle.checked ? toggle.width - width - 3 : 3
        anchors.verticalCenter: parent.verticalCenter
        color: "white"

        Behavior on x {
            NumberAnimation {
                duration: 140
                easing.type: Easing.OutCubic
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: toggle.toggled(!toggle.checked)
    }
}
