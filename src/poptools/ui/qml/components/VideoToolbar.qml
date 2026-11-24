import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

RowLayout {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property var controller: null
    property bool chrome: false
    property string mode: "file"
    signal locateRequested()
    spacing: root.chrome ? Theme.space12 : Theme.space4
    readonly property bool ready: controller !== null && controller.loaded

    component Action: PrimaryButton {
        Layout.preferredWidth: 32
        implicitHeight: root.chrome ? Theme.captionActionHeight : Theme.controlHeight
        Layout.preferredHeight: root.chrome ? Theme.captionActionHeight : 30
        compact: true
        showHoverTips: false
        labelFontWeight: root.chrome ? Font.Normal : Font.DemiBold
        radius: root.chrome ? Theme.radiusTiny : Theme.radiusControl
        contentSpacing: root.chrome ? 6 : (compact ? 0 : Theme.controlSpacing)
        disabledOpacity: root.chrome ? 0.4 : 1
        glyphSize: 20
        border.width: 0
        color: hovered ? _visualPalette.navigationHover : "transparent"
        foregroundColor: root.chrome ? _visualPalette.chromeForeground : _visualPalette.textPrimary
        Accessible.name: text
    }
    Action {
        objectName: "videoOpenButton"
        visible: root.mode === "file"
        Layout.preferredWidth: root.chrome ? -1 : 88
        compact: false
        labelFontSize: Theme.fontSupporting
        text: "打开视频"; iconName: "folder_open"
        enabled: root.controller !== null
        onClicked: root.controller.chooseFiles()
    }
    Action {
        objectName: "videoPreviousButton"
        visible: root.mode === "playback"
        text: "上一帧"; iconName: "skip_previous"
        enabled: root.ready && !root.controller.busy
        onClicked: root.controller.step(-1)
    }
    Action {
        objectName: "videoPlayButton"
        visible: root.mode === "playback"
        Layout.preferredWidth: 40
        text: root.controller && root.controller.playing ? "暂停" : "播放"
        iconName: root.controller && root.controller.playing ? "pause" : "play_arrow"
        enabled: root.ready && !root.controller.busy
        foregroundColor: _visualPalette.primary
        onClicked: root.controller.togglePlayback()
    }
    Action {
        text: "下一帧"; iconName: "skip_next"
        visible: root.mode === "playback"
        enabled: root.ready && !root.controller.busy
        onClicked: root.controller.step(1)
    }
    AppComboBox {
        id: rateBox
        objectName: "videoRateSelector"
        visible: root.mode === "playback"
        Layout.preferredWidth: 76
        Layout.preferredHeight: 30
        leftPadding: 8
        rightPadding: 28
        font.pixelSize: Theme.fontSupporting
        contentItem: Text {
            text: rateBox.displayText
            color: _visualPalette.textPrimary
            font.pixelSize: Theme.fontSupporting
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        model: ["0.25×", "0.5×", "1×", "1.5×", "2×"]
        currentIndex: root.controller ? [0.25, 0.5, 1, 1.5, 2].indexOf(root.controller.rate) : 2
        enabled: root.ready
        Accessible.name: "播放速度（声音音调随速度变化）"
        onActivated: root.controller.setRate([0.25, 0.5, 1, 1.5, 2][currentIndex])
    }
    Action {
        objectName: "videoLocatePlayheadButton"
        text: "定位播放头"; iconName: "my_location"
        // This glyph fills its em square; match the neighboring zoom icons optically.
        glyphSize: 16
        visible: root.mode === "timeline"
        enabled: root.ready
        onClicked: root.locateRequested()
    }
    Action {
        text: "缩小时间轴"; iconName: "zoom_out"
        visible: root.mode === "timeline"
        enabled: root.ready
        onClicked: root.controller.zoom(1 / 1.6)
    }
    AppComboBox {
        id: resolutionBox
        objectName: "videoResolutionSelector"
        visible: root.mode === "playback"
        Layout.preferredWidth: 90
        Layout.preferredHeight: 30
        leftPadding: 8
        rightPadding: 28
        font.pixelSize: Theme.fontSupporting
        contentItem: Text {
            text: resolutionBox.displayText
            color: _visualPalette.textPrimary
            font.pixelSize: Theme.fontSupporting
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }
        model: root.controller ? root.controller.resolutionOptions : []
        textRole: "label"
        valueRole: "value"
        currentIndex: root.controller ? root.controller.resolutionOptions.findIndex(
            item => item.value === root.controller.resolution) : 0
        enabled: root.ready && !root.controller.busy
        Accessible.name: "播放分辨率"
        onActivated: root.controller.setResolution(currentValue)
    }
    Action {
        text: "放大时间轴"; iconName: "zoom_in"
        visible: root.mode === "timeline"
        enabled: root.ready
        onClicked: root.controller.zoom(1.6)
    }
    Action {
        text: "查看完整时间轴"; iconName: "fit_screen"
        visible: root.mode === "timeline"
        enabled: root.ready
        onClicked: root.controller.fit()
    }
    Action {
        objectName: "videoPlaylistButton"
        text: "播放列表" + (root.controller && root.controller.playlist.length > 0
            ? "（" + root.controller.playlist.length + "）" : "")
        iconName: "playlist_play"
        visible: root.mode === "file"
        Layout.preferredWidth: -1
        compact: false
        labelFontSize: Theme.fontSupporting
        enabled: root.controller !== null
        foregroundColor: root.controller && root.controller.listVisible
            ? _visualPalette.primary : _visualPalette.textSecondary
        onClicked: root.controller.toggleList()
    }
    Action {
        text: root.controller && root.controller.volume > 0 ? "静音" : "开启声音"
        visible: root.mode === "playback"
        iconName: root.controller && root.controller.volume > 0 ? "volume_up" : "volume_off"
        enabled: root.ready
        onClicked: root.controller.setVolume(root.controller.volume > 0 ? 0 : 0.8)
    }
    Text {
        objectName: "videoFileName"
        visible: root.mode === "file"
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.maximumWidth: 420
        text: root.controller ? root.controller.fileName : "视频预览"
        color: root.chrome ? _visualPalette.chromeForeground : _visualPalette.textPrimary
        font.pixelSize: Theme.fontSupporting
        elide: Text.ElideMiddle
        verticalAlignment: Text.AlignVCenter
    }
    BusyIndicator {
        visible: root.mode === "file"
        Layout.preferredWidth: 20
        Layout.preferredHeight: 20
        running: root.controller && root.controller.busy
        opacity: running ? 1 : 0
    }
    Text {
        objectName: "videoPreviewPreparationStatus"
        property bool preparing: root.controller && root.controller.previewOptimizing
        property bool browsing: root.controller
            && typeof root.controller.previewApproximate !== "undefined"
            && root.controller.previewApproximate
        visible: root.mode === "file" && root.ready && (preparing || browsing)
        Layout.maximumWidth: 150
        text: preparing ? "正在准备流畅预览…" : "快速浏览"
        color: _visualPalette.textSecondary
        font.pixelSize: Theme.fontSupporting
        elide: Text.ElideRight
        Accessible.name: text
        ToolTip.visible: preparationHover.hovered
        ToolTip.delay: 500
        ToolTip.text: preparing
            ? "正在后台准备高清预览。可继续拖动和播放；完成后快速定位会更流畅。"
            : "快速拖动时显示邻近的清晰画面，停止移动后自动精确定位。"
        HoverHandler { id: preparationHover }
    }
}
