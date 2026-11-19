import QtQuick
import QtQuick.Effects
import QtQuick.Window
import "../theme"

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root

    property color fillColor: _visualPalette.popupSurface
    property color outlineColor: _visualPalette.outlineVariant
    property int cornerRadius: Theme.radiusMedium
    property bool dialogSurface: false
    // Hosts without an isolated page texture (e.g. floating cards) need an
    // almost opaque popup so controls below it cannot bleed through.
    property real minimumOpacity: 0.97
    property bool tooltipSurface: false
    readonly property var hostWindow: root.Window.window
    readonly property Item pageBackgroundSource: _visualPalette.glassMode && hostWindow
        && hostWindow.popupBackgroundSource !== undefined ? hostWindow.popupBackgroundSource : null
    property Item backgroundSource: pageBackgroundSource || glassLens.windowBackgroundSource
    readonly property bool usesPageBackground: !!pageBackgroundSource && backgroundSource === pageBackgroundSource
    DesktopBackground {
        id: popupBackdrop
        hostWindow: root.hostWindow
        drawBackground: false
        // Popup.Item shares the main window; only a separate Popup.Window
        // needs another native backdrop, with its own lifetime.
        enabledForWindow: !root.usesPageBackground && root.visible && !!root.hostWindow
            && root.hostWindow.glassBackgroundReady === undefined
    }

    MultiEffect {
        anchors.fill: surface
        source: surface
        autoPaddingEnabled: true
        shadowEnabled: true
        shadowColor: root.dialogSurface ? _visualPalette.dialogShadow : _visualPalette.popupShadow
        shadowBlur: root.dialogSurface ? 0.9 : 0.65
        shadowVerticalOffset: root.dialogSurface ? 18 : 10
        shadowHorizontalOffset: 0
    }

    GlassSurface {
        id: glassLens
        anchors.fill: parent; cornerRadius: root.cornerRadius
        tintColor: root.usesPageBackground && !_visualPalette.darkMode && !root.tooltipSurface
            ? Theme.glassMaterial.lightPagePopupTint || "#A6B3C5" : root.fillColor
        opacityFloor: root.usesPageBackground
            ? (root.tooltipSurface ? Theme.glassMaterial.pageTooltipOpacity || 0.88
                : _visualPalette.darkMode ? Theme.glassMaterial.darkPagePopupOpacity || 0.72
                    : Theme.glassMaterial.pagePopupOpacity || 0.32) : root.minimumOpacity
        minimumTintOpacity: root.usesPageBackground ? opacityFloor
            : _visualPalette.darkMode ? (windowBackdropTinted ? Theme.glassMaterial.surfaceOpacity || 0.16 : 0.55)
                : (windowBackdropTinted ? Theme.glassMaterial.lightSurfaceOpacity || 0.1 : 0.4)
        backgroundBaseColor: root.usesPageBackground && !_visualPalette.darkMode
            ? Theme.glassMaterial.lightPageBackdropColor || "#B6C2D2" : _visualPalette.surface
        tintStrength: root.usesPageBackground ? opacityFloor
            : _visualPalette.darkMode ? Theme.glassMaterial.darkTintStrength || 0.32
                : Theme.glassMaterial.lightTintStrength || 0.25
        blurRadius: root.usesPageBackground ? Theme.glassMaterial.popupBlurRadius || 64 : -1
        backgroundSource: root.backgroundSource
        systemBackdropActive: root.hostWindow && root.hostWindow.glassBackgroundReady !== undefined
            ? root.hostWindow.glassBackgroundReady : popupBackdrop.ready
    }
    Rectangle {
        id: surface
        anchors.fill: parent
        radius: root.cornerRadius
        color: _visualPalette.glassMode ? "transparent" : root.fillColor
        border.color: root.outlineColor
        border.width: 1
    }
}
