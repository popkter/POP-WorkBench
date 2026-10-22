pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../theme"

Loader {
    id: root
    required property var parameter
    required property var controller
    required property var parameterValues
    property bool framed: false
    property bool submitOnEnter: false
    signal submitRequested()

    function handleEnter(event, editor) {
        event.accepted = false
        if (!submitOnEnter || editor.inputMethodComposing)
            return
        if ((event.modifiers & ~Qt.KeypadModifier) !== Qt.NoModifier)
            return
        event.accepted = true
        if (!event.isAutoRepeat && !root.controller.running)
            root.submitRequested()
    }
    clip: true
    Rectangle {
        anchors.fill: parent
        z: -1
        visible: root.framed
        radius: Theme.radiusMedium
        color: Theme.surface
        border.color: root.item && root.item.activeFocus ? Theme.primary : Theme.outline
    }
    component ParameterDefaultButton: PrimaryButton {
        enabled: !root.controller.running
        width: 30
        height: 30
        compact: true
        text: "设为默认值"
        iconName: "save"
        glyphSize: 19
        tonal: true
        foregroundColor: Theme.primaryText
        border.width: 0
        radius: Theme.radiusControl
        // Keep the button above the text edit menu's input overlay.
        z: 201
        color: hovered ? Theme.primaryContainerHover : Theme.runtimeBadge
    }

    sourceComponent: root.parameter.kind === "choice"
        ? choiceField : root.parameter.kind === "radio"
        ? radioField : root.parameter.kind === "boolean"
        ? booleanField : root.parameter.kind === "multiline"
        ? multilineField : textField

    Component {
        id: textField
        AppTextField {
            id: parameterTextField
            Accessible.name: root.parameter.label
            readonly property bool pathPickerVisible:
                root.parameter.kind === "file"
                || root.parameter.kind === "directory"
            text: String(root.parameter.default ?? "")
            placeholderText: root.parameter.placeholder || ""
            color: Theme.textPrimary
            font.pixelSize: Theme.fontBody
            leftPadding: 13
            rightPadding: pathPickerVisible ? 81 : 45
            validator: root.parameter.kind === "integer" ? integerValidator
                : root.parameter.kind === "number" ? numberValidator : null
            RegularExpressionValidator {
                id: integerValidator
                regularExpression: /[+-]?[0-9]+/
            }
            RegularExpressionValidator {
                id: numberValidator
                regularExpression: /[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?/
            }
            echoMode: root.parameter.kind === "secret"
                ? TextInput.Password : TextInput.Normal
            background: null
            onTextChanged: root.parameterValues[root.parameter.id] = text
            Keys.onReturnPressed: event => root.handleEnter(event, parameterTextField)
            Keys.onEnterPressed: event => root.handleEnter(event, parameterTextField)
            FilePathDropArea { target: parameterTextField }
            AppTextEditMenu { target: parameterTextField }

            ParameterDefaultButton {
                anchors.right: parent.right
                anchors.rightMargin: parameterTextField.pathPickerVisible ? 42 : 6
                anchors.verticalCenter: parent.verticalCenter
                onClicked: root.controller.setParameterDefault(
                    root.parameter.id, parameterTextField.text)
            }

            PrimaryButton {
                anchors.right: parent.right
                anchors.rightMargin: 6
                anchors.verticalCenter: parent.verticalCenter
                visible: parameterTextField.pathPickerVisible
                width: 30
                height: 30
                compact: true
                text: root.parameter.kind === "directory"
                    ? "选择文件夹" : "选择文件"
                iconName: "folder_open"
                glyphSize: 19
                tonal: true
                foregroundColor: Theme.primaryText
                border.width: 0
                radius: Theme.radiusControl
                // Above AppTextEditMenu's input-event overlay (z: 200).
                z: 201
                color: hovered
                    ? Theme.primaryContainerHover
                    : Theme.primaryContainer
                onClicked: {
                    const selectedPath = root.parameter.kind === "directory"
                        ? root.controller.chooseParameterDirectory(parameterTextField.text)
                        : root.controller.chooseParameterFile(parameterTextField.text)
                    if (selectedPath.length > 0) {
                        parameterTextField.text = selectedPath
                        parameterTextField.forceActiveFocus()
                    }
                }
            }
        }
    }

    Component {
        id: multilineField
        TextArea {
            id: parameterTextArea
            Accessible.name: root.parameter.label
            text: String(root.parameter.default ?? "")
            placeholderText: root.parameter.placeholder || ""
            color: Theme.textPrimary
            font.pixelSize: Theme.fontBody
            leftPadding: 13
            rightPadding: 45
            wrapMode: TextEdit.Wrap
            background: null
            onTextChanged: root.parameterValues[root.parameter.id] = text
            Keys.onReturnPressed: event => root.handleEnter(event, parameterTextArea)
            Keys.onEnterPressed: event => root.handleEnter(event, parameterTextArea)
            FilePathDropArea { target: parameterTextArea }
            AppTextEditMenu { target: parameterTextArea }
            ParameterDefaultButton {
                anchors.right: parent.right
                anchors.rightMargin: 6
                anchors.top: parent.top
                anchors.topMargin: 5
                onClicked: root.controller.setParameterDefault(
                    root.parameter.id, parameterTextArea.text)
            }
        }
    }

    Component {
        id: choiceField
        AppComboBox {
            id: choiceControl
            Accessible.name: root.parameter.label
            background: null
            readonly property var choiceOptions: root.parameter.options || []
            function optionValue(index) {
                if (index < 0 || index >= choiceOptions.length)
                    return ""
                const option = choiceOptions[index]
                return typeof option === "object" ? option.value : option
            }
            model: choiceOptions
            currentIndex: {
                const expected = String(root.parameter.default ?? "")
                for (let index = 0; index < choiceOptions.length; index++) {
                    if (String(choiceControl.optionValue(index)) === expected)
                        return index
                }
                return choiceOptions.length > 0 ? 0 : -1
            }
            textRole: choiceOptions.length > 0 && typeof choiceOptions[0] === "object" ? "label" : ""
            leftPadding: 13
            font.pixelSize: Theme.fontBody
            onCurrentIndexChanged: {
                if (currentIndex >= 0)
                    root.parameterValues[root.parameter.id] = optionValue(currentIndex)
            }
        }
    }

    Component {
        id: radioField
        ParameterRadioGroup {
            options: root.parameter.options || []
            currentValue: String(root.parameter.default ?? "")
            onValueChanged: function(value) {
                root.parameterValues[root.parameter.id] = value
            }
        }
    }

    Component {
        id: booleanField
        AppCheckBox {
            text: root.framed ? (checked ? "已启用" : "未启用") : ""
            Accessible.name: root.parameter.label
            checked: root.parameter.default === true
                || String(root.parameter.default).toLowerCase() === "true"
            onToggled: root.parameterValues[root.parameter.id] = checked
            Component.onCompleted: root.parameterValues[root.parameter.id] = checked
        }
    }
}
