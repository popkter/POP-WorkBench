import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "components"
import "theme"

ApplicationWindow {
    id: window
    minimumWidth: Theme.windowMinimumWidth
    minimumHeight: Theme.windowMinimumHeight
    width: Theme.windowDefaultWidth
    height: Theme.windowDefaultHeight
    visible: false
    title: "泡泡工具箱"
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint
        | Qt.WindowMinMaxButtonsHint | Qt.WindowCloseButtonHint
    readonly property bool customTitleBar: Qt.platform.os === "windows"
    property var chromeController: null
    property int captionHovered: -1
    property int captionPressed: -1
    property rect titleBarActionsRect: Qt.rect(0, 0, 0, 0)
    property bool modernCaptionControls: true
    readonly property int captionControlWidth: Theme.captionControlWidth
    readonly property color chromeBackgroundColor: Theme.chromeBackground
    readonly property color chromeForegroundColor: Theme.chromeForeground
    property real nativeTitleBarHeight: 0
    readonly property real titleBarHeight: customTitleBar ? Theme.navigationRailWidth
        : Math.max(Theme.navigationRailWidth, nativeTitleBarHeight)
    readonly property real titleBarContentInset: customTitleBar ? titleBarHeight
        : titleBarHeight - nativeTitleBarHeight
    color: chromeBackgroundColor
    palette.window: chromeBackgroundColor
    palette.windowText: Theme.textPrimary
    palette.base: Theme.surfaceContainerLow
    palette.text: Theme.textPrimary
    palette.button: Theme.surfaceContainer
    palette.buttonText: Theme.textPrimary
    palette.highlight: Theme.primary
    palette.highlightedText: Theme.primaryForeground
    palette.placeholderText: Theme.textSecondary

    Binding {
        target: Theme
        property: "darkMode"
        value: settingsController.darkTheme
    }

    property var parameterValues: ({})
    property string toolSearchQuery: ""
    readonly property real primaryNavWidth: titleBarHeight
    readonly property real toolListWidth: Math.max(
        minimumToolListWidth,
        Math.min(maximumNavigationWidth,
                 width - primaryNavWidth - minimumContentWidth))
    property bool developerSelected: false
    property bool settingsSelected: false
    property bool terminalEnablePending: false
    property bool updateDialogPending: false
    readonly property real minimumToolListWidth: 120
    readonly property real maximumNavigationWidth: Theme.navigationMaximumWidth
    readonly property real minimumContentWidth: 480
    readonly property real minimumContentHeight: 480
    property bool compactPrimaryNav: true
    readonly property bool compactToolList: toolListWidth < 190
    readonly property bool compactContentActions: width < 760
    readonly property bool compactHeight: height < 620
    readonly property bool scrcpySelected:
        appController.selectedTool.workspace === "scrcpy"
    readonly property bool applicationOverlayVisible:
        executionCapacityDialog.visible
        || customScriptImportDialog.visible
        || powershellPluginDialog.visible
        || (updateDialogLoader.item && updateDialogLoader.item.visible)
        || (commandEditorDialogLoader.item && commandEditorDialogLoader.item.visible)
        || (deleteCommandDialogLoader.item && deleteCommandDialogLoader.item.visible)
        || (confirmRunDialogLoader.item && confirmRunDialogLoader.item.visible)
        || (pythonDoctorDialogLoader.item && pythonDoctorDialogLoader.item.visible)
        || (userGuideDialogLoader.item && userGuideDialogLoader.item.visible)

    onToolSearchQueryChanged: appController.setToolSearchQuery(toolSearchQuery)
    function openTerminalPage() {
        if (!developerConsoleController.pluginInstalled) {
            window.requestTerminalEnable()
            return
        }
        window.hideScrcpyWindow()
        window.developerSelected = true
        window.settingsSelected = false
        developerConsoleController.ensureStarted()
    }

    function openCustomScriptsPage() {
        window.hideScrcpyWindow()
        window.developerSelected = false
        window.settingsSelected = false
        appController.navigate("custom")
    }

    Shortcut {
        sequence: "Ctrl+T"
        context: Qt.WindowShortcut
        autoRepeat: false
        enabled: !window.applicationOverlayVisible
        onActivated: {
            if (window.developerSelected && !window.settingsSelected) {
                if (developerConsoleController.canCreateTerminalTab)
                    developerConsoleController.createTerminalTab()
            } else {
                window.openTerminalPage()
            }
        }
    }

    Shortcut {
        sequence: "Ctrl+Q"
        context: Qt.WindowShortcut
        autoRepeat: false
        enabled: !window.applicationOverlayVisible
        onActivated: window.openCustomScriptsPage()
    }

    function openSettingsDialog() {
        developerSelected = false
        settingsSelected = true
        hideScrcpyWindow()
    }

    Connections {
        target: androidController
        function onPluginManagementRequested() { window.openSettingsDialog() }
    }

    function openCommandEditorForCreate(command, kind) {
        commandEditorDialogLoader.active = true
        Qt.callLater(function () { commandEditorDialogLoader.item.openForCreate(command, kind) })
    }

    function openCommandEditorForEdit() {
        commandEditorDialogLoader.active = true
        Qt.callLater(function () { commandEditorDialogLoader.item.openForEdit() })
    }

    function openDeleteCommandDialog() {
        deleteCommandDialogLoader.active = true
        Qt.callLater(function () { deleteCommandDialogLoader.item.open() })
    }

    function importCustomScriptFromClipboard() {
        var result = appController.importScriptFromClipboard()
        if (result.status === "duplicate") {
            customScriptImportDialog.openForReplacement(result)
        } else if (result.status === "error") {
            customScriptImportDialog.openForError(
                result.message || "剪贴板内容无法导入")
        } else {
            customTransferToast.showMessage("已导入脚本“" + result.title + "”", false)
        }
    }

    function openConfirmRunDialog(values) {
        confirmRunDialogLoader.active = true
        Qt.callLater(function () {
            confirmRunDialogLoader.item.openForRun(values)
        })
    }

    function openUserGuideDialog() {
        userGuideDialogLoader.active = true
        Qt.callLater(function () { userGuideDialogLoader.item.open() })
    }

    function queueUpdateDialog() {
        updateDialogPending = true
        updateDialogOpenTimer.start()
    }

    function preparePythonDoctorDialog(callback) {
        pythonDoctorDialogLoader.active = true
        Qt.callLater(function () { callback(pythonDoctorDialogLoader.item) })
    }

    Timer {
        id: updateDialogOpenTimer
        interval: 250
        repeat: true
        onTriggered: {
            if (window.applicationOverlayVisible)
                return
            stop()
            window.updateDialogPending = false
            updateDialogLoader.active = true
            Qt.callLater(function () { updateDialogLoader.item.open() })
        }
    }

    onClosing: function (close) {
        if (trayController.available && !trayController.quitting) {
            close.accepted = false
            window.hide()
            trayController.notify_hidden()
        }
    }

    function resetParameters() {
        var values = {}
        var tool = appController.selectedTool
        var parameters = tool.parameters || []
        for (var i = 0; i < parameters.length; i++)
            values[parameters[i].id] = parameters[i].default
        parameterValues = values
    }

    function hideScrcpyWindow() {
        appController.updateScrcpyGeometry(0, 0, 0, 0, false)
    }

    onScrcpySelectedChanged: {
        if (!scrcpySelected)
            hideScrcpyWindow()
    }
    onDeveloperSelectedChanged: {
        if (developerSelected)
            hideScrcpyWindow()
        if (developerSelected && appController.section === "custom")
            customScriptsPage.closeDrawerImmediately()
    }

    function requestTerminalEnable() {
        if (developerConsoleController.pluginInstalled) {
            settingsController.saveTerminalEnabled(true)
            return
        }
        terminalEnablePending = true
        developerConsoleController.requestTerminalAccess()
    }
    onApplicationOverlayVisibleChanged: {
        if (applicationOverlayVisible)
            hideScrcpyWindow()
    }
    onVisibleChanged: {
        if (!visible) {
            hideScrcpyWindow()
            Qt.callLater(function () { window.releaseResources() })
        }
    }

    Connections {
        target: appController

        function onSelectedToolChanged() {
            window.resetParameters()
            if (!window.scrcpySelected)
                window.hideScrcpyWindow()
        }

        function onPythonDoctorWarning(message) {
            window.preparePythonDoctorDialog(function (dialog) {
                dialog.message = message
                dialog.installStatus = ""
                dialog.installing = false
                dialog.open()
            })
        }

        function onPythonDoctorInstallSuggestion(packages) {
            window.preparePythonDoctorDialog(function (dialog) {
                dialog.packageNames = packages
            })
        }

        function onPythonDependencyInstallFinished(success, message) {
            window.preparePythonDoctorDialog(function (dialog) {
                dialog.installing = false
                dialog.installStatus = message
                if (success)
                    dialog.close()
            })
        }
    }

    Connections {
        target: developerConsoleController

        function onPluginInstallPromptRequested(version, directory) {
            powershellPluginDialog.open()
        }

        function onPluginInstallFinished(success, message) {
            if (!success)
                return
            powershellPluginDialog.close()
        }

        function onTerminalAccessGranted() {
            if (!window.terminalEnablePending)
                return
            settingsController.saveTerminalEnabled(true)
            window.terminalEnablePending = false
        }
    }

    Connections {
        target: settingsController

        function onTerminalEnabledChanged() {
            if (settingsController.terminalEnabled)
                return
            if (window.developerSelected) {
                window.developerSelected = false
                appController.navigate("custom")
            }
            developerConsoleController.stop()
        }
    }

    Component.onCompleted: {
        // Release the startup bindings. The platform controller fits the full
        // window, including its native frame, to the current screen once.
        window.width = window.width
        window.height = window.height
        resetParameters()
        if (settingsController.terminalEnabled
                && !developerConsoleController.pluginInstalled)
            settingsController.saveTerminalEnabled(false)
        if (!settingsController.userGuideSeen)
            window.openUserGuideDialog()
        if (updateController.state === "downloaded")
            window.queueUpdateDialog()
        else
            updateController.checkForUpdatesAutomatically()
    }

    WindowTitleBar {
        id: titleBar
        objectName: "windowTitleBar"
        hostWindow: window
        androidBackend: androidController
        selectedScript: appController.selectedTool
        terminalController: developerConsoleController
        terminalTabsVisible: window.developerSelected && !window.settingsSelected
        terminalTabsEnabled: !window.applicationOverlayVisible
        onTerminalFocusRequested: Qt.callLater(terminalPage.focusTerminal)
        scriptActionsVisible: !window.settingsSelected && !window.developerSelected
            && appController.section === "custom"
        scriptActionsEnabled: !window.applicationOverlayVisible
        scriptSelected: !!appController.selectedTool.id
        scriptEditable: !!appController.selectedTool.editable
        scriptRunning: appController.running
        onImportRequested: window.importCustomScriptFromClipboard()
        onCreateRequested: window.openCommandEditorForCreate()
        onShareRequested: customScriptsPage.shareSelectedTool()
        onEditRequested: window.openCommandEditorForEdit()
        onDeleteRequested: window.openDeleteCommandDialog()
        onRunRequested: customScriptsPage.runSelectedTool()
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: window.titleBarContentInset
        visible: window.customTitleBar
    }

    RowLayout {
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.topMargin: window.titleBarContentInset
        anchors.rightMargin: Theme.space8
        anchors.bottomMargin: Theme.space8
        spacing: 0

        Rectangle {
            Layout.preferredWidth: window.primaryNavWidth
            Layout.minimumWidth: window.primaryNavWidth
            Layout.maximumWidth: window.primaryNavWidth
            Layout.fillHeight: true
            color: Theme.sidebar
            clip: false
            z: 2

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                NavItem {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    visible: true
                    label: "终端"
                    shortcutText: "Ctrl+T"
                    iconName: "terminal"
                    compact: window.compactPrimaryNav
                    dense: window.compactHeight
                    selected: window.developerSelected && !window.settingsSelected
                    onClicked: window.openTerminalPage()
                }
                NavItem {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    label: "自定义"
                    shortcutText: "Ctrl+Q"
                    iconName: "code"
                    compact: window.compactPrimaryNav
                    dense: window.compactHeight
                    selected: !window.developerSelected && !window.settingsSelected
                        && appController.section === "custom"
                    onClicked: window.openCustomScriptsPage()
                }

                NavItem {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    label: "预设"
                    iconName: "widgets"
                    compact: window.compactPrimaryNav
                    dense: window.compactHeight
                    selected: !window.developerSelected && !window.settingsSelected
                        && appController.section === "preset"
                    onClicked: {
                        window.developerSelected = false
                        window.settingsSelected = false
                        appController.navigate("preset")
                    }
                }

                NavItem {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    label: "设置"
                    iconName: "settings"
                    compact: window.compactPrimaryNav
                    dense: window.compactHeight
                    selected: window.settingsSelected
                    actionText: updateController.state === "available"
                                ? "有新版本可用"
                                : updateController.state === "downloaded"
                                  ? "更新已准备好" : ""
                    onActionClicked: window.queueUpdateDialog()
                    onClicked: window.openSettingsDialog()
                }

                Item {
                    Layout.fillHeight: true
                }
            }
        }

        Rectangle {
            objectName: "workspaceSurface"
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.workspaceBackground
            radius: Theme.radiusSmall
            clip: true

            StackLayout {
                anchors.fill: parent
                currentIndex: window.settingsSelected ? 3
                    : window.developerSelected ? 2
                    : (appController.section === "custom" ? 0 : 1)

                CustomScriptsPage {
                    id: customScriptsPage
                    color: "transparent"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    controller: appController
                    androidBackend: androidController
                    parentWindow: window
                    parameterValues: window.parameterValues
                    searchQuery: window.toolSearchQuery
                    compact: window.compactContentActions
                    compactHeight: window.compactHeight
                    overlaysVisible: window.applicationOverlayVisible
                    deviceInTitleBar: window.customTitleBar
                    onSearchEdited: function(query) {
                        window.toolSearchQuery = query
                    }
                    onCreateRequested: window.openCommandEditorForCreate()
                    onImportRequested: window.importCustomScriptFromClipboard()
                    onEditRequested: window.openCommandEditorForEdit()
                    onDeleteRequested: window.openDeleteCommandDialog()
                    onConfirmRunRequested: function(values) {
                        window.openConfirmRunDialog(values)
                    }
                    onToastRequested: function(message, error) {
                        customTransferToast.showMessage(message, error)
                    }
                }

                PresetFunctionsPage {
                    id: presetFunctionsPage
                    color: "transparent"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    controller: appController
                    parentWindow: window
                    parameterValues: window.parameterValues
                    presetUtilities: presetController
                    androidBackend: androidController
                    jiraFeishuBackend: jiraFeishuController
                    toolListWidth: window.toolListWidth
                    searchQuery: window.toolSearchQuery
                    compact: window.compactContentActions
                    overlaysVisible: window.applicationOverlayVisible
                    onSearchEdited: function(query) {
                        window.toolSearchQuery = query
                    }
                }

                TerminalPage {
                    id: terminalPage
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    controller: developerConsoleController
                    parentWindow: window
                    tabsInTitleBar: window.customTitleBar
                    onCreateScriptRequested: function(command, kind) {
                        window.openCommandEditorForCreate(command, kind)
                    }
                }

                SettingsPage {
                    id: settingsPage
                    color: "transparent"
                    objectName: "settingsDialog"
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    controller: settingsController
                    updateBackend: updateController
                    terminalBackend: developerConsoleController
                    onPluginManageRequested: powershellPluginDialog.open()
                    onTerminalEnableRequested: window.requestTerminalEnable()
                    onUserHelpRequested: window.openUserGuideDialog()
                }
            }
        }

    }

    ExecutionCapacityDialog {
        id: executionCapacityDialog
        controller: appController
    }

    CustomScriptImportDialog {
        id: customScriptImportDialog
        objectName: "customScriptImportDialog"
        controller: appController
        parentWindow: window
        onScriptReplaced: function(title) {
            customTransferToast.showMessage("已替换脚本“" + title + "”", false)
        }
    }

    Popup {
        id: customTransferToast
        parent: Overlay.overlay
        property string message: ""
        property bool error: false

        function showMessage(value, isError) {
            message = value
            error = isError
            open()
            closeTimer.restart()
        }

        x: Math.round((Overlay.overlay.width - width) / 2)
        y: 18
        width: Math.min(440, Overlay.overlay.width - 24)
        height: 54
        padding: Theme.space16
        modal: false
        closePolicy: Popup.NoAutoClose
        background: AppPopupSurface {
            fillColor: customTransferToast.error
                       ? Theme.errorContainer : Theme.popupSurface
            outlineColor: customTransferToast.error
                          ? Theme.errorColor : Theme.outlineVariant
        }
        contentItem: RowLayout {
            spacing: Theme.space12
            MaterialIcon {
                icon: customTransferToast.error ? "error" : "check_circle"
                iconSize: 22
                color: customTransferToast.error ? Theme.errorColor : Theme.success
            }
            Text {
                Layout.fillWidth: true
                text: customTransferToast.message
                color: Theme.textPrimary
                font.pixelSize: Theme.fontBody
                elide: Text.ElideRight
            }
        }
        Timer {
            id: closeTimer
            interval: 2400
            onTriggered: customTransferToast.close()
        }
    }

    PowerShellPluginDialog {
        id: powershellPluginDialog
        controller: developerConsoleController
        parentWindow: window
        onClosed: {
            if (!developerConsoleController.pluginInstalled)
                window.terminalEnablePending = false
        }
    }

    Loader {
        id: updateDialogLoader
        active: false
        sourceComponent: UpdateDialog {
            controller: updateController
            parentWindow: window
            onClosed: updateDialogLoader.active = false
        }
    }

    Loader {
        id: deleteCommandDialogLoader
        active: false
        sourceComponent: DeleteToolDialog {
            controller: appController
            parentWindow: window
            onClosed: deleteCommandDialogLoader.active = false
        }
    }
    Loader {
        id: confirmRunDialogLoader
        active: false
        sourceComponent: ConfirmRunDialog {
            controller: appController
            parentWindow: window
            onClosed: confirmRunDialogLoader.active = false
        }
    }
    Loader {
        id: commandEditorDialogLoader
        active: false
        sourceComponent: CommandEditorDialog {
            controller: appController
            onClosed: commandEditorDialogLoader.active = false
        }
    }
    Loader {
        id: pythonDoctorDialogLoader
        active: false
        sourceComponent: PythonDoctorDialog {
            controller: appController
            parentWindow: window
            onPluginManagementRequested: window.openSettingsDialog()
            onClosed: pythonDoctorDialogLoader.active = false
        }
    }
    Loader {
        id: userGuideDialogLoader
        active: false
        sourceComponent: UserGuideDialog {
            controller: settingsController
            parentWindow: window
            onClosed: userGuideDialogLoader.active = false
        }
    }
    Component {
        id: recentToolWindowComponent
        RecentToolDialog {
            presetUtilities: presetController
            deviceController: androidController
            jiraFeishuBackend: jiraFeishuController
        }
    }

    property var recentToolWindows: ({})
    property string lastRequestedToolWindow: ""

    function closeRecentToolWindows() {
        var opened = recentToolWindows
        for (var toolId in opened)
            opened[toolId].close()
    }

    Component.onDestruction: closeRecentToolWindows()

    Connections {
        target: trayController
        function onQuittingChanged() {
            if (trayController.quitting)
                window.closeRecentToolWindows()
        }
    }

    Loader {
        active: typeof floatingController !== "undefined"
        sourceComponent: FloatingLauncher { controller: floatingController }
    }

    Connections {
        target: typeof floatingController !== "undefined" ? floatingController : null
        function onSettingsRequested() {
            window.openSettingsDialog()
            trayController.show_window()
        }
    }

    Connections {
        target: updateController
        function onUpdateAvailable() {
            window.queueUpdateDialog()
        }
    }

    Connections {
        target: appController
        function onRecentToolDialogRequested(toolId) {
            window.lastRequestedToolWindow = toolId
            var existing = Object.prototype.hasOwnProperty.call(window.recentToolWindows, toolId)
                ? window.recentToolWindows[toolId] : null
            if (existing) {
                existing.showNormal()
                existing.raise()
                existing.requestActivate()
                Qt.callLater(function() {
                    if (window.lastRequestedToolWindow === toolId
                            && window.recentToolWindows[toolId] === existing && existing.visible)
                        existing.requestActivate()
                })
                return
            }
            var win = recentToolWindowComponent.createObject(null)
            if (!win)
                return
            var opened = Object.assign({}, window.recentToolWindows)
            opened[toolId] = win
            window.recentToolWindows = opened
            win.dismissed.connect(function(closedToolId) {
                var remaining = Object.assign({}, window.recentToolWindows)
                if (remaining[closedToolId] === win)
                    delete remaining[closedToolId]
                window.recentToolWindows = remaining
                win.destroy()
            })
            win.showWithTool(toolId)
        }
    }

}
