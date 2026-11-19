import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

// Incubated separately: creating a new form must not block cards already in flight.
Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: content
    required property var dialog
    property alias workspace: workspaceLoader
    readonly property bool decadeCard: dialog.customScriptMode && LauncherStyle.mechanical
    readonly property bool standardCard: dialog.customScriptMode && !content.decadeCard
    readonly property real cardScale: Math.max(0.1, dialog.cardUiScale)
    readonly property real cardActionSize: 36 / cardScale
    component CardRunButton: PrimaryButton {
        objectName: content.decadeCard ? "recentToolHeaderRunButton" : "recentToolRunButton"
        width: content.standardCard ? content.cardActionSize : content.decadeCard ? LauncherStyle.decadeCardActionSize : 48
        height: content.standardCard ? content.cardActionSize : content.decadeCard ? LauncherStyle.decadeCardActionSize : 32
        anchors.verticalCenter: parent.verticalCenter
        compact: true
        showHoverTips: !content.decadeCard && compact
        text: dialog.operationRunning ? "停止运行"
            : dialog.customScriptMode ? "运行脚本" : "运行工具"
        iconName: dialog.operationRunning ? "stop" : "play_arrow"
        glyphSize: content.standardCard ? 20 / content.cardScale : dialog.customScriptMode ? 20 : 24
        tonal: true
        foregroundColor: content.standardCard ? (dialog.operationRunning ? _visualPalette.errorColor : _visualPalette.primaryText)
            : content.decadeCard ? _visualPalette.primaryText : dialog.customScriptMode
            ? (dialog.operationRunning ? _visualPalette.errorColor : _visualPalette.success) : "white"
        border.width: content.decadeCard ? Theme.borderWidthThin : 0
        border.color: LauncherStyle.decadeCardActionBorder
        radius: content.standardCard ? Theme.radiusControl / content.cardScale : content.decadeCard ? Theme.radiusSmall : Theme.radiusMedium
        color: content.standardCard ? (hovered ? _visualPalette.primaryContainerHover : _visualPalette.primaryContainer)
            : content.decadeCard ? (hovered ? _visualPalette.primaryContainer : LauncherStyle.decadeCardActionFill) : dialog.customScriptMode
            ? (hovered ? _visualPalette.navigationHover : "transparent")
            : dialog.operationRunning
            ? (hovered ? Qt.darker(_visualPalette.errorColor, 1.1) : _visualPalette.errorColor)
            : (hovered ? _visualPalette.primaryHover : _visualPalette.primary)
        labelFontSize: content.standardCard ? 13 / content.cardScale
            : dialog.customScriptMode ? LauncherStyle.decadeCardTextSize : Theme.fontSupporting
        labelFontWeight: Font.Normal
        Accessible.role: Accessible.Button
        Accessible.name: text
        Accessible.onPressAction: if (enabled) clicked()
        onClicked: dialog.runCustomScript()
    }

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
        shadowOpacity: _visualPalette.darkMode ? 0.72 : 0.42
        shadowColor: "#000000"
        shadowHorizontalOffset: 0
        shadowVerticalOffset: 6
    }

    Rectangle {
        id: contentRect
        objectName: "recentToolCardSurface"
        anchors.fill: parent
        anchors.margins: dialog.customScriptMode ? 0 : Theme.space8
        radius: content.decadeCard ? LauncherStyle.decadeCardRadius : dialog.customScriptMode ? Theme.radiusMedium : Theme.radiusLarge
        color: _visualPalette.glassMode ? "transparent" : content.decadeCard ? LauncherStyle.decadeCardSurface : dialog.customScriptMode ? _visualPalette.surfaceContainerLow
            : _visualPalette.darkMode ? _visualPalette.surfaceContainer : _visualPalette.surface
        border.width: 0
        border.color: content.decadeCard ? _visualPalette.primary : _visualPalette.outlineVariant
        clip: true

        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius
            tintColor: content.decadeCard ? LauncherStyle.decadeCardSurface : _visualPalette.surfaceContainerLow
            z: -0.5
        }

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
                Layout.preferredHeight: content.standardCard ? content.cardActionSize + 8 / content.cardScale
                    : content.decadeCard ? LauncherStyle.decadeCardHeaderHeight : 56
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
                    onDoubleClicked: if (dialog.customScriptMode && LauncherStyle.mechanical)
                        dialog.queueTitleActivation()
                }

                Image {
                    visible: dialog.customScriptMode && !content.decadeCard
                    anchors.left: parent.left
                    anchors.leftMargin: content.standardCard ? Theme.space8 / content.cardScale : Theme.space12
                    anchors.verticalCenter: parent.verticalCenter
                    width: content.standardCard ? 20 / content.cardScale : 20
                    height: width
                    source: "../../../resources/icons/app-icon-ui.png"
                    sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
                    smooth: true
                }

                // Title text
                Text {
                    objectName: "recentToolTitle"
                    visible: true
                    anchors.left: parent.left
                    anchors.leftMargin: content.standardCard ? 40 / content.cardScale
                        : content.decadeCard ? LauncherStyle.decadeCardPadding : Theme.space20
                    anchors.right: titleButtons.left
                    anchors.rightMargin: Theme.space12
                    anchors.verticalCenter: parent.verticalCenter
                    text: content.decadeCard || content.standardCard ? dialog.selectedTool.title || "运行脚本"
                        : dialog.selectedTool.title || "运行工具"
                    color: dialog.customScriptMode ? _visualPalette.chromeForeground : _visualPalette.textPrimary
                    font.pixelSize: content.standardCard ? Theme.fontBody / content.cardScale
                        : content.decadeCard ? LauncherStyle.decadeCardTitleSize : Theme.fontSectionTitle
                    font.weight: content.standardCard ? Font.Bold : content.decadeCard ? Font.DemiBold : dialog.customScriptMode ? Font.Medium : Font.Bold
                    elide: Text.ElideRight
                }

                // Buttons row (right-aligned)
                Row {
                    id: titleButtons
                    anchors.right: parent.right
                    anchors.rightMargin: content.decadeCard ? LauncherStyle.decadeCardPadding : 0
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    spacing: content.decadeCard ? Theme.space8 : Theme.space4

                    // ── Custom command run button ─────────
                    CardRunButton {
                        objectName: dialog.customScriptMode ? "inactiveToolRunButton" : "recentToolRunButton"
                        visible: !dialog.customScriptMode && !dialog.presetMode
                    }

                    DeviceSelector {
                        id: titleDevicePicker
                        parent: content.standardCard ? standardActions : titleButtons
                        anchors.right: content.standardCard ? parent.right : undefined
                        objectName: "recentToolDeviceSelector"
                        visible: dialog.customScriptMode && !!dialog.deviceController
                        width: content.standardCard ? Math.max(0, standardActions.width - headerRunButton.width - standardActions.spacing)
                            : content.decadeCard ? LauncherStyle.decadeCardActionSize : 160
                        uiScale: content.standardCard ? 1 / content.cardScale : 1
                        controlHeight: content.standardCard ? content.cardActionSize
                            : iconOnly ? LauncherStyle.decadeCardActionSize : compact ? Theme.captionActionHeight : 41
                        outlined: content.standardCard
                        labelFontSize: content.standardCard ? 12 : Theme.fontSupporting
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
                        width: content.standardCard ? content.cardActionSize : content.decadeCard ? LauncherStyle.decadeCardActionSize : 32
                        height: width
                        anchors.verticalCenter: parent.verticalCenter
                        checkable: true
                        checked: dialog.pinned
                        text: checked ? "取消置顶" : "置顶卡片"
                        Accessible.name: text
                        onClicked: dialog.pinned = checked
                        contentItem: MaterialIcon {
                            icon: "push_pin"
                            iconSize: content.standardCard ? 20 / content.cardScale : 19
                            color: pinButton.checked ? _visualPalette.primaryText : _visualPalette.textPrimary
                        }
                        background: Rectangle {
                            radius: content.decadeCard ? Theme.radiusSmall : Theme.radiusTiny
                            color: pinButton.checked || pinButton.hovered ? _visualPalette.primaryContainer
                                : content.decadeCard ? LauncherStyle.decadeCardActionFill : "transparent"
                            border.width: content.decadeCard || pinButton.checked ? Theme.borderWidthThin : 0
                            border.color: pinButton.checked ? _visualPalette.primary : LauncherStyle.decadeCardActionBorder
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
                        color: minimizeArea.containsMouse ? _visualPalette.surfaceContainerHigh : "transparent"
                        MaterialIcon {
                            anchors.centerIn: parent; icon: "remove"; iconSize: 19; color: _visualPalette.textPrimary
                        }
                        MouseArea {
                            id: minimizeArea; anchors.fill: parent; hoverEnabled: true; onClicked: dialog.showMinimized()
                        }
                    }

                    // Close
                    Rectangle {
                        objectName: "recentToolCloseButton"
                        width: content.standardCard ? content.cardActionSize : content.decadeCard ? LauncherStyle.decadeCardActionSize : 42
                        height: content.standardCard ? content.cardActionSize
                            : content.decadeCard ? LauncherStyle.decadeCardActionSize : parent.height
                        anchors.verticalCenter: parent.verticalCenter
                        radius: content.decadeCard ? Theme.radiusSmall : 0
                        topRightRadius: content.decadeCard ? Theme.radiusSmall : contentRect.radius
                        border.width: content.decadeCard ? Theme.borderWidthThin : 0
                        border.color: LauncherStyle.decadeCardActionBorder
                        color: content.decadeCard ? (closeArea.containsMouse ? _visualPalette.primaryContainer : LauncherStyle.decadeCardActionFill)
                            : closeArea.containsMouse ? "#C42B1C" : "transparent"
                        MaterialIcon {
                            anchors.centerIn: parent
                            icon: "close"
                            iconSize: content.standardCard ? 20 / content.cardScale : 19
                            color: closeArea.containsMouse ? "white" : _visualPalette.textPrimary
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
            }

            Item {
                visible: content.standardCard
                Layout.fillWidth: true
                Layout.preferredHeight: visible ? content.cardActionSize + Theme.space12 / content.cardScale : 0
                Item {
                    id: standardActions
                    objectName: "recentToolActionRow"
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space8 / content.cardScale
                    anchors.rightMargin: Theme.space8 / content.cardScale
                    anchors.topMargin: Theme.space4 / content.cardScale
                    anchors.bottomMargin: Theme.space8 / content.cardScale
                    readonly property real spacing: Theme.space8 / content.cardScale
                    CardRunButton {
                        id: headerRunButton
                        anchors.left: parent.left
                        visible: content.standardCard && !dialog.presetMode
                    }
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
                    x: LauncherStyle.decadeCardPadding
                    width: parent.width - x * 2
                    height: inlineDeviceChoices.implicitHeight + Theme.space16
                    color: _visualPalette.glassMode ? "transparent" : _visualPalette.surfaceContainerLow
                    GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.surfaceContainerLow; z: -0.5 }
                    border.color: _visualPalette.outlineVariant
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
                Layout.preferredHeight: visible ? LauncherStyle.decadeCounterHeight + Theme.space12 : 0
                DecadeUsageCounter {
                    x: LauncherStyle.decadeCardPadding
                    width: parent.width - LauncherStyle.decadeCardPadding * 2
                    height: LauncherStyle.decadeCounterHeight
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
                    sharedCardBackground: true
                    showHeading: false
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
                        color: _visualPalette.textSecondary
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

            Item {
                id: cardActionFooter
                objectName: "recentToolActionFooter"
                visible: content.decadeCard
                Layout.fillWidth: true
                Layout.preferredHeight: visible
                    ? footerRunButton.height + Theme.space8 + LauncherStyle.decadeCardPadding : 0
                MechanicalRunButton {
                    id: footerRunButton
                    objectName: content.decadeCard ? "recentToolRunButton" : "mechanicalFooterRunButton"
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: LauncherStyle.decadeCardPadding
                    anchors.rightMargin: LauncherStyle.decadeCardPadding
                    anchors.topMargin: Theme.space8
                    uiScale: dialog.cardUiScale
                    running: dialog.operationRunning
                    statusText: dialog.toolController.statusText
                    enabled: !!dialog.selectedTool.id && !dialog.outgoing && !dialog.closing
                    onClicked: dialog.runCustomScript()
                }
            }
        }
        // One continuous frame above the artwork and every content section.
        Rectangle {
            objectName: "recentToolCardOutline"
            visible: content.decadeCard
            anchors.fill: parent
            z: 10
            color: "transparent"
            radius: contentRect.radius
            border.width: LauncherStyle.decadeCardBorderWidth
            border.color: _visualPalette.primary
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
