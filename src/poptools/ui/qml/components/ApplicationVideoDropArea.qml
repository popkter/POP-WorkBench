import QtQuick
import "../theme"

DropArea {
    id: root
    required property var controller
    required property Item hitTestRoot
    signal videoDropped(var urls)
    anchors.fill: parent
    z: 1000000
    property var pathEditor: null

    // Parameter editors keep their file-to-path drop behavior, including when
    // they are nested in a scrolled form or a popup.
    function overPathEditor(item, x, y) {
        if (!item.visible || !item.enabled || item === root)
            return null
        const point = item.mapFromItem(root, x, y)
        const inside = item.contains(point)
        if (item.clip && !inside)
            return null
        if (inside && item.preserveParameterFileDrop === true)
            return item
        for (const child of item.children) {
            const editor = overPathEditor(child, x, y)
            if (editor)
                return editor
        }
        return null
    }
    function accepts(event) {
        return controller && event.hasUrls
            && controller.acceptsVideoDrop(event.urls.map(url => url.toString()))
    }
    onEntered: drag => {
        drag.accepted = accepts(drag)
        pathEditor = overPathEditor(hitTestRoot, drag.x, drag.y)
    }
    onPositionChanged: drag => {
        pathEditor = overPathEditor(hitTestRoot, drag.x, drag.y)
    }
    onExited: pathEditor = null
    onDropped: drop => {
        if (!accepts(drop)) {
            drop.accepted = false
            return
        }
        const urls = drop.urls.map(url => url.toString())
        drop.acceptProposedAction()
        const editor = overPathEditor(hitTestRoot, drop.x, drop.y)
        if (editor) {
            editor.insertUrls(urls)
            return
        }
        root.videoDropped(urls)
    }
    Rectangle {
        anchors.fill: parent
        visible: root.containsDrag && !root.pathEditor
        color: "transparent"
        border.width: 2
        border.color: Theme.primary
        radius: Theme.radiusSmall
    }
}
