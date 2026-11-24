"""Overview cache scheduling without media decoding or rendering benchmarks."""
import threading
import time
from types import SimpleNamespace

import pytest
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Cancelled, Picture
from poptools.infrastructure.video_scrub import ScrubCache
from poptools.viewmodels import video_preview_controller
from poptools.viewmodels.video_preview_controller import VideoPreviewController


class OverviewReader:
    output_height = 0

    def __init__(self):
        self.image = QImage(1280, 720, QImage.Format.Format_RGB888)
        self.image.fill("blue")
        self.targets = []
        self.fast_targets = []
        self.hold_next = False
        self.started = threading.Event()
        self.release = threading.Event()
        self.cancelled = threading.Event()

    def picture(self, target):
        return Picture(target, target + .02, self.image)

    def can_seek_exact_forward(self, target):
        return False

    def seek(self, target, check):
        check()
        self.targets.append(target)
        if self.hold_next:
            self.hold_next = False
            self.started.set()
            try:
                while not self.release.wait(.005):
                    check()
                check()
            except Cancelled:
                self.cancelled.set()
                raise
        return self.picture(target)

    def seek_fast_preview(self, target, check):
        self.fast_targets.append(target)
        return self.seek(target, check)

    def close(self):
        pass


class OverviewProxy:
    on_demand = False
    output_height = 720

    def __init__(self):
        self.image = QImage(1280, 720, QImage.Format.Format_RGB888)
        self.image.fill("green")
        self.exact_available = False
        self.near_available = True
        self.exact_reads = []
        self.near_reads = []
        self.stages = []
        self.overview_end = None
        self.overview_started = threading.Event()
        self.overview_release = threading.Event()
        self.full_started = threading.Event()
        self.full_release = threading.Event()
        self.cancelled = threading.Event()

    def get(self, target):
        self.exact_reads.append(target)
        if self.exact_available:
            return Picture(target, target + .02, self.image)
        return None

    def get_nearest(self, target, tolerance=.12):
        if self.exact_available:
            return Picture(target, target + .02, self.image)
        self.near_reads.append((target, tolerance))
        if self.near_available:
            return Picture(target - .06, target - .04, self.image, approximate=True)
        return None

    def contains_memory(self, target):
        return self.exact_available

    def contains_near_memory(self, target, tolerance=.12):
        return self.near_available

    def _wait(self, released, check):
        try:
            while not released.wait(.005):
                check()
            check()
        except Cancelled:
            self.cancelled.set()
            raise

    def prepare_overview(self, check, spacing=.18, *, frame_threads=1, publish=None,
                         run_event=None):
        self.stages.append("overview")
        self.overview_started.set()
        self._wait(self.overview_release, check)
        return True

    def build(self, check):
        self.stages.append("full")
        self.full_started.set()
        self._wait(self.full_release, check)
        return True

    def warm(self, target, check):
        self.stages.append("warm")
        check()
        return True


@pytest.fixture
def overview(qapp, tmp_path, monkeypatch):
    backend = VideoPreviewController()
    info = {"duration": 10.0, "width": 1280, "height": 720, "fps": 50.0, "audio": False}
    backend._info = dict(info)
    backend._playlist = [{"path": str(tmp_path / name), "name": name, "position": 0}
                         for name in ("first.mp4", "second.mp4")]
    backend._index = 0
    reader, proxy = OverviewReader(), OverviewProxy()
    backend._decoder.reader = reader
    backend._proxy = proxy
    backend._scrub_cache = ScrubCache(backend._playlist[0]["path"])
    backend._drag_cache = ScrubCache(backend._playlist[0]["path"], output_height=720)
    monkeypatch.setattr(backend._decoder, "open",
                        lambda path, target, check: (dict(info), reader.picture(target)))
    # Sampling eligibility has a precise 80 ms boundary. A controller-only clock
    # makes that boundary deterministic without changing pytest/Qt wait clocks.
    now = [time.monotonic()]
    monkeypatch.setattr(video_preview_controller, "time",
                        SimpleNamespace(monotonic=lambda: now[0]))
    try:
        yield backend, proxy, reader, now
    finally:
        reader.release.set()
        proxy.overview_release.set()
        proxy.full_release.set()
        backend.shutdown()


def fast_input(backend, now, target):
    backend._last_scrub_input = (now[0] - .01, target - 1)
    backend.scrub(target)


def test_fast_overview_frames_keep_pixels_and_release_uses_native_exact_frame(overview, qtbot):
    backend, proxy, reader, now = overview
    backend.beginScrub()
    for target in (.2, .6, 1.0):
        fast_input(backend, now, target)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.previewApproximate
        assert backend.position == pytest.approx(target - .06)
        assert backend.images._live == proxy.image
        assert backend.images._live.size() == reader.image.size()
        assert backend._scrub_cache._bytes == 0
        cached = backend._drag_cache.get(target - .06)
        assert cached is not None and cached.approximate
    assert proxy.near_reads == [(.2, .12), (.6, .12), (1.0, .12)]
    assert reader.targets == []
    backend.endScrub(1.0)
    qtbot.waitUntil(lambda: not backend.busy)
    assert len(proxy.near_reads) == 3
    assert reader.targets == [1.0]
    assert not backend.previewApproximate
    assert backend.position == pytest.approx(1.0)
    assert backend.images._live == reader.image


