"""Background preparation starts only after sustained, measured slow scrubbing."""
import threading
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage

from poptools.infrastructure import video_scrub
from poptools.infrastructure.video_media import Cancelled, Picture
from poptools.infrastructure.video_scrub import ScrubCache, ScrubRequest
from poptools.viewmodels import video_preview_controller
from poptools.viewmodels.video_preview_controller import VideoPreviewController


class BlockingProxy:
    on_demand = False
    output_height = 720

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()
        self.build_calls = 0
        self.warm_calls = 0

    def get(self, target):
        return None

    def contains_memory(self, target):
        return False

    def get_nearest(self, target, tolerance=.12):
        return self.get(target)

    def contains_near_memory(self, target, tolerance=.12):
        return False

    def prepare_overview(self, check, spacing=.18, *, frame_threads=1, publish=None,
                         run_event=None):
        check()

    def build(self, check):
        self.build_calls += 1
        self.started.set()
        try:
            while not self.release.wait(.005):
                check()
            check()
            return True
        except Cancelled:
            self.cancelled.set()
            raise

    def warm(self, target, check):
        self.warm_calls += 1
        return self.build(check)


class FakeReader:
    output_height = 0

    def __init__(self, backend):
        self.backend = backend
        self.slow_next = False
        self.observed_delay = .1
        self.sequential = False
        self.hold_next = False
        self.source_started = threading.Event()
        self.source_release = threading.Event()
        self.source_cancelled = threading.Event()
        self.seeks = 0
        self.image = QImage(16, 9, QImage.Format.Format_RGB888)
        self.image.fill("blue")

    def picture(self, target):
        return Picture(target, target + .04, self.image)

    def can_seek_exact_forward(self, target):
        return self.sequential

    def seek(self, target, check):
        check()
        self.seeks += 1
        if self.hold_next:
            self.hold_next = False
            self.source_started.set()
            try:
                while not self.source_release.wait(.005):
                    check()
                check()
            except Cancelled:
                self.source_cancelled.set()
                raise
        # Inject an observed source-job duration without expensive media decoding
        # or sleeps on the worker. The controller still classifies the real result.
        if self.slow_next and self.backend._scrub_request is not None:
            self.backend._scrub_request.sampled_at -= self.observed_delay
            self.slow_next = False
        return self.picture(target)

    def seek_fast_preview(self, target, check):
        return self.seek(target, check)

    def next_for_time(self, target, check):
        check()
        return self.picture(target)

    def close(self):
        pass


@pytest.fixture
def preview(qapp, tmp_path, monkeypatch):
    backend = VideoPreviewController()
    info = {"duration": 10.0, "width": 1280, "height": 720, "fps": 25.0, "audio": False}
    backend._info = dict(info)
    backend._playlist = [{"path": str(tmp_path / name), "name": name, "position": 0}
                         for name in ("first.mp4", "second.mp4")]
    backend._index = 0
    reader = FakeReader(backend)
    backend._decoder.reader = reader
    monkeypatch.setattr(backend._decoder, "open",
                        lambda path, target, check: (dict(info), reader.picture(target)))
    proxy = BlockingProxy()
    backend._proxy = proxy
    try:
        yield backend, proxy, reader
    finally:
        backend.shutdown()


def source_result(backend, qtbot, target):
    backend.scrub(target)
    qtbot.waitUntil(lambda: not backend.busy)
    assert not backend.message


@pytest.fixture
def scrub_clock(monkeypatch):
    now = [100.0]
    clock = SimpleNamespace(monotonic=lambda: now[0])
    monkeypatch.setattr(video_preview_controller, "time", clock)
    monkeypatch.setattr(video_scrub, "time", clock)
    return now


def test_slow_source_defers_one_prepare_job_and_continuous_input_does_not_restart_it(
        preview, qtbot):
    backend, proxy, reader = preview
    backend.beginScrub()
    reader.slow_next = True
    source_result(backend, qtbot, .2)
    assert backend._scrub_source_slow
    assert backend._scrub_prepare_timer.isActive()
    source_result(backend, qtbot, .4)
    assert backend._scrub_prepare_timer.isActive()
    assert backend._scrub_prepare_timer.interval() == 350
    qtbot.wait(150)
    assert not proxy.started.is_set()
    source_result(backend, qtbot, .6)
    assert 0 < backend._scrub_prepare_timer.remainingTime() < 250
    qtbot.waitUntil(proxy.started.is_set, timeout=1000)
    token = backend._proxy_token
    for index in range(20):
        source_result(backend, qtbot, .8 + index * .04)
        backend._ensure_proxy_preparation()
        assert backend._proxy_token == token
    assert proxy.build_calls == 1
    assert not proxy.cancelled.is_set()
    assert backend.previewOptimizing
    proxy.release.set()
    qtbot.waitUntil(lambda: not backend.previewOptimizing)
    assert backend.previewReady
    backend._ensure_proxy_preparation()
    assert proxy.build_calls == 1


