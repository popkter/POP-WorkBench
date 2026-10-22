import QtQuick
import QtQuick.Controls
import "../theme"

// Common collection mechanics. Presentations supply their delegate and activation.
ListView {
    id: root
    required property var controller
    required property var listModel
    property string kindFilter: "all"
    property string keyboardToolId: ""
    property string headingText: "脚本名称"
    property string countSuffix: " 个脚本"
    property string actionText: ""
    property bool settling: false
    property int pendingLaunchCount: 0
    property string emptyText: listModel.totalCount === 0 ? "暂无自定义脚本" : "没有匹配的脚本"
    readonly property int visibleCount: {
        const count = listModel.count;
        return listModel.countForKind(kindFilter);
    }
    readonly property bool needsVerticalScroll: contentHeight > height + 0.5
    readonly property real scrollGutter: verticalBar.width + Theme.space8
    signal toolActivated(string toolId)
    signal toolActivatedAt(string toolId, rect sourceRect)
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
    Keys.onUpPressed: selectAdjacent(-1)
    Keys.onDownPressed: selectAdjacent(1)
    Keys.onReturnPressed: activationRequested(keyboardToolId, null)
    Keys.onEnterPressed: activationRequested(keyboardToolId, null)
    Text {
        anchors.centerIn: parent
        visible: root.visibleCount === 0
        text: root.emptyText
        color: Theme.textSecondary
        font.pixelSize: Theme.fontSupporting
    }
    ScrollBar.vertical: ScrollBar {
        id: verticalBar
        policy: root.needsVerticalScroll ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff
    }
}
