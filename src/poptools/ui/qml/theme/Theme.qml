pragma Singleton
import QtQuick

QtObject {
    property bool darkMode: false
    property bool decadeMode: false
    property bool zioMode: false
    readonly property bool mechanicalMode: decadeMode || zioMode
    property var zioPalette: ({})
    function zioColor(name, fallback) {
        return zioMode && zioPalette[name] !== undefined ? zioPalette[name] : fallback
    }

    // Decade shares layout tokens, with a carbon-black and magenta palette.
    readonly property color primary: zioColor("primary", decadeMode ? "#F12786" : darkMode ? "#4090FF" : "#1677FF")
    readonly property color primaryForeground: zioColor("primaryForeground", "#FFFFFF")
    readonly property color primaryHover: zioColor("primaryHover", decadeMode ? "#FF5BA6" : darkMode ? "#66A5FF" : "#0868EA")
    readonly property color primaryContainer: zioColor("primaryContainer", decadeMode ? "#42182E" : darkMode ? "#16365F" : "#E8F2FF")
    readonly property color primaryContainerHover: zioColor("primaryContainerHover", decadeMode ? "#5B203E" : darkMode ? "#1E477B" : "#D8E9FF")
    readonly property color primaryText: zioColor("primaryText", decadeMode ? "#FF88BE" : darkMode ? "#79B2FF" : "#0E6FEA")
    readonly property color secondary: zioColor("secondary", decadeMode ? "#C7C5CC" : darkMode ? "#AAB6C8" : "#536174")
    readonly property color secondaryForeground: zioColor("secondaryForeground", "#FFFFFF")
    readonly property color secondaryHover: zioColor("secondaryHover", decadeMode ? "#E7E4EB" : darkMode ? "#C3CDDB" : "#405064")
    readonly property color secondaryContainer: zioColor("secondaryContainer", decadeMode ? "#29272F" : darkMode ? "#2A3442" : "#F1F4F8")
    readonly property color secondaryContainerHover: zioColor("secondaryContainerHover", decadeMode ? "#35313D" : darkMode ? "#344152" : "#E7EBF1")
    readonly property color secondaryText: zioColor("secondaryText", decadeMode ? "#E5E1E9" : darkMode ? "#D7DEE8" : "#334155")
    readonly property color tertiary: zioColor("tertiary", darkMode ? "#C29BFF" : "#8556D8")
    readonly property color tertiaryForeground: zioColor("tertiaryForeground", "#FFFFFF")
    readonly property color tertiaryHover: zioColor("tertiaryHover", darkMode ? "#D1B4FF" : "#7145BE")
    readonly property color tertiaryContainer: zioColor("tertiaryContainer", darkMode ? "#3B2858" : "#F1E9FF")
    readonly property color tertiaryContainerHover: zioColor("tertiaryContainerHover", darkMode ? "#4A326E" : "#E7DAFF")
    readonly property color tertiaryText: zioColor("tertiaryText", darkMode ? "#E3D2FF" : "#6F42C1")
    readonly property color surface: zioColor("surface", decadeMode ? "#101014" : darkMode ? "#11161E" : "#F8FAFC")
    readonly property color chromeBackground: zioColor("chromeBackground", decadeMode ? "#19191F" : darkMode ? "#2B2D30" : "#F7F8FA")
    readonly property color chromeForeground: zioColor("chromeForeground", decadeMode ? "#F4F0F5" : darkMode ? "#DFE1E5" : "#27282E")
    readonly property int captionControlWidth: 47
    readonly property int captionGlyphSize: 10
    readonly property int captionActionHeight: 28
    readonly property color sidebar: chromeBackground
    readonly property color workspaceBackground: darkMode ? surface : "#FBFCFE"
    readonly property color navigationHover: zioColor("navigationHover", decadeMode ? "#302631" : darkMode ? "#393B40" : "#E9EAEC")
    readonly property color navigationBorder: darkMode ? outlineVariant : "#E0E5EB"
    readonly property color navigationActiveBorder: zioColor("navigationActiveBorder", decadeMode ? "#F12786" : darkMode ? primary : "#88BFFF")
    readonly property color navigationIcon: zioColor("navigationIcon", decadeMode ? "#BDB6C2" : darkMode ? "#CED0D6" : "#6C707E")
    readonly property color navigationActiveIcon: "#FFFFFF"
    readonly property color listSelected: darkMode ? primaryContainer : "#E5F0FF"
    readonly property color listAlternate: darkMode ? "transparent" : "#FAFBFC"
    readonly property color inputBorder: darkMode ? outline : "#A8CFFF"
    readonly property color terminalToolbar: darkMode ? surface : "#FFFFFF"
    readonly property color terminalBackground: zioColor("terminalBackground", decadeMode ? "#121216" : darkMode ? "#171C24" : "#2B313D")
    readonly property color terminalTabSelected: zioColor("terminalTabSelected", decadeMode ? "#42182E" : darkMode ? "#43546A" : terminalBackground)
    readonly property color terminalTabBorder: zioColor("terminalTabBorder", decadeMode ? "#82516D" : darkMode ? "#647D9B" : "#E1E5EA")
    readonly property color terminalTabText: darkMode ? textPrimary : "#404750"
    readonly property color terminalTabMuted: darkMode ? textSecondary : "#6B737D"
    readonly property color terminalTabAction: darkMode ? "#C3CDDA" : "#7A838D"
    readonly property color terminalTabHover: zioColor("terminalTabHover", decadeMode ? "#302631" : darkMode ? "#39424F" : "#E8ECF1")
    readonly property color terminalTabDivider: darkMode ? outlineVariant : "#D8DDE3"
    readonly property color terminalDropHighlight: zioColor("terminalDropHighlight", decadeMode ? "#33F12786" : "#331B78F2")
    readonly property color navigationSelected: zioColor("navigationSelected", decadeMode ? "#C81768" : "#3574F0")
    readonly property color surfaceContainerLow: zioColor("surfaceContainerLow", decadeMode ? "#17171D" : darkMode ? "#171E28" : "#FFFFFF")
    readonly property color surfaceContainer: zioColor("surfaceContainer", decadeMode ? "#202027" : darkMode ? "#1D2530" : "#F5F7FA")
    readonly property color surfaceContainerHigh: zioColor("surfaceContainerHigh", decadeMode ? "#2B2933" : darkMode ? "#26313F" : "#EDF1F5")
    readonly property color outline: zioColor("outline", decadeMode ? "#51414D" : darkMode ? "#435064" : "#D9DEE7")
    readonly property color outlineVariant: zioColor("outlineVariant", decadeMode ? "#352C37" : darkMode ? "#303B4B" : "#E0E4EA")
    readonly property color popupSurface: zioColor("popupSurface", decadeMode ? "#1D1B23" : darkMode ? "#1B232E" : "#FFFFFF")
    readonly property color popupHover: zioColor("popupHover", decadeMode ? "#302631" : darkMode ? "#26313F" : "#F4F6F9")
    readonly property color popupSelected: zioColor("popupSelected", decadeMode ? "#42182E" : darkMode ? "#173A66" : "#E8F2FF")
    readonly property color popupShadow: darkMode ? "#99000000" : "#290F172A"
    readonly property color dialogShadow: darkMode ? "#B3000000" : "#380F172A"
    readonly property color scrim: darkMode ? "#8F070B12" : "#470F172A"
    readonly property color textPrimary: zioColor("textPrimary", decadeMode ? "#F8F2F7" : darkMode ? "#F3F6FA" : "#0B0F17")
    readonly property color textSecondary: zioColor("textSecondary", decadeMode ? "#B6A9B7" : darkMode ? "#93A0B3" : "#7B8496")
    readonly property color success: zioColor("success", darkMode ? "#5FD49A" : "#29AF6F")
    readonly property color successForeground: zioColor("successForeground", darkMode ? "#071D13" : "#FFFFFF")
    readonly property color successContainer: zioColor("successContainer", darkMode ? "#123D2A" : "#E8F8EF")
    readonly property color tealContainer: zioColor("tealContainer", darkMode ? "#123A3B" : "#E8F8F7")
    readonly property color teal: zioColor("teal", darkMode ? "#63D7D2" : "#159B95")
    readonly property color errorColor: zioColor("errorColor", darkMode ? "#FF8D87" : "#E5484D")
    readonly property color errorContainer: zioColor("errorContainer", darkMode ? "#4C2225" : "#FFF0F0")
    readonly property color middlePanel: zioColor("middlePanel", surfaceContainerLow)
    readonly property color consoleBackground: zioColor("consoleBackground", decadeMode ? "#101014" : "#10151D")
    readonly property color consoleText: zioColor("consoleText", "#E5E7EB")
    readonly property color consoleMuted: zioColor("consoleMuted", decadeMode ? "#AA9BAC" : "#728298")
    readonly property color consoleHeaderBackground: zioColor("consoleHeaderBackground", decadeMode ? "#232028" : "#202731")
    readonly property color consoleTag: zioColor("consoleTag", decadeMode ? "#FF88BE" : "#66AFFF")
    readonly property color consoleWarning: zioColor("consoleWarning", "#FFCE66")
    readonly property color consoleError: zioColor("consoleError", "#FF8585")
    readonly property color consoleDivider: zioColor("consoleDivider", outlineVariant)

    // Decade card values use the same 440 x 680 design space as card motion.
    readonly property color decadeCardSurface: zioColor("decadeCardSurface", "#101118")
    readonly property color decadeCardArtworkFill: zioColor("decadeCardArtworkFill", "#7022131F")
    readonly property color decadeCardArtworkOutline: zioColor("decadeCardArtworkOutline", "#2CF12786")
    readonly property color decadeCardArtworkIcon: zioColor("decadeCardArtworkIcon", "#5F3C5D")
    readonly property color decadeCardBackFill: zioColor("decadeCardBackFill", "#22131F")
    readonly property color decadeCardActionFill: zioColor("decadeCardActionFill", "#251320")
    readonly property color decadeCardActionBorder: zioColor("decadeCardActionBorder", "#B02569")
    readonly property color decadeCounterFill: zioColor("decadeCounterFill", "#1C1420")
    readonly property color decadeCounterBorder: zioColor("decadeCounterBorder", "#8D345F")
    readonly property color decadeCounterMuted: zioColor("decadeCounterMuted", "#BF95B0")
    readonly property color decadeCounterLeading: zioColor("decadeCounterLeading", "#72506A")
    readonly property color decadeCounterEmpty: zioColor("decadeCounterEmpty", "#22212B")
    readonly property color decadeCounterEmptyBorder: zioColor("decadeCounterEmptyBorder", "#4C4655")
    readonly property color decadeCounterGreen: zioColor("decadeCounterGreen", "#7BEA80")
    readonly property real decadeCardBorderWidth: 2.8
    readonly property int decadeCardRadius: 7
    readonly property int decadeCardPadding: 16
    readonly property int decadeCardHeaderHeight: 66
    readonly property int decadeCardActionSize: 35
    readonly property int mechanicalCardRunHeight: zioMode ? 60 : 52
    readonly property int decadeCardTitleSize: 18
    readonly property int decadeCardTextSize: 14
    readonly property int decadeCardMetaSize: 11
    readonly property int decadeCardFieldActionSize: 28
    readonly property int decadeCounterHeight: 56
    readonly property int decadeCounterSquareSize: 17
    readonly property int decadeCounterSquareGap: 5
    readonly property color decadePackSurface: zioColor("decadePackSurface", "#111017")
    readonly property color decadePackWell: zioColor("decadePackWell", "#0C0D13")
    readonly property color decadePackRail: zioColor("decadePackRail", "#352736")
    readonly property color decadePackText: zioColor("decadePackText", "#DCC5D8")
    readonly property int decadePackRadius: 6

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
    readonly property color buttonDefault: zioColor("buttonDefault", primary)
    readonly property color buttonHover: zioColor("buttonHover", primaryHover)
    readonly property color buttonPressed: zioColor("buttonPressed", decadeMode ? "#C81768" : darkMode ? "#2578E8" : "#005AC7")
    readonly property color buttonDisabled: zioColor("buttonDisabled", surfaceContainerHigh)
    readonly property color inputDefault: surfaceContainerLow
    readonly property color inputHover: surfaceContainer
    readonly property color inputFocused: primaryContainer
    readonly property color inputError: errorColor
    readonly property color inputDisabled: surfaceContainer
    readonly property color cardDefault: surfaceContainerLow
    readonly property color cardHover: surfaceContainer
    readonly property color cardSelected: zioColor("cardSelected", primaryContainer)
    readonly property color cardDisabled: surfaceContainerHigh
    readonly property color borderColorDefault: outline
    readonly property color borderColorHover: primary
    readonly property color borderColorFocused: primary
    readonly property color borderColorError: errorColor
    readonly property color buttonShadow: zioColor("buttonShadow", primaryHover)
    readonly property color buttonHighlight: zioColor("buttonHighlight", "transparent")
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
    readonly property int floatingTipWidth: decadeMode ? 76 : 40
    readonly property int floatingTipHeight: decadeMode ? 112 : 40
    readonly property real scriptCardScale: 5 / 7
    readonly property int floatingPanelWidth: decadeMode ? 560 : 360
    readonly property int floatingPanelHeight: decadeMode ? 440 : 480
    readonly property real floatingIdleOpacity: 0.55
}
