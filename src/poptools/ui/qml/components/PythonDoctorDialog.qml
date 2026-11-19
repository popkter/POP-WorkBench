import QtQuick
import QtQuick.Window
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    required property var controller
    required property var parentWindow
    property string message: ""
    property string packageNames: ""
    property string installStatus: ""
    property bool installing: false
    signal pluginManagementRequested()

    width: Math.min(Theme.dialogWidth, parentWindow.width - 24)
    height: Math.min(460, parentWindow.height - 24)
    anchors.centerIn: Overlay.overlay
    modal: true
    closePolicy: root.installing ? Popup.NoAutoClose : Popup.CloseOnEscape

    contentItem: ColumnLayout {
        spacing: Theme.space16
        DialogHeading {
            Layout.fillWidth: true
            title: "检查 Python 依赖"
            description: "检查运行环境并安装脚本所需的依赖"
            iconName: "fact_check"
        }
        DesktopScrollView {
            id: detailsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            contentWidth: availableWidth
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
            ScrollBar.vertical.policy: ScrollBar.AsNeeded
            ColumnLayout {
                width: detailsScroll.availableWidth
                spacing: Theme.space12
                DialogActionButton {
                    text: "打开插件管理"
                    iconName: "extension"
                    visible: root.message.indexOf("插件") >= 0
                    onClicked: { root.close(); root.pluginManagementRequested() }
                }
                Text {
                    Layout.fillWidth: true
                    text: root.message
                    textFormat: Text.PlainText
                    color: _visualPalette.textPrimary
                    font.pixelSize: Theme.fontBody
                    wrapMode: Text.Wrap
                }
                Text {
                    text: "Python 环境目录"
                    color: _visualPalette.textSecondary
                    font.pixelSize: Theme.fontSupporting
                }
                AppTextField {
                    id: environmentField
                    Layout.fillWidth: true
                    readOnly: true
                    text: root.controller.pythonEnvironmentDirectory
                    font.family: "Cascadia Mono"
                    font.pixelSize: Theme.fontCaption
                    AppTextEditMenu { target: environmentField }
                    background: Rectangle {
                        radius: Theme.radiusControl
                        color: _visualPalette.glassMode ? "transparent" : _visualPalette.surfaceContainer
                        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.surfaceContainer; z: -0.5 }
                        border.color: _visualPalette.outlineVariant
                    }
                }
                Text {
                    visible: root.packageNames.length > 0
                    text: "待安装依赖"
                    color: _visualPalette.textSecondary
                    font.pixelSize: Theme.fontSupporting
                }
                TextArea {
                    Layout.fillWidth: true
                    visible: root.packageNames.length > 0
                    readOnly: true
                    text: root.packageNames
                    padding: Theme.space12
                    color: _visualPalette.textPrimary
                    font.family: "Cascadia Mono"
                    font.pixelSize: Theme.fontCaption
                    wrapMode: TextEdit.Wrap
                    selectByMouse: true
                    background: Rectangle {
                        radius: Theme.radiusControl
                        color: _visualPalette.glassMode ? "transparent" : _visualPalette.surfaceContainer
                        GlassSurface { anchors.fill: parent; cornerRadius: parent.radius; tintColor: _visualPalette.surfaceContainer; z: -0.5 }
                        border.color: _visualPalette.outlineVariant
                    }
                }
                Text {
                    Layout.fillWidth: true
                    visible: root.packageNames.length > 0
                    text: "确认后开始安装，可随时取消。"
                    color: _visualPalette.textSecondary
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    visible: root.installStatus.length > 0
                    text: root.installStatus
                    textFormat: Text.PlainText
                    color: root.installStatus.indexOf("失败") >= 0 ? _visualPalette.errorColor : _visualPalette.textSecondary
                    font.pixelSize: Theme.fontSupporting
                    wrapMode: Text.Wrap
                }
            }
        }
        Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: _visualPalette.outlineVariant }
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space8
            Item { Layout.fillWidth: true }
            DialogActionButton {
                text: "取消"
                onClicked: {
                    if (root.installing)
                        root.controller.cancelPythonDependencyInstall()
                    else
                        root.close()
                }
            }
            DialogActionButton {
                visible: root.packageNames.length > 0
                primaryAction: true
                text: root.installing ? "安装中…" : "确认安装"
                iconName: root.installing ? "hourglass_top" : "download"
                enabled: !root.installing
                onClicked: root.installing = root.controller.installPythonDependencies(root.packageNames)
            }
        }
    }
}
