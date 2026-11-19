import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    required property var controller
    required property int minimumVisibleLineCount
    required property real preferredExpandedHeight
    required property real maximumExpandedHeight
    required property bool resizable
    property bool expanded: true
    property real expandedHeight: minimumExpandedHeight
    property bool userResized: false
    property real resizeStartSceneY: 0
    property real resizeStartHeight: 0
    property real panelMargin: Theme.space0
    readonly property real separatorHeight: 8
    readonly property real headerHeight: 62
    readonly property real outputOuterMargin: Theme.space16
    readonly property real outputViewportMargin: Theme.space16
    readonly property real outputTextVerticalPadding: Theme.space12
    readonly property real minimumExpandedHeight:
        separatorHeight + headerHeight + outputOuterMargin
            + outputViewportMargin * 2 + outputTextVerticalPadding
            + Math.ceil(consoleFontMetrics.lineSpacing * minimumVisibleLineCount)
    readonly property real dragMinimumExpandedHeight: root.resizable
        ? Math.max(minimumExpandedHeight,
                   Math.min(maximumExpandedHeight, preferredExpandedHeight))
        : minimumExpandedHeight
    readonly property real collapsedHeight: separatorHeight + headerHeight

    FontMetrics {
        id: consoleFontMetrics
        font.family: "Cascadia Mono"
        font.pixelSize: Theme.fontSupporting
    }

    clip: true

    implicitHeight: !root.resizable
        ? root.clampedHeight(root.preferredExpandedHeight)
        : (root.expanded ? root.expandedHeight : root.collapsedHeight)

    function clampedHeight(value) {
        return Math.max(dragMinimumExpandedHeight,
                        Math.min(maximumExpandedHeight, value))
    }

    function applyDefaultHeight() {
        expandedHeight = clampedHeight(preferredExpandedHeight)
    }

    Component.onCompleted: applyDefaultHeight()
    onResizableChanged: {
        userResized = false
        expanded = true
        applyDefaultHeight()
    }
    onPreferredExpandedHeightChanged: {
        if (!userResized)
            applyDefaultHeight()
    }
    onDragMinimumExpandedHeightChanged: {
        if (userResized)
            expandedHeight = clampedHeight(expandedHeight)
    }
    onMaximumExpandedHeightChanged: {
        if (userResized)
            expandedHeight = clampedHeight(expandedHeight)
        else
            applyDefaultHeight()
    }

    Connections {
        target: root.controller
        function onSelectedToolChanged() {
            root.userResized = false
            Qt.callLater(root.applyDefaultHeight)
        }
    }

    Rectangle {
        id: resizeSeparator
        visible: true
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: root.panelMargin
        anchors.rightMargin: root.panelMargin
        height: root.separatorHeight
        color: _visualPalette.consoleDivider

        MouseArea {
            id: resizeMouse
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: 16
            enabled: root.resizable
            hoverEnabled: true
            cursorShape: root.resizable ? Qt.SizeVerCursor : Qt.ArrowCursor
            onPressed: function(mouse) {
                if (!root.expanded)
                    root.expanded = true
                root.userResized = true
                const scenePoint = resizeMouse.mapToItem(null, mouse.x, mouse.y)
                root.resizeStartSceneY = scenePoint.y
                root.resizeStartHeight = root.expandedHeight
            }
            onPositionChanged: function(mouse) {
                if (!pressed)
                    return
                const scenePoint = resizeMouse.mapToItem(null, mouse.x, mouse.y)
                const requestedHeight = root.resizeStartHeight
                                      + root.resizeStartSceneY - scenePoint.y
                root.expandedHeight = root.clampedHeight(requestedHeight)
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: root.separatorHeight

        spacing: Theme.space0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: root.headerHeight
            Layout.leftMargin: Theme.space20
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            Text {
                text: "控制台输出"
                color: _visualPalette.textPrimary
                font.pixelSize: Theme.fontComponentTitle
                font.weight: Font.DemiBold
            }
            MaterialIcon {
                icon: root.expanded ? "expand_more" : "expand_less"
                iconSize: 22
                color: _visualPalette.textSecondary
            }
            Item { Layout.fillWidth: true }
            PrimaryButton {
                Layout.preferredWidth: 86
                Layout.preferredHeight: 38
                radius: Theme.radiusSmall
                text: "清空"
                iconName: "delete_sweep"
                tonal: true
                color: hovered ? _visualPalette.surfaceContainerHigh : _visualPalette.surface
                border.color: _visualPalette.outlineVariant
                foregroundColor: _visualPalette.textSecondary
                labelFontSize: Theme.fontBody
                labelFontWeight: Font.Normal
                glyphSize: 19
                contentSpacing: Theme.controlSpacing
                onClicked: root.controller.clearConsole()
            }
            PrimaryButton {
                visible: root.resizable
                Layout.preferredWidth: 36
                Layout.preferredHeight: 36
                compact: true
                text: root.expanded ? "收起控制台" : "展开控制台"
                iconName: root.expanded ? "keyboard_arrow_down" : "keyboard_arrow_up"
                glyphSize: 23
                tonal: true
                foregroundColor: _visualPalette.textSecondary
                border.width: 0
                radius: Theme.radiusLarge
                color: hovered ? _visualPalette.surfaceContainerHigh : "transparent"
                onClicked: root.expanded = !root.expanded
            }
        }



        Rectangle {
            visible: root.expanded
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: root.outputOuterMargin
            Layout.rightMargin: root.outputOuterMargin
            Layout.bottomMargin: root.outputOuterMargin
            Layout.topMargin: Theme.space0
            radius: Theme.radiusMedium
            color: _visualPalette.glassMode ? "transparent" : _visualPalette.consoleBackground
            GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.consoleBackground; z: -0.5 }

            DesktopScrollView {
                anchors.fill: parent
                anchors.margins: root.outputViewportMargin
                clip: true
                TextArea {
                    text: root.controller.consoleText
                    readOnly: true
                    selectByMouse: true
                    wrapMode: TextEdit.WrapAnywhere
                    color: _visualPalette.consoleText
                    selectionColor: _visualPalette.primary
                    selectedTextColor: "white"
                    font.family: "Cascadia Mono"
                    font.pixelSize: Theme.fontSupporting
                    topPadding: root.outputTextVerticalPadding / 2
                    bottomPadding: root.outputTextVerticalPadding / 2
                    background: null
                    onTextChanged: cursorPosition = length
                }
            }
        }
    }
}




