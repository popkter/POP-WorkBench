pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

Item {
    readonly property var _visualPalette: LauncherStyle.mechanical ? LauncherPalette : Theme

    id: root
    required property var controller
    property string searchQuery: ""
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
        if (LauncherStyle.decade) {
            titleSearch.forceActiveFocus()
            titleSearch.selectAll()
        } else {
            scripts.focusSearch()
        }
    }
    property bool attached: false
    property bool continuousRecall: false
    property var pendingReturns: []
    property var pendingDocks: []
    readonly property var zioDock: zioDockLoader.item
    function takeCardFace(toolId) { return scripts.takeCardFace(toolId) }
    function cancelCardLaunch(toolId) { scripts.cancelCardLaunch(toolId) }
    function dockCardFace(toolId, face, callback) {
        if (LauncherStyle.zio && zioDock)
            zioDock.dockCardFace(toolId, face)
        else
            scripts.dockCardFace(toolId, face)
        if (!LauncherStyle.mechanical || !(LauncherStyle.zio ? zioDock && zioDock.dockWindow.visible : panel.visible)) {
            callback()
            return
        }
        // Close the old surface only after the pack has presented the same item.
        pendingDocks.push(callback)
        dockDeadline.restart()
        if (LauncherStyle.zio && zioDock) zioDock.dockWindow.update()
        else panel.update()
    }
    function finishCardDocks() {
        dockDeadline.stop()
        const callbacks = pendingDocks
        pendingDocks = []
        for (let callback of callbacks) callback()
    }
    Timer {
        id: dockDeadline
        interval: 250
        // A hidden or suspended panel may stop producing frames altogether.
        onTriggered: root.finishCardDocks()
    }

    function prepareCardReturn(toolId, callback) {
        if (!controller.beginCardReturn(toolId))
            return false
        if (!controller.expanded) {
            callback(collapsedReturnOrigin(toolId))
            return true
        }
        pendingReturns.push({toolId: toolId, callback: callback, attempts: 0})
        returnPreparation.start()
        return true
    }
    function collapsedReturnOrigin(toolId) {
        const face = scripts.cardStore.peek(toolId)
        if (face) {
            face.packVisibleRect = Qt.rect(0, 0, 0, 0)
            face.packViewportTop = NaN
            face.packViewportBottom = NaN
            face.packPort = Qt.rect(0, 0, 0, 0)
            face.packPortOrigin = Qt.rect(0, 0, 0, 0)
        }
        return controller.collapsedCardOrigin()
    }
    Timer {
        id: returnPreparation
        interval: 16; repeat: true
        onTriggered: {
            const pending = root.pendingReturns
            root.pendingReturns = []
            for (let request of pending) {
                request.attempts++
                if (!root.controller.expanded)
                    request.callback(root.collapsedReturnOrigin(request.toolId))
                else if (((LauncherStyle.zio ? zioDock && zioDock.dockWindow.revealProgress === 1 && zioDock.dockWindow.visible
                        : panel.revealProgress === 1 && panel.visible
                        && (root.continuousRecall || !scripts.layoutSettling)))
                        || request.attempts > (LauncherStyle.decade ? 90 : 30))
                    request.callback(LauncherStyle.zio && zioDock ? zioDock.cardRect(request.toolId) : scripts.returnCardRect(request.toolId))
                else
                    root.pendingReturns.push(request)
            }
            if (root.pendingReturns.length === 0)
                stop()
        }
    }

    function cardOrigin(toolId) {
        return LauncherStyle.zio && zioDock ? zioDock.cardRect(toolId) : controller.cardLaunchOrigin(toolId)
    }
    function dockBounds() {
        if (!zioDock) return Qt.rect(0, 0, 0, 0)
        const dock = zioDock.dockWindow
        return Qt.rect(dock.x, dock.y, dock.width, dock.height)
    }
    function attachThemeWindow() {
        if (LauncherStyle.zio) {
            if (!zioDock) return
            panelSlide.stop()
            controller.attachDockWindow(zioDock.dockWindow, zioDock.preferredWidth, zioDock.preferredHeight)
            zioDock.syncProgress()
        } else {
            controller.attachDrawerWindow(panel, LauncherStyle.floatingTipWidth, LauncherStyle.floatingTipHeight,
                LauncherStyle.floatingPanelWidth, LauncherStyle.floatingPanelHeight)
            panel.updateReveal()
            controller.setDrawerProgress(panel.revealProgress)
        }
    }
    Component.onCompleted: {
        attached = true
        attachThemeWindow()
    }
    Connections {
        target: LauncherStyle
        function onZioChanged() { if (root.attached) root.attachThemeWindow() }
        function onFloatingPanelWidthChanged() { if (root.attached && !LauncherStyle.zio) root.attachThemeWindow() }
        function onFloatingPanelHeightChanged() { if (root.attached && !LauncherStyle.zio) root.attachThemeWindow() }
    }
    Loader {
        id: zioDockLoader
        active: LauncherStyle.zio
        onLoaded: if (root.attached) root.attachThemeWindow()
        sourceComponent: ZioDock {
            controller: root.controller
            cardStore: scripts.cardStore
            searchQuery: root.searchQuery
            onSearchEdited: function(query) {
                root.searchQuery = query
                root.controller.setToolSearchQuery(query)
            }
            onPreferredWidthChanged: if (root.attached && LauncherStyle.zio) root.attachThemeWindow()
            onFramePresented: if (root.pendingDocks.length > 0) root.finishCardDocks()
            onRecallRequested: root.controller.recallAllCards()
        }
    }

    ApplicationWindow {
        readonly property var floatingStylePalette: root._visualPalette
        id: panel
        readonly property bool glassBackgroundReady: desktopBackground.ready
        DesktopBackground {
            id: desktopBackground; hostWindow: panel; drawBackground: false
            // DWM's whole-HWND material also fills the transparent animation
            // canvas and the gap below the Tip. This irregular alpha window
            // must keep its material on the visible QML surfaces instead.
            enabledForWindow: false
            anchors.fill: parent; z: -10
        }
        objectName: "floatingScriptPanelWindow"
        transientParent: null
        title: "自定义脚本快捷运行"
        width: LauncherStyle.floatingTipWidth
        height: LauncherStyle.floatingTipHeight
        readonly property bool revealRequested: root.controller.visible && root.controller.expanded
        property real revealProgress: 0
        readonly property real motionProgress: (1 - Math.cos(Math.PI * revealProgress)) / 2
        readonly property real packExpansion: motionProgress
        readonly property real coverOpening: motionProgress
        readonly property real caseWidth: width / 2
        property bool pendingMaskSettlement: false
        property bool dragMaskActive: false
        visible: root.attached && root.controller.visible && !LauncherStyle.zio
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "transparent"
        palette.text: _visualPalette.textPrimary
        palette.windowText: _visualPalette.textPrimary
        palette.highlight: _visualPalette.primary
        palette.highlightedText: _visualPalette.primaryForeground
        contentItem.clip: true

        onVisibleChanged: if (!visible) {
            root.searchFocusPending = false
            scripts.closeMenus()
        }
        onRevealProgressChanged: root.finishSearchFocus()
        onFrameSwapped: {
            if (root.pendingDocks.length > 0)
                root.finishCardDocks()
            if (pendingMaskSettlement && !panelSlide.running && !root.controller.dragging) {
                root.controller.setDrawerAnimating(false);
                pendingMaskSettlement = false;
            }
        }

        function updateReveal() {
            if (!root.attached || LauncherStyle.zio)
                return;
            const requested = root.controller.visible && root.controller.expanded;
            if (!requested)
                scripts.closeMenus();
            if (!root.controller.visible) {
                panelSlide.stop();
                revealProgress = 0;
                root.controller.setDrawerProgress(0);
                pendingMaskSettlement = false;
                root.controller.setDrawerAnimating(false);
                return;
            }
            const targetProgress = requested ? 1 : 0;
            if (panelSlide.running && panelSlide.to === targetProgress)
                return;
            panelSlide.stop();
            if (revealProgress === targetProgress)
                return;
            panelSlide.from = revealProgress;
            panelSlide.to = targetProgress;
            panelSlide.easing.type = LauncherStyle.decade ? Easing.Linear
                : requested ? Easing.OutCubic : Easing.InCubic;
            panelSlide.start();
        }
        Connections {
            target: root.controller
            function onStateChanged() {
                if (LauncherStyle.zio) return;
                if (root.controller.dragging) {
                    panel.dragMaskActive = true;
                    panel.pendingMaskSettlement = false;
                    root.controller.setDrawerAnimating(true);
                } else if (panel.dragMaskActive) {
                    panel.dragMaskActive = false;
                    // Restore the precise native region only after the final
                    // dragged Tip position has reached the rendered frame.
                    panel.pendingMaskSettlement = true;
                    panel.update();
                }
                panel.updateReveal();
            }
        }
        NumberAnimation {
            id: panelSlide
            objectName: "floatingPanelSlideAnimation"
            target: panel
            property: "revealProgress"
            duration: LauncherStyle.decade ? 450 : Theme.motionStandard
            onRunningChanged: {
                if (LauncherStyle.zio) return;
                if (running) {
                    panel.pendingMaskSettlement = false;
                    root.controller.setDrawerAnimating(true);
                } else {
                    root.controller.setDrawerProgress(panel.revealProgress);
                    panel.pendingMaskSettlement = true;
                    panel.update();
                }
            }
        }

        Item {
            id: drawerSurface
            objectName: "floatingDrawerSurface"
            x: LauncherStyle.decade ? 0 : (panel.width - LauncherStyle.floatingTipWidth)
                * (1 - panel.revealProgress)
            width: panel.width
            height: panel.height
            layer.enabled: true
            layer.smooth: true

            DecadePackHinge {
                id: packHinge
                objectName: "decadePackScrollHinge"
                scrollView: LauncherStyle.decade ? scripts.collectionView : null
                interactive: panel.revealProgress === 1 && !root.continuousRecall
                onDraggingChanged: root.controller.setMenuOpen(dragging)
                x: tip.x + tip.width - width / 2
                y: tip.y + 12 * panel.packExpansion
                width: 8 + 12 * panel.packExpansion
                height: Math.max(1, tip.height - 24 * panel.packExpansion)
                z: 4
                visible: LauncherStyle.decade && panel.coverOpening > 0
                opacity: panel.coverOpening
            }
            Item {
                id: decadeSideRail
                objectName: "decadePackSideRail"
                x: panel.width - 44
                y: 30
                width: 30
                height: panel.height - 60
                z: 3
                visible: LauncherStyle.decade && panel.revealProgress === 1
                DecadePackControls {
                    id: sideActions
                    y: Math.round((parent.height - height - 36) / 2)
                    controller: root.controller
                    cardList: scripts
                }
                ToolSortButton {
                    id: sortKey
                    objectName: "decadePackSort"
                    x: 0
                    y: sideActions.y + sideActions.height + 6
                    width: 30; height: 30
                    controller: root.controller
                    cycleOnClick: true
                    glyphSize: 16
                    backgroundColor: "transparent"
                    hoverColor: "transparent"
                    foregroundColor: hovered ? _visualPalette.primaryText : "#A9B0BA"
                    border.width: 0
                    radius: 1
                    DecadePackControlFace {
                        anchors.fill: parent; z: -1
                        hovered: sortKey.hovered; pressed: sortKey.pressed
                    }
                }
            }

            Rectangle {
                id: tip
                objectName: "floatingDrawerTip"
                z: LauncherStyle.decade ? 2 : 0
                x: 0
                y: root.controller.drawerTipOffset * (LauncherStyle.decade ? 1 - panel.packExpansion : 1)
                width: LauncherStyle.decade ? LauncherStyle.floatingTipWidth
                    + (panel.caseWidth - LauncherStyle.floatingTipWidth) * panel.packExpansion : LauncherStyle.floatingTipWidth
                height: LauncherStyle.decade ? LauncherStyle.floatingTipHeight
                    + (panel.height - LauncherStyle.floatingTipHeight) * panel.packExpansion : LauncherStyle.floatingTipHeight
                topLeftRadius: LauncherStyle.decade ? LauncherStyle.decadePackRadius : Theme.radiusMedium
                bottomLeftRadius: LauncherStyle.decade ? LauncherStyle.decadePackRadius : Theme.radiusMedium
                color: LauncherStyle.decade || _visualPalette.glassMode ? "transparent" : _visualPalette.surfaceContainerLow
                GlassSurface {
                    anchors.fill: parent
                    cornerRadius: Theme.radiusMedium
                    tintColor: _visualPalette.surfaceContainerLow
                    z: -0.5
                }
                border.width: LauncherStyle.decade ? 0 : 1
                border.color: LauncherStyle.decade ? LauncherStyle.decadePackRail : _visualPalette.outlineVariant
                opacity: grip.containsMouse || root.controller.dragging || root.controller.expanded
                    ? 1 : LauncherStyle.decade ? 0.92 : Theme.floatingIdleOpacity
                Behavior on opacity {
                    NumberAnimation { duration: Theme.motionStandard }
                }
                Image {
                    objectName: "floatingTipAppIcon"
                    anchors.centerIn: parent
                    width: 28
                    height: 28
                    source: "../../../resources/icons/app-icon-ui.png"
                    sourceSize: Qt.size(width * Screen.devicePixelRatio,
                                        height * Screen.devicePixelRatio)
                    fillMode: Image.PreserveAspectFit
                    smooth: true
                    visible: !LauncherStyle.decade
                }
                Flipable {
                    objectName: "decadePackCoverBook"
                    anchors.fill: parent
                    visible: LauncherStyle.decade
                    front: DecadePackCover {
                        objectName: "decadeFloatingPackCover"
                        anchors.fill: parent
                        layer.enabled: true
                    }
                    back: DecadePackLining {
                        id: packLining
                        objectName: "decadePackInnerCover"
                        anchors.fill: parent
                        layer.enabled: true
                        searching: root.searchQuery.trim().length > 0
                        DecadeSearchResults {
                            id: searchResults
                            objectName: "decadeSearchResults"
                            x: titleSearch.x
                            y: titleSearch.y + titleSearch.height + 14
                            width: titleSearch.width
                            height: Math.max(1, parent.height - y - 36)
                            visible: packLining.searching
                            enabled: panel.revealProgress === 1
                            controller: root.controller
                            deck: scripts.collectionView
                        }
                        AppTextField {
                            id: titleSearch
                            objectName: "floatingTitleSearch"
                            visible: LauncherStyle.decade
                            enabled: panel.revealProgress === 1
                            x: 20; y: 40
                            width: Math.max(60, parent.width - 80)
                            height: 34
                            leftPadding: 30
                            baseRightPadding: Theme.space8
                            clearButtonEnabled: true
                            placeholderText: "搜索脚本..."
                            text: root.searchQuery
                            color: "#D4D8DF"
                            placeholderTextColor: "#7F8895"
                            font.pixelSize: LauncherStyle.decade ? Theme.fontCaption : Theme.fontSupporting
                            onTextChanged: {
                                if (root.searchQuery !== text) {
                                    root.searchQuery = text;
                                    root.controller.setToolSearchQuery(text);
                                }
                            }
                            background: Item {
                                Rectangle {
                                    anchors.fill: parent
                                    radius: 1
                                    color: "#07090C"
                                    border.color: titleSearch.activeFocus ? "#89516F" : "#3B424C"
                                }
                                Rectangle {
                                    anchors.fill: parent; anchors.margins: 3
                                    radius: 1
                                    color: "#0E1217"
                                    border.color: "#1E252D"
                                }
                                Rectangle {
                                    x: 1; y: 8
                                    width: 2; height: parent.height - 16
                                    color: titleSearch.activeFocus ? _visualPalette.primary : "#515B68"
                                }
                                MaterialIcon {
                                    anchors.left: parent.left
                                    anchors.leftMargin: Theme.space8
                                    anchors.verticalCenter: parent.verticalCenter
                                    icon: "search"
                                    iconSize: 16
                                    color: titleSearch.activeFocus ? _visualPalette.primaryText : "#8D98A6"
                                }
                            }
                        }
                    }
                    transform: Rotation {
                        objectName: "decadePackCoverTurn"
                        origin.x: tip.width
                        origin.y: tip.height / 2
                        axis { x: 0; y: 1; z: 0 }
                        // Lift the free edge toward the viewer before opening right.
                        angle: 180 * panel.coverOpening
                    }
                }
                Accessible.role: Accessible.Button
                Accessible.name: root.controller.expanded ? "收起自定义脚本" : "展开自定义脚本"
                Accessible.description: LauncherStyle.decade ? "点击放大并打开卡包，沿屏幕左侧上下拖动"
                    : "点击展开或收起，拖动调整屏幕边缘的位置"
                Accessible.onPressAction: if (!panelSlide.running) root.controller.toggleExpanded()
                MouseArea {
                    id: grip
                    objectName: "floatingDragGrip"
                    anchors.fill: parent
                    enabled: !LauncherStyle.decade || panel.revealProgress === 0
                    hoverEnabled: true
                    preventStealing: true
                    cursorShape: dragStarted ? Qt.ClosedHandCursor : Qt.OpenHandCursor
                    property point pressPosition: Qt.point(0, 0)
                    property bool dragStarted: false
                    onPressed: function(mouse) {
                        if (panelSlide.running) {
                            mouse.accepted = false;
                            return;
                        }
                        pressPosition = mapToGlobal(mouse.x, mouse.y);
                        dragStarted = false;
                    }
                    onPositionChanged: function(mouse) {
                        if (!pressed)
                            return;
                        if (!dragStarted) {
                            const position = mapToGlobal(mouse.x, mouse.y);
                            if (Math.max(Math.abs(position.x - pressPosition.x),
                                Math.abs(position.y - pressPosition.y)) < Theme.space8)
                                return;
                            dragStarted = true;
                            root.controller.beginDrag();
                        }
                        root.controller.updateDrag();
                    }
                    onReleased: {
                        if (dragStarted)
                            root.controller.endDrag();
                        else if (!panelSlide.running)
                            root.controller.toggleExpanded();
                        dragStarted = false;
                    }
                    onCanceled: {
                        if (dragStarted)
                            root.controller.endDrag();
                        dragStarted = false;
                    }
                }
            }

            Rectangle {
                id: panelSurface
                objectName: "floatingPanelSurface"
                x: LauncherStyle.decade ? tip.x : LauncherStyle.floatingTipWidth
                y: LauncherStyle.decade ? tip.y : 0
                width: LauncherStyle.decade ? tip.width : drawerSurface.width - LauncherStyle.floatingTipWidth
                height: LauncherStyle.decade ? tip.height : panel.height
                enabled: panel.revealRequested && (!LauncherStyle.decade || panel.revealProgress === 1)
                visible: !LauncherStyle.decade || panel.revealProgress > 0
                radius: LauncherStyle.decade ? LauncherStyle.decadePackRadius : Theme.radiusMedium
                topLeftRadius: !LauncherStyle.decade && tip.y < radius ? 0 : radius
                bottomLeftRadius: !LauncherStyle.decade && tip.y + tip.height > height - radius ? 0 : radius
                color: LauncherStyle.decade || _visualPalette.glassMode ? "transparent" : _visualPalette.surfaceContainerLow
                GlassSurface {
                    anchors.fill: parent; cornerRadius: parent.radius
                    tintColor: _visualPalette.surfaceContainerLow; z: -0.5
                }
                border.width: LauncherStyle.decade ? 0 : 1
                border.color: _visualPalette.outlineVariant

                DecadePackChrome { anchors.fill: parent; visible: LauncherStyle.decade }

                // Join the grip to the panel without an internal border or corner gap.
                Rectangle {
                    visible: !LauncherStyle.decade
                    x: -1
                    y: tip.y + panelSurface.border.width
                    width: 2
                    height: tip.height - 2 * panelSurface.border.width
                    color: panelSurface.color
                }

                ColumnLayout {
                    id: mainColumn
                    anchors.fill: parent
                    anchors.leftMargin: LauncherStyle.decade ? 12 : 0
                    anchors.rightMargin: LauncherStyle.decade ? 14 : 0
                    anchors.topMargin: LauncherStyle.decade ? 24 : 0
                    anchors.bottomMargin: LauncherStyle.decade ? 24 : 0
                    spacing: 0
                    RowLayout {
                        visible: !LauncherStyle.decade
                        Layout.fillWidth: true
                        Layout.topMargin: Theme.space12
                        Layout.leftMargin: Theme.space16
                        Layout.rightMargin: Theme.space8
                        Text {
                            visible: !LauncherStyle.decade
                            Layout.fillWidth: true
                            text: "自定义脚本"
                            color: _visualPalette.textPrimary
                            font.pixelSize: Theme.fontComponentTitle
                            font.weight: Font.DemiBold
                        }

                        PrimaryButton {
                            objectName: LauncherStyle.decade ? "standardHiddenPin" : "floatingPinButton"
                            Layout.preferredWidth: Theme.controlHeightSmall
                            Layout.preferredHeight: Theme.controlHeightSmall
                            width: Theme.controlHeightSmall
                            height: Theme.controlHeightSmall
                            compact: true
                            showHoverTips: false
                            text: root.controller.pinned ? "取消置顶" : "置顶卡包"
                            iconName: "push_pin"
                            tonal: true
                            radius: LauncherStyle.decade ? Theme.radiusTiny : Theme.radiusControl
                            border.width: 0
                            color: root.controller.pinned ? _visualPalette.primaryContainer
                                : hovered ? _visualPalette.surfaceContainer : "transparent"
                            foregroundColor: LauncherStyle.decade ? _visualPalette.primaryText : root.controller.pinned ? _visualPalette.primary : _visualPalette.textSecondary
                            Accessible.role: Accessible.CheckBox
                            Accessible.name: text
                            Accessible.checked: root.controller.pinned
                            Accessible.onPressAction: root.controller.togglePinned()
                            onClicked: root.controller.togglePinned()
                        }
                        PrimaryButton {
                            objectName: LauncherStyle.decade ? "standardHiddenRecall" : "floatingRecallAllButton"
                            Layout.preferredWidth: Theme.controlHeightSmall
                            Layout.preferredHeight: Theme.controlHeightSmall
                            width: Theme.controlHeightSmall
                            height: Theme.controlHeightSmall
                            compact: true
                            showHoverTips: false
                            text: LauncherStyle.decade ? "收回全部卡牌" : "关闭全部脚本弹窗"
                            iconName: "layers_clear"
                            tonal: true
                            radius: LauncherStyle.decade ? Theme.radiusTiny : Theme.radiusControl
                            border.width: 0
                            disabledOpacity: LauncherStyle.decade ? 0.4 : 1
                            enabled: root.controller.openCardCount > 0 || scripts.pendingLaunchCount > 0
                            color: hovered ? _visualPalette.surfaceContainer : "transparent"
                            Accessible.role: Accessible.Button
                            Accessible.name: text
                            function recall() {
                                scripts.cancelPendingLaunches()
                                root.controller.recallAllCards()
                            }
                            Accessible.onPressAction: recall()
                            onClicked: recall()
                        }
                        PrimaryButton {
                            objectName: LauncherStyle.decade ? "standardHiddenCollapse" : "floatingCollapseButton"
                            Layout.preferredWidth: Theme.controlHeightSmall
                            Layout.preferredHeight: Theme.controlHeightSmall
                            width: Theme.controlHeightSmall
                            height: Theme.controlHeightSmall
                            compact: true
                            showHoverTips: false
                            text: LauncherStyle.decade ? "合上卡包" : "收起"
                            iconName: LauncherStyle.decade ? "remove" : "chevron_right"
                            tonal: true
                            radius: LauncherStyle.decade ? Theme.radiusTiny : Theme.radiusControl
                            border.width: 0
                            color: hovered ? _visualPalette.surfaceContainer : "transparent"
                            onClicked: root.controller.collapse()
                        }
                    }
                    CustomScriptList {
                        deckCardWidth: LauncherStyle.decade ? Math.max(1, Math.min(
                            searchResults.width - 2, searchResults.height * 432 / 672)) : 0
                        continuousRecall: root.continuousRecall
                        id: scripts
                        objectName: "floatingScriptList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        controller: root.controller
                        listModel: root.controller.toolsModel
                        quickLaunch: true
                        showSearchAndFilters: !LauncherStyle.decade
                        searchQuery: root.searchQuery
                        onSearchEdited: function(query) {
                            root.searchQuery = query;
                            root.controller.setToolSearchQuery(query);
                        }
                        onToolActivated: function(toolId) { root.controller.launchTool(toolId); }
                        onToolActivatedAt: function(toolId, sourceRect) {
                            root.controller.launchToolFrom(toolId, sourceRect)
                        }
                        onMenuOpenChanged: root.controller.setMenuOpen(menuOpen)
                    }
                }
            }
        }
        HoverHandler {
            onHoveredChanged: root.controller.pointerChanged()
        }
        Shortcut {
            sequence: "Ctrl+F"
            context: Qt.WindowShortcut
            autoRepeat: false
            enabled: panel.visible && !LauncherStyle.zio
            onActivated: root.focusSearch()
        }
        Shortcut {
            sequence: "Esc"
            context: Qt.WindowShortcut
            enabled: root.controller.expanded
            onActivated: root.controller.collapse()
        }
    }
}
