pragma ComponentBehavior: Bound
import QtQuick
import "../theme"

// Decade alone owns pack layout, occlusion and card launch/landing geometry.
ScriptCollectionView {
    id: root
    required property ScriptCardStore cardStore
    property bool continuousRecall: false
    property var pendingLaunches: []
    pendingLaunchCount: pendingLaunches.length
    readonly property var returningIds: controller.returningCardIds
    readonly property int deckReflowDuration: 160
    readonly property real cardWidth: root.width - root.scrollGutter - 16
    readonly property real cardStep: 76 * Theme.scriptCardScale
    readonly property real cardHeight: Math.min(cardWidth * 672 / 432,
        Math.max(cardStep, height - topMargin))
    // Keep row extents uniform. Expanding the newly last delegate on removal
    // invalidates ListView's estimates and can teleport its origin to row zero.
    // The tail belongs to the view, so it survives taking the last card out.
    displayMarginBeginning: cardStep
    footer: Item {
        height: root.visibleCount > 0 ? Math.max(0, root.cardHeight - root.cardStep) : 0
    }
    // Reserve the same gutter throughout recall; only the handle disappears.
    // Restore after the final dock has settled its scroll extent.
    verticalScrollBar {
        width: 14
        padding: 0
        minimumSize: Math.min(1, 72 / Math.max(1, height))
        hoverEnabled: true
        visible: root.needsVerticalScroll && !root.continuousRecall && !scrollBarRestore.running
        contentItem: DecadeSwordHandle {
            highlighted: root.verticalScrollBar.pressed || root.verticalScrollBar.hovered
        }
        background: Item {}
    }
    onContinuousRecallChanged: {
        if (continuousRecall) {
            scrollBarRestore.stop();
            cancelBottomReveal();
        } else {
            scrollBarRestore.restart();
        }
    }
    Timer {
        id: scrollBarRestore
        interval: root.deckReflowDuration + 20
    }
    property real bottomRevealOffset: 0
    property string bottomAnchorId: ""
    property real bottomAnchorTop: 0
    contentItem.transform: Translate { y: root.bottomRevealOffset }
    settling: deckLayoutSettlement.running || bottomReveal.running
    function cancelBottomReveal() {
        bottomReveal.stop();
        bottomRevealOffset = 0;
        bottomAnchorId = "";
    }
    onDraggingChanged: if (dragging) cancelBottomReveal()
    onFlickingChanged: if (flicking) cancelBottomReveal()
    function revealPreviousCard() {
        if (!bottomAnchorId)
            return;
        root.forceLayout();
        const row = root.findRow(bottomAnchorId);
        bottomAnchorId = "";
        if (!row)
            return;
        bottomReveal.stop();
        // ListView settles its logical extent immediately. Counter that shift
        // in the visual layer, then reveal the previous card without a jump.
        bottomRevealOffset += bottomAnchorTop - row.mapToItem(root, 0, 0).y;
        bottomReveal.from = bottomRevealOffset;
        bottomReveal.start();
    }
    NumberAnimation {
        id: bottomReveal
        target: root
        property: "bottomRevealOffset"
        to: 0
        duration: root.deckReflowDuration
        easing.type: Easing.OutCubic
    }
    headingText: "DECADE / 脚本卡包"
    countSuffix: " 张卡牌"
    actionText: "点击抽卡"
    // A filter can collapse the delegates at the old scroll position to zero
    // height. Reset before laying them out, or the viewport can stay beyond
    // the new extent and never instantiate the remaining matching cards.
    onKindFilterChanged: {
        cancelBottomReveal();
        cancelFlick();
        positionViewAtBeginning();
        forceLayout();
    }
    // Keep offscreen delegates out of the incubation queue. Rapid row removals
    // otherwise race Qt DelegateModel cancellation; face ownership is in the store.
    topMargin: 10
    bottomMargin: 0
    emptyText: controller.openCardCount > 0 && controller.openCardCount === listModel.totalCount ? "卡牌已抽出，关闭卡牌后归还" : listModel.totalCount === 0 ? "暂无自定义脚本" : "没有匹配的脚本"
    Timer {
        id: deckLayoutSettlement
        interval: root.deckReflowDuration + 20
    }
    Timer {
        id: launchDispatch
        interval: 0
        onTriggered: root.dispatchLaunches()
    }
    Component.onDestruction: cancelPendingLaunches()
    function cancelPendingLaunches() {
        launchDispatch.stop();
        for (let request of pendingLaunches)
            cardStore.unlend(request.id);
        pendingLaunches = [];
    }
    function dispatchLaunches() {
        const requests = pendingLaunches;
        pendingLaunches = [];
        for (let request of requests) {
            const face = cardStore.peek(request.id);
            if (!face) {
                cardStore.unlend(request.id);
                continue;
            }
            const host = face.parent;
            try {
                toolActivatedAt(request.id, request.origin);
            } finally {
                if (face.parent === host)
                    cardStore.unlend(request.id);
            }
        }
    }
    Connections {
        target: root.listModel
        function onRowsAboutToBeRemoved(parentIndex, first, last) {
            const atCardEnd = root.atYEnd
                || root.contentY + root.height >= root.originY + root.contentHeight - 2;
            if (root.continuousRecall || !(atCardEnd || bottomReveal.running))
                return;
            const lastIndex = root.listModel.indexOfTool(root.listModel.lastToolId(root.kindFilter));
            if (lastIndex < first || lastIndex > last)
                return;
            for (let index = first - 1; index >= 0; index--) {
                const row = root.itemAtIndex(index);
                if (row && row.height > 0) {
                    root.bottomAnchorId = row.toolId;
                    root.bottomAnchorTop = row.mapToItem(root, 0, 0).y;
                    break;
                }
            }
        }
        function onCountChanged() {
            deckLayoutSettlement.restart();
            if (root.bottomAnchorId)
                Qt.callLater(root.revealPreviousCard);
        }
    }
    displaced: Transition {
        enabled: !root.continuousRecall
        NumberAnimation {
            properties: "x,y"
            duration: root.deckReflowDuration
            easing.type: Easing.OutCubic
        }
    }
    onActivationRequested: function (id, row) {
        handleActivation(id, row);
    }
    function handleActivation(id, row) {
        if (!id || returningIds.indexOf(id) >= 0)
            return;
        row = row || findRow(id);
        if (row)
            launchCard(id, row);
        else
            toolActivated(id);
    }
    function portOrigin(face) {
        // The shared port follows the pack, not a row or the scroll position.
        const point = root.mapToGlobal(-Theme.space16, -32);
        const height = root.height + 32;
        const width = Math.min(root.cardWidth, height * 440 / 680);
        const cardHeight = width * 680 / 440;
        const origin = Qt.rect(point.x, point.y + (height - cardHeight) / 2,
                               width, cardHeight);
        if (face) {
            face.packPort = Qt.rect(point.x, point.y, 1, height);
            face.packPortOrigin = origin;
            face.packViewportTop = point.y;
            face.packViewportBottom = point.y + height;
        }
        return origin;
    }
    function launchCard(id, row) {
        if (cardStore.isBorrowed(id))
            return;
        const face = cardStore.peek(id);
        if (!face)
            return;
        portOrigin(face);
        const point = face.mapToGlobal(0, 0);
        const scaleX = face.width / 432;
        const scaleY = face.height / 672;
        const origin = Qt.rect(point.x - 4 * scaleX, point.y - 4 * scaleY,
                               face.width + 8 * scaleX, face.height + 8 * scaleY);
        const viewport = root.mapToGlobal(0, 0);
        const top = Math.max(origin.y, viewport.y);
        const bottom = Math.min(origin.y + origin.height, viewport.y + root.height,
                                row.mapToGlobal(0, 0).y
                                    + (id === listModel.lastToolId(root.kindFilter)
                                       ? root.cardHeight : row.height));
        face.packVisibleRect = Qt.rect(origin.x, top, origin.width, Math.max(1, bottom - top));
        // Reserve synchronously, but create windows outside the MouseArea event.
        // Showing a native window can pump events and retire this very delegate.
        cardStore.lend(id);
        pendingLaunches = pendingLaunches.concat([
            {
                id: id,
                origin: origin
            }
        ]);
        launchDispatch.start();
    }
    function returnCardRect(toolId) {
        const face = cardStore.peek(toolId);
        portOrigin(face);
        if (!continuousRecall)
            root.forceLayout();
        const index = Math.min(listModel.insertionIndex(toolId), root.count - 1);
        if (index >= 0 && !continuousRecall) {
            root.positionViewAtIndex(index, ListView.Beginning);
            root.forceLayout();
            if (index === 0)
                root.contentY = root.originY - root.topMargin;
        }
        const row = index >= 0 ? root.itemAtIndex(index) as DeckRow : null;
        const point = !continuousRecall && row && row.height > 0 ? row.mapToGlobal(0, 0)
            : root.mapToGlobal(0, !continuousRecall && root.count === 0 ? root.topMargin : 0);
        const scaleX = root.cardWidth / 432;
        const scaleY = root.cardHeight / 672;
        const origin = Qt.rect(point.x + 8 - 4 * scaleX, point.y - 4 * scaleY,
                               root.cardWidth + 8 * scaleX, root.cardHeight + 8 * scaleY);
        if (face) {
            const viewport = root.mapToGlobal(0, 0);
            const top = Math.max(origin.y, viewport.y);
            const headBottom = (continuousRecall && returningIds.length > 1)
                || listModel.insertionIndex(toolId) < root.count
                ? point.y + root.cardStep : origin.y + origin.height;
            const bottom = Math.min(headBottom, viewport.y + root.height);
            face.packVisibleRect = Qt.rect(origin.x, top, origin.width, Math.max(1, bottom - top));
        }
        return origin;
    }
    function dockCardFace(id, face) {
        if (!face)
            return;
        root.forceLayout();
        const index = listModel.indexOfTool(id);
        if (index >= 0) {
            root.positionViewAtIndex(index, ListView.Beginning);
            root.forceLayout();
            if (!continuousRecall && index === 0)
                root.contentY = root.originY - root.topMargin;
        }
        const row = index >= 0 ? root.itemAtIndex(index) as DeckRow : null;
        if (continuousRecall && row && row.height > 0) {
            root.cancelFlick();
            root.contentY += row.mapToGlobal(0, 0).y - root.mapToGlobal(0, 0).y;
        }
        if (row && row.height > 0)
            face.attachTo(row.deckFace);
        else
            cardStore.park(id);
    }
    delegate: DeckRow {}
    component DeckRow: Item {
        id: scriptRow
        required property string toolId
        required property string title
        required property string iconName
        required property string executorKind
        required property bool selected
        required property int index
        property alias deckFace: deckFace
        function mount() {
            root.cardStore.mount(toolId, deckFace, title, iconName);
        }
        Component.onCompleted: mount()
        Component.onDestruction: root.cardStore.park(toolId, deckFace)
        onTitleChanged: mount()
        objectName: "scriptRow_" + toolId
        onSelectedChanged: if (selected)
            root.positionViewAtIndex(index, ListView.Contain)
        width: root.width - root.scrollGutter

        height: (root.kindFilter === "all" || root.kindFilter === executorKind) ? root.cardStep : 0
        z: index
        visible: height > 0
        Item {
            id: deckFace
            x: 8
            width: root.cardWidth
            height: root.cardHeight
            Rectangle {
                x: -3
                y: -10
                width: parent.width + 6
                height: 22
                radius: Theme.radiusMedium + 2
                z: -2
                gradient: Gradient {
                    GradientStop {
                        position: 0
                        color: "#00000000"
                    }
                    GradientStop {
                        position: 0.65
                        color: "#B0000000"
                    }
                    GradientStop {
                        position: 1
                        color: "#E0000000"
                    }
                }
            }
        }
        MouseArea {
            x: deckFace.x
            width: deckFace.width
            height: deckFace.height
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                root.activateTool(scriptRow.toolId, scriptRow);
                root.forceActiveFocus();
            }
        }
    }
}
