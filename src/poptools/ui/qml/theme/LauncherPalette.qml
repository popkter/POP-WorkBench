pragma Singleton
import QtQuick

// Used only inside the Decade/ZIO floating windows, never for application theming.
QtObject {
    readonly property bool darkMode: true
    readonly property bool glassMode: false
    readonly property var colors: {
        "primary": "#D9AE48",
        "primaryForeground": "#171208",
        "primaryHover": "#F4D786",
        "primaryContainer": "#3B2C13",
        "primaryContainerHover": "#51401E",
        "primaryText": "#F4D786",
        "secondary": "#BFAE84",
        "secondaryForeground": "#18150D",
        "secondaryHover": "#DFD0AC",
        "secondaryContainer": "#302A1C",
        "secondaryContainerHover": "#433925",
        "secondaryText": "#E9DDBD",
        "tertiary": "#D6B465",
        "tertiaryForeground": "#191308",
        "tertiaryHover": "#F0CF85",
        "tertiaryContainer": "#3C301B",
        "tertiaryContainerHover": "#514126",
        "tertiaryText": "#F1D8A0",
        "surface": "#10100F",
        "surfaceContainerLow": "#181713",
        "surfaceContainer": "#222019",
        "surfaceContainerHigh": "#302B20",
        "outline": "#77633B",
        "outlineVariant": "#453A25",
        "textPrimary": "#F7EACB",
        "textSecondary": "#B6A681",
        "success": "#A8CC85",
        "successForeground": "#14200C",
        "successContainer": "#26331D",
        "tealContainer": "#20352E",
        "teal": "#92C5B6",
        "errorColor": "#F49B86",
        "errorContainer": "#422720",
        "middlePanel": "#181713",
        "consoleBackground": "#11110F",
        "consoleText": "#F1E4C6",
        "consoleMuted": "#A99A77",
        "consoleHeaderBackground": "#252116",
        "consoleTag": "#F4D786",
        "consoleWarning": "#FFD17C",
        "consoleError": "#FFA38C",
        "consoleDivider": "#453A25",
        "buttonDefault": "#D9AE48",
        "buttonHover": "#F4D786",
        "buttonPressed": "#BA8C2D",
        "buttonDisabled": "#302B20",
        "buttonShadow": "#5B451B",
        "buttonHighlight": "#F8E3AE",
        "cardSelected": "#3B2C13",
        "chromeBackground": "#191813",
        "chromeForeground": "#F7EACB",
        "navigationHover": "#332C1D",
        "navigationSelected": "#7F5D20",
        "navigationActiveBorder": "#D9AE48",
        "navigationIcon": "#B6A681",
        "terminalBackground": "#11110F",
        "terminalTabSelected": "#3B2C13",
        "terminalTabBorder": "#77633B",
        "terminalTabHover": "#332C1D",
        "terminalDropHighlight": "#33D9AE48",
        "popupSurface": "#222019",
        "popupHover": "#332C1D",
        "popupSelected": "#3B2C13",
        "decadeCardSurface": "#17150F",
        "decadeCardArtworkFill": "#302719",
        "decadeCardArtworkOutline": "#77633B",
        "decadeCardArtworkIcon": "#79643A",
        "decadeCardBackFill": "#211C11",
        "decadeCardActionFill": "#292215",
        "decadeCardActionBorder": "#9D7B32",
        "decadeCounterFill": "#211C12",
        "decadeCounterBorder": "#8F733D",
        "decadeCounterMuted": "#C6AF7D",
        "decadeCounterLeading": "#7E6B43",
        "decadeCounterEmpty": "#29251A",
        "decadeCounterEmptyBorder": "#625333",
        "decadeCounterGreen": "#EED28B",
        "decadePackSurface": "#17150F",
        "decadePackWell": "#100F0C",
        "decadePackRail": "#8F733D",
        "decadePackText": "#E9D8AC"
}
    function styleColor(name, fallback) {
        return LauncherStyle.zio && colors[name] !== undefined ? colors[name] : fallback
    }
    readonly property color primary: styleColor("primary", LauncherStyle.decade ? "#F12786" : darkMode ? "#4090FF" : "#1677FF")
    readonly property color primaryForeground: styleColor("primaryForeground", "#FFFFFF")
    readonly property color primaryHover: styleColor("primaryHover", LauncherStyle.decade ? "#FF5BA6" : darkMode ? "#66A5FF" : "#0868EA")
    readonly property color primaryContainer: styleColor("primaryContainer", LauncherStyle.decade ? "#42182E" : darkMode ? "#16365F" : "#E8F2FF")
    readonly property color primaryContainerHover: styleColor("primaryContainerHover", LauncherStyle.decade ? "#5B203E" : darkMode ? "#1E477B" : "#D8E9FF")
    readonly property color primaryText: styleColor("primaryText", LauncherStyle.decade ? "#FF88BE" : darkMode ? "#79B2FF" : "#0E6FEA")
    readonly property color secondary: styleColor("secondary", LauncherStyle.decade ? "#C7C5CC" : darkMode ? "#AAB6C8" : "#536174")
    readonly property color secondaryForeground: styleColor("secondaryForeground", "#FFFFFF")
    readonly property color secondaryHover: styleColor("secondaryHover", LauncherStyle.decade ? "#E7E4EB" : darkMode ? "#C3CDDB" : "#405064")
    readonly property color secondaryContainer: styleColor("secondaryContainer", LauncherStyle.decade ? "#29272F" : darkMode ? "#2A3442" : "#F1F4F8")
    readonly property color secondaryContainerHover: styleColor("secondaryContainerHover", LauncherStyle.decade ? "#35313D" : darkMode ? "#344152" : "#E7EBF1")
    readonly property color secondaryText: styleColor("secondaryText", LauncherStyle.decade ? "#E5E1E9" : darkMode ? "#D7DEE8" : "#334155")
    readonly property color tertiary: styleColor("tertiary", darkMode ? "#C29BFF" : "#8556D8")
    readonly property color tertiaryForeground: styleColor("tertiaryForeground", "#FFFFFF")
    readonly property color tertiaryHover: styleColor("tertiaryHover", darkMode ? "#D1B4FF" : "#7145BE")
    readonly property color tertiaryContainer: styleColor("tertiaryContainer", darkMode ? "#3B2858" : "#F1E9FF")
    readonly property color tertiaryContainerHover: styleColor("tertiaryContainerHover", darkMode ? "#4A326E" : "#E7DAFF")
    readonly property color tertiaryText: styleColor("tertiaryText", darkMode ? "#E3D2FF" : "#6F42C1")
    readonly property color surface: styleColor("surface", LauncherStyle.decade ? "#101014" : darkMode ? "#11161E" : "#F8FAFC")
    readonly property color chromeBackground: styleColor("chromeBackground", LauncherStyle.decade ? "#19191F" : darkMode ? "#2B2D30" : "#F7F8FA")
    readonly property color chromeForeground: styleColor("chromeForeground", LauncherStyle.decade ? "#F4F0F5" : darkMode ? "#DFE1E5" : "#27282E")
    readonly property color sidebar: styleColor("sidebar", chromeBackground)
    readonly property color workspaceBackground: styleColor("workspaceBackground", darkMode ? surface : "#FBFCFE")
    readonly property color navigationHover: styleColor("navigationHover", LauncherStyle.decade ? "#302631" : darkMode ? "#393B40" : "#E9EAEC")
    readonly property color navigationBorder: styleColor("navigationBorder", darkMode ? outlineVariant : "#E0E5EB")
    readonly property color navigationActiveBorder: styleColor("navigationActiveBorder", LauncherStyle.decade ? "#F12786" : darkMode ? primary : "#88BFFF")
    readonly property color navigationIcon: styleColor("navigationIcon", LauncherStyle.decade ? "#BDB6C2" : darkMode ? "#CED0D6" : "#6C707E")
    readonly property color navigationActiveIcon: styleColor("navigationActiveIcon", "#FFFFFF")
    readonly property color listSelected: styleColor("listSelected", darkMode ? primaryContainer : "#E5F0FF")
    readonly property color listAlternate: styleColor("listAlternate", darkMode ? "transparent" : "#FAFBFC")
    readonly property color inputBorder: styleColor("inputBorder", darkMode ? outline : "#A8CFFF")
    readonly property color terminalToolbar: styleColor("terminalToolbar", darkMode ? surface : "#FFFFFF")
    readonly property color terminalBackground: darkMode
        ? styleColor("terminalBackground", LauncherStyle.decade ? "#121216" : "#171C24") : surfaceContainerLow
    readonly property color terminalForeground: darkMode ? consoleText : textPrimary
    readonly property color terminalMuted: darkMode ? consoleMuted : textSecondary
    readonly property color terminalSelection: darkMode ? "#6066C880" : "#401677FF"
    readonly property color terminalTabSelected: darkMode
        ? styleColor("terminalTabSelected", LauncherStyle.decade ? "#42182E" : "#43546A") : listSelected
    readonly property color terminalTabBorder: styleColor("terminalTabBorder", LauncherStyle.decade ? "#82516D" : darkMode ? "#647D9B" : "#E1E5EA")
    readonly property color terminalTabText: styleColor("terminalTabText", darkMode ? textPrimary : "#404750")
    readonly property color terminalTabMuted: styleColor("terminalTabMuted", darkMode ? textSecondary : "#6B737D")
    readonly property color terminalTabAction: styleColor("terminalTabAction", darkMode ? "#C3CDDA" : "#7A838D")
    readonly property color terminalTabHover: styleColor("terminalTabHover", LauncherStyle.decade ? "#302631" : darkMode ? "#39424F" : "#E8ECF1")
    readonly property color terminalTabDivider: styleColor("terminalTabDivider", darkMode ? outlineVariant : "#D8DDE3")
    readonly property color terminalDropHighlight: styleColor("terminalDropHighlight", LauncherStyle.decade ? "#33F12786" : "#331B78F2")
    readonly property color navigationSelected: styleColor("navigationSelected", LauncherStyle.decade ? "#C81768" : "#3574F0")
    readonly property color surfaceContainerLow: styleColor("surfaceContainerLow", LauncherStyle.decade ? "#17171D" : darkMode ? "#171E28" : "#FFFFFF")
    readonly property color surfaceContainer: styleColor("surfaceContainer", LauncherStyle.decade ? "#202027" : darkMode ? "#1D2530" : "#F5F7FA")
    readonly property color surfaceContainerHigh: styleColor("surfaceContainerHigh", LauncherStyle.decade ? "#2B2933" : darkMode ? "#26313F" : "#EDF1F5")
    readonly property color outline: styleColor("outline", LauncherStyle.decade ? "#51414D" : darkMode ? "#435064" : "#D9DEE7")
    readonly property color outlineVariant: styleColor("outlineVariant", LauncherStyle.decade ? "#352C37" : darkMode ? "#303B4B" : "#E0E4EA")
    readonly property color popupSurface: styleColor("popupSurface", LauncherStyle.decade ? "#1D1B23" : darkMode ? "#1B232E" : "#FFFFFF")
    readonly property color popupHover: styleColor("popupHover", LauncherStyle.decade ? "#302631" : darkMode ? "#26313F" : "#F4F6F9")
    readonly property color popupSelected: styleColor("popupSelected", LauncherStyle.decade ? "#42182E" : darkMode ? "#173A66" : "#E8F2FF")
    readonly property color popupShadow: styleColor("popupShadow", darkMode ? "#99000000" : "#290F172A")
    readonly property color dialogShadow: styleColor("dialogShadow", darkMode ? "#B3000000" : "#380F172A")
    readonly property color scrim: styleColor("scrim", darkMode ? "#8F070B12" : "#470F172A")
    readonly property color textPrimary: styleColor("textPrimary", LauncherStyle.decade ? "#F8F2F7" : darkMode ? "#F3F6FA" : "#0B0F17")
    readonly property color textSecondary: styleColor("textSecondary", LauncherStyle.decade ? "#B6A9B7" : darkMode ? "#93A0B3" : "#7B8496")
    readonly property color success: styleColor("success", darkMode ? "#5FD49A" : "#29AF6F")
    readonly property color successForeground: styleColor("successForeground", darkMode ? "#071D13" : "#FFFFFF")
    readonly property color successContainer: styleColor("successContainer", darkMode ? "#123D2A" : "#E8F8EF")
    readonly property color tealContainer: styleColor("tealContainer", darkMode ? "#123A3B" : "#E8F8F7")
    readonly property color teal: styleColor("teal", darkMode ? "#63D7D2" : "#159B95")
    readonly property color errorColor: styleColor("errorColor", darkMode ? "#FF8D87" : "#E5484D")
    readonly property color errorContainer: styleColor("errorContainer", darkMode ? "#4C2225" : "#FFF0F0")
    readonly property color middlePanel: styleColor("middlePanel", surfaceContainerLow)
    readonly property color consoleBackground: styleColor("consoleBackground", LauncherStyle.decade ? "#101014" : "#10151D")
    readonly property color consoleText: styleColor("consoleText", "#E5E7EB")
    readonly property color consoleMuted: styleColor("consoleMuted", LauncherStyle.decade ? "#AA9BAC" : "#728298")
    readonly property color consoleHeaderBackground: styleColor("consoleHeaderBackground", LauncherStyle.decade ? "#232028" : "#202731")
    readonly property color consoleTag: styleColor("consoleTag", LauncherStyle.decade ? "#FF88BE" : "#66AFFF")
    readonly property color consoleWarning: styleColor("consoleWarning", "#FFCE66")
    readonly property color consoleError: styleColor("consoleError", "#FF8585")
    readonly property color consoleDivider: styleColor("consoleDivider", outlineVariant)
    readonly property color buttonDefault: styleColor("buttonDefault", primary)
    readonly property color buttonHover: styleColor("buttonHover", primaryHover)
    readonly property color buttonPressed: styleColor("buttonPressed", LauncherStyle.decade ? "#C81768" : darkMode ? "#2578E8" : "#005AC7")
    readonly property color buttonDisabled: styleColor("buttonDisabled", surfaceContainerHigh)
    readonly property color inputDefault: styleColor("inputDefault", surfaceContainerLow)
    readonly property color inputHover: styleColor("inputHover", surfaceContainer)
    readonly property color inputFocused: styleColor("inputFocused", primaryContainer)
    readonly property color inputError: styleColor("inputError", errorColor)
    readonly property color inputDisabled: styleColor("inputDisabled", surfaceContainer)
    readonly property color cardDefault: styleColor("cardDefault", surfaceContainerLow)
    readonly property color cardHover: styleColor("cardHover", surfaceContainer)
    readonly property color cardSelected: styleColor("cardSelected", primaryContainer)
    readonly property color cardDisabled: styleColor("cardDisabled", surfaceContainerHigh)
    readonly property color borderColorDefault: styleColor("borderColorDefault", outline)
    readonly property color borderColorHover: styleColor("borderColorHover", primary)
    readonly property color borderColorFocused: styleColor("borderColorFocused", primary)
    readonly property color borderColorError: styleColor("borderColorError", errorColor)
    readonly property color buttonShadow: styleColor("buttonShadow", primaryHover)
    readonly property color buttonHighlight: styleColor("buttonHighlight", "transparent")
    readonly property color runtimeBadge: styleColor("runtimeBadge", darkMode ? primaryContainer : "#EFF4FC")
    readonly property color runtimeBadgeText: styleColor("runtimeBadgeText", darkMode ? primaryText : "#4D75A9")
    readonly property color dangerAction: styleColor("dangerAction", darkMode ? errorContainer : "#33FF0000")
}
