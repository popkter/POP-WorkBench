pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import PopTools.Terminal 1.0
import "../theme"

Item {
    id: root
    required property var controller
    required property var parentWindow
    signal createScriptRequested(string command, string kind)
    property bool tabsInTitleBar: false

    function focusTerminal() { terminalView.forceActiveFocus() }

    function copySelectionOrInterrupt() {
        if (terminalView.hasSelection) terminalView.copySelection()
        else root.controller.interrupt()
        terminalView.forceActiveFocus()
    }
    function pasteClipboard() { terminalView.pasteClipboard(); terminalView.forceActiveFocus() }
    function clearTerminal() { root.controller.clear(); terminalView.forceActiveFocus() }
    function syncTerminalSyntaxColors() {
        root.controller.configureTerminalSyntaxColors({
            "default": "#E5E7EB",
            "command": "#8CC8FF",
            "warning": "#FFD166",
            "string": "#9BE3B1",
            "semantic": "#D7B5FF",
            "operator": "#80DED9",
            "error": "#FF9B93",
            "muted": "#AAB4C3"
        })
    }
    function setHistoryListViewEnabled(value) {
        root.controller.setPowerShellHistoryListViewEnabled(value)
        terminalView.forceActiveFocus()
    }

    Shortcut { sequence: "Ctrl+C"; context: Qt.WindowShortcut; enabled: root.visible; onActivated: root.copySelectionOrInterrupt() }
    Shortcut { sequence: "Ctrl+Shift+C"; context: Qt.WindowShortcut; enabled: root.visible && terminalView.hasSelection; onActivated: terminalView.copySelection() }
    Shortcut { sequence: "Ctrl+V"; context: Qt.WindowShortcut; enabled: root.visible; onActivated: root.pasteClipboard() }
    Shortcut { sequence: "Ctrl+Shift+V"; context: Qt.WindowShortcut; enabled: root.visible; onActivated: root.pasteClipboard() }
    Shortcut { sequence: "Ctrl+L"; context: Qt.WindowShortcut; enabled: root.visible; onActivated: root.clearTerminal() }

    Component.onDestruction: root.controller.terminalDetached()
    onVisibleChanged: if (visible) {
        root.syncTerminalSyntaxColors()
        root.controller.ensureStarted()
        terminalView.forceActiveFocus()
    }

    Timer {
        id: terminalSyntaxColorSync
        interval: 0
        onTriggered: root.syncTerminalSyntaxColors()
    }

    Connections {
        target: Theme
        function onConsoleTextChanged() { terminalSyntaxColorSync.restart() }
        function onConsoleTagChanged() { terminalSyntaxColorSync.restart() }
        function onConsoleWarningChanged() { terminalSyntaxColorSync.restart() }
        function onConsoleErrorChanged() { terminalSyntaxColorSync.restart() }
        function onConsoleMutedChanged() { terminalSyntaxColorSync.restart() }
        function onSuccessChanged() { terminalSyntaxColorSync.restart() }
        function onTertiaryTextChanged() { terminalSyntaxColorSync.restart() }
        function onTealChanged() { terminalSyntaxColorSync.restart() }
    }

    Connections {
        target: root.controller
        function onTerminalData(tabId, data) { terminalView.feed(tabId, data) }
        function onTerminalSnapshotData(tabId, data) { terminalView.feed(tabId, data) }
        function onTerminalResetRequested(tabId) { terminalView.resetSession(tabId) }
        function onTerminalSessionRemoved(tabId) { terminalView.removeSession(tabId) }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusSmall
            color: Theme.terminalBackground
            clip: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 0

                TerminalTabBar {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Theme.terminalToolbarHeight
                    visible: !root.tabsInTitleBar
                    controller: root.controller
                    onTerminalFocusRequested: root.focusTerminal()
                }

                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true

                    TerminalView {
                        id: terminalView
                        visible: root.controller.terminalTabs.length > 0
                        anchors.fill: parent
                        anchors.leftMargin: Theme.space8
                        anchors.rightMargin: Theme.space8
                        anchors.topMargin: Theme.space8
                        anchors.bottomMargin: 10
                        sessionId: root.controller.activeTerminalTabId
                        fillColor: Theme.terminalBackground
                        fontSize: Theme.fontBody
                        focus: true
                        Accessible.role: Accessible.EditableText
                        Accessible.name: "开发者终端"
                        Component.onCompleted: {
                            root.syncTerminalSyntaxColors()
                            root.controller.terminalReady()
                            forceActiveFocus()
                        }
                        onInputGenerated: function(tabId, data) { root.controller.writeInputToTab(tabId, data) }
                        onTerminalSizeChanged: function(columns, rows) { root.controller.resizeTerminal(columns, rows) }
                        onTerminalTitleChanged: function(tabId, title) { root.controller.updateTerminalTitle(tabId, title) }
                        onContextMenuRequested: function(x, y) { terminalContextMenu.popup(x, y) }
                    }

                    ColumnLayout {
                        anchors.centerIn: parent
                        width: Math.min(360, parent.width - Theme.space32)
                        visible: root.controller.terminalTabs.length === 0
                        spacing: Theme.space16
                        MaterialIcon {
                            Layout.alignment: Qt.AlignHCenter
                            icon: "terminal"; iconSize: 40; color: Theme.consoleMuted
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "没有打开的终端"
                            color: Theme.consoleText; font.pixelSize: Theme.fontSectionTitle
                            horizontalAlignment: Text.AlignHCenter
                        }
                        Text {
                            Layout.fillWidth: true
                            text: "可以前往设置管理插件，或新建终端继续使用。"
                            color: Theme.consoleMuted; font.pixelSize: Theme.fontBody
                            horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap
                        }
                        PrimaryButton {
                            Layout.alignment: Qt.AlignHCenter
                            text: "新建终端"; iconName: "add"
                            onClicked: root.controller.createTerminalTab()
                        }
                    }

                    DropArea {
                        id: terminalPathDropArea
                        enabled: root.controller.terminalTabs.length > 0
                        anchors.fill: terminalView
                        z: 2
                        onEntered: function(drag) {
                            drag.accepted = drag.hasUrls
                                && root.controller.formatDroppedPaths(drag.urls).length > 0
                        }
                        onDropped: function(drop) {
                            if (!drop.hasUrls)
                                return
                            var text = root.controller.formatDroppedPaths(drop.urls)
                            if (!text.length)
                                return
                            terminalView.pasteText(text)
                            drop.accepted = true
                            terminalView.forceActiveFocus()
                        }

                        Rectangle {
                            anchors.fill: parent
                            visible: terminalPathDropArea.containsDrag
                            radius: Theme.radiusSmall
                            color: Theme.terminalDropHighlight
                            border.color: Theme.primary
                            border.width: 2

                            Text {
                                anchors.centerIn: parent
                                text: "释放以插入路径"
                                color: Theme.consoleText
                                font.pixelSize: Theme.fontButton
                                font.weight: Font.DemiBold
                            }
                        }
                    }

                    ScrollBar {
                        anchors.top: terminalView.top; anchors.right: terminalView.right; anchors.bottom: terminalView.bottom
                        orientation: Qt.Vertical
                        policy: terminalView.scrollbackLineCount > 0 ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
                        size: terminalView.rows / Math.max(terminalView.rows, terminalView.rows + terminalView.scrollbackLineCount)
                        position: terminalView.scrollbackLineCount > 0 ? (terminalView.scrollbackLineCount - terminalView.scrollOffset) / (terminalView.rows + terminalView.scrollbackLineCount) : 0
                    }

                    AppMenu {
                        id: terminalContextMenu
                        objectName: "terminalContextMenu"
                        AppMenuItem { text: "复制"; enabled: terminalView.hasSelection; onTriggered: terminalView.copySelection() }
                        AppMenuItem {
                            objectName: "addSelectionToCustomScript"
                            text: "添加到自定义脚本"
                            enabled: terminalView.hasSelection
                            onTriggered: {
                                var command = terminalView.selectionText()
                                if (command.trim().length > 0)
                                    root.createScriptRequested(command,
                                        Qt.platform.os === "windows" ? "powershell" : "bash")
                            }
                        }
                        AppMenuItem { text: "粘贴"; onTriggered: root.pasteClipboard() }
                        AppMenuItem { text: "全选"; onTriggered: terminalView.selectAll() }
                        AppMenuItem { text: "清屏"; onTriggered: root.clearTerminal() }
                        AppMenuItem { text: "重启终端"; onTriggered: root.controller.restart() }
                        AppMenuItem {
                            visible: root.controller.terminalName === "PowerShell 7"
                            text: root.controller.powerShellHistoryListViewEnabled
                                ? "关闭历史预测列表" : "显示历史预测列表"
                            onTriggered: root.setHistoryListViewEnabled(
                                !root.controller.powerShellHistoryListViewEnabled)
                        }
                        AppMenuItem { text: "停止当前命令"; destructive: true; enabled: root.controller.running; onTriggered: root.controller.interrupt() }
                        AppMenuItem {
                            text: "停止所有终端会话"
                            destructive: true
                            enabled: root.controller.terminalTabs.some(function(tab) { return tab.running })
                            onTriggered: root.controller.stop()
                        }
                    }
                }
            }
        }
    }

}
