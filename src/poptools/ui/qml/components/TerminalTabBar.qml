pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    required property var controller
    property bool vertical: false
    readonly property color selectedBackground: vertical
        ? Qt.tint(_visualPalette.terminalBackground,
            Qt.rgba(_visualPalette.primary.r, _visualPalette.primary.g, _visualPalette.primary.b, 0.32)) : _visualPalette.terminalTabSelected
    readonly property color hoverBackground: vertical
        ? Qt.tint(_visualPalette.terminalBackground, Qt.rgba(_visualPalette.terminalForeground.r,
            _visualPalette.terminalForeground.g, _visualPalette.terminalForeground.b, 0.06)) : _visualPalette.terminalTabHover
    signal terminalFocusRequested()
    implicitHeight: 32
    readonly property real interactiveWidth: Math.min(width,
        terminalTabAddButton.x + terminalTabAddButton.width)
    readonly property var groupColors: [
        { id: "slate", name: "灰色", light: "#63748b", dark: "#a5b4c8" },
        { id: "blue", name: "蓝色", light: "#276dc4", dark: "#8bbcff" },
        { id: "red", name: "红色", light: "#ba4342", dark: "#ff9c99" },
        { id: "amber", name: "琥珀色", light: "#926100", dark: "#ffd47a" },
        { id: "green", name: "绿色", light: "#347543", dark: "#91d29a" },
        { id: "pink", name: "粉色", light: "#a73f76", dark: "#ffa6d2" },
        { id: "purple", name: "紫色", light: "#7850ad", dark: "#d4b0ff" },
        { id: "teal", name: "青色", light: "#007876", dark: "#71d9d0" }
    ]
    // Share the controller data across delegates and menus in the visible strip.
    readonly property var tabs: visible ? root.controller.terminalTabs : []
    readonly property var groups: visible ? (root.controller.terminalTabGroups || []) : []
    readonly property bool shortcutsEnabled: visible && enabled && renamingTabId.length === 0
        && !groupEditor.visible && !groupConfirmation.visible
    readonly property var groupsById: {
        var result = {}
        for (var group of root.groups)
            result[group.groupId] = group
        return result
    }
    readonly property var stripMetrics: {
        var count = 0
        var headers = 0
        var previousGroup = ""
        for (var tab of root.tabs) {
            var group = root.groupsById[tab.groupId]
            if (group && tab.groupId !== previousGroup)
                headers += root.groupHeaderWidth(group) + terminalTabs.spacing
            if (!group || !group.collapsed)
                ++count
            previousGroup = tab.groupId
        }
        return { count: count, extraWidth: Math.max(0, headers - (count ? 0 : terminalTabs.spacing)) }
    }
    readonly property real terminalTabMaximumWidth: Theme.terminalTabMaximumWidth
    readonly property real terminalTabMinimumWidth: Theme.terminalTabMinimumWidth
    readonly property int scrollButtonWidth: 24
    readonly property real availableTabWidth: Math.max(0,
        width - terminalTabAddButton.width - terminalTabs.spacing)
    // Decide overflow from minimum tab widths before reserving the bumpers,
    // so showing/hiding the buttons cannot cause a layout feedback loop.
    readonly property bool tabsOverflowing: !vertical && root.tabs.length > 0
        && root.stripMetrics.count * terminalTabMinimumWidth + root.stripMetrics.extraWidth
            + Math.max(0, root.stripMetrics.count - 1) * terminalTabs.spacing
            > availableTabWidth + 0.5
    readonly property real responsiveTerminalTabWidth: {
        var tabCount = Math.max(1, root.stripMetrics.count)
        var bumperWidth = root.tabsOverflowing ? 2 * root.scrollButtonWidth : 0
        var totalSpacing = terminalTabs.spacing * (tabCount - 1)
        var fittedWidth = (root.availableTabWidth - bumperWidth - totalSpacing
            - root.stripMetrics.extraWidth) / tabCount
        return Math.max(root.terminalTabMinimumWidth,
            Math.min(root.terminalTabMaximumWidth, fittedWidth))
    }
    property string renamingTabId: ""
    property string lastPressedTabId: ""
    property double lastTabPressTime: 0
    property var selectedTabIds: []
    property string selectionAnchor: ""
    property string dragTabId: ""
    property string dragGroupId: ""
    property var dropTarget: null
    property point dragPoint

    function groupColor(colorId) {
        var entry = root.groupColors.find(color => color.id === colorId) || root.groupColors[0]
        return root._visualPalette.darkMode ? entry.dark : entry.light
    }
    function groupHeaderWidth(group) {
        return group.title ? 96 : 28
    }
    function tabIsVisible(info) {
        if (!info)
            return false
        var group = root.groupsById[info.groupId]
        return !group || !group.collapsed
    }
    function selectTab(tabId, modifiers) {
        var tabs = root.tabs
        if (modifiers & Qt.ShiftModifier) {
            root.lastPressedTabId = ""
            var anchor = root.tabIndex(root.selectionAnchor || root.controller.activeTerminalTabId)
            var end = root.tabIndex(tabId)
            if (anchor < 0 || !root.tabIsVisible(tabs[anchor]))
                anchor = end
            root.selectedTabIds = tabs.slice(Math.min(anchor, end), Math.max(anchor, end) + 1)
                .filter(root.tabIsVisible).map(tab => tab.tabId)
            root.selectionAnchor = tabs[anchor].tabId
        } else if (modifiers & Qt.ControlModifier) {
            root.lastPressedTabId = ""
            var selected = root.selectedTabIds.slice()
            var active = root.controller.activeTerminalTabId
            if (selected.length === 0 && active && root.tabIsVisible(tabs[root.tabIndex(active)]))
                selected.push(active)
            var index = selected.indexOf(tabId)
            if (index < 0)
                selected.push(tabId)
            else
                selected.splice(index, 1)
            root.selectedTabIds = selected
            root.selectionAnchor = tabId
        } else {
            root.selectedTabIds = []
            root.selectionAnchor = tabId
        }
    }
    function startDrag(tabId, groupId, item, point) {
        root.dragTabId = tabId
        root.dragGroupId = groupId
        root.updateDrag(item, point)
    }
    function updateDrag(item, point) {
        root.dragPoint = item.mapToItem(terminalTabFlick, point.x, point.y)
        root.updateDropTarget()
    }
    function updateDropTarget() {
        root.dropTarget = null
        var point = root.dragPoint
        if (point.x < 0 || point.y < 0 || point.x > terminalTabFlick.width
                || point.y > terminalTabFlick.height)
            return
        point = terminalTabFlick.mapToItem(terminalTabs, point.x, point.y)
        for (var i = 0; i < tabRepeater.count; ++i) {
            var entry = tabRepeater.itemAt(i)
            if (!entry || !entry.visible)
                continue
            for (var item of [entry.headerItem, entry.tabItem]) {
                if (!item.visible)
                    continue
                var local = terminalTabs.mapToItem(item, point.x, point.y)
                var along = root.vertical ? local.y : local.x
                var across = root.vertical ? local.x : local.y
                var extent = root.vertical ? item.height : item.width
                var crossExtent = root.vertical ? item.width : item.height
                if (along < -2 || along > extent + 2 || across < 0 || across > crossExtent)
                    continue
                var position = along < extent * 0.25 ? -1 : along > extent * 0.75 ? 1 : 0
                if (root.dragGroupId && position === 0)
                    position = along < extent / 2 ? -1 : 1
                if (root.dragGroupId && entry.group) {
                    if (position < 0) {
                        while (!entry.firstInGroup)
                            entry = tabRepeater.itemAt(entry.index - 1)
                        item = entry.headerItem
                    } else if (entry.group.collapsed) {
                        item = entry.headerItem
                    } else {
                        while (!entry.lastInGroup)
                            entry = tabRepeater.itemAt(entry.index + 1)
                        item = entry.tabItem
                    }
                }
                root.dropTarget = { item: item, tabId: entry.tabInfo.tabId,
                    groupHeader: item === entry.headerItem, position: position }
                return
            }
        }
    }
    function finishDrag(commit) {
        var target = root.dropTarget
        var ids = root.selectedTabIds.includes(root.dragTabId)
            ? root.selectedTabIds : [root.dragTabId]
        var groupId = root.dragGroupId
        root.dropTarget = null
        root.dragTabId = ""
        root.dragGroupId = ""
        if (commit && target)
            root.controller.moveTerminalItems(ids, groupId, target.tabId,
                target.position, target.groupHeader)
    }
    function openGroupMenu(group, item, x, y) {
        groupMenu.groupId = group.groupId
        groupMenu.popup(item, x, y)
    }
    function editGroup(groupId) {
        var group = root.groupsById[groupId]
        if (!group)
            return
        groupEditor.groupId = groupId
        groupEditor.colorId = group.color
        groupName.text = group.title
        groupEditor.open()
    }
    function confirmCloseGroup(group) {
        groupConfirmation.groupId = group.groupId
        groupConfirmation.groupName = group.title || "未命名分组"
        groupConfirmation.open()
    }

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
        var tabs = root.tabs
        for (var index = 0; index < tabs.length; ++index) {
            if (tabs[index].tabId === tabId)
                return index
        }
        return -1
    }
    function ensureActiveTerminalTabVisible() {
        if (!root.visible || root.dragTabId || root.dragGroupId)
            return
        var index = root.tabIndex(root.controller.activeTerminalTabId)
        var entry = tabRepeater.itemAt(index)
        if (!entry)
            return
        var item = entry.tabItem
        if (!item.visible) {
            while (index > 0
                    && root.tabs[index - 1].groupId === entry.tabInfo.groupId)
                --index
            item = tabRepeater.itemAt(index).headerItem
        }
        var position = item.mapToItem(terminalTabFlick.contentItem, 0, 0)
        if (root.vertical) {
            var bottom = position.y + item.height
            var maximumY = Math.max(0, terminalTabFlick.contentHeight - terminalTabFlick.height)
            var y = Math.min(maximumY, terminalTabFlick.contentY)
            if (position.y < y)
                y = position.y
            else if (bottom > y + terminalTabFlick.height)
                y = bottom - terminalTabFlick.height
            terminalTabFlick.contentY = Math.max(0, Math.min(maximumY, y))
            return
        }
        var maximumContentX = Math.max(0,
            terminalTabFlick.contentWidth - terminalTabFlick.width)
        if (maximumContentX <= 0) {
            terminalTabFlick.contentX = 0
            return
        }
        terminalTabFlick.contentX = Math.max(0,
            Math.min(maximumContentX, terminalTabFlick.contentX))
        var tabLeft = position.x
        var tabRight = tabLeft + item.width
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

    Shortcut { sequence: "Ctrl+Shift+T"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled && root.controller.canCreateTerminalTab; onActivated: root.createTab() }
    Shortcut { sequence: "Ctrl+Shift+W"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled; onActivated: root.closeTab(root.controller.activeTerminalTabId) }
    Shortcut { sequence: "Ctrl+Tab"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled; onActivated: { root.controller.activateRelativeTerminalTab(1); root.terminalFocusRequested() } }
    Shortcut { sequence: "Ctrl+Shift+Tab"; context: Qt.WindowShortcut; enabled: root.shortcutsEnabled; onActivated: { root.controller.activateRelativeTerminalTab(-1); root.terminalFocusRequested() } }

    onWidthChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
    onHeightChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
    onVisibleChanged: if (!visible) {
        root.renamingTabId = ""
        root.selectedTabIds = []
        root.finishDrag(false)
    }
    Connections {
        target: root.controller
        function onTerminalGroupCreatedByDrop(groupId) {
            if (root.visible && root.enabled)
                root.editGroup(groupId)
        }
        function onTerminalTabsChanged() {
            root.selectedTabIds = root.selectedTabIds.filter(id => {
                var index = root.tabIndex(id)
                return index >= 0 && root.tabIsVisible(root.tabs[index])
            })
            Qt.callLater(root.ensureActiveTerminalTabVisible)
        }
    }

    component StripDragHandler: DragHandler {
        id: handler
        required property Item sourceItem
        required property string tabId
        property string groupId: ""
        target: null
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
        acceptedButtons: Qt.LeftButton
        acceptedModifiers: Qt.NoModifier
        grabPermissions: PointerHandler.CanTakeOverFromItems
        onGrabChanged: function(transition, point) {
            if (transition === PointerDevice.GrabExclusive)
                root.startDrag(tabId, groupId, sourceItem, centroid.position)
            else if (transition === PointerDevice.UngrabExclusive)
                root.finishDrag(true)
            else if (transition === PointerDevice.CancelGrabExclusive)
                root.finishDrag(false)
        }
        onActiveTranslationChanged: if (active)
            root.updateDrag(sourceItem, centroid.position)
    }

    component DropMark: Rectangle {
        id: mark
        required property Item item
        readonly property bool matches: root.dropTarget?.item === item
        readonly property int position: matches ? root.dropTarget.position : 0
        visible: matches
        z: 5
        x: root.vertical || position <= 0 ? 0 : item.width - 3
        y: !root.vertical || position <= 0 ? 0 : item.height - 3
        width: root.vertical || position === 0 ? item.width : 3
        height: !root.vertical || position === 0 ? item.height : 3
        radius: Theme.radiusTiny
        color: position === 0 ? "transparent" : _visualPalette.primary
        border.color: _visualPalette.primary
        border.width: position === 0 ? 2 : 0
    }

    Timer {
        interval: 40
        repeat: true
        running: root.dragTabId !== "" || root.dragGroupId !== ""
        onTriggered: {
            var point = root.dragPoint
            var position = root.vertical ? point.y : point.x
            var extent = root.vertical ? terminalTabFlick.height : terminalTabFlick.width
            if (position < 0 || position > extent)
                return
            var delta = position < 18 ? -12 : position > extent - 18 ? 12 : 0
            if (!delta)
                return
            if (root.vertical)
                terminalTabFlick.contentY = Math.max(0,
                    Math.min(terminalTabFlick.contentHeight - extent, terminalTabFlick.contentY + delta))
            else
                root.scrollTerminalTabs(delta)
            root.updateDropTarget()
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
            color: _visualPalette.chromeForeground
        }
        background: Rectangle {
            radius: Theme.radiusTiny
            color: scrollButton.hovered || scrollButton.down
                ? _visualPalette.navigationHover : "transparent"
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
        x: root.vertical ? 6 : root.tabsOverflowing ? scrollBackwardButton.width : 0
        anchors.top: parent.top
        anchors.topMargin: root.vertical ? 44 : 0
        anchors.bottom: parent.bottom
        anchors.bottomMargin: root.vertical ? 6 : 0
        width: root.vertical ? Math.max(0, root.width - 12) : Math.max(0, (root.tabsOverflowing ? scrollForwardButton.x
            : terminalTabAddButton.x - terminalTabs.spacing) - x)
        contentWidth: root.vertical ? width : terminalTabs.implicitWidth
        contentHeight: root.vertical ? terminalTabs.implicitHeight : height
        clip: true
        interactive: root.vertical ? contentHeight > height : contentWidth > width
        acceptedButtons: Qt.NoButton
        flickableDirection: root.vertical ? Flickable.VerticalFlick : Flickable.HorizontalFlick
        boundsBehavior: Flickable.StopAtBounds
        onWidthChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
        onContentWidthChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
        onContentHeightChanged: Qt.callLater(root.ensureActiveTerminalTabVisible)
        ScrollBar.vertical: ScrollBar { policy: root.vertical ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff }
        Grid {
            id: terminalTabs
            columns: root.vertical ? 1 : Math.max(1, root.tabs.length)
            anchors.bottom: root.vertical ? undefined : parent.bottom
            anchors.top: root.vertical ? parent.top : undefined
            spacing: Theme.space4
            Repeater {
                id: tabRepeater
                model: root.tabs.length
                delegate: Item {
                    id: entry
                    required property int index
                    readonly property var tabInfo: root.tabs[index] || ({})
                    readonly property var group: root.groupsById[tabInfo.groupId]
                    readonly property bool firstInGroup: !!group && (index === 0
                        || root.tabs[index - 1]?.groupId !== tabInfo.groupId)
                    readonly property bool lastInGroup: !!group
                        && root.tabs[index + 1]?.groupId !== tabInfo.groupId
                    readonly property bool showTab: !group || !group.collapsed
                    readonly property int verticalGroupInset: root.vertical && group ? Theme.space8 : 0
                    readonly property color accent: root.groupColor(group?.color)
                    readonly property alias headerItem: groupHeader
                    readonly property alias tabItem: tab
                    visible: showTab || firstInGroup
                    width: root.vertical ? terminalTabFlick.width
                        : (firstInGroup ? groupHeader.width : 0) + (showTab ? tab.width : 0)
                            + (firstInGroup && showTab ? terminalTabs.spacing : 0)
                    height: root.vertical && firstInGroup && showTab
                        ? groupHeader.height + terminalTabs.spacing + tab.height
                        : root.vertical ? 32 : root.height

                    Control {
                        id: groupHeader
                        objectName: entry.firstInGroup ? "terminalGroup_" + entry.group.groupId : ""
                        visible: entry.firstInGroup
                        width: root.vertical ? entry.width : entry.group ? root.groupHeaderWidth(entry.group) : 0
                        height: root.vertical ? 32 : root.height
                        padding: 0
                        hoverEnabled: true
                        activeFocusOnTab: true
                        readonly property bool collapsedActive: !!entry.group?.collapsed && !!entry.group?.active
                        readonly property string text: entry.group?.title || "未命名分组"
                        Accessible.role: Accessible.Button
                        Accessible.name: text + (collapsedActive ? "，当前终端所在分组" : "")
                        Accessible.description: entry.group?.collapsed ? "已折叠" : "已展开"
                        Accessible.onPressAction: toggleGroup()
                        function toggleGroup() {
                            root.controller.toggleTerminalGroup(entry.group.groupId)
                        }
                        Keys.onReturnPressed: toggleGroup()
                        Keys.onSpacePressed: toggleGroup()
                        Keys.onPressed: function(event) {
                            if (event.key === Qt.Key_Menu) {
                                root.openGroupMenu(entry.group, groupHeader, 0, height)
                                event.accepted = true
                            }
                        }
                        background: Rectangle {
                            anchors.fill: parent
                            radius: Theme.radiusSmall
                            color: Qt.alpha(entry.accent, groupHeader.hovered || groupHeader.collapsedActive ? 0.24 : 0.12)
                            border.width: groupHeader.activeFocus || groupHeader.collapsedActive ? 1 : 0
                            border.color: entry.accent
                        }
                        contentItem: RowLayout {
                            spacing: 6
                            Rectangle {
                                Layout.leftMargin: groupHeader.width <= 28 ? 10 : 8
                                Layout.preferredWidth: 8
                                Layout.preferredHeight: 8
                                radius: 4
                                color: entry.accent
                            }
                            Text {
                                Layout.fillWidth: true
                                Layout.rightMargin: 6
                                visible: root.vertical || !!entry.group?.title
                                text: groupHeader.text
                                color: root.vertical ? _visualPalette.terminalForeground : _visualPalette.chromeForeground
                                font.pixelSize: Theme.fontSupporting
                                elide: Text.ElideRight
                            }
                            MaterialIcon {
                                Layout.rightMargin: 8
                                visible: root.vertical
                                icon: entry.group?.collapsed ? "chevron_right" : "expand_more"
                                iconSize: 14
                                color: entry.accent
                            }
                        }
                        TapHandler {
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onTapped: function(eventPoint, button) {
                                if (button === Qt.RightButton) {
                                    root.openGroupMenu(entry.group, groupHeader,
                                        eventPoint.position.x, eventPoint.position.y)
                                } else {
                                    groupHeader.forceActiveFocus(Qt.MouseFocusReason)
                                    groupHeader.toggleGroup()
                                }
                            }
                        }
                        StripDragHandler {
                            sourceItem: groupHeader
                            tabId: entry.tabInfo.tabId
                            groupId: entry.tabInfo.groupId || ""
                        }
                        DropMark { item: groupHeader }
                    }

                    Rectangle {
                        objectName: "terminalGroupIndicator_" + entry.tabInfo.tabId
                        z: 2
                        visible: !!entry.group && entry.showTab
                        x: root.vertical ? 1 : tab.x
                        y: root.vertical ? tab.y : tab.y + tab.height - height
                        width: root.vertical ? 3 : tab.width + (entry.lastInGroup ? 0 : terminalTabs.spacing)
                        height: root.vertical ? tab.height + (entry.lastInGroup ? 0 : terminalTabs.spacing) : 2
                        radius: 1
                        color: entry.accent
                    }

                    Rectangle {
                        id: tab
                        readonly property var tabInfo: entry.tabInfo
                        readonly property bool selected: tabInfo.active === true
                        readonly property bool multiSelected: root.selectedTabIds.includes(tabInfo.tabId)
                        visible: entry.showTab
                        x: root.vertical ? entry.verticalGroupInset
                            : entry.firstInGroup ? groupHeader.width + terminalTabs.spacing : 0
                        y: root.vertical && entry.firstInGroup ? groupHeader.height + terminalTabs.spacing : 0
                        width: root.vertical ? Math.max(0, entry.width - x) : root.responsiveTerminalTabWidth
                        height: root.vertical ? 32 : root.height
                        radius: Theme.radiusSmall
                        color: _visualPalette.glassMode ? "transparent" : tab.selected || tab.multiSelected ? root.selectedBackground
                            : tabHover.hovered ? root.hoverBackground : "transparent"
                        GlassListHighlight {
                            objectName: "terminalTabGlass_" + tab.tabInfo.tabId
                            anchors.fill: parent; cornerRadius: parent.radius
                            selected: tab.selected || tab.multiSelected
                            hovered: tabHover.hovered
                            hoverColor: _visualPalette.terminalForeground
                            outlineVisible: root.vertical && selected
                            tintColor: root.vertical
                                ? (tab.selected ? _visualPalette.primary : _visualPalette.terminalForeground)
                                : (tab.selected ? root.selectedBackground : root.hoverBackground)
                            tintStrength: root.vertical ? (tab.selected ? 0.18 : 0.04) : 0.86
                            minimumTintOpacity: root.vertical ? 0.04 : 0.65
                            pointerReactive: root.vertical
                        }
                        border.width: !_visualPalette.glassMode && tab.selected && (root.vertical || _visualPalette.darkMode) ? 1 : 0
                        border.color: root.vertical
                            ? (_visualPalette.glassMode ? Qt.rgba(_visualPalette.primary.r, _visualPalette.primary.g, _visualPalette.primary.b, 0.42)
                                : _visualPalette.navigationActiveBorder) : _visualPalette.terminalTabBorder
                        objectName: "terminalTab_" + tabInfo.tabId
                        Accessible.role: Accessible.PageTab
                        Accessible.name: tabInfo.title || "终端"
                        Accessible.onPressAction: root.activateTab(tabInfo.tabId)
                        HoverHandler { id: tabHover }
                        HoverTips {
                            visible: tabTitle.truncated && tabHover.hovered && root.renamingTabId.length === 0
                            text: tab.tabInfo.title || "终端"
                        }
                        Rectangle {
                            objectName: "terminalTabSelection_" + tab.tabInfo.tabId
                            z: 2
                            visible: root.vertical && tab.selected
                            x: 0; y: 6; width: 3; height: parent.height - 12
                            radius: 1.5; color: _visualPalette.navigationActiveBorder
                        }
                        RowLayout {
                            z: 1
                            anchors.fill: parent; anchors.leftMargin: 12; anchors.rightMargin: Theme.space8; spacing: 8
                            MaterialIcon {
                                icon: "terminal"
                                iconSize: 16
                                color: tab.selected ? _visualPalette.terminalForeground
                                    : root.vertical ? _visualPalette.terminalMuted : _visualPalette.chromeForeground
                            }
                            Text {
                                id: tabTitle
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                visible: root.renamingTabId !== tab.tabInfo.tabId
                                text: tab.tabInfo.title || "终端"
                                color: tab.selected
                                    ? _visualPalette.terminalForeground
                                    : root.vertical ? _visualPalette.terminalMuted : _visualPalette.chromeForeground
                                font.pixelSize: Theme.fontSupporting
                                elide: Text.ElideRight
                            }
                            AppTextField {
                                id: renameField
                                objectName: "terminalTabRename_" + tab.tabInfo.tabId
                                Layout.fillWidth: true
                                Layout.minimumWidth: 0
                                Layout.preferredHeight: 28
                                visible: root.renamingTabId === tab.tabInfo.tabId
                                color: _visualPalette.terminalForeground
                                font.pixelSize: Theme.fontSupporting
                                leftPadding: 6; rightPadding: 6; topPadding: 0; bottomPadding: 0
                                selectByMouse: true
                                background: Rectangle {
                                    radius: Theme.radiusTiny
                                    color: _visualPalette.terminalBackground
                                    border.color: _visualPalette.primary
                                    border.width: 1
                                }
                                onVisibleChanged: if (visible) {
                                    text = tab.tabInfo.title
                                    forceActiveFocus()
                                    selectAll()
                                }
                                onEditingFinished: root.finishRename(tab.tabInfo.tabId, text)
                                Keys.onReturnPressed: function(event) {
                                    root.finishRename(tab.tabInfo.tabId, text)
                                    event.accepted = true
                                }
                                Keys.onEscapePressed: function(event) {
                                    root.cancelRename(tab.tabInfo.tabId)
                                    event.accepted = true
                                }
                            }
                            PrimaryButton {
                                objectName: "terminalTabClose_" + tab.tabInfo.tabId
                                visible: true
                                opacity: tab.selected || tabHover.hovered ? 1 : 0
                                enabled: opacity > 0
                                Layout.preferredWidth: 20
                                Layout.preferredHeight: 20
                                compact: true
                                text: "关闭终端标签"
                                iconName: "close"
                                glyphSize: 15
                                tonal: true
                                foregroundColor: tab.selected
                                    ? (_visualPalette.darkMode ? _visualPalette.terminalTabAction : _visualPalette.terminalMuted)
                                    : root.vertical ? _visualPalette.terminalMuted : _visualPalette.chromeForeground
                                color: hovered
                                    ? root.hoverBackground
                                    : "transparent"
                                border.width: 0
                                radius: Theme.radiusTiny
                                onClicked: root.closeTab(tab.tabInfo.tabId)
                            }
                        }
                        MouseArea {
                            id: tabHoverArea
                            anchors.fill: parent
                            z: 0
                            hoverEnabled: true
                            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
                            cursorShape: Qt.PointingHandCursor
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.LeftButton) {
                                    root.selectTab(tab.tabInfo.tabId, mouse.modifiers)
                                    if (!(mouse.modifiers & (Qt.ControlModifier | Qt.ShiftModifier)))
                                        root.handleTabPress(tab.tabInfo.tabId)
                                } else if (mouse.button === Qt.MiddleButton) {
                                    root.closeTab(tab.tabInfo.tabId)
                                } else if (mouse.button === Qt.RightButton) {
                                    if (!tab.multiSelected) {
                                        root.selectedTabIds = []
                                        root.activateTab(tab.tabInfo.tabId)
                                    }
                                    terminalTabContextMenu.tabId = tab.tabInfo.tabId
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
                            color: _visualPalette.terminalTabDivider
                            opacity: 1
                            visible: !root.vertical && !tab.selected && !entry.group
                                && entry.index < root.tabs.length - 1
                                && !root.tabs[entry.index + 1].active
                        }
                        StripDragHandler { sourceItem: tab; tabId: tab.tabInfo.tabId || "" }
                        DropMark { item: tab }
                    }
                }
            }
        }
    }

    PrimaryButton {
        id: terminalTabAddButton
        objectName: "terminalTabAddButton"
        z: 4
        x: root.vertical ? 6 : root.tabs.length === 0 ? 0
            : Math.max(0, Math.min(terminalTabs.implicitWidth + terminalTabs.spacing,
                parent.width - width))
        anchors.verticalCenter: root.vertical ? undefined : parent.verticalCenter
        anchors.top: root.vertical ? parent.top : undefined
        anchors.topMargin: root.vertical ? 6 : 0
        width: root.vertical ? Math.max(0, root.width - 12) : 32
        height: 32
        radius: Theme.radiusTiny
        compact: !root.vertical
        text: root.vertical ? "新建终端" : "新增终端标签 (Ctrl+T)"
        iconName: "add"
        glyphSize: 20
        tonal: true
        foregroundColor: root.vertical ? _visualPalette.terminalForeground : _visualPalette.chromeForeground
        border.width: 0
        color: hovered || pressed ? (root.vertical ? root.hoverBackground : _visualPalette.navigationHover) : "transparent"
        enabled: root.controller.canCreateTerminalTab
        disabledOpacity: 1
        onClicked: root.createTab()
    }

    MouseArea {
        z: 3
        anchors.fill: parent
        acceptedButtons: Qt.NoButton
        onWheel: function(wheel) {
            if (root.vertical) { wheel.accepted = false; return }
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
        objectName: "terminalTabContextMenu"
        property string tabId: ""
        readonly property var tabIds: root.selectedTabIds.includes(tabId) ? root.selectedTabIds : [tabId]
        readonly property bool containsGrouped: tabIds.some(id =>
            !!root.tabs[root.tabIndex(id)]?.groupId)
        AppMenuItem { text: "重命名"; onTriggered: root.beginRename(terminalTabContextMenu.tabId) }
        AppMenuItem {
            text: "恢复自动标题"
            enabled: {
                var index = root.tabIndex(terminalTabContextMenu.tabId)
                return index >= 0 && root.tabs[index].hasCustomTitle
            }
            onTriggered: root.controller.resetTerminalTabTitle(terminalTabContextMenu.tabId)
        }
        AppMenuSeparator {}
        AppMenu {
            title: terminalTabContextMenu.tabIds.length > 1 ? "将所选标签加入分组" : "将标签加入分组"
            AppMenuItem {
                text: "新建分组"
                objectName: "createTerminalGroup"
                onTriggered: root.editGroup(root.controller.createTerminalGroup(terminalTabContextMenu.tabIds))
            }
            Instantiator {
                model: root.groups
                delegate: AppMenuItem {
                    required property var modelData
                    text: modelData.title || "未命名分组 · "
                        + (root.groupColors.find(color => color.id === modelData.color)?.name || "")
                    enabled: terminalTabContextMenu.tabIds.some(id =>
                        root.tabs[root.tabIndex(id)]?.groupId !== modelData.groupId)
                    onTriggered: root.controller.addTabsToTerminalGroup(
                        terminalTabContextMenu.tabIds, modelData.groupId)
                }
                onObjectAdded: (index, item) => parentMenu.insertItem(index + 1, item)
                onObjectRemoved: (index, item) => parentMenu.removeItem(item)
                property Menu parentMenu: groupPicker
            }
            id: groupPicker
        }
        AppMenuItem {
            text: "移出分组"
            enabled: terminalTabContextMenu.containsGrouped
            onTriggered: root.controller.removeTabsFromTerminalGroups(terminalTabContextMenu.tabIds)
        }
        AppMenuSeparator {}
        AppMenuItem { text: "关闭"; onTriggered: root.closeTab(terminalTabContextMenu.tabId) }
        AppMenuItem {
            text: "关闭其他标签"
            enabled: root.tabs.length > 1
            onTriggered: root.controller.closeOtherTerminalTabs(terminalTabContextMenu.tabId)
        }
        AppMenuItem {
            text: root.vertical ? "关闭下方标签" : "关闭右侧标签"
            enabled: {
                var index = root.tabIndex(terminalTabContextMenu.tabId)
                return index >= 0 && index < root.tabs.length - 1
            }
            onTriggered: root.controller.closeTerminalTabsToRight(terminalTabContextMenu.tabId)
        }
        AppMenuSeparator {}
        AppMenuItem {
            objectName: "toggleTerminalTabLayout"
            text: root.controller.terminalTabLayout === "vertical" ? "使用水平标签栏" : "使用垂直标签栏"
            onTriggered: {
                root.controller.setTerminalTabLayout(
                    root.controller.terminalTabLayout === "vertical" ? "horizontal" : "vertical")
                root.terminalFocusRequested()
            }
        }
    }

    AppMenu {
        id: groupMenu
        objectName: "terminalGroupContextMenu"
        property string groupId: ""
        readonly property var group: root.groupsById[groupId]
        AppMenuItem { text: "编辑组名和颜色"; onTriggered: root.editGroup(groupMenu.groupId) }
        AppMenuItem {
            text: "在组内新建终端"
            onTriggered: {
                root.controller.createTerminalTabInGroup(groupMenu.groupId)
                root.terminalFocusRequested()
            }
        }
        AppMenuItem {
            text: groupMenu.group?.collapsed ? "展开分组" : "折叠分组"
            onTriggered: root.controller.toggleTerminalGroup(groupMenu.groupId)
        }
        AppMenuSeparator {}
        AppMenuItem {
            text: "解散分组"
            onTriggered: root.controller.ungroupTerminalGroup(groupMenu.groupId)
        }
        AppMenuItem {
            text: "关闭整组…"
            objectName: "confirmCloseTerminalGroup"
            destructive: true
            onTriggered: root.confirmCloseGroup(groupMenu.group)
        }
    }

    AppDialog {
        id: groupEditor
        objectName: "terminalGroupEditor"
        property string groupId: ""
        property string colorId: ""
        compactLayout: true
        width: Math.min(380, (root.Window.window?.width || 400) - 24)
        onOpened: {
            groupName.forceActiveFocus()
            groupName.selectAll()
        }
        function save() {
            root.controller.editTerminalGroup(groupId, groupName.text, colorId)
            close()
        }
        contentItem: ColumnLayout {
            spacing: Theme.space12
            DialogHeading { Layout.fillWidth: true; title: "编辑终端分组"; iconName: "terminal" }
            AppTextField {
                id: groupName
                objectName: "terminalGroupName"
                Layout.fillWidth: true
                placeholderText: "分组名称（可选）"
                Accessible.name: "分组名称"
                maximumLength: 60
                onAccepted: groupEditor.save()
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 3
                Repeater {
                    model: root.groupColors
                    delegate: Button {
                        id: swatch
                        required property var modelData
                        readonly property color accent: root.groupColor(modelData.id)
                        readonly property bool selected: groupEditor.colorId === modelData.id
                        Layout.fillWidth: true
                        Layout.preferredHeight: 32
                        text: modelData.name
                        Accessible.name: text
                        Accessible.checkable: true
                        Accessible.checked: selected
                        onClicked: groupEditor.colorId = modelData.id
                        background: Rectangle {
                            radius: Theme.radiusSmall
                            color: swatch.hovered ? Qt.alpha(swatch.accent, 0.15) : "transparent"
                            border.width: swatch.selected || swatch.activeFocus ? 1 : 0
                            border.color: swatch.accent
                        }
                        contentItem: Item {
                            Rectangle {
                                anchors.centerIn: parent
                                width: 16; height: 16; radius: 8
                                color: swatch.accent
                            }
                        }
                        HoverTips { visible: swatch.hovered; text: swatch.text }
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                DialogActionButton { text: "取消"; onClicked: groupEditor.close() }
                DialogActionButton { text: "保存"; onClicked: groupEditor.save() }
            }
        }
    }

    AppDialog {
        id: groupConfirmation
        objectName: "terminalGroupConfirmation"
        property string groupId: ""
        property string groupName: ""
        compactLayout: true
        width: Math.min(Theme.compactDialogWidth, (root.Window.window?.width || 400) - 24)
        contentItem: ColumnLayout {
            spacing: Theme.space12
            DialogHeading {
                Layout.fillWidth: true
                title: "关闭终端分组？"
                iconName: "close"
                destructive: true
                description: "关闭“" + groupConfirmation.groupName
                    + "”将停止组内 Shell 和正在运行的命令。"
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                DialogActionButton { text: "取消"; onClicked: groupConfirmation.close() }
                DialogActionButton {
                    text: "关闭整组"
                    objectName: "executeTerminalGroupAction"
                    destructive: true
                    onClicked: {
                        root.controller.closeTerminalGroup(groupConfirmation.groupId)
                        groupConfirmation.close()
                    }
                }
            }
        }
    }
}
