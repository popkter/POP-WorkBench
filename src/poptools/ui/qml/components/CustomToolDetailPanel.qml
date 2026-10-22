pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root
    objectName: "customToolDetailPanel"

    required property var controller
    required property var androidBackend
    required property var parentWindow
    required property var parameterValues
    required property var displayedTool
    property bool splitConsole: false
    property bool consoleExpanded: !splitConsole || controller.running
    property real consoleReveal: consoleExpanded ? 1 : 0
    Behavior on consoleReveal {
        enabled: root.splitConsole
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
        if (splitConsole && executionRunning)
            consoleExpanded = true
    }
    property bool allowManagement: true
    property bool actionsInTitleBar: false
    property bool deviceInTitleBar: false
    property bool externalRun: false
    property bool submitParametersOnEnter: false
    property bool compactLayout: false
    readonly property real panelPadding: compactLayout ? Theme.space8 : Theme.detailPanelPadding
    property real minimumFormReservedHeight: Theme.detailFormReservedHeight
    readonly property bool narrowManagementLayout: allowManagement && width < Theme.detailCompactWidth
    readonly property bool compactConsoleActions: consolePanel.width < (splitConsole ? 560 : 458)
    readonly property bool showConsoleStatusText: !compactConsoleActions
        || consolePanel.width >= (splitConsole ? 340 : 280)
    readonly property color consoleStatusColor: controller.running ? Theme.consoleWarning
        : controller.statusText === "执行成功" ? Theme.success
        : controller.statusText.indexOf("执行失败") === 0 ? Theme.consoleError
        : Theme.consoleMuted

    signal editRequested()
    signal deleteRequested()
    signal confirmRunRequested(var values)
    signal runRequested()
    signal toastRequested(string message, bool error)

    radius: Theme.radiusMedium
    color: splitConsole ? "transparent" : Theme.surfaceContainerLow
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
        return kind === "python" ? Theme.tertiary
            : kind === "batch" ? Theme.success : Theme.runtimeBadgeText
    }

    function kindBackground() {
        const kind = root.displayedTool.executor ? root.displayedTool.executor.kind : ""
        return kind === "python" ? Theme.tertiaryContainer
            : kind === "batch" ? Theme.successContainer : Theme.runtimeBadge
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
        color: root.splitConsole ? Theme.surfaceContainerLow : "transparent"
        border.width: 0
        clip: true

        Item {
            id: header
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            height: headingRow.implicitHeight + root.panelPadding * 2

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
                        color: Theme.textPrimary
                        font.pixelSize: root.compactLayout ? Theme.fontSectionTitle : Theme.fontDetailTitle
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: root.displayedTool.description || "选择脚本以查看参数、运行状态和输出"
                        color: Theme.textSecondary
                        font.pixelSize: root.compactLayout ? Theme.fontSupporting : Theme.fontBody
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
                color: Theme.outlineVariant
            }
        }

        Flickable {
            id: parameterArea
            objectName: "customParameterArea"
            x: root.panelPadding
            anchors.top: header.bottom
            anchors.topMargin: root.compactLayout ? Theme.space8 : Theme.space12
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
                    objectName: "customEditButton"
                    visible: root.allowManagement
                    width: root.narrowManagementLayout
                        ? actionFlow.halfButtonWidth : Theme.detailActionWidth
                    height: Theme.controlHeightSmall
                    radius: Theme.radiusSmall
                    text: "编辑脚本"
                    iconName: ""
                    tonal: true
                    color: hovered ? Theme.surfaceContainer : Theme.surfaceContainerLow
                    border.color: Theme.outline
                    foregroundColor: Theme.textPrimary
                    labelFontSize: Theme.fontSupporting
                    labelFontWeight: Font.Normal
                    glyphSize: 18
                    contentSpacing: 7
                    enabled: !!root.displayedTool.editable && !root.controller.running
                    onClicked: root.editRequested()
                }

                PrimaryButton {
                    objectName: "customDeleteButton"
                    visible: root.allowManagement
                    width: root.narrowManagementLayout
                        ? actionFlow.halfButtonWidth : Theme.detailActionWidth
                    height: Theme.controlHeightSmall
                    radius: Theme.radiusSmall
                    tonal: true
                    color: Theme.dangerAction
                    border.color: Theme.errorColor
                    text: "删除脚本"
                    iconName: ""
                    foregroundColor: Theme.textPrimary
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
                    color: hovered ? Theme.primaryHover : Theme.primary
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
                ? Theme.primary : Theme.outline
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
        color: Theme.consoleBackground
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
            color: Theme.consoleHeaderBackground
            RowLayout {
                objectName: "customConsoleHeader"
                anchors.fill: parent
                anchors.leftMargin: root.compactConsoleActions ? 12 : 15
                anchors.rightMargin: root.compactConsoleActions ? 12 : 15
                spacing: root.compactConsoleActions ? 6 : 10
                Text { text: "控制台输出"; color: Theme.consoleText; font.pixelSize: Theme.fontSupporting; font.weight: Font.DemiBold }
                Item { visible: !root.compactConsoleActions; Layout.preferredWidth: 20 }
                Rectangle {
                    Layout.preferredWidth: 8
                    Layout.preferredHeight: 8
                    radius: Theme.radiusTiny
                    color: root.consoleStatusColor
                    Accessible.name: root.controller.statusText
                }
                Text {
                    visible: root.showConsoleStatusText
                    text: root.controller.statusText
                    color: root.consoleStatusColor
                    font.pixelSize: Theme.fontCaption
                }
                Item { Layout.fillWidth: true }
                PrimaryButton {
                    objectName: "customConsoleRunButton"
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
                    color: hovered ? Theme.consoleBackground : "transparent"
                    border.width: 0
                    foregroundColor: root.controller.running ? Theme.consoleError : Theme.success
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 16
                    contentSpacing: 4
                    onClicked: root.runSelectedTool()
                }
                PrimaryButton {
                    objectName: "customConsoleCopyButton"
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
                    foregroundColor: hovered ? Theme.consoleText : Theme.consoleMuted
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 15
                    contentSpacing: 4
                    onClicked: { consoleText.selectAll(); consoleText.copy(); consoleText.deselect() }
                }
                Item { visible: !root.compactConsoleActions; Layout.preferredWidth: 8 }
                PrimaryButton {
                    objectName: "customConsoleClearButton"
                    implicitWidth: root.compactConsoleActions ? 30 : 62
                    implicitHeight: 30
                    radius: Theme.radiusTiny
                    text: "清空"
                    iconName: "delete_sweep"
                    compact: root.compactConsoleActions
                    Accessible.name: "清空控制台输出"
                    tonal: true
                    color: "transparent"
                    border.width: 0
                    foregroundColor: hovered ? Theme.consoleText : Theme.consoleMuted
                    labelFontSize: 12
                    labelFontWeight: Font.Normal
                    glyphSize: 15
                    contentSpacing: 4
                    onClicked: root.controller.clearConsole()
                }
                PrimaryButton {
                    objectName: "customConsoleToggle"
                    implicitWidth: root.compactConsoleActions ? 30 : 66
                    implicitHeight: 30
                    radius: Theme.radiusTiny
                    text: root.consoleExpanded ? "收起" : "展开"
                    iconName: root.consoleExpanded ? "expand_more" : "expand_less"
                    compact: root.compactConsoleActions
                    Accessible.name: root.consoleExpanded ? "收起控制台输出" : "展开控制台输出"
                    tonal: true
                    color: hovered ? Theme.consoleBackground : "transparent"
                    border.width: 0
                    foregroundColor: Theme.consoleText
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
            anchors.topMargin: 51
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
                color: Theme.consoleText
                selectionColor: Theme.primary
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
            visible: consolePanel.height > Theme.consoleHeaderHeight + height
            opacity: root.consoleReveal
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: Theme.consoleFooterHeight
            color: Theme.consoleBackground
            border.color: Theme.darkMode ? "#2A3442" : "#25303D"
            border.width: 1
            Text { anchors.left: parent.left; anchors.leftMargin: 15; anchors.verticalCenter: parent.verticalCenter; text: "脚本输出"; color: Theme.consoleMuted; font.pixelSize: Theme.fontSmall }
            Text { anchors.right: parent.right; anchors.rightMargin: 15; anchors.verticalCenter: parent.verticalCenter; text: root.controller.statusText; color: Theme.consoleMuted; font.pixelSize: Theme.fontSmall }
        }
    }

}
