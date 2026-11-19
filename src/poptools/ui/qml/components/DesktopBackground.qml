import QtQuick
import QtQuick.Window
import "../theme"

// Only configures DWM. No images, timers or window-local desktop textures.
Item {
    readonly property var _visualPalette: Theme.paletteFor(this)

    id: root
    required property var hostWindow
    property bool drawBackground: true
    property bool enabledForWindow: true
    readonly property var backend: typeof systemBackdropController !== "undefined"
        ? systemBackdropController : null
    readonly property bool active: enabledForWindow && _visualPalette.glassMode && !!hostWindow && hostWindow.visible
        && hostWindow.visibility !== Window.Minimized
    property bool ready: false
    property string error: ""
    property bool configured: false

    function synchronize() {
        if (!active) {
            if (backend && configured && hostWindow) backend.configure(hostWindow, false, _visualPalette.darkMode)
            configured = false
            ready = false
            error = ""
            return
        }
        if (!backend) {
            ready = false
            error = active ? "系统背景服务不可用" : ""
            return
        }
        error = backend.configure(hostWindow, active, _visualPalette.darkMode)
        ready = active && error.length === 0
        configured = ready
    }
    onActiveChanged: synchronize()
    Component.onCompleted: synchronize()
    Component.onDestruction: { if (backend && configured) backend.release(hostWindow) }
    Connections {
        target: Theme
        function onDarkModeChanged() { root.synchronize() }
    }
    Rectangle {
        anchors.fill: parent
        visible: root.active && root.drawBackground
        // A cheap constant theme film bounds contrast over very bright/dark
        // desktops. DWM still owns and updates all pixels underneath it.
        color: root.ready ? (Theme.glassPalette.desktopTint || "transparent") : _visualPalette.surface
    }
}
