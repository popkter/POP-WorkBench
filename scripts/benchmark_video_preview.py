"""Measure source seeking and reusable previews on a target computer.

Run from the repository with its Python environment:
    python scripts/benchmark_video_preview.py video.mp4 --output build/video-benchmark.json
Add --ui for a real timeline gesture benchmark, and --cpu-count 1 for CPU contention.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from poptools.infrastructure.video_media import PlaybackDecoder  # noqa: E402
from poptools.infrastructure.video_proxy import ScrubProxy  # noqa: E402


def summarize(elapsed):
    return {'samples': len(elapsed), 'p50_ms': statistics.median(elapsed),
            'p95_ms': sorted(elapsed)[min(len(elapsed) - 1, int(len(elapsed) * .95))],
            'max_ms': max(elapsed)}


def measure(read, targets):
    elapsed = []
    for target in targets:
        start = time.perf_counter()
        picture = read(target)
        elapsed.append((time.perf_counter() - start) * 1000)
        if picture is None or picture.time > target + 1e-6:
            raise RuntimeError(f'No valid preview at {target:.3f}s')
    return summarize(elapsed)


def measure_ui(source, proxy, fractions, data_dir=None):
    """Measure an upper bound from a timeline gesture to Qt presentation.

    frameSwapped marks submission to the window system, not physical display scanout.
    After the requested Image is ready, wait for two further swaps. The first can
    belong to an in-flight render; the second includes the updated scene. This adds
    up to an extra refresh interval rather than undercounting presentation latency.
    """
    from PySide6.QtCore import QEventLoop, QObject, QPoint, Qt, QTimer, QUrl
    from PySide6.QtGui import QFontDatabase
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from poptools.paths import package_root
    from poptools.viewmodels.video_preview_controller import VideoPreviewController

    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(str(
        package_root() / 'resources/fonts/MaterialIconsRound-Regular.otf'))
    backend = VideoPreviewController(data_dir)
    engine = QQmlEngine()
    engine.addImageProvider('video', backend.images)
    engine.rootContext().setContextProperty('videoBackend', backend)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 1100; height: 720; visible: true
    title: "Video preview latency benchmark"
    VideoPreviewWorkspace {
        anchors.fill: parent; anchors.margins: 16
        controller: videoBackend
    }
}
''', QUrl.fromLocalFile(str(package_root() / 'ui/qml/VideoBenchmark.qml')))
    window = component.create()
    if not isinstance(window, QQuickWindow):
        backend.shutdown()
        raise RuntimeError([error.toString() for error in component.errors()])
    picture = window.findChild(QObject, 'videoPicture')
    swaps = [0]

    def swapped():
        swaps[0] += 1

    window.frameSwapped.connect(swapped, Qt.ConnectionType.QueuedConnection)
    timings = []

    def wait_for(condition, timeout_ms=30000):
        if condition():
            return
        # Use a Qt event loop like the application; a Python qWait polling loop
        # competes with the Python decoder threads for the GIL.
        loop = QEventLoop()
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if condition() else None)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        poll.start(1)
        timeout.start(timeout_ms)
        loop.exec()
        poll.stop()
        timeout.stop()
        if not condition():
            raise TimeoutError(f'Video operation did not finish within {timeout_ms / 1000:g}s')

    def gesture(action):
        previous = backend.frameSource
        start = time.perf_counter()
        action()
        dispatched = time.perf_counter()
        wait_for(lambda: backend.frameSource != previous
                 and picture.property('source').toString() == backend.frameSource
                 and picture.property('progress') == 1 and not backend.busy)
        ready = time.perf_counter()
        for _ in range(2):
            before = swaps[0]
            window.update()
            wait_for(lambda before=before: swaps[0] > before)
        elapsed = (time.perf_counter() - start) * 1000
        timings.append({'dispatch_ms': (dispatched - start) * 1000,
                        'image_ready_ms': (ready - start) * 1000, 'presented_ms': elapsed})
        return elapsed

    try:
        if not QTest.qWaitForWindowExposed(window):
            raise RuntimeError('Benchmark window is not exposed')
        first_ms = gesture(lambda: backend.addFiles([str(source)]))
        if proxy is not None:
            backend._scrub_cache.proxy = proxy
        # Include the actual filmstrip, but finish its initial construction before
        # measuring steady-state drag performance with a prepared proxy.
        wait_for(lambda: bool(backend.thumbnails) and not backend.thumbnailBusy)
        track = window.findChild(QObject, 'videoTimelineTrack')
        timeline = window.findChild(QObject, 'videoTimeline')
        bounds = track.mapRectToItem(window.contentItem(), track.boundingRect())
        popup = window.findChild(QObject, 'videoHoverPreview')

        def point(fraction):
            return QPoint(round(bounds.x() + backend.duration * fraction
                                * timeline.property('pixelsPerSecond')),
                          round(bounds.y() + 36))

        preparation_start = time.perf_counter()
        if proxy is not None and proxy.on_demand:
            # A pixel can span several seconds on a feature-length timeline.
            # Prepare the positions actually hit by the integer mouse coordinates.
            prepared = []
            targets = [(point(fraction).x() - bounds.x())
                       / timeline.property('pixelsPerSecond') for fraction in [.05, *fractions]]

            def prepare(check):
                try:
                    for target in targets:
                        if proxy.get(target) is None:
                            proxy.warm(target, check)
                    prepared.append(None)
                except Exception as error:
                    prepared.append(error)

            backend._cache_worker.submit(prepare)
            wait_for(lambda: bool(prepared), timeout_ms=300000)
            if prepared[0] is not None:
                raise prepared[0]
        preparation_ms = (time.perf_counter() - preparation_start) * 1000
        gesture(lambda: QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.05)))
        timings.clear()
        elapsed = []
        for fraction in fractions * 4:
            elapsed.append(gesture(
                lambda fraction=fraction: QTest.mouseMove(window, point(fraction), delay=0)))
            target = ((point(fraction).x() - bounds.x())
                      / timeline.property('pixelsPerSecond'))
            if abs(backend.position - target) > 2 / backend.nominalFps:
                raise RuntimeError('Timeline presented a frame outside the requested position')
            if popup.property('visible'):
                raise RuntimeError('Hover popup is visible during dragging')
        drag_timings = list(timings)
        release_ms = gesture(lambda: QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=point(fractions[-1])))
        if (backend.images._live.width(), backend.images._live.height()) != (
                backend._info['width'], backend._info['height']):
            raise RuntimeError('Releasing the timeline did not restore native resolution')
        return {'measurement': 'upper bound: mouse event to two swaps after Image ready',
                'cache': ('prepared proxy' if proxy is not None else
                          'application-managed cache' if data_dir else 'memory cache'),
                'window': [window.width(), window.height()],
                'screen_refresh_hz': window.screen().refreshRate(),
                'pointer_cache_preparation_ms': preparation_ms,
                'first_frame_ms': first_ms, 'drag': summarize(elapsed),
                'drag_stages': {stage: summarize([row[stage] for row in drag_timings])
                                for stage in drag_timings[0]},
                'release_to_source_frame_ms': release_ms,
                'release_stages': timings[-1],
                'release_frame_size': [backend.images._live.width(), backend.images._live.height()]}
    finally:
        backend.shutdown()
        window.close()
        window.frameSwapped.disconnect(swapped)
        window.deleteLater()
        engine.deleteLater()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--output', type=Path, default=Path('build/video-benchmark.json'))
    parser.add_argument('--cache-dir', type=Path, default=Path('build/video-benchmark-cache'))
    parser.add_argument('--ui', action='store_true',
                        help='Also measure actual Qt timeline dragging')
    parser.add_argument('--cpu-count', type=int, help='Restrict this process to N available CPUs')
    args = parser.parse_args()
    import psutil
    process = psutil.Process()
    if args.cpu_count is not None:
        if args.cpu_count < 1 or not hasattr(process, 'cpu_affinity'):
            parser.error('--cpu-count requires a positive count and CPU affinity support')
        available = process.cpu_affinity()
        if args.cpu_count > len(available):
            parser.error('--cpu-count exceeds the available CPUs')
        process.cpu_affinity(available[:args.cpu_count])
    source = args.video.resolve(strict=True)
    decoder = PlaybackDecoder()
    try:
        start = time.perf_counter()
        info, _ = decoder.open(str(source), 0, lambda: None)
        first_ms = (time.perf_counter() - start) * 1000
        fractions = [.85, .1, .7, .25, .9, .4, .6]
        targets = [info['duration'] * fraction for fraction in fractions]
        original = measure(lambda target: decoder.reader.seek(target, lambda: None), targets)
    finally:
        decoder.close()
    on_demand = info['duration'] > 300 or source.stat().st_size >= 2 * 1024**3
    proxy = ScrubProxy(str(source), args.cache_dir, on_demand=on_demand)
    start = time.perf_counter()
    if on_demand:
        for target in targets:
            proxy.warm(target, lambda: None)
        complete = all(proxy.get(target) is not None for target in targets)
    else:
        complete = proxy.build(lambda: None)
    preparation_ms = (time.perf_counter() - start) * 1000
    report = {'system': platform.platform(), 'machine': platform.machine(),
              'video': source.name, 'width': info['width'], 'height': info['height'],
              'duration_seconds': info['duration'], 'first_frame_ms': first_ms,
              'source_seek': original, 'proxy_preparation_ms': preparation_ms,
              'proxy_mode': 'on-demand neighborhoods' if on_demand else 'whole clip',
              'proxy_complete': complete and not on_demand,
              'sampled_positions_ready': complete, 'proxy_bytes': proxy.path.stat().st_size,
              'proxy_seek': measure(proxy.get, targets * 4) if complete else None}
    report['cpu_affinity'] = process.cpu_affinity() if hasattr(process, 'cpu_affinity') else None
    if args.ui:
        if not complete:
            raise RuntimeError('UI benchmark requires previews at the sampled positions')
        report['ui'] = measure_ui(source, proxy, fractions)
        report['proxy_bytes'] = proxy.path.stat().st_size
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
