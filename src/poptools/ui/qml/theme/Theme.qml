pragma Singleton
import QtQuick

QtObject {
    property bool darkMode: false

    // The application ships one visual language with light and dark palettes.
    readonly property color primary: darkMode ? "#4090FF" : "#1677FF"
    readonly property color primaryForeground: "#FFFFFF"
    readonly property color primaryHover: darkMode ? "#66A5FF" : "#0868EA"
    readonly property color primaryContainer: darkMode ? "#16365F" : "#E8F2FF"
    readonly property color primaryContainerHover: darkMode ? "#1E477B" : "#D8E9FF"
    readonly property color primaryText: darkMode ? "#79B2FF" : "#0E6FEA"
    readonly property color secondary: darkMode ? "#AAB6C8" : "#536174"
    readonly property color secondaryForeground: "#FFFFFF"
    readonly property color secondaryHover: darkMode ? "#C3CDDB" : "#405064"
    readonly property color secondaryContainer: darkMode ? "#2A3442" : "#F1F4F8"
    readonly property color secondaryContainerHover: darkMode ? "#344152" : "#E7EBF1"
    readonly property color secondaryText: darkMode ? "#D7DEE8" : "#334155"
    readonly property color tertiary: darkMode ? "#C29BFF" : "#8556D8"
    readonly property color tertiaryForeground: "#FFFFFF"
    readonly property color tertiaryHover: darkMode ? "#D1B4FF" : "#7145BE"
    readonly property color tertiaryContainer: darkMode ? "#3B2858" : "#F1E9FF"
    readonly property color tertiaryContainerHover: darkMode ? "#4A326E" : "#E7DAFF"
    readonly property color tertiaryText: darkMode ? "#E3D2FF" : "#6F42C1"
    readonly property color surface: darkMode ? "#11161E" : "#F8FAFC"
    readonly property color chromeBackground: darkMode ? "#2B2D30" : "#F7F8FA"
    readonly property color chromeForeground: darkMode ? "#DFE1E5" : "#27282E"
    readonly property int captionControlWidth: 47
    readonly property int captionGlyphSize: 10
    readonly property int captionActionHeight: 28
    readonly property color sidebar: chromeBackground
    readonly property color workspaceBackground: darkMode ? surface : "#FBFCFE"
    readonly property color navigationHover: darkMode ? "#393B40" : "#E9EAEC"
    readonly property color navigationBorder: darkMode ? outlineVariant : "#E0E5EB"
    readonly property color navigationActiveBorder: darkMode ? primary : "#88BFFF"
    readonly property color navigationIcon: darkMode ? "#CED0D6" : "#6C707E"
    readonly property color navigationActiveIcon: "#FFFFFF"
    readonly property color listSelected: darkMode ? primaryContainer : "#E5F0FF"
    readonly property color listAlternate: darkMode ? "transparent" : "#FAFBFC"
    readonly property color inputBorder: darkMode ? outline : "#A8CFFF"
    readonly property color terminalToolbar: darkMode ? surface : "#FFFFFF"
    readonly property color terminalBackground: "#2B313D"
    readonly property color terminalTabSelected: darkMode ? surfaceContainerHigh : "#E3E7EC"
    readonly property color terminalTabBorder: darkMode ? outlineVariant : "#E1E5EA"
    readonly property color terminalTabText: darkMode ? textPrimary : "#404750"
    readonly property color terminalTabMuted: darkMode ? textSecondary : "#6B737D"
    readonly property color terminalTabAction: darkMode ? textSecondary : "#7A838D"
    readonly property color terminalTabHover: darkMode ? surfaceContainerHigh : "#E8ECF1"
    readonly property color terminalTabDivider: darkMode ? outlineVariant : "#D8DDE3"
    readonly property color terminalDropHighlight: "#331B78F2"
    readonly property color navigationSelected: "#3574F0"
    readonly property color surfaceContainerLow: darkMode ? "#171E28" : "#FFFFFF"
    readonly property color surfaceContainer: darkMode ? "#1D2530" : "#F5F7FA"
    readonly property color surfaceContainerHigh: darkMode ? "#26313F" : "#EDF1F5"
    readonly property color outline: darkMode ? "#435064" : "#D9DEE7"
    readonly property color outlineVariant: darkMode ? "#303B4B" : "#E0E4EA"
    readonly property color popupSurface: darkMode ? "#1B232E" : "#FFFFFF"
    readonly property color popupHover: darkMode ? "#26313F" : "#F4F6F9"
    readonly property color popupSelected: darkMode ? "#173A66" : "#E8F2FF"
    readonly property color popupShadow: darkMode ? "#99000000" : "#290F172A"
    readonly property color dialogShadow: darkMode ? "#B3000000" : "#380F172A"
    readonly property color scrim: darkMode ? "#8F070B12" : "#470F172A"
    readonly property color textPrimary: darkMode ? "#F3F6FA" : "#0B0F17"
    readonly property color textSecondary: darkMode ? "#93A0B3" : "#7B8496"
    readonly property color success: darkMode ? "#5FD49A" : "#29AF6F"
    readonly property color successForeground: darkMode ? "#071D13" : "#FFFFFF"
    readonly property color successContainer: darkMode ? "#123D2A" : "#E8F8EF"
    readonly property color tealContainer: darkMode ? "#123A3B" : "#E8F8F7"
    readonly property color teal: darkMode ? "#63D7D2" : "#159B95"
    readonly property color errorColor: darkMode ? "#FF8D87" : "#E5484D"
    readonly property color errorContainer: darkMode ? "#4C2225" : "#FFF0F0"
    readonly property color middlePanel: surfaceContainerLow
    readonly property color consoleBackground: "#10151D"
    readonly property color consoleText: "#E5E7EB"
    readonly property color consoleMuted: "#728298"
    readonly property color consoleHeaderBackground: "#202731"
    readonly property color consoleTag: "#66AFFF"
    readonly property color consoleWarning: "#FFCE66"
    readonly property color consoleError: "#FF8585"
    readonly property color consoleDivider: outlineVariant

    property int fontDisplay: 40
    property int fontPageTitle: 30
    property int fontTitleLarge: 22
    property int fontDialogTitle: 24
    property int fontSectionTitle: 19
    property int fontComponentTitle: 15
    property int fontButton: 14
    property int fontBody: 14
    property int fontLabel: 13
    property int fontSupporting: 13
    property int fontCode: 13
    property int fontCaption: 12
    property int fontMicro: 10
    readonly property int fontSmall: 11
    readonly property int fontTitleSmall: 16
    readonly property int fontDetailTitle: 24
    property int radiusNone: 0
    property int radiusTiny: 4
    property int radiusSmall: 7
    property int radiusMedium: 10
    property int radiusLarge: 16
    property int radiusXLarge: 20
    property int radiusFull: 9999
    readonly property int applicationRadius: 10
    property int space0: 0
    property int space4: 4
    property int space8: 8
    property int space12: 12
    property int space16: 16
    property int space20: 20
    property int space24: 24
    property int space28: 28
    property int space32: 32
    property int space36: 36
    property int space40: 40
    property int pagePadding: 24
    property int pagePaddingCompact: 14
    property int panelPadding: 16
    property int panelPaddingCompact: 10
    property int sectionSpacing: 16
    property int controlSpacing: 8
    property int terminalContentPadding: 20
    readonly property int primaryNavigationWidth: 246
    readonly property int primaryNavigationCompactWidth: 134
    property int navigationMaximumWidth: 306
    property int borderWidthThin: 1
    property int borderWidthMedium: 2
    property int borderWidthThick: 3
    readonly property color buttonDefault: primary
    readonly property color buttonHover: primaryHover
    readonly property color buttonPressed: darkMode ? "#2578E8" : "#005AC7"
    readonly property color buttonDisabled: surfaceContainerHigh
    readonly property color inputDefault: surfaceContainerLow
    readonly property color inputHover: surfaceContainer
    readonly property color inputFocused: primaryContainer
    readonly property color inputError: errorColor
    readonly property color inputDisabled: surfaceContainer
    readonly property color cardDefault: surfaceContainerLow
    readonly property color cardHover: surfaceContainer
    readonly property color cardSelected: primaryContainer
    readonly property color cardDisabled: surfaceContainerHigh
    readonly property color borderColorDefault: outline
    readonly property color borderColorHover: primary
    readonly property color borderColorFocused: primary
    readonly property color borderColorError: errorColor
    readonly property color buttonShadow: primaryHover
    readonly property color buttonHighlight: "transparent"
    property int unit: 8

    // PopTools / Page 1: Screen / 自定义, Screen / 终端, Screen / 设置.
    // Dimensions are logical pixels; responsive rules use available content width.
    readonly property int windowMinimumWidth: 960
    readonly property int windowMinimumHeight: 640
    readonly property int windowDefaultWidth: 1100
    readonly property int windowDefaultHeight: 740
    readonly property int navigationRailWidth: 40
    readonly property int navigationItemHeight: 40
    readonly property int navigationIconSize: 20
    readonly property int navigationItemInset: 5
    readonly property int navigationLogoSize: 40
    readonly property int workspaceInset: 16
    readonly property int workspaceGap: 16
    readonly property int scriptPanelGap: 12
    readonly property int settingsHeaderHeight: 80
    readonly property int dialogWidth: 548
    readonly property int fontDialogDescription: 18
    readonly property int fontPageDescription: 15
    readonly property color runtimeBadge: darkMode ? primaryContainer : "#EFF4FC"
    readonly property color runtimeBadgeText: darkMode ? primaryText : "#4D75A9"
    readonly property color dangerAction: darkMode ? errorContainer : "#33FF0000"
    readonly property int pageHeaderHeight: 66
    readonly property int pageHeaderCompactHeight: 54
    readonly property int workspaceTitleSize: 36
    readonly property int controlHeightSmall: 36
    readonly property int controlHeight: 40
    readonly property int controlHeightLarge: 48
    readonly property int inputHeight: 42
    readonly property int iconSmall: 16
    readonly property int iconMedium: 20
    readonly property int iconLarge: 24
    readonly property int scriptListMinimumWidth: 290
    readonly property int scriptListMaximumWidth: 438
    readonly property real scriptListWidthRatio: 0.356
    readonly property int scriptRowHeight: 40
    readonly property int settingsColumnMinimumWidth: 440
    readonly property int settingsTwoColumnWidth: settingsColumnMinimumWidth * 2 + workspaceGap
    readonly property int terminalTabMinimumWidth: 120
    readonly property int terminalTabMaximumWidth: 180
    readonly property int terminalToolbarHeight: 38
    readonly property int menuWidth: 180
    readonly property int menuItemHeight: 38
    readonly property int radiusControl: 7
    readonly property int radiusCard: 12
    readonly property int radiusConsole: 8
    readonly property int detailPanelPadding: 16
    readonly property int detailActionWidth: 94
    readonly property int detailRunWidth: 108
    readonly property int detailCompactWidth: 440
    readonly property int consoleHeaderHeight: 42
    readonly property int consoleFooterHeight: 28
    readonly property int consoleMaximumHeight: 348
    readonly property int consoleMinimumHeight: 152
    readonly property int detailFormReservedHeight: 380
    readonly property int detailFormMaximumVisibleHeight: 240
    readonly property int motionFast: 120
    readonly property int motionStandard: 180
    readonly property int motionSpinner: 750
    readonly property int floatingNotchWidth: 44
    readonly property int floatingGripHeight: 20
    readonly property int floatingPanelWidth: 360
    readonly property int floatingPanelHeight: 480
    readonly property real floatingIdleOpacity: 0.55
}
