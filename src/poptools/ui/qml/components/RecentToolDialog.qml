import QtQuick
import QtQuick.Controls
import QtQuick.Effects
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

Window {
    id: root
    objectName: "recentToolWindow"
    transientParent: null
    title: root.toolController.selectedTool.title || "运行工具"

    property string toolId: ""
    property var toolController: appController
    property bool ownsController: false
    readonly property bool keepsFloatingLauncherVisible: true
    signal dismissed(string dismissedToolId)

    onClosing: dismissed(toolId)
    Component.onDestruction: {
        if (ownsController && toolController)
            toolController.dispose()
    }
    property var parameterValues: ({})
    property var presetUtilities
    property var deviceController
    property var jiraFeishuBackend
    readonly property bool presetMode: root.toolController.selectedTool.workspace === "preset"
    readonly property bool customScriptMode: root.toolController.selectedTool.section === "custom"
        && root.toolController.selectedTool.workspace === "command"
    readonly property bool recordingPreset: presetMode
        && root.toolController.selectedTool.executor
        && root.toolController.selectedTool.executor.command === "recording"
    readonly property bool operationRunning: recordingPreset
        ? presetUtilities && presetUtilities.recording
        : root.toolController.running
    readonly property real consolePreferredHeight: 292
    readonly property real bodySpacing: 12

    width: customScriptMode ? 440 : presetMode ? 720 : 680
    height: Math.min(customScriptMode ? 680 : presetMode ? 560 : 600, Screen.height - 48)
    visible: false
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"

    function centerOnScreen() {
        x = Screen.virtualX + Math.round((Screen.width - width) / 2)
        y = Screen.virtualY + Math.round((Screen.height - height) / 2)
    }

    function showWithTool(tid) {
        toolId = tid
        if (ownsController && toolController)
            toolController.dispose()
        var session = appController.createToolSession(tid)
        if (!session)
            return
        toolController = session
        ownsController = true
        session.attachWindow(root)
        var values = {}
        var tool = root.toolController.selectedTool
        var parameters = tool.parameters || []
        for (var i = 0; i < parameters.length; i++)
            values[parameters[i].id] = parameters[i].default
        parameterValues = values
        session.placeWindow()
        visible = true
        requestActivate()
    }

    function toggleRecording() {
        if (!presetUtilities || !deviceController)
            return
        if (presetUtilities.recording) {
            presetUtilities.stopRecording()
            if (!presetUtilities.recordingOutputDirectory
                || presetUtilities.recordingOutputDirectory.length === 0)
                if (workspaceLoader.item && workspaceLoader.item.openRecordingFolderDialog)
                    workspaceLoader.item.openRecordingFolderDialog()
        } else {
            const device = deviceController.selectedAndroidDevice
            if (device.available)
                presetUtilities.startRecording(device.serial)
        }
    }

    function runCustomScript() {
        if (root.toolController.running)
            root.toolController.stopExecution()
        else
            root.toolController.runSelected(root.parameterValues)
    }

    // ── Main content ───────────────────────────────────────
    MultiEffect {
        id: dialogShadow
        anchors.fill: contentRect
        source: contentRect
        shadowEnabled: true
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
        anchors.margins: root.customScriptMode ? Theme.space4 : Theme.space8
        radius: root.customScriptMode ? Theme.radiusMedium : Theme.radiusLarge
        color: root.customScriptMode ? Theme.chromeBackground
            : Theme.darkMode ? Theme.surfaceContainer : Theme.surface
        border.width: root.customScriptMode ? 1 : 0
        border.color: Theme.outlineVariant
        clip: true

        ColumnLayout {
            anchors.fill: parent
            spacing: 0

            // ── Title bar ─────────────────────────────────
            Rectangle {
                id: dialogTitleBar
                Layout.fillWidth: true
                Layout.preferredHeight: root.customScriptMode ? 40 : 56
                color: "transparent"

                // Drag-to-move area (covers title bar, behind interactive elements)
                MouseArea {
                    anchors.left: parent.left
                    anchors.right: titleButtons.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    onPressed: root.startSystemMove()
                }

                Image {
                    visible: root.customScriptMode
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
                    visible: !root.customScriptMode
                    anchors.left: parent.left
                    anchors.leftMargin: root.customScriptMode ? 40 : Theme.space20
                    anchors.right: titleButtons.left
                    anchors.rightMargin: Theme.space12
                    anchors.verticalCenter: parent.verticalCenter
                    text: root.customScriptMode ? "泡泡工具箱"
                        : root.toolController.selectedTool.title || "运行工具"
                    color: root.customScriptMode ? Theme.chromeForeground : Theme.textPrimary
                    font.pixelSize: root.customScriptMode ? Theme.fontSupporting : Theme.fontSectionTitle
                    font.weight: root.customScriptMode ? Font.Medium : Font.Bold
                    elide: Text.ElideRight
                }

                // Buttons row (right-aligned)
                Row {
                    id: titleButtons
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    spacing: Theme.space4

                    // ── Custom command run button ─────────
                    PrimaryButton {
                        objectName: "recentToolRunButton"
                        visible: !root.presetMode
                        width: root.customScriptMode ? 102 : 48
                        height: root.customScriptMode ? Theme.captionActionHeight : 32
                        anchors.verticalCenter: parent.verticalCenter
                        compact: !root.customScriptMode
                        text: root.operationRunning ? "停止运行"
                            : root.customScriptMode ? "运行脚本" : "运行工具"
                        iconName: root.operationRunning ? "stop" : "play_arrow"
                        glyphSize: root.customScriptMode ? 20 : 24
                        tonal: true
                        foregroundColor: root.customScriptMode
                            ? (root.operationRunning ? Theme.errorColor : Theme.success) : "white"
                        border.width: 0
                        radius: root.customScriptMode ? Theme.radiusTiny : Theme.radiusMedium
                        color: root.customScriptMode
                            ? (hovered ? Theme.navigationHover : "transparent")
                            : root.operationRunning
                            ? (hovered ? Qt.darker(Theme.errorColor, 1.1) : Theme.errorColor)
                            : (hovered ? Theme.primaryHover : Theme.primary)
                        labelFontSize: Theme.fontSupporting
                        labelFontWeight: Font.Normal
                        Accessible.role: Accessible.Button
                        Accessible.name: text
                        Accessible.onPressAction: if (enabled) clicked()
                        onClicked: root.runCustomScript()
                    }

                    DeviceSelector {
                        objectName: "recentToolDeviceSelector"
                        visible: root.customScriptMode && !!root.deviceController
                        width: root.customScriptMode ? 148 : 160
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        controller: root.deviceController
                        toolId: root.toolId
                        requiredDevice: !!root.toolController.selectedTool.requires_android_device
                        explicitTarget: !!root.toolController.selectedTool.android_explicit_target
                    }

                    PrimaryButton {
                        visible: root.recordingPreset
                        width: 132
                        height: 36
                        anchors.verticalCenter: parent.verticalCenter
                        text: (presetUtilities && presetUtilities.exporting)
                              ? "正在导出"
                              : (root.operationRunning ? "结束录制" : "开始录制")
                        iconName: (presetUtilities && presetUtilities.exporting)
                                  ? "hourglass_top"
                                  : (root.operationRunning ? "stop" : "play_arrow")
                        successStyle: root.operationRunning
                        enabled: !(presetUtilities && presetUtilities.exporting)
                        onClicked: root.toggleRecording()
                    }

                    // Minimize
                    Rectangle {
                        objectName: "recentToolMinimizeButton"
                        width: 42; height: parent.height
                        color: minimizeArea.containsMouse ? Theme.surfaceContainerHigh : "transparent"
                        MaterialIcon {
                            anchors.centerIn: parent; icon: "remove"; iconSize: 19; color: Theme.textPrimary
                        }
                        MouseArea {
                            id: minimizeArea; anchors.fill: parent; hoverEnabled: true; onClicked: root.showMinimized()
                        }
                    }

                    // Close
                    Rectangle {
                        objectName: "recentToolCloseButton"
                        width: 42; height: parent.height
                        topRightRadius: contentRect.radius
                        color: closeArea.containsMouse ? "#C42B1C" : "transparent"
                        MaterialIcon {
                            anchors.centerIn: parent
                            icon: "close"
                            iconSize: 19
                            color: closeArea.containsMouse ? "white" : Theme.textPrimary
                        }
                        MouseArea {
                            id: closeArea; anchors.fill: parent; hoverEnabled: true; onClicked: root.close()
                        }
                    }
                }
            }

            Loader {
                id: customScriptLoader
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.margins: 0
                active: root.customScriptMode
                visible: active
                sourceComponent: CustomToolDetailPanel {
                    controller: root.toolController
                    androidBackend: root.deviceController
                    parentWindow: root
                    parameterValues: root.parameterValues
                    displayedTool: root.toolController.selectedTool
                    allowManagement: false
                    actionsInTitleBar: true
                    deviceInTitleBar: true
                    externalRun: true
                    compactLayout: true
                    minimumFormReservedHeight: 0
                    onRunRequested: root.runCustomScript()
                }
            }

            // ── Body ──────────────────────────────────────
            Item {
                id: dialogBody
                visible: !root.customScriptMode
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
                        text: root.toolController.selectedTool.description || ""
                        color: Theme.textSecondary
                        Layout.leftMargin: 20
                        Layout.rightMargin: 20
                        font.pixelSize: Theme.fontBody
                        wrapMode: Text.WordWrap
                    }

                    Loader {
                        id: workspaceLoader
                        active: !root.customScriptMode
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
                        sourceComponent: root.toolController.selectedTool.workspace === "preset"
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
                        dialogBody.height - workspaceTop - root.bodySpacing)
                    readonly property real parameterLimitedHeight: Math.max(
                        minimumExpandedHeight,
                        dialogBody.height - parameterContentBottom - root.bodySpacing)
                    visible: !root.presetMode
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: visible ? Math.min(implicitHeight, parent.height) : 0
                    minimumVisibleLineCount: 5
                    preferredExpandedHeight: Math.max(
                        minimumExpandedHeight,
                        Math.min(root.consolePreferredHeight,
                                 fixedExpandedHeight,
                                 parameterLimitedHeight))
                    maximumExpandedHeight: fixedExpandedHeight
                    resizable: false
                    controller: root.toolController
                }
            }
        }
    }

    Component {
        id: commandWorkspace
        CommandWorkspace {
            controller: root.toolController
            androidController: root.deviceController
            parentWindow: root
            parameterValues: root.parameterValues
            scrcpySelected: root.toolController.selectedTool.workspace === "scrcpy"
            overlaysVisible: false
        }
    }

    Component {
        id: presetWorkspace
        PresetWorkspace {
            toolController: root.toolController
            utilities: root.presetUtilities
            androidBackend: root.deviceController
            jiraFeishuBackend: root.jiraFeishuBackend
            compact: true
        }
    }
}
