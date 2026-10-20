import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root
    objectName: "userGuideDialog"
    required property var controller
    required property var parentWindow
    property int sectionIndex: 0
    property string copyStatus: ""
    readonly property var sections: controller.userGuideSections
    readonly property var section: sections[sectionIndex]
    width: Math.min(860, parentWindow.width - Theme.space24)
    height: Math.min(780, parentWindow.height - Theme.space24)
    closePolicy: Popup.CloseOnEscape
    onAboutToShow: { sectionIndex = 0; copyStatus = ""; guideScroll.contentY = 0 }
    onAboutToHide: controller.markUserGuideSeen()
    onSectionIndexChanged: { guideScroll.contentY = 0; copyStatus = "" }
    function finishGuide() { close() }
    function copied(text) {
        controller.copyGuideText(text)
        copyStatus = "已复制，可粘贴到脚本编辑器"
        copyTimer.restart()
    }
    Timer { id: copyTimer; interval: 3000; onTriggered: root.copyStatus = "" }
    contentItem: ColumnLayout {
        spacing: Theme.space16
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.space12
            DialogHeading {
                Layout.fillWidth: true
                title: "使用手册"
                description: "了解功能、编写脚本，以及管理运行环境"
                iconName: "menu_book"
            }
            DialogActionButton {
                objectName: "closeUserGuideButton"
                Layout.preferredWidth: Theme.controlHeight
                Layout.preferredHeight: Theme.controlHeight
                compact: true
                text: "关闭使用手册"; iconName: "close"
                glyphSize: Theme.iconMedium
                tonal: true
                foregroundColor: Theme.textSecondary
                border.width: 0
                radius: height / 2
                color: hovered ? Theme.surfaceContainerHigh : "transparent"
                Accessible.name: "关闭使用手册"
                onClicked: root.finishGuide()
            }
        }
        Flow {
            Layout.fillWidth: true; spacing: Theme.space8
            Repeater {
                model: root.sections
                delegate: DialogActionButton {
                    required property var modelData
                    required property int index
                    objectName: "guideSection_" + modelData.id
                    text: modelData.title; iconName: modelData.icon
                    implicitHeight: Theme.controlHeightSmall; labelFontSize: Theme.fontSupporting
                    tonal: true
                    color: root.sectionIndex === index ? Theme.primaryContainer : Theme.surfaceContainerLow
                    foregroundColor: root.sectionIndex === index ? Theme.primaryText : Theme.textSecondary
                    onClicked: root.sectionIndex = index
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        Flickable {
            id: guideScroll
            objectName: "guideScroll"
            Layout.fillWidth: true; Layout.fillHeight: true; clip: true
            contentWidth: width; contentHeight: guideContent.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { }
            ColumnLayout {
                id: guideContent
                width: guideScroll.width - Theme.space16; spacing: Theme.space12
                Repeater {
                    model: root.section ? root.section.cards : []
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: cardContent.implicitHeight + Theme.space32
                        radius: Theme.radiusMedium; color: Theme.surfaceContainer; border.color: Theme.outlineVariant
                        ColumnLayout {
                            id: cardContent
                            anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.space16 }
                            spacing: Theme.space8
                            RowLayout {
                                Layout.fillWidth: true; spacing: Theme.space8
                                MaterialIcon { visible: !!modelData.icon; icon: modelData.icon || "info"; iconSize: 20; color: Theme.primary }
                                Text {
                                    Layout.fillWidth: true; text: modelData.title
                                    color: Theme.textPrimary; font.pixelSize: Theme.fontTitleSmall
                                    font.weight: Font.DemiBold; wrapMode: Text.Wrap
                                }
                                DialogActionButton {
                                    visible: !!modelData.code
                                    text: "复制"; iconName: "content_copy"; tonal: true; implicitHeight: Theme.controlHeightSmall
                                    onClicked: root.copied(modelData.code)
                                }
                            }
                            Text {
                                Layout.fillWidth: true; text: modelData.body || ""
                                textFormat: Text.PlainText; wrapMode: Text.Wrap
                                color: Theme.textSecondary; font.pixelSize: Theme.fontBody
                            }
                            TextArea {
                                Layout.fillWidth: true; visible: !!modelData.code
                                text: modelData.code || ""; readOnly: true; selectByMouse: true
                                wrapMode: TextEdit.Wrap; textFormat: TextEdit.PlainText
                                font.family: "Cascadia Mono"; font.pixelSize: Theme.fontCode
                                color: Theme.consoleText; padding: Theme.space12
                                background: Rectangle { radius: Theme.radiusConsole; color: Theme.consoleBackground }
                            }
                        }
                    }
                }
                Loader {
                    Layout.fillWidth: true
                    active: root.section && root.section.id === "syntax"
                    sourceComponent: GuideTemplatePreview {
                        controller: root.controller
                        onCopyRequested: function(text) { root.copied(text) }
                    }
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.outlineVariant }
        RowLayout {
            Layout.fillWidth: true; spacing: Theme.space12
            Text {
                objectName: "guideCopyStatus"
                Layout.fillWidth: true
                text: root.copyStatus || "可随时从「设置 → 关于 → 用户手册」重新打开"
                color: root.copyStatus ? Theme.success : Theme.textSecondary
                font.pixelSize: Theme.fontCaption; wrapMode: Text.Wrap
            }
            DialogActionButton {
                objectName: "finishUserGuideButton"
                primaryAction: true
                text: "我知道了"; iconName: ""; implicitHeight: Theme.controlHeight
                onClicked: root.finishGuide()
            }
        }
    }
}
