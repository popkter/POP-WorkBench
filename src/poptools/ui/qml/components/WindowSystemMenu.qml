import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import "../theme"

AppMenu {
    id: menu
    required property var hostWindow
    objectName: "windowSystemMenu"
    implicitWidth: 232
    readonly property bool maximized: hostWindow.visibility === Window.Maximized
    readonly property bool minimized: hostWindow.visibility === Window.Minimized
    function showAt(x, y) {
        menu.x = Math.max(8, Math.min(x, parent.width - width - 8))
        menu.y = Math.max(8, Math.min(y, parent.height - implicitHeight - 8))
        open()
    }
    component WindowAction: AppMenuItem {
        id: action
        property string command
        property string glyph
        property string shortcutText: ""
        objectName: "windowMenu_" + command
        contentItem: RowLayout {
            spacing: 12
            MaterialIcon {
                Layout.preferredWidth: 18
                icon: action.glyph
                iconSize: 18
                color: action.destructive ? Theme.errorColor : Theme.textSecondary
                opacity: action.enabled ? 1 : 0.48
            }
            Text {
                Layout.fillWidth: true
                text: action.text
                color: action.destructive ? Theme.errorColor : Theme.textPrimary
                opacity: action.enabled ? 1 : 0.48
                font.pixelSize: Theme.fontSupporting
            }
            Text {
                text: action.shortcutText
                visible: text.length > 0
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
            }
        }
        onTriggered: {
            menu.close()
            menu.hostWindow.chromeController.windowCommand(command)
        }
    }
    WindowAction {
        text: "还原"; command: "restore"; glyph: "filter_none"
        enabled: menu.maximized || menu.minimized
    }
    WindowAction {
        text: "移动"; command: "move"; glyph: "open_with"
        enabled: !menu.maximized && !menu.minimized
    }
    WindowAction {
        text: "调整大小"; command: "resize"; glyph: "open_in_full"
        enabled: !menu.maximized && !menu.minimized
            && !(menu.hostWindow.flags & Qt.MSWindowsFixedSizeDialogHint)
            && (menu.hostWindow.minimumWidth !== menu.hostWindow.maximumWidth
                || menu.hostWindow.minimumHeight !== menu.hostWindow.maximumHeight)
    }
    WindowAction {
        text: "最小化"; command: "minimize"; glyph: "minimize"
        enabled: !!(menu.hostWindow.flags & Qt.WindowMinimizeButtonHint) && !menu.minimized
    }
    WindowAction {
        text: "最大化"; command: "maximize"; glyph: "crop_square"
        enabled: !!(menu.hostWindow.flags & Qt.WindowMaximizeButtonHint) && !menu.maximized
    }
    AppMenuSeparator {}
    WindowAction {
        text: "关闭"; command: "close"; glyph: "close"; shortcutText: "Alt+F4"
        destructive: true
        enabled: !!(menu.hostWindow.flags & Qt.WindowCloseButtonHint)
    }
}
