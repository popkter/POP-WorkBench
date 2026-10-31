import QtQuick
import QtQuick.Controls
import "../theme"

// Common collection mechanics. Presentations supply their delegate and activation.
ListView {
    id: root
    required property var controller
    required property var listModel
    property string kindFilter: "all"
    property string headingText: "脚本名称"
    property string countSuffix: " 个脚本"
    property string actionText: ""
    property bool settling: false
    property bool reordering: false
    property int pendingLaunchCount: 0
    property string emptyText: listModel.totalCount === 0 ? "暂无自定义脚本" : "没有匹配的脚本"
    readonly property int visibleCount: {
        const count = listModel.count;
        return listModel.countForKind(kindFilter);
    }
    readonly property bool needsVerticalScroll: contentHeight > height + 0.5
    readonly property real scrollGutter: verticalBar.width + Theme.space8
    property alias verticalScrollBar: verticalBar
    signal toolActivated(string toolId)
    signal toolActivatedAt(string toolId, rect sourceRect)
    signal toolRunRequested(string toolId)
    signal toolActionRequested(string toolId, string action)
    signal reorderFailed()
    signal navigationRequested(string toolId)
    signal activationRequested(string toolId, var row)
    objectName: "sharedScriptList"
    model: listModel
    clip: true
    spacing: 0
    cacheBuffer: 0
    boundsBehavior: Flickable.StopAtBounds

    // Stable interface for the host. A presentation handles activation through
    // the signal and can override the optional card return hooks.
    function activateTool(id, row) {
        activationRequested(id, row);
    }
    function returnCardRect(id) {
        return Qt.rect(0, 0, 0, 0);
    }
    function dockCardFace(id, face) {
    }
    function cancelPendingLaunches() {
    }

    function findRow(id) {
        const index = listModel.indexOfTool(id);
        return index >= 0 ? itemAtIndex(index) : null;
    }
    function selectAdjacent(direction) {
        const id = listModel.adjacentToolId(direction, kindFilter);
        if (id.length > 0)
            navigationRequested(id);
    }
    // Delegates are recreated as they enter the viewport. Moving the view from
    // their selectedChanged handler reenters ListView layout and can collapse
    // its content extent to a single row. Follow actual selection changes here,
    // after model notifications and delegate creation have finished instead.
    function revealSelection() {
        if (reordering) return;
        const index = listModel.indexOfTool(listModel.selectedToolId, kindFilter);
        if (index >= 0) {
            cancelFlick();
            positionViewAtIndex(index, ListView.Contain);
        }
    }
    Connections {
        target: root.listModel
        function onSelectedToolIdChanged() {
            if (!root.reordering) Qt.callLater(root.revealSelection);
        }
        function onLayoutChanged() {
            if (!root.reordering) Qt.callLater(root.revealSelection);
        }
    }
    Component.onCompleted: Qt.callLater(root.revealSelection)
    function activateSelection() {
        const id = listModel.selectedToolId;
        if (listModel.indexOfTool(id, kindFilter) >= 0)
            activationRequested(id, null);
    }
    Keys.onUpPressed: selectAdjacent(-1)
    Keys.onDownPressed: selectAdjacent(1)
    Keys.onReturnPressed: activateSelection()
    Keys.onEnterPressed: activateSelection()
    Text {
        anchors.centerIn: parent
        visible: root.visibleCount === 0
        text: root.emptyText
        color: Theme.textSecondary
        font.pixelSize: Theme.fontSupporting
    }
    ScrollBar.vertical: ScrollBar {
        id: verticalBar
        objectName: "scriptListScrollBar"
        policy: root.needsVerticalScroll ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
    }
}
