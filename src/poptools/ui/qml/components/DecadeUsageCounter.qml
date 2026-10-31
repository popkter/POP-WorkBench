import QtQuick
import QtQuick.Shapes
import "../theme"

Item {
    id: root
    objectName: "decadeUsageCounter"
    property real count: 0
    readonly property real usageCount: Math.max(0, Math.floor(Number(count) || 0))
    // Integer division avoids floating log rounding at exact powers of ten.
    readonly property real unit: {
        let value = usageCount
        let scale = 1
        while (value >= 10) { value = Math.floor(value / 10); scale *= 10 }
        return scale
    }
    readonly property int filledCount: Math.min(10, Math.floor(usageCount / unit))
    readonly property string digits: String(usageCount)
    implicitHeight: Theme.decadeCounterHeight
    Accessible.role: Accessible.StaticText
    Accessible.name: "已使用 " + usageCount + " 次，每格 " + unit + " 次"

    Shape {
        anchors.fill: parent
        ShapePath {
            strokeColor: Theme.decadeCounterBorder
            strokeWidth: Theme.borderWidthThin
            fillColor: Theme.decadeCounterFill
            startX: 1; startY: 1
            PathLine { x: root.width - Theme.radiusMedium; y: 1 }
            PathLine { x: root.width - 1; y: Theme.radiusMedium }
            PathLine { x: root.width - 1; y: root.height - 1 }
            PathLine { x: Theme.radiusMedium; y: root.height - 1 }
            PathLine { x: 1; y: root.height - Theme.radiusMedium }
            PathLine { x: 1; y: 1 }
        }
    }
    Rectangle {
        x: Theme.space12; y: 0; width: 44; height: Theme.borderWidthMedium
        color: Theme.primary
    }
    Item {
        id: meter
        x: Theme.space12
        anchors.verticalCenter: parent.verticalCenter
        width: Math.max(0, divider.x - x - Theme.space12)
        height: Theme.decadeCounterSquareSize
        Row {
            id: barcode
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Repeater {
                model: 8
                Rectangle {
                    required property int index
                    width: index % 3 === 0 ? 3 : 1
                    height: 12
                    color: Theme.primaryText
                    opacity: 0.7
                }
            }
        }
        Row {
            id: blocks
            objectName: "decadeUsageBlocks"
            x: barcode.width + Theme.space8
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.decadeCounterSquareGap
            Repeater {
                model: 10
                Rectangle {
                    required property int index
                    objectName: "decadeUsageBlock_" + index
                    width: Math.max(1, Math.min(Theme.decadeCounterSquareSize,
                        (meter.width - blocks.x - blocks.spacing * 9) / 10))
                    height: width
                    color: index < root.filledCount ? Theme.decadeCounterGreen : Theme.decadeCounterEmpty
                    border.color: index < root.filledCount ? Theme.decadeCounterGreen : Theme.decadeCounterEmptyBorder
                    border.width: Theme.borderWidthThin
                    Rectangle {
                        anchors.fill: parent; anchors.margins: 2
                        color: "transparent"; border.width: 1
                        border.color: Theme.decadeCardSurface
                        opacity: index < root.filledCount ? 0.2 : 0
                    }
                }
            }
        }
    }
    Rectangle {
        id: divider
        x: numberReadout.x - Theme.space12
        y: Theme.space8; width: 1; height: parent.height - Theme.space16
        color: Theme.decadeCounterBorder
        Rectangle { width: 1; height: Theme.space12; color: Theme.primary }
    }
    Row {
        id: numberReadout
        anchors.right: parent.right; anchors.rightMargin: Theme.space12
        anchors.verticalCenter: parent.verticalCenter
        Text {
            text: "0".repeat(Math.max(0, 4 - root.digits.length))
            color: Theme.decadeCounterLeading
            font.family: "Consolas"; font.pixelSize: 32; font.weight: Font.DemiBold
        }
        Text {
            objectName: "decadeUsageValue"
            text: root.digits
            color: Theme.textPrimary
            font.family: "Consolas"; font.pixelSize: root.digits.length > 4 ? 22 : 32
            font.weight: Font.DemiBold
        }
    }
}
