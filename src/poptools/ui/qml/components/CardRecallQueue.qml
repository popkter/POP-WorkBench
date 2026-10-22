import QtQuick
import "../theme"

// A short cadence overlaps returning flights; landing never gates the next launch.
QtObject {
    id: root
    property var pending: []
    property var activeCards: []
    property var launchingCard: null
    readonly property bool running: pending.length > 0 || activeCards.length > 0
    readonly property int staggerDuration: 50
    property Timer cadence: Timer {
        interval: root.staggerDuration
        onTriggered: { root.launchingCard = null; root.advance() }
    }
    property Connections launchObserver: Connections {
        target: root.launchingCard
        function onRecycleAnimationRunningChanged() { root.scheduleNext() }
    }

    function recall(cards) {
        const additions = []
        for (let card of cards) {
            if (!card || !card.visible || !card.customScriptMode
                    || activeCards.indexOf(card) >= 0 || pending.indexOf(card) >= 0)
                continue
            card.recallQueued = true
            additions.push(card)
        }
        // Join an existing manual return without restarting it.
        additions.sort((a, b) => Number(b.returnPending || b.recycleAnimationRunning)
            - Number(a.returnPending || a.recycleAnimationRunning))
        pending = pending.concat(additions)
        if (!launchingCard && !cadence.running)
            advance()
    }

    function scheduleNext() {
        if (launchingCard && launchingCard.recycleAnimationRunning && !cadence.running)
            cadence.start()
    }

    function advance() {
        while (pending.length > 0) {
            const card = pending[0]
            pending = pending.slice(1)
            if (!card || !card.visible)
                continue
            activeCards = activeCards.concat([card])
            if (Theme.decadeMode) {
                launchingCard = card
                if (!card.returnPending && !card.recycleAnimationRunning)
                    card.closeCardAnimated()
                // Start the cadence from the actual animation, including when
                // the pack first needs to expand. Never release a waiting burst.
                scheduleNext()
                return
            }
            card.closeCardAnimated()
        }
    }

    function completed(card) {
        if (card) card.recallQueued = false
        pending = pending.filter(candidate => candidate && candidate !== card)
        activeCards = activeCards.filter(candidate => candidate && candidate !== card)
        if (launchingCard === card) {
            cadence.stop()
            launchingCard = null
            Qt.callLater(advance)
        }
    }

    function clear() {
        cadence.stop()
        for (let card of pending.concat(activeCards))
            if (card) card.recallQueued = false
        launchingCard = null
        pending = []
        activeCards = []
    }
}
