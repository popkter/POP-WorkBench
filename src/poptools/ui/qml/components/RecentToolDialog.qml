import QtQuick
import QtQuick.Controls
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
    property rect launchOrigin: Qt.rect(0, 0, 0, 0)
    property var prepareReturn: null
    property var dockReturn: null
    property alias cardFace: cardMotion.cardFace
    property bool returnPending: false
    property bool recallQueued: false
    property bool presented: false
    signal cardPresented(string presentedToolId)
    readonly property bool keepsFloatingLauncherVisible: true
    readonly property bool entryAnimationRunning: cardMotion.entering
    readonly property bool activationAnimationRunning: cardMotion.activating
    readonly property bool focusScanRunning: cardMotion.focusing
    readonly property bool recycleAnimationRunning: cardMotion.recycling
    onRecycleAnimationRunningChanged: if (ownsController && toolController)
        toolController.setCardReturnLayer(Theme.decadeMode && recycleAnimationRunning)
    readonly property rect cardPlacementRect: cardMotion.desktopFlight
        ? Qt.rect(cardMotion.flightGeometry.x + cardMotion.flightGeometry.targetX,
                  cardMotion.flightGeometry.y + cardMotion.flightGeometry.targetY,
                  cardMotion.flightGeometry.targetWidth, cardMotion.flightGeometry.targetHeight)
        : Qt.rect(x, y, width, height)
    signal dismissed(string dismissedToolId)

    onClosing: { cardMotion.finish(); dismissed(toolId) }
    onFrameSwapped: {
        if (!presented && visible && toolId.length > 0) {
            presented = true
            cardPresented(toolId)
        }
        cardMotion.startPreparedEntry()
    }
    onActiveChanged: if (active) Qt.callLater(showFocusFeedback)
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
    onVisibleChanged: if (!visible) cardMotion.finish()
    onVisibilityChanged: if (root.visibility === Window.Minimized) cardMotion.finish()

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
        formLoader.setSource(Qt.resolvedUrl("RecentToolContent.qml"), {dialog: root})
        if (customScriptMode && Theme.decadeMode
                && launchOrigin.width > 0 && launchOrigin.height > 0) {
            var geometry = session.prepareCardFlight(launchOrigin, cardFace !== null)
            if (geometry.width > 0) {
                // Move this execution window itself. Its size, native surface and
                // live form stay unchanged from the first frame through the scan.
                cardMotion.prepareFlight(geometry)
                visible = true
                requestActivate()
                return
            }
        }
        session.placeWindow()
        if (customScriptMode)
            cardMotion.play()
        visible = true
        requestActivate()
    }

    function activateCard() {
        if (returnPending || recallQueued || cardMotion.entering)
            return
        showNormal()
        raise()
        requestActivate()
        if (customScriptMode)
            cardMotion.activate()
    }

    function showFocusFeedback() {
        // Let the opening/list-activation handler select its animation first.
        // The scan is visual only: the activating click still reaches the form.
        if (active && visible && customScriptMode && !returnPending)
            cardMotion.focusScan()
    }

    function closeCardAnimated() {
        if (cardMotion.recycling || returnPending)
            return
        if (!customScriptMode || !visible) {
            dismissCard()
            return
        }
        if (!Theme.decadeMode) {
            cardMotion.fadeOut()
            return
        }
        cardMotion.finish()
        if (prepareReturn) {
            returnPending = true
            if (prepareReturn(toolId, function(origin) {
                if (root && root.visible && root.returnPending)
                    root.startCardReturn(origin)
            }))
                return
            returnPending = false
        }
        startCardReturn(launchOrigin)
    }

    function startCardReturn(origin) {
        returnPending = false
        if (!Theme.decadeMode) {
            cardMotion.fadeOut()
            return
        }
        const geometry = toolController.prepareCardReturn(origin, dockReturn !== null)
        if (geometry.width > 0)
            cardMotion.recycle(geometry)
        else
            close()
    }

    function dismissCard() {
        if (visible) {
            close()
        } else {
            cardMotion.finish()
            dismissed(toolId)
        }
    }

    function toggleRecording() {
        if (!presetUtilities || !deviceController)
            return
        if (presetUtilities.recording) {
            presetUtilities.stopRecording()
            if (!presetUtilities.recordingOutputDirectory
                || presetUtilities.recordingOutputDirectory.length === 0)
                if (formLoader.item && formLoader.item.workspace.item
                        && formLoader.item.workspace.item.openRecordingFolderDialog)
                    formLoader.item.workspace.item.openRecordingFolderDialog()
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
    MechanicalCardMotion {
        id: cardMotion
        width: root.width
        height: root.height
        contentReady: formLoader.status === Loader.Ready
        cardTitle: root.toolController.selectedTool.title || "运行脚本"
        cardIcon: root.toolController.selectedTool.presentation
            ? root.toolController.selectedTool.presentation.icon || "terminal" : "terminal"
        onPositionRequested: function(globalX, globalY) {
            root.toolController.moveCard(globalX, globalY)
        }
        onRecycled: {
            if (Theme.decadeMode && root.dockReturn && cardFace) {
                const face = releaseFace()
                root.dockReturn(root.toolId, face, function() { if (root) root.close() })
            } else {
                root.close()
            }
        }
    }

    // Keep controls visually unchanged while blocking input during entry.
    MouseArea {
        anchors.fill: parent
        z: 1
        visible: root.returnPending || cardMotion.entering || cardMotion.activating || cardMotion.recycling
        acceptedButtons: Qt.AllButtons
        onWheel: function(wheel) { wheel.accepted = true }
    }

    Loader {
        id: formLoader
        objectName: "recentToolFormLoader"
        parent: cardMotion.surface
        anchors.fill: parent
        asynchronous: Theme.decadeMode && root.customScriptMode
    }
}