@pytest.mark.parametrize("boundary", ["release", "seek", "play", "hide", "resolution",
                                       "switch", "pause", "shutdown"])
def test_foreground_boundaries_cancel_preparation_and_reject_late_results(preview, qtbot, boundary):
    backend, proxy, reader = preview
    backend.beginScrub()
    backend._scrub_source_slow = True
    backend._prepare_scrub_proxy()
    qtbot.waitUntil(proxy.started.is_set)
    old_token = backend._proxy_token
    actions = {
        "release": lambda: backend.endScrub(.4),
        "seek": lambda: backend.seek(.4),
        "play": backend.togglePlayback,
        "hide": lambda: backend.setPreviewActive(False),
        "resolution": lambda: backend.setResolution(720),
        "switch": lambda: backend.selectVideo(1),
        "pause": backend.pause,
        "shutdown": backend.shutdown,
    }
    actions[boundary]()
    qtbot.waitUntil(proxy.cancelled.is_set)
    assert backend._proxy_token != old_token
    assert not backend._scrub_prepare_timer.isActive()
    assert not backend.previewOptimizing
    state = (backend.previewOptimizing, backend.previewReady, backend._proxy_exhausted)
    backend._proxy_finished(old_token, True)
    backend._proxy_failed(old_token, "obsolete result")
    assert (backend.previewOptimizing, backend.previewReady, backend._proxy_exhausted) == state
    assert proxy.build_calls == 1


@pytest.mark.parametrize("ineligible", ["long", "detailed", "hidden", "ready", "exhausted"])
def test_progressive_prepare_skips_ineligible_scrubbing_modes(preview, qtbot, ineligible):
    backend, proxy, reader = preview
    if ineligible == "long":
        backend._info["duration"] = 3600
        proxy.on_demand = True
    elif ineligible == "detailed":
        backend._detailed = True
    elif ineligible == "hidden":
        backend.setPreviewActive(False)
    elif ineligible == "ready":
        backend._proxy_ready = True
    else:
        backend._proxy_exhausted = True
    backend.beginScrub()
    reader.slow_next = True
    source_result(backend, qtbot, .2)
    source_result(backend, qtbot, .4)
    backend._prepare_scrub_proxy()
    qtbot.wait(400)
    assert proxy.build_calls == proxy.warm_calls == 0
    assert not backend.previewOptimizing


def test_fast_continuous_source_does_not_start_background_preparation(preview, qtbot, scrub_clock):
    backend, proxy, reader = preview
    backend.beginScrub()
    for index in range(20):
        source_result(backend, qtbot, .2 + index * .04)
        assert not backend._scrub_source_slow
        scrub_clock[0] += .02
        qtbot.wait(20)
    qtbot.wait(400)
    assert reader.seeks == 20
    assert proxy.build_calls == 0
    assert not backend.previewOptimizing


def test_slow_sequential_source_does_not_start_background_preparation(preview, qtbot):
    backend, proxy, reader = preview
    reader.sequential = True
    reader.observed_delay = .5
    backend.beginScrub()
    for index in range(20):
        reader.slow_next = True
        source_result(backend, qtbot, .2 + index * .04)
        assert not backend._scrub_source_slow
        assert not backend._scrub_prepare_timer.isActive()
        qtbot.wait(20)
    assert reader.seeks == 20
    assert proxy.build_calls == 0
    assert not backend.previewOptimizing


def test_new_gesture_clears_previous_slow_source_feedback(preview, qtbot):
    backend, proxy, reader = preview
    backend.beginScrub()
    reader.slow_next = True
    source_result(backend, qtbot, .2)
    assert backend._scrub_source_slow
    backend.endScrub(.2)
    qtbot.waitUntil(lambda: not backend.busy)
    backend.beginScrub()
    assert not backend._scrub_source_slow
    source_result(backend, qtbot, .4)
    backend._prepare_scrub_proxy()
    qtbot.wait(400)
    assert proxy.build_calls == 0


