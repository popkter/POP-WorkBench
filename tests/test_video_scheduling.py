import threading
import time
import weakref
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import LatestWorker, Picture, VideoReader
from poptools.infrastructure.video_scrub import ScrubRequest
from poptools.viewmodels.video_preview_controller import VideoPreviewController
from test_video_preview import make_video


def test_idle_worker_releases_completed_job_and_decoded_frame(qapp, qtbot):
    class Payload:
        pass

    task_cache = Payload()
    task_cache_ref = weakref.ref(task_cache)
    received = []
    worker = LatestWorker('video-lifetime-test')

    def decode(check, cache=task_cache):
        check()
        return Payload()

    def completed(_token, picture):
        assert isinstance(picture, Payload)
        received.append(weakref.ref(picture))

    worker.completed.connect(completed)
    try:
        worker.submit(decode)
        del decode, task_cache
        qtbot.waitUntil(lambda: bool(received))
        qtbot.waitUntil(lambda: task_cache_ref() is None and received[0]() is None)
    finally:
        worker.close()


def test_scrub_mailbox_keeps_only_latest_image_and_rejects_distant_targets():
    image = QImage(16, 16, QImage.Format.Format_RGB888)
    request = ScrubRequest(1)
    assert request.publish(Picture(1, 1.04, image))
    for _ in range(50):
        assert not request.publish(Picture(1.02, 1.06, image))
    assert request.take_progress().time == 1.02
    assert request.take_progress() is None
    assert request.publish(Picture(1, 1.04, image))
    request.update(8)
    assert request.take_progress() is None
    assert not request.publish(Picture(1, 1.04, image))


def test_playback_drops_expired_frames_without_converting_them(tmp_path, monkeypatch):
    path = make_video(tmp_path / 'vfr.mkv', pts=[0, 40, 80, 160, 200, 320, 360, 400, 560, 600])
    reader = VideoReader(str(path))
    converted = []
    picture = reader.picture
    def convert(frame, *args):
        converted.append(reader.timestamp(frame))
        return picture(frame, *args)
    monkeypatch.setattr(reader, 'picture', convert)
    try:
        actual = reader.next_for_time(.39, lambda: None)
        assert actual.time == pytest.approx(.36)
        assert actual.end == pytest.approx(.4)
        assert converted == pytest.approx([.36])
        assert reader.next(lambda: None).time == pytest.approx(.4)
    finally:
        reader.close()


def test_drag_defers_thumbnails_and_resumes_idle_prefetch(qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / 'clip.mp4')
    backend = VideoPreviewController()
    warmed = []
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._cache_worker.cancel()
        monkeypatch.setattr(backend._scrub_cache, 'warm',
                            lambda target, check: warmed.append(target))
        backend.beginScrub()
        backend.requestThumbnails(.2, .6, 2500)
        assert backend._deferred_thumbnails == (.2, .6, 2500)
        assert not backend.thumbnailBusy
        backend.scrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        qtbot.wait(180)
        assert not warmed
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy and bool(backend.thumbnails))
        qtbot.waitUntil(lambda: bool(warmed))
        assert warmed[-1] == pytest.approx(.8)
        assert backend._deferred_thumbnails is None
    finally:
        backend.shutdown()


def test_expensive_exact_seek_releases_filmstrip_decoder_until_ready(qapp, qtbot, tmp_path,
                                                                    monkeypatch):
    from poptools.viewmodels import video_preview_controller

    path = make_video(tmp_path / 'precise.mp4')
    backend = VideoPreviewController()
    started, resume = threading.Event(), threading.Event()
    original = video_preview_controller.filmstrip

    def filmstrip(*args, **kwargs):
        started.set()
        assert resume.wait(3)
        args[-1]()
        return original(*args, **kwargs)

    monkeypatch.setattr(video_preview_controller, 'filmstrip', filmstrip)
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._info['expensive_random_seek'] = True
        backend.requestThumbnails(0, .6, 2500)
        qtbot.waitUntil(started.is_set)
        backend.seek(.56)
        assert backend._deferred_thumbnails == (0, .6, 2500)
        assert not backend.thumbnailBusy
        resume.set()
        qtbot.waitUntil(lambda: not backend.busy and not backend.thumbnailBusy
                        and bool(backend.thumbnails))
        assert backend.position == pytest.approx(.56)
        assert backend._deferred_thumbnails is None
    finally:
        resume.set()
        backend.shutdown()


