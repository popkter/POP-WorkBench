pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    required property var controller
    signal terminalFocusRequested()
    implicitHeight: 32
    readonly property real interactiveWidth: Math.min(width,
        terminalTabAddButton.x + terminalTabAddButton.width)
    readonly property real terminalTabMaximumWidth: Theme.terminalTabMaximumWidth
    readonly property real terminalTabMinimumWidth: Theme.terminalTabMinimumWidth
    readonly property int scrollButtonWidth: 24
    readonly property real availableTabWidth: Math.max(0,
        width - terminalTabAddButton.width - terminalTabs.spacing)
    // Decide overflow from minimum tab widths before reserving the bumpers,
    // so showing/hiding the buttons cannot cause a layout feedback loop.
    readonly property bool tabsOverflowing: root.controller.terminalTabs.length > 0
        && root.controller.terminalTabs.length * terminalTabMinimumWidth
            + (root.controller.terminalTabs.length - 1) * terminalTabs.spacing
            > availableTabWidth + 0.5
    readonly property real responsiveTerminalTabWidth: {
        var tabCount = Math.max(1, root.controller.terminalTabs.length)
        var bumperWidth = root.tabsOverflowing ? 2 * root.scrollButtonWidth : 0
        var totalSpacing = terminalTabs.spacing * (tabCount - 1)
        var fittedWidth = (root.availableTabWidth - bumperWidth - totalSpacing) / tabCount
        return Math.max(root.terminalTabMinimumWidth,
            Math.min(root.terminalTabMaximumWidth, fittedWidth))
    }
    property string renamingTabId: ""
    property string lastPressedTabId: ""
    property double lastTabPressTime: 0

    function activateTab(tabId) {
        root.controller.activateTerminalTab(tabId)
        root.terminalFocusRequested()
    }
    function createTab() {
        root.controller.createTerminalTab()
        root.terminalFocusRequested()
    }
    function closeTab(tabId) {
        root.controller.closeTerminalTab(tabId)
        root.terminalFocusRequested()
    }
    function beginRename(tabId) { root.renamingTabId = tabId }
    function handleTabPress(tabId) {
        var now = Date.now()
        if (root.lastPressedTabId === tabId && now - root.lastTabPressTime <= 500) {
            root.lastPressedTabId = ""
            root.lastTabPressTime = 0
            root.beginRename(tabId)
            return
        }
        root.lastPressedTabId = tabId
        root.lastTabPressTime = now
        root.activateTab(tabId)
    }
    function finishRename(tabId, title) {
        if (root.renamingTabId !== tabId)
            return
        root.controller.renameTerminalTab(tabId, title)
        root.renamingTabId = ""
        root.terminalFocusRequested()
    }
    function cancelRename(tabId) {
        if (root.renamingTabId !== tabId)
            return
        root.renamingTabId = ""
        root.terminalFocusRequested()
    }
    function tabIndex(tabId) {
        var tabs = root.controller.terminalTabs
        for (var index = 0; index < tabs.length; ++index) {
            if (tabs[index].tabId === tabId)
                return index
        }
        return -1
    }
    function ensureActiveTerminalTabVisible() {
        if (terminalTabFlick.width <= 0)
            return
        var maximumContentX = Math.max(0,
            terminalTabFlick.contentWidth - terminalTabFlick.width)
        if (maximumContentX <= 0) {
            terminalTabFlick.contentX = 0
            return
        }
        terminalTabFlick.contentX = Math.max(0,
            Math.min(maximumContentX, terminalTabFlick.contentX))
        var index = root.tabIndex(root.controller.activeTerminalTabId)
        if (index < 0)
            return
        var tabLeft = index * (root.responsiveTerminalTabWidth + terminalTabs.spacing)
        var tabRight = tabLeft + root.responsiveTerminalTabWidth
        var viewportLeft = terminalTabFlick.contentX
        var viewportRight = viewportLeft + terminalTabFlick.width
        if (tabLeft < viewportLeft)
            terminalTabFlick.contentX = Math.max(0, tabLeft)
        else if (tabRight > viewportRight)
            terminalTabFlick.contentX = Math.min(maximumContentX,
                tabRight - terminalTabFlick.width)
    }
    function scrollTerminalTabs(delta) {
        var maximumContentX = Math.max(0,
            terminalTabFlick.contentWidth - terminalTabFlick.width)
        terminalTabFlick.contentX = Math.max(0,
            Math.min(maximumContentX, terminalTabFlick.contentX + delta))
    }

    Shortcut { sequence: "Ctrl+Shift+T"; context: Qt.WindowShortcut; enabled: root.visible && root.enabled && root.renamingTabId.length === 0 && root.controller.canCreateTerminalTab; onActivated: root.createTab() }
    Shortcut { sequence: "Ctrl+Shift+W"; context: Qt.WindowShortcut; enabled: root.visible && root.enabled && root.renamingTabId.length === 0; onActivated: root.closeTab(root.controller.activeTerminalTabId) }
    Shortcut { sequence: "Ctrl+Tab"; context: Qt.WindowShortcut; enabled: root.visible && root.enabled && root.renamingTabId.length === 0; onActivated: { root.controller.activateRelativeTerminalTab(1); root.terminalFocusRequested() } }
    Shortcut { sequence: "Ctrl+Shift+Tab"; context: Qt.WindowShortcut; enabled: root.visible && root.enabled && root.renamingTabId.length === 0; onActivated: { root.controller.activateRelativeTerminalTab(-1); root.terminalFocusRequested() } }

    onWidthChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
    onVisibleChanged: if (!visible) root.renamingTabId = ""
    Connections {
        target: root.controller
        function onTerminalTabsChanged() {
            Qt.callLater(root.ensureActiveTerminalTabVisible)
        }
    }

    component TabScrollButton: Button {
        id: scrollButton
        property string glyph
        width: root.scrollButtonWidth
        height: 28
        anchors.verticalCenter: parent.verticalCenter
        visible: root.tabsOverflowing
        focusPolicy: Qt.NoFocus
        padding: 0
        autoRepeat: true
        autoRepeatDelay: 400
        autoRepeatInterval: 75
        opacity: enabled ? 1 : 0.35
        Accessible.name: text
        contentItem: MaterialIcon {
            icon: scrollButton.glyph
            iconSize: 12
            color: Theme.chromeForeground
        }
        background: Rectangle {
            radius: Theme.radiusTiny
            color: scrollButton.hovered || scrollButton.down
                ? Theme.navigationHover : "transparent"
        }
        HoverTips {
            visible: scrollButton.enabled && scrollButton.hovered
            text: scrollButton.text
        }
    }

    TabScrollButton {
        id: scrollBackwardButton
        objectName: "terminalTabsScrollBackward"
        x: 0
        text: "向左滚动标签"
        glyph: "chevron_left"
        enabled: terminalTabFlick.contentX > 0.5
        // Match the WinUI TabView bumpers' 50-DIP step, including press-and-hold.
        onClicked: root.scrollTerminalTabs(-50)
    }

    TabScrollButton {
        id: scrollForwardButton
        objectName: "terminalTabsScrollForward"
        x: terminalTabAddButton.x - terminalTabs.spacing - width
        text: "向右滚动标签"
        glyph: "chevron_right"
        enabled: terminalTabFlick.contentX
            < terminalTabFlick.contentWidth - terminalTabFlick.width - 0.5
        onClicked: root.scrollTerminalTabs(50)
    }

    Flickable {
        id: terminalTabFlick
        objectName: "terminalTabFlick"
        x: root.tabsOverflowing ? scrollBackwardButton.width : 0
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: Math.max(0, (root.tabsOverflowing ? scrollForwardButton.x
            : terminalTabAddButton.x - terminalTabs.spacing) - x)
        contentWidth: terminalTabs.implicitWidth
        contentHeight: height
        clip: true
        interactive: contentWidth > width
        flickableDirection: Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        onWidthChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
        onContentWidthChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
        Row {
            id: terminalTabs
            anchors.bottom: parent.bottom
            spacing: Theme.space4
            Repeater {
                model: root.controller.terminalTabs
                delegate: Rectangle {
                    id: tab
                    required property int index
                    required property var modelData
                    width: root.responsiveTerminalTabWidth
                    height: root.height
                    topLeftRadius: Theme.radiusSmall
                    topRightRadius: Theme.radiusSmall
                    color: modelData.active ? Theme.terminalBackground
                        : tabHover.hovered ? Theme.navigationHover : "transparent"
                    objectName: "terminalTab_" + modelData.tabId
                    Accessible.role: Accessible.PageTab
                    Accessible.name: modelData.title || "终端"
                    Accessible.onPressAction: root.activateTab(modelData.tabId)
                    HoverHandler { id: tabHover }
                    RowLayout {
                        z: 1
                        anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: Theme.space8; spacing: 8
                        MaterialIcon {
                            icon: "terminal"
                            iconSize: 16
                            color: tab.modelData.active ? Theme.consoleText : Theme.chromeForeground
                        }
                        Text {
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            visible: root.renamingTabId !== tab.modelData.tabId
                            text: tab.modelData.title || "终端"
                            color: tab.modelData.active
                                ? Theme.consoleText
                                : Theme.chromeForeground
                            font.pixelSize: Theme.fontSupporting
                            elide: Text.ElideRight
                        }
                        AppTextField {
                            id: renameField
                            objectName: "terminalTabRename_" + tab.modelData.tabId
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            Layout.preferredHeight: 28
                            visible: root.renamingTabId === tab.modelData.tabId
                            color: Theme.consoleText
                            font.pixelSize: Theme.fontSupporting
                            leftPadding: 6; rightPadding: 6; topPadding: 0; bottomPadding: 0
                            selectByMouse: true
                            background: Rectangle {
                                radius: Theme.radiusTiny
                                color: Theme.terminalBackground
                                border.color: Theme.primary
                                border.width: 1
                            }
                            onVisibleChanged: if (visible) {
                                text = tab.modelData.title
                                forceActiveFocus()
                                selectAll()
                            }
                            onEditingFinished: root.finishRename(tab.modelData.tabId, text)
                            Keys.onReturnPressed: function(event) {
                                root.finishRename(tab.modelData.tabId, text)
                                event.accepted = true
                            }
                            Keys.onEscapePressed: function(event) {
                                root.cancelRename(tab.modelData.tabId)
                                event.accepted = true
                            }
                        }
                        PrimaryButton {
                            objectName: "terminalTabClose_" + tab.modelData.tabId
                            visible: true
                            opacity: tab.modelData.active || tabHover.hovered ? 1 : 0
                            enabled: opacity > 0
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20
                            compact: true
                            text: "关闭终端标签"
                            iconName: "close"
                            glyphSize: 15
                            tonal: true
                            foregroundColor: tab.modelData.active ? Theme.consoleMuted : Theme.chromeForeground
                            color: hovered
                                ? (Theme.terminalTabHover)
                                : "transparent"
                            border.width: 0
                            radius: Theme.radiusTiny
                            onClicked: root.closeTab(tab.modelData.tabId)
                        }
                    }
                    MouseArea {
                        id: tabHoverArea
                        anchors.fill: parent
                        z: 0
                        hoverEnabled: true
                        acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                        cursorShape: Qt.PointingHandCursor
                        onPressed: function(mouse) {
                            if (mouse.button === Qt.LeftButton)
                                root.handleTabPress(tab.modelData.tabId)
                        }
                        onClicked: function(mouse) {
                            if (mouse.button === Qt.MiddleButton) {
                                root.closeTab(tab.modelData.tabId)
                            } else if (mouse.button === Qt.RightButton) {
                                root.activateTab(tab.modelData.tabId)
                                terminalTabContextMenu.tabId = tab.modelData.tabId
                                terminalTabContextMenu.popup(tab, mouse.x, mouse.y)
                            }
                        }
                    }
                    Rectangle {
                        z: 2
                        anchors.right: parent.right
                        anchors.rightMargin: -Math.floor(terminalTabs.spacing / 2)
                        anchors.verticalCenter: parent.verticalCenter
                        width: 1
                        height: 20
                        color: Theme.terminalTabDivider
                        opacity: 1
                        visible: !tab.modelData.active
                            && tab.index < root.controller.terminalTabs.length - 1
                            && !root.controller.terminalTabs[tab.index + 1].active
                    }
                }
            }
        }
    }

    PrimaryButton {
        id: terminalTabAddButton
        objectName: "terminalTabAddButton"
        z: 4
        x: Math.max(0, Math.min(terminalTabs.implicitWidth + terminalTabs.spacing, parent.width - width))
        anchors.verticalCenter: parent.verticalCenter
        width: 32
        height: 32
        radius: Theme.radiusTiny
        compact: true
        text: "新增终端标签 (Ctrl+T)"
        iconName: "add"
        glyphSize: 20
        tonal: true
        foregroundColor: Theme.chromeForeground
        border.width: 0
        color: hovered || pressed ? Theme.navigationHover : "transparent"
        enabled: root.controller.canCreateTerminalTab
        disabledOpacity: 1
        onClicked: root.createTab()
    }

    MouseArea {
        z: 3
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: function(wheel) {
            if (!terminalTabFlick.interactive) {
                wheel.accepted = false
                return
            }
            var delta = wheel.pixelDelta.x !== 0
                ? wheel.pixelDelta.x : wheel.pixelDelta.y
            if (delta === 0)
                delta = wheel.angleDelta.x !== 0
                    ? wheel.angleDelta.x : wheel.angleDelta.y
            root.scrollTerminalTabs(-delta)
            wheel.accepted = true
        }
    }

    AppMenu {
        id: terminalTabContextMenu
        property string tabId: ""
        AppMenuItem { text: "重命名"; onTriggered: root.beginRename(terminalTabContextMenu.tabId) }
        AppMenuItem {
            text: "恢复自动标题"
            enabled: {
                var index = root.tabIndex(terminalTabContextMenu.tabId)
                return index >= 0 && root.controller.terminalTabs[index].hasCustomTitle
            }
            onTriggered: root.controller.resetTerminalTabTitle(terminalTabContextMenu.tabId)
        }
        AppMenuSeparator {}
        AppMenuItem { text: "关闭"; onTriggered: root.closeTab(terminalTabContextMenu.tabId) }
        AppMenuItem {
            text: "关闭其他标签"
            enabled: root.controller.terminalTabs.length > 1
            onTriggered: root.controller.closeOtherTerminalTabs(terminalTabContextMenu.tabId)
        }
        AppMenuItem {
            text: "关闭右侧标签"
            enabled: {
                var index = root.tabIndex(terminalTabContextMenu.tabId)
                return index >= 0 && index < root.controller.terminalTabs.length - 1
            }
            onTriggered: root.controller.closeTerminalTabsToRight(terminalTabContextMenu.tabId)
        }
    }
}
