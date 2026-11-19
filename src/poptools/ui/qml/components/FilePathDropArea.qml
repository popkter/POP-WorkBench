import QtQuick
import QtQuick.Window
import "../theme"

DropArea {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    required property var target
    property bool append: false

    function localPath(url) {
        var value = decodeURIComponent(String(url))
        if (value.match(/^file:\/\/\/[A-Za-z]:/))
            value = value.substring(8)
        else if (value.indexOf("file://") === 0)
            value = value.substring(7)
        if (Qt.platform.os === "windows")
            value = value.replace(/\//g, "\\")
        return value
    }

    anchors.fill: parent
    z: 100
    function insertUrls(urls) {
        var paths = []
        for (var index = 0; index < urls.length; ++index)
            paths.push(root.localPath(urls[index]))
        var value = paths.join(" ")
        root.target.text = root.append && root.target.text.length
            ? root.target.text + " " + value : value
        root.target.forceActiveFocus()
    }
    onDropped: function(drop) {
        if (!drop.hasUrls || drop.urls.length === 0)
            return
        insertUrls(drop.urls)
        drop.accepted = true
    }

    Rectangle {
        anchors.fill: parent
        visible: root.containsDrag
        radius: Theme.radiusMedium
        color: "transparent"
        border.color: _visualPalette.primary
        border.width: 2
    }
}
