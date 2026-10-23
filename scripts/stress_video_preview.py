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
from pathlib import Path

import psutil
from PySide6.QtCore import QEventLoop, QObject, QPoint, Qt, QTimer, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from poptools.paths import package_root  # noqa: E402
from poptools.viewmodels.video_preview_controller import VideoPreviewController  # noqa: E402


def stats(values):
    values = sorted(values)
    return {'count': len(values), 'p50': values[len(values) // 2],
            'p95': values[min(len(values) - 1, int(len(values) * .95))], 'max': values[-1]}


def run(args):
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
    os.environ.setdefault('QSG_RENDER_LOOP', 'basic')
    app = QApplication.instance() or QApplication([])
    process = psutil.Process()
    if args.cpu_count:
        process.cpu_affinity(process.cpu_affinity()[:args.cpu_count])
    QFontDatabase.addApplicationFont(str(
        package_root() / 'resources/fonts/MaterialIconsRound-Regular.otf'))
    backend = VideoPreviewController(args.output.parent / (args.output.stem + '-session'))
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
    heartbeat_gaps, memory, frame_times, phases = [], [], [], []
    active_phase, slow_beats, actions = ['startup'], [], []
    heartbeat = QTimer()
    heartbeat.setTimerType(Qt.TimerType.PreciseTimer)
    previous = [time.perf_counter()]

    def beat():
        now = time.perf_counter()
        heartbeat_gaps.append((now - previous[0]) * 1000)
        if heartbeat_gaps[-1] > 100:
            slow_beats.append({'phase': active_phase[0], 'gap_ms': heartbeat_gaps[-1]})
        previous[0] = now

    heartbeat.timeout.connect(beat)
    sampler = QTimer()
    sampler.timeout.connect(lambda: memory.append(process.memory_info().rss / 1024**2))
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
        timer = QTimer()
        timer.setTimerType(Qt.TimerType.PreciseTimer)
        start_frames = len(frame_times)
        start = time.perf_counter()

        def move():
            x = round(bounds.x() + bounds.width() * randomizer.uniform(.05, .95))
            point = QPoint(x, round(bounds.y() + 36))
            positions.append(point)
            QTest.mouseMove(window, point, delay=0)
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
        target = timeline.property('hoverTime')
        released = time.perf_counter()
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=positions[-1])
        wait_until(lambda: not backend.busy)
        assert abs(backend.position - target) <= 2 / backend.nominalFps, (backend.position, target)
        assert not failures, set(failures)
        updates = frame_times[start_frames:]
        phases.append({'name': name, 'seconds': time.perf_counter() - start,
                       'mouse_moves': len(positions), 'main_picture_updates': len(updates),
                       'frame_gap_ms': stats([(b - a) * 1000 for a, b in
                                              zip(updates, updates[1:], strict=False)])
                       if len(updates) > 1 else None,
                       'release_ms': (time.perf_counter() - released) * 1000})

    report = {'system': platform.platform(), 'video': args.video.name, 'phases': phases,
              'render_loop': os.environ.get('QSG_RENDER_LOOP')}
    try:
        window.raise_()
        window.requestActivate()
        assert QTest.qWaitForWindowExposed(window)
        backend.setVolume(.1)
        backend.addFiles([str(args.video.resolve()), str(args.alternate.resolve())])
        backend.closeList()
        wait_until(lambda: backend.loaded and not backend.busy)
        assert not window.grabWindow().isNull()
        wait_until(lambda: not backend.thumbnailBusy and bool(backend.thumbnails))
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
            assert backend.fileName == expected.name
            quality = backend.resolutionOptions[index % len(backend.resolutionOptions)]['value']
            action('resolution', lambda quality=quality: backend.setResolution(quality))
            wait_until(lambda: not backend.busy)
            action('start_playback', backend.togglePlayback)
            run_for(.5)
            assert backend.playing
            action('pause', backend.pause)
            backend.toggleList()
            action('resize', lambda index=index: window.setWidth(720 if index % 2 == 0 else 1100))
            run_for(.15)
            backend.closeList()
            assert not backend.message, backend.message
        run_for(1)
        assert not warnings, warnings
        report.update({'heartbeat_gap_ms': stats(heartbeat_gaps),
                       'slow_heartbeats': slow_beats, 'actions': actions,
                       'rss_mb': stats(memory), 'rss_last_samples_mb': memory[-10:],
                       'threads': process.num_threads(),
                       'handles': (process.num_handles()
                                   if hasattr(process, 'num_handles') else None),
                       'qml_warnings': warnings, 'mixed_transitions': 8, 'passed': True})
    finally:
        heartbeat.stop()
        sampler.stop()
        started = time.perf_counter()
        backend.shutdown()
        report['shutdown_ms'] = (time.perf_counter() - started) * 1000
        workers = (backend._worker, backend._thumb_worker, backend._cache_worker,
                   backend._proxy_worker, backend._metadata_worker,
                   backend._preview_worker, backend._audio.worker)
        report['workers_remaining'] = [worker._thread.name for worker in workers
                                       if worker._thread.is_alive()]
        window.close()
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert not report['workers_remaining'], report['workers_remaining']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--alternate', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=30)
    parser.add_argument('--cpu-count', type=int)
    parser.add_argument('--output', type=Path, default=Path('build/video-stress.json'))
    arguments = parser.parse_args()
    if arguments.seconds < 4 or arguments.cpu_count is not None and arguments.cpu_count < 1:
        parser.error('Use --seconds >= 4 and a positive --cpu-count')
    run(arguments)