def test_cold_seek_finishes_and_only_latest_pending_target_is_decoded(qapp, qtbot, tmp_path,
                                                                     monkeypatch):
    from poptools.infrastructure.video_scrub import ScrubCache

    path = make_video(tmp_path / 'cold.mp4')
    backend = VideoPreviewController()
    first_started, second_started = threading.Event(), threading.Event()
    first_release, second_release = threading.Event(), threading.Event()
    calls, shown = [], []
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._stop_preparation()
        backend._scrub_cache = ScrubCache(str(path))
        seek = backend._decoder.reader.seek
        def slow_seek(target, check):
            calls.append(target)
            if len(calls) == 1:
                first_started.set()
                assert first_release.wait(2)
            elif len(calls) == 2:
                second_started.set()
                assert second_release.wait(2)
            check()
            return seek(target, check)
        monkeypatch.setattr(backend._decoder.reader, 'seek', slow_seek)
        backend.frameChanged.connect(lambda: shown.append(backend.position))
        backend.beginScrub()
        backend.scrub(.4)
        qtbot.waitUntil(first_started.is_set)
        for target in (.5, .6, .7, .8):
            backend.scrub(target)
        qtbot.wait(120)  # Source work may exceed the hot-cache freshness limit.
        first_release.set()
        qtbot.waitUntil(second_started.is_set)
        assert calls == [.4, .8]
        assert shown == pytest.approx([.4])
        backend.endScrub(.6)
        second_release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(.6)
        assert .8 not in shown  # Completion after release cannot roll the picture back.
    finally:
        first_release.set()
        second_release.set()
        backend.shutdown()


def test_viewport_memory_cache_is_separate_from_native_release(qapp, qtbot, tmp_path,
                                                              monkeypatch):
    path = make_video(tmp_path / 'hd.mp4', size=(1920, 1080))
    backend = VideoPreviewController(tmp_path / 'session')
    try:
        backend.setPreviewViewport(800, 450)
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._stop_preparation()
        backend._proxy = None  # Exercise the cold-source and memory paths.
        backend.beginScrub()
        backend.scrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1067
        assert backend._scrub_cache.get(.8) is None
        seek = backend._decoder.reader.seek
        monkeypatch.setattr(backend._decoder.reader, 'seek',
                            lambda *a: pytest.fail('Second pass should use the viewport cache'))
        backend.scrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        monkeypatch.setattr(backend._decoder.reader, 'seek', seek)
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1920
        assert backend._scrub_cache.get(.8).image == backend.images._live
        backend.beginScrub()
        # Evict viewport frames to force a native-cache hit on the next drag.
        backend._drag_cache = type(backend._drag_cache)(str(path), output_height=720)
        backend.scrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1280
        assert backend._scrub_cache.get(.8).image.width() == 1920
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1920
        assert backend._drag_cache._bytes <= 64 * 1024 * 1024
    finally:
        backend.shutdown()


@pytest.mark.parametrize('holding_still', [False, True])
def test_newly_prepared_proxy_preempts_slow_source_seek(qapp, qtbot, tmp_path,
                                                      monkeypatch, holding_still):
    from poptools.infrastructure.video_media import Cancelled

    path = make_video(tmp_path / 'newly-ready.mp4')
    reference = VideoReader(str(path))
    try:
        prepared = reference.seek(.8, lambda: None)
    finally:
        reference.close()
    backend = VideoPreviewController(tmp_path / 'session')
    started, prepared_ready, cancelled = (threading.Event() for _ in range(3))
    release = threading.Event()
    calls, shown = [], []
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.beginScrub()
        proxy = backend._proxy
        monkeypatch.setattr(proxy, '_read_frame',
                            lambda target, tolerance: prepared
                            if prepared_ready.is_set() and target == .8 else None)
        monkeypatch.setattr(proxy, 'contains_memory',
                            lambda target: prepared_ready.is_set() and target == .8,
                            raising=False)
        seek = backend._decoder.reader.seek

        def blocked_seek(target, check):
            calls.append(target)
            if len(calls) == 1:
                started.set()
                try:
                    while not release.wait(.005):
                        check()
                except Cancelled:
                    cancelled.set()
                    raise
            return seek(target, check)

        monkeypatch.setattr(backend._decoder.reader, 'seek', blocked_seek)
        backend.frameChanged.connect(lambda: shown.append(backend.position))
        backend.scrub(.4)
        qtbot.waitUntil(started.is_set)
        if holding_still:
            backend.scrub(.8)  # Last mouse move precedes the new cache commit.
            backend._proxy_busy = True
            backend._proxy_progress_timer.start(10)
            prepared_ready.set()
        else:
            prepared_ready.set()
            backend.scrub(.8)
        qtbot.waitUntil(lambda: cancelled.is_set() and not backend.busy)
        assert calls == [.4]
        assert shown == [.8]
        assert backend.images._live == prepared.image
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(.8)
    finally:
        release.set()
        backend.shutdown()


