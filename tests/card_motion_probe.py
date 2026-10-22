"""Run real-time card motion with the app's default renderer, outside pytest-qt.

Usage: python tests/card_motion_probe.py build/card-motion-stress.json [decade|light|dark]
Uses temporary data and synthetic scripts; never executes a script or contacts devices.
Does not pause animations, grab frames, or force the basic/offscreen render loop.
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

import psutil
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QRectF, Qt, QTimer, QUrl, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtWidgets import QApplication

from poptools.domain.models import ExecutorDefinition, ParameterDefinition, ToolDefinition
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, package_root, resource_path
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.app_controller import AppController


class Probe(QObject):
    def __init__(self, app, component, backend, output, theme):
        super().__init__()
        self.app, self.component, self.backend, self.output = app, component, backend, output
        self.theme = theme
        self.mechanical = theme == "decade"
        self.window = None
        self.rows, self.errors, self.frames = [], [], []
        self.timer = QTimer(self)
        self.timer.setInterval(8)
        self.timer.timeout.connect(self.sample)
        self.process = psutil.Process()

    @Slot()
    def frame(self):
        self.frames.append(perf_counter())

    @Slot()
    def start(self):
        self.frames = []
        self.started = perf_counter()
        self.window = self.component.createWithInitialProperties({
            "deviceController": self.backend.android_controller,
            "presetUtilities": None, "jiraFeishuBackend": None})
        if self.window is None:
            raise RuntimeError(self.component.errors())
        # Never acquire Python's GIL from the render thread: synthetic input can
        # hold it while waiting for rendering, deadlocking even a timestamp-only
        # callback. These timestamps measure GUI delivery, not GPU presentation.
        self.window.frameSwapped.connect(self.frame, Qt.ConnectionType.QueuedConnection)
        area = self.app.primaryScreen().availableGeometry()
        self.window.setProperty("launchOrigin", QRectF(area.right() - 300,
                                                       area.center().y(), 280, 40))
        QMetaObject.invokeMethod(self.window, "showWithTool", Q_ARG("QVariant", "custom.probe"))
        self.handle = self.window.winId()
        self.size = self.window.size()
        self.session = self.window.property("toolController")
        self.live = self.window.findChild(QObject, "liveScriptCardContent")
        self.motion = self.window.findChild(QObject, "mechanicalCardMotion")
        self.mode = ("normal" if len(self.rows) < 20
                     else "activate" if len(self.rows) < 25 else "close")
        self.interrupted = False
        self.scan_samples = 0
        self.spin_samples = 0
        self.recycle_samples = 0
        self.hidden_samples = 0
        self.timer.start()

    @Slot()
    def sample(self):
        window = self.window
        elapsed = perf_counter() - self.started
        if not window.isVisible() and not (self.mode == "close" and self.interrupted
                                          and not window.property("recycleAnimationRunning")):
            self.hidden_samples += 1
        if window.isVisible() and (window.winId() != self.handle or window.size() != self.size):
            self.errors.append("Native window or surface size changed")
        if window.property("toolController") is not self.session:
            self.errors.append("Session changed")
        if window.findChild(QObject, "liveScriptCardContent") is not self.live:
            self.errors.append("Live form replaced")
        if 0 < self.motion.property("scan") < 1:
            self.scan_samples += 1
        if 0 < self.motion.property("spinAngle") < 360:
            self.spin_samples += 1
        if window.property("recycleAnimationRunning"):
            self.recycle_samples += 1
        if (self.mode != "normal" and not self.interrupted
                and elapsed > (.4 if self.mechanical else .08)
                and (self.mode != "activate" or not window.property("entryAnimationRunning"))):
            self.interrupted = True
            method = "activateCard" if self.mode == "activate" else "closeCardAnimated"
            QMetaObject.invokeMethod(window, method)
            if (self.mode == "activate" and self.mechanical
                    and not window.property("activationAnimationRunning")):
                self.errors.append("Activation rotation missing")
        if (not window.property("entryAnimationRunning")
                and not window.property("activationAnimationRunning")
                and not window.property("recycleAnimationRunning")) or elapsed > 5:
            self.timer.stop()
            if elapsed > 5:
                self.errors.append("Animation timed out")
            if self.hidden_samples:
                self.errors.append("Window hidden during animation")
            if self.mechanical and self.mode == "normal" and not self.scan_samples:
                self.errors.append("No scan frames")
            if self.mechanical and self.mode == "activate" and not self.spin_samples:
                self.errors.append("No rotation frames")
            if not self.mechanical and (self.spin_samples or window.property("focusScanRunning")):
                self.errors.append("Mechanical feedback in a standard theme")
            if self.mode == "close" and not self.recycle_samples:
                self.errors.append("No recycling frames")
            gaps = [(b - a) * 1000 for a, b in zip(self.frames, self.frames[1:], strict=False)]
            self.rows.append({"mode": self.mode, "elapsed_ms": round(elapsed * 1000, 2),
                              "frames": len(self.frames), "scan_samples": self.scan_samples,
                              "spin_samples": self.spin_samples,
                              "recycle_samples": self.recycle_samples,
                              "frame_gaps_ms": gaps,
                              "rss_mb": round(self.process.memory_info().rss / 1024 ** 2, 2)})
            window.frameSwapped.disconnect(self.frame)
            QMetaObject.invokeMethod(window, "dismissCard")
            window.deleteLater()
            self.window = None
            QTimer.singleShot(100, self.finish if elapsed > 5 or len(self.rows) == 30
                              else self.start)

    @Slot()
    def finish(self):
        normal = [row for row in self.rows if row["mode"] == "normal"]
        gaps = sorted(gap for row in normal for gap in row["frame_gaps_ms"])
        # A locked/occluded desktop can advance GUI timers while presenting only
        # startup frames. Such a run checks lifecycle, but cannot measure frame pacing.
        minimum_frames = 10 if self.mechanical else 5
        frame_timing_available = bool(normal) and all(
            row["frames"] >= minimum_frames for row in normal)
        residual = [w.objectName() for w in self.app.topLevelWindows()
                    if w.objectName() in ("recentToolWindow", "cardFlightWindow")]
        if residual:
            self.errors.append(f"Residual windows: {residual}")
        result = {"render_loop": os.getenv("QSG_RENDER_LOOP", "Qt default"),
                  "frame_measurement": "GUI delivery of queued frameSwapped signals",
                  "theme": self.theme,
                  "cycles": len(self.rows), "errors": self.errors,
                  "frame_timing_available": frame_timing_available,
                  "median_frame_ms": (round(statistics.median(gaps), 2)
                                      if frame_timing_available else None),
                  "p95_frame_ms": (round(gaps[int(len(gaps) * .95)], 2)
                                   if frame_timing_available else None),
                  "max_frame_ms": round(max(gaps), 2) if frame_timing_available else None,
                  "rows": self.rows}
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "rows"}))
        self.app.exit(bool(self.errors))


def main():
    theme = sys.argv[2] if len(sys.argv) > 2 else "decade"
    if theme not in ("decade", "light", "dark"):
        raise ValueError("Choose decade, light or dark")
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    with tempfile.TemporaryDirectory(prefix="poptools-card-probe-") as directory:
        paths = AppPaths(Path(directory))
        config = ConfigStore(paths)
        tool = ToolDefinition(id="custom.probe", title="连续抽卡压力测试", section="custom",
                              executor=ExecutorDefinition(kind="python", command="print('test')"),
                              parameters=[ParameterDefinition(id="message", label="测试内容",
                                                              default="Hello")])
        registry = ToolRegistry(Path(directory) / "builtin",
                                SimpleNamespace(list_tools=lambda: [tool]))
        environment = PythonEnvironment(paths, config)
        coordinator = ExecutionCoordinator(ExecutionManager(paths, environment), 3)
        android = AndroidController(config)
        android.stopAutoRefresh()
        backend = AppController(registry, coordinator, config, android)
        engine = QQmlEngine()
        engine.rootContext().setContextProperty("appController", backend)
        engine.rootContext().setContextProperty("probeTheme", theme)
        component = QQmlComponent(engine)
        component.setData(b'''
import QtQuick
import "components"
import "theme"
RecentToolDialog {
    Component.onCompleted: {
        Theme.darkMode = probeTheme !== "light"
        Theme.decadeMode = probeTheme === "decade"
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/CardStressHarness.qml")))
        probe = Probe(app, component, backend, Path(sys.argv[1]), theme)
        engine.warnings.connect(
            lambda messages: probe.errors.extend(m.toString() for m in messages))
        QTimer.singleShot(0, probe.start)
        return app.exec()


def supervised_main():
    """Keep a GUI-thread deadlock from leaving an unresponsive test on the desktop."""
    child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                              *sys.argv[1:], "--probe-worker"])
    try:
        return child.wait(timeout=90)
    except subprocess.TimeoutExpired:
        # The venv launcher can create a second Python process on Windows. Only
        # terminate this owned test tree, never another running app instance.
        try:
            descendants = psutil.Process(child.pid).children(recursive=True)
        except psutil.NoSuchProcess:
            descendants = []
        for process in reversed(descendants):
            with suppress(psutil.NoSuchProcess):
                process.kill()
        child.kill()
        child.wait(timeout=5)
        print("Card motion probe exceeded 90 seconds; its test windows were stopped.",
              file=sys.stderr)
        return 2


if __name__ == "__main__":
    if "--probe-worker" in sys.argv:
        sys.argv.remove("--probe-worker")
        sys.exit(main())
    sys.exit(supervised_main())
