import sqlite3
import threading
from fractions import Fraction

import av
import pytest
from PIL import Image, ImageDraw

from poptools.infrastructure.video_proxy import ScrubProxy


@pytest.fixture
def hd_video(tmp_path):
    path = tmp_path / "hd.mp4"
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=25)
        stream.width, stream.height = 1280, 720
        stream.pix_fmt = "yuv420p"
        for index in range(4):
            image = Image.new("RGB", (1280, 720), (30, 60, 90))
            ImageDraw.Draw(image).text((20, 20), f"Preview detail {index}", fill="white")
            frame = av.VideoFrame.from_image(image)
            frame.pts, frame.time_base = index, Fraction(1, 25)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    return path


def test_full_quality_proxy_preserves_dimensions_and_isolates_legacy_cache(hd_video, tmp_path):
    directory = tmp_path / "cache"
    legacy = ScrubProxy(str(hd_video), directory)
    native = ScrubProxy(str(hd_video), directory, full_quality=True)
    scaled = ScrubProxy(str(hd_video), directory, full_quality=True, output_height=180)
    assert len({legacy.path, native.path, scaled.path}) == 3
    for proxy, size in ((legacy, (960, 540)), (native, (1280, 720)), (scaled, (320, 180))):
        assert proxy.build(lambda: None)
        image = proxy.get(.08).image
        assert (image.width(), image.height()) == size
        status = proxy.status()
        assert status['complete'] and not status['limited']
        assert status['frames'] == 4 and status['seconds'] == pytest.approx(.16)
        assert 0 < status['bytes'] <= proxy.MAX_FILE_BYTES
    reopened = ScrubProxy(str(hd_video), directory, full_quality=True)
    assert reopened.path == native.path and reopened.get(.08).image.width() == 1280


def test_capacity_limited_proxy_does_not_redecode_on_every_retry(hd_video, tmp_path, monkeypatch):
    proxy = ScrubProxy(str(hd_video), tmp_path / 'limited', full_quality=True)
    proxy.MAX_FILE_BYTES = 100
    assert not proxy.build(lambda: None)
    assert proxy.status()['limited']
    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader',
                        lambda *a: pytest.fail('Saturated full build must not restart decoding'))
    assert not proxy.build(lambda: None)


def test_unwritable_cache_disables_preparation_without_breaking_playback(
        hd_video, tmp_path, monkeypatch):
    proxy = ScrubProxy(str(hd_video), tmp_path / 'unwritable', full_quality=True)
    attempts = []

    def unavailable(*args, **kwargs):
        attempts.append(None)
        raise sqlite3.OperationalError('attempt to write a readonly database')

    monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect', unavailable)
    assert not proxy.build(lambda: None)
    assert proxy.build_disabled
    assert not proxy.build(lambda: None)
    assert len(attempts) == 1


def test_pruning_runs_once_during_background_preparation(hd_video, tmp_path, monkeypatch):
    pruned = []
    monkeypatch.setattr(ScrubProxy, '_prune', lambda self: pruned.append(None))
    proxy = ScrubProxy(str(hd_video), tmp_path / 'prune', full_quality=True)
    assert not pruned
    assert proxy.build(lambda: None)
    assert proxy.build(lambda: None)
    assert len(pruned) == 1


def test_new_proxy_target_waits_for_pending_cached_frame_before_following_latest(
        hd_video, tmp_path, qapp, qtbot, monkeypatch):
    from poptools.infrastructure.video_media import VideoReader
    from poptools.infrastructure.video_scrub import ScrubCache
    from poptools.viewmodels.video_preview_controller import VideoPreviewController

    proxy = ScrubProxy(str(hd_video), tmp_path / 'ready', full_quality=True)
    assert proxy.build(lambda: None)
    first_started, second_started = threading.Event(), threading.Event()
    first_release, second_release = threading.Event(), threading.Event()
    original_get = proxy._read_frame

    def pending_get(target, tolerance):
        if target == .04:
            first_started.set()
            assert first_release.wait(2)
        elif target == .08:
            second_started.set()
            assert second_release.wait(2)
        return original_get(target, tolerance)

    monkeypatch.setattr(proxy, '_read_frame', pending_get)
    backend = VideoPreviewController()
    shown = []
    try:
        backend.addFiles([str(hd_video)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._cache_worker.cancel()
        backend._scrub_cache = ScrubCache(str(hd_video))
        backend._proxy = proxy
        backend.frameChanged.connect(lambda: shown.append(backend.position))
        backend.beginScrub()
        backend.scrub(.04)
        qtbot.waitUntil(first_started.is_set)
        request, token = backend._scrub_request, backend._token
        backend.scrub(.08)
        assert backend._scrub_request is request and backend._token == token
        first_release.set()
        qtbot.waitUntil(second_started.is_set)
        assert shown == pytest.approx([.04])  # A fresh cache read can finish without starvation.
        backend.endScrub(.08)
        second_release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        reader = VideoReader(str(hd_video))
        try:
            assert backend.images._live == reader.seek(.08, lambda: None).image
        finally:
            reader.close()
    finally:
        first_release.set()
        second_release.set()
        backend.shutdown()


@pytest.mark.parametrize("preview_source", ["proxy", "drag-cache"])
def test_release_shows_correct_preview_before_slow_native_refinement(
        hd_video, tmp_path, qapp, qtbot, monkeypatch, preview_source):
    from poptools.infrastructure.video_media import VideoReader
    from poptools.infrastructure.video_scrub import ScrubCache
    from poptools.viewmodels.video_preview_controller import VideoPreviewController

    proxy = None
    if preview_source == "proxy":
        proxy = ScrubProxy(str(hd_video), tmp_path / 'release', full_quality=True)
        assert proxy.build(lambda: None)
    backend = VideoPreviewController()
    decoding, release = threading.Event(), threading.Event()
    try:
        backend.addFiles([str(hd_video)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._stop_preparation()
        backend._scrub_cache = ScrubCache(str(hd_video))
        backend._proxy = proxy
        backend._drag_cache = ScrubCache(str(hd_video), output_height=64)
        reader = VideoReader(str(hd_video))
        try:
            reader.output_height = 64
            drag_picture = reader.seek(.08, lambda: None)
        finally:
            reader.close()
        drag_picture.approximate = proxy is not None
        backend._drag_cache.put(drag_picture)
        expected = proxy.get(.08) if proxy else drag_picture
        seek = backend._decoder.reader.seek
        def slow_native(target, check):
            decoding.set()
            assert release.wait(2)
            return seek(target, check)
        monkeypatch.setattr(backend._decoder.reader, 'seek', slow_native)
        backend.beginScrub()
        backend.endScrub(.08)
        if preview_source == "drag-cache":
            assert backend.position == .08
            assert backend.images._live == expected.image
        qtbot.waitUntil(lambda: decoding.is_set() and backend.position == .08)
        assert backend.busy
        assert backend.images._live == expected.image
        release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live == seek(.08, lambda: None).image
    finally:
        release.set()
        backend.shutdown()
