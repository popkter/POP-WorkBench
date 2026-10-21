import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root
    required property var controller
    required property var parentWindow

    readonly property real maximumDialogHeight: Math.min(600, parentWindow.height - 24)
    readonly property real availableDialogChromeHeight: 200
    readonly property real maximumReleaseCardHeight: Math.max(
        76, maximumDialogHeight - availableDialogChromeHeight)

    width: Math.min(620, parentWindow.width - 24)
    height: controller.state === "available"
            ? Math.min(maximumDialogHeight,
                       Math.max(300, releaseCard.implicitHeight
                                + availableDialogChromeHeight))
            : Math.min(340, parentWindow.height - 24)
    anchors.centerIn: Overlay.overlay
    modal: true
    padding: Theme.space24
    closePolicy: controller.state === "downloading"
                 || controller.state === "downloaded"
                 || controller.state === "installing"
                 ? Popup.NoAutoClose : Popup.CloseOnEscape

    contentItem: ColumnLayout {
        spacing: Theme.space16

        DialogHeading {
            Layout.fillWidth: true
            iconName: root.controller.state === "downloaded" ? "download_done" : "system_update"
            title: root.controller.state === "downloading" ? "正在下载更新"
                   : root.controller.state === "downloaded" ? "更新已准备好"
                   : root.controller.state === "installing" ? "正在安装更新"
                   : root.controller.state === "error" ? "更新遇到问题" : "发现新版本"
            description: root.controller.availableVersion.length > 0
                         ? "当前 " + root.controller.currentVersion + "  →  最新 " + root.controller.availableVersion : ""
            destructive: root.controller.state === "error"
        }

        Rectangle {
            id: releaseCard
            visible: root.controller.state === "available"
            Layout.fillWidth: true
            Layout.preferredHeight: implicitHeight
            Layout.minimumHeight: 0
            Layout.fillHeight: true
            implicitHeight: Math.min(root.maximumReleaseCardHeight,
                                     releaseContent.implicitHeight + 32)
            radius: Theme.radiusMedium
            color: Theme.surfaceContainer
            border.color: Theme.outlineVariant
            ColumnLayout {
                id: releaseContent
                anchors.fill: parent
                anchors.margins: Theme.space16
                spacing: Theme.space8
                Text {
                    Layout.fillWidth: true
                    text: root.controller.releaseName
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontComponentTitle
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }

                DesktopScrollView {
                    id: releaseNotesScroll
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredHeight: releaseNotesText.implicitHeight
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded

                    Text {
                        id: releaseNotesText
                        width: releaseNotesScroll.availableWidth
                        text: root.controller.releaseNotes
                            + (root.controller.runtimeUpdateNotice
                               ? "\n\n" + root.controller.runtimeUpdateNotice : "")
                        textFormat: Text.MarkdownText
                        wrapMode: Text.Wrap
                        color: Theme.textPrimary
                        linkColor: Theme.primary
                        font.pixelSize: Theme.fontBody
                        onLinkActivated: function(link) {
                            Qt.openUrlExternally(link)
                        }
                    }
                }

                Text {
                    visible: root.controller.releasePageUrl.length > 0
                    text: "在 GitHub 查看此版本"
                    color: Theme.primary
                    font.pixelSize: Theme.fontSupporting
                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: Qt.openUrlExternally(root.controller.releasePageUrl)
                    }
                }
            }
        }

        ColumnLayout {
            visible: root.controller.state === "downloading"
                     || root.controller.state === "downloaded"
                     || root.controller.state === "installing"
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 0
            spacing: 6
            Item { Layout.fillHeight: true }
            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 44
                MaterialIcon {
                    anchors.centerIn: parent
                    icon: root.controller.state === "downloaded" ? "check_circle" : "download"
                    iconSize: 44
                    color: root.controller.state === "downloaded" ? Theme.success : Theme.primary
                }
            }
            Text {
                Layout.fillWidth: true
                text: root.controller.status
                color: Theme.textPrimary
                font.pixelSize: Theme.fontComponentTitle
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.Wrap
            }
            AppProgressBar {
                visible: root.controller.state === "downloading"
                Layout.fillWidth: true
                from: 0
                to: 100
                value: root.controller.downloadProgress
                indeterminate: root.controller.totalSize.length === 0
            }
            Text {
                visible: root.controller.state === "downloading"
                         && root.controller.downloadedSize.length > 0
                Layout.fillWidth: true
                text: root.controller.totalSize.length > 0
                      ? root.controller.downloadedSize + " / " + root.controller.totalSize
                      : root.controller.downloadedSize
                color: Theme.textSecondary
                font.pixelSize: Theme.fontSupporting
                horizontalAlignment: Text.AlignHCenter
            }
            Item { Layout.fillHeight: true }
        }

        Rectangle {
            visible: root.controller.state === "error"
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radiusMedium
            color: Theme.errorContainer
            RowLayout {
                anchors.fill: parent
                anchors.margins: 18
                spacing: Theme.space12
                MaterialIcon { icon: "error"; iconSize: 28; color: Theme.errorColor }
                DialogMessage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    text: root.controller.status
                    foregroundColor: Theme.textPrimary
                }
            }
        }

        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true
            spacing: 10
            Item { Layout.fillWidth: true }
            DialogActionButton {
                visible: root.controller.state === "available"
                implicitWidth: 112; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: "下次提醒"; iconName: "schedule"; tonal: true
                onClicked: root.close()
            }
            DialogActionButton {
                visible: root.controller.state === "available"
                implicitWidth: 128; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: "跳过此版本"; iconName: "skip_next"; tonal: true
                onClicked: {
                    root.controller.skipVersion()
                    root.close()
                }
            }
            DialogActionButton {
                visible: root.controller.state === "available"
                implicitWidth: 122; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                primaryAction: true
                text: "立即更新"; iconName: "download"
                onClicked: root.controller.downloadUpdate()
            }
            DialogActionButton {
                visible: root.controller.state === "downloading"
                implicitWidth: 120; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: "取消下载"; iconName: "close"; tonal: true
                onClicked: root.controller.cancelDownload()
            }
            DialogActionButton {
                visible: root.controller.state === "downloaded"
                implicitWidth: 116; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: "稍后安装"; iconName: "schedule"; tonal: true
                onClicked: {
                    if (root.controller.installLater())
                        root.close()
                }
            }
            DialogActionButton {
                visible: root.controller.state === "downloaded"
                implicitWidth: 150; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                primaryAction: true
                text: "安装并重启"; iconName: "restart_alt"
                onClicked: root.controller.installAndRestart()
            }
            DialogActionButton {
                visible: root.controller.state === "error"
                implicitWidth: 104; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                text: "关闭"; iconName: "close"; tonal: true
                onClicked: root.close()
            }
            DialogActionButton {
                visible: root.controller.state === "error"
                implicitWidth: 112; implicitHeight: Theme.controlHeight; radius: Theme.radiusControl
                primaryAction: true
                text: "重试"; iconName: "refresh"
                onClicked: root.controller.retryUpdate()
            }
        }
    }
}
