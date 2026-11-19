import QtQuick
import QtQuick.Window
import QtQuick.Layouts
import "../theme"

Rectangle {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property string text: "运行"
    property string iconName: "play_arrow"
    property Component iconComponent: null
    property bool tonal: false
    property bool compact: false
    property bool showHoverTips: compact
    property bool successStyle: false
    property bool dangerStyle: false
    property bool iconSpinning: false
    property color foregroundColor: "transparent"
    property real labelFontSize: Theme.fontButton
    property int labelFontWeight: _visualPalette.glassMode ? Font.Bold : Font.DemiBold
    property real glyphSize: Theme.iconMedium
    property real contentSpacing: compact ? 0 : Theme.controlSpacing
    property real disabledOpacity: 1
    property bool contentFillWidth: false
    property real contentHorizontalPadding: 0
    property int labelElide: Text.ElideNone
    readonly property bool hovered: mouseArea.containsMouse
    readonly property bool pressed: mouseArea.pressed
    readonly property color contentColor: foregroundColor.a > 0 ? foregroundColor
                                          : !enabled ? _visualPalette.textSecondary
                                          : dangerStyle ? (_visualPalette.glassMode && _visualPalette.darkMode ? _visualPalette.surface : _visualPalette.primaryForeground)
                                          : successStyle ? _visualPalette.successForeground
                                          : tonal ? _visualPalette.primaryText : _visualPalette.primaryForeground
    signal clicked()

    implicitHeight: Theme.controlHeight
    implicitWidth: compact ? Theme.controlHeight : Math.max(Theme.controlHeight, buttonLabel.implicitWidth + (iconName.length > 0 ? glyphSize + contentSpacing : 0) + Theme.space32)
    opacity: enabled ? 1 : disabledOpacity
    radius: Theme.radiusControl
    readonly property color regularBackground: !enabled ? (_visualPalette.buttonDisabled || _visualPalette.surfaceContainerHigh)
                    : dangerStyle ? (mouseArea.containsMouse ? Qt.darker(_visualPalette.errorColor, 1.08) : _visualPalette.errorColor)
                    : successStyle ? (mouseArea.containsMouse ? Qt.darker(_visualPalette.success, 1.08) : _visualPalette.success)
                    : tonal ? (mouseArea.containsMouse ? _visualPalette.primaryContainerHover : _visualPalette.primaryContainer)
                            : (mouseArea.containsMouse ? _visualPalette.primaryHover : _visualPalette.primary)
    color: _visualPalette.glassMode ? Qt.rgba(regularBackground.r, regularBackground.g,
                                    regularBackground.b, 0.6) : regularBackground
    border.width: mouseArea.pressed ? Theme.borderWidthMedium : Theme.borderWidthThin
    border.color: !enabled ? _visualPalette.outline
                    : mouseArea.pressed ? _visualPalette.buttonShadow
                    : dangerStyle ? _visualPalette.errorColor
                    : mouseArea.containsMouse ? _visualPalette.primaryHover
                    : _visualPalette.primary

    GlassSurface {
        anchors.fill: parent; cornerRadius: root.radius
        tintColor: root.color; pressed: root.pressed
        minimumTintOpacity: 0.96
        visible: _visualPalette.glassMode && root.color.a > 0
    }

    RowLayout {
        anchors.verticalCenter: parent.verticalCenter
        x: root.contentFillWidth ? root.contentHorizontalPadding
                                 : Math.round((parent.width - width) / 2)
        width: root.contentFillWidth
               ? Math.max(0, parent.width - root.contentHorizontalPadding * 2)
               : implicitWidth
        spacing: root.contentSpacing
        MaterialIcon {
            id: buttonIcon
            visible: root.iconName.length > 0 && !root.iconComponent
            icon: root.iconName
            iconSize: root.glyphSize
            color: root.contentColor
        }
        Loader {
            Layout.preferredWidth: root.glyphSize
            Layout.preferredHeight: root.glyphSize
            visible: root.iconComponent !== null
            active: visible
            sourceComponent: root.iconComponent
        }
        Text {
            id: buttonLabel
            Layout.fillWidth: root.contentFillWidth
            Layout.minimumWidth: 0
            visible: !root.compact
            text: root.text
            color: root.contentColor
            font.pixelSize: root.labelFontSize
            font.weight: root.labelFontWeight
            elide: root.labelElide
        }
    }

    RotationAnimator {
        target: buttonIcon
        from: 0
        to: 360
        duration: Theme.motionSpinner
        loops: Animation.Infinite
        running: root.iconSpinning && buttonIcon.visible
        onRunningChanged: {
            if (!running)
                buttonIcon.rotation = 0
        }
    }

    HoverTips {
        visible: root.showHoverTips && root.enabled && mouseArea.containsMouse
        text: root.text
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }
}
