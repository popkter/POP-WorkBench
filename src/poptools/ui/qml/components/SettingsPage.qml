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
    color: "transparent"

    function scrollToBottom() {
        settingsFlick.contentY = Math.max(0, settingsFlick.contentHeight - settingsFlick.height)
    }

    component SettingsAction: PrimaryButton {
        implicitHeight: 32
        iconName: ""
        tonal: true
        radius: Theme.radiusControl
        border.width: 0
        color: hovered ? Theme.primaryContainerHover : Theme.runtimeBadge
        foregroundColor: Theme.primaryText
        labelFontSize: Theme.fontSupporting
        labelFontWeight: Font.Normal
        glyphSize: 18
        contentSpacing: Theme.space8
    }

    component SectionCard: Rectangle {
        id: section
        property string title: ""
        property string description: ""
        property string iconName: "settings"
        default property alias content: sectionBody.data
        Layout.fillWidth: true
        implicitHeight: sectionLayout.implicitHeight + Theme.detailPanelPadding * 2
        radius: Theme.radiusMedium
        color: Theme.surfaceContainerLow
        border.width: 0

        ColumnLayout {
            id: sectionLayout
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: Theme.detailPanelPadding
            spacing: Theme.space12
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space12
                Rectangle {
                    Layout.preferredWidth: 40
                    Layout.preferredHeight: 40
                    radius: Theme.radiusMedium
                    color: Theme.runtimeBadge
                    MaterialIcon {
                        anchors.centerIn: parent
                        icon: section.iconName
                        iconSize: 24
                        color: Theme.primaryText
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 0
                    spacing: Theme.space4
                    Text {
                        Layout.fillWidth: true
                        text: section.title
                        color: Theme.textPrimary
                        font.pixelSize: Theme.fontSectionTitle
                        font.weight: Font.Bold
                        elide: Text.ElideRight
                    }
                    Text {
                        Layout.fillWidth: true
                        text: section.description
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSupporting
                        wrapMode: Text.Wrap
                    }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: 1
                color: Theme.outlineVariant
            }
            ColumnLayout {
                id: sectionBody
                Layout.fillWidth: true
                spacing: Theme.space8
            }
        }
    }

    component SettingRow: Rectangle {
        id: setting
        property string label: ""
        property string description: ""
        property bool stacked: width < 480
        default property alias controls: controlSlot.data
        Layout.fillWidth: true
        implicitHeight: Math.max(Theme.inputHeight, rowGrid.implicitHeight + Theme.space16)
        radius: Theme.radiusSmall
        color: Theme.surfaceContainerLow
        border.width: 1
        border.color: Theme.inputBorder

        GridLayout {
            id: rowGrid
            x: Theme.space12
            y: Theme.space8
            width: parent.width - Theme.space24
            columns: setting.stacked ? 1 : 2
            columnSpacing: Theme.space12
            rowSpacing: Theme.space8
            ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredWidth: setting.stacked ? -1 : rowGrid.width * 0.3
                spacing: Theme.space4
                Text {
                    Layout.fillWidth: true
                    text: setting.label
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSupporting
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: setting.description
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.Wrap
                }
            }
            RowLayout {
                id: controlSlot
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.preferredWidth: setting.stacked ? rowGrid.width
                    : rowGrid.width * 0.7 - rowGrid.columnSpacing
                spacing: Theme.space8
            }
        }
    }

    component ToggleRow: Rectangle {
        id: toggleRow
        property string label: ""
        property string description: ""
        property alias checked: toggle.checked
        signal toggled(bool value)
        Layout.fillWidth: true
        implicitHeight: Math.max(Theme.inputHeight, toggleText.implicitHeight + Theme.space16)
        radius: Theme.radiusSmall
        color: Theme.surfaceContainerLow
        border.color: Theme.inputBorder
        border.width: 1
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.space12
            anchors.rightMargin: Theme.space12
            spacing: Theme.space12
            ColumnLayout {
                id: toggleText
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                spacing: Theme.space4
                Text {
                    Layout.fillWidth: true
                    text: toggleRow.label
                    color: Theme.textPrimary
                    font.pixelSize: Theme.fontSupporting
                    font.weight: Font.DemiBold
                    wrapMode: Text.Wrap
                }
                Text {
                    Layout.fillWidth: true
                    visible: text.length > 0
                    text: toggleRow.description
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontCaption
                    wrapMode: Text.Wrap
                }
            }
            AppSwitch {
                id: toggle
                objectName: toggleRow.objectName + "Control"
                Layout.preferredWidth: 52
                Layout.preferredHeight: 28
                padding: 0
                spacing: 0
                Accessible.name: toggleRow.label
                onToggled: toggleRow.toggled(checked)
            }
        }
    }

    component PluginRow: SettingRow {
        id: plugin
        property string actionLabel: ""
        property string hint: ""
        property bool available: true
        property real progress: 0
        signal activated()
        stacked: false
        description: hint
        AppProgressBar {
            Layout.fillWidth: true
            visible: plugin.progress > 0
            value: plugin.progress
        }
        Item { Layout.fillWidth: true; visible: plugin.progress <= 0 }
        SettingsAction {
            text: plugin.actionLabel
            enabled: plugin.available
            onClicked: plugin.activated()
        }
    }

    Flickable {
        id: settingsFlick
        objectName: "settingsScroll"
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: settingsGrid.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        acceptedButtons: Qt.NoButton
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        GridLayout {
            id: settingsGrid
            width: parent.width
            columns: width >= Theme.settingsTwoColumnWidth ? 2 : 1
            columnSpacing: Theme.scriptPanelGap
            rowSpacing: Theme.scriptPanelGap

            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
                spacing: Theme.scriptPanelGap

                SectionCard {
                    objectName: "appearanceSettingsCard"
                    title: "外观与交互"
                    description: "选择主题，设置日常使用方式"
                    iconName: "palette"
                    SettingRow {
                        label: "主题模式"
                        stacked: true
                        Repeater {
                            model: [
                                {label: "浅色", value: "light", icon: "light_mode"},
                                {label: "深色", value: "dark", icon: "dark_mode"},
                                {label: "跟随系统", value: "system", icon: "computer"},
                                {label: "Decade", value: "decade", icon: "style"}
                            ]
                            delegate: PrimaryButton {
                                required property var modelData
                                objectName: "themeChoice_" + modelData.value
                                Layout.fillWidth: true
                                Layout.preferredWidth: 0
                                Layout.minimumWidth: 0
                                implicitHeight: 32
                                text: modelData.label
                                iconName: modelData.icon
                                glyphSize: 18
                                contentSpacing: Theme.space4
                                labelFontSize: Theme.fontSupporting
                                labelFontWeight: Font.Normal
                                radius: Theme.radiusControl
                                tonal: true
                                border.width: root.controller.themeMode === modelData.value ? 1 : 0
                                border.color: Theme.primary
                                color: root.controller.themeMode === modelData.value
                                    ? Theme.primaryContainer : hovered ? Theme.navigationHover : "transparent"
                                foregroundColor: root.controller.themeMode === modelData.value
                                    ? Theme.primaryText : Theme.textPrimary
                                Accessible.name: modelData.label + "主题"
                                onClicked: root.controller.saveThemeMode(modelData.value)
                            }
                        }
                    }
                    ToggleRow {
                        objectName: "floatingLauncherToggle"
                        label: "后台悬浮入口"
                        description: "切换到其他应用时，在屏幕右侧显示快捷入口"
                        checked: root.controller.floatingLauncherEnabled
                        onToggled: function(value) { root.controller.saveFloatingLauncherEnabled(value) }
                    }
                }

                SectionCard {
                    objectName: "scriptStorageCard"
                    title: "脚本与数据"
                    description: "查看本地目录，迁移和备份自定义脚本"
                    iconName: "folder"
                    SettingRow {
                        label: "存储目录"
                        stacked: true
                        PrimaryButton {
                            objectName: "openConfigurationDirectoryButton"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            implicitHeight: 32
                            text: root.controller.configurationDirectory
                            iconName: "folder_open"
                            glyphSize: 18
                            tonal: true
                            radius: Theme.radiusControl
                            border.width: 0
                            color: hovered ? Theme.surfaceContainer : "transparent"
                            foregroundColor: Theme.textSecondary
                            labelFontSize: Theme.fontSupporting
                            labelFontWeight: Font.Normal
                            labelElide: Text.ElideMiddle
                            contentFillWidth: true
                            contentHorizontalPadding: 0
                            onClicked: root.controller.openConfigurationDirectory()
                            HoverTips { visible: parent.hovered; text: root.controller.configurationDirectory }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8
                        SettingsAction {
                            objectName: "importConfigurationButton"
                            Layout.fillWidth: true
                            implicitWidth: 0
                            text: "导入脚本"
                            iconName: "file_download"
                            onClicked: root.controller.importConfiguration()
                        }
                        SettingsAction {
                            objectName: "exportConfigurationButton"
                            Layout.fillWidth: true
                            implicitWidth: 0
                            text: "导出脚本"
                            iconName: "file_upload"
                            onClicked: root.controller.exportConfiguration()
                        }
                    }
                    Text {
                        Layout.fillWidth: true
                        visible: text.length > 0
                        text: root.controller.configurationStatus
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontCaption
                        wrapMode: Text.Wrap
                    }
                }

                SectionCard {
                    objectName: "updateSettingsCard"
                    title: "应用更新"
                    description: "管理检查频率与版本渠道"
                    iconName: "autorenew"
                    ToggleRow {
                        objectName: "automaticUpdatesToggle"
                        label: "自动检查更新"
                        description: "有新版本时通知，不会自动下载安装"
                        checked: root.updateBackend.updateCheckFrequency !== "never"
                        onToggled: function(value) {
                            root.updateBackend.setUpdateCheckFrequency(value ? "weekly" : "never")
                        }
                    }
                    ToggleRow {
                        objectName: "prereleaseUpdatesToggle"
                        label: "接收测试版本"
                        description: "提前体验 Beta 等预发布版本"
                        enabled: root.updateBackend.canChangeUpdateChannel
                        opacity: enabled ? 1 : 0.5
                        checked: root.updateBackend.prereleaseUpdatesEnabled
                        onToggled: function(value) { root.updateBackend.setPrereleaseUpdatesEnabled(value) }
                    }
                    SettingRow {
                        label: "检查频率"
                        stacked: true
                        Rectangle {
                            objectName: "updateFrequencyChoice"
                            Layout.fillWidth: true
                            Layout.minimumWidth: 0
                            implicitHeight: 34
                            radius: Theme.radiusControl
                            color: Theme.surfaceContainer
                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 2
                                spacing: Theme.space4
                                Repeater {
                                    model: [{label: "手动", value: "never"}, {label: "每天", value: "daily"},
                                        {label: "每周", value: "weekly"}, {label: "每次启动", value: "startup"}]
                                    delegate: PrimaryButton {
                                        required property var modelData
                                        objectName: "updateFrequency_" + modelData.value
                                        Layout.fillWidth: true
                                        Layout.minimumWidth: 0
                                        Layout.preferredWidth: 0
                                        Layout.fillHeight: true
                                        text: modelData.label
                                        iconName: ""
                                        labelFontSize: Theme.fontSupporting
                                        labelFontWeight: Font.Normal
                                        radius: Theme.radiusControl
                                        tonal: true
                                        border.width: 0
                                        color: root.updateBackend.updateCheckFrequency === modelData.value
                                            ? Theme.primaryContainer : hovered ? Theme.navigationHover : "transparent"
                                        foregroundColor: root.updateBackend.updateCheckFrequency === modelData.value
                                            ? Theme.primaryText : Theme.textPrimary
                                        onClicked: root.updateBackend.setUpdateCheckFrequency(modelData.value)
                                    }
                                }
                            }
                        }
                    }
                    SettingsAction {
                        objectName: "checkUpdateButton"
                        Layout.fillWidth: true
                        implicitHeight: 36
                        text: root.updateBackend.state === "checking" ? "检查中…" : "立即检查更新"
                        iconName: "autorenew"
                        iconSpinning: root.updateBackend.state === "checking"
                        enabled: root.updateBackend.canChangeUpdateChannel
                        onClicked: root.updateBackend.checkForUpdates()
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

            ColumnLayout {
                Layout.fillWidth: true
                Layout.preferredWidth: 0
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
                spacing: Theme.scriptPanelGap

                SectionCard {
                    objectName: "runtimePluginsCard"
                    title: "运行环境"
                    description: "为 Python、Android 工具与 PowerShell 选择应用管理或本地环境"
                    iconName: "extension"
                    PluginManagerPanel {
                        Layout.fillWidth: true
                        visible: !!root.controller.pluginManager
                        backend: root.controller.pluginManager || null
                    }
                    PluginRow {
                        visible: !root.controller.pluginManager
                        label: "PowerShell " + (root.terminalBackend ? root.terminalBackend.pluginVersion : "7")
                        actionLabel: root.terminalBackend && root.terminalBackend.pluginInstalling ? "安装中"
                            : root.terminalBackend && root.terminalBackend.pluginInstalled ? "查看" : "安装"
                        available: root.terminalBackend !== null
                        progress: root.terminalBackend && root.terminalBackend.pluginInstalling
                            ? root.terminalBackend.pluginInstallProgress / 100 : 0
                        onActivated: root.pluginManageRequested()
                    }
                    Repeater {
                        model: root.controller.pluginManager ? [] : root.controller.runtimePlugins || []
                        delegate: PluginRow {
                            required property var modelData
                            label: modelData.name
                            available: modelData.available
                            actionLabel: available ? "查看" : "未就绪"
                            hint: modelData.status
                            onActivated: root.controller.openRuntimeDirectory(modelData.name)
                        }
                    }
                }

                SectionCard {
                    objectName: "aboutSettingsCard"
                    title: "关于与帮助"
                    description: "应用信息、使用说明与问题反馈"
                    iconName: "info"
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space12
                        AppMark { Layout.preferredWidth: 40; Layout.preferredHeight: 40 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space4
                            Text {
                                Layout.fillWidth: true
                                text: "泡泡的工作台 · Pop’s Workbench"
                                color: Theme.textPrimary
                                font.pixelSize: Theme.fontComponentTitle
                                font.weight: Font.DemiBold
                                wrapMode: Text.Wrap
                            }
                            Text {
                                Layout.fillWidth: true
                                text: "脚本、设备与日常工具 · v" + root.controller.appVersion
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontCaption
                                wrapMode: Text.Wrap
                            }
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: Theme.space8
                        rowSpacing: Theme.space8
                        SettingsAction {
                            Layout.fillWidth: true
                            implicitWidth: 0
                            text: "访问官网"
                            iconName: "public"
                            onClicked: Qt.openUrlExternally(root.controller.appInfoUrl)
                        }
                        SettingsAction {
                            Layout.fillWidth: true
                            implicitWidth: 0
                            text: "GitHub"
                            iconName: "code"
                            onClicked: Qt.openUrlExternally(root.controller.appInfoUrl)
                        }
                        SettingsAction {
                            Layout.fillWidth: true
                            implicitWidth: 0
                            text: "反馈问题"
                            iconName: "bug_report"
                            onClicked: Qt.openUrlExternally(root.controller.appInfoUrl + "/issues")
                        }
                        SettingsAction {
                            objectName: "openUserHelpButton"
                            Layout.fillWidth: true
                            implicitWidth: 0
                            text: "用户手册"
                            iconName: "menu_book"
                            onClicked: root.userHelpRequested()
                        }
                    }
                }
            }
        }
    }
}
