pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window
import QtQuick.Controls
import "../theme"

PrimaryButton {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    objectName: "scriptIconPicker"

    property string selectedIcon: "terminal"
    signal iconSelected(string iconName)

    readonly property var icons: [
        "terminal", "code", "build", "settings", "home", "apps",
        "dashboard", "handyman", "tune", "extension", "star", "bookmark",
        "label", "info", "help", "notifications", "integration_instructions",
        "input", "developer_mode", "web", "http", "storage", "dns", "memory",
        "developer_board", "widgets", "commit", "merge_type", "account_tree",
        "android", "smartphone", "phone_android", "tablet_android", "devices",
        "monitor", "computer", "keyboard", "mouse", "usb", "bluetooth",
        "cast", "cast_connected", "devices_other", "folder", "folder_open",
        "create_new_folder", "insert_drive_file", "description", "content_copy",
        "content_cut", "content_paste", "save", "archive", "unarchive", "delete",
        "restore", "print", "search", "filter_alt", "sort", "list", "checklist",
        "add_circle", "edit", "refresh", "sync", "play_arrow", "stop", "pause",
        "skip_next", "schedule", "timer", "bolt", "power_settings_new",
        "cleaning_services", "task_alt", "undo", "redo", "cloud", "cloud_upload",
        "cloud_download", "download", "upload", "link", "public", "language",
        "wifi", "router", "wifi_tethering", "network_check", "rss_feed", "send",
        "bug_report", "speed", "monitor_heart", "security", "vpn_key", "key",
        "lock", "lock_open", "visibility", "visibility_off", "verified_user",
        "warning", "error", "mic", "volume_up", "headphones", "record_voice_over",
        "image", "photo_camera", "palette", "calculate", "functions", "percent"
    ]

    width: 40
    height: 40
    compact: true
    text: "选择脚本图标"
    iconName: root.selectedIcon
    glyphSize: 24
    tonal: true
    foregroundColor: _visualPalette.primary
    border.width: 0
    radius: Theme.radiusSmall
    color: root.hovered || iconPopup.opened
        ? _visualPalette.primaryContainer : _visualPalette.surfaceContainerLow
    onClicked: iconPopup.open()

    Popup {
        id: iconPopup
        objectName: "scriptIconPickerPopup"
        x: -5
        y: root.height + Theme.space8
        width: 300
        height: 214
        padding: Theme.space8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

        background: AppPopupSurface {}

        contentItem: GridView {
            id: iconGrid
            cellWidth: 52
            cellHeight: 48
            model: root.icons
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

            delegate: Rectangle {
                id: iconChoice
                required property string modelData
                width: 44
                height: 40
                radius: Theme.radiusSmall
                color: root.selectedIcon === modelData
                    ? _visualPalette.primaryContainer
                    : (choiceMouse.containsMouse
                        ? _visualPalette.surfaceContainerHigh : "transparent")

                MaterialIcon {
                    anchors.centerIn: parent
                    icon: iconChoice.modelData
                    iconSize: 25
                    color: root.selectedIcon === iconChoice.modelData
                        ? _visualPalette.primary : _visualPalette.textSecondary
                }

                HoverTips {
                    visible: choiceMouse.containsMouse
                    text: iconChoice.modelData
                    delay: 350
                }

                MouseArea {
                    id: choiceMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.iconSelected(iconChoice.modelData)
                        iconPopup.close()
                    }
                }
            }
        }
    }
}
