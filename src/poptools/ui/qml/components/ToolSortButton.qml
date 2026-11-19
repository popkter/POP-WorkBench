import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

PrimaryButton {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    required property var controller
    property color backgroundColor: "transparent"
    property color hoverColor: _visualPalette.primaryContainerHover
    property bool popupAbove: false
    property bool cycleOnClick: false
    readonly property bool menuOpen: sortPopup.visible
    readonly property var options: [
        { "label": "按添加时间", "value": "added_time", "icon": "schedule" },
        { "label": "按名称", "value": "name", "icon": "sort_by_alpha" },
        { "label": "按使用频率", "value": "usage", "icon": "trending_up" },
        { "label": "自定义排序", "value": "custom", "icon": "drag_indicator" }
    ]
    readonly property int modeIndex: Math.max(0,
        options.findIndex(option => option.value === root.controller.toolSortMode))

    implicitWidth: 40
    implicitHeight: 40
    compact: true
    text: "排序：" + root.controller.toolSortModeLabel
    iconName: cycleOnClick ? options[modeIndex].icon : "sort"
    showHoverTips: false
    glyphSize: 24
    tonal: true
    foregroundColor: _visualPalette.primary
    border.width: 0
    radius: Theme.radiusSmall
    color: root.hovered || sortPopup.opened
           ? root.hoverColor : root.backgroundColor
    onClicked: cycleOnClick ? root.cycleMode() : root.openMenu()
    Accessible.role: Accessible.Button
    Accessible.name: "排序：" + root.controller.toolSortModeLabel
    Accessible.onPressAction: root.clicked()

    function cycleMode() {
        root.controller.setToolSortMode(options[(modeIndex + 1) % options.length].value)
    }

    function closeMenu() { sortPopup.close() }

    function openMenu() {
        if (cycleOnClick) return
        var point = root.mapToItem(Overlay.overlay, 0, root.height)
        sortPopup.x = Math.max(12, Math.min(point.x + root.width - sortPopup.width,
                                           Overlay.overlay.width - sortPopup.width - 12))
        sortPopup.y = root.popupAbove ? point.y - root.height - sortPopup.height - 6
            : Math.max(12, Math.min(point.y + 6,
                                   Overlay.overlay.height - sortPopup.height - 12))
        sortPopup.open()
    }

    Popup {
        id: sortPopup
        popupType: _visualPalette.glassMode ? Popup.Item : root.popupAbove ? Popup.Window : Popup.Item
        parent: Overlay.overlay
        width: 188
        height: contentColumn.implicitHeight + 16
        padding: Theme.space8
        modal: false
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: AppPopupSurface {
            minimumOpacity: Theme.glassMaterial.tooltipOpacity === undefined
                ? 0.97 : Theme.glassMaterial.tooltipOpacity
        }

        contentItem: ColumnLayout {
            id: contentColumn
            spacing: Theme.space4
            Repeater {
                model: root.options
                delegate: Rectangle {
                    id: optionRow
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.preferredHeight: 44
                    radius: Theme.radiusMedium
                    color: modelData.value === root.controller.toolSortMode
                           ? _visualPalette.primaryContainer
                           : (optionMouse.containsMouse ? _visualPalette.surfaceContainerHigh : "transparent")
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.space12
                        anchors.rightMargin: Theme.space12
                        spacing: Theme.space12
                        MaterialIcon {
                            icon: optionRow.modelData.icon
                            iconSize: 20
                            color: optionRow.modelData.value === root.controller.toolSortMode
                                   ? _visualPalette.primary : _visualPalette.textSecondary
                        }
                        Text {
                            Layout.fillWidth: true
                            text: optionRow.modelData.label
                            color: _visualPalette.textPrimary
                            font.pixelSize: Theme.fontSupporting
                        }
                        MaterialIcon {
                            visible: optionRow.modelData.value === root.controller.toolSortMode
                            icon: "check"
                            iconSize: 19
                            color: _visualPalette.primary
                        }
                    }
                    MouseArea {
                        id: optionMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            root.controller.setToolSortMode(optionRow.modelData.value)
                            sortPopup.close()
                        }
                    }
                }
            }
        }
    }
}
