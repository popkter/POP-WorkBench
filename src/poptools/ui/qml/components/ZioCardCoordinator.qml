import QtQuick

// Keep independent Dock cards alive; only repeat requests for a returning card wait.
Item {
    id: root
    property bool active: false
    property var windows: ({})
    property var pendingIds: []
    property var parameterSnapshots: ({})
    property var launchOrigin: null
    property var dockBounds: null
    signal launchRequested(string toolId)

    function remember(card) {
        if (card && card.customScriptMode)
            parameterSnapshots[card.toolId] = Object.assign({}, card.parameterValues)
    }
    function request(id) {
        const card = windows[id]
        if (card && (card.returnPending || card.recycleAnimationRunning || card.outgoing)) {
            if (pendingIds.indexOf(id) < 0) pendingIds = pendingIds.concat([id])
            return
        }
        launchRequested(id)
    }
    function clear() { pendingIds = [] }
    function normalize() {
        clear()
        for (const card of Object.values(windows)) {
            if (!card.customScriptMode || !card.visible || card.closing) continue
            card.handoffBlocked = false
            if (card.returnPending || card.recycleAnimationRunning) {
                remember(card)
                card.dismissCard()
                continue
            }
            card.settleCard()
            if (active && launchOrigin && dockBounds)
                card.placeZioCard(launchOrigin(card.toolId), dockBounds())
        }
    }
    onActiveChanged: {
        if (active) Qt.callLater(normalize)
        else normalize()
    }
    function settleScreen() {
        if (active) normalize()
    }
    Timer {
        interval: 16; repeat: true
        running: root.active && root.pendingIds.length > 0
        onTriggered: {
            const requests = root.pendingIds
            root.pendingIds = []
            for (const id of requests) root.request(id)
        }
    }
}
