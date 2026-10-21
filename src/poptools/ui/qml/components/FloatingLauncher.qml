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

    Component.onCompleted: {
        controller.attachDrawerWindow(panel, Theme.floatingTipWidth, Theme.floatingTipHeight,
            Theme.floatingPanelWidth, Theme.floatingPanelHeight);
        attached = true;
        panel.updateReveal();
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
        visible: root.attached && root.controller.visible
        flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        color: "transparent"
        palette.text: Theme.textPrimary
        palette.windowText: Theme.textPrimary
        palette.highlight: Theme.primary
        palette.highlightedText: Theme.primaryForeground
        contentItem.clip: true

        onVisibleChanged: if (!visible) scripts.closeMenus()
        onFrameSwapped: {
            if (pendingMaskSettlement && !panelSlide.running) {
                pendingMaskSettlement = false;
                root.controller.setDrawerAnimating(false);
            }
        }

        function updateReveal() {
            if (!root.attached)
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
            function onStateChanged() { panel.updateReveal(); }
        }
        NumberAnimation {
            id: panelSlide
            objectName: "floatingPanelSlideAnimation"
            target: panel
            property: "revealProgress"
            duration: Theme.motionStandard
            onRunningChanged: {
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
                topLeftRadius: Theme.radiusMedium
                bottomLeftRadius: Theme.radiusMedium
                color: grip.containsMouse || root.controller.expanded
                    ? Theme.primaryContainer : Theme.surfaceContainerLow
                border.width: 1
                border.color: Theme.outlineVariant
                opacity: grip.containsMouse || root.controller.dragging || root.controller.expanded
                    ? 1 : Theme.floatingIdleOpacity
                Behavior on opacity {
                    NumberAnimation { duration: Theme.motionStandard }
                }
                MaterialIcon {
                    anchors.centerIn: parent
                    icon: "drag_indicator"
                    iconSize: 18
                    color: root.controller.expanded ? Theme.primaryText : Theme.textSecondary
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
                radius: Theme.radiusMedium
                color: Theme.surfaceContainerLow
                border.width: 1
                border.color: Theme.outlineVariant

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: Theme.space12
                        Layout.leftMargin: Theme.space16
                        Layout.rightMargin: Theme.space8
                        Text {
                            Layout.fillWidth: true
                            text: "自定义脚本"
                            color: Theme.textPrimary
                            font.pixelSize: Theme.fontComponentTitle
                            font.weight: Font.DemiBold
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
                            border.width: 0
                            color: hovered ? Theme.surfaceContainer : "transparent"
                            onClicked: root.controller.collapse()
                        }
                    }
                    CustomScriptList {
                        id: scripts
                        objectName: "floatingScriptList"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        controller: root.controller
                        listModel: root.controller.toolsModel
                        quickLaunch: true
                        searchQuery: root.searchQuery
                        onSearchEdited: function(query) {
                            root.searchQuery = query;
                            root.controller.setToolSearchQuery(query);
                        }
                        onToolActivated: function(toolId) { root.controller.launchTool(toolId); }
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
