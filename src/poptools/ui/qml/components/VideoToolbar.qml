import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

RowLayout {
    id: root
    property var controller: null
    property bool chrome: false
    property string mode: "file"
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
        color: hovered ? Theme.navigationHover : "transparent"
        foregroundColor: root.chrome ? Theme.chromeForeground : Theme.textPrimary
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
        foregroundColor: Theme.primary
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
            color: Theme.textPrimary
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
        text: "缩小时间轴"; iconName: "zoom_out"
        visible: root.mode === "timeline"
        enabled: root.ready
        onClicked: root.controller.zoom(1 / 1.6)
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
        text: "播放列表"; iconName: "playlist_play"
        visible: root.mode === "file"
        Layout.preferredWidth: root.chrome ? -1 : 88
        compact: false
        labelFontSize: Theme.fontSupporting
        enabled: root.controller !== null
        foregroundColor: root.controller && root.controller.listVisible
            ? Theme.primary : Theme.textSecondary
        onClicked: root.controller.toggleList()
    }
    Action {
        text: root.controller && root.controller.volume > 0 ? "静音" : "开启声音"
        visible: root.mode === "playback"
        iconName: root.controller && root.controller.volume > 0 ? "volume_up" : "volume_off"
        enabled: root.ready
        onClicked: root.controller.setVolume(root.controller.volume > 0 ? 0 : 0.8)
    }
}