@pytest.mark.parametrize("expensive", [False, True])
def test_cold_random_seek_starts_preparation_before_source_result_arrives(
        preview, qtbot, expensive):
    backend, proxy, reader = preview
    backend.beginScrub()
    if expensive:
        backend._info["expensive_random_seek"] = True
        backend._last_scrub_input = (video_preview_controller.time.monotonic() - .02, 0.0)
    reader.hold_next = True
    backend.scrub(.2)
    qtbot.waitUntil(reader.source_started.is_set)
    qtbot.waitUntil(backend._scrub_prepare_timer.isActive)
    assert backend.busy and not backend._scrub_source_slow
    assert backend._scrub_prepare_timer.interval() == (120 if expensive else 350)
    if not expensive:
        qtbot.wait(200)
        assert not proxy.started.is_set()
    qtbot.waitUntil(proxy.started.is_set, timeout=1000)
    assert backend.busy and backend._scrub_source_slow
    assert not reader.source_release.is_set()
    assert reader.seeks == proxy.build_calls == 1
    token = backend._proxy_token
    for target in (.4, .6, .8):
        backend.scrub(target)
    backend._schedule_scrub_preparation(backend._scrub_request)
    assert backend._proxy_token == token and proxy.build_calls == 1


@pytest.mark.parametrize("cancel", ["release", "exact_seek", "hide", "new_gesture"])
def test_cancelled_cold_seek_and_delayed_start_signal_cannot_prepare(preview, qtbot, cancel):
    backend, proxy, reader = preview
    backend.beginScrub()
    reader.hold_next = True
    backend.scrub(.2)
    qtbot.waitUntil(reader.source_started.is_set)
    qtbot.waitUntil(backend._scrub_prepare_timer.isActive)
    old_request = backend._scrub_request
    if cancel == "release":
        backend.endScrub(.4)
    elif cancel == "exact_seek":
        backend.seek(.4)
    elif cancel == "hide":
        backend.setPreviewActive(False)
    else:
        backend.pause()
        backend.beginScrub()
    assert not backend._scrub_prepare_timer.isActive()
    reader.source_release.set()
    qtbot.waitUntil(lambda: not backend.busy)
    # Idle preparation after a release is valid and has its own timer. Isolate
    # the cancelled drag timer and a queued signal from its obsolete request.
    backend._cache_timer.stop()
    backend._coldScrubStarted.emit(old_request)
    assert not backend._scrub_prepare_timer.isActive()
    qtbot.wait(400)
    assert proxy.build_calls == 0
    assert not backend.previewOptimizing


def test_blocked_sequential_seek_never_schedules_cold_preparation(preview, qtbot):
    backend, proxy, reader = preview
    reader.sequential = True
    reader.hold_next = True
    backend.beginScrub()
    backend.scrub(.2)
    qtbot.waitUntil(reader.source_started.is_set)
    assert not backend._scrub_request.random_access
    qtbot.wait(400)
    assert backend.busy
    assert not backend._scrub_prepare_timer.isActive()
    assert proxy.build_calls == 0
    reader.source_release.set()
    qtbot.waitUntil(lambda: not backend.busy)
    assert not backend._scrub_source_slow
    assert not backend._scrub_prepare_timer.isActive()


@pytest.mark.parametrize("elapsed,from_source,random_access,expected", [
    (.059, True, True, False), (.060, True, True, True), (.061, True, True, True),
    (.5, False, True, False), (.5, True, False, False),
])
def test_only_random_source_jobs_at_least_60ms_enable_progressive_preparation(
        preview, monkeypatch, elapsed, from_source, random_access, expected):
    backend, proxy, reader = preview
    backend.beginScrub()
    request = ScrubRequest(.2)
    request.sampled_at = 0
    request.from_source = from_source
    request.random_access = random_access
    backend._scrub_request = request
    backend._kind = "seek"
    backend._busy = True
    # Replace only the controller module's clock, not the process-wide time
    # module or Qt timers. Deliver a deterministic completed source/cache job.
    monkeypatch.setattr(video_preview_controller, "time",
                        SimpleNamespace(monotonic=lambda: elapsed))
    backend._received(backend._token, reader.picture(.2))
    assert backend._scrub_source_slow is expected
    assert proxy.build_calls == 0


