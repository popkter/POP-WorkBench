import QtQuick

Item {
    id: root
    property var scrollView: null
    property bool interactive: true
    readonly property bool dragging: scrollInput.pressed
    readonly property bool scrollable: scrollView && scrollEnd > scrollStart + 0.5
    readonly property real scrollStart: scrollView ? scrollView.originY - scrollView.topMargin : 0
    readonly property real scrollEnd: scrollView ? Math.max(scrollStart,
        scrollView.originY + scrollView.contentHeight - scrollView.height + scrollView.bottomMargin) : 0
    readonly property real scrollProgress: scrollable
        ? Math.max(0, Math.min(1, (scrollView.contentY - scrollStart) / (scrollEnd - scrollStart))) : 0
    readonly property real trackTop: 16
    readonly property real trackHeight: Math.max(1, height - 32)
    function scrollTo(position) {
        if (!scrollable) return;
        scrollView.cancelFlick();
        scrollView.contentY = Math.max(scrollStart, Math.min(scrollEnd, position));
    }
    function dragThumb(y, offset) {
        const travel = Math.max(1, trackHeight - thumb.height);
        scrollTo(scrollStart + (y - offset - trackTop) / travel * (scrollEnd - scrollStart));
    }
    Accessible.role: Accessible.Slider
    Accessible.name: "卡片列表滚动条"
    Accessible.onIncreaseAction: if (scrollView) scrollTo(scrollView.contentY + scrollView.height * 0.8)
    Accessible.onDecreaseAction: if (scrollView) scrollTo(scrollView.contentY - scrollView.height * 0.8)
    Rectangle {
        anchors.fill: parent
        radius: width / 2
        border.color: "#63666C"
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: "#07080A" }
            GradientStop { position: 0.4; color: "#42454B" }
            GradientStop { position: 0.7; color: "#14161A" }
            GradientStop { position: 1; color: "#060709" }
        }
    }
    Repeater {
        model: 8
        Rectangle {
            required property int index
            x: -1; y: 18 + index * (root.height - 36) / 8
            width: root.width + 2; height: 5; radius: 2
            color: "#111216"
            border.color: "#4E5157"
        }
    }
    Rectangle {
        id: thumb
        objectName: "decadePackScrollThumb"
        x: 2
        y: root.scrollable ? root.trackTop + (root.trackHeight - height) * root.scrollProgress
            : root.height * 0.43
        width: root.width - 4
        height: root.scrollable ? Math.max(32, Math.min(root.trackHeight * 0.32,
            root.trackHeight * root.scrollView.height / Math.max(root.scrollView.height,
                root.scrollView.contentHeight + root.scrollView.topMargin + root.scrollView.bottomMargin)))
            : root.height * 0.21
        radius: 3; color: root.dragging ? "#E1E3E6" : "#B1B2B4"
        Rectangle {
            anchors.centerIn: parent
            width: 4; height: parent.height * 0.7
            radius: 2; color: "#292C31"
        }
    }
    MouseArea {
        id: scrollInput
        objectName: "decadePackScrollInput"
        anchors.fill: parent
        enabled: root.interactive && root.scrollable
        hoverEnabled: true
        preventStealing: true
        cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        property real grabOffset: 0
        onPressed: function(mouse) {
            grabOffset = mouse.y >= thumb.y && mouse.y <= thumb.y + thumb.height
                ? mouse.y - thumb.y : thumb.height / 2;
            root.dragThumb(mouse.y, grabOffset);
        }
        onPositionChanged: function(mouse) {
            if (pressed) root.dragThumb(mouse.y, grabOffset);
        }
        onWheel: function(wheel) {
            const delta = wheel.pixelDelta.y !== 0 ? wheel.pixelDelta.y
                : wheel.angleDelta.y / 120 * root.scrollView.cardStep;
            root.scrollTo(root.scrollView.contentY - delta);
            wheel.accepted = true;
        }
    }
}
