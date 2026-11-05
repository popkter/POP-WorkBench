"""Verify real occluded-window capture through the actual Glass renderer.

The background belongs to a separate process. Only these controlled test
windows are saved as images. No desktop or third-party app screenshots are saved.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def background() -> int:
    app = QApplication([])
    engine = QQmlApplicationEngine()
    engine.loadData(b'''
import QtQuick
Window {
    id: host; width: Screen.width; height: Screen.height; x: 0; y: 0; visible: true
    flags: Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
    property color fill: "#d72e46"
    color: fill
    Repeater {
        model: Math.ceil(host.width / 110)
        Rectangle {
            required property int index
            x: index * 110; width: 30; height: host.height; color: "#b0ffffff"
        }
    }
    Repeater {
        model: Math.ceil(host.height / 90)
        Rectangle {
            required property int index
            y: index * 90; width: host.width; height: 14; color: "#50ffffff"
        }
    }
    Rectangle { x: 420; y: 260; width: 150; height: 130; color: "#1649ed" }
    Text { x: 90; y: 220; text: "REAL WINDOW BEHIND GLASS"; font.pixelSize: 34; color: "white" }
}
''')
    window = engine.rootObjects()[0]
    window.setProperty("fill", QColor(os.environ.get("POPTOOLS_PROOF_BACKGROUND", "#d72e46")))
    ctypes.WinDLL("user32").AllowSetForegroundWindow(ctypes.c_uint(-1))

    class Commands(QObject):
        color = Signal(str)

    commands = Commands()
    def apply_color(value: str) -> None:
        window.setProperty("fill", QColor(value))
        window.update()

    commands.color.connect(apply_color)

    def read() -> None:
        for line in sys.stdin:
            commands.color.emit(line.strip())

    threading.Thread(target=read, daemon=True).start()
    QTimer.singleShot(200, lambda: print("READY", flush=True))
    return app.exec()


def verify() -> int:
    from poptools.infrastructure.desktop_backdrop import (
        SystemBackdropController,
        prepare_system_backdrops,
    )
    from poptools.infrastructure.window_chrome import WindowChromeController

    background_environment = os.environ.copy()
    if "--white" in sys.argv or "--black" in sys.argv:
        background_environment["POPTOOLS_PROOF_BACKGROUND"] = (
            "#ffffff" if "--white" in sys.argv else "#000000")
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--background"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                             env=background_environment)
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "READY"
        if "--application" in sys.argv:
            mode = ("decade" if "--decade" in sys.argv else "zio" if "--zio" in sys.argv
                    else "light" if "--light" in sys.argv else "dark")
            section = "developer" if "--terminal" in sys.argv else "custom"
            suffix = "-settings" if "--settings" in sys.argv else (
                "-terminal" if "--terminal" in sys.argv else
                "-card" if "--card" in sys.argv else "")
            if "--white" in sys.argv or "--black" in sys.argv:
                suffix += "-white" if "--white" in sys.argv else "-black"
            environment = os.environ.copy()
            environment.update({
                "PYTHONPATH": str(ROOT / "src"),
                "POPTOOLS_DATA_DIR": str(ROOT / "build/glass-native-app-proof-data"),
                "POPTOOLS_CAPTURE_THEME": mode,
                "POPTOOLS_CAPTURE_THEME_STYLE": "glass",
                "POPTOOLS_CAPTURE_GRID_SAMPLE": "1",
                "POPTOOLS_CAPTURE_QML_WARNINGS": "1",
                "POPTOOLS_CAPTURE_WINDOW_FRAME": "1",
                "POPTOOLS_CAPTURE_COMPOSITED_FRAME": "1",
                "POPTOOLS_CAPTURE_RENDERED_FRAME": "0",
                "POPTOOLS_CAPTURE_WAIT_DESKTOP": "1",
                "QT_QUICK_BACKEND": "rhi",
            })
            if "--settings" in sys.argv:
                environment["POPTOOLS_CAPTURE_DIALOG"] = "settings"
            if "--card" in sys.argv:
                environment["POPTOOLS_CAPTURE_DIALOG"] = "recent-tool"
            if "--terminal" in sys.argv:
                environment["POPTOOLS_CAPTURE_TERMINAL_SAMPLE"] = "faint"
            return subprocess.run([
                sys.executable, str(ROOT / "tests/capture_ui.py"),
                str(ROOT / f"build/glass-system-{mode}{suffix}.png"), section, "__dynamic__",
            ], env=environment, check=False).returncode

        app = QApplication([])
        prepare_system_backdrops()
        engine = QQmlApplicationEngine()
        controller = SystemBackdropController(app)
        app.aboutToQuit.connect(controller.shutdown)
        engine.rootContext().setContextProperty("systemBackdropController", controller)
        config = json.loads((ROOT / "src/poptools/ui/qml/theme/configs/glass.json").read_text())
        component = '''
import QtQuick
import "components"
import "theme"
Window {
    id: host; width: 620; height: 400; x: 280; y: 160; visible: false
    flags: Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowStaysOnTopHint
    property bool customTitleBar: true
    property int captionControlWidth: 47
    property real titleBarHeight: 40
    property rect titleBarActionsRect
    property int captionHovered: -1
    property int captionPressed: -1
    property bool modernCaptionControls: true
    property var chromeController: null
    property real nativeTitleBarHeight: 0
    readonly property bool glassEnabled: Theme.glassMode
    readonly property bool glassBackgroundReady: desktop.ready
    readonly property bool systemBackdropTinted: desktop.drawBackground
    readonly property string backdropError: desktop.error
    property var config: CONFIG
    color: desktop.ready ? "transparent" : Theme.surface
    Binding { target: Theme; property: "glassMode"; value: true }
    Binding { target: Theme; property: "darkMode"; value: false }
    Binding { target: Theme; property: "glassPalette"; value: host.config.colors }
    Binding { target: Theme; property: "glassMaterial"; value: host.config.material }
    DesktopBackground { id: desktop; hostWindow: host; anchors.fill: parent }
    GlassSurface { x: 90; y: 70; width: 440; height: 260; cornerRadius: 40 }
    Rectangle { width: 50; height: 24; color: "#ffb000" }
    Text { x: 24; y: 350; text: "DWM DESKTOP ACRYLIC"; color: Theme.textPrimary }
}
'''.replace("CONFIG", json.dumps(config))
        if "--frameless" in sys.argv:
            component = component.replace("property bool customTitleBar: true",
                                          "property bool customTitleBar: false").replace(
                "Qt.WindowTitleHint | Qt.WindowSystemMenuHint", "Qt.FramelessWindowHint")
        if "--card" in sys.argv:
            component = component.replace("property bool customTitleBar: true", """
    property bool customTitleBar: false
    property bool nativeCardFrame: true
    Component.onCompleted: systemBackdropController.prepareCardWindow(host)
