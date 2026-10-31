import QtQuick
import QtQuick.Controls
import "../theme"

Item {
    id: root
    property var options: []
    property string currentValue: ""
    property real leftPadding: Theme.space4
    signal valueChanged(string value)
    implicitHeight: choices.height

    ButtonGroup { id: group }
    Flow {
        id: choices
        anchors.verticalCenter: parent.verticalCenter
        width: parent.width
        spacing: Theme.space8
        Repeater {
            model: root.options
            delegate: RadioButton {
                id: control
                required property var modelData
                readonly property string optionValue: String(
                    typeof modelData === "object" ? modelData.value : modelData)
                text: typeof modelData === "object" ? modelData.label : String(modelData)
                width: Math.min(implicitWidth, choices.width)
                ButtonGroup.group: group
                checked: optionValue === root.currentValue
                spacing: Theme.space8
                padding: Theme.space4
                leftPadding: root.leftPadding
                font.pixelSize: Theme.fontBody
                indicator: Rectangle {
                    x: control.leftPadding
                    y: (control.height - height) / 2
                    width: 22; height: 22; radius: 11
                    color: Theme.inputDefault
                    border.color: control.checked || control.activeFocus ? Theme.primary : Theme.outline
                    border.width: 2
                    Rectangle {
                        anchors.centerIn: parent
                        width: 12; height: 12; radius: 6
                        color: Theme.primary
                        visible: control.checked
                    }
                }
                contentItem: Text {
                    text: control.text; font: control.font
                    leftPadding: control.indicator.width + control.spacing
                    color: Theme.textPrimary
                    verticalAlignment: Text.AlignVCenter
                    wrapMode: Text.Wrap
                }
                onToggled: if (checked) {
                    root.currentValue = optionValue
                    root.valueChanged(optionValue)
                }
            }
        }
    }
    Component.onCompleted: valueChanged(currentValue)
}
