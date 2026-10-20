pragma ComponentBehavior: Bound

import QtQuick

Item {
    id: root
    required property var controller
    required property var parentWindow
    property bool tabsInTitleBar: false
    signal createScriptRequested(string command, string kind)
    function focusTerminal() { terminalConsole.focusTerminal() }

    // The terminal intentionally fills the complete workspace so it behaves
    // like a native command-line surface rather than a padded content page.
    DeveloperConsole {
        id: terminalConsole
        anchors.fill: parent
        controller: root.controller
        parentWindow: root.parentWindow
        tabsInTitleBar: root.tabsInTitleBar
        onCreateScriptRequested: function(command, kind) {
            root.createScriptRequested(command, kind)
        }
    }
}
