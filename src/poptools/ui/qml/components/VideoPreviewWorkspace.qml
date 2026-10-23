import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Item {
    id: root
    property var controller: null
    property bool actionsInTitleBar: false
    property bool shortcutsEnabled: true
    onVisibleChanged: {
        if (!visible && controller) { controller.pause(); controller.closeList(); controller.clearPreview() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 6
        VideoToolbar {
            controller: root.controller
            visible: !root.actionsInTitleBar
        }
        RowLayout {
            Layout.fillWidth: true
            Text {
                Layout.fillWidth: true
                text: root.controller ? root.controller.fileName : "视频预览"
                color: Theme.textPrimary
                font.pixelSize: Theme.fontBody
                elide: Text.ElideMiddle
            }
            BusyIndicator {
                Layout.preferredWidth: 20; Layout.preferredHeight: 20
                running: root.controller && root.controller.busy
                visible: running
            }
        }
        Rectangle {
            id: videoSurface
            objectName: "videoSurface"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 100
            color: "#101217"
            radius: Theme.radiusSmall
            clip: true
            property real zoomFactor: 1
            property real panX: 0
            property real panY: 0
            readonly property bool ready: root.controller && root.controller.loaded
            function constrainPan() {
                const limitX = Math.max(0, (videoPicture.paintedWidth - width) / 2)
                const limitY = Math.max(0, (videoPicture.paintedHeight - height) / 2)
                panX = Math.max(-limitX, Math.min(limitX, panX))
                panY = Math.max(-limitY, Math.min(limitY, panY))
            }
            function fitPicture() { zoomFactor = 1; panX = 0; panY = 0 }
            function zoomAt(factor, x, y) {
                const next = Math.max(1, Math.min(16, zoomFactor * factor))
                const ratio = next / zoomFactor
                // Keep the image point under the pointer fixed as the image grows.
                panX = (x - width / 2) * (1 - ratio) + panX * ratio
                panY = (y - height / 2) * (1 - ratio) + panY * ratio
                zoomFactor = next
                constrainPan()
            }
            onReadyChanged: if (!ready) fitPicture()
            onWidthChanged: Qt.callLater(constrainPan)
            onHeightChanged: Qt.callLater(constrainPan)
            Image {
                id: videoPicture
                objectName: "videoPicture"
                width: parent.width * parent.zoomFactor
                height: parent.height * parent.zoomFactor
                x: (parent.width - width) / 2 + parent.panX
                y: (parent.height - height) / 2 + parent.panY
                source: root.controller ? root.controller.frameSource : ""
                fillMode: Image.PreserveAspectFit
                cache: false
            }
            ColumnLayout {
                anchors.centerIn: parent
                width: Math.min(parent.width - 24, 340)
                visible: !root.controller || !root.controller.loaded
                spacing: 12
                MaterialIcon {
                    Layout.alignment: Qt.AlignHCenter
                    icon: "video_library"; iconSize: 40; color: "#CCD3DD"
                }
                Text {
                    Layout.fillWidth: true
                    text: root.controller && root.controller.busy ? "正在打开视频…" : "拖入视频，或点击文件夹图标打开"
                    color: "#CCD3DD"
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.WordWrap
                    horizontalAlignment: Text.AlignHCenter
                }
                PrimaryButton {
                    Layout.alignment: Qt.AlignHCenter
                    text: "打开视频"; iconName: "folder_open"
                    onClicked: if (root.controller) root.controller.chooseFiles()
                }
            }
            MouseArea {
                id: picturePointer
                objectName: "videoPicturePointer"
                anchors.fill: parent
                enabled: videoSurface.ready
                acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                preventStealing: true
                cursorShape: videoSurface.zoomFactor > 1
                    ? (pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor) : Qt.ArrowCursor
                property point previousPoint: Qt.point(0, 0)
                onPressed: mouse => { previousPoint = Qt.point(mouse.x, mouse.y) }
                onPositionChanged: mouse => {
                    if (!pressed || videoSurface.zoomFactor <= 1) return
                    videoSurface.panX += mouse.x - previousPoint.x
                    videoSurface.panY += mouse.y - previousPoint.y
                    videoSurface.constrainPan()
                    previousPoint = Qt.point(mouse.x, mouse.y)
                }
                onWheel: wheel => {
                    const delta = wheel.angleDelta.y || wheel.pixelDelta.y
                    if (delta) videoSurface.zoomAt(Math.pow(1.2, delta / 120), wheel.x, wheel.y)
                    wheel.accepted = true
                }
                onDoubleClicked: root.controller.togglePlayback()
            }
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: 8
            VideoToolbar {
                objectName: "videoPlaybackControls"
                controller: root.controller
                mode: "playback"
            }
            PrimaryButton {
                objectName: "videoFitPictureButton"
                Layout.preferredHeight: 30
                text: videoSurface.zoomFactor > 1 ? Math.round(videoSurface.zoomFactor * 100) + "% · 复位" : "适应画面"
                iconName: "fit_screen"
                glyphSize: 20
                labelFontSize: Theme.fontSupporting
                color: hovered ? Theme.navigationHover : "transparent"
                foregroundColor: Theme.textSecondary
                border.width: 0
                enabled: videoSurface.ready
                Accessible.name: "恢复完整画面；画面上滚轮缩放，放大后拖动平移"
                onClicked: videoSurface.fitPicture()
            }
        }
        Text {
            Layout.fillWidth: true
            visible: text.length > 0
            text: root.controller ? root.controller.message : ""
            color: Theme.errorColor
            font.pixelSize: Theme.fontSupporting
            wrapMode: Text.WordWrap
        }
        VideoTimeline {
            objectName: "videoTimeline"
            Layout.fillWidth: true
            controller: root.controller
        }
    }
    DropArea {
        anchors.fill: parent
        onEntered: drag => { drag.accepted = drag.hasUrls }
        onDropped: drop => {
            if (root.controller && drop.hasUrls) {
                root.controller.addFiles(drop.urls.map(url => url.toString()))
                drop.acceptProposedAction()
            }
        }
        Rectangle {
            anchors.fill: parent
            visible: parent.containsDrag
            color: "transparent"
            border.width: 2
            border.color: Theme.primary
            radius: Theme.radiusSmall
        }
    }
    Drawer {
        id: listDrawer
        objectName: "videoPlaylistDrawer"
        parent: root
        edge: Qt.RightEdge
        width: Math.min(320, root.width * 0.85)
        height: root.height
        modal: false
        dim: false
        interactive: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        visible: root.visible && root.controller && root.controller.listVisible
        onClosed: if (root.controller) root.controller.closeList()
        background: Rectangle {
            color: Theme.popupSurface
            border.color: Theme.outline
            radius: Theme.radiusSmall
        }
        contentItem: ColumnLayout {
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: "播放列表"
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontBody
                }
                PrimaryButton {
                    Layout.preferredWidth: 28; Layout.preferredHeight: 28
                    text: "关闭播放列表"; iconName: "close"; compact: true
                    color: "transparent"; border.width: 0
                    foregroundColor: Theme.textSecondary
                    onClicked: root.controller.closeList()
                }
            }
            ListView {
                id: playlist
                objectName: "videoPlaylist"
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: root.controller ? root.controller.playlist : []
                spacing: 4
                ScrollBar.vertical: ScrollBar {}
                delegate: Rectangle {
                    id: row
                    required property var modelData
                    required property int index
                    width: playlist.width
                    height: 48
                    radius: Theme.radiusSmall
                    color: modelData.selected ? Theme.primaryContainer : Theme.surfaceContainer
                    Text {
                        anchors.left: parent.left
                        anchors.leftMargin: 8
                        anchors.right: remove.left
                        anchors.verticalCenter: parent.verticalCenter
                        text: row.modelData.name
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSupporting
                        elide: Text.ElideMiddle
                    }
                    MouseArea {
                        anchors.fill: parent
                        anchors.rightMargin: 30
                        onClicked: { root.controller.selectVideo(row.index); root.controller.closeList() }
                    }
                    PrimaryButton {
                        id: remove
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: 28; height: 28
                        text: "移出列表"; iconName: "close"; compact: true
                        color: "transparent"; border.width: 0
                        foregroundColor: Theme.textSecondary
                        onClicked: root.controller.removeVideo(row.index)
                    }
                }
            }
            Text {
                visible: !root.controller || root.controller.playlist.length === 0
                text: "打开或拖入视频以添加到列表"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSupporting
                wrapMode: Text.WordWrap
                Layout.fillWidth: true
            }
        }
        padding: 12
    }
    Shortcut {
        sequence: "Space"
        enabled: root.visible && root.shortcutsEnabled && root.controller && root.controller.loaded
        onActivated: root.controller.togglePlayback()
    }
    Shortcut {
        sequence: "Left"
        enabled: root.visible && root.shortcutsEnabled && root.controller && root.controller.loaded
        onActivated: root.controller.step(-1)
    }
    Shortcut {
        sequence: "Right"
        enabled: root.visible && root.shortcutsEnabled && root.controller && root.controller.loaded
        onActivated: root.controller.step(1)
    }
    Shortcut {
        sequence: "Ctrl+O"
        enabled: root.visible && root.shortcutsEnabled && root.controller !== null
        onActivated: root.controller.chooseFiles()
    }
}