def test_exact_proxy_frame_has_priority_over_near_overview(overview, qtbot):
    backend, proxy, reader, now = overview
    proxy.exact_available = True
    backend.beginScrub()
    fast_input(backend, now, .6)
    qtbot.waitUntil(lambda: not backend.busy)
    assert not backend.previewApproximate
    assert backend.position == pytest.approx(.6)
    assert proxy.near_reads == reader.targets == []


@pytest.mark.parametrize("mode", ["slow", "detailed", "stationary", "release"])
def test_exact_navigation_never_reads_near_overview(overview, qtbot, mode):
    backend, proxy, reader, now = overview
    backend.beginScrub()
    backend._scrub_fast = mode != "slow"
    backend._detailed = mode == "detailed"
    backend._last_scrub_input = (now[0] - (.081 if mode == "stationary" else .01), .8)
    if mode == "release":
        backend.endScrub(.8)
    else:
        backend._seek(.8, fast=True)
    qtbot.waitUntil(lambda: not backend.busy)
    assert proxy.near_reads == reader.fast_targets == []
    assert reader.targets == [.8]
    assert not backend.previewApproximate
    assert backend.position == pytest.approx(.8)


def test_stationary_overview_refines_without_releasing_mouse(overview, qtbot):
    backend, proxy, reader, now = overview
    backend.beginScrub()
    fast_input(backend, now, .8)
    qtbot.waitUntil(lambda: not backend.busy)
    assert backend.previewApproximate
    now[0] += .081
    qtbot.waitUntil(lambda: not backend.busy and not backend.previewApproximate)
    assert backend._scrub_active
    assert backend.position == pytest.approx(.8)
    assert reader.targets == [.8]
    assert proxy.near_reads == [(.8, .12)]


@pytest.mark.parametrize("brief_slowdown", [False, True])
def test_preparation_runs_overview_then_full_once_and_only_full_sets_ready(
        overview, qtbot, brief_slowdown):
    backend, proxy, _reader, now = overview
    backend.beginScrub()
    backend._scrub_fast = not brief_slowdown
    backend._last_fast_scrub_at = now[0] - .04
    backend._last_scrub_input = (now[0], .8)
    backend._ensure_proxy_preparation()
    qtbot.waitUntil(proxy.overview_started.is_set)
    token = backend._proxy_token
    for _ in range(5):
        backend._ensure_proxy_preparation()
    assert backend._proxy_token == token
    assert proxy.stages == ["overview"]
    assert backend.previewOptimizing and not backend.previewReady
    proxy.overview_release.set()
    qtbot.waitUntil(proxy.full_started.is_set)
    assert proxy.stages == ["overview", "full"]
    assert backend.previewOptimizing and not backend.previewReady
    proxy.full_release.set()
    qtbot.waitUntil(lambda: backend.previewReady)
    assert not backend.previewOptimizing


def test_first_frame_is_reused_and_overview_starts_before_idle_timer(overview, qtbot):
    backend, proxy, reader, _now = overview
    backend._cache_timer.setInterval(10000)
    backend._kind = 'open'
    frame = reader.picture(0)
    backend._received(backend._token, ({**backend._info, 'overview_decode_threads': 4}, frame))
    assert backend.images._live == frame.image
    assert backend._scrub_cache.get(0).image == frame.image
    qtbot.waitUntil(proxy.overview_started.is_set)
    assert backend.previewOptimizing and not backend.previewReady


def test_idle_overview_keeps_the_same_job_on_first_drag_and_refines_duration(overview, qtbot):
    backend, proxy, _reader, now = overview
    backend._info["overview_decode_threads"] = 4
    backend._metadata_pending = backend._playlist[0]["path"]
    proxy.overview_end = 10.42
    backend._warm_scrub_cache()
    qtbot.waitUntil(proxy.overview_started.is_set)
    token = backend._proxy_token
    assert backend._metadata_token == -1 and backend._metadata_pending
    assert not backend.previewReady

    backend.beginScrub()
    fast_input(backend, now, .8)
    qtbot.waitUntil(lambda: not backend.busy)
    assert backend._proxy_token == token and not proxy.cancelled.is_set()
    assert backend.previewApproximate and backend.images._live == proxy.image

    proxy.overview_release.set()
    qtbot.waitUntil(proxy.full_started.is_set)
    assert proxy.stages == ["overview", "full"]
    assert backend._metadata_pending is None and backend.duration == pytest.approx(10.42)
    assert not backend.previewReady
    proxy.full_release.set()
    qtbot.waitUntil(lambda: backend.previewReady)


