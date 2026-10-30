import QtQuick
import QtQuick.Shapes

// The cover and inner case share the lower-left cut corner.
Shape {
    id: root
    property color fillColor: "#17191D"
    property color edgeColor: "#5C6066"
    property real cut: Math.min(width * 0.19, 28)
    preferredRendererType: Shape.GeometryRenderer
    ShapePath {
        strokeWidth: 2
        strokeColor: root.edgeColor
        fillColor: root.fillColor
        joinStyle: ShapePath.MiterJoin
        startX: 2; startY: 2
        PathLine { x: root.width - 2; y: 2 }
        PathLine { x: root.width - 2; y: root.height - 2 }
        PathLine { x: root.cut; y: root.height - 2 }
        PathLine { x: 2; y: root.height - root.cut }
        PathLine { x: 2; y: 2 }
    }
}
