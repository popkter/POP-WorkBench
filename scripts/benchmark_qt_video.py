"""Cold seek prototype using QMediaPlayer directly into QML VideoOutput.

No QVideoFrame.toImage() call or CPU readback is made. Frame arrival is not
equivalent to visible display presentation, especially with an offscreen QPA.
Software-decoding configuration follows Qt's advanced FFmpeg documentation:
https://doc.qt.io/qtforpython-6.11/overviews/qtmultimedia-advanced-ffmpeg-configuration.html
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path


def stats(values):
    if not values:
        return None
    values = sorted(values)
    return {'count': len(values), 'median': statistics.median(values),
            'p95': values[min(len(values) - 1, int(len(values) * .95))], 'max': max(values)}


def run(args):
    if args.decode == 'software':
        os.environ['QT_FFMPEG_DECODING_HW_DEVICE_TYPES'] = ','
    from PySide6.QtCore import QEventLoop, QObject, QTimer, QUrl, qVersion
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtMultimedia import QMediaPlayer
    from PySide6.QtQml import QQmlComponent, QQmlEngine
    from PySide6.QtQuick import QQuickWindow

    app = QGuiApplication([])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Window
import QtMultimedia
Window {
    width: 1100; height: 720; visible: true; color: "black"
    VideoOutput { objectName: "videoOutput"; anchors.fill: parent }
}
''', QUrl())
    window = component.create()
    if not isinstance(window, QQuickWindow):
        raise RuntimeError([error.toString() for error in component.errors()])
    output = window.findChild(QObject, 'videoOutput')
    sink = output.property('videoSink')
    player = QMediaPlayer()
    player.setVideoSink(sink)
    frames, errors, inputs, sizes, handles = [], [], [], set(), set()
    swaps = [0]
    current = [0]
    in_flight = [None]
    queued = [None]
    native_seek_count = [0]

    def dispatch_latest():
        if queued[0] is not None and in_flight[0] is None:
            in_flight[0], queued[0] = queued[0], None
            native_seek_count[0] += 1
            player.setPosition(in_flight[0])

    def frame_received(frame):
        if not frame.isValid():
            return
        now = time.perf_counter()
        start, end = frame.startTime() / 1000, frame.endTime() / 1000
        match = next((row for row in reversed(inputs)
                      if start - 1 <= row['target_ms'] < end + 1), None)
        frames.append({'at': now, 'start_ms': start, 'end_ms': end,
                       'pointer_error_ms': abs(start - current[0]),
                       'matching_input_age_ms': ((now - match['at']) * 1000 if match else None),
                       'paused': player.playbackState() == QMediaPlayer.PlaybackState.PausedState})
        sizes.add((frame.width(), frame.height()))
        handles.add(str(frame.handleType()))
        if in_flight[0] is not None and start - 1 <= in_flight[0] < end + 1:
            in_flight[0] = None
            QTimer.singleShot(0, dispatch_latest)

    def swapped():
        swaps[0] += 1

    sink.videoFrameChanged.connect(frame_received)
    player.errorOccurred.connect(lambda error, message: errors.append(message))
    window.frameSwapped.connect(swapped)

    def wait_for(condition, timeout_ms=10000):
        if condition():
            return True
        loop, timer, timeout = QEventLoop(), QTimer(), QTimer()
        timer.timeout.connect(lambda: loop.quit() if condition() or errors else None)
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timer.start(1)
        timeout.start(timeout_ms)
        loop.exec()
        timer.stop()
        timeout.stop()
        return condition()

    try:
        # Establish the scene graph/RHI before opening media so VideoOutput can
        # give the backend its render device instead of a not-yet-created one.
        initial_swap = wait_for(lambda: swaps[0] > 0, timeout_ms=2000)
        first_started = time.perf_counter()
        player.setSource(QUrl.fromLocalFile(str(args.source.resolve())))
        player.play()
        if not wait_for(lambda: bool(frames)):
            raise RuntimeError(errors or 'No initial video frame')
        first_ms = (time.perf_counter() - first_started) * 1000
        player.pause()
        wait_for(lambda: player.playbackState() == QMediaPlayer.PlaybackState.PausedState)
        # Let the initial play/pause operation settle before measuring seeks.
        settle = QEventLoop()
        QTimer.singleShot(100, settle.quit)
        settle.exec()
        frames.clear()
        sizes.clear()
        handles.clear()
        if args.strategy == 'play':
            player.play()
        started = time.perf_counter()
        swaps_before = swaps[0]
        timer = QTimer()
        dispatched = []

        def move():
            index = len(inputs)
            phase = index % 30
            fraction = .05 + .9 * (phase if phase <= 15 else 30 - phase) / 15
            target = round(player.duration() * fraction)
            current[0] = target
            at = time.perf_counter()
            inputs.append({'target_ms': target, 'at': at})
            if args.queue == 'latest':
                queued[0] = target
                dispatch_latest()
            else:
                native_seek_count[0] += 1
                player.setPosition(target)
            dispatched.append((time.perf_counter() - at) * 1000)
            if len(inputs) >= args.samples:
                timer.stop()

        timer.timeout.connect(move)
        timer.start(16)
        wait_for(lambda: not timer.isActive(), timeout_ms=args.samples * 50 + 5000)
        timer.stop()
        motion_ended = time.perf_counter()
        motion_frames = [row for row in frames if row['at'] >= inputs[0]['at']]
        motion_swaps = swaps[0] - swaps_before
        queued[0] = in_flight[0] = None
        release_started = time.perf_counter()
        target = inputs[-1]['target_ms']
        player.pause()
        player.setPosition(target)
        final_correct = wait_for(lambda: bool(frames) and
                                 frames[-1]['start_ms'] - 1 <= target < frames[-1]['end_ms'] + 1,
                                 timeout_ms=5000)
        release_ms = (time.perf_counter() - release_started) * 1000
        frame_times = [started, *[row['at'] for row in motion_frames], motion_ended]
        paused_motion = sum(row['paused'] for row in motion_frames)
        for row in frames:
            row['at_ms'] = (row.pop('at') - started) * 1000
        return {
            'measurement': 'QVideoSink arrivals; VideoOutput connected; no toImage or readback',
            'qt_version': qVersion(), 'qpa': app.platformName(),
            'scenegraph_api': str(window.rendererInterface().graphicsApi()),
            'scenegraph_ready_before_media': initial_swap,
            'decode_configuration': args.decode,
            'hardware_priority_environment': os.environ.get('QT_FFMPEG_DECODING_HW_DEVICE_TYPES'),
            'scenegraph_backend_environment': os.environ.get('QT_QUICK_BACKEND'),
            'rhi_backend_environment': os.environ.get('QSG_RHI_BACKEND'),
            'hardware_decode_verified': False,
            'strategy': args.strategy, 'first_frame_ms': first_ms,
            'queue': args.queue, 'native_seek_count': native_seek_count[0],
            'source_duration_ms': player.duration(), 'input_count': len(inputs),
            'motion_duration_ms': (motion_ended - started) * 1000,
            'frames_during_motion': len(motion_frames), 'frames_while_paused': paused_motion,
            'frames_matching_requested_target': sum(row['matching_input_age_ms'] is not None
                                                    for row in motion_frames),
            'frame_arrival_fps': len(motion_frames) / (motion_ended - started),
            'frame_sizes': sorted(sizes), 'frame_handle_types': sorted(handles),
            'window_swaps_during_motion': motion_swaps,
            'input_dispatch_ms': stats(dispatched),
            'frame_gap_ms': stats([(b - a) * 1000
                                   for a, b in zip(frame_times, frame_times[1:], strict=False)]),
            'pointer_error_ms': stats([row['pointer_error_ms'] for row in motion_frames]),
            'matched_input_age_ms': stats([row['matching_input_age_ms'] for row in motion_frames
                                           if row['matching_input_age_ms'] is not None]),
            'release_ms': release_ms, 'release_correct_frame': final_correct,
            'final_frame': frames[-1] if frames else None,
            'errors': errors, 'frames': frames}
    finally:
        player.stop()
        player.setVideoSink(None)
        player.setSource(QUrl())
        window.close()
        app.processEvents()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--decode', choices=['default', 'software'], default='default')
    parser.add_argument('--strategy', choices=['paused', 'play'], default='paused')
    parser.add_argument('--samples', type=int, default=60)
    parser.add_argument('--queue', choices=['all', 'latest'], default='all')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: value for key, value in report.items() if key != 'frames'}, indent=2))


if __name__ == '__main__':
    main()