@pytest.mark.parametrize('detailed', [False, True])
def test_approximate_cache_does_not_interrupt_exact_scrub(qapp, qtbot, tmp_path,
                                                         monkeypatch, detailed):
    from poptools.infrastructure.video_scrub import ScrubCache

    path = make_video(tmp_path / 'precise.mp4')
    backend = VideoPreviewController()
    started, release = threading.Event(), threading.Event()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.beginScrub()
        backend._detailed = detailed
        backend._scrub_cache = ScrubCache(str(path))
        backend._drag_cache = ScrubCache(str(path))
        approximate = Picture(.4, .44, QImage(backend.images._live), approximate=True)
        backend._drag_cache.put(approximate)
        assert backend._drag_cache.contains_memory(.42)
        assert not backend._drag_cache.contains_memory(.42, allow_approximate=False)
        seek = backend._decoder.reader.seek

        def blocked_seek(target, check):
            started.set()
            assert release.wait(2)
            check()
            return seek(target, check)

        monkeypatch.setattr(backend._decoder.reader, 'seek', blocked_seek)
        backend.scrub(.4)
        qtbot.waitUntil(started.is_set)
        request, token = backend._scrub_request, backend._token
        for target in (.405, .41, .42):
            backend._last_scrub_input = (time.monotonic(), 0 if detailed else target)
            backend.scrub(target)
            assert backend._scrub_request is request
            assert backend._token == token
        assert request.target == .42
        release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert not backend.previewApproximate
        assert backend.position == pytest.approx(.4)
    finally:
        release.set()
        backend.shutdown()


@pytest.mark.parametrize('prepared', [True, False])
def test_fast_drag_uses_memory_during_pending_read_only_with_prepared_proxy(
        qapp, qtbot, tmp_path, monkeypatch, prepared):
    path = make_video(tmp_path / 'cached-drag.mp4')
    backend = VideoPreviewController(tmp_path / 'session')
    reading, release, finished = (threading.Event() for _ in range(3))
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.beginScrub()
        backend._proxy_ready = prepared
        image = QImage(32, 18, QImage.Format.Format_RGB888)
        image.fill('blue')
        backend._drag_cache.put(Picture(.8, .84, image))
        read = backend._proxy._read_frame

        def blocked_read(target, tolerance):
            if target == .4:
                reading.set()
                if not release.wait(5):
                    raise TimeoutError('Blocked proxy read was not released')
                finished.set()
                return Picture(.4, .44, image)
            return read(target, tolerance)

        monkeypatch.setattr(backend._proxy, '_read_frame', blocked_read)
        backend.scrub(.4)
        qtbot.waitUntil(reading.is_set)
        backend._last_scrub_input = (time.monotonic(), .4)
        backend.scrub(.8)
        assert not finished.is_set()
        if prepared:
            assert backend.position == pytest.approx(.8)
            assert backend.images._live == image
            assert not backend.busy
        else:
            assert backend.images._live != image
            assert backend.busy and backend._scrub_request.target == .8

        release.set()
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert finished.is_set()
        assert backend.position == pytest.approx(.8)
        assert not backend.previewApproximate
        assert backend.images._live != image
    finally:
        release.set()
        backend.shutdown()


def test_slow_prepared_read_uses_nearby_frame_without_showing_stale_result(
        qapp, qtbot, tmp_path, monkeypatch):
    from poptools.viewmodels import video_preview_controller

    path = make_video(tmp_path / 'slow-prepared-read.mp4')
    backend = VideoPreviewController(tmp_path / 'session')
    reading, release = threading.Event(), threading.Event()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.beginScrub()
        backend._proxy_ready = True
        image = QImage(32, 18, QImage.Format.Format_RGB888)
        image.fill('blue')
        backend._drag_cache.put(Picture(.86, .9, image))
        read = backend._proxy._read_frame

        def blocked_read(target, tolerance):
            if target == .4:
                reading.set()
                if not release.wait(5):
                    raise TimeoutError('Prepared JPEG read was not released')
                return Picture(.4, .44, image)
            return read(target, tolerance)

        monkeypatch.setattr(backend._proxy, '_read_frame', blocked_read)
        backend.scrub(.4)
        qtbot.waitUntil(reading.is_set)
        request = backend._scrub_request
        shown = []
        backend.frameChanged.connect(lambda: shown.append(
            (backend.position, backend.previewApproximate)))
        request.sampled_at = 1
        now = [1.02]
        monkeypatch.setattr(video_preview_controller, 'time',
                            SimpleNamespace(monotonic=lambda: now[0]))
        backend._last_scrub_input = (1.01, .4)
        backend.scrub(.8)
        assert not shown

        now[0] = 1.06
        backend._last_scrub_input = (1.05, .4)
        backend.scrub(.8)
        assert backend._scrub_request is request and backend.busy
        assert shown == [(.86, True)]
        assert backend.images._live == image

        release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert all(position != .4 for position, _ in shown)
        assert backend.position == pytest.approx(.8)
        assert not backend.previewApproximate

        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        reference = VideoReader(str(path))
        try:
            assert backend.images._live == reference.seek(.8, lambda: None).image
        finally:
            reference.close()
    finally:
        release.set()
        backend.shutdown()


