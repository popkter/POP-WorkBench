pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import "../theme"

Item {
    id: root
    required property var controller
    required property var deck
    readonly property int count: results.count
    readonly property real cardWidth: root.deck && root.deck.cardWidth !== undefined ? root.deck.cardWidth
        : Math.max(1, Math.min(width - 2, height * 432 / 672))
    readonly property real cardHeight: root.deck && root.deck.cardHeight !== undefined
        ? root.deck.cardHeight : cardWidth * 672 / 432
    ListView {
        id: results
        anchors.fill: parent
        model: root.visible ? root.controller.searchResultsModel : null
        clip: true
        spacing: 6
        snapMode: ListView.SnapToItem
        boundsBehavior: Flickable.StopAtBounds
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }
        delegate: Item {
            id: row
            required property string toolId
            required property string title
            required property string iconName
            objectName: "decadeSearchResult_" + toolId
            x: Math.round((results.width - width) / 2)
            width: root.cardWidth
            height: faceHost.height
            clip: true
            Component.onDestruction: if (root.deck && root.deck.cardStore) root.deck.cardStore.park(toolId, faceHost)
            Item {
                id: faceHost
                width: row.width
                height: root.cardHeight
                MechanicalCardFace {
                    anchors.fill: parent
                    cardTitle: row.title
                    cardIcon: row.iconName
                }

            }
            MouseArea {
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onDoubleClicked: function(mouse) { mouse.accepted = true }
                onClicked: if (root.deck) {
                    root.forceActiveFocus();
                    root.deck.launchSearchResult(row.toolId, faceHost, row.title, row.iconName, root);
                }
            }
            Accessible.role: Accessible.Button
            Accessible.name: title
            Accessible.onPressAction: if (root.deck)
                root.deck.launchSearchResult(row.toolId, faceHost, row.title, row.iconName, root)
        }
    }
    Text {
        anchors.centerIn: parent
        visible: results.count === 0
        text: "无匹配卡片"
        color: Theme.textSecondary
        font.pixelSize: Theme.fontCaption
    }
}
