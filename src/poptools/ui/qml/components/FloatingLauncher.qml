pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

Item {
    id: root
    required property var controller
    property string searchQuery: ""
    property bool attached: false
    property bool continuousRecall: false
    property var pendingReturns: []
    property var pendingDocks: []
    readonly property var zioDock: zioDockLoader.item
    function takeCardFace(toolId) { return scripts.takeCardFace(toolId) }
    function cancelCardLaunch(toolId) { scripts.cancelCardLaunch(toolId) }
    function dockCardFace(toolId, face, callback) {
        if (Theme.zioMode && zioDock)
            zioDock.dockCardFace(toolId, face)
        else
            scripts.dockCardFace(toolId, face)
        if (!Theme.mechanicalMode || !(Theme.zioMode ? zioDock && zioDock.dockWindow.visible : panel.visible)) {
            callback()
            return
        }
        // Close the old surface only after the pack has presented the same item.
        pendingDocks.push(callback)
        dockDeadline.restart()
        if (Theme.zioMode && zioDock) zioDock.dockWindow.update()
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
        pendingReturns.push({toolId: toolId, callback: callback, attempts: 0})
        returnPreparation.start()
        return true
    }
    Timer {
        id: returnPreparation
        interval: 16; repeat: true
        onTriggered: {
            const pending = root.pendingReturns
            root.pendingReturns = []
            for (let request of pending) {
                request.attempts++
                if (((Theme.zioMode ? zioDock && zioDock.dockWindow.revealProgress === 1 && zioDock.dockWindow.visible
                        : panel.revealProgress === 1 && panel.visible
                        && (root.continuousRecall || !scripts.layoutSettling)))
                        || request.attempts > 30)
                    request.callback(Theme.zioMode && zioDock ? zioDock.cardRect(request.toolId) : scripts.returnCardRect(request.toolId))
                else
                    root.pendingReturns.push(request)
            }
            if (root.pendingReturns.length === 0)
                stop()
        }
    }

    function cardOrigin(toolId) {
        return Theme.zioMode && zioDock ? zioDock.cardRect(toolId) : controller.cardLaunchOrigin(toolId)
    }
    function dockBounds() {
        if (!zioDock) return Qt.rect(0, 0, 0, 0)
        const dock = zioDock.dockWindow
        return Qt.rect(dock.x, dock.y, dock.width, dock.height)
    }
    function attachThemeWindow() {
        if (Theme.zioMode) {
            if (!zioDock) return
            panelSlide.stop()
            controller.attachDockWindow(zioDock.dockWindow, zioDock.preferredWidth, zioDock.preferredHeight)
            zioDock.syncProgress()
        } else {
            controller.attachDrawerWindow(panel, Theme.floatingTipWidth, Theme.floatingTipHeight,
                Theme.floatingPanelWidth, Theme.floatingPanelHeight)
            panel.updateReveal()
            controller.setDrawerProgress(panel.revealProgress)
        }
    }
    Component.onCompleted: {
        attached = true
        attachThemeWindow()
    }
    Connections {
        target: Theme
        function onZioModeChanged() { if (root.attached) root.attachThemeWindow() }
        function onFloatingPanelWidthChanged() { if (root.attached && !Theme.zioMode) root.attachThemeWindow() }
        function onFloatingPanelHeightChanged() { if (root.attached && !Theme.zioMode) root.attachThemeWindow() }
    }
    Loader {
        id: zioDockLoader
        active: Theme.zioMode
        onLoaded: if (root.attached) root.attachThemeWindow()
        sourceComponent: ZioDock {
            controller: root.controller
            cardStore: scripts.cardStore
            searchQuery: root.searchQuery
            onSearchEdited: function(query) {
                root.searchQuery = query
                root.controller.setToolSearchQuery(query)
            }
            onPreferredWidthChanged: if (root.attached && Theme.zioMode) root.attachThemeWindow()
            onFramePresented: if (root.pendingDocks.length > 0) root.finishCardDocks()
            onRecallRequested: root.controller.recallAllCards()
        }
    }

    ApplicationWindow {
        id: panel
        objectName: "floatingScriptPanelWindow"
        transientParent: null
        title: "自定义脚本快捷运行"
        width: Theme.floatingTipWidth
        height: Theme.floatingTipHeight
        readonly property bool revealRequested: root.controller.visible && root.controller.expanded
        property real revealProgress: 0
        property bool pendingMaskSettlement: false
        property bool dragMaskActive: false
        visible: root.attached && root.controller.visible && !Theme.zioMode
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "transparent"
        palette.text: Theme.textPrimary
        palette.windowText: Theme.textPrimary
        palette.highlight: Theme.primary
        palette.highlightedText: Theme.primaryForeground
        contentItem.clip: true

        onVisibleChanged: if (!visible) scripts.closeMenus()
        onFrameSwapped: {
            if (root.pendingDocks.length > 0)
                root.finishCardDocks()
            if (pendingMaskSettlement && !panelSlide.running && !root.controller.dragging) {
                pendingMaskSettlement = false;
                root.controller.setDrawerAnimating(false);
            }
        }

        function updateReveal() {
            if (!root.attached || Theme.zioMode)
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
            panelSlide.easing.type = requested ? Easing.OutCubic : Easing.InCubic;
            panelSlide.start();
        }
        Connections {
            target: root.controller
            function onStateChanged() {
                if (Theme.zioMode) return;
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
            duration: Theme.motionStandard
            onRunningChanged: {
                if (Theme.zioMode) return;
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
            x: (panel.width - Theme.floatingTipWidth)
                * (1 - panel.revealProgress)
            width: panel.width
            height: panel.height
            layer.enabled: true
            layer.smooth: true

            Rectangle {
                id: tip
                objectName: "floatingDrawerTip"
                x: 0
                y: root.controller.drawerTipOffset
                width: Theme.floatingTipWidth
                height: Theme.floatingTipHeight
                topLeftRadius: Theme.decadeMode ? Theme.decadePackRadius : Theme.radiusMedium
                bottomLeftRadius: Theme.decadeMode ? Theme.decadePackRadius : Theme.radiusMedium
                color: Theme.decadeMode ? (grip.containsMouse ? Theme.decadeCardActionFill : Theme.decadePackSurface) : grip.containsMouse || root.controller.expanded
                    ? Theme.primaryContainer : Theme.surfaceContainerLow
                border.width: 1
                border.color: Theme.decadeMode ? Theme.decadePackRail : Theme.outlineVariant
                opacity: grip.containsMouse || root.controller.dragging || root.controller.expanded
                    ? 1 : Theme.floatingIdleOpacity
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
                }
                Accessible.role: Accessible.Button
                Accessible.name: root.controller.expanded ? "收起自定义脚本" : "展开自定义脚本"
                Accessible.description: "点击展开或收起，拖动调整屏幕边缘的位置"
                Accessible.onPressAction: if (!panelSlide.running) root.controller.toggleExpanded()
                MouseArea {
                    id: grip
                    objectName: "floatingDragGrip"
                    anchors.fill: parent
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
                x: Theme.floatingTipWidth
                y: 0
                width: drawerSurface.width - Theme.floatingTipWidth
                height: panel.height
                enabled: panel.revealRequested
                radius: Theme.decadeMode ? Theme.decadePackRadius : Theme.radiusMedium
                topLeftRadius: tip.y < radius ? 0 : radius
                bottomLeftRadius: tip.y + tip.height > height - radius ? 0 : radius
                color: Theme.decadeMode ? Theme.decadePackSurface : Theme.surfaceContainerLow
                border.width: Theme.decadeMode ? 0 : 1
                border.color: Theme.outlineVariant

                DecadePackChrome { anchors.fill: parent; visible: Theme.decadeMode }

                // Join the grip to the panel without an internal border or corner gap.
                Rectangle {
                    x: -1
                    y: tip.y + panelSurface.border.width
                    width: 2
                    height: tip.height - 2 * panelSurface.border.width
                    color: panelSurface.color
                }

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: Theme.space12
                        Layout.leftMargin: Theme.space16
                        Layout.rightMargin: Theme.space8
                        Text {
                            visible: !Theme.decadeMode
                            Layout.fillWidth: true
                            text: "自定义脚本"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontComponentTitle
                            font.weight: Font.DemiBold
                        }
                        AppTextField {
                            id: titleSearch
                            objectName: "floatingTitleSearch"
                            visible: Theme.decadeMode
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredHeight: Theme.controlHeightSmall
                            leftPadding: 30
                            baseRightPadding: Theme.space8
                            clearButtonEnabled: true
                            placeholderText: "搜索脚本..."
                            text: root.searchQuery
                            color: Theme.textPrimary
                            font.pixelSize: Theme.decadeMode ? Theme.fontCaption : Theme.fontSupporting
                            onTextChanged: {
                                if (root.searchQuery !== text) {
                                    root.searchQuery = text;
                                    root.controller.setToolSearchQuery(text);
                                }
                            }
                            background: Rectangle {
                                radius: Theme.decadeMode ? Theme.radiusTiny : Theme.radiusSmall
                                color: Theme.decadeMode ? Theme.decadePackWell : Theme.surfaceContainer
                                border.width: titleSearch.activeFocus ? 1 : 0
                                border.color: Theme.primary
                                MaterialIcon {
                                    anchors.left: parent.left
                                    anchors.leftMargin: Theme.space8
                                    anchors.verticalCenter: parent.verticalCenter
                                    icon: "search"
                                    iconSize: 18
                                    color: Theme.decadeMode ? Theme.primaryText : Theme.textSecondary
                                }
                            }
                        }
                        PrimaryButton {
                            objectName: "floatingPinButton"
                            width: Theme.controlHeightSmall
                            height: Theme.controlHeightSmall
                            compact: true
                            showHoverTips: false
                            text: root.controller.pinned ? "取消置顶" : "置顶卡包"
                            iconName: "push_pin"
                            tonal: true
                            radius: Theme.decadeMode ? Theme.radiusTiny : Theme.radiusControl
                            border.width: 0
                            color: root.controller.pinned ? Theme.primaryContainer
                                : hovered ? Theme.surfaceContainer : "transparent"
                            foregroundColor: Theme.decadeMode ? Theme.primaryText : root.controller.pinned ? Theme.primary : Theme.textSecondary
                            Accessible.role: Accessible.CheckBox
                            Accessible.name: text
                            Accessible.checked: root.controller.pinned
                            Accessible.onPressAction: root.controller.togglePinned()
                            onClicked: root.controller.togglePinned()
                        }
                        PrimaryButton {
                            objectName: "floatingRecallAllButton"
                            width: Theme.controlHeightSmall
                            height: Theme.controlHeightSmall
                            compact: true
                            showHoverTips: false
                            text: Theme.decadeMode ? "收回全部卡牌" : "关闭全部脚本弹窗"
                            iconName: "layers_clear"
                            tonal: true
                            radius: Theme.decadeMode ? Theme.radiusTiny : Theme.radiusControl
                            border.width: 0
                            disabledOpacity: Theme.decadeMode ? 0.4 : 1
                            enabled: root.controller.openCardCount > 0 || scripts.pendingLaunchCount > 0
                            color: hovered ? Theme.surfaceContainer : "transparent"
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
                            objectName: "floatingCollapseButton"
                            width: Theme.controlHeightSmall
                            height: Theme.controlHeightSmall
                            compact: true
                            showHoverTips: false
                            text: "收起"
                            iconName: "chevron_right"
                            tonal: true
                            radius: Theme.decadeMode ? Theme.radiusTiny : Theme.radiusControl
                            border.width: 0
                            color: hovered ? Theme.surfaceContainer : "transparent"
                            onClicked: root.controller.collapse()
                        }
                    }
                    CustomScriptList {
                        continuousRecall: root.continuousRecall
                        id: scripts
                        objectName: "floatingScriptList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        controller: root.controller
                        listModel: root.controller.toolsModel
                        quickLaunch: true
                        showSearchAndFilters: !Theme.decadeMode
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
            sequence: "Esc"
            context: Qt.WindowShortcut
            enabled: root.controller.expanded
            onActivated: root.controller.collapse()
        }
    }
}
