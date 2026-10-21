import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

Item {
    id: root
    required property var hostWindow
    property var androidBackend: null
    property var selectedScript: ({})
    readonly property bool scriptDeviceVisible: scriptActionsVisible && androidBackend !== null
    readonly property bool compactScriptActions: scriptDeviceVisible && hostWindow.width < 1100
    property var terminalController: null
    property bool terminalTabsVisible: false
    property bool terminalTabsEnabled: true
    signal terminalFocusRequested()
    property bool scriptActionsVisible: false
    property bool scriptActionsEnabled: true
    property bool scriptSelected: false
    property bool scriptEditable: false
    property bool scriptRunning: false
    signal importRequested()
    signal createRequested()
    signal shareRequested()
    signal editRequested()
    signal deleteRequested()
    signal runRequested()
    readonly property bool dark: Theme.darkMode
    readonly property bool active: hostWindow.active
    readonly property real contentLeftInset: hostWindow.titleBarHeight + Theme.workspaceInset
    // JetBrains Runtime uses three 47-DIP controls, with 10-DIP glyphs.
    readonly property int controlWidth: hostWindow.captionControlWidth
    readonly property bool modern: hostWindow.modernCaptionControls

    Binding {
        target: root.hostWindow
        property: "titleBarActionsRect"
        value: root.terminalTabsVisible && terminalTabsLoader.item
            ? Qt.rect(terminalTabsLoader.x, terminalTabsLoader.y,
                terminalTabsLoader.item.interactiveWidth, terminalTabsLoader.height)
            : root.scriptActionsVisible
            ? Qt.rect(scriptActions.x, scriptActions.y, scriptActions.width, scriptActions.height)
            : Qt.rect(0, 0, 0, 0)
    }

    component ChromeAction: PrimaryButton {
        implicitHeight: Theme.captionActionHeight
        compact: false
        showHoverTips: false
        color: hovered || pressed ? Theme.navigationHover : "transparent"
        foregroundColor: Theme.chromeForeground
        border.width: 0
        radius: Theme.radiusTiny
        labelFontSize: Theme.fontSupporting
        labelFontWeight: Font.Normal
        glyphSize: 20
        contentSpacing: 6
        disabledOpacity: 0.4
        Accessible.role: Accessible.Button
        Accessible.name: text
        Accessible.onPressAction: if (enabled) clicked()
    }

    Image {
        anchors.left: parent.left
        anchors.leftMargin: (Theme.navigationRailWidth - width) / 2
        anchors.verticalCenter: parent.verticalCenter
        width: 20
        height: 20
        source: "../../../resources/icons/app-icon-ui.png"
        sourceSize: Qt.size(width * Screen.devicePixelRatio, height * Screen.devicePixelRatio)
        smooth: true
        opacity: root.active ? 1 : 0.6
    }

    Loader {
        id: terminalTabsLoader
        objectName: "titleBarTerminalTabs"
        anchors.left: parent.left
        anchors.leftMargin: root.contentLeftInset
        anchors.right: controls.left
        // Keep a reliable caption drag target even when tabs overflow.
        anchors.rightMargin: 64
        anchors.bottom: parent.bottom
        height: 32
        active: root.terminalTabsVisible && root.terminalController !== null
        visible: active
        enabled: root.terminalTabsEnabled
        sourceComponent: TerminalTabBar {
            controller: root.terminalController
            onTerminalFocusRequested: root.terminalFocusRequested()
        }
    }

    RowLayout {
        id: scriptActions
        objectName: "titleBarScriptActions"
        anchors.left: parent.left
        anchors.leftMargin: root.contentLeftInset
        anchors.verticalCenter: parent.verticalCenter
        height: Theme.captionActionHeight
        spacing: Theme.space4
        visible: root.scriptActionsVisible
        enabled: root.scriptActionsEnabled

        RowLayout {
            id: scriptButtons
            spacing: Theme.space4
            ChromeAction {
                objectName: "titleBarImportScript"
                text: "导入"
                iconName: "file_download"
                onClicked: root.importRequested()
            }
            ChromeAction {
                objectName: "titleBarCreateScript"
                text: root.compactScriptActions ? "新建" : "新建脚本"
                Accessible.name: "新建脚本"
                iconName: "add"
                onClicked: root.createRequested()
            }
            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 16
                Layout.leftMargin: Theme.space8
                Layout.rightMargin: Theme.space8
                color: Theme.navigationBorder
            }
            ChromeAction {
                objectName: "titleBarShareScript"
                text: "分享"
                iconName: "file_upload"
                enabled: root.scriptSelected
                onClicked: root.shareRequested()
            }
            ChromeAction {
                objectName: "titleBarEditScript"
                text: root.compactScriptActions ? "编辑" : "编辑脚本"
                Accessible.name: "编辑脚本"
                iconName: "edit"
                enabled: root.scriptSelected && root.scriptEditable && !root.scriptRunning
                onClicked: root.editRequested()
            }
            ChromeAction {
                objectName: "titleBarDeleteScript"
                text: root.compactScriptActions ? "删除" : "删除脚本"
                Accessible.name: "删除脚本"
                iconName: "delete_outline"
                enabled: root.scriptSelected && !root.scriptRunning
                foregroundColor: hovered ? Theme.errorColor : Theme.chromeForeground
                onClicked: root.deleteRequested()
            }
            ChromeAction {
                objectName: "titleBarRunScript"
                text: root.scriptRunning
                    ? (root.compactScriptActions ? "停止" : "停止运行")
                    : (root.compactScriptActions ? "运行" : "运行脚本")
                Accessible.name: root.scriptRunning ? "停止运行" : "运行脚本"
                iconName: root.scriptRunning ? "stop" : "play_arrow"
                enabled: root.scriptSelected
                foregroundColor: root.scriptRunning ? Theme.errorColor : Theme.success
                onClicked: root.runRequested()
            }
        }
        DeviceSelector {
            id: titleDevicePicker
            objectName: "titleBarDeviceSelector"
            visible: root.scriptDeviceVisible
            Layout.preferredWidth: Math.max(110, Math.min(210,
                controls.x - root.contentLeftInset
                - scriptButtons.implicitWidth - Theme.space12 - 32))
            Layout.preferredHeight: Theme.captionActionHeight
            Layout.leftMargin: Theme.space8
            compact: true
            controller: root.androidBackend
            toolId: root.selectedScript.id || ""
            requiredDevice: !!root.selectedScript.requires_android_device
            explicitTarget: !!root.selectedScript.android_explicit_target
        }
    }

    Row {
        id: controls
        objectName: "captionControls"
        anchors.right: parent.right
        height: parent.height
        Repeater {
            model: ["最小化", "最大化", "关闭"]
            delegate: Item {
                id: button
                required property int index
                required property string modelData
                objectName: "captionButton" + index
                width: root.controlWidth
                height: controls.height
                enabled: !!(root.hostWindow.flags & (index === 0 ? Qt.WindowMinimizeButtonHint
                    : index === 1 ? Qt.WindowMaximizeButtonHint : Qt.WindowCloseButtonHint))
                readonly property bool hovered: root.hostWindow.captionHovered === index
                readonly property bool pressed: hovered && root.hostWindow.captionPressed === index
                readonly property bool restored: root.hostWindow.visibility !== Window.Maximized
                readonly property color foreground: !enabled ? (root.dark ? "#33FFFFFF" : "#33000000")
                    : index === 2 && hovered ? "#FFFFFF"
                    : !root.active && !hovered ? (root.dark ? "#60FFFFFF" : "#60000000")
                    : root.dark ? "#FFFFFF" : "#000000"
                Accessible.role: Accessible.Button
                Accessible.name: index === 1 && !restored ? "还原" : modelData
                Accessible.onPressAction: root.hostWindow.chromeController.captionCommand(index)

                Rectangle {
                    objectName: "captionBackground"
                    anchors.fill: parent
                    color: !button.enabled || !button.hovered ? "transparent"
                        : button.index === 2 ? (root.modern
                            ? (button.pressed ? "#E5C32B1B" : "#C42B1C")
                            : (button.pressed ? "#99E71022" : "#E81123"))
                        : root.modern ? (root.dark
                            ? (button.pressed ? "#0BFEFEFE" : "#0FFFFFFF")
                            : (button.pressed ? "#06000000" : "#0A000000"))
                        : root.dark ? (button.pressed ? "#33FFFFFF" : "#1AFEFEFE")
                        : button.pressed ? "#33000000" : "#1A000000"
                }
                Canvas {
                    id: glyph
                    anchors.centerIn: parent
                    width: Theme.captionGlyphSize
                    height: Theme.captionGlyphSize
                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.reset()
                        ctx.strokeStyle = button.foreground
                        ctx.lineWidth = 1
                        ctx.lineJoin = "round"
                        ctx.beginPath()
                        if (button.index === 0) {
                            ctx.moveTo(0, 5.5)
                            ctx.lineTo(10, 5.5)
                        } else if (button.index === 1) {
                            if (button.restored) {
                                if (root.modern)
                                    ctx.roundedRect(0.5, 0.5, 9, 9, 0.6, 0.6)
                                else
                                    ctx.rect(0.5, 0.5, 9, 9)
                            } else {
                                ctx.moveTo(2.5, 2.5)
                                ctx.lineTo(2.5, 0.5)
                                ctx.lineTo(9.5, 0.5)
                                ctx.lineTo(9.5, 7.5)
                                ctx.lineTo(7.5, 7.5)
                                ctx.rect(0.5, 2.5, 7, 7)
                            }
                        } else {
                            ctx.moveTo(0.5, 0.5)
                            ctx.lineTo(9.5, 9.5)
                            ctx.moveTo(9.5, 0.5)
                            ctx.lineTo(0.5, 9.5)
                        }
                        ctx.stroke()
                    }
                    Connections {
                        target: button
                        function onForegroundChanged() { glyph.requestPaint() }
                        function onRestoredChanged() { glyph.requestPaint() }
                    }
                }
            }
        }
    }
}
