pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "../theme"

Rectangle {
    id: root
    required property var controller
    required property var updateBackend
    property var terminalBackend: null
    signal pluginManageRequested()
    signal terminalEnableRequested()
    signal userHelpRequested()
    color: Theme.workspaceBackground

    function scrollToBottom() {
        settingsFlick.contentY = Math.max(0, settingsFlick.contentHeight - settingsFlick.height)
    }

    component LinkButton: PrimaryButton {
        iconName: ""
        Layout.fillWidth: true
        Layout.minimumWidth: 0
        Layout.preferredHeight: 24
        implicitWidth: 96
        tonal: true; border.width: 0
        color: hovered ? Theme.surfaceContainer : "transparent"
        foregroundColor: Theme.secondaryText
        labelFontSize: Theme.fontSupporting; labelFontWeight: Font.Normal
        glyphSize: 14; contentSpacing: 6; contentHorizontalPadding: 0; contentFillWidth: true
    }

    component PluginRow: Rectangle {
        id: plugin
        property string label: ""
        property string actionLabel: ""
        property string hint: ""
        property bool available: true
        property real progress: 0
        signal activated()
        Layout.preferredHeight: 42
        radius: Theme.radiusSmall; color: Theme.surfaceContainerLow; border.color: Theme.outline
        Rectangle { anchors.left: parent.left; anchors.top: parent.top; anchors.bottom: parent.bottom; width: parent.width * plugin.progress; color: Theme.surfaceContainerHigh; radius: parent.radius }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: 14; anchors.rightMargin: 9
            Text { Layout.fillWidth: true; text: plugin.label; font.pixelSize: Theme.fontSupporting; font.weight: Font.DemiBold; color: Theme.secondaryText; elide: Text.ElideRight }
            PrimaryButton { implicitWidth: 62; implicitHeight: 24; iconName: ""; text: plugin.actionLabel; labelFontSize: Theme.fontCaption; labelFontWeight: Font.Normal; enabled: plugin.available; onClicked: plugin.activated(); HoverTips { visible: parent.hovered && plugin.hint.length > 0; text: plugin.hint } }
        }
    }

    component Card: Rectangle {
        color: Theme.surfaceContainerLow
        border.color: Theme.outlineVariant
        border.width: 1
        radius: Theme.radiusCard
    }

    component SectionTitle: RowLayout {
        id: sectionHeader
        property string iconName: "settings"
        property string title: ""
        property string description: ""
        spacing: Theme.space12
        MaterialIcon {
            icon: parent.iconName
            iconSize: 24
            color: Theme.primary
            Layout.preferredWidth: 28
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text { text: sectionHeader.title; color: Theme.textPrimary; font.pixelSize: Theme.fontSectionTitle; font.weight: Font.Bold }
            Text { text: sectionHeader.description; color: Theme.textSecondary; font.pixelSize: Theme.fontSupporting }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.workspaceInset
        anchors.rightMargin: Theme.workspaceInset
        anchors.topMargin: Theme.workspaceInset
        anchors.bottomMargin: Theme.workspaceInset
        spacing: Theme.space12

        Flickable {
            id: settingsFlick
            objectName: "settingsScroll"
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: settingsGrid.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            acceptedButtons: Qt.NoButton

            GridLayout {
                id: settingsGrid
                width: parent.width
                columns: width >= Theme.settingsTwoColumnWidth ? 2 : 1
                columnSpacing: Theme.space12
                rowSpacing: Theme.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: Theme.space12

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: appearanceContent.implicitHeight + Theme.space24
                        ColumnLayout {
                            id: appearanceContent
                            anchors.fill: parent
                            anchors.margins: Theme.space12
                            spacing: 10
                            SectionTitle { Layout.fillWidth: true; iconName: "palette"; title: "外观"; description: "选择应用的外观主题" }
                            RowLayout {
                                Layout.fillWidth: true
                                Layout.rightMargin: 0
                                spacing: Theme.space12
                                Repeater {
                                    model: [
                                        { label: "浅色", value: "light", icon: "light_mode" },
                                        { label: "深色", value: "dark", icon: "dark_mode" },
                                        { label: "跟随系统", value: "system", icon: "computer" }
                                    ]
                                    delegate: Rectangle {
                                        id: themeChoice
                                        required property var modelData
                                        objectName: "themeChoice_" + modelData.value
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 48
                                        Layout.minimumHeight: 48
                                        Layout.maximumHeight: 48
                                        radius: Theme.radiusMedium
                                        color: root.controller.themeMode === modelData.value ? Theme.primaryContainer : Theme.surfaceContainerLow
                                        border.width: root.controller.themeMode === modelData.value ? 2 : 1
                                        border.color: root.controller.themeMode === modelData.value ? Theme.primary : Theme.outline
                                        Row {
                                            anchors.centerIn: parent
                                            spacing: Theme.space8
                                            MaterialIcon { anchors.verticalCenter: parent.verticalCenter; icon: themeChoice.modelData.icon; iconSize: 20; color: root.controller.themeMode === themeChoice.modelData.value ? Theme.primary : Theme.textSecondary }
                                            Text { anchors.verticalCenter: parent.verticalCenter; text: themeChoice.modelData.label; color: root.controller.themeMode === themeChoice.modelData.value ? Theme.primary : Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold }
                                        }
                                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: root.controller.saveThemeMode(themeChoice.modelData.value) }
                                    }
                                }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: launcherSettings.implicitHeight + Theme.space24
                        ColumnLayout {
                            id: launcherSettings
                            anchors.fill: parent
                            anchors.margins: Theme.space12
                            spacing: Theme.space12
                            SectionTitle { Layout.fillWidth: true; iconName: "dock"; title: "后台悬浮入口"; description: "切换到其他应用时，在屏幕右侧显示快捷入口" }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { Layout.fillWidth: true; text: "启用悬浮刘海"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody }
                                ToggleControl {
                                    objectName: "floatingLauncherToggle"
                                    checked: root.controller.floatingLauncherEnabled
                                    onToggled: function(value) { root.controller.saveFloatingLauncherEnabled(value) }
                                }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: directoryContent.implicitHeight + Theme.space24
                        ColumnLayout {
                            id: directoryContent
                            anchors.fill: parent
                            anchors.margins: Theme.space12
                            spacing: 10
                            SectionTitle { Layout.fillWidth: true; iconName: "folder"; title: "脚本目录"; description: "设置脚本文件的默认存储目录" }
                            PrimaryButton {
                                Layout.fillWidth: true; Layout.preferredHeight: 42
                                radius: Theme.radiusSmall; tonal: true; color: Theme.surfaceContainerLow
                                border.color: Theme.outline
                                text: root.controller.configurationDirectory
                                iconName: ""
                                foregroundColor: Theme.textSecondary
                                labelFontSize: Theme.fontSupporting
                                labelFontWeight: Font.Normal
                                glyphSize: 18
                                contentSpacing: Theme.space8
                                contentFillWidth: true
                                contentHorizontalPadding: 14
                                labelElide: Text.ElideMiddle
                                onClicked: root.controller.openConfigurationDirectory()
                            }
                            Text { text: "自定义脚本、预设和相关数据将保存在此目录下。"; color: Theme.textSecondary; font.pixelSize: Theme.fontCaption }
                            RowLayout {
                                Layout.fillWidth: true; spacing: Theme.space12
                                PrimaryButton { Layout.fillWidth: true; implicitWidth: 0; implicitHeight: 48; tonal: true; color: Theme.surfaceContainerLow; border.color: Theme.darkMode ? Theme.outline : "#333333"; text: "批量导入自定义脚本"; iconName: ""; onClicked: root.controller.importConfiguration() }
                                PrimaryButton { Layout.fillWidth: true; implicitWidth: 0; implicitHeight: 48; text: "批量导出自定义脚本"; iconName: ""; onClicked: root.controller.exportConfiguration() }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: updateContent.implicitHeight + Theme.space24
                        ColumnLayout {
                            id: updateContent
                            anchors.fill: parent; anchors.margins: Theme.space12; spacing: Theme.space12
                            RowLayout {
                                Layout.fillWidth: true
                                SectionTitle { Layout.fillWidth: true; iconName: "autorenew"; title: "检查更新"; description: "检查新版本并保持应用为最新" }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout { Layout.fillWidth: true; Layout.preferredWidth: (settingsFlick.width - 16) / settingsGrid.columns - 96; spacing: 2
                                    Text { text: "自动检查更新"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold }
                                    Text { text: "定期检查新版本，在有新版本时通知我"; color: Theme.textSecondary; font.pixelSize: Theme.fontCaption }
                                }
                                ToggleControl {
                                    checked: root.updateBackend.updateCheckFrequency !== "never"
                                    onToggled: function(value) { root.updateBackend.setUpdateCheckFrequency(value ? "weekly" : "never") }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                ColumnLayout {
                                    Layout.fillWidth: true; Layout.preferredWidth: (settingsFlick.width - 16) / settingsGrid.columns - 96; spacing: 2
                                    Text { text: "接受 Beta 版本更新"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold }
                                    Text { text: "接收测试版本，提前体验新功能"; color: Theme.textSecondary; font.pixelSize: Theme.fontCaption }
                                }
                                ToggleControl {
                                    enabled: root.updateBackend.canChangeUpdateChannel
                                    opacity: enabled ? 1 : 0.5
                                    checked: root.updateBackend.prereleaseUpdatesEnabled
                                    onToggled: function(value) { root.updateBackend.setPrereleaseUpdatesEnabled(value) }
                                }
                            }
                            RowLayout {
                                Layout.fillWidth: true
                                Text { text: "检查更新频率"; color: Theme.textPrimary; font.pixelSize: Theme.fontBody }
                                Rectangle {
                                    objectName: "updateFrequencyChoice"
                                    Layout.fillWidth: true; Layout.preferredWidth: 400; Layout.minimumWidth: 0; Layout.preferredHeight: 32
                                    radius: Theme.radiusSmall; color: Theme.surfaceContainerLow; border.color: Theme.outline
                                    RowLayout {
                                        anchors.fill: parent; anchors.margins: 2; spacing: 0
                                        Repeater {
                                            model: [{label: "手动更新", value: "never"}, {label: "每天一次", value: "daily"}, {label: "每周一次", value: "weekly"}, {label: "启动时检查", value: "startup"}]
                                            delegate: PrimaryButton {
                                                required property var modelData
                                                objectName: "updateFrequency_" + modelData.value
                                                Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.preferredWidth: 0; Layout.fillHeight: true
                                                text: modelData.label; iconName: ""; labelFontSize: Theme.fontCaption; labelFontWeight: Font.Normal
                                                tonal: true; border.width: 0; contentHorizontalPadding: 2
                                                color: root.updateBackend.updateCheckFrequency === modelData.value ? Theme.listSelected : "transparent"
                                                foregroundColor: root.updateBackend.updateCheckFrequency === modelData.value ? Theme.primary : Theme.textPrimary
                                                onClicked: root.updateBackend.setUpdateCheckFrequency(modelData.value)
                                            }
                                        }
                                    }
                                }
                            }
                            PrimaryButton {
                                objectName: "checkUpdateButton"
                                Layout.fillWidth: true
                                implicitHeight: Theme.controlHeightLarge
                                text: root.updateBackend.state === "checking" ? "检查中…" : "立即检查"
                                iconName: "autorenew"
                                iconSpinning: root.updateBackend.state === "checking"
                                enabled: root.updateBackend.canChangeUpdateChannel
                                onClicked: root.updateBackend.checkForUpdates()
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    spacing: Theme.space12

                    Card {
                        objectName: "runtimePluginsCard"
                        Layout.fillWidth: true
                        implicitHeight: pluginsContent.implicitHeight + Theme.space24
                        ColumnLayout {
                            id: pluginsContent
                            anchors.fill: parent; anchors.margins: Theme.space12; spacing: 10
                            SectionTitle { Layout.fillWidth: true; iconName: "extension"; title: "插件"; description: "查看与管理脚本运行环境" }
                            PluginManagerPanel {
                                Layout.fillWidth: true
                                visible: !!root.controller.pluginManager
                                backend: root.controller.pluginManager || null
                            }
                            PluginRow {
                                visible: !root.controller.pluginManager
                                Layout.fillWidth: true
                                label: "PowerShell " + (root.terminalBackend ? root.terminalBackend.pluginVersion : "7")
                                actionLabel: root.terminalBackend && root.terminalBackend.pluginInstalling ? "安装中"
                                    : root.terminalBackend && root.terminalBackend.pluginInstalled ? "查看" : "安装"
                                available: root.terminalBackend !== null
                                progress: root.terminalBackend && root.terminalBackend.pluginInstalling ? root.terminalBackend.pluginInstallProgress / 100 : 0
                                onActivated: root.pluginManageRequested()
                            }
                            Repeater {
                                model: root.controller.pluginManager ? [] : root.controller.runtimePlugins || []
                                delegate: PluginRow {
                                    required property var modelData
                                    Layout.fillWidth: true
                                    label: modelData.name
                                    available: modelData.available
                                    actionLabel: available ? "查看" : "未就绪"
                                    hint: modelData.status + "\n" + modelData.path
                                    onActivated: root.controller.openRuntimeDirectory(modelData.name)
                                }
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        implicitHeight: aboutContent.implicitHeight + Theme.space24
                        ColumnLayout {
                            id: aboutContent
                            anchors.fill: parent; anchors.margins: Theme.space12; spacing: Theme.space8
                            SectionTitle { Layout.fillWidth: true; iconName: "info"; title: "关于"; description: "应用信息与相关链接" }
                            RowLayout {
                                Layout.fillWidth: true; spacing: Theme.space12
                                AppMark { Layout.preferredWidth: 48; Layout.preferredHeight: 48 }
                                ColumnLayout { Layout.fillWidth: true; spacing: 2
                                    Text { text: "泡泡工具箱"; color: Theme.textPrimary; font.pixelSize: 17; font.weight: Font.Bold }
                                    Text { text: "Android 开发者工具  ·  v" + root.controller.appVersion; color: Theme.textSecondary; font.pixelSize: Theme.fontCaption }
                                }
                            }
                            Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: Theme.outlineVariant }
                            GridLayout {
                                Layout.fillWidth: true
                                columns: 2; columnSpacing: Theme.space12; rowSpacing: 0
                                LinkButton { text: "访问官网"; iconName: "public"; onClicked: Qt.openUrlExternally(root.controller.appInfoUrl) }
                                LinkButton { text: "在 GitHub 上查看"; iconName: "code"; onClicked: Qt.openUrlExternally(root.controller.appInfoUrl) }
                                LinkButton { text: "反馈问题"; iconName: "bug_report"; onClicked: Qt.openUrlExternally(root.controller.appInfoUrl + "/issues") }
                                LinkButton { objectName: "openUserHelpButton"; text: "用户手册"; iconName: "menu_book"; onClicked: root.userHelpRequested() }
                            }
                            Text {
                                Layout.fillWidth: true
                                visible: text.length > 0
                                text: root.updateBackend.status
                                color: root.updateBackend.state === "error" ? Theme.errorColor : Theme.textSecondary
                                font.pixelSize: Theme.fontCaption
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                }
            }
        }
    }
}
