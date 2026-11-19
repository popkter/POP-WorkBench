import QtQuick
import QtQuick.Window
import "../theme"
import "glass/LiquidGlass" as Liquid

Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    property real cornerRadius: Theme.radiusMedium
    property color tintColor: _visualPalette.surfaceContainerLow
    property real tintStrength: _visualPalette.darkMode
        ? (Theme.glassMaterial.darkTintStrength === undefined ? 0.32 : Theme.glassMaterial.darkTintStrength)
        : (Theme.glassMaterial.lightTintStrength === undefined ? 0.65 : Theme.glassMaterial.lightTintStrength)
    property real opacityFloor: 0
    property real blurRadius: -1
    property color backgroundBaseColor: _visualPalette.surface
    // Semantic controls opt into a stronger tint; the optical rim stays live.
    property real minimumTintOpacity: _visualPalette.darkMode
        ? (windowBackdropTinted ? Theme.glassMaterial.surfaceOpacity || 0.16 : 0.55)
        : (windowBackdropTinted ? Theme.glassMaterial.lightSurfaceOpacity || 0.1 : 0.4)
    property bool pressed: false
    property bool pointerReactive: false
    // State highlights overlay an existing readable surface even without DWM.
    property bool overlay: false
    readonly property real effectiveTintOpacity: Math.max(root.opacityFloor,
        root.minimumTintOpacity, root.tintColor.a * root.tintStrength)
    readonly property var host: root.Window.window
    property bool systemBackdropActive: host && host.glassBackgroundReady !== undefined
        && host.glassBackgroundReady
    readonly property bool windowBackdropTinted: host && host.systemBackdropTinted !== undefined
        && host.systemBackdropTinted
    // Sample an actual lower layer, never an ancestor containing this glass.
    readonly property Item windowBackgroundSource: {
        let candidate = host
        while (candidate) {
            if (candidate.glassBackgroundSource !== undefined && candidate.glassBackgroundSource)
                return candidate.glassBackgroundSource
            candidate = candidate.transientParent || null
        }
        return null
    }
    property Item backgroundSource: windowBackgroundSource
    readonly property point sourcePosition: {
        let node = root
        let geometryRevision = 0
        while (node) {
            geometryRevision += node.x + node.y + node.width + node.height
            node = node.parent
        }
        return backgroundSource ? root.mapToItem(backgroundSource, 0, 0) : Qt.point(0, 0)
    }
    readonly property bool effectsAvailable: GraphicsInfo.api !== GraphicsInfo.Software
    visible: _visualPalette.glassMode

    Loader {
        anchors.fill: parent
        active: root.visible && root.effectsAvailable
        sourceComponent: root.backgroundSource ? opticalComponent : nativeComponent
    }
    Component {
        id: opticalComponent
        Liquid.GlassSurface {
            id: opticalSurface
            anchors.fill: parent
            visible: root.effectsAvailable
            backdrop: root.visible ? root.backgroundSource : null
            backdropColor: root.backgroundBaseColor
            radius: root.cornerRadius
            dark: _visualPalette.darkMode
            blurRadius: root.blurRadius
            toneLift: _visualPalette.darkMode ? (Theme.glassMaterial.darkLift || 0) : 0
            tintAmount: Theme.glassMaterial.tintAmount === undefined ? 35 : Theme.glassMaterial.tintAmount
            tint: [root.tintColor.r, root.tintColor.g, root.tintColor.b,
                   Math.max(root.opacityFloor, root.minimumTintOpacity, root.tintColor.a * root.tintStrength)]
            touch: hover.point.position
            touchAmount: root.pointerReactive ? (root.pressed ? 1 : hover.hovered ? 0.35 : 0) : 0
            Behavior on touchAmount { NumberAnimation { duration: 140 } }
            followsMovement: root.visible && root.backgroundSource !== null
        }
    }
    Component {
        id: nativeComponent
        ShaderEffect {
            anchors.fill: parent
            fragmentShader: "glass/LiquidGlass/shaders/nativeglass.frag.qsb"
            property point uSize: Qt.point(width, height)
            property real uRadius: root.cornerRadius
            property vector4d uTint: Qt.vector4d(root.tintColor.r, root.tintColor.g, root.tintColor.b,
                root.systemBackdropActive || root.overlay ? root.effectiveTintOpacity : 1)
            property point uTouch: hover.point.position
            property real uTouchAmount: root.pointerReactive ? (root.pressed ? 1 : hover.hovered ? 0.35 : 0) : 0
            Behavior on uTouchAmount { NumberAnimation { duration: 140 } }
        }
    }
    Rectangle {
        anchors.fill: parent
        visible: !root.effectsAvailable
        radius: root.cornerRadius
        color: root.tintColor
        opacity: root.systemBackdropActive || root.overlay ? root.effectiveTintOpacity : 1
    }
    HoverHandler { id: hover; enabled: root.pointerReactive }
}
