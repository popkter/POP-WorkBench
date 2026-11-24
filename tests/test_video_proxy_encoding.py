"""Proxy JPEG parallelism preserves order, pixels and bounded image ownership."""
import os
import sqlite3
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Cancelled, Picture
from poptools.infrastructure.video_proxy import ScrubProxy


@pytest.fixture(autouse=True)
def application(qapp):
    # Production constructs QApplication before any Qt image codec worker.
    return qapp


class SizedImage:
    """A storage counter for large-frame scheduling tests without large allocations."""
    def __init__(self, serial, size):
        self.serial = serial
        self.size = size

    def sizeInBytes(self):
        return self.size


def make_reader(monkeypatch, dimensions=(32, 18), count=9, real_images=False):
    readers = []

    class Reader:
        def __init__(self, source):
            self.stream = SimpleNamespace(codec_context=SimpleNamespace(thread_count=2))
            self.output_height = 0
            self.rotation = 0
            self.owner = threading.get_ident()
            self.closed = False
            self.produced = []
            self.frames = [SimpleNamespace(width=dimensions[0], height=dimensions[1],
                                           index=index, time=index * .04)
                           for index in range(count)]
            readers.append(self)

        def seek_raw(self, target, check):
            check()
            self.index = min(count, int(round(target / .04)))
            return self.raw_next(check)

        def raw_next(self, check):
            assert threading.get_ident() == self.owner
            check()
            if self.index >= count:
                return None
            frame = self.frames[self.index]
            self.index += 1
            return frame

        @staticmethod
        def timestamp(frame):
            return frame.time

        def picture(self, frame, width):
            assert threading.get_ident() == self.owner
            scale = min(1, self.output_height / min(dimensions)) if self.output_height else 1
            width = max(2, round(dimensions[0] * scale))
            height = max(2, round(dimensions[1] * scale))
            if real_images:
                image = QImage(width, height, QImage.Format.Format_RGB888)
                image.fill(0xFF000000 | ((frame.index + 1) << 16) | 0x2030)
            else:
                image = SizedImage(frame.index, ((width * 3 + 3) // 4 * 4) * height)
            self.produced.append(frame.index)
            return Picture(frame.time, frame.time + .04, image)

        def close(self):
            assert threading.get_ident() == self.owner
            self.closed = True

    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader', Reader)
    return readers


def make_proxy(tmp_path):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'Only the fake reader opens this fixture')
    return ScrubProxy(str(source), tmp_path / 'proxy', full_quality=True)


def start_build(proxy, check=lambda: None):
    outcome = []

    def run():
        try:
            outcome.append(proxy.build(check))
        except BaseException as error:
            outcome.append(error)

    worker = threading.Thread(target=run)
    worker.start()
    return worker, outcome


def wait_until(condition):
    deadline = time.monotonic() + 3
    while not condition():
        assert time.monotonic() < deadline
        time.sleep(.005)


def test_parallel_results_keep_jpeg_quality_and_single_owner_write_order(tmp_path, monkeypatch):
    readers = make_reader(monkeypatch, real_images=True)
    proxy = make_proxy(tmp_path)
    serial_encode = proxy._encode_image
    completed, inserted, write_threads = [], [], set()
    second_done = threading.Event()

    def encode(image, quality):
        serial = image.pixelColor(0, 0).red() - 1
        if serial == 0:
            assert second_done.wait(3)
        data = serial_encode(image, quality)
        completed.append(serial)
        if serial == 1:
            second_done.set()
        return data

    class TrackedConnection(sqlite3.Connection):
        def execute(self, query, parameters=()):
            if query.startswith('INSERT OR REPLACE INTO frames'):
                inserted.append(parameters[0])
                write_threads.add(threading.get_ident())
            return super().execute(query, parameters)

    connect = sqlite3.connect
    monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect',
                        lambda *args, **kwargs: connect(*args, factory=TrackedConnection, **kwargs))
    monkeypatch.setattr(proxy, '_encode_image', encode)
    assert proxy.build(lambda: None)
    assert completed.index(1) < completed.index(0)
    assert inserted == pytest.approx([index * .04 for index in range(9)])
    assert write_threads == {readers[0].owner}
    assert readers[0].closed
    with connect(proxy.path) as db:
        rows = db.execute('SELECT time, end, jpeg FROM frames ORDER BY time').fetchall()
    for index, (timestamp, frame_end, encoded) in enumerate(rows):
        image = QImage(32, 18, QImage.Format.Format_RGB888)
        image.fill(0xFF000000 | ((index + 1) << 16) | 0x2030)
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        assert image.save(buffer, 'JPEG', 95)
        assert encoded == bytes(buffer.data())
        assert timestamp == pytest.approx(index * .04)
        assert frame_end == pytest.approx((index + 1) * .04)


