import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "../theme"

Window {
    id: root
    objectName: "recentToolWindow"
    transientParent: null
    title: root.selectedTool.title || "运行工具"

    property string toolId: ""
    property var toolController: appController
    readonly property var selectedTool: toolController.selectedTool
    property bool ownsController: false
    property rect launchOrigin: Qt.rect(0, 0, 0, 0)
    property rect launchDockBounds: Qt.rect(0, 0, 0, 0)
    property var prepareReturn: null
    property var dockReturn: null
    property alias cardFace: cardMotion.cardFace
    property bool zioManaged: false
    property bool handoffBlocked: false
    property bool outgoing: false
    property bool returnPending: false
    property int returnGeneration: 0
    property bool recallQueued: false
    property bool presented: false
    property bool closing: false
    property bool pinned: false
    property int floatingActivationToken: -1
    property bool floatingFocusHandoff: floatingActivationToken >= 0
    signal cardPresented(string presentedToolId)
    signal cardActivated(string activatedToolId)
    readonly property bool entryAnimationRunning: cardMotion.entering
    readonly property bool activationAnimationRunning: cardMotion.activating
    readonly property bool focusScanRunning: cardMotion.focusing
    readonly property bool recycleAnimationRunning: cardMotion.recycling
    readonly property bool nativeFlightActive: Theme.mechanicalMode && cardMotion.desktopFlight
    onNativeFlightActiveChanged: if (ownsController && toolController)
        toolController.setCardFlightLayer(nativeFlightActive)
    readonly property rect cardPlacementRect: cardMotion.desktopFlight
        ? Qt.rect(cardMotion.flightGeometry.x + cardMotion.flightGeometry.targetX,
                  cardMotion.flightGeometry.y + cardMotion.flightGeometry.targetY,
                  cardMotion.flightGeometry.targetWidth, cardMotion.flightGeometry.targetHeight)
        : Qt.rect(x, y, width, height)
    signal dismissed(string dismissedToolId)

    onClosing: {
        if (closing) return
        closing = true
        closeDeadline.stop()
        returnPending = false
        returnGeneration++
        // Hide with the docking mask intact. finish() restores the normal
        // surface/mask and must not expose a closing full-size native window.
        visible = false
        // Main releases the hidden window when other flights have settled.
        // Destroying a whole form here stalls every other card's GUI animation.
        cardMotion.finish()
        dismissed(toolId)
    }
    onFrameSwapped: {
        if (!presented && visible && toolId.length > 0) {
            presented = true
            // Never mutate the source ListView/model from a frame callback.
            Qt.callLater(notifyPresented)
        }
        cardMotion.startPreparedEntry()
    }
    function notifyPresented() {
        if (visible && !closing) cardPresented(toolId)
    }
    onActiveChanged: if (active) {
        Qt.callLater(showFocusFeedback)
        if (toolId.length > 0 && !outgoing && !closing) cardActivated(toolId)
    }
    Component.onDestruction: {
        if (ownsController && toolController)
            toolController.dispose()
    }
    property var initialParameterValues: null
    property var parameterValues: ({})
    property var presetUtilities
    property var deviceController
    property var jiraFeishuBackend
    readonly property bool presetMode: root.selectedTool.workspace === "preset"
    readonly property bool customScriptMode: root.selectedTool.section === "custom"
        && root.selectedTool.workspace === "command"
    readonly property bool recordingPreset: presetMode
        && root.selectedTool.executor
        && root.selectedTool.executor.command === "recording"
    readonly property bool operationRunning: recordingPreset
        ? presetUtilities && presetUtilities.recording
        : root.toolController.running
    readonly property real consolePreferredHeight: 292
    readonly property real bodySpacing: 12

    readonly property real cardUiScale: customScriptMode ? Theme.scriptCardScale : 1
    width: customScriptMode ? Math.round(440 * cardUiScale) : presetMode ? 720 : 680
    height: Math.min(customScriptMode ? Math.round(680 * cardUiScale)
                                    : presetMode ? 560 : 600, Screen.height - 48)
    visible: false
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint
        | (pinned ? Qt.WindowStaysOnTopHint : 0)
    color: "transparent"
    onVisibleChanged: if (!visible) cardMotion.finish()
    onVisibilityChanged: if (root.visibility === Window.Minimized) cardMotion.finish()

    function settleCard() {
        closeDeadline.stop()
        returnPending = false
        returnGeneration++
        cardMotion.finish()
    }

    readonly property string cardTheme: Theme.zioMode ? "zio"
        : Theme.decadeMode ? "decade" : "standard"
    // Settle the old presentation before a new activation can start.
    onCardThemeChanged: if (visible && !closing) settleThemeChange()
    function settleThemeChange() {
        if (!visible || closing) return
        // A return belongs to the presentation that supplied its destination.
        // Complete it before stale callbacks can hold the new presentation open.
        if (closeDeadline.running || returnPending || cardMotion.recycling)
            dismissCard()
        else
            settleCard()
    }
    function placeZioCard(origin, dockBounds) {
        cardMotion.finish()
        if (ownsController && customScriptMode) toolController.placeZioCard(origin, dockBounds)
    }

    function centerOnScreen() {
        x = Screen.virtualX + Math.round((Screen.width - width) / 2)
        y = Screen.virtualY + Math.round((Screen.height - height) / 2)
    }

    function showWithTool(tid) {
        const initialValues = initialParameterValues
        closing = false
        presented = false
        formLoader.active = true
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
        var tool = root.selectedTool
        var parameters = tool.parameters || []
        for (var i = 0; i < parameters.length; i++)
            values[parameters[i].id] = initialValues && initialValues[parameters[i].id] !== undefined
                ? initialValues[parameters[i].id] : parameters[i].default
        parameterValues = values
        formLoader.setSource(Qt.resolvedUrl("RecentToolContent.qml"), {dialog: root})
        if (customScriptMode && Theme.mechanicalMode
                && launchOrigin.width > 0 && launchOrigin.height > 0) {
            var geometry = session.prepareCardFlight(launchOrigin, cardFace !== null,
                Theme.zioMode ? "zio" : "decade", launchDockBounds)
            if (geometry.width > 0) {
                // Move this execution window itself. Its size, native surface and
                // live form stay unchanged from the first frame through the scan.
                cardMotion.prepareFlight(geometry)
                visible = true
                if (Theme.zioMode) raise()
                requestActivate()
                return
            }
        }
        session.placeWindow(Theme.decadeMode && customScriptMode ? "decade" : "standard")
        if (customScriptMode)
            cardMotion.play()
        visible = true
        requestActivate()
    }

    function queueTitleActivation() {
        // Finish delivery to the title MouseArea before enabling the animation's
        // input shield and transforming that MouseArea's ancestors.
        Qt.callLater(activateFromTitle)
    }

    function activateFromTitle() {
        if (Theme.mechanicalMode && customScriptMode && visible && !closing
                && !cardMotion.recycling)
            activateCard()
    }

    function activateCard() {
        if (closing || returnPending || recallQueued || cardMotion.recycling)
            return
        if (visibility === Window.Minimized)
            showNormal()
        raise()
        requestActivate()
        if (customScriptMode && !cardMotion.entering && !cardMotion.activating)
            cardMotion.activate()
    }

    function showFocusFeedback() {
        // Let the opening/list-activation handler select its animation first.
        // The scan is visual only: the activating click still reaches the form.
        if (active && visible && customScriptMode && !closing && !returnPending)
            cardMotion.focusScan()
    }

    function closeCardAnimated() {
        // This deadline covers destination preparation, flight and face docking.
        // Repeated X/bulk-close requests must not prolong a lost callback.
        if (closing) return
        if (!closeDeadline.running) closeDeadline.start()
        if (cardMotion.recycling || returnPending)
            return
        const generation = ++returnGeneration
        if (!customScriptMode || !visible) {
            dismissCard()
            return
        }
        if (!Theme.mechanicalMode) {
            cardMotion.fadeOut()
            return
        }
        cardMotion.finish()
        if (prepareReturn) {
            returnPending = true
            if (prepareReturn(toolId, function(origin) {
                if (root && root.visible && !root.closing && root.returnPending
                        && root.returnGeneration === generation)
                    root.startCardReturn(origin)
            }))
                return
            returnPending = false
        }
        startCardReturn(launchOrigin)
    }

    function startCardReturn(origin) {
        if (closing || !visible) return
        returnPending = false
        if (!Theme.mechanicalMode) {
            cardMotion.fadeOut()
            return
        }
        const geometry = toolController.prepareCardReturn(origin, dockReturn !== null, Theme.zioMode ? "zio" : "decade")
        if (geometry.width > 0)
            cardMotion.recycle(geometry)
        else
            close()
    }

    function dismissCard() {
        if (closing) return
        closeDeadline.stop()
        returnPending = false
        returnGeneration++
        if (visible) {
            close()
        } else {
            cardMotion.finish()
            dismissed(toolId)
        }
    }

    Timer {
        id: closeDeadline
        objectName: "cardCloseDeadline"
        interval: 4000
        onTriggered: root.dismissCard()
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
        else if (root.selectedTool.presentation && root.selectedTool.presentation.confirm_before_run) {
            if (runConfirmationLoader.active) return
            runConfirmationLoader.active = true
            Qt.callLater(openRunConfirmation)
        }
        else
            root.toolController.runSelected(root.parameterValues)
    }

    function openRunConfirmation() {
        if (visible && !closing && !outgoing && runConfirmationLoader.item)
            runConfirmationLoader.item.openForRun(parameterValues)
        else
            runConfirmationLoader.active = false
    }

    // ── Main content ───────────────────────────────────────
    MechanicalCardMotion {
        id: cardMotion
        designScale: root.cardUiScale
        width: root.width
        height: root.height
        contentReady: formLoader.status === Loader.Ready
        cardTitle: root.selectedTool.title || "运行脚本"
        cardIcon: root.selectedTool.presentation
            ? root.selectedTool.presentation.icon || "terminal" : "terminal"
        onPositionRequested: function(globalX, globalY, packBounds, packOpening) {
            root.toolController.moveCard(globalX, globalY, packBounds, packOpening)
        }
        onRecycled: {
            if (Theme.mechanicalMode && root.dockReturn && cardFace) {
                const face = releaseFace()
                root.dockReturn(root.toolId, face, function() { if (root && !root.closing) root.close() })
            } else {
                root.close()
            }
        }
    }

    // Keep controls visually unchanged while blocking input during entry.
    MouseArea {
        anchors.fill: parent
        z: 1
        visible: root.handoffBlocked || root.outgoing || root.returnPending || cardMotion.entering || cardMotion.activating || cardMotion.recycling
        acceptedButtons: Qt.AllButtons
        onWheel: function(wheel) { wheel.accepted = true }
    }

    Item {
        id: scaledForm
        // Warm the form shortly before the scan, rather than redraw it behind
        // an opaque, rotating card in every window throughout the flight.
        visible: !Theme.mechanicalMode || (!cardMotion.entering && !cardMotion.recycling)
            || cardMotion.scan > 0
            || (cardMotion.entering && cardMotion.progress
                >= cardMotion.scanStartDuration / cardMotion.flightDuration - .05)
        parent: cardMotion.surface
        width: parent.width / root.cardUiScale
        height: parent.height / root.cardUiScale
        scale: root.cardUiScale
        transformOrigin: Item.TopLeft
    }
    Loader {
        id: formLoader
        objectName: "recentToolFormLoader"
        parent: scaledForm
        anchors.fill: parent
        asynchronous: Theme.mechanicalMode && root.customScriptMode
    }
    Loader {
        id: runConfirmationLoader
        objectName: "recentToolConfirmRunLoader"
        active: false
        sourceComponent: ConfirmRunDialog {
            controller: root.toolController
            parentWindow: root
            onClosed: runConfirmationLoader.active = false
        }
    }
}
