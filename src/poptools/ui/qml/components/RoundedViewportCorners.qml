pragma ComponentBehavior: Bound
import QtQuick

// Cover only the four outside corners, keeping scrolling content and input
// untouched, without adding a full-page rendering layer.
Item {
    id: root
    required property real cornerRadius
    required property color outsideColor

    Repeater {
        model: 4
        delegate: Canvas {
            required property int index
            readonly property real size: Math.min(root.cornerRadius, root.width / 2, root.height / 2)
            readonly property color fillColor: root.outsideColor
            width: size
            height: size
            x: index === 1 || index === 2 ? root.width - size : 0
            y: index >= 2 ? root.height - size : 0
            rotation: index * 90
            antialiasing: true
            onWidthChanged: requestPaint()
            onHeightChanged: requestPaint()
            onFillColorChanged: requestPaint()
            onPaint: {
                const ctx = getContext("2d");
                ctx.clearRect(0, 0, width, height);
                if (size <= 0)
                    return;
                ctx.fillStyle = fillColor;
                ctx.beginPath();
                ctx.moveTo(0, 0);
                ctx.lineTo(size, 0);
                ctx.arc(size, size, size, -Math.PI / 2, -Math.PI, true);
                ctx.closePath();
                ctx.fill();
            }
        }
    }
}