@pytest.mark.parametrize('dimensions,slots', [
    ((1280, 720), 3), ((2800, 1600), 2), ((3840, 2160), 1), ((7680, 4320), 1),
])
def test_encoding_queue_obeys_frame_and_rgb_budgets(tmp_path, monkeypatch, dimensions, slots):
    readers = make_reader(monkeypatch, dimensions=dimensions)
    proxy = make_proxy(tmp_path)
    release = threading.Event()
    started = []

    def encode(image, quality):
        started.append(threading.get_ident())
        assert release.wait(3)
        return b'JPEG'

    monkeypatch.setattr(proxy, '_encode_image', encode)
    worker, outcome = start_build(proxy)
    try:
        wait_until(lambda: bool(readers) and len(readers[0].produced) == slots
                   and len(started) == min(2, slots))
        time.sleep(.03)
        assert len(readers[0].produced) == slots
        assert len(set(started)) <= 2
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and outcome == [True]
    assert readers[0].closed


def test_cancel_drops_waiting_job_and_joins_running_encoders(tmp_path, monkeypatch):
    readers = make_reader(monkeypatch)
    proxy = make_proxy(tmp_path)
    cancel, observed, release = threading.Event(), threading.Event(), threading.Event()
    started = []

    def encode(image, quality):
        started.append(image.serial)
        assert release.wait(3)
        return b'JPEG'

    def check():
        if cancel.is_set():
            observed.set()
            raise Cancelled()

    monkeypatch.setattr(proxy, '_encode_image', encode)
    worker, outcome = start_build(proxy, check)
    try:
        wait_until(lambda: len(started) == 2 and len(readers[0].produced) == 3)
        cancel.set()
        assert observed.wait(3)
        time.sleep(.03)
        assert worker.is_alive()  # Cleanup waits for only the two running saves.
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and isinstance(outcome[0], Cancelled)
    assert started == [0, 1] and readers[0].closed
    assert not proxy.status()['complete']
    assert not any(thread.name.startswith('video-proxy-jpeg') for thread in threading.enumerate())


@pytest.mark.parametrize('failure', [ValueError('JPEG unavailable'),
                                     TimeoutError('encoder failure')])
def test_encoder_error_cleans_up_and_does_not_mark_cache_complete(
        tmp_path, monkeypatch, failure):
    readers = make_reader(monkeypatch)
    proxy = make_proxy(tmp_path)
    release = threading.Event()
    both_started = threading.Event()
    started = []

    def encode(image, quality):
        started.append(image.serial)
        if len(started) >= 2:
            both_started.set()
        if image.serial == 0:
            assert both_started.wait(3)
            raise failure
        assert release.wait(3)
        return b'JPEG'

    monkeypatch.setattr(proxy, '_encode_image', encode)
    worker, outcome = start_build(proxy)
    try:
        assert both_started.wait(3)
        time.sleep(.05)
        assert worker.is_alive()
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive() and readers[0].closed
    assert not proxy.status()['complete']
    if isinstance(failure, OSError):
        assert outcome == [False] and proxy.build_disabled
    else:
        assert outcome == [failure]
    assert not any(thread.name.startswith('video-proxy-jpeg') for thread in threading.enumerate())


def test_standalone_build_can_create_qapplication_afterward(tmp_path):
    script = '''
import sys
from pathlib import Path
import av
from PIL import Image
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
import poptools.infrastructure.video_proxy as module

directory = Path(sys.argv[1])
source = directory / 'standalone.mp4'
with av.open(str(source), 'w') as output:
    stream = output.add_stream('libx264', rate=25)
    stream.width, stream.height, stream.pix_fmt = 32, 18, 'yuv420p'
    for index in range(3):
        frame = av.VideoFrame.from_image(Image.new('RGB', (32, 18), (index * 30, 60, 90)))
        for packet in stream.encode(frame):
            output.mux(packet)
    for packet in stream.encode():
        output.mux(packet)

assert QCoreApplication.instance() is None
def no_threads(*args, **kwargs):
    raise AssertionError('Headless Qt codec initialization must stay on the owner')
module.ThreadPoolExecutor = no_threads
proxy = module.ScrubProxy(str(source), directory / 'cache', full_quality=True)
assert proxy.build(lambda: None)
assert proxy.get(.04) is not None
application = QApplication([])
application.processEvents()
print('standalone-to-gui-ok')
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)],
                            env={**os.environ, 'QT_QPA_PLATFORM': 'offscreen'},
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'standalone-to-gui-ok' in result.stdout
