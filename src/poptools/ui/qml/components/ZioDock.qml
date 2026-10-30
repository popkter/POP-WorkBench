pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

Item {
    id: root
    required property var controller
    required property ScriptCardStore cardStore
    property alias dockWindow: panel
    property string searchQuery: ""
    readonly property int preferredWidth: Math.min(960, Math.max(520, controller.toolsModel.count * 84 + 76))
    readonly property int preferredHeight: 176
    signal searchEdited(string query)
    signal framePresented()
    signal recallRequested()
    property bool searchFocusPending: false
    function focusSearch() {
        searchFocusPending = true
        if (!controller.expanded) controller.toggleExpanded()
        finishSearchFocus()
    }
    function finishSearchFocus() {
        if (!controller.visible || !controller.expanded) {
            searchFocusPending = false
            return
        }
        if (!searchFocusPending || panel.revealProgress !== 1) return
        searchFocusPending = false
        dockSearch.forceActiveFocus()
        dockSearch.selectAll()
    }

    function cardRect(id) {
        let index = controller.toolsModel.indexOfTool(id)
        if (index < 0 && searchQuery.length > 0) {
            searchEdited("")
            index = controller.toolsModel.indexOfTool(id)
        }
        if (index < 0) return controller.dockLaunchOrigin()
        cards.stopScrolling()
        cards.positionViewAtIndex(index, ListView.Contain)
        cards.forceLayout()
        cards.snapScroll()
        const row = cards.itemAtIndex(index)
        if (!row) return controller.dockLaunchOrigin()
        const point = row.faceHost.mapToGlobal(0, 0)
        return Qt.rect(point.x, point.y, 72, 104)
    }
    function dockCardFace(id, face) {
        cardStore.accept(id, face)
        controller.setCardOpen(id, false)
        cards.forceLayout()
        const row = cards.itemAtIndex(controller.toolsModel.indexOfTool(id))
        if (row) row.mountFace()
        panel.update()
    }
    function closeMenus() { sort.closeMenu() }
    function syncProgress() {
        if (Theme.zioMode) controller.setDrawerProgress(panel.revealProgress)
    }

    ApplicationWindow {
        id: panel
        objectName: "zioDockWindow"
        transientParent: null
        title: "ZIO / 脚本腰带"
        width: root.preferredWidth; height: root.preferredHeight
        visible: Theme.zioMode && root.controller.visible
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "transparent"
        property real revealProgress: root.controller.expanded ? 1 : 0
        Behavior on revealProgress {
            NumberAnimation {
                duration: Theme.motionStandard
                easing.type: Easing.OutCubic
            }
        }
        onRevealProgressChanged: {
            root.syncProgress()
            root.finishSearchFocus()
        }
        onVisibleChanged: if (!visible) {
            root.searchFocusPending = false
            root.closeMenus()
        }
        onFrameSwapped: root.framePresented()
        palette.text: Theme.textPrimary
        palette.highlight: Theme.primary
        palette.highlightedText: Theme.primaryForeground

        Item {
            id: body
            anchors.fill: parent
            opacity: panel.revealProgress
            visible: opacity > 0
            enabled: root.controller.expanded
            transform: Translate { y: 24 * (1 - panel.revealProgress) }
            Item {
                id: belt
                objectName: "zioDockBase"
                x: 0; y: 132; width: parent.width; height: 40
                ZioBeltBlock {
                    anchors.centerIn: parent
                    width: 76; height: 26
                    ribs: true
                }
                ZioBeltBlock {
                    id: searchBay
                    objectName: "zioSearchBeltBlock"
                    width: (parent.width - 64) / 2; height: parent.height
                    highlighted: dockSearch.activeFocus
                    AppTextField {
                        id: dockSearch
                        objectName: "zioDockSearch"
                        x: 6; y: 4; width: parent.width - 12; height: 32
                        leftPadding: 32
                        clearButtonEnabled: true
                        font.pixelSize: 12
                        placeholderText: "搜索脚本…"
                        text: root.searchQuery
                        onTextChanged: if (root.searchQuery !== text) root.searchEdited(text)
                        background: Item {}
                        ZioDial {
                            objectName: "zioDockBrandDial"
                            anchors.left: parent.left
                            anchors.leftMargin: 5
                            anchors.verticalCenter: parent.verticalCenter
                            width: 20; height: 20
                        }
                    }
                }
                Row {
                    id: actions
                    objectName: "zioDockActions"
                    anchors.right: parent.right
                    width: (parent.width - 64) / 2
                    height: parent.height
                    spacing: 4
                    readonly property real segmentWidth: width - 3 * spacing
                    ToolSortButton {
                        id: sort
                        objectName: "zioDockSort"
                        cycleOnClick: true
                        controller: root.controller
                        width: actions.segmentWidth * 0.29; height: 40; glyphSize: 18
                        compact: false; text: "排序"; labelFontSize: 11; contentSpacing: 4
                        popupAbove: true
                        showHoverTips: false
                        color: "transparent"
                        ZioBeltBlock {
                            anchors.fill: parent; z: -1
                            bevel: 10
                            highlighted: sort.hovered || sort.menuOpen
                        }
                        onMenuOpenChanged: root.controller.setMenuOpen(menuOpen)
                    }
                    PrimaryButton {
                        objectName: "zioDockPin"
                        width: actions.segmentWidth * 0.17; height: 30; glyphSize: 18
                        y: (actions.height - height) / 2
                        compact: true; tonal: true; iconName: "push_pin"
                        showHoverTips: false
                        text: root.controller.pinned ? "取消置顶" : "置顶腰带"
                        color: "transparent"; border.width: 0
                        ZioBeltBlock {
                            anchors.fill: parent; z: -1
                            highlighted: parent.hovered || root.controller.pinned
                        }
                        onClicked: root.controller.togglePinned()
                    }
                    PrimaryButton {
                        objectName: "zioDockRecall"
                        width: actions.segmentWidth * 0.35; height: 36; glyphSize: 18
                        y: (actions.height - height) / 2
                        compact: false; tonal: true; iconName: "layers_clear"; text: "回收"
                        labelFontSize: 11; contentSpacing: 4
                        showHoverTips: false
                        color: "transparent"; border.width: 0
                        ZioBeltBlock { anchors.fill: parent; z: -1; bevel: 9; highlighted: parent.hovered }
                        onClicked: root.recallRequested()
                    }
                    PrimaryButton {
                        objectName: "zioDockCollapse"
                        width: actions.segmentWidth * 0.19; height: 30; glyphSize: 18
                        y: (actions.height - height) / 2
                        compact: true; tonal: true; iconName: "expand_more"; text: "收起腰带"
                        showHoverTips: false
                        color: "transparent"; border.width: 0
                        ZioBeltBlock { anchors.fill: parent; z: -1; highlighted: parent.hovered }
                        onClicked: root.controller.collapse()
                    }
                }
            }
            ListView {
                id: cards
                objectName: "zioDockCards"
                x: (parent.width - width) / 2; y: 0
                // Show whole slots at both viewport edges, including the 8px end gutters.
                width: Math.min(Math.max(88, Math.floor((parent.width - 68) / 84) * 84 + 4),
                    Math.max(88, count * 84 + 4))
                height: 126
                orientation: ListView.Horizontal
                spacing: 12; clip: true
                header: Item { width: 8; height: 1 }
                footer: Item { width: 8; height: 1 }
                model: Theme.zioMode ? root.controller.toolsModel : null
                boundsBehavior: Flickable.StopAtBounds
                // Keep neighbouring faces mounted throughout a slide.
                cacheBuffer: width
                readonly property real minimumContentX: originX
                readonly property real maximumContentX: Math.max(minimumContentX,
                    originX + contentWidth - width)
                property int wheelDirection: 0
                property int notchDirection: 0
                property real scrollTarget: 0
                readonly property bool scrollAnimating: scrollMotion.running
                function stopScrolling() {
                    scrollMotion.stop()
                    wheelSnap.stop()
                    cancelFlick()
                }
                function animateScroll(target) {
                    scrollMotion.stop()
                    cancelFlick()
                    scrollTarget = Math.max(minimumContentX, Math.min(maximumContentX, target))
                    scrollMotion.from = contentX
                    scrollMotion.to = scrollTarget
                    scrollMotion.start()
                }
                function scrollNotches(angle) {
                    if (!angle) return
                    wheelSnap.stop()
                    const direction = angle > 0 ? -1 : 1
                    // Accumulate matching notches, but reverse immediately on a direction change.
                    const position = ((scrollMotion.running && notchDirection === direction
                        ? scrollTarget : contentX) - minimumContentX) / 84
                    notchDirection = direction
                    const steps = Math.max(1, Math.round(Math.abs(angle) / 120))
                    // Up reveals earlier slots; down reveals later slots.
                    const index = direction > 0 ? Math.floor(position + 0.000001) + steps
                        : Math.ceil(position - 0.000001) - steps
                    animateScroll(minimumContentX + index * 84)
                }
                function scrollPixels(delta) {
                    if (!delta) return
                    scrollMotion.stop()
                    notchDirection = 0
                    wheelDirection = delta > 0 ? -1 : 1
                    const target = contentX - delta
                    cancelFlick()
                    contentX = Math.max(minimumContentX, Math.min(maximumContentX, target))
                    wheelSnap.restart()
                }
                function snapWheelScroll() {
                    const position = (contentX - minimumContentX) / 84
                    const index = wheelDirection > 0 ? Math.ceil(position - 0.000001)
                        : Math.floor(position + 0.000001)
                    animateScroll(minimumContentX + index * 84)
                }
                function snapScroll() {
                    stopScrolling()
                    contentX = Math.max(minimumContentX, Math.min(maximumContentX,
                        minimumContentX + Math.round((contentX - minimumContentX) / 84) * 84))
                }
                function settleBounds() {
                    if (!Theme.zioMode) return
                    forceLayout()
                    snapScroll()
                }
                onMovementEnded: if (!wheelSnap.running && !scrollMotion.running) snapScroll()
                onVisibleChanged: if (!visible) stopScrolling()
                NumberAnimation {
                    id: scrollMotion
                    target: cards; property: "contentX"
                    duration: 220
                    easing.type: Easing.OutCubic
                }
                Timer {
                    id: wheelSnap
                    interval: 120
                    onTriggered: cards.snapWheelScroll()
                }
                Timer {
                    id: layoutSettlement
                    property bool rewind: false
                    interval: 0
                    onTriggered: {
                        cards.stopScrolling()
                        if (rewind) cards.positionViewAtBeginning()
                        rewind = false
                        cards.settleBounds()
                    }
                }
                Component.onCompleted: layoutSettlement.restart()
                onCountChanged: if (layoutSettlement) layoutSettlement.restart()
                onWidthChanged: if (layoutSettlement) layoutSettlement.restart()
                Connections {
                    target: root.controller.toolsModel
                    function onModelReset() {
                        layoutSettlement.rewind = true
                        layoutSettlement.restart()
                    }
                    function onLayoutChanged() { layoutSettlement.restart() }
                }
                function selectAdjacent(direction) {
                    const id = root.controller.toolsModel.adjacentToolId(direction, "all")
                    root.controller.toolsModel.select(id)
                    const index = root.controller.toolsModel.indexOfTool(id)
                    if (index >= 0) currentIndex = index
                    stopScrolling()
                    positionViewAtIndex(currentIndex, ListView.Contain)
                }
                Keys.onLeftPressed: selectAdjacent(-1)
                Keys.onRightPressed: selectAdjacent(1)
                Keys.onReturnPressed: if (currentItem) currentItem.activate()
                Keys.onEnterPressed: if (currentItem) currentItem.activate()
                MouseArea {
                    parent: cards
                    anchors.fill: parent
                    z: 1
                    acceptedButtons: Qt.NoButton
                    scrollGestureEnabled: true
                    onWheel: function(event) {
                        const polarity = event.inverted ? -1 : 1
                        if (event.pixelDelta.x || event.pixelDelta.y)
                            cards.scrollPixels((event.pixelDelta.y || event.pixelDelta.x) * polarity)
                        else
                            cards.scrollNotches((event.angleDelta.y || event.angleDelta.x) * polarity)
                        event.accepted = true
                    }
                }
                delegate: Item {
                    id: slot
                    required property string toolId
                    required property string title
                    required property string iconName
                    required property bool running
                    required property int index
                    property alias faceHost: host
                    readonly property bool borrowed: {
                        const revision = root.cardStore.revision
                        return root.cardStore.isBorrowed(toolId)
                    }
                    objectName: "zioSlot_" + toolId
                    width: 72; height: 126
                    function mountFace() {
                        if (Theme.zioMode) root.cardStore.mount(toolId, host, title, iconName)
                    }
                    function activate() {
                        cards.currentIndex = index
                        root.controller.toolsModel.select(toolId)
                        cards.forceActiveFocus()
                        root.controller.launchToolFrom(toolId, root.cardRect(toolId))
                    }
                    Component.onCompleted: Qt.callLater(mountFace)
                    Component.onDestruction: root.cardStore.park(toolId, host)
                    onTitleChanged: Qt.callLater(mountFace)
                    onIconNameChanged: Qt.callLater(mountFace)
                    Connections {
                        target: root.cardStore
                        function onRevisionChanged() { Qt.callLater(slot.mountFace) }
                    }
                    Connections {
                        target: Theme
                        function onZioModeChanged() { if (Theme.zioMode) Qt.callLater(slot.mountFace) }
                    }
                    Rectangle {
                        x: 0; y: 20; width: 72; height: 104; radius: 5
                        color: Theme.primaryContainer
                        border.color: Theme.primary
                        opacity: 0.2
                        visible: !slot.borrowed
                    }
                    Item {
                        id: host
                        objectName: "zioMiniCard_" + slot.toolId
                        x: 0; y: hover.containsMouse && !slot.borrowed ? 0 : 20
                        width: 72; height: 104
                        Behavior on y { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
                    }
                    // The live face flies with the window; a dim preview preserves the slot's identity.
                    Loader {
                        objectName: "zioBorrowedMiniCard_" + slot.toolId
                        x: host.x; y: host.y; width: host.width; height: host.height
                        active: slot.borrowed
                        opacity: 0.55
                        sourceComponent: MechanicalCardFace {
                            cardTitle: slot.title
                            cardIcon: slot.iconName
                            border.color: Qt.rgba(Theme.primary.r, Theme.primary.g, Theme.primary.b, 0.25)
                        }
                    }
                    Rectangle {
                        objectName: "zioRunningIndicator_" + slot.toolId
                        x: 33; y: 119; width: 6; height: 6; radius: 3
                        visible: slot.running
                        color: Theme.success
                    }
                    MouseArea {
                        id: hover
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onDoubleClicked: function(mouse) { mouse.accepted = true }
                        onClicked: slot.activate()
                    }
                    Accessible.role: Accessible.Button
                    Accessible.name: title + (running ? "，运行中" : "")
                    Accessible.onPressAction: activate()
                }
                Text {
                    anchors.centerIn: parent
                    visible: cards.count === 0
                    text: root.controller.toolsModel.totalCount === 0 ? "暂无脚本，请在工作台添加自定义脚本" : "没有匹配的脚本"
                    color: Theme.textSecondary; font.pixelSize: 13
                }
            }
        }
        Item {
            id: buckle
            objectName: "zioDockBuckle"
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            width: 48; height: 48
            opacity: grip.containsMouse || grip.dragging || root.controller.expanded
                ? 1 : Theme.floatingIdleOpacity
            Behavior on opacity { NumberAnimation { duration: Theme.motionStandard } }
            ZioDial {
                objectName: "zioDockButtonDial"
                anchors.fill: parent
                highlighted: grip.containsMouse || root.controller.expanded
            }
            MouseArea {
                id: grip
                anchors.fill: parent
                hoverEnabled: true
                property point pressPosition
                property bool dragging: false
                cursorShape: dragging ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                onPressed: function(mouse) { pressPosition = mapToGlobal(mouse.x, mouse.y); dragging = false }
                onPositionChanged: function(mouse) {
                    if (!pressed) return
                    const point = mapToGlobal(mouse.x, mouse.y)
                    if (!dragging && Math.max(Math.abs(point.x - pressPosition.x), Math.abs(point.y - pressPosition.y)) >= Qt.styleHints.startDragDistance) {
                        dragging = true
                        root.controller.beginDrag()
                    }
                    if (dragging) root.controller.updateDrag()
                }
                onReleased: {
                    if (dragging) root.controller.endDrag()
                    else root.controller.toggleExpanded()
                    dragging = false
                }
                onCanceled: { if (dragging) root.controller.endDrag(); dragging = false }
            }
            Accessible.role: Accessible.Button
            Accessible.name: root.controller.expanded ? "收起 ZIO 腰带" : "展开 ZIO 腰带"
            Accessible.onPressAction: root.controller.toggleExpanded()
        }
        HoverHandler { onHoveredChanged: if (Theme.zioMode) root.controller.pointerChanged() }
        Shortcut {
            sequence: "Ctrl+F"; context: Qt.WindowShortcut
            autoRepeat: false
            enabled: panel.visible
            onActivated: root.focusSearch()
        }
        Shortcut {
            sequence: "Esc"; context: Qt.WindowShortcut
            enabled: Theme.zioMode && root.controller.expanded
            onActivated: root.controller.collapse()
        }
    }
}
