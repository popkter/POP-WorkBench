import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ColumnLayout {
    id: root

    required property var controller
    required property var parentWindow
    required property var parameterValues
    property var androidController: null
    property bool scrcpySelected: false
    property bool overlaysVisible: false
    readonly property int parameterCount:
        (root.controller.selectedTool.parameters || []).length
    readonly property bool hasParameters: parameterCount > 0
    readonly property real parameterLabelHeight: 20
    readonly property real parameterInputHeight: 54
    readonly property real parameterLabelSpacing: 6
    readonly property real parameterItemSpacing: 13
    readonly property real parameterItemHeight:
        parameterLabelHeight + parameterLabelSpacing + parameterInputHeight
    readonly property real parameterFieldsHeight: parameterFlow.childrenRect.height
    readonly property real parameterContentHeight: parameterFieldsHeight
        + (deviceSelector.visible ? deviceSelector.implicitHeight + spacing : 0)

    spacing: Theme.sectionSpacing

    DeviceSelector {
        id: deviceSelector
        Layout.fillWidth: true
        visible: !!root.controller.selectedTool.uses_android_device
        enabled: !root.scrcpySelected || !root.controller.running
        controller: root.androidController
        toolId: root.controller.selectedTool.id || ""
        requiredDevice: !!root.controller.selectedTool.requires_android_device
        explicitTarget: !!root.controller.selectedTool.android_explicit_target
    }

    Rectangle {
        id: scrcpyHost
        property bool geometryReady: false
        property int stableGeometryFrames: 0
        property string lastGeometryKey: ""
        readonly property real nativeContentInset: Math.max(2, radius / 2)
        visible: root.scrcpySelected
        Layout.fillWidth: true
        Layout.fillHeight: true
        Layout.minimumHeight: 180
        radius: Theme.radiusLarge
        color: Theme.consoleBackground
        clip: true

        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            preventStealing: true
            onPressed: function(mouse) { mouse.accepted = true }
            onReleased: function(mouse) { mouse.accepted = true }
            onDoubleClicked: function(mouse) { mouse.accepted = true }
        }

        function geometrySnapshot() {
            const inset = nativeContentInset
            const point = mapToItem(null, inset, inset)
            return {
                x: Math.round(point.x),
                y: Math.round(point.y),
                width: Math.round(Math.max(0, width - inset * 2)),
                height: Math.round(Math.max(0, height - inset * 2))
            }
        }

        function hideUntilLayoutSettles() {
            geometryReady = false
            stableGeometryFrames = 0
            lastGeometryKey = ""
            root.controller.updateScrcpyGeometry(0, 0, 0, 0, false)
        }

        function syncGeometry() {
            const geometry = geometrySnapshot()
            const geometryKey = geometry.x + ":" + geometry.y + ":"
                              + geometry.width + ":" + geometry.height
            const validGeometry = geometry.width > 1 && geometry.height > 1

            if (!geometryReady) {
                if (validGeometry && geometryKey === lastGeometryKey)
                    stableGeometryFrames += 1
                else
                    stableGeometryFrames = 0
                lastGeometryKey = geometryKey
                geometryReady = validGeometry && stableGeometryFrames >= 2
            }

            const canShow = geometryReady && visible
                         && root.parentWindow.visible && !root.overlaysVisible
            root.controller.updateScrcpyGeometry(
                        geometry.x, geometry.y,
                        geometry.width, geometry.height, canShow)
        }

        Column {
            anchors.centerIn: parent
            spacing: Theme.space12
            MaterialIcon {
                anchors.horizontalCenter: parent.horizontalCenter
                icon: root.controller.running ? "cast_connected" : "cast"
                iconSize: 54
                color: Theme.consoleMuted
            }
            Text {
                anchors.horizontalCenter: parent.horizontalCenter
                text: root.controller.running
                      ? "正在连接设备并准备投屏…"
                      : "点击“开始投屏”，设备画面将在此处显示"
                color: Theme.consoleText
                font.pixelSize: Theme.fontBody
            }
        }

        Timer {
            interval: 16
            repeat: true
            running: scrcpyHost.visible
            onTriggered: scrcpyHost.syncGeometry()
        }
        onVisibleChanged: {
            if (visible)
                hideUntilLayoutSettles()
            else
                root.controller.updateScrcpyGeometry(0, 0, 0, 0, false)
        }
        Component.onCompleted: hideUntilLayoutSettles()
    }

    PrimaryButton {
        visible: root.scrcpySelected
        Layout.alignment: Qt.AlignRight
        Layout.preferredWidth: 168
        Layout.preferredHeight: 40
        enabled: root.controller.running
                 || deviceSelector.deviceState.available
        text: root.controller.running ? "结束投屏" : "开始投屏"
        iconName: root.controller.running ? "stop" : "cast_connected"
        dangerStyle: root.controller.running
        onClicked: {
            if (root.controller.running)
                root.controller.stopExecution()
            else
                root.controller.runSelected({})
        }
    }

    DesktopScrollView {
        id: commandParameterScroll
        visible: !root.scrcpySelected
        Layout.fillWidth: true
        Layout.fillHeight: true
        contentWidth: availableWidth
        clip: true
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        Flow {
            id: parameterFlow
            width: commandParameterScroll.availableWidth
            height: root.parameterFieldsHeight
            spacing: root.parameterItemSpacing

            Repeater {
                model: root.controller.selectedTool.parameters || []
                delegate: Column {
                    required property var modelData
                    width: parameterFlow.width
                    height: root.parameterLabelHeight + root.parameterLabelSpacing
                        + parameterInputLoader.height
                    spacing: root.parameterLabelSpacing

                    Text {
                        width: parent.width
                        height: root.parameterLabelHeight
                        text: modelData.label + (modelData.required ? " *" : "")
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontLabel
                        font.weight: Font.Medium
                    }

                    Loader {
                        id: parameterInputLoader
                        readonly property real singleLineHeight: root.parameterInputHeight
                        width: parent.width
                        height: modelData.kind === "multiline" ? 108
                            : modelData.kind === "radio" && item
                            ? Math.max(singleLineHeight, item.implicitHeight) : singleLineHeight
                        sourceComponent: modelData.kind === "multiline" ? multilineField
                                         : modelData.kind === "choice" ? choiceField
                                         : modelData.kind === "radio" ? radioField
                                         : modelData.kind === "boolean" ? booleanField : normalField

                        Component {
                            id: normalField
                            AppTextField {
                                id: normalTextField
                                readonly property bool pathPickerVisible:
                                    modelData.kind === "file" || modelData.kind === "directory"
                                implicitHeight: parameterInputLoader.singleLineHeight
                                text: String(modelData.default ?? "")
                                placeholderText: modelData.placeholder || ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                leftPadding: Theme.space16
                                rightPadding: pathPickerVisible ? 88 : modelData.kind === "secret" ? 16 : 48
                                validator: modelData.kind === "integer" ? integerValidator
                                    : modelData.kind === "number" ? numberValidator : null
                                RegularExpressionValidator {
                                    id: integerValidator
                                    regularExpression: /[+-]?[0-9]+/
                                }
                                RegularExpressionValidator {
                                    id: numberValidator
                                    regularExpression: /[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?/
                                }
                                echoMode: modelData.kind === "secret"
                                          ? TextInput.Password : TextInput.Normal
                                background: Rectangle {
                                    radius: Theme.radiusMedium
                                    color: Theme.surface
                                    border.color: parent.activeFocus || fileDropArea.containsDrag
                                        ? Theme.primary : Theme.outline
                                    border.width: parent.activeFocus || fileDropArea.containsDrag ? 2 : 1
                                }
                                AppTextEditMenu { target: normalTextField }
                                onTextChanged: root.parameterValues[modelData.id] = text

                                DropArea {
                                    id: fileDropArea
                                    anchors.fill: parent
                                    enabled: modelData.kind === "text"
                                        || modelData.kind === "file"
                                        || modelData.kind === "directory"

                                    onEntered: function(drag) {
                                        if (!drag.hasUrls || drag.urls.length === 0
                                                || root.controller.localPathFromUrl(
                                                    String(drag.urls[0])).length === 0) {
                                            drag.accepted = false
                                        }
                                    }
                                    onDropped: function(drop) {
                                        if (!drop.hasUrls || drop.urls.length === 0)
                                            return
                                        const localPath = root.controller.localPathFromUrl(
                                            String(drop.urls[0]))
                                        if (localPath.length === 0)
                                            return
                                        normalTextField.text = localPath
                                        normalTextField.forceActiveFocus()
                                        drop.acceptProposedAction()
                                    }
                                }

                                PrimaryButton {
                                    visible: modelData.kind !== "secret"
                                    anchors.right: parent.right
                                    anchors.rightMargin: normalTextField.pathPickerVisible ? 48 : Theme.space8
                                    anchors.verticalCenter: parent.verticalCenter
                                    enabled: !root.controller.running
                                    width: 32
                                    height: 32
                                    compact: true
                                    text: "设为默认值"
                                    // Above AppTextEditMenu's input-event overlay (z: 200).
                                    z: 201
                                    iconName: "save"
                                    glyphSize: 20
                                    tonal: true
                                    foregroundColor: Theme.primaryText
                                    border.width: 0
                                    radius: Theme.radiusSmall
                                    color: hovered
                                        ? Theme.primaryContainerHover
                                        : Theme.primaryContainer
                                    onClicked: root.controller.setParameterDefault(
                                        modelData.id, normalTextField.text)
                                }

                                PrimaryButton {
                                    anchors.right: parent.right
                                    anchors.rightMargin: Theme.space8
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: modelData.kind === "file" || modelData.kind === "directory"
                                    width: 32
                                    height: 32
                                    compact: true
                                    text: modelData.kind === "directory" ? "选择文件夹" : "选择文件"
                                    iconName: "folder_open"
                                    glyphSize: 20
                                    tonal: true
                                    foregroundColor: Theme.primaryText
                                    border.width: 0
                                    radius: Theme.radiusSmall
                                    // Above AppTextEditMenu's input-event overlay (z: 200).
                                    z: 201
                                    color: hovered
                                        ? Theme.primaryContainerHover
                                        : Theme.primaryContainer
                                    onClicked: {
                                        const selectedPath = modelData.kind === "directory"
                                            ? root.controller.chooseParameterDirectory(normalTextField.text)
                                            : root.controller.chooseParameterFile(normalTextField.text)
                                        if (selectedPath.length > 0) {
                                            normalTextField.text = selectedPath
                                            normalTextField.forceActiveFocus()
                                        }
                                    }
                                }
                            }
                        }

                        Component {
                            id: multilineField
                            TextArea {
                                id: multilineTextArea
                                implicitHeight: parameterInputLoader.singleLineHeight
                                text: String(modelData.default ?? "")
                                placeholderText: modelData.placeholder || ""
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontBody
                                leftPadding: Theme.space16
                                rightPadding: 48
                                topPadding: Theme.space16
                                bottomPadding: Theme.space16
                                wrapMode: TextEdit.Wrap
                                background: Rectangle {
                                    radius: Theme.radiusMedium
                                    color: Theme.surface
                                    border.color: parent.activeFocus ? Theme.primary : Theme.outline
                                    border.width: parent.activeFocus ? 2 : 1
                                }
                                AppTextEditMenu { target: multilineTextArea }
                                onTextChanged: root.parameterValues[modelData.id] = text
                                PrimaryButton {
                                    anchors.right: parent.right
                                    anchors.rightMargin: Theme.space8
                                    anchors.top: parent.top
                                    anchors.topMargin: Theme.space8
                                    enabled: !root.controller.running
                                    width: 32
                                    height: 32
                                    compact: true
                                    text: "设为默认值"
                                    z: 201
                                    iconName: "save"
                                    glyphSize: 20
                                    tonal: true
                                    foregroundColor: Theme.primaryText
                                    border.width: 0
                                    radius: Theme.radiusSmall
                                    color: hovered ? Theme.primaryContainerHover : Theme.primaryContainer
                                    onClicked: root.controller.setParameterDefault(
                                        modelData.id, multilineTextArea.text)
                                }
                            }
                        }

                        Component {
                            id: choiceField
                            AppComboBox {
                                id: choiceControl
                                readonly property var choiceOptions: modelData.options || []
                                function optionValue(index) {
                                    if (index < 0 || index >= choiceOptions.length)
                                        return ""
                                    const option = choiceOptions[index]
                                    return typeof option === "object" ? option.value : option
                                }
                                implicitHeight: parameterInputLoader.singleLineHeight
                                model: choiceOptions
                                textRole: choiceOptions.length > 0
                                    && typeof choiceOptions[0] === "object" ? "label" : ""
                                currentIndex: {
                                    const expected = String(modelData.default ?? "")
                                    for (let index = 0; index < count; index++) {
                                        if (String(choiceControl.optionValue(index)) === expected)
                                            return index
                                    }
                                    return count > 0 ? 0 : -1
                                }
                                leftPadding: Theme.space16
                                rightPadding: Theme.space40
                                font.pixelSize: Theme.fontBody
                                onCurrentIndexChanged: {
                                    if (currentIndex >= 0)
                                        root.parameterValues[modelData.id] = optionValue(currentIndex)
                                }
                            }
                        }

                        Component {
                            id: radioField
                            ParameterRadioGroup {
                                options: modelData.options || []
                                currentValue: String(modelData.default ?? "")
                                onValueChanged: function(value) {
                                    root.parameterValues[modelData.id] = value
                                }
                            }
                        }

                        Component {
                            id: booleanField
                            Rectangle {
                                implicitHeight: parameterInputLoader.singleLineHeight
                                radius: Theme.radiusMedium
                                color: Theme.surface
                                border.color: Theme.outline
                                AppCheckBox {
                                    anchors.fill: parent
                                    anchors.leftMargin: Theme.space12
                                    anchors.rightMargin: Theme.space12
                                    text: checked ? "已启用" : "未启用"
                                    checked: modelData.default === true
                                        || String(modelData.default).toLowerCase() === "true"
                                    onToggled: root.parameterValues[modelData.id] = checked
                                    Component.onCompleted: root.parameterValues[modelData.id] = checked
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
