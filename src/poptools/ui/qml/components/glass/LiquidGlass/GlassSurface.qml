// Modified for PopToolProject: pointer controls, theme lift and synchronous layout uniforms.
// Apache-2.0. A rounded piece of Liquid Glass with children on top. It refracts `backdrop` live, every
// frame: a ShaderEffectSource renders the part of the backdrop under the glass, and GlassEffect runs the
// production material over it. Put it over the backdrop (siblings in the same parent, say), never inside it.
import QtQuick
import QtQuick.Effects
import "material.js" as Material

Item {
    id: root

    /** The item the glass refracts: the page, a ListView, an Image. Keep the glass outside it. */
    property point touch: Qt.point(width / 2, height / 2)
    property real touchAmount: 0
    // Negative keeps the upstream material's default lift.
    property real toneLift: -1
    // PopToolProject: explicit in-app popup frost, in logical pixels.
    property real blurRadius: -1
    property Item backdrop
    /** What the glass sees where the backdrop is transparent (a ListView's empty margins, say): the
        window's colour, usually. The material needs an opaque backdrop. */
    property color backdropColor: "white"
    /** Corner radius, logical pixels. */
    property real radius: 20
    /** The dark material. */
    property bool dark: false
    /** 0 to 100. */
    property real tintAmount: 50
    /** Toward the light (y up is negative); Qt.point(0, -1) is iOS 27's measured overhead light. */
    property point light: Qt.point(-0.35, -0.94)
    /** [r, g, b, a] in sRGB 0..1 replacing the tint colour and opacity, or null. */
    property var tint: null
    /** 0 to 1: glass materializes in and out rather than fading. */
    property real materialize: 1
    /** 0 to 1, the accessibility settings. */
    property real reducedTransparency: 0
    property real increasedContrast: 0
    /** Re-map the glass onto the backdrop every frame, for glass or a backdrop that moves without
        changing its geometry properties (inside an animated parent, say). A backdrop that scrolls its
        own content, like a ListView, needs none of this: the glass stays where it is over it. */
    property bool followsMovement: false
    /** Children are drawn on top of the glass. */
    default property alias content: contentItem.data
    /** The shader's status (ShaderEffect.Compiled 0, Uncompiled 1, Error 2) and its log, for diagnostics.
        An int, so hosts that cannot convert the enum (PySide) can read it. */
    readonly property int shaderStatus: effect.status
    readonly property string shaderLog: effect.log

    // Two device pixels around the glass for the outer contour, as in every port.
    readonly property real dpr: Screen.devicePixelRatio > 0 ? Screen.devicePixelRatio : 1
    readonly property real padUnits: 2 / dpr

    function updateSourceRect() {
        if (!backdrop) return
        const r = backdrop.mapFromItem(root, -padUnits, -padUnits, width + 2 * padUnits, height + 2 * padUnits)
        if (r.x !== backdropTexture.sourceRect.x || r.y !== backdropTexture.sourceRect.y ||
                r.width !== backdropTexture.sourceRect.width || r.height !== backdropTexture.sourceRect.height)
            backdropTexture.sourceRect = r
    }

    function updateUniforms() {
        if (!visible || !effect || width <= 0 || height <= 0) return
        const values = Material.uniforms({
            radius: radius, dark: dark, tintAmount: tintAmount, light: [light.x, light.y], tint: tint,
            materialize: materialize, reducedTransparency: reducedTransparency, increasedContrast: increasedContrast,
        }, width * dpr, height * dpr, dpr)
        values.uBase = [backdropColor.r, backdropColor.g, backdropColor.b]
        if (toneLift >= 0) values.uLift = [toneLift]
        if (blurRadius >= 0) {
            // The page texture is already Gaussian-blurred by MultiEffect.
            // Keep refraction/highlights without sparse-kernel text echoes.
            values.uBlur = [0]
            values.uWideKernel = [1]
            values.uFineShare = [1]
        }
        values.uTouch = [touch.x * dpr, touch.y * dpr]
        values.uTouchAmt = [touchAmount]
        effect.setUniforms(values)
    }

    ShaderEffectSource {
        id: backdropTexture
        width: effect.width
        height: effect.height
        sourceItem: root.blurRadius < 0 ? root.backdrop : null
        live: true
        hideSource: false
        visible: false
        smooth: true
        textureSize: Qt.size(Math.ceil(effect.width * root.dpr), Math.ceil(effect.height * root.dpr))
    }

    Item {
        id: opaquePage
        width: effect.width; height: effect.height
        visible: root.blurRadius >= 0
        Rectangle { anchors.fill: parent; color: root.backdropColor }
        ShaderEffectSource {
            anchors.fill: parent
            sourceItem: root.blurRadius >= 0 ? root.backdrop : null
            sourceRect: backdropTexture.sourceRect
            textureSize: backdropTexture.textureSize
            live: true
            smooth: true
        }
    }
    ShaderEffectSource {
        id: opaquePageTexture
        sourceItem: root.blurRadius >= 0 ? opaquePage : null
        hideSource: true
        live: true
        visible: false
        width: effect.width; height: effect.height
        textureSize: backdropTexture.textureSize
    }
    MultiEffect {
        id: frostedBackdrop
        x: -root.padUnits; y: -root.padUnits
        width: effect.width; height: effect.height
        visible: root.blurRadius >= 0
        source: opaquePageTexture
        autoPaddingEnabled: false
        blurEnabled: true
        blurMax: 64
        blur: Math.min(1, Math.max(0, root.blurRadius) / 64)
        blurMultiplier: Math.max(0, root.blurRadius / 64 - 1)
    }
    ShaderEffectSource {
        id: frostedTexture
        sourceItem: root.blurRadius >= 0 ? frostedBackdrop : null
        hideSource: true
        live: true
        visible: false
        width: effect.width; height: effect.height
        textureSize: backdropTexture.textureSize
    }

    GlassEffect {
        id: effect
        x: -root.padUnits
        y: -root.padUnits
        width: root.width + 2 * root.padUnits
        height: root.height + 2 * root.padUnits
        source: root.blurRadius >= 0 ? frostedTexture : backdropTexture
        field: effect.source   // the shape is analytic; the field is bound but unread
        uLayerSize: Qt.point(width * root.dpr, height * root.dpr)
    }

    Item {
        id: contentItem
        anchors.fill: parent
    }

    FrameAnimation {
        running: root.followsMovement && root.visible && root.backdrop !== null
        onTriggered: root.updateSourceRect()
    }
    onVisibleChanged: { if (visible) updateUniforms() }
    onTouchChanged: updateUniforms()
    onToneLiftChanged: updateUniforms()
    onBlurRadiusChanged: updateUniforms()
    onTouchAmountChanged: updateUniforms()
    onXChanged: updateSourceRect()
    onYChanged: updateSourceRect()
    Connections {
        target: root.backdrop
        ignoreUnknownSignals: true
        function onXChanged() { root.updateSourceRect() }
        function onYChanged() { root.updateSourceRect() }
        function onWidthChanged() { root.updateSourceRect() }
        function onHeightChanged() { root.updateSourceRect() }
    }

    // Layout can resize during scene-graph polish. Deferred uniform updates
    // would render one frame with a different lens size than its texture.
    onWidthChanged: { updateUniforms(); updateSourceRect() }
    onHeightChanged: { updateUniforms(); updateSourceRect() }
    onRadiusChanged: updateUniforms()
    onDarkChanged: updateUniforms()
    onTintAmountChanged: updateUniforms()
    onLightChanged: updateUniforms()
    onTintChanged: updateUniforms()
    onMaterializeChanged: updateUniforms()
    onReducedTransparencyChanged: updateUniforms()
    onIncreasedContrastChanged: updateUniforms()
    onBackdropColorChanged: updateUniforms()
    onDprChanged: updateUniforms()
    onBackdropChanged: updateSourceRect()
    Component.onCompleted: { updateUniforms(); updateSourceRect() }
}
