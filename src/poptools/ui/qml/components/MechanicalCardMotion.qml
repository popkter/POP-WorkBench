import QtQuick
import "../theme"

// The execution window and its live form own the complete flight and reveal.
Item {
    id: root
    objectName: "mechanicalCardMotion"
    property alias surface: liveContent
    property Item cardFace: null
    property bool faceReleased: false
    Component { id: faceComponent; MechanicalCardFace { objectName: "mechanicalCardBack" } }
    function ensureFace() {
        faceReleased = false
        if (!cardFace)
            cardFace = faceComponent.createObject(root)
        cardFace.cardTitle = cardTitle
        cardFace.cardIcon = cardIcon
        cardFace.attachTo(faceHost)
    }
    function releaseFace() {
        const face = cardFace
        cardFace = null
        faceReleased = true
        return face
    }
    property string cardTitle: ""
    property string cardIcon: "terminal"
    property real progress: 1
    property real spinAngle: 0
    property real activationScan: 0
    property real focusScanProgress: 0
    property real returnScan: 1
    property real returnProgress: 0
    property bool returning: false
    readonly property int travelDuration: 360
    readonly property int scanDuration: 300
    readonly property int flightDuration: travelDuration + scanDuration
    property var flightGeometry: null
    property bool prepared: false
    property bool contentReady: true
    property bool waitingForContent: false
    onContentReadyChanged: {
        if (contentReady && waitingForContent) {
            waitingForContent = false
            entry.resume()
        }
    }
    property rect packClip: Qt.rect(0, 0, 0, 0)
    readonly property bool sourceFrameClipped: desktopFlight && entering && progress === 0
        && packClip.width > 0 && packClip.height > 0
    // Tuck the lower body into the stack during the approach. This is one
    // card-local rectangle, transformed with the card (no desktop-space mask).
    readonly property real dockingProgress: returning && desktopFlight && packClip.height > 0
        ? easeOut(Math.max(0, Math.min(1, (returnProgress - 0.45) / 0.4))) : 0
    readonly property real dockTop: desktopFlight
        ? Math.max(0, (packClip.y - flightGeometry.y - flightGeometry.sourceY)
                   * height / flightGeometry.sourceHeight) : 0
    readonly property real dockBottom: desktopFlight
        ? Math.min(height, dockTop + packClip.height * height / flightGeometry.sourceHeight) : height
    readonly property bool mechanicalEnabled: Theme.decadeMode
    property real fadeOpacity: 1
    readonly property bool desktopFlight: flightGeometry !== null
    readonly property bool entering: prepared || entry.running || fadeEntry.running
    readonly property bool activating: activation.running
    readonly property bool focusing: focusScanAnimation.running
    readonly property bool recycling: returning
    readonly property bool activationBack: activating && spinAngle > 90 && spinAngle < 270
    readonly property color accent: "#F12786"
    readonly property real draw: easeOut(phase(0, 0.38))
    readonly property real turn: easeOut(phase(0.12, 0.62))
    readonly property real flightProgress: returning ? 1 - returnProgress
        : phase(0, travelDuration / flightDuration)
    readonly property real travel: travelAt(flightProgress)
    readonly property real scan: !contentReady ? 0 : returning ? returnScan : activating ? activationScan
        : focusing ? focusScanProgress
        : phase(travelDuration / flightDuration, 1)
    readonly property real initialScale: desktopFlight
        ? Math.min(flightGeometry.sourceWidth / width, flightGeometry.sourceHeight / height) : 1
    readonly property real flightScale: initialScale + (1 - initialScale) * travel
    readonly property real flightTilt: desktopFlight
        ? (flightGeometry.targetX < flightGeometry.sourceX ? -1 : 1)
            * 8 * Math.sin(Math.PI * flightProgress) : 0
    readonly property real radians: flightTilt * Math.PI / 180
    // Keep rotation inside this fixed-size native surface; never resize or swap it.
    readonly property real fit: Math.min(1,
        width / (width * flightScale * Math.abs(Math.cos(radians))
            + height * flightScale * Math.abs(Math.sin(radians))),
        height / (height * flightScale * Math.abs(Math.cos(radians))
            + width * flightScale * Math.abs(Math.sin(radians))))
    readonly property real settleScale: 1 - 0.008 * Math.sin(
        Math.PI * Math.max(0, (flightProgress - 0.85) / 0.15))
    readonly property real edgeStrength: entering
        ? Math.sin(Math.PI * phase(0.10, 1)) * 0.85
        : activating ? Math.max(Math.sin(Math.PI * spinAngle / 360) * .45,
                               Math.sin(Math.PI * activationScan) * .85)
        : returning ? .65 * (1 - returnProgress)
        : focusing ? Math.sin(Math.PI * focusScanProgress) * .85 : 0
    signal positionRequested(real globalX, real globalY)
    signal recycled()

    // Settle an open card in place when switching themes. A pending close must
    // still complete, and must never leave an invisible, input-blocking window.
    onMechanicalEnabledChanged: {
        const closing = recycling
        finish()
        if (closing)
            recycled()
    }

    onProgressChanged: {
        // Only this card waits at its destination if its form is still incubating.
        // Keep the opaque face until the live controls can be scanned into view.
        if (entry.running && !entry.paused && !contentReady
                && progress >= travelDuration / flightDuration) {
            entry.pause()
            waitingForContent = true
            progress = travelDuration / flightDuration
        }
        syncFlightPosition()
    }
    onReturnProgressChanged: syncFlightPosition()
    onWidthChanged: syncFlightPosition()
    onHeightChanged: syncFlightPosition()
    function syncFlightPosition() {
        if (!desktopFlight || width <= 0 || height <= 0)
            return
        const g = flightGeometry
        const fromX = g.sourceX + g.sourceWidth / 2
        const fromY = g.sourceY + g.sourceHeight / 2
        const toX = g.targetX + width / 2
        const toY = g.targetY + height / 2
        // Compute from the current tick: dependent QML bindings may still hold
        // their previous values while onProgressChanged is being delivered.
        const tick = returning ? 1 - returnProgress : phase(0, travelDuration / flightDuration)
        const eased = travelAt(tick)
        const angle = 8 * Math.sin(Math.PI * tick) * Math.PI / 180
        const startScale = Math.min(g.sourceWidth / width, g.sourceHeight / height)
        const scale = startScale + (1 - startScale) * eased
        const rotatedWidth = scale * (width * Math.abs(Math.cos(angle))
            + height * Math.abs(Math.sin(angle)))
        const rotatedHeight = scale * (height * Math.abs(Math.cos(angle))
            + width * Math.abs(Math.sin(angle)))
        const fitting = Math.min(1, width / rotatedWidth, height / rotatedHeight)
        const bounce = 1 - 0.008 * Math.sin(Math.PI * Math.max(0, (tick - .85) / .15))
        const footprintWidth = rotatedWidth * fitting * bounce
        const footprintHeight = rotatedHeight * fitting * bounce
        if (g.preserveSource) {
            positionRequested(g.x + fromX + (toX - fromX) * eased - width / 2,
                              g.y + fromY + (toY - fromY) * eased
                              - 32 * Math.sin(Math.PI * tick) - height / 2)
            return
        }
        const centerX = Math.max(footprintWidth / 2, Math.min(g.width - footprintWidth / 2,
            fromX + (toX - fromX) * eased))
        const centerY = Math.max(footprintHeight / 2, Math.min(g.height - footprintHeight / 2,
            fromY + (toY - fromY) * eased - 32 * Math.sin(Math.PI * tick)))
        positionRequested(g.x + centerX - width / 2, g.y + centerY - height / 2)
    }
    function prepareFlight(geometry) {
        if (!mechanicalEnabled) {
            play()
            return
        }
        finish()
        packClip = cardFace ? cardFace.packVisibleRect : Qt.rect(0, 0, 0, 0)
        ensureFace()
        flightGeometry = geometry
        progress = 0
        prepared = true
        syncFlightPosition()
    }
    function startPreparedEntry() {
        if (!prepared)
            return
        if (mechanicalEnabled) {
            entry.duration = flightDuration
            entry.start()
        } else {
            fadeEntry.start()
        }
        prepared = false
    }

    function phase(start, end) {
        return Math.max(0, Math.min(1, (progress - start) / (end - start)))
    }
    function easeOut(value) { return 1 - Math.pow(1 - value, 3) }
    function travelAt(value) {
        // Decelerate into the pack instead of reversing the entry easing and
        // accelerating through the final handoff.
        return returning ? (1 - Math.cos(Math.PI * value)) / 2 : easeOut(value)
    }
    function play() {
        finish()
        ensureFace()
        progress = mechanicalEnabled ? 0 : 1
        fadeOpacity = mechanicalEnabled ? 1 : 0
        prepared = true
    }
    function finish() {
        waitingForContent = false
        entry.stop()
        activation.stop()
        focusScanAnimation.stop()
        recycleSequence.stop()
        fadeEntry.stop()
        fadeExit.stop()
        prepared = false
        packClip = Qt.rect(0, 0, 0, 0)
        returning = false
        progress = 1
        syncFlightPosition()
        flightGeometry = null
        spinAngle = 0
        activationScan = 0
        focusScanProgress = 0
        fadeOpacity = 1
    }
    function focusScan() {
        if (!mechanicalEnabled || entering || activating || recycling || focusing)
            return
        focusScanAnimation.start()
    }
    function activate() {
        // Coalesce rapid clicks instead of snapping a partly rotated card back.
        if (activating)
            return
        finish()
        if (mechanicalEnabled) {
            ensureFace()
            activation.start()
        }
    }
    function recycle(geometry) {
        if (!mechanicalEnabled) {
            fadeOut()
            return
        }
        if (returning)
            return
        finish()
        packClip = cardFace ? cardFace.packVisibleRect : Qt.rect(0, 0, 0, 0)
        ensureFace()
        returnScan = 1
        returnProgress = 0
        flightGeometry = geometry
        returning = true
        recycleSequence.start()
    }
    function fadeOut() {
        if (returning)
            return
        // Preserve the current alpha when closing during fade-in.
        const alpha = fadeOpacity
        finish()
        fadeOpacity = alpha
        returning = true
        fadeExit.start()
    }

    NumberAnimation {
        id: fadeEntry
        objectName: "cardFadeInAnimation"
        target: root; property: "fadeOpacity"
        to: 1; duration: 180; easing.type: Easing.OutCubic
    }
    NumberAnimation {
        id: fadeExit
        objectName: "cardFadeOutAnimation"
        target: root; property: "fadeOpacity"
        to: 0; duration: 140; easing.type: Easing.InCubic
        onFinished: root.recycled()
    }

    NumberAnimation {
        id: entry
        objectName: "mechanicalCardEntryAnimation"
        target: root; property: "progress"
        from: 0; to: 1; duration: 420
        onFinished: root.flightGeometry = null
    }
    SequentialAnimation {
        id: activation
        objectName: "mechanicalCardActivationAnimation"
        NumberAnimation {
            target: root; property: "spinAngle"
            from: 0; to: 360; duration: 420; easing.type: Easing.InOutCubic
        }
        NumberAnimation {
            target: root; property: "activationScan"
            from: 0; to: 1; duration: root.scanDuration
        }
    }
    NumberAnimation {
        id: focusScanAnimation
        objectName: "mechanicalCardFocusScanAnimation"
        target: root; property: "focusScanProgress"
        from: 0; to: 1; duration: root.scanDuration
    }
    SequentialAnimation {
        id: recycleSequence
        objectName: "mechanicalCardRecycleAnimation"
        NumberAnimation {
            target: root; property: "returnScan"
            from: 1; to: 0; duration: 180
        }
        NumberAnimation {
            target: root; property: "returnProgress"
            from: 0; to: 1; duration: 300
        }
        onFinished: root.recycled()
    }

    // Clip only the stationary handoff frame to the exposed card head. Once
    // movement begins the card is a complete rectangle, with no desktop-space
    // mask or cached effect texture that can cut holes into a later flight frame.
    Item {
        id: sourceFrameClip
        objectName: "cardSourceFrameClip"
        readonly property var g: root.flightGeometry
        x: root.sourceFrameClipped && g
            ? root.packClip.x - (g.x + g.sourceX + (g.sourceWidth - root.width) / 2) : 0
        y: root.sourceFrameClipped && g
            ? root.packClip.y - (g.y + g.sourceY + (g.sourceHeight - root.height) / 2) : 0
        width: root.sourceFrameClipped ? root.packClip.width : root.width
        height: root.sourceFrameClipped ? root.packClip.height : root.height
        clip: root.sourceFrameClipped
    }
    Item {
        id: card
        parent: sourceFrameClip
        objectName: "movingScriptCard"
        x: -sourceFrameClip.x; y: -sourceFrameClip.y
        width: root.width; height: root.height
        opacity: root.fadeOpacity
        visible: !root.faceReleased
        transform: [
            Rotation {
                objectName: "mechanicalCardSpin"
                origin.x: card.width / 2; origin.y: card.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: root.spinAngle
            },
            Scale {
                origin.x: card.width / 2; origin.y: card.height / 2
                xScale: root.desktopFlight ? root.flightScale * root.fit * root.settleScale
                    : root.progress < 0.78
                    ? 0.72 + 0.28 * root.easeOut(root.phase(0, 0.78))
                    : 1 - 0.012 * Math.sin(Math.PI * root.phase(0.78, 1))
                yScale: xScale
            },
            Rotation {
                origin.x: card.width / 2; origin.y: card.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: root.desktopFlight ? 0 : -72 * (1 - root.turn)
            },
            Rotation {
                origin.x: card.width / 2; origin.y: card.height / 2
                angle: root.desktopFlight ? root.flightTilt : -6 * (1 - root.draw)
            },
            Translate {
                x: root.desktopFlight ? 0 : card.width * 0.10 * (1 - root.draw)
                y: root.desktopFlight ? 0 : card.height * 0.06 * (1 - root.draw)
            }
        ]

        Item {
            id: dockingClip
            objectName: "cardDockingClip"
            y: root.dockTop * root.dockingProgress
            width: card.width
            height: card.height + (root.dockBottom - card.height) * root.dockingProgress - y
            clip: root.dockingProgress > 0
        }
        Item {
            parent: dockingClip
            y: -dockingClip.y
            width: card.width; height: card.height

            // Render the real form from frame one, beneath the opaque card back.
            // Scanning uncovers it in place, without capture, loading or reparenting.
            Item {
                id: liveContent
                objectName: "liveScriptCardContent"
                width: card.width; height: card.height
            }

            Item {
                width: card.width
                y: root.activationBack ? 0 : card.height * root.scan
                height: card.height - y
                visible: root.mechanicalEnabled
                    && (!root.contentReady || root.activationBack
                        || ((root.entering || root.recycling) && root.scan < 1))
                clip: true
                Item {
                    id: faceHost
                    x: Theme.space4
                    y: Theme.space4 - parent.y
                    width: card.width - Theme.space4 * 2
                    height: card.height - Theme.space4 * 2
                    transform: Rotation {
                        origin.x: (card.width - Theme.space4 * 2) / 2
                        origin.y: (card.height - Theme.space4 * 2) / 2
                        axis { x: 0; y: 1; z: 0 }
                        angle: root.activationBack ? 180 : 0
                    }
                }
            }

            Item {
                anchors.fill: parent
                anchors.margins: Theme.space4
                visible: root.mechanicalEnabled
                    && (root.entering || root.activating || root.recycling || root.focusing)
                clip: true

                Rectangle {
                    objectName: "mechanicalCardScan"
                    x: 2; width: parent.width - 4; height: 88
                    y: parent.height * root.scan - height
                    opacity: root.entering || root.recycling || root.focusing
                        || (root.activating && root.spinAngle >= 360)
                        ? Math.sin(Math.PI * root.scan) * 0.95 : 0
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#00F12786" }
                        GradientStop { position: 0.65; color: "#40F12786" }
                        GradientStop { position: 0.88; color: "#99F12786" }
                        GradientStop { position: 0.96; color: "#FFFFB8DB" }
                        GradientStop { position: 0.98; color: "#FFF12786" }
                        GradientStop { position: 1; color: "#00F12786" }
                    }
                }
                Rectangle {
                    objectName: "mechanicalCardEdge"
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: Theme.radiusMedium
                    color: "transparent"
                    border.width: 2
                    border.color: root.accent
                    opacity: root.edgeStrength
                }
                Repeater {
                    model: 2
                    Rectangle {
                        required property int index
                        x: index === 0 ? 12 : parent.width - width - 12
                        y: index === 0 ? 3 : parent.height - height - 3
                        width: 44; height: 3
                        color: "#FFD3E8"
                        opacity: root.edgeStrength
                    }
                }
            }
        }
    }
}
