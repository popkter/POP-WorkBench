"""Tail-duration decoding yields to foreground interactions and hidden views."""
import threading
import time

import pytest

from poptools.infrastructure.video_media import VideoReader
from poptools.infrastructure.video_scrub import ScrubCache
from poptools.viewmodels.video_preview_controller import VideoPreviewController
from test_video_preview import make_video


@pytest.mark.parametrize("interaction", ["scrub", "hide", "play"])
def test_interaction_cancels_duration_probe_and_idle_retries(
        qapp, qtbot, tmp_path, monkeypatch, interaction):
    path = make_video(tmp_path / "duration.mp4")
    started, cancelled, release = threading.Event(), threading.Event(), threading.Event()
    attempts = []

    def probe(reader, check):
        attempts.append(None)
        started.set()
        try:
            while not release.is_set():
                check()
                time.sleep(.005)
            check()
        finally:
            cancelled.set()

    monkeypatch.setattr(VideoReader, "probe_end", probe)
    monkeypatch.setattr(ScrubCache, "warm", lambda *args: None)
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(started.is_set)
        if interaction == "scrub":
            backend.beginScrub()
        elif interaction == "hide":
            backend.setPreviewActive(False)
        else:
            backend.togglePlayback()
        qtbot.waitUntil(cancelled.is_set)
        assert backend._metadata_token == -1
        assert backend._metadata_pending == str(path)
        qtbot.wait(200)
        assert len(attempts) == 1

        release.set()
        if interaction == "scrub":
            backend.endScrub(.4)
        elif interaction == "hide":
            backend.setPreviewActive(True)
        else:
            backend.pause()
        qtbot.waitUntil(lambda: backend._metadata_pending is None)
        assert len(attempts) == 2
        assert backend._metadata_token == -1
    finally:
        release.set()
        backend.shutdown()


def test_open_finishing_while_hidden_defers_probe_and_cache(
        qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / "hidden-open.mp4")
    started, release = threading.Event(), threading.Event()
    probes, warmed = [], []
    backend = VideoPreviewController()
    open_video = backend._decoder.open

    def slow_open(*args):
        started.set()
        assert release.wait(3)
        return open_video(*args)

    monkeypatch.setattr(backend._decoder, "open", slow_open)
    monkeypatch.setattr(VideoReader, "probe_end", lambda *args: probes.append(None))
    monkeypatch.setattr(ScrubCache, "warm", lambda *args: warmed.append(None))
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(started.is_set)
        backend.setPreviewActive(False)
        release.set()
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        qtbot.wait(250)
        assert not probes and not warmed
        assert backend._metadata_pending == str(path)
        assert backend._metadata_token == -1
        backend.setPreviewActive(True)
        qtbot.waitUntil(lambda: bool(probes) and bool(warmed))
    finally:
        release.set()
        backend.shutdown()


def test_switching_video_discards_cancelled_duration_result(
        qapp, qtbot, tmp_path, monkeypatch):
    first = make_video(tmp_path / "first.mp4")
    second = make_video(tmp_path / "second.mp4")
    started, release = threading.Event(), threading.Event()
    attempts = []

    def probe(reader, check):
        attempts.append(reader.container.name)
        if len(attempts) == 1:
            started.set()
            assert release.wait(3)
            reader.duration = 999  # A completion already overtaken by selection.

    monkeypatch.setattr(VideoReader, "probe_end", probe)
    monkeypatch.setattr(ScrubCache, "warm", lambda *args: None)
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(first), str(second)])
        qtbot.waitUntil(started.is_set)
        backend.selectVideo(1)
        release.set()
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy
                        and backend._metadata_pending is None)
        assert attempts == [str(first), str(second)]
        assert backend.duration < 999
    finally:
        release.set()
        backend.shutdown()


def test_bad_tail_stops_retrying_and_allows_cache_preparation(
        qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / "bad-tail.mp4")
    attempts, warmed = [], []

    def probe(reader, check):
        attempts.append(None)
        raise ValueError("Cannot decode final GOP")

    monkeypatch.setattr(VideoReader, "probe_end", probe)
    monkeypatch.setattr(ScrubCache, "warm", lambda *args: warmed.append(None))
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: bool(warmed))
        assert backend.loaded and not backend.busy
        assert backend._metadata_pending is None and backend._metadata_token == -1
        backend._warm_scrub_cache()
        qtbot.wait(200)
        assert len(attempts) == 1
    finally:
        backend.shutdown()


def test_deferred_probe_still_recovers_underreported_vfr_end(
        qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / "vfr.mp4", pts=[0, 40, 80, 400, 800])
    reference = VideoReader(str(path))
    try:
        reference.probe_end(lambda: None)
        expected = reference.duration
    finally:
        reference.close()
    original_init = VideoReader.__init__

    def underreported(reader, *args):
        original_init(reader, *args)
        reader.duration = .12

    monkeypatch.setattr(VideoReader, "__init__", underreported)
    monkeypatch.setattr(ScrubCache, "warm", lambda *args: None)
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend.duration == pytest.approx(.12)
        qtbot.waitUntil(lambda: backend._metadata_pending is None)
        assert backend.duration == pytest.approx(expected)
        backend.seek(backend.duration)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(.8)
    finally:
        backend.shutdown()
