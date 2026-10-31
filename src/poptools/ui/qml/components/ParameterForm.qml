pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../theme"

Column {
    id: root
    required property var parameters
    required property var controller
    required property var parameterValues
    property bool compactLayout: false
    property bool decadeCardLayout: false
    property bool inlineLabels: true
    property bool submitOnEnter: false
    signal submitRequested()
    spacing: inlineLabels ? Theme.space8 : 13
    Repeater {
        model: root.parameters
        delegate: Column {
            id: parameterItem
            required property var modelData
            width: root.width
            spacing: 6

            Text {
                visible: !root.inlineLabels
                width: parent.width
                text: parameterItem.modelData.label + (parameterItem.modelData.required ? " *" : "")
                color: Theme.textPrimary
                font.pixelSize: Theme.fontLabel
            }
            Rectangle {
                id: parameterRow
                objectName: "customParameterRow_" + parameterItem.modelData.id
                width: parent.width
                height: parameterItem.modelData.kind === "multiline" ? (root.inlineLabels ? 88 : 108)
                    : parameterItem.modelData.kind === "radio" && parameterInput.item
                    ? Math.max(root.inlineLabels ? Theme.inputHeight : 54, parameterInput.item.implicitHeight + 2)
                    : (root.inlineLabels ? Theme.inputHeight : 54)
                radius: Theme.radiusSmall
                color: Theme.surfaceContainerLow
                readonly property bool inputFocused: parameterInput.item
                    ? parameterInput.item.activeFocus : false
                border.color: inputFocused ? Theme.primary : Theme.inputBorder
                border.width: inputFocused ? 2 : 1

                Item {
                    id: parameterLabelCell
                    visible: root.inlineLabels
                    objectName: "customParameterLabelCell_" + parameterItem.modelData.id
                    x: 1
                    y: 1
                    width: Math.max(0, (parameterRow.width - 2)
                        * (root.decadeCardLayout ? 0.30 : root.compactLayout ? 0.34 : 0.25))
                    height: parameterInput.height
                    MouseArea {
                        anchors.fill: parent
                        onClicked: if (parameterInput.item)
                            parameterInput.item.forceActiveFocus()
                    }
                    Text {
                        id: parameterLabelText
                        objectName: "customParameterLabel_" + parameterItem.modelData.id
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.space12
                        anchors.right: requiredLabel.left
                        anchors.rightMargin: requiredLabel.visible ? Theme.space4 : 0
                        anchors.verticalCenter: parent.verticalCenter
                        text: parameterItem.modelData.label
                        color: Theme.textPrimary
                        font.pixelSize: root.decadeCardLayout ? Theme.decadeCardTextSize : Theme.fontCaption
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        HoverHandler { id: labelHover }
                        HoverTips {
                            visible: parameterLabelText.truncated && labelHover.hovered
                            text: parameterLabelText.text
                        }
                    }
                    Text {
                        id: requiredLabel
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.space8
                        anchors.verticalCenter: parent.verticalCenter
                        visible: !!parameterItem.modelData.required && !root.decadeCardLayout
                        text: visible ? "必填" : ""
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontCaption
                    }
                }

                Rectangle {
                    visible: root.inlineLabels
                    x: parameterInput.x
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    anchors.margins: Theme.space8
                    width: 1
                    color: Theme.outlineVariant
                }

                ParameterField {
                    id: parameterInput
                    objectName: "customParameterInput_" + parameterItem.modelData.id
                    x: root.inlineLabels ? parameterLabelCell.x + parameterLabelCell.width : 1
                    y: 1
                    width: parameterRow.width - x - 1
                    height: parameterRow.height - 2
                    parameter: parameterItem.modelData
                    controller: root.controller
                    parameterValues: root.parameterValues
                    framed: !root.inlineLabels
                    submitOnEnter: root.submitOnEnter
                    decadeCardLayout: root.decadeCardLayout
                    onSubmitRequested: root.submitRequested()
                }

            }

            Text {
                x: parameterInput.x + parameterInput.contentLeftPadding
                width: Math.max(0, parameterInput.width - parameterInput.contentLeftPadding)
                visible: parameterItem.modelData.kind !== "boolean" && text.length > 0
                text: root.submitOnEnter && parameterItem.modelData.kind === "multiline"
                    ? "Enter 运行，Shift+Enter 换行"
                    : parameterItem.modelData.label.indexOf("VIN") >= 0
                    ? "17 位车辆识别码，写入后将自动读取并验证。"
                    : ""
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSmall
                elide: Text.ElideRight
            }

        }
    }

}
