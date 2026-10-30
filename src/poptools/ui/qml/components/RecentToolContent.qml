import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

// Incubated separately: creating a new form must not block cards already in flight.
Item {
    id: content
    required property var dialog
    property alias workspace: workspaceLoader
    readonly property bool decadeCard: dialog.customScriptMode && Theme.mechanicalMode
    Keys.onEscapePressed: function(event) {
        if (titleDevicePicker.inlineExpanded)
            titleDevicePicker.closeDeviceMenu()
        else
            event.accepted = false
    }
    MultiEffect {
        id: dialogShadow
        visible: !dialog.customScriptMode
        anchors.fill: parent
        anchors.margins: dialog.customScriptMode ? Theme.space4 : Theme.space8
        source: contentRect
        shadowEnabled: !dialog.customScriptMode
        shadowBlur: 0.7
        blurMax: 24
        shadowOpacity: Theme.darkMode ? 0.72 : 0.42
        shadowColor: "#000000"
        shadowHorizontalOffset: 0
        shadowVerticalOffset: 6
    }

    Rectangle {
        id: contentRect
        anchors.fill: parent
        anchors.margins: content.decadeCard ? 0 : dialog.customScriptMode ? Theme.space4 : Theme.space8
        radius: content.decadeCard ? Theme.decadeCardRadius : dialog.customScriptMode ? Theme.radiusMedium : Theme.radiusLarge
        color: content.decadeCard ? Theme.decadeCardSurface : dialog.customScriptMode ? Theme.chromeBackground
            : Theme.darkMode ? Theme.surfaceContainer : Theme.surface
        border.width: content.decadeCard ? Theme.decadeCardBorderWidth : dialog.customScriptMode ? 1 : 0
        border.color: content.decadeCard ? Theme.primary : Theme.outlineVariant
        clip: true

        DecadeCardArtwork {
            anchors.fill: parent
            visible: content.decadeCard
            iconName: dialog.selectedTool.presentation
                ? dialog.selectedTool.presentation.icon || "terminal" : "terminal"
        }

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // ── Title bar ─────────────────────────────────
            Rectangle {
                id: dialogTitleBar
                Layout.fillWidth: true
                Layout.preferredHeight: content.decadeCard ? Theme.decadeCardHeaderHeight : dialog.customScriptMode ? 40 : 56
                color: "transparent"

                // Drag-to-move area (covers title bar, behind interactive elements)
                MouseArea {
                    objectName: "recentToolTitleDragArea"
                    anchors.left: parent.left
                    anchors.right: titleButtons.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    property point pressPosition: Qt.point(0, 0)
                    property bool systemDragging: false
                    onPressed: function(mouse) {
                        pressPosition = Qt.point(mouse.x, mouse.y)
                        systemDragging = false
                    }
                    onPositionChanged: function(mouse) {
                        if (pressed && !systemDragging
                                && Math.max(Math.abs(mouse.x - pressPosition.x),
                                            Math.abs(mouse.y - pressPosition.y)) >= Qt.styleHints.startDragDistance) {
                            systemDragging = true
                            dialog.startSystemMove()
                        }
                    }
                    onDoubleClicked: if (dialog.customScriptMode && Theme.mechanicalMode)
                        dialog.queueTitleActivation()
                }

                Image {
                    visible: dialog.customScriptMode && !content.decadeCard
                    anchors.left: parent.left
                    anchors.leftMargin: Theme.space12
                    anchors.verticalCenter: parent.verticalCenter
                    width: 20
                    height: 20
                    source: "../../../resources/icons/app-icon-ui.png"
                    sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
                    smooth: true
                }

                // Title text
                Text {
                    objectName: "recentToolTitle"
                    visible: content.decadeCard || !dialog.customScriptMode
                    anchors.left: parent.left
                    anchors.leftMargin: content.decadeCard ? Theme.decadeCardPadding : dialog.customScriptMode ? 40 : Theme.space20
                    anchors.right: titleButtons.left
                    anchors.rightMargin: Theme.space12
                    anchors.verticalCenter: parent.verticalCenter
                    text: content.decadeCard ? dialog.selectedTool.title || "运行脚本" : dialog.customScriptMode ? "泡泡的工作台"
                        : dialog.selectedTool.title || "运行工具"
                    color: dialog.customScriptMode ? Theme.chromeForeground : Theme.textPrimary
                    font.pixelSize: content.decadeCard ? Theme.decadeCardTitleSize : dialog.customScriptMode ? Theme.fontSupporting : Theme.fontSectionTitle
                    font.weight: content.decadeCard ? Font.DemiBold : dialog.customScriptMode ? Font.Medium : Font.Bold
                    elide: Text.ElideRight
                }

                // Buttons row (right-aligned)
                Row {
                    id: titleButtons
                    anchors.right: parent.right
                    anchors.rightMargin: content.decadeCard ? Theme.decadeCardPadding : 0
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    spacing: content.decadeCard ? Theme.space8 : Theme.space4

                    // ── Custom command run button ─────────
                    PrimaryButton {
                        objectName: "recentToolRunButton"
                        visible: !dialog.presetMode
                        width: content.decadeCard ? Theme.decadeCardActionSize : dialog.customScriptMode ? 102 : 48
                        height: content.decadeCard ? Theme.decadeCardActionSize : dialog.customScriptMode ? Theme.captionActionHeight : 32
                        anchors.verticalCenter: parent.verticalCenter
                        compact: content.decadeCard || !dialog.customScriptMode
                        showHoverTips: !content.decadeCard && compact
                        text: dialog.operationRunning ? "停止运行"
                            : dialog.customScriptMode ? "运行脚本" : "运行工具"
                        iconName: dialog.operationRunning ? "stop" : "play_arrow"
                        glyphSize: dialog.customScriptMode ? 20 : 24
                        tonal: true
                        foregroundColor: content.decadeCard ? Theme.primaryText : dialog.customScriptMode
                            ? (dialog.operationRunning ? Theme.errorColor : Theme.success) : "white"
                        border.width: content.decadeCard ? Theme.borderWidthThin : 0
                        border.color: Theme.decadeCardActionBorder
                        radius: content.decadeCard ? Theme.radiusSmall : dialog.customScriptMode ? Theme.radiusTiny : Theme.radiusMedium
                        color: content.decadeCard ? (hovered ? Theme.primaryContainer : Theme.decadeCardActionFill) : dialog.customScriptMode
                            ? (hovered ? Theme.navigationHover : "transparent")
                            : dialog.operationRunning
                            ? (hovered ? Qt.darker(Theme.errorColor, 1.1) : Theme.errorColor)
                            : (hovered ? Theme.primaryHover : Theme.primary)
                        labelFontSize: Theme.fontSupporting
                        labelFontWeight: Font.Normal
                        Accessible.role: Accessible.Button
                        Accessible.name: text
                        Accessible.onPressAction: if (enabled) clicked()
                        onClicked: dialog.runCustomScript()
                    }

                    DeviceSelector {
                        id: titleDevicePicker
                        objectName: "recentToolDeviceSelector"
                        visible: dialog.customScriptMode && !!dialog.deviceController
                        width: content.decadeCard ? Theme.decadeCardActionSize : dialog.customScriptMode ? 148 : 160
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        iconOnly: content.decadeCard
                        showHoverTips: !content.decadeCard
                        inlineMode: content.decadeCard
                        controller: dialog.deviceController
                        toolId: dialog.toolId
                        requiredDevice: !!dialog.selectedTool.requires_android_device
                        explicitTarget: !!dialog.selectedTool.android_explicit_target
                    }

                    PrimaryButton {
                        visible: dialog.recordingPreset
                        width: 132
                        height: 36
                        anchors.verticalCenter: parent.verticalCenter
                        text: (dialog.presetUtilities && dialog.presetUtilities.exporting)
                              ? "正在导出"
                              : (dialog.operationRunning ? "结束录制" : "开始录制")
                        iconName: (dialog.presetUtilities && dialog.presetUtilities.exporting)
                                  ? "hourglass_top"
                                  : (dialog.operationRunning ? "stop" : "play_arrow")
                        successStyle: dialog.operationRunning
                        enabled: !(dialog.presetUtilities && dialog.presetUtilities.exporting)
                        onClicked: dialog.toggleRecording()
                    }

                    ToolButton {
                        id: pinButton
                        objectName: "recentToolPinButton"
                        width: content.decadeCard ? Theme.decadeCardActionSize : 32
                        height: content.decadeCard ? Theme.decadeCardActionSize : 32
                        anchors.verticalCenter: parent.verticalCenter
                        checkable: true
                        checked: dialog.pinned
                        text: checked ? "取消置顶" : "置顶卡片"
                        Accessible.name: text
                        onClicked: dialog.pinned = checked
                        contentItem: MaterialIcon {
                            icon: "push_pin"
                            iconSize: 19
                            color: pinButton.checked ? Theme.primaryText : Theme.textPrimary
                        }
                        background: Rectangle {
                            radius: content.decadeCard ? Theme.radiusSmall : Theme.radiusTiny
                            color: pinButton.checked || pinButton.hovered ? Theme.primaryContainer
                                : content.decadeCard ? Theme.decadeCardActionFill : "transparent"
                            border.width: content.decadeCard || pinButton.checked ? Theme.borderWidthThin : 0
                            border.color: pinButton.checked ? Theme.primary : Theme.decadeCardActionBorder
                        }
                        HoverTips {
                            visible: pinButton.hovered
                            text: pinButton.text
                        }
                    }

                    // Minimize
                    Rectangle {
                        objectName: "recentToolMinimizeButton"
                        visible: !dialog.customScriptMode
                        width: 42; height: parent.height
                        color: minimizeArea.containsMouse ? Theme.surfaceContainerHigh : "transparent"
                        MaterialIcon {
                            anchors.centerIn: parent; icon: "remove"; iconSize: 19; color: Theme.textPrimary
                        }
                        MouseArea {
                            id: minimizeArea; anchors.fill: parent; hoverEnabled: true; onClicked: dialog.showMinimized()
                        }
                    }

                    // Close
                    Rectangle {
                        objectName: "recentToolCloseButton"
                        width: content.decadeCard ? Theme.decadeCardActionSize : 42
                        height: content.decadeCard ? Theme.decadeCardActionSize : parent.height
                        anchors.verticalCenter: parent.verticalCenter
                        radius: content.decadeCard ? Theme.radiusSmall : 0
                        topRightRadius: content.decadeCard ? Theme.radiusSmall : contentRect.radius
                        border.width: content.decadeCard ? Theme.borderWidthThin : 0
                        border.color: Theme.decadeCardActionBorder
                        color: content.decadeCard ? (closeArea.containsMouse ? Theme.primaryContainer : Theme.decadeCardActionFill)
                            : closeArea.containsMouse ? "#C42B1C" : "transparent"
                        MaterialIcon {
                            anchors.centerIn: parent
                            icon: "close"
                            iconSize: 19
                            color: closeArea.containsMouse ? "white" : Theme.textPrimary
                        }
                        MouseArea {
                            id: closeArea; anchors.fill: parent; hoverEnabled: true
                            onClicked: dialog.closeCardAnimated()
                        }
                        activeFocusOnTab: true
                        Accessible.role: Accessible.Button
                        Accessible.name: "关闭卡片"
                        Accessible.onPressAction: dialog.closeCardAnimated()
                        Keys.onReturnPressed: dialog.closeCardAnimated()
                        Keys.onSpacePressed: dialog.closeCardAnimated()
                    }
                }
                Rectangle {
                    visible: content.decadeCard
                    x: Theme.decadeCardPadding
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: Theme.space8
                    width: 49; height: Theme.borderWidthMedium
                    color: Theme.primary
                }
            }

            Item {
                id: inlineDeviceSection
                objectName: "decadeInlineDeviceSection"
                Layout.fillWidth: true
                Layout.preferredHeight: (inlineDevicePanel.height + Theme.space12) * reveal
                Layout.minimumHeight: 0
                property real reveal: content.decadeCard && titleDevicePicker.inlineExpanded ? 1 : 0
                visible: reveal > 0
                enabled: titleDevicePicker.inlineExpanded
                clip: true
                Behavior on reveal {
                    NumberAnimation { duration: Theme.motionStandard; easing.type: Easing.InOutCubic }
                }
                Rectangle {
                    id: inlineDevicePanel
                    x: Theme.decadeCardPadding
                    width: parent.width - x * 2
                    height: inlineDeviceChoices.implicitHeight + Theme.space16
                    color: Theme.surfaceContainerLow
                    border.color: Theme.outlineVariant
                    radius: Theme.radiusSmall
                    AndroidDevicePicker {
                        id: inlineDeviceChoices
                        objectName: "decadeInlineDeviceChoices"
                        x: Theme.space8; y: Theme.space8
                        width: parent.width - x * 2
                        controller: dialog.deviceController
                        deviceState: titleDevicePicker.deviceState
                        explicitTarget: titleDevicePicker.explicitTarget
                        showHoverTips: false
                        maximumListHeight: Math.max(52, Math.min(208, contentRect.height * .3))
                        onDeviceSelected: titleDevicePicker.closeDeviceMenu()
                    }
                }
            }

            Item {
                visible: content.decadeCard
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? Theme.decadeCounterHeight + Theme.space12 : 0
                DecadeUsageCounter {
                    x: Theme.decadeCardPadding
                    width: parent.width - Theme.decadeCardPadding * 2
                    height: Theme.decadeCounterHeight
                    count: dialog.toolController && dialog.toolController.usageCount !== undefined
                        ? dialog.toolController.usageCount : 0
                }
            }

            Loader {
                id: customScriptLoader
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 0
                active: dialog.customScriptMode
                visible: active
                sourceComponent: CustomToolDetailPanel {
                    controller: dialog.toolController
                    androidBackend: dialog.deviceController
                    parentWindow: dialog
                    parameterValues: dialog.parameterValues
                    displayedTool: dialog.selectedTool
                    allowManagement: false
                    actionsInTitleBar: true
                    deviceInTitleBar: true
                    externalRun: true
                    submitParametersOnEnter: true
                    compactLayout: true
                    decadeCardLayout: content.decadeCard
                    minimumFormReservedHeight: 0
                    onRunRequested: dialog.runCustomScript()
                }
            }

            // ── Body ──────────────────────────────────────
            Item {
                id: dialogBody
                visible: !dialog.customScriptMode
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.topMargin: 16
                Layout.bottomMargin: 16

                ColumnLayout {
                    id: bodyContent
                    anchors.fill: parent
                    anchors.bottomMargin: consolePanel.visible ? consolePanel.height : 0
                    spacing: Theme.space12

                    Text {
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: dialog.selectedTool.description || ""
                        color: Theme.textSecondary
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                    }

                    Loader {
                        id: workspaceLoader
                        active: !dialog.customScriptMode
                        readonly property real parameterContentHeight:
                                item && item.parameterContentHeight !== undefined
                            ? item.parameterContentHeight : 0
                        readonly property bool hasParameters:
                                item && item.hasParameters !== undefined
                            ? item.hasParameters : false
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        sourceComponent: dialog.selectedTool.workspace === "preset"
                            ? presetWorkspace : commandWorkspace
                    }
                }


                // ── Console ───────────────────────────
                ConsolePanel {
                    id: consolePanel
                    readonly property real workspaceTop: bodyContent.y + workspaceLoader.y
                    readonly property real parameterContentBottom:
                        workspaceTop + workspaceLoader.parameterContentHeight
                    readonly property real fixedExpandedHeight: Math.max(
                        minimumExpandedHeight,
                        dialogBody.height - workspaceTop - dialog.bodySpacing)
                    readonly property real parameterLimitedHeight: Math.max(
                        minimumExpandedHeight,
                        dialogBody.height - parameterContentBottom - dialog.bodySpacing)
                    visible: !dialog.presetMode
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: visible ? Math.min(implicitHeight, parent.height) : 0
                    minimumVisibleLineCount: 5
                    preferredExpandedHeight: Math.max(
                        minimumExpandedHeight,
                        Math.min(dialog.consolePreferredHeight,
                                 fixedExpandedHeight,
                                 parameterLimitedHeight))
                    maximumExpandedHeight: fixedExpandedHeight
                    resizable: false
                    controller: dialog.toolController
                }
            }
        }
    }

    Component {
        id: commandWorkspace
        CommandWorkspace {
            controller: dialog.toolController
            androidController: dialog.deviceController
            parentWindow: dialog
            parameterValues: dialog.parameterValues
            scrcpySelected: dialog.selectedTool.workspace === "scrcpy"
            overlaysVisible: false
        }
    }

    Component {
        id: presetWorkspace
        PresetWorkspace {
            toolController: dialog.toolController
            utilities: dialog.presetUtilities
            androidBackend: dialog.deviceController
            jiraFeishuBackend: dialog.jiraFeishuBackend
            compact: true
        }
    }
}
