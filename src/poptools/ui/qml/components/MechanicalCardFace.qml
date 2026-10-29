import QtQuick
import "../theme"

Rectangle {
    id: root
    property string cardTitle: ""
    property string cardIcon: "terminal"
    property rect packVisibleRect: Qt.rect(0, 0, 0, 0)
    property real packViewportTop: NaN
    property real packViewportBottom: NaN
    property rect packPort: Qt.rect(0, 0, 0, 0)
    property rect packPortOrigin: Qt.rect(0, 0, 0, 0)
    readonly property color accent: Theme.primary
    radius: Theme.zioMode ? Math.max(4, Theme.decadeCardRadius * width / 440) : Theme.decadeCardRadius * width / 440
    color: Theme.zioMode && width < 120 ? Theme.decadeCardBackFill : Theme.decadeCardSurface
    border.color: root.accent
    border.width: Theme.zioMode ? Math.max(1.2, Theme.decadeCardBorderWidth * width / 440) : Theme.decadeCardBorderWidth * width / 440
    clip: true
    function attachTo(host) {
        parent = host
        x = 0; y = 0; rotation = 0; scale = 1
        width = Qt.binding(function() { return host.width })
        height = Qt.binding(function() { return host.height })
        visible = true
    }

    DecadeCardArtwork { anchors.fill: parent; backFace: true; iconName: root.cardIcon }

    // One design coordinate system keeps the pack face and flying face identical.
    Item {
        visible: !Theme.zioMode
        width: 432
        height: root.height / scale
        scale: root.width > 0 ? root.width / width : 1
        transformOrigin: Item.TopLeft
        Row {
            x: 18; y: 12; spacing: 3
            Repeater {
                model: 13
                Rectangle {
                    required property int index
                    width: index % 3 === 0 ? 5 : 2
                    height: 10
                    color: index % 4 === 0 ? root.accent : "#D9DAE1"
                }
            }
        }
        Text {
            x: 18; y: 38; width: parent.width - 36
            text: root.cardTitle
            color: Theme.textPrimary; font.pixelSize: Theme.decadeCardTitleSize; font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
        Rectangle {
            objectName: "decadeCardBackTitleDivider"
            x: 18; y: 70
            width: parent.width - 36
            height: Theme.borderWidthThin
            color: Theme.decadeCounterBorder
        }
    }
    Text {
        visible: Theme.zioMode
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: parent.width * 0.08
        text: root.cardTitle
        color: Theme.textPrimary
        font.pixelSize: Math.max(10, 18 * parent.width / 440)
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        maximumLineCount: 2
        wrapMode: Text.Wrap
        elide: Text.ElideRight
    }
}
