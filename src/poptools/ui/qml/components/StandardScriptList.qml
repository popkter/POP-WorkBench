pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import "../theme"

ScriptCollectionView {
    id: root
    property bool quickLaunch: false
    actionText: quickLaunch ? "点击运行" : "↑ / ↓ 切换脚本"
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
        objectName: "scriptRow_" + toolId
        onSelectedChanged: if (selected)
            root.positionViewAtIndex(index, ListView.Contain)
        width: root.width - (root.needsVerticalScroll ? root.scrollGutter : 0)
        height: root.kindFilter === "all" || root.kindFilter === executorKind ? Theme.scriptRowHeight : 0
        visible: height > 0
        radius: Theme.radiusControl
        color: selected ? Theme.listSelected : rowMouse.containsMouse ? Theme.surfaceContainer : index % 2 === 0 ? Theme.listAlternate : "transparent"
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.space12
            anchors.rightMargin: Theme.space8
            spacing: 10
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
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                text: scriptRow.title
                color: scriptRow.selected ? Theme.primary : Theme.textPrimary
                font.pixelSize: Theme.fontSupporting
                font.weight: scriptRow.selected ? Font.Bold : Font.Normal
                elide: Text.ElideRight
            }
            MaterialIcon {
                icon: scriptRow.running ? "hourglass_top" : root.quickLaunch ? "play_arrow" : "chevron_right"
                iconSize: 14
                color: scriptRow.running ? Theme.primary : Theme.textSecondary
                Layout.preferredWidth: 14
            }
        }
        MouseArea {
            id: rowMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                root.activateTool(scriptRow.toolId, scriptRow);
                root.forceActiveFocus();
            }
        }
    }
}
