import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

RowLayout {
    id: root
    property var backend: null
    readonly property bool popupVisible: screenPopup.opened
    property string lastSelectedId: ""
    property string lastSerial: ""
    spacing: 4
    implicitWidth: 190
    implicitHeight: Theme.captionActionHeight
    enabled: !!backend && backend.deviceAvailable

    function syncSelection(force) {
        const value = backend ? backend.selectedId : "0"
        const serial = backend ? backend.deviceSerial : ""
        if (force || lastSelectedId !== value || lastSerial !== serial) {
            lastSelectedId = value
            lastSerial = serial
            displayInput.text = value
        }
    }
    function openMenu() {
        const point = root.mapToItem(Overlay.overlay, 0, root.height)
        screenPopup.x = Math.max(8, Math.min(point.x, Overlay.overlay.width - screenPopup.width - 8))
        screenPopup.y = point.y + 6
        screenPopup.open()
    }
    Component.onCompleted: {
        syncSelection()
        if (visible && backend) backend.setEnabled(true)
    }
    Component.onDestruction: if (visible && backend) backend.setEnabled(false)
    onVisibleChanged: {
        if (backend) backend.setEnabled(visible)
        if (!visible) screenPopup.close()
    }
    Connections {
        target: root.backend
        function onChanged() { root.syncSelection() }
    }
    Text {
        text: "屏幕"
        color: Theme.chromeForeground
        font.pixelSize: Theme.fontSupporting
    }
    AppTextField {
        id: displayInput
        objectName: "displayIdInput"
        Layout.fillWidth: true
        Layout.minimumWidth: 46
        Layout.preferredHeight: Theme.captionActionHeight
        leftPadding: 6
        rightPadding: 6
        font.pixelSize: Theme.fontSupporting
        Accessible.name: "屏幕 displayId，输入后按 Enter 切换"
        selectByMouse: true
        validator: IntValidator { bottom: 0; top: 2147483647 }
        onAccepted: {
            if (root.backend && root.backend.selectDisplay(text))
                root.syncSelection(true)
        }
    }
    PrimaryButton {
        objectName: "displayListButton"
        text: "选择屏幕"
        iconName: "expand_more"
        compact: true
        Layout.preferredWidth: 28
        Layout.preferredHeight: Theme.captionActionHeight
        glyphSize: 18
        color: hovered ? Theme.navigationHover : "transparent"
        foregroundColor: Theme.chromeForeground
        border.width: 0
        radius: Theme.radiusTiny
        onClicked: root.openMenu()
    }
    Popup {
        id: screenPopup
        objectName: "displaySelectorPopup"
        parent: Overlay.overlay
        width: Math.min(320, Overlay.overlay ? Overlay.overlay.width - 16 : 320)
        padding: 8
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        background: AppPopupSurface { }
        contentItem: ColumnLayout {
            spacing: 6
            RowLayout {
                Layout.fillWidth: true
                Text {
                    Layout.fillWidth: true
                    text: root.backend && root.backend.loading ? "正在查询屏幕…" : "设备屏幕"
                    font.pixelSize: Theme.fontSupporting
                    color: Theme.textPrimary
                }
                PrimaryButton {
                    text: "刷新屏幕列表"; iconName: "refresh"; compact: true
                    Layout.preferredWidth: 28; Layout.preferredHeight: 28; glyphSize: 18
                    color: hovered ? Theme.popupHover : "transparent"
                    foregroundColor: Theme.textSecondary
                    border.width: 0
                    enabled: !!root.backend && !root.backend.loading
                    onClicked: root.backend.refresh()
                }
            }
            Text {
                Layout.fillWidth: true
                visible: text.length > 0
                text: root.backend ? root.backend.error : ""
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.Wrap
            }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(contentHeight, 220)
                clip: true
                model: root.backend ? root.backend.displays : []
                delegate: ItemDelegate {
                    id: displayRow
                    required property var modelData
                    width: ListView.view.width
                    height: 36
                    text: modelData.label
                    highlighted: root.backend && modelData.id === root.backend.selectedId
                    contentItem: Text {
                        text: displayRow.text
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSupporting
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: displayRow.highlighted ? Theme.popupSelected
                            : displayRow.hovered ? Theme.popupHover : "transparent"
                    }
                    onClicked: {
                        root.backend.selectDisplay(modelData.id)
                        root.syncSelection(true)
                        screenPopup.close()
                    }
                }
                ScrollIndicator.vertical: ScrollIndicator { }
            }
            Text {
                Layout.fillWidth: true
                text: "也可直接输入 displayId，按 Enter 确认"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
            }
        }
    }
}
