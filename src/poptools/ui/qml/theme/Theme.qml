pragma Singleton
import QtQuick

QtObject {
    property bool darkMode: false
    property bool glassMode: false
    property var glassPalette: ({})
    property var glassMaterial: ({})
    function paletteFor(target) {
        const item = target && target.contentItem !== undefined ? target.contentItem : target
        let host = item ? item.Window.window : null
        while (host) {
            if (host.floatingStylePalette) return host.floatingStylePalette
            host = host.transientParent || null
        }
        return Theme
    }
    function paletteColor(name, fallback) {
        if (glassMode && glassPalette[name] !== undefined)
            return glassPalette[name]
        return fallback
    }

    readonly property color primary: paletteColor("primary", darkMode ? "#4090FF" : "#1677FF")
    readonly property color primaryForeground: paletteColor("primaryForeground", "#FFFFFF")
    readonly property color primaryHover: paletteColor("primaryHover", darkMode ? "#66A5FF" : "#0868EA")
    readonly property color primaryContainer: paletteColor("primaryContainer", darkMode ? "#16365F" : "#E8F2FF")
    readonly property color primaryContainerHover: paletteColor("primaryContainerHover", darkMode ? "#1E477B" : "#D8E9FF")
    readonly property color primaryText: paletteColor("primaryText", darkMode ? "#79B2FF" : "#0E6FEA")
    readonly property color secondary: paletteColor("secondary", darkMode ? "#AAB6C8" : "#536174")
    readonly property color secondaryForeground: paletteColor("secondaryForeground", "#FFFFFF")
    readonly property color secondaryHover: paletteColor("secondaryHover", darkMode ? "#C3CDDB" : "#405064")
    readonly property color secondaryContainer: paletteColor("secondaryContainer", darkMode ? "#2A3442" : "#F1F4F8")
    readonly property color secondaryContainerHover: paletteColor("secondaryContainerHover", darkMode ? "#344152" : "#E7EBF1")
    readonly property color secondaryText: paletteColor("secondaryText", darkMode ? "#D7DEE8" : "#334155")
    readonly property color tertiary: paletteColor("tertiary", darkMode ? "#C29BFF" : "#8556D8")
    readonly property color tertiaryForeground: paletteColor("tertiaryForeground", "#FFFFFF")
    readonly property color tertiaryHover: paletteColor("tertiaryHover", darkMode ? "#D1B4FF" : "#7145BE")
    readonly property color tertiaryContainer: paletteColor("tertiaryContainer", darkMode ? "#3B2858" : "#F1E9FF")
    readonly property color tertiaryContainerHover: paletteColor("tertiaryContainerHover", darkMode ? "#4A326E" : "#E7DAFF")
    readonly property color tertiaryText: paletteColor("tertiaryText", darkMode ? "#E3D2FF" : "#6F42C1")
    readonly property color surface: paletteColor("surface", darkMode ? "#11161E" : "#F8FAFC")
    readonly property color chromeBackground: paletteColor("chromeBackground", darkMode ? "#2B2D30" : "#F7F8FA")
    readonly property color chromeForeground: paletteColor("chromeForeground", darkMode ? "#DFE1E5" : "#27282E")
    readonly property int captionControlWidth: 47
    readonly property int captionGlyphSize: 10
    readonly property int captionActionHeight: 28
    readonly property color sidebar: paletteColor("sidebar", chromeBackground)
    readonly property color workspaceBackground: paletteColor("workspaceBackground", darkMode ? surface : "#FBFCFE")
    readonly property color navigationHover: paletteColor("navigationHover", darkMode ? "#393B40" : "#E9EAEC")
    readonly property color navigationBorder: paletteColor("navigationBorder", darkMode ? outlineVariant : "#E0E5EB")
    readonly property color navigationActiveBorder: paletteColor("navigationActiveBorder", darkMode ? primary : "#88BFFF")
    readonly property color navigationIcon: paletteColor("navigationIcon", darkMode ? "#CED0D6" : "#6C707E")
    readonly property color navigationActiveIcon: paletteColor("navigationActiveIcon", "#FFFFFF")
    readonly property color listSelected: paletteColor("listSelected", darkMode ? primaryContainer : "#E5F0FF")
    readonly property color listAlternate: paletteColor("listAlternate", darkMode ? "transparent" : "#FAFBFC")
    readonly property color inputBorder: paletteColor("inputBorder", darkMode ? outline : "#A8CFFF")
    readonly property color terminalToolbar: paletteColor("terminalToolbar", darkMode ? surface : "#FFFFFF")
    readonly property color terminalBackground: darkMode
        ? paletteColor("terminalBackground", "#171C24") : surfaceContainerLow
    readonly property color terminalForeground: darkMode ? consoleText : textPrimary
    readonly property color terminalMuted: darkMode ? consoleMuted : textSecondary
    readonly property color terminalSelection: darkMode ? "#6066C880" : "#401677FF"
    readonly property color terminalTabSelected: darkMode
        ? paletteColor("terminalTabSelected", "#43546A") : listSelected
    readonly property color terminalTabBorder: paletteColor("terminalTabBorder", darkMode ? "#647D9B" : "#E1E5EA")
    readonly property color terminalTabText: paletteColor("terminalTabText", darkMode ? textPrimary : "#404750")
    readonly property color terminalTabMuted: paletteColor("terminalTabMuted", darkMode ? textSecondary : "#6B737D")
    readonly property color terminalTabAction: paletteColor("terminalTabAction", darkMode ? "#C3CDDA" : "#7A838D")
    readonly property color terminalTabHover: paletteColor("terminalTabHover", darkMode ? "#39424F" : "#E8ECF1")
    readonly property color terminalTabDivider: paletteColor("terminalTabDivider", darkMode ? outlineVariant : "#D8DDE3")
    readonly property color terminalDropHighlight: paletteColor("terminalDropHighlight", "#331B78F2")
    readonly property color navigationSelected: paletteColor("navigationSelected", "#3574F0")
    readonly property color surfaceContainerLow: paletteColor("surfaceContainerLow", darkMode ? "#171E28" : "#FFFFFF")
    readonly property color surfaceContainer: paletteColor("surfaceContainer", darkMode ? "#1D2530" : "#F5F7FA")
    readonly property color surfaceContainerHigh: paletteColor("surfaceContainerHigh", darkMode ? "#26313F" : "#EDF1F5")
    readonly property color outline: paletteColor("outline", darkMode ? "#435064" : "#D9DEE7")
    readonly property color outlineVariant: paletteColor("outlineVariant", darkMode ? "#303B4B" : "#E0E4EA")
    readonly property color popupSurface: paletteColor("popupSurface", darkMode ? "#1B232E" : "#FFFFFF")
    readonly property color popupHover: paletteColor("popupHover", darkMode ? "#26313F" : "#F4F6F9")
    readonly property color popupSelected: paletteColor("popupSelected", darkMode ? "#173A66" : "#E8F2FF")
    readonly property color popupShadow: paletteColor("popupShadow", darkMode ? "#99000000" : "#290F172A")
    readonly property color dialogShadow: paletteColor("dialogShadow", darkMode ? "#B3000000" : "#380F172A")
    readonly property color scrim: paletteColor("scrim", darkMode ? "#8F070B12" : "#470F172A")
    readonly property color textPrimary: paletteColor("textPrimary", darkMode ? "#F3F6FA" : "#0B0F17")
    readonly property color textSecondary: paletteColor("textSecondary", darkMode ? "#93A0B3" : "#7B8496")
    readonly property color success: paletteColor("success", darkMode ? "#5FD49A" : "#29AF6F")
    readonly property color successForeground: paletteColor("successForeground", darkMode ? "#071D13" : "#FFFFFF")
    readonly property color successContainer: paletteColor("successContainer", darkMode ? "#123D2A" : "#E8F8EF")
    readonly property color tealContainer: paletteColor("tealContainer", darkMode ? "#123A3B" : "#E8F8F7")
    readonly property color teal: paletteColor("teal", darkMode ? "#63D7D2" : "#159B95")
    readonly property color errorColor: paletteColor("errorColor", darkMode ? "#FF8D87" : "#E5484D")
    readonly property color errorContainer: paletteColor("errorContainer", darkMode ? "#4C2225" : "#FFF0F0")
    readonly property color middlePanel: paletteColor("middlePanel", surfaceContainerLow)
    readonly property color consoleBackground: paletteColor("consoleBackground", "#10151D")
    readonly property color consoleText: paletteColor("consoleText", "#E5E7EB")
    readonly property color consoleMuted: paletteColor("consoleMuted", "#728298")
    readonly property color consoleHeaderBackground: paletteColor("consoleHeaderBackground", "#202731")
    readonly property color consoleTag: paletteColor("consoleTag", "#66AFFF")
    readonly property color consoleWarning: paletteColor("consoleWarning", "#FFCE66")
    readonly property color consoleError: paletteColor("consoleError", "#FF8585")
    readonly property color consoleDivider: paletteColor("consoleDivider", outlineVariant)

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
    readonly property color buttonDefault: paletteColor("buttonDefault", primary)
    readonly property color buttonHover: paletteColor("buttonHover", primaryHover)
    readonly property color buttonPressed: paletteColor("buttonPressed", darkMode ? "#2578E8" : "#005AC7")
    readonly property color buttonDisabled: paletteColor("buttonDisabled", surfaceContainerHigh)
    readonly property color inputDefault: paletteColor("inputDefault", surfaceContainerLow)
    readonly property color inputHover: paletteColor("inputHover", surfaceContainer)
    readonly property color inputFocused: paletteColor("inputFocused", primaryContainer)
    readonly property color inputError: paletteColor("inputError", errorColor)
    readonly property color inputDisabled: paletteColor("inputDisabled", surfaceContainer)
    readonly property color cardDefault: paletteColor("cardDefault", surfaceContainerLow)
    readonly property color cardHover: paletteColor("cardHover", surfaceContainer)
    readonly property color cardSelected: paletteColor("cardSelected", primaryContainer)
    readonly property color cardDisabled: paletteColor("cardDisabled", surfaceContainerHigh)
    readonly property color borderColorDefault: paletteColor("borderColorDefault", outline)
    readonly property color borderColorHover: paletteColor("borderColorHover", primary)
    readonly property color borderColorFocused: paletteColor("borderColorFocused", primary)
    readonly property color borderColorError: paletteColor("borderColorError", errorColor)
    readonly property color buttonShadow: paletteColor("buttonShadow", primaryHover)
    readonly property color buttonHighlight: paletteColor("buttonHighlight", "transparent")
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
    readonly property int compactDialogWidth: 420
    readonly property int fontDialogDescription: 18
    readonly property int fontPageDescription: 15
    readonly property color runtimeBadge: paletteColor("runtimeBadge", darkMode ? primaryContainer : "#EFF4FC")
    readonly property color runtimeBadgeText: paletteColor("runtimeBadgeText", darkMode ? primaryText : "#4D75A9")
    readonly property color dangerAction: paletteColor("dangerAction", darkMode ? errorContainer : "#33FF0000")
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
    readonly property real scriptCardScale: 5 / 7
    readonly property real floatingIdleOpacity: 0.55
}
