pragma Singleton
import QtQuick

QtObject {
    property string style: "default"
    readonly property bool decade: style === "decade"
    readonly property bool zio: style === "zio"
    readonly property bool mechanical: decade || zio
    readonly property color accent: zio ? "#D9AE48" : decade ? "#F12786" : Theme.primary
    readonly property var zioArtwork: {"decadeCardSurface": "#17150F", "decadeCardArtworkFill": "#302719", "decadeCardArtworkOutline": "#77633B", "decadeCardArtworkIcon": "#79643A", "decadeCardBackFill": "#211C11", "decadeCardActionFill": "#292215", "decadeCardActionBorder": "#9D7B32", "decadeCounterFill": "#211C12", "decadeCounterBorder": "#8F733D", "decadeCounterMuted": "#C6AF7D", "decadeCounterLeading": "#7E6B43", "decadeCounterEmpty": "#29251A", "decadeCounterEmptyBorder": "#625333", "decadeCounterGreen": "#EED28B", "decadePackSurface": "#17150F", "decadePackWell": "#100F0C", "decadePackRail": "#8F733D", "decadePackText": "#E9D8AC"}
    function styleColor(name, fallback) {
        return zio && zioArtwork[name] !== undefined ? zioArtwork[name] : fallback
    }
    // Decade card values use the same 440 x 680 design space as card motion.
    readonly property color decadeCardSurface: styleColor("decadeCardSurface", "#101118")
    readonly property color decadeCardArtworkFill: styleColor("decadeCardArtworkFill", "#7022131F")
    readonly property color decadeCardArtworkOutline: styleColor("decadeCardArtworkOutline", "#2CF12786")
    readonly property color decadeCardArtworkIcon: styleColor("decadeCardArtworkIcon", "#5F3C5D")
    readonly property color decadeCardBackFill: styleColor("decadeCardBackFill", "#22131F")
    readonly property color decadeCardActionFill: styleColor("decadeCardActionFill", "#251320")
    readonly property color decadeCardActionBorder: styleColor("decadeCardActionBorder", "#B02569")
    readonly property color decadeCounterFill: styleColor("decadeCounterFill", "#1C1420")
    readonly property color decadeCounterBorder: styleColor("decadeCounterBorder", "#8D345F")
    readonly property color decadeCounterMuted: styleColor("decadeCounterMuted", "#BF95B0")
    readonly property color decadeCounterLeading: styleColor("decadeCounterLeading", "#72506A")
    readonly property color decadeCounterEmpty: styleColor("decadeCounterEmpty", "#22212B")
    readonly property color decadeCounterEmptyBorder: styleColor("decadeCounterEmptyBorder", "#4C4655")
    readonly property color decadeCounterGreen: styleColor("decadeCounterGreen", "#7BEA80")
    readonly property real decadeCardBorderWidth: 2.8
    readonly property int decadeCardRadius: 7
    readonly property int decadeCardPadding: 16
    readonly property int decadeCardHeaderHeight: 66
    readonly property int decadeCardActionSize: 35
    readonly property int mechanicalCardRunHeight: zio ? 60 : 52
    readonly property int decadeCardTitleSize: 18
    readonly property int decadeCardTextSize: 14
    readonly property int decadeCardMetaSize: 11
    readonly property int decadeCardFieldActionSize: 28
    readonly property int decadeCounterHeight: 56
    readonly property int decadeCounterSquareSize: 17
    readonly property int decadeCounterSquareGap: 5
    readonly property color decadePackSurface: styleColor("decadePackSurface", "#111017")
    readonly property color decadePackWell: styleColor("decadePackWell", "#0C0D13")
    readonly property color decadePackRail: styleColor("decadePackRail", "#352736")
    readonly property color decadePackText: styleColor("decadePackText", "#DCC5D8")
    readonly property int decadePackRadius: 6

    readonly property int floatingTipWidth: decade ? 76 : 40
    readonly property int floatingTipHeight: decade ? 112 : 40
    readonly property int floatingPanelWidth: decade ? 560 : 360
    readonly property int floatingPanelHeight: decade ? 440 : 480
}