def test_sequential_scrub_decodes_current_frame_instead_of_repeating_nearby_cache(
        qapp, qtbot, tmp_path):
    path = make_video(tmp_path / 'sequential.mp4')
    backend = VideoPreviewController(tmp_path / 'session')
    shown = []
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.beginScrub()
        backend._proxy = None
        backend.scrub(.4)
        qtbot.waitUntil(lambda: not backend.busy)
        backend.frameChanged.connect(lambda: shown.append(backend.previewApproximate))
        backend._last_scrub_input = (time.monotonic(), 0)
        backend.scrub(.48)
        qtbot.waitUntil(lambda: not backend.busy)
        assert shown and not any(shown)
        assert backend.position == pytest.approx(.48)
    finally:
        backend.shutdown()


def test_hidden_workspace_defers_background_decoding(qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / 'hidden.mp4')
    backend = VideoPreviewController()
    warmed = []
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.setPreviewActive(False)
        monkeypatch.setattr(backend._scrub_cache, 'warm',
                            lambda target, check: warmed.append(target))
        backend.requestThumbnails(.2, .6, 2500)
        backend._warm_scrub_cache()
        qtbot.wait(180)
        assert not warmed
        assert not backend.thumbnailBusy
        backend.setPreviewActive(True)
        qtbot.waitUntil(lambda: bool(warmed) and backend.detailed)
        assert backend._deferred_thumbnails is None
    finally:
        backend.shutdown()


def test_fast_motion_preserves_pixels_and_refines_without_mouse_release(qapp, qtbot, tmp_path,
                                                                       monkeypatch):
    from poptools.infrastructure.video_scrub import ScrubCache

    path = make_video(tmp_path / 'adaptive.mp4', size=(1280, 720))
    backend = VideoPreviewController()
    shown, sampled = [], []
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._stop_preparation()
        backend._scrub_cache = ScrubCache(str(path))
        original = backend._decoder.reader.seek_fast_preview
        def fast(target, check):
            sampled.append(target)
            return original(target, check)
        monkeypatch.setattr(backend._decoder.reader, 'seek_fast_preview', fast)
        backend.frameChanged.connect(lambda: shown.append(
            (backend.position, backend.previewApproximate, QImage(backend.images._live))))
        backend.beginScrub()
        backend.scrub(.2)
        backend.scrub(1.6)
        qtbot.waitUntil(lambda: any(row[1] for row in shown))
        qtbot.waitUntil(lambda: not backend.busy and not backend.previewApproximate)
        assert backend._scrub_active  # Still holding the mouse, now exact.
        assert backend.position == pytest.approx(1.6)
        reference = VideoReader(str(path))
        try:
            for timestamp, _approximate, image in shown:
                assert image == reference.seek(timestamp, lambda: None).image
            assert backend.images._live == reference.seek(1.6, lambda: None).image
        finally:
            reference.close()
        before = len(sampled)
        backend.scrub(1.64)  # Small movement after settling is not fast motion.
        qtbot.waitUntil(lambda: not backend.busy)
        assert len(sampled) == before
        backend._detailed = True
        backend.scrub(.8)  # Frame-zoom mode must retain exact sampling even for a jump.
        qtbot.waitUntil(lambda: not backend.busy)
        assert len(sampled) == before
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(.8)
    finally:
        backend.shutdown()


@pytest.mark.parametrize('action', ['play', 'hide'])
def test_approximate_frame_survives_play_or_visibility_transition(qapp, qtbot, tmp_path, action):
    path = make_video(tmp_path / 'transition.mp4')
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.beginScrub()
        backend._last_scrub_input = (time.monotonic() - .1, .8)
        backend._show(Picture(.72, .76, QImage(backend.images._live), approximate=True))
        backend._scrub_refine_timer.start()
        if action == 'play':
            backend.togglePlayback()
            assert not backend._scrub_refine_timer.isActive()
            qtbot.wait(130)
            assert backend.playing
            assert not backend.previewApproximate
        else:
            backend.setPreviewActive(False)
            assert not backend._scrub_refine_timer.isActive()
            backend.setPreviewActive(True)
            qtbot.waitUntil(lambda: not backend.busy and not backend.previewApproximate)
            assert backend.position == pytest.approx(.8)
    finally:
        backend.shutdown()
