import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

ColumnLayout {
    id: root
    required property var controller
    property real pixelsPerSecond: 100
    property real viewStart: 0
    property bool followPlayback: true
    property real hoverTime: 0
    property real hoverX: 0
    property bool hovering: false
    property real dragTime: -1
    readonly property real playheadTime: dragTime >= 0 ? dragTime : (controller ? controller.position : 0)
    property point previewPoint: Qt.point(0, 0)
    readonly property real duration: controller ? controller.duration : 0
    readonly property real minimumScale: Math.max(0.001, track.width / Math.max(1, duration))
    readonly property real maximumScale: Math.max(minimumScale, (controller ? controller.nominalFps : 30) * 200)
    readonly property real viewSpan: track.width / pixelsPerSecond
    readonly property real tickStep: {
        const steps = [0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5,
                       1, 2, 5, 10, 20, 30, 60, 120, 300, 600, 1800, 3600]
        for (let step of steps) if (step * pixelsPerSecond >= 64) return step
        return 3600
    }
    readonly property bool previewMatches: controller
        && Math.abs(controller.previewTarget - hoverTime) < 0.00001
    spacing: 2

    function timeText(seconds) {
        const ms = Math.max(0, Math.round(seconds * 1000))
        const h = Math.floor(ms / 3600000)
        return (h > 0 ? String(h).padStart(2, "0") + ":" : "")
            + String(Math.floor(ms / 60000) % 60).padStart(2, "0") + ":"
            + String(Math.floor(ms / 1000) % 60).padStart(2, "0") + "."
            + String(ms % 1000).padStart(3, "0")
    }
    function pan(start) {
        viewStart = Math.max(0, Math.min(Math.max(0, duration - viewSpan), start))
    }
    function zoomAt(factor, anchor) {
        const time = viewStart + anchor / pixelsPerSecond
        pixelsPerSecond = Math.max(minimumScale, Math.min(maximumScale, pixelsPerSecond * factor))
        pan(time - anchor / pixelsPerSecond)
        reload.restart()
    }
    function fit() { pixelsPerSecond = minimumScale; viewStart = 0; reload.restart() }
    function updateHover(x) {
        hoverX = Math.max(0, Math.min(track.width, x))
        hoverTime = Math.max(0, Math.min(Math.max(0, duration - 0.000001),
                                        viewStart + hoverX / pixelsPerSecond))
        previewPoint = track.mapToItem(preview.parent, hoverX, 0)
        if (!previewDelay.running) previewDelay.start()
    }
    function endHover() {
        hovering = false
        previewDelay.stop()
        if (controller) controller.clearPreview()
    }
    onPixelsPerSecondChanged: { reload.restart(); if (hovering) updateHover(hoverX) }
    onViewStartChanged: { reload.restart(); if (hovering) updateHover(hoverX) }
    onVisibleChanged: { if (visible) reload.restart(); else endHover() }
    onDurationChanged: { dragTime = -1; fit(); endHover() }

    Timer {
        id: reload
        interval: 120
        onTriggered: if (root.visible && root.controller && root.duration > 0)
            root.controller.requestThumbnails(root.viewStart,
                Math.min(root.duration, root.viewStart + root.viewSpan), root.pixelsPerSecond)
    }
    Timer {
        id: previewDelay
        interval: 55
        onTriggered: if (root.hovering) root.controller.requestPreview(root.hoverTime)
    }
    Timer {
        id: scrubDelay
        interval: 35
        onTriggered: if (pointer.pressed && pointer.pressedButtons & Qt.LeftButton)
            root.controller.scrub(root.hoverTime)
    }
    Connections {
        target: root.controller
        property bool wasPlaying: false
        function onFitRequested() { root.fit() }
        function onZoomRequested(factor) {
            root.zoomAt(factor, Math.max(0, Math.min(track.width,
                (root.controller.position - root.viewStart) * root.pixelsPerSecond)))
        }
        function onPositionChanged() {
            if (!root.controller.playing || !root.followPlayback) return
            const t = root.controller.position
            if (t < root.viewStart || t > root.viewStart + root.viewSpan)
                root.pan(t - root.viewSpan * 0.15)
        }
        function onChanged() {
            if (root.controller.playing && !wasPlaying) root.followPlayback = true
            wasPlaying = root.controller.playing
            if (!pointer.pressed && !root.controller.busy) root.dragTime = -1
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Text {
            text: root.controller ? root.timeText(root.controller.position) + " / " + root.timeText(root.duration) : ""
            color: Theme.textPrimary
            font.pixelSize: Theme.fontSupporting
            font.family: "Consolas"
        }
        Item { Layout.fillWidth: true }
        Text {
            visible: root.width >= 500
            text: root.controller && root.controller.detailed ? "逐帧刻度" : "时间轴"
            color: Theme.textSecondary
            font.pixelSize: Theme.fontMicro
        }
        VideoToolbar { controller: root.controller; mode: "timeline" }
    }
    Item {
        id: track
        objectName: "videoTimelineTrack"
        Layout.fillWidth: true
        Layout.preferredHeight: 104
        clip: true
        onWidthChanged: {
            if (root.pixelsPerSecond < root.minimumScale) root.pixelsPerSecond = root.minimumScale
            root.pan(root.viewStart)
            root.endHover()
            reload.restart()
        }
        Rectangle {
            y: 34; width: parent.width; height: 66
            radius: 4
            color: Theme.surfaceContainerHigh
        }
        Rectangle {
            x: -root.viewStart * root.pixelsPerSecond
            y: 34
            width: root.duration * root.pixelsPerSecond
            height: 66
            radius: 4
            color: Theme.primary
            opacity: 0.16
        }
        Repeater {
            model: root.controller ? root.controller.thumbnails : []
            Rectangle {
                required property var modelData
                objectName: "videoTimelineThumbnail"
                x: (modelData.start - root.viewStart) * root.pixelsPerSecond
                y: 53; height: 44
                width: Math.max(1, (modelData.end - modelData.start) * root.pixelsPerSecond)
                color: "#101217"
                clip: true
                Image {
                    objectName: "videoTimelineThumbnailPicture"
                    anchors.fill: parent
                    anchors.rightMargin: 1
                    source: modelData.source
                    fillMode: Image.PreserveAspectFit
                    cache: false
                }
                Rectangle { width: 1; height: parent.height; color: Theme.outline; opacity: 0.5 }
            }
        }
        Text {
            x: 7; y: 36; width: parent.width - 14
            text: root.controller ? root.controller.fileName : ""
            color: Theme.textSecondary
            font.pixelSize: Theme.fontMicro
            elide: Text.ElideRight
        }
        Repeater {
            model: Math.ceil(track.width / (root.tickStep / 5 * root.pixelsPerSecond)) + 2
            Rectangle {
                required property int index
                property real time: (Math.floor(root.viewStart / (root.tickStep / 5)) + index) * root.tickStep / 5
                x: (time - root.viewStart) * root.pixelsPerSecond
                y: 24; width: 1; height: 3
                visible: time <= root.duration
                color: Theme.outline
            }
        }
        Repeater {
            model: Math.ceil(track.width / (root.tickStep * root.pixelsPerSecond)) + 2
            Item {
                required property int index
                property real time: (Math.floor(root.viewStart / root.tickStep) + index) * root.tickStep
                x: (time - root.viewStart) * root.pixelsPerSecond
                width: 80; height: 48
                visible: time <= root.duration
                Text {
                    text: root.tickStep < 1 ? time.toFixed(root.tickStep < 0.01 ? 3 : root.tickStep < 0.1 ? 2 : 1) + "s"
                        : root.timeText(time).split(".")[0]
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontMicro
                }
                Rectangle { y: 20; width: 1; height: 7; color: Theme.textSecondary }
            }
        }
        Rectangle {
            visible: root.hovering && !pointer.pressed
            x: root.hoverX; y: 22; width: 1; height: 78
            color: Theme.textPrimary
            opacity: 0.45
        }
        Item {
            id: playhead
            objectName: "videoTimelinePlayhead"
            x: (root.playheadTime - root.viewStart) * root.pixelsPerSecond
            y: 17; width: 0; height: 87
            visible: root.duration > 0
            Rectangle {
                x: -1; y: 12; width: 2; height: parent.height - 12
                color: Theme.textPrimary
            }
            Canvas {
                x: -7; width: 14; height: 17
                property color handleColor: Theme.textPrimary
                onHandleColorChanged: requestPaint()
                onPaint: {
                    const ctx = getContext("2d")
                    ctx.clearRect(0, 0, width, height)
                    ctx.fillStyle = handleColor
                    ctx.beginPath()
                    ctx.moveTo(1, 1); ctx.lineTo(13, 1)
                    ctx.lineTo(13, 10); ctx.lineTo(7, 16); ctx.lineTo(1, 10)
                    ctx.closePath(); ctx.fill()
                }
            }
        }
        MouseArea {
            id: pointer
            objectName: "videoTimelinePointer"
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.MiddleButton
            enabled: root.duration > 0
            preventStealing: true
            cursorShape: pressed && pressedButtons & Qt.LeftButton ? Qt.ClosedHandCursor
                : Math.abs(mouseX - playhead.x) < 12 ? Qt.OpenHandCursor : Qt.PointingHandCursor
            property real dragX: 0
            property real dragStart: 0
            onEntered: { root.hovering = true; root.updateHover(mouseX) }
            onExited: if (!pressed) root.endHover()
            onPressed: mouse => {
                root.followPlayback = false
                root.updateHover(mouse.x)
                if (mouse.button === Qt.MiddleButton) {
                    dragX = mouse.x; dragStart = root.viewStart
                } else {
                    root.dragTime = root.hoverTime
                    root.controller.seek(root.dragTime)
                }
            }
            onPositionChanged: mouse => {
                root.hovering = containsMouse
                root.updateHover(mouse.x)
                if (pressed && pressedButtons & Qt.MiddleButton)
                    root.pan(dragStart + (dragX - mouse.x) / root.pixelsPerSecond)
                else if (pressed && pressedButtons & Qt.LeftButton) {
                    root.dragTime = root.hoverTime
                    if (!scrubDelay.running) scrubDelay.start()
                }
            }
            onReleased: mouse => {
                scrubDelay.stop()
                if (mouse.button === Qt.LeftButton) root.controller.seek(root.hoverTime)
                if (!containsMouse) root.endHover()
            }
            onCanceled: { root.dragTime = -1; scrubDelay.stop(); root.endHover() }
            onWheel: wheel => {
                root.followPlayback = false
                if (wheel.modifiers & Qt.ControlModifier)
                    root.zoomAt(wheel.angleDelta.y > 0 ? 1.3 : 1 / 1.3, wheel.x)
                else root.pan(root.viewStart - (wheel.angleDelta.x || wheel.angleDelta.y) / root.pixelsPerSecond)
                root.updateHover(wheel.x)
                wheel.accepted = true
            }
        }
    }
    ScrollBar {
        Layout.fillWidth: true
        Layout.preferredHeight: 12
        orientation: Qt.Horizontal
        policy: ScrollBar.AlwaysOn
        size: Math.min(1, root.viewSpan / Math.max(0.001, root.duration))
        position: root.viewStart / Math.max(0.001, root.duration)
        onPositionChanged: if (pressed) { root.followPlayback = false; root.pan(position * root.duration) }
        Accessible.name: "浏览时间轴范围"
    }
    Text {
        Layout.fillWidth: true
        text: "点击或拖动定位 · 悬停预览 · Ctrl + 滚轮缩放 · ← / → 逐帧"
        color: Theme.textSecondary
        font.pixelSize: Theme.fontMicro
        elide: Text.ElideRight
    }
    Popup {
        id: preview
        objectName: "videoHoverPreview"
        parent: Overlay.overlay
        width: Math.min(280, root.width)
        height: 188
        padding: 8
        modal: false; dim: false; focus: false
        closePolicy: Popup.NoAutoClose
        visible: root.hovering && root.visible && root.duration > 0
        x: Math.max(8, Math.min(parent.width - width - 8, root.previewPoint.x - width / 2))
        y: Math.max(8, root.previewPoint.y - height - 10)
        background: Rectangle {
            color: Theme.popupSurface
            radius: Theme.radiusSmall
            border.color: Theme.outline
        }
        contentItem: ColumnLayout {
            spacing: 5
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                color: "#101217"
                Image {
                    objectName: "videoHoverPicture"
                    anchors.fill: parent
                    source: root.previewMatches && root.controller ? root.controller.previewSource : ""
                    fillMode: Image.PreserveAspectFit
                    cache: false
                }
                BusyIndicator {
                    anchors.centerIn: parent
                    width: 28; height: 28
                    running: !root.previewMatches || (root.controller && root.controller.previewBusy)
                    visible: running
                }
            }
            Text {
                Layout.alignment: Qt.AlignHCenter
                text: root.timeText(root.previewMatches && root.controller.previewSource
                    ? root.controller.previewTime : root.hoverTime)
                color: Theme.textPrimary
                font.pixelSize: Theme.fontSupporting
            }
        }
    }
}
