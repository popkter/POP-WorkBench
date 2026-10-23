import QtQuick
import "../theme"

// The execution window and its live form own the complete flight and reveal.
Item {
    id: root
    objectName: "mechanicalCardMotion"
    property alias surface: liveContent
    property real designScale: 1
    property Item cardFace: null
    property bool faceReleased: false
    // Construct the fallback with the window, before it can receive input.
    // Activation must never enter QQmlComponent.createObject while an async
    // form is incubating (a not-ready component can return no native object).
    MechanicalCardFace {
        id: fallbackFace
        objectName: "mechanicalCardBack"
        visible: false
    }
    function ensureFace() {
        faceReleased = false
        if (!cardFace)
            cardFace = fallbackFace
        cardFace.cardTitle = cardTitle
        cardFace.cardIcon = cardIcon
        if (cardFace.parent !== faceHost)
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
    property bool entrySpinEnabled: false
    readonly property int entrySpinDuration: entrySpinEnabled ? 420 : 0
    readonly property int scanDuration: 300
    readonly property int scanStartDuration: travelDuration + entrySpinDuration
    readonly property int flightDuration: scanStartDuration + scanDuration
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
    property real packTop: NaN
    property real packBottom: NaN
    property rect portBounds: Qt.rect(0, 0, 0, 0)
    property rect portSource: Qt.rect(0, 0, 0, 0)
    readonly property bool portFlight: desktopFlight && flightGeometry.preserveSource && portBounds.height > 0
    readonly property bool sleeveFlight: desktopFlight && flightGeometry.preserveSource && isFinite(packTop)
    readonly property bool mechanicalEnabled: Theme.decadeMode
    property real fadeOpacity: 1
    readonly property bool desktopFlight: flightGeometry !== null
    readonly property bool entering: prepared || entry.running || fadeEntry.running
    readonly property bool activating: activation.running
    readonly property bool focusing: focusScanAnimation.running
    readonly property bool recycling: returning
    readonly property real displayedSpinAngle: entering && entrySpinEnabled
        ? 360 * easeInOut(phase(travelDuration / flightDuration, scanStartDuration / flightDuration))
        : spinAngle
    readonly property bool activationBack: (activating || entering)
        && displayedSpinAngle > 90 && displayedSpinAngle < 270
    readonly property color accent: "#F12786"
    readonly property real draw: easeOut(phase(0, 0.38))
    readonly property real turn: easeOut(phase(0.12, 0.62))
    readonly property real flightProgress: returning ? 1 - returnProgress
        : phase(0, travelDuration / flightDuration)
    readonly property real travel: travelAt(flightProgress)
    // Keep the original size and orientation until the whole card has cleared
    // the sleeve. A low row must not enlarge while still crossing the pack.
    readonly property real freeTravel: sleeveFlight ? Math.max(0, (travel - .5) * 2) : travel
    readonly property real scan: !contentReady ? 0 : returning ? returnScan : activating ? activationScan
        : focusing ? focusScanProgress
        : phase(scanStartDuration / flightDuration, 1)
    readonly property real initialScale: desktopFlight
        ? Math.min(flightGeometry.sourceWidth / width, flightGeometry.sourceHeight / height) : 1
    readonly property real initialScaleX: portFlight ? flightGeometry.sourceWidth / width : initialScale
    readonly property real initialScaleY: portFlight ? flightGeometry.sourceHeight / height : initialScale
    readonly property real portScale: portFlight && portSource.width > 0
        ? Math.min(portSource.width / width, portSource.height / height) : initialScale
    readonly property real portAlignment: Math.min(1, travel / .2)
    readonly property real flightScaleX: portFlight
        ? initialScaleX + (portScale - initialScaleX) * portAlignment + (1 - portScale) * freeTravel
        : initialScale + (1 - initialScale) * freeTravel
    readonly property real flightScale: portFlight
        ? initialScaleY + (portScale - initialScaleY) * portAlignment + (1 - portScale) * freeTravel
        : initialScale + (1 - initialScale) * freeTravel
    readonly property real faceAspectCompensation: desktopFlight && flightScale > 0
        ? flightScaleX / flightScale : 1
    readonly property real flightTilt: desktopFlight
        ? (flightGeometry.preserveSource || flightGeometry.targetX < flightGeometry.sourceX ? -1 : 1)
            * 8 * Math.sin(Math.PI * (sleeveFlight ? freeTravel : flightProgress)) : 0
    readonly property real radians: flightTilt * Math.PI / 180
    // Keep rotation inside this fixed-size native surface; never resize or swap it.
    readonly property real fit: Math.min(1,
        width / (width * flightScaleX * Math.abs(Math.cos(radians))
            + height * flightScale * Math.abs(Math.sin(radians))),
        height / (height * flightScale * Math.abs(Math.cos(radians))
            + width * flightScaleX * Math.abs(Math.sin(radians))))
    readonly property real settleScale: 1 - 0.008 * Math.sin(
        Math.PI * Math.max(0, (flightProgress - 0.85) / 0.15))
    readonly property real edgeStrength: entering
        ? Math.sin(Math.PI * phase(0.10, 1)) * 0.85
        : activating ? Math.max(Math.sin(Math.PI * spinAngle / 360) * .45,
                               Math.sin(Math.PI * activationScan) * .85)
        : returning ? .65 * (1 - returnProgress)
        : focusing ? Math.sin(Math.PI * focusScanProgress) * .85 : 0
    signal positionRequested(real globalX, real globalY, rect packBounds, rect packOpening)
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
                && progress >= scanStartDuration / flightDuration) {
            entry.pause()
            waitingForContent = true
            progress = scanStartDuration / flightDuration
        }
        syncFlightPosition()
    }
    onReturnProgressChanged: syncFlightPosition()
    onWidthChanged: syncFlightPosition()
    onHeightChanged: syncFlightPosition()
    function packFlightPoint(distance) {
        const g = flightGeometry
        const startX = g.sourceX + g.sourceWidth / 2
        const startY = g.sourceY + g.sourceHeight / 2
        const endX = g.targetX + width / 2
        const endY = g.targetY + height / 2
        if (portFlight) {
            const gate = portSource.width > 0 ? portSource
                : Qt.rect(g.x + g.sourceX, g.y + g.sourceY, g.sourceWidth, g.sourceHeight)
            const gateY = gate.y - g.y + gate.height / 2
            const exitX = portBounds.x - g.x - gate.width / 2 - 12
            // First align the real list face vertically inside the pack. Only
            // then travel through the side port, so low rows never leak below.
            if (distance <= .2) {
                const t = easeInOut(distance / .2)
                return Qt.point(startX, startY + (gateY - startY) * t)
            }
            if (distance <= .5)
                return curve((distance - .2) / .3, startX, gateY,
                    startX - gate.width * .3, gateY,
                    exitX + gate.width * .3, gateY, exitX, gateY)
            return curve((distance - .5) * 2, exitX, gateY,
                exitX - gate.width * .2, gateY,
                endX + (exitX - endX) * .12, endY, endX, endY)
        }
        if (sleeveFlight) {
            const left = g.sourceX - g.sourceWidth / 2 - 12
            const top = Math.min(g.sourceY - g.sourceHeight * .65,
                                 packTop - g.y - g.sourceHeight * .15)
            const gateY = Math.max(g.screenTop - g.y + g.sourceHeight / 2 + 8,
                Math.min(g.screenBottom - g.y - g.sourceHeight / 2 - 8,
                         top + g.sourceHeight / 2))
            // Low cards first rise inside the sleeve, with no sideways escape.
            // Only pull left once their full body fits above the viewport bottom.
            const liftY = isFinite(packBottom)
                ? Math.min(startY, packBottom - g.y - g.sourceHeight / 2 - 8) : startY
            const liftEnd = liftY < startY ? .18 : 0
            if (distance < liftEnd)
                return Qt.point(startX, startY + (liftY - startY) * distance / liftEnd)
            if (distance <= .5)
                return curve((distance - liftEnd) / (.5 - liftEnd), startX, liftY, startX,
                    liftY + (gateY - liftY) * .8,
                    left + g.sourceWidth * .35, gateY, left, gateY)
            return curve((distance - .5) * 2, left, gateY,
                         left - g.sourceWidth * .1, gateY,
                         endX + (left - endX) * .12, endY, endX, endY)
        }
        // Pull diagonally through the upper-left sleeve corner first. The
        // tangent is independent of the landing window (which may be below or
        // to the right). Returning retraces this same curve into the sleeve.
        const controlX = startX - g.sourceWidth * 1.1
        const controlY = startY - g.sourceHeight * .7
        const approachX = endX + (startX - endX) * .12
        const remaining = 1 - distance
        return Qt.point(remaining * remaining * remaining * startX
                        + 3 * remaining * remaining * distance * controlX
                        + 3 * remaining * distance * distance * approachX
                        + distance * distance * distance * endX,
                        remaining * remaining * remaining * startY
                        + 3 * remaining * remaining * distance * controlY
                        + 3 * remaining * distance * distance * endY
                        + distance * distance * distance * endY)
    }
    function curve(t, x0, y0, x1, y1, x2, y2, x3, y3) {
        const r = 1 - t
        return Qt.point(r*r*r*x0 + 3*r*r*t*x1 + 3*r*t*t*x2 + t*t*t*x3,
                        r*r*r*y0 + 3*r*r*t*y1 + 3*r*t*t*y2 + t*t*t*y3)
    }
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
        const free = sleeveFlight ? Math.max(0, (eased - .5) * 2) : eased
        const angle = 8 * Math.sin(Math.PI * (sleeveFlight ? free : tick)) * Math.PI / 180
        const startScale = Math.min(g.sourceWidth / width, g.sourceHeight / height)
        const gateScale = portFlight && portSource.width > 0
            ? Math.min(portSource.width / width, portSource.height / height) : startScale
        const alignment = Math.min(1, eased / .2)
        const scale = portFlight
            ? g.sourceHeight / height + (gateScale - g.sourceHeight / height) * alignment
                + (1 - gateScale) * free
            : startScale + (1 - startScale) * free
        const scaleX = portFlight
            ? g.sourceWidth / width + (gateScale - g.sourceWidth / width) * alignment
                + (1 - gateScale) * free : scale
        const rotatedWidth = scaleX * width * Math.abs(Math.cos(angle))
            + scale * height * Math.abs(Math.sin(angle))
        const rotatedHeight = scale * height * Math.abs(Math.cos(angle))
            + scaleX * width * Math.abs(Math.sin(angle))
        const fitting = Math.min(1, width / rotatedWidth, height / rotatedHeight)
        const bounce = 1 - 0.008 * Math.sin(Math.PI * Math.max(0, (tick - .85) / .15))
        const footprintWidth = rotatedWidth * fitting * bounce
        const footprintHeight = rotatedHeight * fitting * bounce
        if (g.preserveSource) {
            const point = packFlightPoint(eased)
            if (sleeveFlight && eased > .5) {
                point.x = Math.max(g.screenLeft - g.x + footprintWidth / 2,
                    Math.min(g.screenRight - g.x - footprintWidth / 2, point.x))
                point.y = Math.max(g.screenTop - g.y + footprintHeight / 2,
                    Math.min(g.screenBottom - g.y - footprintHeight / 2, point.y))
            }
            const occluded = !sleeveFlight || eased <= .5
            // Grow the exposed list area while the face moves towards the port;
            // shrink it in reverse on return, ending at the actual row's head.
            const rowBottom = packClip.y + packClip.height
            const openingBottom = rowBottom + (packBottom - rowBottom) * alignment
            const opening = portFlight
                ? Qt.rect(packClip.x, packClip.y, packClip.width,
                          Math.max(1, openingBottom - packClip.y)) : packClip
            positionRequested(g.x + point.x - width / 2,
                              g.y + point.y - height / 2,
                              occluded ? Qt.rect(g.x + g.sourceX, g.y + g.sourceY,
                                      g.sourceWidth, g.sourceHeight) : Qt.rect(0, 0, 0, 0),
                              occluded ? opening : Qt.rect(0, 0, 0, 0))
            return
        }
        const centerX = Math.max(footprintWidth / 2, Math.min(g.width - footprintWidth / 2,
            fromX + (toX - fromX) * eased))
        const centerY = Math.max(footprintHeight / 2, Math.min(g.height - footprintHeight / 2,
            fromY + (toY - fromY) * eased - 32 * Math.sin(Math.PI * tick)))
        positionRequested(g.x + centerX - width / 2, g.y + centerY - height / 2,
                          Qt.rect(0, 0, 0, 0), Qt.rect(0, 0, 0, 0))
    }
    function prepareFlight(geometry) {
        if (!mechanicalEnabled) {
            play()
            return
        }
        finish()
        packClip = cardFace ? cardFace.packVisibleRect : Qt.rect(0, 0, 0, 0)
        packTop = cardFace ? cardFace.packViewportTop : NaN
        packBottom = cardFace ? cardFace.packViewportBottom : NaN
        portBounds = cardFace ? cardFace.packPort : Qt.rect(0, 0, 0, 0)
        portSource = cardFace ? cardFace.packPortOrigin : Qt.rect(0, 0, 0, 0)
        ensureFace()
        entrySpinEnabled = true
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
    function easeInOut(value) {
        return value < .5 ? 4 * value * value * value : 1 - Math.pow(-2 * value + 2, 3) / 2
    }
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
        packTop = NaN
        returning = false
        progress = 1
        syncFlightPosition()
        flightGeometry = null
        entrySpinEnabled = false
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
            // The entry already mounted the face. A flip changes only visual
            // properties; it must not create or reparent the active card.
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
        packTop = cardFace ? cardFace.packViewportTop : NaN
        packBottom = cardFace ? cardFace.packViewportBottom : NaN
        portBounds = cardFace ? cardFace.packPort : Qt.rect(0, 0, 0, 0)
        portSource = cardFace ? cardFace.packPortOrigin : Qt.rect(0, 0, 0, 0)
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

    // Always paint a complete card, including the first frame. The native
    // window applies the stationary pack's occlusion when moving; a cropped
    // render buffer must never travel across the desktop with the window.
    Item {
        id: card
        objectName: "movingScriptCard"
        width: root.width; height: root.height
        opacity: root.fadeOpacity
        visible: !root.faceReleased
        transform: [
            Rotation {
                objectName: "mechanicalCardSpin"
                origin.x: card.width / 2; origin.y: card.height / 2
                axis { x: 0; y: 1; z: 0 }
                angle: root.displayedSpinAngle
            },
            Scale {
                origin.x: card.width / 2; origin.y: card.height / 2
                xScale: root.desktopFlight ? root.flightScaleX * root.fit * root.settleScale
                    : root.progress < 0.78
                    ? 0.72 + 0.28 * root.easeOut(root.phase(0, 0.78))
                    : 1 - 0.012 * Math.sin(Math.PI * root.phase(0.78, 1))
                yScale: root.desktopFlight ? root.flightScale * root.fit * root.settleScale : xScale
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
                    x: Theme.space4 * root.designScale
                    y: (Theme.space4 * root.designScale - parent.y) / root.faceAspectCompensation
                    width: card.width - Theme.space4 * root.designScale * 2
                    height: (card.height - Theme.space4 * root.designScale * 2)
                        / root.faceAspectCompensation
                    // Compact pack cards change layout height, not text shape.
                    // Counter the flight's outer Y scale for the live card face.
                    transform: Scale { yScale: root.faceAspectCompensation }
                    // The whole card owns the single 0..360 degree turn.
                    // Do not flip this face again at 90/270 degrees: that
                    // creates extra apparent turns in the middle of the spin.
                }
            }

            Item {
                anchors.fill: parent
                anchors.margins: Theme.space4 * root.designScale
                visible: root.mechanicalEnabled
                    && (root.entering || root.activating || root.recycling || root.focusing)
                clip: true

                Rectangle {
                    objectName: "mechanicalCardScan"
                    x: 2 * root.designScale
                    width: parent.width - 4 * root.designScale
                    // A soft light band straddles the reveal boundary. Broad,
                    // gradual highlights avoid a hard white line on dark cards.
                    height: 156 * root.designScale
                    y: parent.height * root.scan - height * .55
                    opacity: root.entering || root.recycling || root.focusing
                        || (root.activating && root.spinAngle >= 360)
                        ? Math.sin(Math.PI * root.scan) * 0.95 : 0
                    gradient: Gradient {
                        GradientStop { position: 0; color: "#00F12786" }
                        GradientStop { position: 0.18; color: "#04F12786" }
                        GradientStop { position: 0.38; color: "#20F12786" }
                        GradientStop { position: 0.52; color: "#65F12786" }
                        GradientStop { position: 0.62; color: "#55FA9AC5" }
                        GradientStop { position: 0.78; color: "#20F12786" }
                        GradientStop { position: 1; color: "#00F12786" }
                    }
                }
                Rectangle {
                    objectName: "mechanicalCardEdge"
                    anchors.fill: parent
                    anchors.margins: 1
                    radius: Theme.radiusMedium
                    color: "transparent"
                    border.width: 2 * root.designScale
                    border.color: root.accent
                    opacity: root.edgeStrength
                }
            }
        }
    }
}
