pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    objectName: "customToolDetailPanel"

    required property var controller
    required property var androidBackend
    required property var parentWindow
    required property var parameterValues
    required property var displayedTool
    property bool splitConsole: false
    property bool consoleExpanded: decadeCardLayout ? controller.running : !splitConsole || controller.running
    property real consoleReveal: consoleExpanded ? 1 : 0
    Behavior on consoleReveal {
        enabled: root.splitConsole || root.decadeCardLayout
        NumberAnimation {
            objectName: "customConsoleRevealAnimation"
            duration: Theme.motionStandard
            easing.type: Easing.InOutCubic
        }
    }
    property real consoleHeightRatio: 0.4
    readonly property real separatorHeight: splitConsole ? Theme.space12 : Theme.space8
    readonly property bool executionRunning: !!controller.running
    onExecutionRunningChanged: {
        if ((splitConsole || decadeCardLayout) && executionRunning)
            consoleExpanded = true
    }
    property bool allowManagement: true
    property bool actionsInTitleBar: false
    property bool deviceInTitleBar: false
    property bool externalRun: false
    property bool submitParametersOnEnter: false
    property bool compactLayout: false
    property bool decadeCardLayout: false
    property bool sharedCardBackground: false
    property bool showHeading: true
    readonly property bool cardTypography: sharedCardBackground || decadeCardLayout
    readonly property real panelPadding: decadeCardLayout ? LauncherStyle.decadeCardPadding : compactLayout ? Theme.space8 : Theme.detailPanelPadding
    property real minimumFormReservedHeight: Theme.detailFormReservedHeight
    readonly property bool narrowManagementLayout: allowManagement && width < Theme.detailCompactWidth
    readonly property bool compactConsoleActions: consolePanel.width < (splitConsole ? 560 : 458)
    readonly property bool showConsoleStatusText: !compactConsoleActions
        || consolePanel.width >= (splitConsole ? 340 : 280)
    readonly property color consoleStatusColor: controller.running ? _visualPalette.consoleWarning
        : controller.statusText === "执行成功" ? _visualPalette.success
        : controller.statusText.indexOf("执行失败") === 0 ? _visualPalette.consoleError
        : _visualPalette.consoleMuted

    signal editRequested()
    signal deleteRequested()
    signal confirmRunRequested(var values)
    signal runRequested()
    signal toastRequested(string message, bool error)

    radius: Theme.radiusMedium
    color: sharedCardBackground || _visualPalette.glassMode || splitConsole || decadeCardLayout ? "transparent" : _visualPalette.surfaceContainerLow
    GlassSurface {
        anchors.fill: parent; cornerRadius: parent.radius; z: -0.5
        visible: _visualPalette.glassMode && !root.sharedCardBackground && !root.splitConsole && !root.decadeCardLayout
    }
    border.width: 0
    clip: true

    function kindLabel() {
        if (!root.displayedTool.executor)
            return ""
        const kind = root.displayedTool.executor.kind
        return kind === "batch" ? "ADB"
            : kind === "powershell" ? "PowerShell"
            : kind === "python" ? "Python" : kind
    }

    function kindColor() {
        const kind = root.displayedTool.executor ? root.displayedTool.executor.kind : ""
        return kind === "python" ? _visualPalette.tertiary
            : kind === "batch" ? _visualPalette.success : _visualPalette.runtimeBadgeText
    }

    function kindBackground() {
        const kind = root.displayedTool.executor ? root.displayedTool.executor.kind : ""
        return kind === "python" ? _visualPalette.tertiaryContainer
            : kind === "batch" ? _visualPalette.successContainer : _visualPalette.runtimeBadge
    }

    function runSelectedTool() {
        if (root.splitConsole && root.displayedTool.id && !root.controller.running)
            root.consoleExpanded = true
        if (root.externalRun) {
            root.runRequested()
            return
        }
        if (root.controller.running) {
            root.controller.stopExecution()
        } else if (root.displayedTool.presentation
                   && root.displayedTool.presentation.confirm_before_run) {
            root.confirmRunRequested(root.parameterValues)
        } else {
            root.controller.runSelected(root.parameterValues)
        }
    }

    Rectangle {
        id: formPanel
        objectName: "customParameterPanel"
        width: parent.width
        height: Math.max(0, consolePanel.y - root.separatorHeight)
        radius: Theme.radiusMedium
        color: !_visualPalette.glassMode && root.splitConsole ? _visualPalette.surfaceContainerLow : "transparent"
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; z: -0.5
            visible: _visualPalette.glassMode && root.splitConsole
        }
        border.width: 0
        clip: true

        Item {
            id: header
            objectName: "customScriptHeading"
            visible: root.showHeading && !root.decadeCardLayout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: visible ? headingRow.implicitHeight + root.panelPadding * 2 : 0

            RowLayout {
                id: headingRow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: root.panelPadding
                spacing: root.compactLayout ? Theme.space8 : Theme.space16

                Rectangle {
                    Layout.preferredWidth: root.compactLayout ? 32 : 46
                    Layout.preferredHeight: root.compactLayout ? 32 : 46
                    Layout.alignment: Qt.AlignTop
                    radius: Theme.radiusMedium
                    color: root.kindBackground()
                    MaterialIcon {
                        anchors.centerIn: parent
                        icon: root.displayedTool.presentation
                            ? (root.displayedTool.presentation.icon || "terminal") : "terminal"
                        iconSize: Theme.iconLarge
                        color: root.kindColor()
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: Theme.space4
                    Text {
                        Layout.fillWidth: true
                        text: root.displayedTool.title || "请选择脚本"
                        color: _visualPalette.textPrimary
                        font.pixelSize: root.cardTypography ? LauncherStyle.decadeCardTitleSize
                            : root.compactLayout ? Theme.fontSectionTitle : Theme.fontDetailTitle
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.displayedTool.description || "选择脚本以查看参数、运行状态和输出"
                        color: _visualPalette.textSecondary
                        font.pixelSize: root.cardTypography ? LauncherStyle.decadeCardTextSize
                            : root.compactLayout ? Theme.fontSupporting : Theme.fontBody
                        wrapMode: root.compactLayout ? Text.Wrap : Text.NoWrap
                        maximumLineCount: root.compactLayout ? 2 : 1
                        elide: Text.ElideRight
                    }
                }

                Rectangle {
                    objectName: "customScriptKindBadge"
                    visible: root.kindLabel().length > 0
                    implicitWidth: root.compactLayout ? 76 : 98
                    implicitHeight: 22
                    Layout.alignment: Qt.AlignTop
                    Layout.topMargin: root.compactLayout ? 0 : 6
                    radius: Theme.radiusTiny
                    color: root.kindBackground()
                    Text {
                        anchors.centerIn: parent
                        text: root.kindLabel()
                        color: root.kindColor()
                        font.pixelSize: Theme.fontSmall
                    }
                }
            }
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.leftMargin: root.panelPadding
                anchors.rightMargin: root.panelPadding
                height: Theme.borderWidthThin
                color: _visualPalette.outlineVariant
            }
        }

        Flickable {
            id: parameterArea
            objectName: "customParameterArea"
            x: root.panelPadding
            anchors.top: header.bottom
            anchors.topMargin: header.visible ? (root.compactLayout ? Theme.space8 : Theme.space12) : 0
            width: parent.width - root.panelPadding * 2
            height: Math.max(0, actionArea.y - y - Theme.space8)
            clip: true
            contentWidth: width
            contentHeight: parameterColumn.height
            boundsBehavior: Flickable.StopAtBounds
            acceptedButtons: Qt.NoButton
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            Column {
                id: parameterColumn
                width: parameterArea.width
                spacing: Theme.space8

                ParameterForm {
                    width: parent.width
                    parameters: root.displayedTool.parameters || []
                    controller: root.controller
                    parameterValues: root.parameterValues
                    compactLayout: root.compactLayout
                    decadeCardLayout: root.decadeCardLayout
                    cardTypography: root.cardTypography
                    submitOnEnter: root.submitParametersOnEnter
                    onSubmitRequested: {
                        if (root.displayedTool.id && !root.controller.running)
                            root.runSelectedTool()
                    }
                }

                DeviceSelector {
                    width: parent.width
                    visible: !!root.displayedTool.uses_android_device && !root.deviceInTitleBar
                    controller: root.androidBackend
                    toolId: root.displayedTool.id || ""
                    requiredDevice: !!root.displayedTool.requires_android_device
                    explicitTarget: !!root.displayedTool.android_explicit_target
                }
            }
        }

        Item {
            id: actionArea
            objectName: "customActionArea"
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: root.panelPadding
            anchors.rightMargin: root.panelPadding
            anchors.bottomMargin: root.splitConsole ? root.panelPadding : 0
            height: root.actionsInTitleBar ? 0 : actionFlow.implicitHeight
            visible: !root.actionsInTitleBar

            Flow {
                id: actionFlow
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                spacing: Theme.space8
                layoutDirection: root.allowManagement ? Qt.LeftToRight : Qt.RightToLeft

                readonly property real halfButtonWidth: (width - spacing) / 2

                PrimaryButton {
                    id: editButton
                    showHoverTips: !root.decadeCardLayout && compact
                    objectName: "customEditButton"
                    visible: root.allowManagement
                    width: root.narrowManagementLayout
                        ? actionFlow.halfButtonWidth : Theme.detailActionWidth
                    height: Theme.controlHeightSmall
                    radius: Theme.radiusSmall
                    text: "编辑脚本"
                    iconName: ""
                    tonal: true
                    color: hovered ? _visualPalette.surfaceContainer : _visualPalette.surfaceContainerLow
                    border.color: _visualPalette.outline
                    foregroundColor: _visualPalette.textPrimary
                    labelFontSize: Theme.fontSupporting
                    labelFontWeight: Font.Normal
                    glyphSize: 18
                    contentSpacing: 7
                    enabled: !!root.displayedTool.editable && !root.controller.running
                    onClicked: root.editRequested()
                }

                PrimaryButton {
                    objectName: "customDeleteButton"
                    showHoverTips: !root.decadeCardLayout && compact
                    visible: root.allowManagement
                    width: root.narrowManagementLayout
                        ? actionFlow.halfButtonWidth : Theme.detailActionWidth
                    height: Theme.controlHeightSmall
                    radius: Theme.radiusSmall
                    tonal: true
                    color: _visualPalette.dangerAction
                    border.color: _visualPalette.errorColor
                    text: "删除脚本"
                    iconName: ""
                    foregroundColor: _visualPalette.textPrimary
                    labelFontSize: Theme.fontSupporting
                    labelFontWeight: Font.Normal
                    glyphSize: 18
                    contentSpacing: 7
                    enabled: !!root.displayedTool.id && !root.controller.running
                    onClicked: root.deleteRequested()
                }

                Item {
                    visible: root.allowManagement && !root.narrowManagementLayout
                    width: Math.max(0, actionFlow.width
                        - Theme.detailActionWidth * 2 - Theme.detailRunWidth
                        - actionFlow.spacing * 3)
                    height: Theme.controlHeightSmall
                }

                PrimaryButton {
                    id: runButton
                    showHoverTips: !root.decadeCardLayout && compact
                    objectName: "customRunButton"
                    width: root.allowManagement
                        ? (root.narrowManagementLayout
                            ? actionFlow.width : Theme.detailRunWidth)
                        : Math.min(Theme.detailRunWidth, actionFlow.width)
                    height: Theme.controlHeightSmall
                    radius: Theme.radiusSmall
                    text: root.controller.running ? "停止运行" : "运行脚本"
                    iconName: root.controller.running ? "stop" : "play_arrow"
                    tonal: true
                    color: hovered ? _visualPalette.primaryHover : _visualPalette.primary
                    border.width: 0
                    foregroundColor: "white"
                    labelFontSize: Theme.fontSupporting
                    labelFontWeight: Font.Medium
                    glyphSize: 16
                    contentSpacing: 6
                    enabled: !!root.displayedTool.id
                    onClicked: root.runSelectedTool()
                }
            }
        }

    }

    Item {
        id: consoleSeparator
        objectName: "customConsoleSeparator"
        visible: root.splitConsole
        width: parent.width
        y: formPanel.height
        height: root.separatorHeight

        Rectangle {
            anchors.centerIn: parent
            width: 40
            height: 3
            radius: 1.5
            color: separatorMouse.containsMouse || separatorMouse.pressed
                ? _visualPalette.primary : _visualPalette.outline
            visible: root.consoleExpanded
        }
        MouseArea {
            id: separatorMouse
            objectName: "customConsoleResizeHandle"
            anchors.fill: parent
            enabled: root.consoleExpanded && root.consoleReveal === 1
            hoverEnabled: true
            cursorShape: Qt.SizeVerCursor
            property real startY: 0
            property real startHeight: 0
            onPressed: function(mouse) {
                startY = mapToItem(root, mouse.x, mouse.y).y
                startHeight = consolePanel.height
            }
            onPositionChanged: function(mouse) {
                if (!pressed)
                    return
                const delta = startY - mapToItem(root, mouse.x, mouse.y).y
                const requested = Math.max(consolePanel.minimumSplitHeight,
                    Math.min(consolePanel.maximumSplitHeight, startHeight + delta))
                root.consoleHeightRatio = requested / Math.max(1, root.height)
            }
        }
    }

    Rectangle {
        id: consolePanel
        objectName: "customConsolePanel"
        x: root.splitConsole ? 0 : root.panelPadding
        width: parent.width - x * 2
        readonly property real maximumSplitHeight: Math.max(Theme.consoleHeaderHeight,
            root.height - header.height - actionArea.height
            - root.panelPadding * 2 - Theme.inputHeight - root.separatorHeight)
        readonly property real minimumSplitHeight: Math.min(140, maximumSplitHeight)
        readonly property real formReservedHeight: Math.max(root.minimumFormReservedHeight,
            parameterArea.y + Math.min(parameterColumn.height, Theme.detailFormMaximumVisibleHeight)
            + actionArea.height + Theme.space8 * 2 + root.panelPadding)
        readonly property real expandedHeight: root.splitConsole
                ? Math.max(minimumSplitHeight,
                    Math.min(maximumSplitHeight, root.height * root.consoleHeightRatio))
                : Math.min(root.compactLayout ? root.height : Theme.consoleMaximumHeight,
                       Math.max(Math.min(Theme.consoleMinimumHeight,
                           Math.max(Theme.consoleHeaderHeight, root.height - parameterArea.y
                               - actionArea.height - root.panelPadding * 2)),
                           root.height - formReservedHeight))
        height: Theme.consoleHeaderHeight
            + (expandedHeight - Theme.consoleHeaderHeight) * root.consoleReveal
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.splitConsole ? 0 : root.panelPadding
        radius: 9
        color: _visualPalette.glassMode ? "transparent" : _visualPalette.consoleBackground
        GlassSurface {
            anchors.fill: parent; cornerRadius: parent.radius; z: -0.5
            tintColor: _visualPalette.consoleBackground; tintStrength: 0.94
        }
        border.width: root.decadeCardLayout ? Theme.borderWidthThin : 0
        border.color: _visualPalette.outline
        clip: true

        function scrollConsoleToBottom() {
            if (!root.consoleExpanded || !consoleScroll.contentItem)
                return

            var flickable = consoleScroll.contentItem
            flickable.contentY = Math.max(0, flickable.contentHeight - flickable.height)
        }

        onHeightChanged: Qt.callLater(scrollConsoleToBottom)

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: Theme.consoleHeaderHeight
            radius: Theme.radiusConsole
            color: _visualPalette.glassMode ? "transparent" : _visualPalette.consoleHeaderBackground
            GlassSurface {
                anchors.fill: parent; cornerRadius: parent.radius; z: -0.5
                tintColor: _visualPalette.consoleHeaderBackground
                tintStrength: 0.82; minimumTintOpacity: 0.74
            }
            RowLayout {
                objectName: "customConsoleHeader"
                anchors.fill: parent
                anchors.leftMargin: root.compactConsoleActions ? 12 : 15
                anchors.rightMargin: root.compactConsoleActions ? 12 : 15
                spacing: root.compactConsoleActions ? 6 : 10
                MaterialIcon {
                    visible: root.decadeCardLayout
                    icon: "terminal"; iconSize: 24; color: _visualPalette.consoleText
                }
                Text {
                    text: "控制台输出"; color: _visualPalette.consoleText
                    font.pixelSize: root.cardTypography ? LauncherStyle.decadeCardTextSize : Theme.fontSupporting
                    font.weight: _visualPalette.glassMode && root.cardTypography ? Font.Bold : Font.DemiBold
                    MouseArea {
                        anchors.fill: parent
                        enabled: root.decadeCardLayout
                        onClicked: root.consoleExpanded = !root.consoleExpanded
                    }
                }
                Item { visible: !root.compactConsoleActions; Layout.preferredWidth: 20 }
                Rectangle {
                    visible: !root.decadeCardLayout
                    Layout.preferredWidth: 8
                    Layout.preferredHeight: 8
                    radius: Theme.radiusTiny
                    color: root.consoleStatusColor
                    Accessible.name: root.controller.statusText
                }
                Text {
                    visible: !root.decadeCardLayout && root.showConsoleStatusText
                    text: root.controller.statusText
                    color: root.consoleStatusColor
                    font.pixelSize: Theme.fontCaption
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    objectName: "customConsoleRunButton"
                    showHoverTips: !root.decadeCardLayout && compact
                    visible: root.splitConsole
                    enabled: !!root.displayedTool.id
                    implicitWidth: root.compactConsoleActions ? 30 : 90
                    implicitHeight: 30
                    radius: Theme.radiusTiny
                    text: root.controller.running ? "停止运行" : "运行脚本"
                    iconName: root.controller.running ? "stop" : "play_arrow"
                    compact: root.compactConsoleActions
                    Accessible.name: text
                    tonal: true
                    color: hovered ? _visualPalette.consoleBackground : "transparent"
                    border.width: 0
                    foregroundColor: root.controller.running ? _visualPalette.consoleError : _visualPalette.success
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 16
                    contentSpacing: 4
                    onClicked: root.runSelectedTool()
                }
                PrimaryButton {
                    objectName: "customConsoleCopyButton"
                    showHoverTips: !root.decadeCardLayout && compact
                    visible: !root.decadeCardLayout
                    implicitWidth: root.compactConsoleActions ? 30 : 82
                    implicitHeight: 30
                    radius: Theme.radiusTiny
                    text: "复制输出"
                    iconName: "content_copy"
                    compact: root.compactConsoleActions
                    Accessible.name: "复制控制台输出"
                    tonal: true
                    color: "transparent"
                    border.width: 0
                    foregroundColor: hovered ? _visualPalette.consoleText : _visualPalette.consoleMuted
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 15
                    contentSpacing: 4
                    onClicked: { consoleText.selectAll(); consoleText.copy(); consoleText.deselect() }
                }
                Item { visible: !root.compactConsoleActions; Layout.preferredWidth: 8 }
                PrimaryButton {
                    objectName: "customConsoleClearButton"
                    showHoverTips: !root.decadeCardLayout && compact
                    visible: !root.decadeCardLayout || root.consoleExpanded
                    implicitWidth: root.compactConsoleActions ? 30 : 62
                    implicitHeight: 30
                    radius: Theme.radiusTiny
                    text: "清空"
                    iconName: root.decadeCardLayout ? "delete_outline" : "delete_sweep"
                    compact: root.compactConsoleActions
                    Accessible.name: "清空控制台输出"
                    tonal: true
                    color: "transparent"
                    border.width: 0
                    foregroundColor: hovered ? _visualPalette.consoleText : _visualPalette.consoleMuted
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 15
                    contentSpacing: 4
                    onClicked: root.controller.clearConsole()
                }
                PrimaryButton {
                    objectName: "customConsoleToggle"
                    showHoverTips: !root.decadeCardLayout && compact
                    implicitWidth: root.compactConsoleActions ? 30 : 66
                    implicitHeight: 30
                    radius: Theme.radiusTiny
                    text: root.consoleExpanded ? "收起" : "展开"
                    iconName: root.decadeCardLayout
                        ? (root.consoleExpanded ? "expand_less" : "expand_more")
                        : (root.consoleExpanded ? "expand_more" : "expand_less")
                    compact: root.compactConsoleActions
                    Accessible.name: root.consoleExpanded ? "收起控制台输出" : "展开控制台输出"
                    tonal: true
                    color: hovered ? _visualPalette.consoleBackground : "transparent"
                    border.width: 0
                    foregroundColor: _visualPalette.consoleText
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 16
                    contentSpacing: 4
                    onClicked: root.consoleExpanded = !root.consoleExpanded
                }
            }
        }

        Connections {
            target: root
            function onConsoleExpandedChanged() {
                Qt.callLater(consolePanel.scrollConsoleToBottom)
            }
        }

        DesktopScrollView {
            id: consoleScroll
            objectName: "customConsoleScroll"
            visible: height > 0
            opacity: root.consoleReveal
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.topMargin: root.decadeCardLayout ? Theme.consoleHeaderHeight + Theme.space8 : 51
            anchors.bottom: footer.top
            anchors.leftMargin: Theme.space12
            anchors.rightMargin: Theme.space12
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            TextArea {
                id: consoleText
                objectName: "customConsoleText"
                width: consoleScroll.availableWidth
                // Keep the document alive while output grows. Replacing text on
                // every batch resets layout and the viewport before tail scrolling.
                property string output: root.controller.consoleText
                property string renderedOutput: ""
                function updateOutput() {
                    if (output === renderedOutput)
                        return
                    if (output.startsWith(renderedOutput))
                        insert(length, output.slice(renderedOutput.length))
                    else
                        text = output // Clear or bounded-history truncation.
                    renderedOutput = output
                }
                onOutputChanged: updateOutput()
                Component.onCompleted: updateOutput()
                textFormat: TextEdit.PlainText
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.WrapAnywhere
                color: _visualPalette.consoleText
                selectionColor: _visualPalette.primary
                selectedTextColor: "white"
                font.family: "Cascadia Mono"
                font.pixelSize: Theme.fontCaption
                background: null
                AppTextEditMenu { target: consoleText }
                onTextChanged: Qt.callLater(consolePanel.scrollConsoleToBottom)
                onContentHeightChanged: Qt.callLater(consolePanel.scrollConsoleToBottom)
            }
        }

        Rectangle {
            id: footer
            radius: Theme.radiusConsole
            visible: !root.decadeCardLayout && consolePanel.height > Theme.consoleHeaderHeight + height
            opacity: root.consoleReveal
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: root.decadeCardLayout ? 0 : Theme.consoleFooterHeight
            color: _visualPalette.glassMode ? "transparent" : _visualPalette.consoleBackground
            GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.consoleBackground; z: -0.5 }
            border.color: _visualPalette.darkMode ? "#2A3442" : "#25303D"
            border.width: _visualPalette.glassMode ? 0 : 1
            Text { anchors.left: parent.left; anchors.leftMargin: 15; anchors.verticalCenter: parent.verticalCenter; text: "脚本输出"; color: _visualPalette.consoleMuted; font.pixelSize: Theme.fontSmall }
            Text { anchors.right: parent.right; anchors.rightMargin: 15; anchors.verticalCenter: parent.verticalCenter; text: root.controller.statusText; color: _visualPalette.consoleMuted; font.pixelSize: Theme.fontSmall }
        }
    }

}
