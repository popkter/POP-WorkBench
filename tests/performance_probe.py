"""Repeatable local load test; run directly with an output JSON path.

Uses isolated data, real controllers/QML/native terminal and synthetic scripts.
No devices, downloads, user configuration or external services are used.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QSG_RENDER_LOOP", "basic")

import psutil
from PySide6.QtCore import Q_ARG, QMetaObject, QObject, QTimer, QUrl, Signal
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from poptools.domain.models import ExecutorDefinition, ToolDefinition
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.native_terminal import register_terminal_type
from poptools.paths import AppPaths, package_root
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.app_controller import AppController


class Devices(QObject):
    devicesChanged = Signal()
    refreshingChanged = Signal()
    devices = []
    refreshing = False

    def refresh(self):
        pass


def measure(action, count):
    samples = []
    for _ in range(count):
        start = time.perf_counter()
        action()
        samples.append((time.perf_counter() - start) * 1000)
    return {"median_ms": statistics.median(samples),
            "p95_ms": sorted(samples)[int(len(samples) * .95)], "iterations": count}


def main():
    app = QApplication([])
    register_terminal_type()
    result = {"platform": sys.platform, "rendering": "offscreen/software", "tools": 1000}
    with tempfile.TemporaryDirectory(prefix="poptools-perf-") as directory:
        paths = AppPaths(Path(directory))
        config = ConfigStore(paths)
        tools = [ToolDefinition(id=f"custom.{i}", section="custom", title=f"Script {i:04}",
                 executor=ExecutorDefinition(kind="python", command="print('hello')"))
                 for i in range(1000)]
        registry = ToolRegistry(Path(directory) / "builtin",
                                SimpleNamespace(list_tools=lambda: tools))
        environment = PythonEnvironment(paths, config)
        coordinator = ExecutionCoordinator(ExecutionManager(paths, environment), 3)
        android = AndroidController(config, Devices())
        android.stopAutoRefresh()
        backend = AppController(registry, coordinator, config, android)
        backend._analysis_timer.stop()
        result["config_1000_reads"] = measure(config.tool_usage_counts, 1000)
        result["usage_record"] = measure(lambda: backend._record_tool_usage(tools[0]), 100)
        engine = QQmlEngine()
        engine.rootContext().setContextProperty("backend", backend)
        engine.rootContext().setContextProperty("android", android)
        component = QQmlComponent(engine)
        component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
import PopTools.Terminal 1.0
ApplicationWindow {
    id: host; width: 1100; height: 800; visible: true
    CustomScriptsPage {
        anchors.fill: parent; controller: backend; androidBackend: android
        parentWindow: host; parameterValues: ({})
    }
    TerminalView {
        objectName: "stressTerminal"; width: 960; height: 600
        visible: false; sessionId: "stress"
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/PerformanceHarness.qml")))
        window = component.create()
        if window is None:
            raise RuntimeError([e.toString() for e in component.errors()])
        QTest.qWait(200)
        resets = []
        backend.toolsModel.modelReset.connect(lambda: resets.append(1))
        result["unchanged_list_refresh"] = measure(
            lambda: (backend._refresh(notify_selected=False), app.processEvents()), 100)
        result["list_resets"] = len(resets)
        large = tools[0].model_copy(deep=True)
        large.executor.command = (
            "x = 1\n" * 2000 + "import subprocess\nsubprocess.run(['adb', 'devices'])"
        )
        backend._analyze_tool(large)
        result["adb_2000_lines"] = measure(lambda: backend._analyze_tool(large), 100)
        terminal = window.findChild(QObject, "stressTerminal")
        def feed():
            QMetaObject.invokeMethod(terminal, "feed", Q_ARG(str, "stress"),
                                     Q_ARG(str, "terminal output 0123456789\r\n" * 1000))
        feed()
        result["native_50000_lines"] = measure(feed, 50)
        result["native_history_lines"] = terminal.property("scrollbackLineCount")
        process = psutil.Process()
        rss_start = process.memory_info().rss
        cpu_start = sum(process.cpu_times()[:2])
        ticks, frames = [], []
        heartbeat = QTimer()
        heartbeat.setInterval(10)
        heartbeat.timeout.connect(lambda: ticks.append(time.perf_counter()))
        window.frameSwapped.connect(lambda: frames.append(time.perf_counter()))
        output = QTimer()
        output.setInterval(10)
        chunk = "script output 0123456789 abcdefghijklmnopqrstuvwxyz\n" * 20
        output.timeout.connect(lambda: backend._queue_console(tools[0].id, chunk))
        heartbeat.start()
        output.start()
        QTest.qWait(5000)
        output.stop()
        heartbeat.stop()
        gaps = [(b-a)*1000 for a, b in zip(ticks, ticks[1:], strict=False)]
        result["console_5_seconds"] = {
            "target_bytes_per_second": len(chunk) * 100,
            "heartbeat_p95_ms": sorted(gaps)[int(len(gaps)*.95)],
            "heartbeat_max_ms": max(gaps), "frames": len(frames),
            "cpu_seconds": sum(process.cpu_times()[:2]) - cpu_start,
            "rss_growth_mb": (process.memory_info().rss - rss_start) / 1024**2,
        }
        if "--stress" in sys.argv:
            # Five real child processes, three independent execution windows,
            # bounded output buffers and the regular application event loop.
            import gc
            gc.collect()
            coordinator.set_ordinary_limit(5)
            sessions, windows, components = [], [], []
            for index in range(3):
                session = backend.createToolSession(tools[index].id)
                sessions.append(session)
                dialog = QQmlComponent(engine)
                dialog.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host; width: 600; height: 600; visible: true
    required property var session
    CustomToolDetailPanel {
        anchors.fill: parent; controller: host.session; androidBackend: android
        parentWindow: host; parameterValues: ({}); displayedTool: host.session.selectedTool
        splitConsole: true; consoleExpanded: true
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/StressDialog.qml")))
                dialog_window = dialog.createWithInitialProperties({"session": session})
                if dialog_window is None:
                    raise RuntimeError([e.toString() for e in dialog.errors()])
                windows.append(dialog_window)
                components.append(dialog)
            finished, output_sizes, memory = [], [], []
            coordinator.finished.connect(lambda tool_id, code: finished.append((tool_id, code)))
            coordinator.output.connect(lambda tool_id, text: output_sizes.append(len(text)))
            command = (
                "import sys,time\n"
                "end=time.monotonic()+60\n"
                "while time.monotonic()<end:\n"
                " sys.stdout.write('x'*1000+'\\n');sys.stdout.flush();time.sleep(.02)\n"
            )
            ticks.clear()
            frames.clear()
            sampler = QTimer()
            sampler.setInterval(1000)
            sampler.timeout.connect(lambda: memory.append(process.memory_info().rss / 1024**2))
            sampler.start()
            heartbeat.start()
            cpu_start = sum(process.cpu_times()[:2])
            started = time.perf_counter()
            for definition in tools[:5]:
                execution_tool = definition.model_copy(deep=True)
                execution_tool.executor.command = command
                if not coordinator.start(execution_tool, {}):
                    raise RuntimeError("Stress process could not start")
            while len(finished) < 5 and time.perf_counter() - started < 75:
                QTest.qWait(100)
            elapsed = time.perf_counter() - started
            sampler.stop()
            heartbeat.stop()
            gaps = [(b-a)*1000 for a, b in zip(ticks, ticks[1:], strict=False)]
            result["real_process_stress"] = {
                "seconds": elapsed, "processes": 5, "execution_windows": 3,
                "finished": finished, "output_mb": sum(output_sizes) / 1024**2,
                "heartbeat_p95_ms": sorted(gaps)[int(len(gaps)*.95)],
                "heartbeat_max_ms": max(gaps), "main_window_frames": len(frames),
                "cpu_seconds": sum(process.cpu_times()[:2]) - cpu_start,
                "peak_rss_mb": max(memory),
                "rss_last_10s_growth_mb": memory[-1] - memory[-10] if len(memory) >= 10 else None,
            }
            for definition in tools[:5]:
                coordinator.stop(definition.id)
            for dialog_window in windows:
                dialog_window.close()
                dialog_window.deleteLater()
            for session in sessions:
                session.dispose()
            QTest.qWait(100)
            if len(finished) != 5 or any(code != 0 for _, code in finished):
                raise RuntimeError(f"Stress processes failed: {finished}")
        window.close()
        window.deleteLater()
        app.processEvents()
    Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
