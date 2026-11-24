"""Exercise real video UI under continuous input; writes only an isolated report/session.

python scripts/stress_video_preview.py movie.mkv --alternate clip.mp4 --seconds 30
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import sys
import time
from collections import deque
from pathlib import Path

import psutil
from PySide6.QtCore import QEventLoop, QObject, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from poptools.paths import package_root  # noqa: E402
from poptools.viewmodels.video_preview_controller import VideoPreviewController  # noqa: E402


def stats(values):
    values = sorted(values)
    return {'count': len(values), 'p50': values[len(values) // 2],
            'p95': values[min(len(values) - 1, int(len(values) * .95))], 'max': values[-1]}


def require(condition, message):
    # Release bytecode uses optimize=1; validation must not disappear with asserts.
    if not condition:
        raise RuntimeError(str(message))


def trace_slow_reads(events):
    """Record slow decode calls and cache misses for correlation with frame gaps."""
    from poptools.infrastructure.video_media import VideoReader
    from poptools.infrastructure.video_proxy import ScrubProxy

    originals = []

    def wrap(owner, method, *, cache=False):
        original = getattr(owner, method)
        originals.append((owner, method, original))

        def timed(self, target, *args, **kwargs):
            started = time.perf_counter()
            result = original(self, target, *args, **kwargs)
            finished = time.perf_counter()
            if finished - started >= .04 or (cache and result is None):
                events.append({'stage': method, 'target_seconds': target,
                               'start_seconds': started, 'end_seconds': finished,
                               'ms': (finished - started) * 1000,
                               'cache_miss': cache and result is None})
            return result

        setattr(owner, method, timed)

    wrap(ScrubProxy, '_read_frame', cache=True)
    wrap(VideoReader, 'seek')
    wrap(VideoReader, 'seek_fast_preview')
    return originals


def run(args):
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Microsoft YaHei UI" if sys.platform == "win32" else "PingFang SC", 10))
    process = psutil.Process()
    if args.cpu_count:
        process.cpu_affinity(process.cpu_affinity()[:args.cpu_count])
    QFontDatabase.addApplicationFont(str(
        package_root() / 'resources/fonts/MaterialIconsRound-Regular.otf'))
    session_dir = args.session_dir or args.output.parent / (args.output.stem + '-session')
    decode_events = deque(maxlen=128)
    traced = trace_slow_reads(decode_events) if args.trace_slow_decode else []
    backend = VideoPreviewController(session_dir)
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(error.toString() for error in errors))
    engine.addImageProvider('video', backend.images)
    engine.rootContext().setContextProperty('videoBackend', backend)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 1100; height: 720; visible: true
    color: "#f6f8fc"
    title: "Video stress test"
    VideoPreviewWorkspace { anchors.fill: parent; anchors.margins: 16; controller: videoBackend }
}
''', QUrl.fromLocalFile(str(package_root() / 'ui/qml/VideoStress.qml')))
    window = component.create()
    if not isinstance(window, QQuickWindow):
        backend.shutdown()
        raise RuntimeError([error.toString() for error in component.errors()])
    heartbeat_gaps, memory, frame_times, phases, cpu = [], [], [], [], []
    process.cpu_percent(None)
    active_phase, slow_beats, actions = ['startup'], [], []
    heartbeat = QTimer()
    heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
    previous = [time.perf_counter()]

    def beat():
        now = time.perf_counter()
        heartbeat_gaps.append((now - previous[0]) * 1000)
        if heartbeat_gaps[-1] > 100:
            slow_beats.append({'phase': active_phase[0], 'gap_ms': heartbeat_gaps[-1],
                               'perf_counter_seconds': now})
        previous[0] = now

    heartbeat.timeout.connect(beat)
    sampler = QTimer()
    def sample_resources():
        memory.append(process.memory_info().rss / 1024**2)
        cpu.append(process.cpu_percent(None))
    sampler.timeout.connect(sample_resources)
    backend.frameChanged.connect(lambda: frame_times.append(time.perf_counter()))

    def wait_until(condition, timeout_ms=15000):
        if condition():
            return
        loop, poll, timeout = QEventLoop(), QTimer(), QTimer()
        poll.timeout.connect(lambda: loop.quit() if condition() else None)
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        poll.start(5)
        timeout.start(timeout_ms)
        loop.exec()
        poll.stop()
        timeout.stop()
        if not condition():
            raise TimeoutError(f'Operation timed out: {backend.message}; loaded={backend.loaded}, '
                               f'thumb_busy={backend.thumbnailBusy}, '
                               f'thumbnails={len(backend.thumbnails)}, '
                               f'thumb_token={backend._thumb_token}, warnings={warnings}')

    def run_for(seconds):
        stop = time.monotonic() + seconds
        wait_until(lambda: time.monotonic() >= stop, timeout_ms=round(seconds * 1000) + 5000)

    def action(name, call):
        active_phase[0] = name
        started = time.perf_counter()
        call()
        actions.append({'name': name, 'ms': (time.perf_counter() - started) * 1000})

    def drag(name, seconds, local=False):
        active_phase[0] = name
        timeline = window.findChild(QObject, 'videoTimeline')
        track = window.findChild(QObject, 'videoTimelineTrack')
        surface = window.findChild(QObject, 'videoSurface')
        popup = window.findChild(QObject, 'videoHoverPreview')
        if local:
            timeline.setProperty('pixelsPerSecond', 200)
            timeline.setProperty('viewStart', min(1200, max(0, backend.duration - 6)))
        else:
            backend.fit()
        run_for(.15)
        bounds = track.mapRectToItem(window.contentItem(), track.boundingRect())
        baseline = surface.mapRectToItem(window.contentItem(), surface.boundingRect())
        randomizer, positions, failures = random.Random(42), [], []
        pointer_errors, picture_errors, picture_sizes = [], [], set()
        frame_metadata = {}
        def frame_observed():
            picture_errors.append(abs(backend.position - timeline.property('hoverTime')))
            size = (backend.images._live.width(), backend.images._live.height())
            picture_sizes.add(size)
            # The global observer was connected first, so reuse the timestamp
            # used by the unchanged gap gate instead of taking another clock sample.
            frame_metadata[frame_times[-1]] = (backend.position, size, backend.previewApproximate)
        backend.frameChanged.connect(frame_observed)
        timer = QTimer()
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        start_frames = len(frame_times)
        start = time.perf_counter()

        def move():
            x = round(bounds.x() + bounds.width() * randomizer.uniform(.05, .95))
            point = QPoint(x, round(bounds.y() + 36))
            positions.append(point)
            QTest.mouseMove(window, point, delay=0)
            pointer_errors.append(abs(timeline.property('playheadTime')
                                      - timeline.property('hoverTime'))
                                  * timeline.property('pixelsPerSecond'))
            if popup.property('visible'):
                failures.append('Hover popup visible during drag')
            current = surface.mapRectToItem(window.contentItem(), surface.boundingRect())
            if current != baseline:
                failures.append('Player geometry changed during drag')

        QTest.mousePress(window, Qt.MouseButton.LeftButton,
                         pos=QPoint(round(bounds.center().x()), round(bounds.y() + 36)))
        timer.timeout.connect(move)
        timer.start(16)
        try:
            run_for(seconds)
        finally:
            timer.stop()
        backend.frameChanged.disconnect(frame_observed)
        if not phases:
            capture = args.output.with_suffix('.drag.png')
            capture.parent.mkdir(parents=True, exist_ok=True)
            require(window.grabWindow().save(str(capture)), 'Drag screenshot could not be saved')
            report['drag_screenshot'] = str(capture.resolve())
        updates = frame_times[start_frames:]
        target = timeline.property('hoverTime')
        released = time.perf_counter()
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=positions[-1])
        wait_until(lambda: not backend.busy)
        require(abs(backend.position - target) <= 2 / backend.nominalFps,
                (backend.position, target))
        require(not failures, set(failures))
        bounded_updates = [start, *updates, released]
        require(max(pointer_errors) <= .5, pointer_errors)
        gaps = [(b - a) * 1000 for a, b in
                zip(bounded_updates, bounded_updates[1:], strict=False)]
        longest_index = max(range(len(gaps)), key=gaps.__getitem__)

        def frame_trace(timestamp):
            trace = {'perf_counter_seconds': timestamp, 'phase_ms': (timestamp - start) * 1000}
            metadata = frame_metadata.get(timestamp)
            if metadata is None:
                # A first-phase grabWindow may pump events after the observer
                # disconnects; do not attach another frame's metadata to them.
                trace['metadata_recorded'] = False
            else:
                trace.update({'metadata_recorded': True, 'pts_seconds': metadata[0],
                              'size': metadata[1], 'approximate': metadata[2]})
            return trace

        longest_gap = {
            'ms': gaps[longest_index],
            'segment': ('entire_phase' if not updates else
                        'start' if longest_index == 0 else
                        'tail' if longest_index == len(gaps) - 1 else 'motion'),
            'start_phase_ms': (bounded_updates[longest_index] - start) * 1000,
            'end_phase_ms': (bounded_updates[longest_index + 1] - start) * 1000,
            'previous_frames': [frame_trace(timestamp) for timestamp in
                                updates[max(0, longest_index - 2):longest_index]],
            'following_frames': [frame_trace(timestamp) for timestamp in
                                 updates[longest_index:longest_index + 2]],
        }
        phases.append({'name': name, 'seconds': released - start,
                       'started_perf_counter_seconds': start,
                       'mouse_moves': len(positions), 'main_picture_updates': len(updates),
                       'frame_gap_ms': stats(gaps),
                       'longest_frame_gap': longest_gap,
                       'pointer_max_error_pixels': max(pointer_errors),
                       'picture_position_error_seconds': (stats(picture_errors)
                                                          if picture_errors else None),
                       'picture_sizes': sorted(picture_sizes),
                       'release_ms': (time.perf_counter() - released) * 1000})
        if args.max_drag_gap_ms is not None:
            require(max(gaps) <= args.max_drag_gap_ms, phases[-1])

    report = {'system': platform.platform(), 'video': args.video.name, 'phases': phases,
              'render_loop': os.environ.get('QSG_RENDER_LOOP'),
              'drag_gap_budget_ms': args.max_drag_gap_ms,
              'frozen': bool(getattr(sys, 'frozen', False)),
              'controller_module_file': sys.modules[VideoPreviewController.__module__].__file__,
              'qt_platform': app.platformName(),
              'qt_test_module_file': sys.modules['PySide6.QtTest'].__file__,
              'passed': False, 'actions': actions}
    try:
        window.raise_()
        window.requestActivate()
        require(QTest.qWaitForWindowExposed(window), 'Window was not exposed')
        backend.setVolume(.1)
        backend.addFiles([str(args.video.resolve()), str(args.alternate.resolve())])
        backend.closeList()
        wait_until(lambda: backend.loaded and not backend.busy)
        require(not window.grabWindow().isNull(), 'Window has no rendered image')
        wait_until(lambda: not backend.thumbnailBusy and bool(backend.thumbnails))
        if args.wait_prepared:
            wait_until(lambda: backend.previewReady, timeout_ms=300000)
        report['preview_prepared_at_start'] = backend.previewReady
        previous[0] = time.perf_counter()
        heartbeat.start(16)
        sampler.start(200)
        for _ in range(2):
            drag('whole_movie_random', args.seconds / 4)
            drag('zoomed_neighborhood', args.seconds / 4, local=True)
        for index in range(8):
            backend.seek(backend.duration * .3)
            action('file_switch',
                   lambda index=index: backend.selectVideo(1 if index % 2 == 0 else 0))
            wait_until(lambda: backend.loaded and not backend.busy)
            expected = args.alternate if index % 2 == 0 else args.video
            require(backend.fileName == expected.name, 'File switch selected the wrong video')
            quality = backend.resolutionOptions[index % len(backend.resolutionOptions)]['value']
            action('resolution', lambda quality=quality: backend.setResolution(quality))
            wait_until(lambda: not backend.busy)
            backend.seek(backend.duration * .25)
            wait_until(lambda: not backend.busy)
            action('start_playback', backend.togglePlayback)
            run_for(.5)
            require(backend.playing, f'Playback stopped: index={index}, '
                    f'position={backend.position}, duration={backend.duration}, '
                    f'message={backend.message}')
            action('pause', backend.pause)
            backend.toggleList()
            action('resize', lambda index=index: window.setWidth(720 if index % 2 == 0 else 1100))
            run_for(.15)
            backend.closeList()
            require(not backend.message, backend.message)
        run_for(1)
        require(not warnings, warnings)
        report.update({'threads': process.num_threads(),
                       'handles': (process.num_handles()
                                   if hasattr(process, 'num_handles') else None),
                       'mixed_transitions': 8, 'passed': True})
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        heartbeat.stop()
        sampler.stop()
        # A failed gate must retain the same evidence as a successful run.
        report.update({'heartbeat_gap_ms': stats(heartbeat_gaps) if heartbeat_gaps else None,
                       'slow_heartbeats': slow_beats, 'actions': actions,
                       'slow_decode_events': list(decode_events),
                       'rss_mb': stats(memory) if memory else None,
                       'cpu_percent_of_one_core': stats(cpu) if cpu else None,
                       'rss_last_samples_mb': memory[-10:], 'qml_warnings': warnings})
        started = time.perf_counter()
        backend.shutdown()
        for owner, name, method in traced:
            setattr(owner, name, method)
        report['shutdown_ms'] = (time.perf_counter() - started) * 1000
        workers = [value for value in vars(backend).values()
                   if hasattr(value, '_thread') and hasattr(value, '_condition')]
        workers.append(backend._audio.worker)
        report['workers_remaining'] = [worker._thread.name for worker in workers
                                       if worker._thread.is_alive()]
        if report['workers_remaining']:
            report['passed'] = False
            report['error'] = 'Preview workers remained alive after shutdown'
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    require(not report['workers_remaining'], report['workers_remaining'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--alternate', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--cpu-count', type=int)
    parser.add_argument('--session-dir', type=Path)
    parser.add_argument('--wait-prepared', action='store_true')
    parser.add_argument('--trace-slow-decode', action='store_true')
    parser.add_argument('--max-drag-gap-ms', type=float,
                        help='Fail if any drag freeze, including either edge, exceeds this budget')
    parser.add_argument('--output', type=Path, default=Path('build/video-stress.json'))
    arguments = parser.parse_args()
    if arguments.seconds < 4 or arguments.cpu_count is not None and arguments.cpu_count < 1:
        parser.error('Use --seconds >= 4 and a positive --cpu-count')
    run(arguments)


if __name__ == '__main__':
    main()
