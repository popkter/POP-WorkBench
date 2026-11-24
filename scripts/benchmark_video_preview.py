"""Measure source seeking and reusable previews on a target computer.

Run from the repository with its Python environment:
    python scripts/benchmark_video_preview.py video.mp4 --output build/video-benchmark.json
Add --ui for a real timeline gesture benchmark, and --cpu-count 1 for CPU contention.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import random
import statistics
import sys
import time
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from poptools.infrastructure.video_media import Picture, PlaybackDecoder  # noqa: E402
from poptools.infrastructure.video_proxy import ScrubProxy  # noqa: E402


def summarize(elapsed):
    return {'samples': len(elapsed), 'p50_ms': statistics.median(elapsed),
            'p95_ms': sorted(elapsed)[min(len(elapsed) - 1, int(len(elapsed) * .95))],
            'max_ms': max(elapsed)}


def summarize_values(values):
    if not values:
        return None
    return {'samples': len(values), 'p50': statistics.median(values),
            'p95': sorted(values)[min(len(values) - 1, int(len(values) * .95))],
            'max': max(values)}


def measure(read, targets):
    elapsed = []
    for target in targets:
        start = time.perf_counter()
        picture = read(target)
        elapsed.append((time.perf_counter() - start) * 1000)
        if picture is None or picture.time > target + 1e-6:
            raise RuntimeError(f'No valid preview at {target:.3f}s')
    return summarize(elapsed)


def summarize_motion_windows(frames, resources, moves, requests, started, duration,
                             planned_duration, window_seconds=2):
    """Partition recorded observations without adding timers or changing input."""
    windows = []
    count = max(1, math.ceil(planned_duration / window_seconds))
    for index in range(count):
        left = index * window_seconds
        # Include a late final input in the last bucket, not a tiny extra bucket
        # with a misleading FPS denominator. Report its actual duration explicitly.
        right = duration if index == count - 1 else min(duration, left + window_seconds)
        if right <= left:
            break
        rows = [row for row in frames if left * 1000 <= row['shown_at_ms'] < right * 1000]
        exact = [row for row in rows if not row['approximate']
                 and row.get('covers_original_sampled_job', False)]
        approximate = [row for row in rows if row['approximate']
                       and row.get('valid_browsing_frame', False)]
        valid = exact + approximate
        samples = [row for row in resources if left <= row['at'] - started < right]
        changes = sum(previous['pts_seconds'] != current['pts_seconds']
                      for previous, current in zip(frames, frames[1:], strict=False)
                      if left * 1000 <= current['shown_at_ms'] < right * 1000)

        def latency(items, key):
            values = [row[key] for row in items if row.get(key) is not None]
            return summarize(values) if values else None

        bounds = [left * 1000, *[row['shown_at_ms'] for row in rows], right * 1000]
        seconds = right - left
        windows.append({
            'start_seconds': left, 'end_seconds': right, 'duration_seconds': seconds,
            'nominal_end_seconds': min(planned_duration, left + window_seconds),
            'shown_frames': len(rows), 'exact_frames': len(exact),
            'approximate_browsing_frames': len(approximate),
            'valid_browsing_frames': len(valid),
            'unattributed_or_invalid_frames': len(rows) - len(valid),
            'exact_frame_fps': len(exact) / seconds,
            'approximate_browsing_frame_fps': len(approximate) / seconds,
            'valid_browsing_frame_fps': len(valid) / seconds,
            'content_change_fps': changes / seconds,
            'sampled_job_age_ms': latency(valid, 'sampled_job_age_ms'),
            'exact_sampled_job_age_ms': latency(exact, 'sampled_job_age_ms'),
            'approximate_sampled_job_age_ms': latency(approximate, 'sampled_job_age_ms'),
            'input_to_exact_frame_ms': latency(exact, 'original_input_age_ms'),
            'input_to_approximate_frame_ms': latency(approximate, 'original_input_age_ms'),
            'sampled_target_pts_error_ms': (summarize(
                [abs(row['signed_pts_error_ms']) for row in valid]) if valid else None),
            'input_effective_hz': sum(left <= at - started < right for at in moves) / seconds,
            'controller_scrub_hz': sum(left <= at - started < right
                                       for at, _ in requests) / seconds,
            'window_bounded_update_gap_ms': summarize(
                [b - a for a, b in zip(bounds, bounds[1:], strict=False)]),
            'cpu_percent_of_one_core': summarize_values([row['cpu'] for row in samples]),
            'rss_mb': summarize_values([row['rss'] for row in samples]),
            'resource_samples': len(samples),
            'preview_ready_samples': sum(row['preview_ready'] for row in samples),
            'preview_optimizing_samples': sum(row['preview_optimizing'] for row in samples),
            'preview_ready_at_last_sample': samples[-1]['preview_ready'] if samples else None,
        })
    return windows


def measure_ui(source, proxy, fractions, data_dir=None, wait_prepared=False,
               input_hz=60, rapid_moves=60, timeline_span=None, synthetic_cached=False,
               trajectory="triangle", half_sweep_seconds=.25, exact_drag_only=False,
               immediate_drag=False, first_drag_delay_ms=0):
    """Measure an upper bound from a timeline gesture to Qt presentation.

    frameSwapped marks submission to the window system, not physical display scanout.
    After the requested Image is ready, wait for two further swaps. The first can
    belong to an in-flight render; the second includes the updated scene. This adds
    up to an extra refresh interval rather than undercounting presentation latency.
    """
    from PySide6.QtCore import QEventLoop, QObject, QPoint, Qt, QTimer, QUrl, Slot
    from PySide6.QtGui import QFont, QFontDatabase, QImage
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from poptools.paths import package_root
    from poptools.viewmodels.video_preview_controller import VideoPreviewController

    source_module_sha256 = {
        cls.__module__: hashlib.sha256(
            Path(sys.modules[cls.__module__].__file__).read_bytes()).hexdigest()
        for cls in (VideoPreviewController, PlaybackDecoder)
        if Path(sys.modules[cls.__module__].__file__).is_file()}
    os.environ.setdefault('QT_QUICK_CONTROLS_STYLE', 'Basic')
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont("Microsoft YaHei UI" if sys.platform == "win32" else "PingFang SC", 10))
    QFontDatabase.addApplicationFont(str(
        package_root() / 'resources/fonts/MaterialIconsRound-Regular.otf'))
    import psutil
    process = psutil.Process()
    process.cpu_percent(None)
    psutil.cpu_percent(None)
    rss_samples, cpu_samples, host_cpu_samples, resource_records = [], [], [], []
    sampler = QTimer()
    def sample_resources():
        rss_samples.append(process.memory_info().rss / 1024**2)
        cpu_samples.append(process.cpu_percent(None))
        host_cpu_samples.append(psutil.cpu_percent(None))
        resource_records.append({'at': time.perf_counter(), 'rss': rss_samples[-1],
                                 'cpu': cpu_samples[-1], 'preview_ready': backend.previewReady,
                                 'preview_optimizing': backend.previewOptimizing})
    sampler.timeout.connect(sample_resources)
    sampler.start(100)
    scrub_requests, last_picture, last_origin = [], [None], [None]
    recording_scrubs = [False]
    class ObservedController(VideoPreviewController):
        def __init__(self, *args, **kwargs):
            self.measure_jobs, self.measure_requests = {}, {}
            self.measure_cache_job = None
            self.measure_show_origin = None
            super().__init__(*args, **kwargs)

        def _seek(self, position, fast=False, **kwargs):
            origin = (time.perf_counter(), position)
            # A benchmark-only baseline keeps production scheduling/caches intact,
            # but disables temporal sampling for this submitted decode job.
            previous_fast = self._scrub_fast
            try:
                if exact_drag_only:
                    self._scrub_fast = False
                super()._seek(position, fast=fast, **kwargs)
            finally:
                self._scrub_fast = previous_fast
            if recording_scrubs[0]:
                self.measure_jobs[self._token] = origin
                for name in ('_scrub_request', '_refine_request'):
                    request = getattr(self, name, None)
                    if request is not None:
                        self.measure_requests[id(request)] = origin

        def _received(self, token, result):
            self.measure_show_origin = self.measure_jobs.pop(token, None)
            request = self._scrub_request
            retargeted = getattr(request, 'retargeted_at', None)
            if self.measure_show_origin is not None and token == self._token and retargeted is not None:
                observed = time.perf_counter() - (time.monotonic() - retargeted)
                self.measure_show_origin = (observed, request.sampled_target)
            try:
                super()._received(token, result)
            finally:
                self.measure_show_origin = None

        def _scrub_progress(self, request, *args):
            self.measure_show_origin = self.measure_requests.get(id(request))
            try:
                super()._scrub_progress(request, *args)
            finally:
                self.measure_show_origin = None

        def _preview_cached_scrub(self, request):
            previous = self.measure_show_origin
            if recording_scrubs[0] and previous is None:
                self.measure_show_origin = (time.perf_counter(), request.target)
            try:
                super()._preview_cached_scrub(request)
            finally:
                self.measure_show_origin = previous

        def _read_cached_scrub_preview(self, request, target, cache, proxy):
            origin = (time.perf_counter(), target)
            super()._read_cached_scrub_preview(request, target, cache, proxy)
            if recording_scrubs[0]:
                self.measure_cache_job = (self._cached_scrub_preview_token, origin)

        def _cached_scrub_preview_received(self, token, result):
            if self.measure_cache_job is not None and self.measure_cache_job[0] == token:
                self.measure_show_origin = self.measure_cache_job[1]
                self.measure_cache_job = None
            try:
                super()._cached_scrub_preview_received(token, result)
            finally:
                self.measure_show_origin = None

        @Slot(float)
        def scrub(self, position):
            if recording_scrubs[0]:
                origin = (time.perf_counter(), position)
                scrub_requests.append(origin)
                # An exact memory hit can display during the scrub call.
                self.measure_show_origin = origin
            try:
                super().scrub(position)
            finally:
                self.measure_show_origin = None

        def _show(self, frame):
            last_picture[0] = frame
            last_origin[0] = self.measure_show_origin
            super()._show(frame)

    backend = ObservedController(data_dir)
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
    def viewport_quality_ok():
        # Judge physical display pixels (including DPR/zoom), not invisible 4K
        # pixels in a small preview. Native source is the upper quality bound.
        required_width = min(backend._info['width'],
                             math.ceil(picture.property('paintedWidth')
                                       * window.devicePixelRatio()))
        required_height = min(backend._info['height'],
                              math.ceil(picture.property('paintedHeight')
                                        * window.devicePixelRatio()))
        return (backend.images._live.width() >= required_width
                and backend.images._live.height() >= required_height)

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

    def gesture(action, preview_target=None):
        previous = backend.frameSource
        start = time.perf_counter()
        action()
        dispatched = time.perf_counter()
        preview_ready_ms = None
        if preview_target is not None:
            wait_for(lambda: backend.frameSource != previous
                     and picture.property('source').toString() == backend.frameSource
                     and picture.property('progress') == 1
                     and last_picture[0] is not None
                     and not last_picture[0].approximate
                     and last_picture[0].time - 1e-7 <= preview_target
                     < last_picture[0].end - 1e-7)
            preview_ready_ms = (time.perf_counter() - start) * 1000
        wait_for(lambda: backend.frameSource != previous
                 and picture.property('source').toString() == backend.frameSource
                 and picture.property('progress') == 1 and not backend.busy
                 and not backend.previewApproximate)
        ready = time.perf_counter()
        for _ in range(2):
            before = swaps[0]
            window.update()
            try:
                wait_for(lambda before=before: swaps[0] > before)
            except TimeoutError as error:
                raise TimeoutError(
                    'Image ready, but native window frameSwapped did not advance: '
                    f'platform={app.platformName()}, exposed={window.isExposed()}, '
                    f'active={window.isActive()}, visible={window.isVisible()}, '
                    f'swaps={swaps[0]}, busy={backend.busy}, '
                    f'approximate={backend.previewApproximate}') from error
        elapsed = (time.perf_counter() - start) * 1000
        timings.append({'dispatch_ms': (dispatched - start) * 1000,
                        'image_ready_ms': (ready - start) * 1000, 'presented_ms': elapsed})
        if preview_ready_ms is not None:
            timings[-1]['correct_preview_image_ready_ms'] = preview_ready_ms
        return elapsed

    try:
        if not QTest.qWaitForWindowExposed(window):
            raise RuntimeError('Benchmark window is not exposed')
        first_ms = gesture(lambda: backend.addFiles([str(source)]))
        first_frame_stages = timings[0]
        first_presented_at = time.perf_counter()
        if first_drag_delay_ms:
            drag_delay = QEventLoop()
            drag_timer = QTimer()
            drag_timer.setTimerType(Qt.TimerType.PreciseTimer)
            drag_timer.setSingleShot(True)
            drag_timer.timeout.connect(drag_delay.quit)
            drag_timer.start(first_drag_delay_ms)
            drag_delay.exec()
        if not immediate_drag:
            wait_for(lambda: bool(backend.thumbnails) and not backend.thumbnailBusy)
        preparation_started = time.perf_counter()
        if wait_prepared:
            if backend.duration > 300:
                raise ValueError('Long-video previews prepare locally, not as a complete clip')
            wait_for(lambda: backend.previewReady, timeout_ms=300000)
        preparation_ms = (time.perf_counter() - preparation_started) * 1000
        track = window.findChild(QObject, 'videoTimelineTrack')
        timeline = window.findChild(QObject, 'videoTimeline')
        bounds = track.mapRectToItem(window.contentItem(), track.boundingRect())
        popup = window.findChild(QObject, 'videoHoverPreview')
        if timeline_span is not None:
            span = min(backend.duration, timeline_span)
            timeline.setProperty('pixelsPerSecond', bounds.width() / span)
            timeline.setProperty('viewStart', max(0, (backend.duration - span) / 2))
        actual_span = min(backend.duration, timeline.property('viewSpan'))

        def point(fraction):
            return QPoint(round(bounds.x() + actual_span * fraction
                                * timeline.property('pixelsPerSecond')),
                          round(bounds.y() + 36))

        if synthetic_cached:
            # Diagnostic only: remove decode/upload cost to expose QML sampling limits.
            # Never interpret this mode as real preview performance or image correctness.
            backend._cache_worker.cancel()
            sample = backend.images._live.scaled(160, 90)
            def instant_frame(target):
                start = math.floor(target * backend.nominalFps) / backend.nominalFps
                return Picture(start, start + 1 / backend.nominalFps, sample)
            backend._scrub_cache.get = instant_frame
        if not immediate_drag:
            gesture(lambda: QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.05)))
        # Run continuous input BEFORE isolated seeks can populate the frame cache.
        # Do not wait for decoding between moves: detect motion-time starvation.
        rapid_frames = []
        rapid_sizes = set()
        pointer_errors = []
        input_dispatch_ms = []
        move_times = []
        input_records = []
        correct_request_ages, correct_input_ages = [], []
        frame_pixel_errors, content_times = [], []
        delivered_deadline_errors = []
        sampled_job_ages, sampled_target_errors = [], []
        exact_job_ages, approximate_job_ages = [], []
        exact_job_frames, approximate_job_frames, covering_job_frames = [], [], []
        frame_records = []
        rapid_quality_errors = []
        rapid_target = [backend.position]
        prepared_at_start = backend.previewReady
        rapid_resource_start = len(cpu_samples)
        rapid_swap_start = swaps[0]
        rapid_window_start = {'exposed': window.isExposed(), 'active': window.isActive(),
                              'visible': window.isVisible()}
        rapid_started = time.perf_counter()

        def rapid_frame():
            rapid_frames.append((time.perf_counter() - rapid_started,
                                 abs(backend.position - rapid_target[0])))
            now = time.perf_counter()
            frame = last_picture[0]
            origin = last_origin[0]
            approximate = frame.approximate
            if origin is not None:
                age_ms = (now - origin[0]) * 1000
                covers_job = frame.time - 1e-7 <= origin[1] < frame.end - 1e-7
                target_error_ms = (frame.time - origin[1]) * 1000
                useful_approximation = (approximate and
                                       (covers_job or abs(target_error_ms) <= 120 + 1e-6))
                exact = not approximate and covers_job
                sampled_job_ages.append(age_ms)
                sampled_target_errors.append(abs(target_error_ms))
                covering_job_frames.append(covers_job)
                exact_job_frames.append(exact)
                approximate_job_frames.append(useful_approximation)
                if exact:
                    exact_job_ages.append(age_ms)
                if useful_approximation:
                    approximate_job_ages.append(age_ms)
                # Attribute latency only to the input that caused the original
                # sampled job, never a later repeated visit to the same frame.
                requests = [row for row in scrub_requests
                            if row[0] <= origin[0] and abs(row[1] - origin[1]) < 1e-6]
                inputs = [row for row in input_records
                          if row[0] <= origin[0] and abs(row[1] - origin[1]) < 1e-6]
                input_age_ms = (now - inputs[-1][0]) * 1000 if inputs else None
                request_age_ms = (now - requests[-1][0]) * 1000 if requests else None
                if exact and requests:
                    correct_request_ages.append(request_age_ms)
                if exact and inputs:
                    correct_input_ages.append(input_age_ms)
                frame_records.append({'shown_at_ms': (now - rapid_started) * 1000,
                                      'pts_seconds': frame.time, 'end_seconds': frame.end,
                                      'sampled_target_seconds': origin[1],
                                      'sampled_job_age_ms': age_ms,
                                      'original_input_age_ms': input_age_ms,
                                      'original_request_age_ms': request_age_ms,
                                      'signed_pts_error_ms': target_error_ms,
                                      'approximate': approximate,
                                      'covers_original_sampled_job': covers_job,
                                      'valid_browsing_frame': exact or useful_approximation})
            else:
                frame_records.append({'shown_at_ms': (now - rapid_started) * 1000,
                                      'pts_seconds': frame.time, 'end_seconds': frame.end,
                                      'approximate': approximate,
                                      'sampled_target_seconds': None})
            frame_distance = max(frame.time - rapid_target[0],
                                 rapid_target[0] - frame.end, 0)
            frame_pixel_errors.append(frame_distance * timeline.property('pixelsPerSecond'))
            content_times.append(frame.time)
            rapid_sizes.add((backend.images._live.width(), backend.images._live.height()))
            if not synthetic_cached and not viewport_quality_ok():
                rapid_quality_errors.append(True)

        move_count = [0]
        randomizer = random.Random(42)
        # Index by scheduled input, not delivered callbacks: A/B coalescing must
        # not change the random trajectory that the pointer would have followed.
        random_fractions = [randomizer.uniform(.05, .95) for _ in range(rapid_moves)]
        rapid_timer = QTimer()
        rapid_timer.setTimerType(Qt.TimerType.PreciseTimer)
        rapid_timer.setSingleShot(True)

        def rapid_move():
            now = time.perf_counter()
            move_times.append(now)
            deadline = rapid_started + (move_count[0] + 1) / input_hz
            delivered_deadline_errors.append(max(0, now - deadline) * 1000)
            # A delayed UI must receive the pointer's current coordinate, not
            # replay stale coordinates at 1 ms intervals after it catches up.
            scheduled_index = min(rapid_moves, max(move_count[0] + 1,
                math.floor((now - rapid_started) * input_hz)))
            if trajectory == 'triangle':
                phase = (scheduled_index / input_hz / half_sweep_seconds) % 2
                fraction = .05 + .9 * (phase if phase <= 1 else 2 - phase)
            elif trajectory == 'sweep':
                fraction = .05 + .9 * scheduled_index / rapid_moves
            else:
                fraction = random_fractions[scheduled_index - 1]
            pos = point(fraction)
            rapid_target[0] = (timeline.property('viewStart')
                               + (pos.x() - bounds.x()) / timeline.property('pixelsPerSecond'))
            input_records.append((now, rapid_target[0]))
            dispatched = time.perf_counter()
            QTest.mouseMove(window, pos, delay=0)
            input_dispatch_ms.append((time.perf_counter() - dispatched) * 1000)
            pointer_errors.append(abs(timeline.property('playheadTime') - rapid_target[0])
                                  * timeline.property('pixelsPerSecond'))
            move_count[0] = scheduled_index
            if move_count[0] < rapid_moves:
                next_deadline = rapid_started + (move_count[0] + 1) / input_hz
                rapid_timer.start(max(1, math.ceil((next_deadline - time.perf_counter()) * 1000)))

        backend.frameChanged.connect(rapid_frame)
        rapid_timer.timeout.connect(rapid_move)
        recording_scrubs[0] = True
        if immediate_drag:
            # Do not let thumbnail generation or an isolated press-seek warm the
            # application caches before the first continuous gesture.
            press_point = point(.05)
            rapid_target[0] = (timeline.property('viewStart')
                              + (press_point.x() - bounds.x())
                              / timeline.property('pixelsPerSecond'))
            input_records.append((time.perf_counter(), rapid_target[0]))
            QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=press_point)
        rapid_timer.start(math.ceil(1000 / input_hz))
        try:
            wait_for(lambda: move_count[0] >= rapid_moves)
        finally:
            rapid_timer.stop()
            backend.frameChanged.disconnect(rapid_frame)
            recording_scrubs[0] = False
        rapid_duration = time.perf_counter() - rapid_started
        rapid_window_end = {'exposed': window.isExposed(), 'active': window.isActive(),
                            'visible': window.isVisible()}
        if rapid_quality_errors:
            raise RuntimeError('Rapid dragging undersampled the visible preview pixels')
        frame_times = [0, *[row[0] for row in rapid_frames], rapid_duration]
        rapid_report = {
            'measurement': 'continuous pointer moves; decoded frames, not display swaps',
            'window_state_at_start': rapid_window_start,
            'window_state_at_end': rapid_window_end,
            'window_frame_swapped_count': swaps[0] - rapid_swap_start,
            'window_frame_swapped_hz': (swaps[0] - rapid_swap_start) / rapid_duration,
            'window_frame_swapped_caveat': ('Scene submissions can repeat the same video frame; '
                                          'not physical display scanout or new decoded content'),
            'pointer_updates': len(move_times), 'frames_during_motion': len(rapid_frames),
            'sampler_version': 2,
            'input_driver': ('GUI deadlines with latest-coordinate coalescing; '
                             'not OS hardware input'),
            'scheduled_pointer_updates': rapid_moves,
            'coalesced_pointer_updates': rapid_moves - len(move_times),
            'input_nominal_hz': input_hz,
            'trajectory': trajectory,
            'random_seed': 42 if trajectory == 'random' else None,
            'half_sweep_seconds': half_sweep_seconds if trajectory == 'triangle' else None,
            'nominal_pointer_pixels_per_second': (
                .9 * bounds.width() / half_sweep_seconds if trajectory == 'triangle' else
                .9 * bounds.width() / (rapid_moves / input_hz) if trajectory == 'sweep' else None),
            'first_motion_frame_ms': rapid_frames[0][0] * 1000 if rapid_frames else None,
            'input_delivery_deadline_error_ms': summarize(delivered_deadline_errors),
            'input_effective_hz': len(move_times) / rapid_duration,
            'controller_scrub_requests': len(scrub_requests),
            'controller_scrub_hz': len(scrub_requests) / rapid_duration,
            'controller_scrub_gap_ms': (summarize([(b[0] - a[0]) * 1000 for a, b in
                zip(scrub_requests, scrub_requests[1:], strict=False)])
                if len(scrub_requests) > 1 else None),
            'exact_requested_frames': sum(exact_job_frames),
            'approximate_browsing_frames': sum(approximate_job_frames),
            'valid_browsing_frames': sum(exact_job_frames) + sum(approximate_job_frames),
            'frames_without_original_sampled_job': len(rapid_frames) - len(exact_job_frames),
            'invalid_sampled_frames': sum(not exact and not approximate for exact, approximate in
                                        zip(exact_job_frames, approximate_job_frames, strict=True)),
            'exact_requested_frame_fps': sum(exact_job_frames) / rapid_duration,
            'approximate_browsing_frame_fps': sum(approximate_job_frames) / rapid_duration,
            'valid_browsing_frame_fps': ((sum(exact_job_frames) + sum(approximate_job_frames))
                                         / rapid_duration),
            'content_change_fps': (sum(a != b for a, b in
                zip(content_times, content_times[1:], strict=False)) / rapid_duration),
            'sampled_job_age_ms': summarize(sampled_job_ages) if sampled_job_ages else None,
            'exact_sampled_job_age_ms': summarize(exact_job_ages) if exact_job_ages else None,
            'approximate_sampled_job_age_ms': (summarize(approximate_job_ages)
                                               if approximate_job_ages else None),
            'sampled_target_pts_error_ms': (summarize(sampled_target_errors)
                                            if sampled_target_errors else None),
            'frames_covering_original_sampled_job': sum(covering_job_frames),
            'frames_with_original_sampled_job': len(covering_job_frames),
            'frame_records': frame_records,
            'time_window_seconds': 2,
            'time_window_measurement': (
                'Frames grouped by decoded publication time; original sampled-job/input ages. '
                'Resource samples assigned by observation time. Cross-boundary frame gaps '
                'are clipped to each window; aggregate update_gap_ms remains authoritative.'),
            'time_windows': summarize_motion_windows(
                frame_records, resource_records, move_times, scrub_requests,
                rapid_started, rapid_duration, rapid_moves / input_hz),
            'request_to_correct_frame_ms': (summarize(correct_request_ages)
                                            if correct_request_ages else None),
            'input_to_correct_frame_ms': (summarize(correct_input_ages)
                                          if correct_input_ages else None),
            'current_pointer_frame_error_pixels': (summarize_values(frame_pixel_errors)
                                                    if frame_pixel_errors else None),
            'timeline_visible_seconds': actual_span,
            'synthetic_cached_diagnostic': synthetic_cached,
            'duration_ms': rapid_duration * 1000,
            'delivered_input_gap_ms': summarize([(b - a) * 1000 for a, b in
                zip([rapid_started, *move_times], move_times, strict=False)]),
            'preview_prepared_at_start': prepared_at_start,
            'first_presented_frame_to_motion_ms': (rapid_started - first_presented_at) * 1000,
            'immediate_drag_after_first_frame': immediate_drag,
            'first_drag_delay_ms': first_drag_delay_ms,
            'drag_strategy': 'exact_only_baseline' if exact_drag_only else 'adaptive',
            'frame_sizes': sorted(rapid_sizes),
            'cpu_percent_of_one_core': summarize_values(cpu_samples[rapid_resource_start:]),
            'host_cpu_percent': summarize_values(host_cpu_samples[rapid_resource_start:]),
            'rss_mb': summarize_values(rss_samples[rapid_resource_start:]),
            'pointer_max_error_pixels': max(pointer_errors),
            'input_dispatch_ms': summarize(input_dispatch_ms),
            'update_gap_ms': summarize([(b - a) * 1000
                                        for a, b in zip(frame_times, frame_times[1:],
                                                        strict=False)]),
            'video_position_error_ms': (summarize([row[1] * 1000 for row in rapid_frames])
                                       if rapid_frames else None)}
        timings.clear()
        elapsed = []
        for fraction in fractions * 4:
            elapsed.append(gesture(
                lambda fraction=fraction: QTest.mouseMove(window, point(fraction), delay=0)))
            if not synthetic_cached and not viewport_quality_ok():
                raise RuntimeError('Dragging undersampled the visible preview pixels')
            target = (timeline.property('viewStart') + (point(fraction).x() - bounds.x())
                      / timeline.property('pixelsPerSecond'))
            if abs(backend.position - target) > 2 / backend.nominalFps:
                raise RuntimeError('Timeline presented a frame outside the requested position')
            if popup.property('visible'):
                raise RuntimeError('Hover popup is visible during dragging')
        drag_timings = list(timings)
        # Release at a different point, not the already displayed final drag frame.
        release_point = point(.37)
        release_target = (timeline.property('viewStart') + (release_point.x() - bounds.x())
                          / timeline.property('pixelsPerSecond'))
        release_ms = gesture(lambda: QTest.mouseRelease(
            window, Qt.MouseButton.LeftButton, pos=release_point),
            preview_target=release_target)
        native_size = (backend._info['width'], backend._info['height'])
        if (not synthetic_cached
                and (backend.images._live.width(), backend.images._live.height()) != native_size):
            raise RuntimeError('Releasing the timeline did not restore native resolution')
        sample_resources()
        displayed_quality = None
        if not synthetic_cached and backend._proxy is not None:
            preview = backend._proxy.get(release_target)
            if preview is not None:
                display_width = max(1, round(picture.property('paintedWidth')
                                             * window.devicePixelRatio()))
                display_height = max(1, round(picture.property('paintedHeight')
                                              * window.devicePixelRatio()))
                def displayed_pixels(image):
                    scaled = image.scaled(display_width, display_height,
                                          Qt.AspectRatioMode.KeepAspectRatio,
                                          Qt.TransformationMode.SmoothTransformation)
                    rgb = scaled.convertToFormat(QImage.Format.Format_RGB888)
                    return bytes(rgb.constBits())
                reference = displayed_pixels(backend.images._live)
                proxy_pixels = displayed_pixels(preview.image)
                mse = sum((a - b) ** 2 for a, b in zip(reference, proxy_pixels, strict=True))
                mse /= max(1, len(reference))
                displayed_quality = {
                    'measurement': 'proxy vs exact frame, Qt smooth downscale to physical viewport',
                    'proxy_frame_size': [preview.image.width(), preview.image.height()],
                    'viewport_size': [display_width, display_height],
                    'mean_squared_channel_error': mse,
                    'psnr_db': 10 * math.log10(255**2 / mse) if mse else None,
                    'identical': mse == 0}
        report = {'measurement' : 'upper bound: mouse event to two swaps after Image ready',
                'frozen': bool(getattr(sys, 'frozen', False)),
                'controller_module_file': (
                    sys.modules[VideoPreviewController.__module__].__file__),
                'decoder_module_file': sys.modules[PlaybackDecoder.__module__].__file__,
                'source_module_sha256': source_module_sha256,
                'qt_platform': app.platformName(),
                'qt_test_module_file': sys.modules['PySide6.QtTest'].__file__,
                'cpu_percent_of_one_core': summarize_values(cpu_samples),
                'rss_mb': summarize_values(rss_samples),
                'cache': 'application-managed',
                'session_directory': str(data_dir) if data_dir else None,
                'window': [window.width(), window.height()],
                'screen_refresh_hz': window.screen().refreshRate(),
                'device_pixel_ratio': window.devicePixelRatio(),
                'painted_size': [picture.property('paintedWidth'),
                                 picture.property('paintedHeight')],
                'pointer_cache_preparation_ms': preparation_ms,
                'first_frame_ms': first_ms, 'first_frame_stages': first_frame_stages,
                'drag': summarize(elapsed),
                'rapid_drag': rapid_report,
                'drag_stages': {stage: summarize([row[stage] for row in drag_timings])
                                for stage in drag_timings[0]},
                'release_to_correct_preview_ms': timings[-1]['correct_preview_image_ready_ms'],
                'release_to_source_frame_ms': release_ms,
                'release_stages': timings[-1],
                'release_frame_size': [backend.images._live.width(), backend.images._live.height()],
                'release_frame_approximate': last_picture[0].approximate,
                'release_frame_covers_target': (last_picture[0].time - 1e-7 <= release_target
                                                < last_picture[0].end - 1e-7),
                'displayed_proxy_quality': displayed_quality}
        return report
    finally:
        sampler.stop()
        shutdown_started = time.perf_counter()
        backend.shutdown()
        if 'report' in locals():
            report['shutdown_ms'] = (time.perf_counter() - shutdown_started) * 1000
            workers = [value for value in vars(backend).values()
                       if hasattr(value, '_thread') and hasattr(value, '_condition')]
            workers.append(backend._audio.worker)
            report['workers_remaining'] = [worker._thread.name for worker in workers
                                           if worker._thread.is_alive()]
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
    parser.add_argument('--wait-prepared', action='store_true',
                        help='Wait for application-managed full-quality proxy before gestures')
    parser.add_argument('--session-dir', type=Path,
                        help='Isolated application session/cache directory')
    parser.add_argument('--legacy-proxy', action='store_true',
                        help='Separately compare the obsolete JPEG proxy; not used by the UI')
    parser.add_argument('--ui', action='store_true',
                        help='Also measure actual Qt timeline dragging')
    parser.add_argument('--input-hz', type=float, default=60)
    parser.add_argument('--rapid-moves', type=int, default=60)
    parser.add_argument('--timeline-span', type=float)
    parser.add_argument('--trajectory', choices=['triangle', 'sweep', 'random'], default='triangle')
    parser.add_argument('--half-sweep-seconds', type=float, default=.25,
                        help='Triangle velocity independent of event frequency')
    parser.add_argument('--synthetic-cached', action='store_true',
                        help='Diagnostic only: instant 160x90 cache to isolate input sampling')
    parser.add_argument('--exact-drag-only', action='store_true',
                        help='Benchmark baseline: disable adaptive temporal sampling for drag jobs')
    parser.add_argument('--immediate-drag', action='store_true',
                        help='Start dragging after the first displayed frame; do not wait for '
                             'thumbnails or run source seek measurements before the UI')
    parser.add_argument('--first-drag-delay-ms', type=int, default=0,
                        help='Allow idle preparation this long after the first displayed frame')
    parser.add_argument('--cpu-count', type=int, help='Restrict this process to N available CPUs')
    args = parser.parse_args()
    if args.half_sweep_seconds <= 0:
        parser.error('--half-sweep-seconds must be positive')
    if args.input_hz <= 0 or args.rapid_moves < 2:
        parser.error('--input-hz must be positive; --rapid-moves must be at least 2')
    if args.timeline_span is not None and args.timeline_span <= 0:
        parser.error('--timeline-span must be positive')
    if args.wait_prepared and args.session_dir is None:
        parser.error('--wait-prepared requires --session-dir')
    if args.immediate_drag and (not args.ui or args.wait_prepared):
        parser.error('--immediate-drag requires --ui and cannot use --wait-prepared')
    if args.first_drag_delay_ms < 0 or (args.first_drag_delay_ms and not args.immediate_drag):
        parser.error('--first-drag-delay-ms must be non-negative and requires --immediate-drag')
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
    fractions = [.85, .1, .7, .25, .9, .4, .6]

    def run_ui():
        return measure_ui(source, None, fractions, data_dir=args.session_dir,
                          wait_prepared=args.wait_prepared, input_hz=args.input_hz,
                          rapid_moves=args.rapid_moves, timeline_span=args.timeline_span,
                          synthetic_cached=args.synthetic_cached,
                          trajectory=args.trajectory,
                          half_sweep_seconds=args.half_sweep_seconds,
                          exact_drag_only=args.exact_drag_only,
                          immediate_drag=args.immediate_drag,
                          first_drag_delay_ms=args.first_drag_delay_ms)

    # Immediate-start sessions must precede the standalone decoder benchmark;
    # otherwise its seven random seeks prewarm the OS file cache first.
    ui_report = run_ui() if args.ui and args.immediate_drag else None
    decoder = PlaybackDecoder()
    try:
        start = time.perf_counter()
        info, _ = decoder.open(str(source), 0, lambda: None)
        first_ms = (time.perf_counter() - start) * 1000
        targets = [info['duration'] * fraction for fraction in fractions]
        original = measure(lambda target: decoder.reader.seek(target, lambda: None), targets)
    finally:
        decoder.close()
    report = {'system': platform.platform(), 'machine': platform.machine(),
              'video': source.name, 'width': info['width'], 'height': info['height'],
              'duration_seconds': info['duration'], 'first_frame_ms': first_ms,
              'source_seek': original, 'frozen': bool(getattr(sys, 'frozen', False))}
    if args.legacy_proxy:
        on_demand = info['duration'] > 300 or source.stat().st_size >= 2 * 1024**3
        proxy = ScrubProxy(str(source), args.cache_dir, on_demand=on_demand)
        start = time.perf_counter()
        if on_demand:
            for target in targets:
                proxy.warm(target, lambda: None)
            complete = all(proxy.get(target) is not None for target in targets)
        else:
            complete = proxy.build(lambda: None)
        report['legacy_proxy'] = {
            'preparation_ms': (time.perf_counter() - start) * 1000,
            'complete': complete, 'bytes': proxy.path.stat().st_size,
            'seek': measure(proxy.get, targets * 4) if complete else None}
    report['cpu_affinity'] = process.cpu_affinity() if hasattr(process, 'cpu_affinity') else None
    if args.ui:
        report['ui'] = ui_report if ui_report is not None else run_ui()
        report['ui']['source_seek_benchmark_order'] = (
            'after_ui' if args.immediate_drag else 'before_ui')
        report['ui']['os_file_cache_flushed'] = False
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.ui and report['ui']['workers_remaining']:
        raise RuntimeError('Preview workers remained alive after shutdown')


if __name__ == '__main__':
    main()
