import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

AppDialog {
    id: root
    objectName: "runtimeEnvironmentDialog"
    required property var backend
    property string pluginId: ""
    property string pluginName: ""
    property bool saving: false
    property string errorText: ""
    parent: Overlay.overlay
    compactLayout: true
    width: Math.min(560, parent.width - Theme.space24)
    height: Math.min(body.implicitHeight + topPadding + bottomPadding,
                     parent.height - Theme.space24)
    closePolicy: saving ? Popup.NoAutoClose : Popup.CloseOnEscape

    function configure(row) {
        pluginId = row.id
        pluginName = row.name
        source.currentIndex = row.managed ? 0 : 1
        executable.text = row.customExecutable || ""
        scrcpy.text = row.customScrcpy || ""
        errorText = ""
        saving = false
        open()
    }

    Connections {
        target: root.backend
        ignoreUnknownSignals: true
        function onCompleted(plugin, success, message) {
            if (!root.saving || plugin !== root.pluginId)
                return
            root.saving = false
            if (success)
                root.close()
            else
                root.errorText = message
        }
    }

    contentItem: Flickable {
        contentHeight: body.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        ColumnLayout {
            id: body
            width: parent.width
            spacing: Theme.space12
            DialogHeading { Layout.fillWidth: true; title: root.pluginName + " 运行环境" }
            AppComboBox {
                id: source
                objectName: "runtimeSource"
                Layout.fillWidth: true
                model: ["应用管理", "本地环境"]
                enabled: !root.saving
            }
            Text {
                Layout.fillWidth: true
                text: source.currentIndex === 0
                    ? "由应用提供安装、更新和卸载。升级时保留相同版本的运行时；Python 版本变化时自动迁移依赖，成功后再切换。"
                    : "直接使用所选环境。应用不更新或卸载这些文件，升级应用也会保留此选择。"
                color: Theme.textSecondary
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.fillWidth: true
                visible: source.currentIndex === 1
                AppTextField {
                    id: executable
                    objectName: "runtimeExecutable"
                    Layout.fillWidth: true
                    enabled: !root.saving
                    placeholderText: root.pluginId === "python" ? "python.exe 的完整路径（支持虚拟环境）"
                        : root.pluginId === "powershell" ? "pwsh.exe 的完整路径" : "adb.exe 的完整路径"
                }
                DialogActionButton {
                    text: "浏览"; enabled: !root.saving
                    onClicked: {
                        const path = root.backend.browseExecutable(executable.text)
                        if (path.length > 0) executable.text = path
                    }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                visible: source.currentIndex === 1 && root.pluginId === "android"
                AppTextField {
                    id: scrcpy
                    objectName: "runtimeScrcpy"
                    Layout.fillWidth: true
                    enabled: !root.saving
                    placeholderText: "scrcpy.exe 的完整路径（可选，投屏和录屏需要）"
                }
                DialogActionButton {
                    text: "浏览"; enabled: !root.saving
                    onClicked: {
                        const path = root.backend.browseExecutable(scrcpy.text)
                        if (path.length > 0) scrcpy.text = path
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                visible: root.errorText.length > 0
                text: root.errorText
                color: Theme.errorColor
                font.pixelSize: Theme.fontCaption
                wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                DialogActionButton { text: "取消"; enabled: !root.saving; onClicked: root.close() }
                DialogActionButton {
                    objectName: "saveRuntimeEnvironment"
                    text: root.saving ? "正在检测…" : "检测并保存"
                    enabled: !root.saving
                    onClicked: {
                        root.errorText = ""
                        root.saving = root.backend.configureRuntime(root.pluginId,
                            source.currentIndex === 0 ? "managed" : "custom", executable.text, scrcpy.text)
                        if (!root.saving) {
                            const row = root.backend.plugins.find(item => item.id === root.pluginId)
                            root.errorText = row ? row.status : "请先结束相关任务或等待其他操作完成"
                        }
                    }
                }
            }
        }
    }
}