""")
            component = component.replace("Qt.WindowTitleHint | Qt.WindowSystemMenuHint",
                                          "Qt.CustomizeWindowHint")
        engine.loadData(component.encode(), QUrl.fromLocalFile(
            str(ROOT / "src/poptools/ui/qml/SystemGlassProof.qml")))
        assert engine.rootObjects()
        window = engine.rootObjects()[0]
        chrome = WindowChromeController(window)
        window.raise_()
        window.requestActivate()
        user = ctypes.WinDLL("user32")
        user.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                                      ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
        user.SetWindowPos(int(window.winId()), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0003)
        foreground = user.GetForegroundWindow()
        thread = user.GetWindowThreadProcessId(ctypes.c_void_p(foreground), None)
        current_thread = ctypes.WinDLL("kernel32").GetCurrentThreadId()
        attached = user.AttachThreadInput(current_thread, thread, True)
        try:
            assert user.SetForegroundWindow(ctypes.c_void_p(int(window.winId())))
        finally:
            if attached:
                user.AttachThreadInput(current_thread, thread, False)
        output = ROOT / "build/glass-system-proof"
        output.mkdir(parents=True, exist_ok=True)
        frames = []
        started = time.monotonic()
        changed_at = 0.0
        moved_at = 0.0
        movement_index = 0
        steps = ((44, 58), (-31, -42), (11, 19))
        position = (window.x(), window.y())
        results = []
        timer = QTimer()
        swap_times = []
        window.frameSwapped.connect(lambda: swap_times.append(time.monotonic()))
        initial_swaps = 0

        def screenshot():
            # Test-only readback of DWM output; never supplied to the application.
            return window.screen().grabWindow(
                0, window.x(), window.y(), window.width(), window.height()).toImage()

        def pixel(image, x, y):
            dpr = image.devicePixelRatio()
            return image.pixelColor(round(x * dpr), round(y * dpr))

        def check():
            nonlocal changed_at, moved_at, movement_index, initial_swaps
            if time.monotonic() - started > 20:
                screenshot().save(str(output / "failed.png"))
                print("FAIL", window.property("backdropError"), "active", window.isActive(),
                      "alpha", window.format().alphaBufferSize(), "position", window.position(),
                      "geometry", window.geometry(), "color", window.color().name(),
                      window.color().alpha(), "api", window.rendererInterface().graphicsApi(),
                      flush=True)
                results.append(False)
                app.quit()
                return
            if not window.property("glassBackgroundReady") or time.monotonic() - started < 1.0:
                return
            current = screenshot()
            if moved_at:
                if time.monotonic() - moved_at < 0.5:
                    return
                # The blue block's global center is unchanged after every move.
                blue = pixel(current, 495 - window.x(), 325 - window.y())
                assert blue.blue() > blue.red() + 5, ("Global blue block moved", blue.name())
                movement_index += 1
                if movement_index < len(steps):
                    dx, dy = steps[movement_index]
                    window.setPosition(position[0] + dx, position[1] + dy)
                    moved_at = time.monotonic()
                    return
                current.save(str(output / "moved.png"))
                print("PASS: DWM live blur and globally anchored blue block; no capture backend",
                      flush=True)
                print("Foreground frames during background update:",
                      len(swap_times) - initial_swaps, flush=True)
                results.append(True)
                app.quit()
                return
            marker = pixel(current, 10, 10)
            if marker.red() < 230 or marker.green() < 130 or marker.blue() > 40:
                return
            color = pixel(current, 55, 50)
            if not frames:
                if color.red() <= color.green() + 3:
                    return
                current.save(str(output / "red.png"))
                frames.append(current)
                initial_swaps = len(swap_times)
                assert child.stdin is not None
                child.stdin.write("#22984d\n")
                child.stdin.flush()
                changed_at = time.monotonic()
                return
            if time.monotonic() - changed_at < 1.0 or color.green() <= color.red() + 3:
                return
            current.save(str(output / "green.png"))
            assert "windows_capture" not in sys.modules
            dx, dy = steps[0]
            window.setPosition(position[0] + dx, position[1] + dy)
            moved_at = time.monotonic()

        timer.timeout.connect(check)
        timer.start(150)
        app.exec()
        controller.shutdown()
        del chrome
        return 0 if results == [True] else 1
    finally:
        child.terminate()
        child.wait(timeout=5)


if __name__ == "__main__":
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    raise SystemExit(background() if "--background" in sys.argv else verify())
