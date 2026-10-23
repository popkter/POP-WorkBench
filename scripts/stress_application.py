"""Wall-clock application soak using isolated data and harmless local workloads.

External devices, account credentials, package downloads and updates are excluded;
their boundary/failure tests belong in pytest. The real Main.qml and controllers
remain alive throughout. Offscreen timing measures event-loop responsiveness, not
desktop compositor FPS. Run a short pilot before --seconds 3600.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
import time
import traceback
from collections import Counter, defaultdict
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
os.environ.setdefault("QSG_RENDER_LOOP", "basic")

import psutil
from PySide6.QtCore import QMetaObject, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from poptools.domain.models import ExecutorDefinition, ToolDefinition, ToolOrigin
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.system_tray import SystemTrayController
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.native_terminal import register_terminal_type
from poptools.paths import AppPaths, package_root, resource_path
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels import (
    AndroidController,
    AppController,
    DeveloperConsoleController,
    JiraFeishuController,
    PresetController,
    SettingsController,
    UpdateController,
)
from poptools.viewmodels.video_preview_controller import VideoPreviewController


class NoDevices(QObject):
    devicesChanged = Signal()
    refreshingChanged = Signal()
    devices = []
    refreshing = False

    def refresh(self):
        pass


def stats(values):
    values = sorted(values)
    if not values:
        return {"count": 0}
    return {
        "count": len(values),
        "p50_ms": values[len(values) // 2],
        "p95_ms": values[min(len(values) - 1, int(len(values) * 0.95))],
        "max_ms": values[-1],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=3600)
    parser.add_argument("--tools", type=int, default=500)
    parser.add_argument("--video", type=Path)
    parser.add_argument("--alternate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-actions", action="store_true")
    parser.add_argument("--interval-ms", type=int, default=2500)
    args = parser.parse_args()
    if args.seconds < 1 or args.tools < 5 or args.interval_ms < 250:
        parser.error("seconds must be positive; tools >= 5; interval-ms >= 250")
    for clip in (args.video, args.alternate):
        if clip is not None and not clip.is_file():
            parser.error(f"Video does not exist: {clip}")
    if args.alternate and not args.video:
        parser.error("--alternate requires --video")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    session = output.with_name(output.stem + "-session")
    session.mkdir(exist_ok=False)  # Never reuse or modify user application data.
    paths = AppPaths(session)
    paths.ensure()
    os.environ["POPTOOLS_DATA_DIR"] = str(session)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    for filename in ("msyh.ttc", "consola.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / filename
        if font_path.is_file():
            QFontDatabase.addApplicationFont(str(font_path))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    register_terminal_type()
    config = ConfigStore(paths)
    config.set_runtime_environment("python", "custom", sys.executable)
    pwsh = shutil.which("pwsh")
    if pwsh:
        config.set_runtime_environment("powershell", "custom", pwsh)
    repository = JsonToolRepository(paths)
    fixtures = []
    for index in range(args.tools):
        tool = ToolDefinition(
            id=f"custom.soak_{index}",
            title=f"Stress script {index:04}",
            description="Isolated local stress fixture",
            section="custom",
            origin=ToolOrigin.CUSTOM,
            executor=ExecutorDefinition(kind="python", command="print('soak ok')"),
        )
        repository.save_tool(tool)
        fixtures.append(tool)
    registry = ToolRegistry(resource_path("tools"), repository)
    python = PythonEnvironment(paths, config)
    execution = ExecutionManager(paths, python)
    coordinator = ExecutionCoordinator(execution, 6)
    android = AndroidController(config, NoDevices())
    android.stopAutoRefresh()
    backend = AppController(registry, coordinator, config, android)
    settings = SettingsController(config, python, coordinator)
    settings.markUserGuideSeen()
    presets = PresetController(paths)
    jira = JiraFeishuController(paths.data_dir)
    terminal = DeveloperConsoleController(
        python,
        working_directory=session,
        plugin_manager=settings.pluginManager,
    )
    update = UpdateController(config, auto_check_enabled=False)
    video = VideoPreviewController(paths.data_dir)
    tray = SystemTrayController(app)
    engine = QQmlApplicationEngine()
    warnings = Counter()
    engine.warnings.connect(lambda items: warnings.update(item.toString() for item in items))
    context = {
        "appController": backend,
        "settingsController": settings,
        "presetController": presets,
        "jiraFeishuController": jira,
        "developerConsoleController": terminal,
        "androidController": android,
        "trayController": tray,
        "updateController": update,
        "videoPreviewController": video,
    }
    for name, value in context.items():
        engine.rootContext().setContextProperty(name, value)
    engine.addImageProvider("video", video.images)
    engine.load(QUrl.fromLocalFile(str(package_root() / "ui/qml/Main.qml")))
    if not engine.rootObjects():
        raise RuntimeError(dict(warnings))
    window = engine.rootObjects()[0]
    tray.attach_window(window)
    tray.set_app_controller(backend)
    backend.attach_window(window)
    window.resize(1100, 800)
    window.show()

    process = psutil.Process()
    rng = random.Random(8042)
    counts = Counter()
    actions = defaultdict(list)
    errors = []

    def capture_exception(kind, value, trace):
        errors.append(
            {
                "second": time.perf_counter() - started,
                "action": "qt_callback",
                "trace": "".join(traceback.format_exception(kind, value, trace)),
            }
        )
        print(json.dumps(errors[-1]), flush=True)

    sys.excepthook = capture_exception
    memory = []
    heartbeats = []
    minute_beats = []
    slow_beats = []
    started = time.perf_counter()
    previous = started
    frame_count = 0
    step = 0
    edit_id = None
    scrub_target = 0.0
    video_bounds = None
    shot_names = set()
    finished = []
    coordinator.finished.connect(lambda tool_id, code: finished.append((tool_id, code)))
    baseline_cpu = sum(process.cpu_times()[:2])

    def invoke(method):
        if not QMetaObject.invokeMethod(window, method):
            raise RuntimeError(f"Missing QML action {method}")

    def close_dialogs():
        for obj in window.findChildren(QObject):
            if obj.metaObject().indexOfProperty("opened") >= 0 and obj.property("opened"):
                QMetaObject.invokeMethod(obj, "close")

    def snapshot(name):
        if name in shot_names:
            return
        image = window.grabWindow()
        if image.isNull():
            raise RuntimeError(f"Empty screenshot: {name}")
        image.save(str(session / f"{name}.png"))
        shot_names.add(name)

    def beat():
        nonlocal previous
        now = time.perf_counter()
        gap = (now - previous) * 1000
        previous = now
        heartbeats.append(gap)
        minute_beats.append(gap)
        if gap > 100 and len(slow_beats) < 500:
            slow_beats.append({"second": now - started, "ms": gap, "step": step % 24})

    def frame():
        nonlocal frame_count
        frame_count += 1

    video.frameChanged.connect(frame)

    def sample():
        entry = {
            "pid": process.pid,
            "second": round(time.perf_counter() - started, 2),
            "rss_mb": process.memory_info().rss / 1024**2,
            "threads": process.num_threads(),
            "handles": process.num_handles(),
            "children": len(process.children(recursive=True)),
            "qml_objects": len(window.findChildren(QObject)),
            "cpu_seconds": sum(process.cpu_times()[:2]) - baseline_cpu,
            "heartbeat": stats(minute_beats),
            "actions": dict(counts),
            "video_frames": frame_count,
            "errors": len(errors),
        }
        minute_beats.clear()
        memory.append(entry)
        with output.with_suffix(".progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")
        print(json.dumps(entry), flush=True)

    def log_output():
        # Exercise bounded script and native-terminal histories between actions.
        backend._queue_console(fixtures[0].id, "soak output 0123456789 " * 20 + "\n")
        if terminal._tabs:
            terminal._append_to_tab(terminal._tabs[0], "soak terminal 0123456789\r\n" * 10)
        if video._scrub_active:
            video.scrub(max(0, min(video.duration - 0.1, scrub_target + rng.uniform(-1, 1))))
            counts["scrub_moves"] += 1

    def action():
        nonlocal step, edit_id, scrub_target, video_bounds
        slot = step % 24
        cycle = step // 24
        tick = time.perf_counter()
        name = f"step_{slot:02}"
        try:
            if slot == 0:
                name = "custom_navigation_and_execution"
                close_dialogs()
                invoke("openCustomScriptsPage")
                window.setProperty("toolSearchQuery", "")
                backend.selectTool(fixtures[0].id)
                for tool in fixtures[:3]:
                    workload = tool.model_copy(deep=True)
                    workload.executor.command = (
                        "import time\nfor i in range(100):\n"
                        " print('local stress output ' * 20, flush=True)\n time.sleep(.01)"
                    )
                    assert coordinator.start(workload, {})
            elif slot == 1:
                name = "search_and_sort"
                snapshot("custom")
                window.setProperty("toolSearchQuery", "Stress script 00")
                assert backend.setToolSortMode(["name", "added_time", "usage"][cycle % 3])
            elif slot == 2:
                name = "command_editor"
                window.setProperty("toolSearchQuery", "")
                backend.selectTool(fixtures[0].id)
                invoke("openCommandEditorForEdit")
            elif slot == 3:
                name = "create_script"
                snapshot("editor")
                close_dialogs()
                assert backend.createCommand(
                    "Temporary soak script", "Isolated", "python", "print('created')"
                )
                edit_id = backend.selectedTool["id"]
            elif slot == 4:
                name = "delete_script"
                backend.selectTool(edit_id)
                assert backend.deleteSelected()
                edit_id = None
            elif slot == 5:
                name = "settings_and_theme"
                invoke("openSettingsDialog")
                assert settings.saveThemeMode(["light", "dark", "system", "decade"][cycle % 4])
                assert settings.saveThemeStyle(["material3", "mario"][cycle % 2])
                assert settings.saveCustomScriptConcurrency(5)
            elif slot == 6:
                name = "user_guide"
                snapshot("settings")
                invoke("openUserGuideDialog")
            elif slot == 7:
                name = "terminal_navigation"
                snapshot("guide")
                close_dialogs()
                invoke("openTerminalPage")
                if terminal.pluginInstalled:
                    terminal.writeInput("Write-Output 'isolated terminal soak'\r")
            elif slot == 8:
                name = "terminal_tabs"
                snapshot("terminal")
                for _ in range(3):
                    terminal.createTerminalTab()
                terminal.renameTerminalTab(terminal.activeTerminalTabId, f"Stress {cycle}")
                terminal.activateRelativeTerminalTab(-1)
            elif slot == 9:
                name = "terminal_close_tabs"
                terminal.closeOtherTerminalTabs(terminal.terminalTabs[0]["tabId"])
            elif slot == 10:
                name = "color_palette"
                invoke("openPresetFunctionsPage")
                backend.selectTool("preset.colors")
            elif slot == 11:
                name = "android_empty_state"
                snapshot("palette")
                backend.selectTool(["preset.android.scrcpy", "preset.android.recording"][cycle % 2])
                android.refreshAndroidDevices()
            elif slot == 12:
                name = "video_load"
                snapshot("android")
                backend.selectTool("preset.video_preview")
                if args.video and not video.loaded:
                    video.addFiles(
                        [str(args.video.resolve())]
                        + ([str(args.alternate.resolve())] if args.alternate else [])
                    )
                elif args.video:
                    video.selectVideo(0)
            elif slot == 13:
                name = "video_play"
                if args.video:
                    assert video.loaded, f"Video failed to load: {video.message}"
                if video.loaded:
                    snapshot("video")
                    video.setVolume(0)
                    video.togglePlayback()
            elif slot == 14:
                name = "video_drag_start"
                if video.loaded:
                    video.beginScrub()
                    scrub_target = rng.uniform(10, max(11, video.duration - 10))
                    surface = window.findChild(QObject, "videoSurface")
                    video_bounds = tuple(surface.property(v) for v in ("x", "y", "width", "height"))
            elif slot == 15:
                name = "video_drag_finish"
                if video.loaded:
                    surface = window.findChild(QObject, "videoSurface")
                    assert video_bounds == tuple(
                        surface.property(v) for v in ("x", "y", "width", "height")
                    )
                    video.endScrub(scrub_target)
            elif slot == 16:
                name = "video_playlist"
                if not video.listVisible:
                    video.toggleList()
            elif slot == 17:
                name = "video_switch"
                drawer = window.findChild(QObject, "videoPlaylistDrawer")
                surface = window.findChild(QObject, "videoSurface")
                assert video.listVisible and drawer.property("opened")
                assert drawer.property("height") == surface.property("height")
                assert drawer.property("x") + drawer.property("width") == surface.property("width")
                snapshot("playlist")
                video.closeList()
                if args.alternate:
                    video.selectVideo(1)
            elif slot == 18:
                name = "video_quality_rate"
                if video.loaded:
                    video.setResolution([0, 720, 1080][cycle % 3])
                    video.setRate([0.5, 1, 2][cycle % 3])
                    video.step(1)
            elif slot == 19:
                name = "video_return"
                if args.video:
                    video.selectVideo(0)
                    video.setResolution(720)
                    video.pause()
            elif slot == 20:
                name = "settings_runtime_status"
                invoke("openSettingsDialog")
                assert len(settings.runtimePlugins) >= 2
            elif slot == 21:
                name = "update_dialog"
                invoke("queueUpdateDialog")
            elif slot == 22:
                name = "close_dialogs"
                snapshot("update")
                close_dialogs()
            elif slot == 23:
                name = "resize_and_cleanup"
                window.resize(*[(960, 640), (1400, 900), (1100, 800)][cycle % 3])
                engine.collectGarbage()
            counts[name] += 1
        except Exception:
            errors.append(
                {
                    "second": time.perf_counter() - started,
                    "action": name,
                    "trace": traceback.format_exc(),
                }
            )
            print(json.dumps(errors[-1]), flush=True)
        finally:
            actions[name].append((time.perf_counter() - tick) * 1000)
            step += 1
            if args.trace_actions:
                QTimer.singleShot(
                    min(1000, args.interval_ms // 2), lambda label=name: trace_action(label)
                )

    def trace_action(label):
        entry = {
            "second": time.perf_counter() - started,
            "action": label,
            "handles": process.num_handles(),
            "threads": process.num_threads(),
            "rss_mb": process.memory_info().rss / 1024**2,
            "terminal_sessions": len(terminal.active_session_titles()),
            "closing_tabs": len(terminal._closing_tabs),
            "video_loaded": video.loaded,
            "video_playing": video.playing,
            "audio_error": video._audio.error,
        }
        with output.with_suffix(".actions.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry) + "\n")

    def finish():
        for timer in timers:
            timer.stop()
        elapsed = time.perf_counter() - started
        sample()
        video.shutdown()
        terminal.shutdown()
        jira.shutdown()
        update.shutdown()
        settings.pluginManager.shutdown()
        backend.dependencies.shutdown()
        for tool in fixtures[:3]:
            coordinator.stop(tool.id)
        # Windows process teardown may outlive the stopped reader thread briefly.
        # Observe actual exits, never kill unrelated processes or count stale PIDs.
        _, remaining = psutil.wait_procs(process.children(recursive=True), timeout=3)
        report = {
            "requested_seconds": args.seconds,
            "action_interval_ms": args.interval_ms,
            "elapsed_seconds": elapsed,
            "rendering": {
                k: os.environ[k] for k in ("QT_QPA_PLATFORM", "QT_QUICK_BACKEND", "QSG_RENDER_LOOP")
            },
            "fixture_tools": args.tools,
            "actions": dict(counts),
            "action_latency": {name: stats(samples) for name, samples in actions.items()},
            "heartbeat": stats(heartbeats),
            "slow_beats": slow_beats,
            "samples": memory,
            "video_frames": frame_count,
            "script_completions": dict(Counter(str(code) for _, code in finished)),
            "qml_warnings": dict(warnings),
            "errors": errors,
            "children_after_shutdown": [
                {"pid": child.pid, "name": child.name()}
                for child in remaining
                if child.is_running()
            ],
            "external_coverage": (
                "No real Android devices, downloads, installs, updates or Jira/Feishu calls"
            ),
            "video_source": str(args.video.resolve()) if args.video else None,
            "audio_error_at_shutdown": video._audio.error,
        }
        report["passed"] = (
            elapsed >= args.seconds
            and not errors
            and not warnings
            and not report["children_after_shutdown"]
        )
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(output), "passed": report["passed"]}), flush=True)
        app.exit(0 if report["passed"] else 1)

    timers = []
    for interval, callback in (
        (16, beat),
        (100, log_output),
        (args.interval_ms, action),
        (60000, sample),
    ):
        timer = QTimer()
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        timer.setInterval(interval)
        timer.timeout.connect(callback)
        timer.start()
        timers.append(timer)
    sample()
    deadline = QTimer()
    deadline.setTimerType(Qt.TimerType.PreciseTimer)
    deadline.setSingleShot(True)
    deadline.timeout.connect(finish)
    deadline.start(args.seconds * 1000)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