@pytest.mark.parametrize("hide", [False, True], ids=["resume", "cancel-when-hidden"])
def test_release_yields_an_idle_overview_to_exact_seek(overview, qtbot, hide):
    backend, proxy, reader, _now = overview
    backend._info["overview_decode_threads"] = 4
    backend._warm_scrub_cache()
    qtbot.waitUntil(proxy.overview_started.is_set)
    token, run_event = backend._proxy_token, backend._overview_run
    assert run_event.is_set()
    backend.beginScrub()
    reader.hold_next = True
    backend.endScrub(.8)
    qtbot.waitUntil(reader.started.is_set)
    assert backend._proxy_token == token
    assert not run_event.is_set()
    assert proxy.stages == ["overview"]
    if hide:
        backend.setPreviewActive(False)
        qtbot.waitUntil(proxy.cancelled.is_set)
        assert backend._overview_run is None and run_event.is_set()
    else:
        reader.release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend._proxy_token == token and run_event.is_set()
        assert backend.position == pytest.approx(.8)
        assert not backend.previewApproximate


@pytest.mark.parametrize("threads,local", [(4, False), (1, False), (4, True)])
def test_only_sustained_fast_drag_with_spare_threads_prepares_immediately(
        overview, qtbot, threads, local):
    backend, proxy, _reader, now = overview
    backend._info["overview_decode_threads"] = threads
    proxy.on_demand = local
    backend.beginScrub()
    fast_input(backend, now, .8)
    qtbot.waitUntil(lambda: not backend.busy)
    assert not backend.previewOptimizing
    now[0] += .02
    backend.scrub(1.6)
    if threads > 1 and not local:
        qtbot.waitUntil(proxy.overview_started.is_set)
        assert backend.previewOptimizing and proxy.stages == ["overview"]
        assert backend._overview_run.is_set()
    else:
        assert not backend.previewOptimizing


@pytest.mark.parametrize("mode", ["idle", "slow", "detailed", "stationary", "on_demand"])
def test_non_fast_preparation_skips_overview_stage(overview, qtbot, mode):
    backend, proxy, _reader, now = overview
    if mode != "idle":
        backend.beginScrub()
    backend._scrub_fast = mode != "slow"
    backend._detailed = mode == "detailed"
    backend._last_scrub_input = (now[0] - (.081 if mode == "stationary" else .01), .8)
    proxy.on_demand = mode == "on_demand"
    proxy.full_release.set()
    backend._ensure_proxy_preparation()
    qtbot.waitUntil(lambda: not backend.previewOptimizing)
    assert proxy.stages == (["warm"] if proxy.on_demand else ["full"])
    assert backend.previewReady == (not proxy.on_demand)


@pytest.mark.parametrize("boundary", ["release", "hide", "switch", "resolution", "shutdown"])
def test_cancelled_overview_cannot_continue_full_or_publish_ready(overview, qtbot, boundary):
    backend, proxy, _reader, now = overview
    backend.beginScrub()
    backend._scrub_fast = True
    backend._last_scrub_input = (now[0], .8)
    backend._ensure_proxy_preparation()
    qtbot.waitUntil(proxy.overview_started.is_set)
    token = backend._proxy_token
    actions = {
        "release": lambda: backend.endScrub(.8),
        "hide": lambda: backend.setPreviewActive(False),
        "switch": lambda: backend.selectVideo(1),
        "resolution": lambda: backend.setResolution(720),
        "shutdown": backend.shutdown,
    }
    actions[boundary]()
    qtbot.waitUntil(proxy.cancelled.is_set)
    assert proxy.stages == ["overview"]
    assert backend._proxy_token != token
    assert not backend.previewOptimizing
    state = (backend.previewReady, backend._proxy_exhausted, backend.frameSource)
    backend._proxy_finished(token, True)
    backend._proxy_failed(token, "obsolete overview")
    assert (backend.previewReady, backend._proxy_exhausted, backend.frameSource) == state


@pytest.mark.parametrize("trigger,mode", [
    ("input", "fast"), ("input", "slow"), ("input", "detailed"),
    ("poll", "fast"), ("poll", "slow"), ("poll", "detailed"), ("poll", "stationary"),
])
def test_near_ready_preempts_source_only_while_fast_input_is_current(
        overview, qtbot, trigger, mode):
    backend, proxy, reader, now = overview
    proxy.near_available = False
    reader.hold_next = True
    backend.beginScrub()
    backend.scrub(.2)
    qtbot.waitUntil(reader.started.is_set)
    request, token = backend._scrub_request, backend._token
    proxy.near_available = True
    backend._detailed = mode == "detailed"
    if trigger == "input":
        backend._last_scrub_input = (now[0] - .01, .8 if mode == "slow" else 0)
        backend.scrub(.8)
    else:
        request.update(.8)
        backend._scrub_fast = mode != "slow"
        backend._last_scrub_input = (now[0] - (.081 if mode == "stationary" else .01), .8)
        backend._use_prepared_scrub()
    if mode == "fast":
        assert backend._token != token and backend._scrub_request is not request
        qtbot.waitUntil(reader.cancelled.is_set)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.previewApproximate
        assert backend.position == pytest.approx(.74)
        assert reader.targets == [.2]
    else:
        assert backend._token == token and backend._scrub_request is request
        assert not reader.cancelled.is_set()
        reader.release.set()
        qtbot.waitUntil(lambda: not backend.busy)
        assert proxy.near_reads == []
        assert not backend.previewApproximate
        assert backend.position == pytest.approx(.8)
