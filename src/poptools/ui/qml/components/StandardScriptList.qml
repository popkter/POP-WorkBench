pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "../theme"

ScriptCollectionView {
    id: root
    property bool quickLaunch: false
    readonly property real rowActionSize: width < 280 ? 24 : 26
    readonly property bool reorderEnabled: !quickLaunch && controller.toolSortMode === "custom"
    property string draggedToolId: ""
    property string dropTargetId: ""
    property bool dropAfter: false
    property real dropLineY: 0
    property real dragPointerY: 0
    property bool committingReorder: false
    interactive: !reordering
    actionText: quickLaunch ? "点击出卡" : reorderEnabled ? "拖动左侧手柄排序 · 双击运行" : "双击运行 · ↑ / ↓ 切换"
    onReorderEnabledChanged: if (!reorderEnabled) cancelReorder()
    onKindFilterChanged: cancelReorder()

    function cancelReorder() {
        reordering = false;
        draggedToolId = "";
        dropTargetId = "";
    }
    function updateDropTarget(y) {
        dragPointerY = y;
        const index = indexAt(1, contentY + Math.max(0, Math.min(height - 1, y)));
        const row = index >= 0 ? itemAtIndex(index)
            : itemAtIndex(listModel.indexOfTool(listModel.lastToolId(kindFilter)));
        if (!row || row.height <= 0 || row.running) {
            dropTargetId = "";
            return;
        }
        dropTargetId = row.toolId;
        dropAfter = y + contentY >= row.y + row.height / 2;
        dropLineY = row.y - contentY + (dropAfter ? row.height : 0);
    }
    function finishReorder(y) {
        if (reordering) {
            updateDropTarget(y);
            if (dropTargetId && dropTargetId !== draggedToolId) {
                committingReorder = true;
                const success = controller.moveToolRelative(draggedToolId, dropTargetId, dropAfter);
                committingReorder = false;
                if (!success) reorderFailed();
            }
        }
        cancelReorder();
    }
    Connections {
        target: root.listModel
        function onModelAboutToBeReset() { root.cancelReorder(); }
        function onLayoutAboutToBeChanged() {
            if (!root.committingReorder) root.cancelReorder();
        }
    }
    Keys.onEscapePressed: cancelReorder()

    // Keep the mouse grab on the view, rather than a virtualized delegate: the
    // source row may be destroyed while the user scrolls during a long drag.
    MouseArea {
        id: reorderGrip
        objectName: "scriptReorderGrip"
        width: 36
        height: root.height
        z: 5
        visible: root.reorderEnabled
        preventStealing: true
        hoverEnabled: true
        property real pressY: 0
        cursorShape: root.reordering ? Qt.ClosedHandCursor : Qt.OpenHandCursor
        HoverTips {
            visible: reorderGrip.containsMouse && !reorderGrip.pressed
            text: "拖动调整脚本顺序"
            y: reorderGrip.mouseY - height - Theme.space8
        }
        onPressed: function(mouse) {
            const index = root.indexAt(1, root.contentY + mouse.y);
            const row = index >= 0 ? root.itemAtIndex(index) : null;
            if (!row || row.running) {
                mouse.accepted = false;
                return;
            }
            root.cancelFlick();
            root.forceActiveFocus();
            root.draggedToolId = row.toolId;
            pressY = mouse.y;
        }
        onPositionChanged: function(mouse) {
            if (!pressed || !root.draggedToolId) return;
            if (!root.reordering && Math.abs(mouse.y - pressY) >= Qt.styleHints.startDragDistance)
                root.reordering = true;
            if (root.reordering) root.updateDropTarget(mouse.y);
        }
        onReleased: function(mouse) { root.finishReorder(mouse.y); }
        onCanceled: root.cancelReorder()
    }
    Timer {
        interval: 30
        repeat: true
        running: root.reordering
        onTriggered: {
            const edge = Math.min(36, root.height / 4);
            const delta = root.dragPointerY < edge ? -12
                : root.dragPointerY > root.height - edge ? 12 : 0;
            if (!delta) return;
            root.contentY = Math.max(root.originY, Math.min(
                root.originY + root.contentHeight - root.height, root.contentY + delta));
            root.forceLayout();
            root.updateDropTarget(root.dragPointerY);
        }
    }
    Rectangle {
        objectName: "scriptDropIndicator"
        z: 6
        x: 4
        y: root.dropLineY - height / 2
        width: root.width - (root.needsVerticalScroll ? root.scrollGutter : 0) - 8
        height: 2
        color: Theme.primary
        visible: root.reordering && root.dropTargetId !== "" && root.dropTargetId !== root.draggedToolId
    }
    onActivationRequested: function (id, row) {
        handleActivation(id, row);
    }
    function handleActivation(id, row) {
        if (!id)
            return;
        if (!quickLaunch) {
            toolActivated(id);
            return;
        }
        row = row || findRow(id);
        if (!row) {
            toolActivated(id);
            return;
        }
        const point = row.mapToGlobal(0, 0);
        toolActivatedAt(id, Qt.rect(point.x, point.y, row.width, row.height));
    }
    delegate: Rectangle {
        id: scriptRow
        required property string toolId
        required property string title
        required property string iconName
        required property string executorKind
        required property bool selected
        required property bool running
        required property int index
        readonly property bool cardOpen: root.quickLaunch && root.controller.openCardIds.indexOf(toolId) >= 0
        objectName: "scriptRow_" + toolId
        width: root.width - (root.needsVerticalScroll ? root.scrollGutter : 0)
        height: root.kindFilter === "all" || root.kindFilter === executorKind ? Theme.scriptRowHeight : 0
        visible: height > 0
        opacity: root.reordering && root.draggedToolId === toolId ? 0.45 : 1
        radius: Theme.radiusControl
        color: selected ? Theme.listSelected : rowMouse.containsMouse ? Theme.surfaceContainer : index % 2 === 0 ? Theme.listAlternate : "transparent"
        RowLayout {
            z: 1
            anchors.fill: parent
            anchors.leftMargin: Theme.space12
            anchors.rightMargin: Theme.space8
            spacing: 8
            MaterialIcon {
                objectName: "scriptDragHandle_" + scriptRow.toolId
                visible: root.reorderEnabled
                icon: "drag_indicator"
                iconSize: 16
                color: scriptRow.running ? Theme.outline : Theme.textSecondary
                Layout.preferredWidth: 16
            }
            Rectangle {
                Layout.preferredWidth: 26
                Layout.preferredHeight: 26
                radius: 5
                color: scriptRow.executorKind === "python" ? Theme.tertiaryContainer : scriptRow.executorKind === "powershell" ? Theme.runtimeBadge : Theme.successContainer
                MaterialIcon {
                    anchors.centerIn: parent
                    icon: scriptRow.iconName || (scriptRow.executorKind === "batch" ? "smartphone" : "terminal")
                    iconSize: 16
                    color: scriptRow.executorKind === "python" ? Theme.tertiary : scriptRow.executorKind === "powershell" ? Theme.runtimeBadgeText : Theme.success
                }
            }
            Text {
                objectName: "scriptRowTitle_" + scriptRow.toolId
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: scriptRow.title
                color: scriptRow.selected ? Theme.primary : Theme.textPrimary
                font.pixelSize: Theme.fontSupporting
                font.weight: scriptRow.selected ? Font.Bold : Font.Normal
                elide: Text.ElideRight
            }
            RowLayout {
                objectName: "scriptRowActions_" + scriptRow.toolId
                visible: scriptRow.selected && !root.quickLaunch
                spacing: 4
                Layout.minimumWidth: root.rowActionSize * 4 + spacing * 3
                Layout.maximumWidth: Layout.minimumWidth
                ScriptListActionButton {
                    objectName: "scriptRowEdit_" + scriptRow.toolId
                    buttonSize: root.rowActionSize
                    text: "编辑脚本"
                    iconName: "edit"
                    enabled: !root.quickLaunch && !scriptRow.running && !!root.controller.selectedTool.editable
                    onClicked: root.toolActionRequested(scriptRow.toolId, "edit")
                }
                ScriptListActionButton {
                    objectName: "scriptRowDelete_" + scriptRow.toolId
                    buttonSize: root.rowActionSize
                    text: "删除脚本"
                    iconName: "delete_outline"
                    tint: hovered ? Theme.errorColor : Theme.primary
                    enabled: !scriptRow.running
                    onClicked: root.toolActionRequested(scriptRow.toolId, "delete")
                }
                ScriptListActionButton {
                    objectName: "scriptRowShare_" + scriptRow.toolId
                    buttonSize: root.rowActionSize
                    text: "分享脚本"
                    iconName: "share"
                    onClicked: root.toolActionRequested(scriptRow.toolId, "share")
                }
                ScriptListActionButton {
                    objectName: "scriptRowRun_" + scriptRow.toolId
                    buttonSize: root.rowActionSize
                    text: scriptRow.running ? "停止运行" : "运行脚本"
                    iconName: scriptRow.running ? "stop" : "play_arrow"
                    tint: scriptRow.running ? Theme.errorColor : Theme.primary
                    onClicked: root.toolActionRequested(scriptRow.toolId, "run")
                }
            }
            MaterialIcon {
                icon: scriptRow.running ? "hourglass_top" : "chevron_right"
                iconSize: 14
                color: scriptRow.running ? Theme.primary : Theme.textSecondary
                Layout.preferredWidth: 14
            }
            Text {
                visible: root.quickLaunch && scriptRow.cardOpen
                text: "已打开"
                color: Theme.primary
                font.pixelSize: Theme.fontCaption
            }
        }
        MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onDoubleClicked: function(mouse) {
                mouse.accepted = true;
                if (!root.quickLaunch) root.toolRunRequested(scriptRow.toolId);
            }
            onClicked: {
                root.forceActiveFocus();
                root.activateTool(scriptRow.toolId, scriptRow);
            }
        }
    }
}