def test_slow_cached_reads_finish_while_new_targets_keep_arriving(
        preview, qtbot, monkeypatch, scrub_clock):
    backend, proxy, reader = preview
    started = [threading.Event() for _ in range(3)]
    released = [threading.Event() for _ in range(3)]
    calls, shown = [], []

    def cached(target):
        index = len(calls)
        calls.append(target)
        if index < len(started):
            started[index].set()
            assert released[index].wait(2)
        return reader.picture(target)

    monkeypatch.setattr(proxy, "get", cached)
    monkeypatch.setattr(proxy, "contains_memory", lambda target: True)
    backend.frameChanged.connect(lambda: shown.append(backend.position))
    backend.beginScrub()
    backend.scrub(.2)
    try:
        for wave in range(3):
            qtbot.waitUntil(started[wave].is_set)
            request, token = backend._scrub_request, backend._token
            assert not request.from_source
            for offset in (.02, .04, .06):
                backend.scrub(.2 + wave * .1 + offset)
                scrub_clock[0] += .008  # Input continues during a 24 ms cache read.
                assert backend._scrub_request is request and backend._token == token
            released[wave].set()
            qtbot.waitUntil(lambda wave=wave: len(shown) > wave)
            assert shown[wave] == pytest.approx(calls[wave])
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(.46)
        assert reader.seeks == 0
        assert calls == pytest.approx([.2, .26, .36, .46])
    finally:
        for event in released:
            event.set()


def test_ready_proxy_target_still_preempts_a_blocked_source(preview, qtbot, monkeypatch):
    backend, proxy, reader = preview
    ready, shown = [False], []
    monkeypatch.setattr(proxy, "contains_memory", lambda target: ready[0])
    monkeypatch.setattr(proxy, "get", lambda target: reader.picture(target) if ready[0] else None)
    backend.frameChanged.connect(lambda: shown.append(backend.position))
    reader.hold_next = True
    backend.beginScrub()
    backend.scrub(.2)
    qtbot.waitUntil(reader.source_started.is_set)
    request, token = backend._scrub_request, backend._token
    assert request.from_source
    ready[0] = True
    backend.scrub(.8)
    assert backend._scrub_request is not request and backend._token != token
    qtbot.waitUntil(reader.source_cancelled.is_set)
    qtbot.waitUntil(lambda: not backend.busy)
    assert shown == pytest.approx([.8])
    assert reader.seeks == 1


@pytest.mark.parametrize("retarget", [False, True])
def test_cold_drag_can_read_partial_proxy_without_cancelling_source(
        preview, qtbot, monkeypatch, scrub_clock, retarget):
    backend, proxy, reader = preview
    backend._info["expensive_random_seek"] = True
    backend._drag_cache = ScrubCache("first.mp4", output_height=720)
    reading, release = threading.Event(), threading.Event()
    shown = []
    monkeypatch.setattr(proxy, "contains_near_memory", lambda target, tolerance: target == .8)

    def cached(target, tolerance):
        assert target == .8
        reading.set()
        assert release.wait(3)
        return reader.picture(target)

    monkeypatch.setattr(proxy, "get_nearest", cached)
    backend.frameChanged.connect(lambda: shown.append(backend.position))
    reader.hold_next = True
    backend.beginScrub()
    backend.scrub(.2)
    try:
        qtbot.waitUntil(reader.source_started.is_set)
        request, token = backend._scrub_request, backend._token
        scrub_clock[0] += .02
        backend.scrub(.8)
        qtbot.waitUntil(reading.is_set)
        if retarget:
            scrub_clock[0] += .02
            backend.scrub(1.6)
        release.set()
        qtbot.waitUntil(lambda: backend._cached_scrub_preview_token == -1)
        if retarget:
            assert not shown
            scrub_clock[0] += .02
            backend.scrub(.8)  # The completed read is now an in-memory hit.
        assert shown == [.8]
        assert backend._scrub_request is request and backend._token == token
        assert backend.busy and not reader.source_cancelled.is_set()

        backend.endScrub(.9)
        qtbot.waitUntil(lambda: not backend.busy)
        assert reader.source_cancelled.is_set()
        assert shown == [.8, .9] and not backend.previewApproximate
    finally:
        release.set()
        reader.source_release.set()


@pytest.mark.parametrize("finish", ["release", "exact_seek"])
def test_exact_target_cancels_pending_cached_result_immediately(
        preview, qtbot, monkeypatch, finish):
    backend, proxy, reader = preview
    started, released = threading.Event(), threading.Event()
    shown = []

    def cached(target):
        if target == .2:
            started.set()
            assert released.wait(2)
        return reader.picture(target)

    monkeypatch.setattr(proxy, "get", cached)
    monkeypatch.setattr(proxy, "contains_memory", lambda target: True)
    backend.frameChanged.connect(lambda: shown.append(backend.position))
    backend.beginScrub()
    backend.scrub(.2)
    try:
        qtbot.waitUntil(started.is_set)
        token = backend._token
        if finish == "release":
            backend.endScrub(.8)
        else:
            backend.seek(.8)
        assert backend._token != token and backend._scrub_request is None
        released.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert shown and all(position == pytest.approx(.8) for position in shown)
    finally:
        released.set()
