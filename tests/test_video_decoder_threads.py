"""Interactive decode parallelism must preserve exact presentation frames."""
from fractions import Fraction
from types import SimpleNamespace

import av
import psutil
import pytest
from PIL import Image, ImageDraw

from poptools.infrastructure import video_media
from poptools.infrastructure.video_media import Cancelled, PlaybackDecoder, VideoReader


def policy_reader(*, codec="h264", b_frames=False, size=(2560, 1440)):
    reader = VideoReader.__new__(VideoReader)
    reader.stream = SimpleNamespace(
        width=size[0], height=size[1], thread_type="SLICE", start_time=0,
        time_base=Fraction(1, 1000),
        codec_context=SimpleNamespace(name=codec, has_b_frames=b_frames, thread_count=2),
    )
    return reader


def affinity(monkeypatch, count):
    monkeypatch.setattr(video_media.psutil, "Process", lambda: SimpleNamespace(
        cpu_affinity=lambda: list(range(count))))


@pytest.mark.parametrize("cpus,expected,overview_threads", [
    (1, ("SLICE", 2), 0), (2, ("SLICE", 2), 0), (3, ("SLICE", 2), 0),
    (4, ("FRAME", 2), 1), (6, ("FRAME", 3), 1), (8, ("FRAME", 4), 2), (32, ("FRAME", 4), 4),
])
def test_interactive_threads_respect_process_cpu_affinity(
        monkeypatch, cpus, expected, overview_threads):
    reader = policy_reader()
    affinity(monkeypatch, cpus)
    probes = []
    monkeypatch.setattr(PlaybackDecoder, "_has_long_gop",
                        lambda reader, check: probes.append(reader) or True)
    assert PlaybackDecoder._configure_interactive_threads(reader, lambda: None) == overview_threads
    assert (reader.stream.thread_type, reader.stream.codec_context.thread_count) == expected
    assert bool(probes) == (cpus >= 4)


@pytest.mark.parametrize("kwargs", [
    {"codec": "hevc"}, {"b_frames": True}, {"size": (2560, 1438)},
])
def test_ineligible_sources_do_not_probe_or_change_threads(monkeypatch, kwargs):
    reader = policy_reader(**kwargs)

    def unexpected_probe(*args):
        pytest.fail("Ineligible sources must not inspect CPU or packet state")

    monkeypatch.setattr(video_media.psutil, "Process", unexpected_probe)
    monkeypatch.setattr(PlaybackDecoder, "_has_long_gop", unexpected_probe)
    PlaybackDecoder._configure_interactive_threads(reader, lambda: None)
    assert reader.stream.thread_type == "SLICE"
    assert reader.stream.codec_context.thread_count == 2


def test_platform_without_affinity_uses_logical_cpu_budget(monkeypatch):
    reader = policy_reader()
    monkeypatch.setattr(video_media.psutil, "Process", lambda: SimpleNamespace())
    monkeypatch.setattr(video_media.os, "cpu_count", lambda: 6)
    monkeypatch.setattr(PlaybackDecoder, "_has_long_gop", lambda reader, check: True)
    PlaybackDecoder._configure_interactive_threads(reader, lambda: None)
    assert reader.stream.thread_type == "FRAME"
    assert reader.stream.codec_context.thread_count == 3


@pytest.mark.parametrize("error", [psutil.AccessDenied(), OSError(), NotImplementedError()])
def test_unknown_cpu_budget_keeps_conservative_default(monkeypatch, error):
    reader = policy_reader()

    def unavailable():
        raise error

    monkeypatch.setattr(video_media.psutil, "Process", unavailable)
    PlaybackDecoder._configure_interactive_threads(reader, lambda: None)
    assert reader.stream.thread_type == "SLICE"
    assert reader.stream.codec_context.thread_count == 2


def packet(pts, keyframe=False, size=1024):
    return SimpleNamespace(pts=pts, dts=pts, time_base=Fraction(1, 1000),
                           is_keyframe=keyframe, size=size)


def probe_reader(packets, *, error=None, seek_error=False):
    reader = policy_reader()
    consumed, seeks = [], []

    def demux(stream):
        assert stream is reader.stream
        for item in packets:
            consumed.append(item)
            yield item
        if error:
            raise error

    def seek(offset, **kwargs):
        seeks.append(offset)
        if seek_error:
            raise OSError("seek failed")

    reader.container = SimpleNamespace(demux=demux, seek=seek, decode=lambda stream: iter(()))
    return reader, consumed, seeks


@pytest.mark.parametrize("packets,expected,count", [
    ([packet(0, True), packet(1000)], True, 2),
    ([packet(0, True), packet(40, True), packet(1000)], False, 2),
    ([packet(0, True), packet(1000, True)], False, 2),
    ([packet(0, True), packet(40)], False, 2),
    ([packet(0), packet(1000)], False, 2),
    ([packet(None, True), packet(1000)], False, 2),
    ([packet(0, True)] + [packet(1)] * 119 + [packet(1000)], False, 120),
    ([packet(0, True, 8 * 1024 * 1024), packet(1000)], False, 2),
])
def test_gop_probe_requires_bounded_evidence_and_rewinds(packets, expected, count):
    reader, consumed, seeks = probe_reader(packets)
    assert PlaybackDecoder._has_long_gop(reader, lambda: None) is expected
    assert len(consumed) == count
    assert seeks == [0]
    assert reader._pending is reader._cursor_frame is None
    assert not reader._fast_cursor


def test_forward_reuse_stops_at_the_next_verified_keyframe():
    reader, consumed, _ = probe_reader(
        [packet(0, True), packet(1000), packet(2000), packet(3000, True), packet(4000)])
    assert PlaybackDecoder._has_long_gop(reader, lambda: None)
    assert len(consumed) == 4
    reader.timestamp = lambda frame: frame
    reader._cursor_frame = 1.5
    assert reader._can_reuse_forward(2.9)
    assert not reader._can_reuse_forward(3.0)
    assert not reader._can_reuse_forward(.5)


def test_unordered_lookahead_disables_reuse_without_disabling_threading():
    reader, _, _ = probe_reader([packet(0, True), packet(1000), packet(800, True)])
    assert PlaybackDecoder._has_long_gop(reader, lambda: None)
    assert reader._first_gop is None


@pytest.mark.parametrize("seek_error", [False, True])
def test_probe_errors_keep_default_threads_and_reset_cursor(monkeypatch, seek_error):
    reader, _, seeks = probe_reader([packet(0, True)], error=OSError("bad packet"),
                                    seek_error=seek_error)
    affinity(monkeypatch, 8)
    PlaybackDecoder._configure_interactive_threads(reader, lambda: None)
    assert reader.stream.thread_type == "SLICE"
    assert reader.stream.codec_context.thread_count == 2
    assert reader._pending is reader._cursor_frame is None
    assert seeks == [0]


def test_probe_cancellation_rewinds_and_remains_cancellable():
    reader, consumed, seeks = probe_reader([packet(0, True), packet(1000)])

    def cancel():
        raise Cancelled()

    with pytest.raises(Cancelled):
        PlaybackDecoder._has_long_gop(reader, cancel)
    assert consumed == []
    assert seeks == [0]
    assert reader._pending is reader._cursor_frame is None


def make_clip(path, *, size=(2560, 1440), gop=125, b_frames=0):
    timestamps = [0, 40, 80, 160, 320, 600, 800, 1000, 1200, 1440]
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=25)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)
        stream.codec_context.max_b_frames = b_frames
        stream.codec_context.gop_size = gop
        stream.codec_context.thread_count = 2
        stream.codec_context.options = {"preset": "ultrafast",
                                        "x264-params": "b-adapt=0:scenecut=0"}
        for index, timestamp in enumerate(timestamps):
            image = Image.new("RGB", size, (20 + index * 20, 40, 90))
            draw = ImageDraw.Draw(image)
            draw.rectangle((index * 20, 10, index * 20 + 60, 70), fill="white")
            draw.text((100, 100), f"Frame {index}", fill="yellow")
            frame = av.VideoFrame.from_image(image)
            frame.pts, frame.time_base = timestamp, Fraction(1, 1000)
            for encoded in stream.encode(frame):
                output.mux(encoded)
        for encoded in stream.encode():
            output.mux(encoded)
    return path


def same_picture(actual, expected):
    assert actual.time == pytest.approx(expected.time)
    assert actual.end == pytest.approx(expected.end)
    assert actual.image == expected.image


def test_indexed_filmstrip_extends_ordered_gop_with_exact_thumbnails(tmp_path, monkeypatch):
    path = make_clip(tmp_path / "indexed.mp4", size=(320, 180), gop=9)
    baseline = video_media.filmstrip(str(path), 0, 1.46, 100, lambda: None)
    # Simulate finding only the first second within the compressed scan budget.
    monkeypatch.setattr(PlaybackDecoder, "_first_gop_end", lambda _, end, *args: end)
    initialized = []
    original = VideoReader._can_reuse_forward

    def can_reuse(reader, target):
        initialized.append(reader._first_gop)
        return original(reader, target)

    monkeypatch.setattr(VideoReader, "_can_reuse_forward", can_reuse)
    optimized = video_media.filmstrip(str(path), 0, 1.46, 100, lambda: None, reuse_gop=True)
    assert initialized and all(interval == pytest.approx((0, 1.44)) for interval in initialized)
    assert optimized == baseline


def test_large_long_gop_parallel_decode_preserves_first_seek_next_and_previous(
    tmp_path, monkeypatch
):
    path = make_clip(tmp_path / "large-long-gop.mp4")
    affinity(monkeypatch, 8)
    reference = VideoReader(str(path))
    decoder = PlaybackDecoder()
    seek = VideoReader.seek

    def first_seek(reader, *args, **kwargs):
        assert not reader.stream.codec_context.is_open
        assert reader.stream.thread_type.name == "FRAME"
        assert reader.stream.codec_context.thread_count == 4
        return seek(reader, *args, **kwargs)

    try:
        assert reference.stream.thread_type.name == "SLICE"
        assert reference.stream.codec_context.thread_count == 2
        assert not reference.stream.codec_context.has_b_frames
        with monkeypatch.context() as opening:
            opening.setattr(VideoReader, "seek", first_seek)
            _, picture = decoder.open(str(path), 0, lambda: None)
        same_picture(picture, reference.seek(0, lambda: None))
        assert picture.time == 0  # Packet probing must not consume the first frame.
        assert not decoder.reader.can_seek_exact_forward(1.201)
        fast = decoder.reader.seek_fast_preview(1.201, lambda: None)
        same_picture(fast, reference.seek(1.201, lambda: None))
        assert not fast.approximate
        for output_height in (0, 720):
            reference.output_height = decoder.reader.output_height = output_height
            for target in (1.201, .161, .801):
                actual = decoder.reader.seek(target, lambda: None)
                expected = reference.seek(target, lambda: None)
                same_picture(actual, expected)
                assert actual.time <= target < actual.end
                same_picture(decoder.reader.next(lambda: None), reference.next(lambda: None))
                same_picture(decoder.reader.previous(actual.time, lambda: None),
                             reference.previous(expected.time, lambda: None))
    finally:
        decoder.close()
        reference.close()


@pytest.mark.parametrize("b_frames", [0, 2])
def test_backward_scrub_and_release_reuse_exact_recent_source_frames(
    qapp, qtbot, tmp_path, monkeypatch, b_frames
):
    from poptools.viewmodels.video_preview_controller import VideoPreviewController

    path = make_clip(tmp_path / "backward-release.mp4", b_frames=b_frames)
    affinity(monkeypatch, 8)
    budget = 20 * 1024**2
    available = (48 if b_frames else 16) * budget
    monkeypatch.setattr(video_media.psutil, "virtual_memory",
                        lambda: SimpleNamespace(available=available))
    backend = VideoPreviewController()
    reference = VideoReader(str(path))
    target = .62
    drag_target = .82
    try:
        expected = reference.seek(target, lambda: None)
        expected_drag = reference.seek(drag_target, lambda: None)
        backend.setPreviewActive(False)
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend._info["seek_history_bytes"] == budget
        reader = backend._decoder.reader
        backend.beginScrub()
        backend.scrub(1.05)
        qtbot.waitUntil(lambda: not backend.busy and backend.position == pytest.approx(1.0))
        assert 0 < reader._seek_history_bytes <= budget

        def unexpected_seek(*args, **kwargs):
            pytest.fail("A recent exact source frame must not decode from the keyframe again")

        monkeypatch.setattr(reader, "seek_raw", unexpected_seek)
        backend.scrub(drag_target)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == expected_drag.time
        assert backend.images._live == expected_drag.image
        assert not backend.previewApproximate
        assert reader._seek_history_bytes > 0

        backend.endScrub(target)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == expected.time
        assert backend.images._live == expected.image
        assert not backend.previewApproximate
        assert reader._seek_history_bytes == 0 and not reader._seek_history
    finally:
        backend.shutdown()
        reference.close()


def test_cancelled_long_gop_fast_seek_can_continue_forward_without_restarting(
    tmp_path, monkeypatch,
):
    path = make_clip(tmp_path / "cancelled-scrub.mp4")
    affinity(monkeypatch, 8)
    decoder = PlaybackDecoder()
    reference = VideoReader(str(path))
    normal_check = lambda: None
    try:
        decoder.open(str(path), 0, normal_check)
        reader = decoder.reader
        reader.seek(1.201, normal_check)

        def cancel_after_progress():
            if (reader._fast_cursor and reader._cursor_frame is not None
                    and reader.timestamp(reader._cursor_frame) >= .16):
                raise Cancelled()

        with pytest.raises(Cancelled):
            reader.seek_fast_preview(.82, cancel_after_progress)
        assert reader._fast_cursor and reader._cursor_frame is not None
        assert reader.stream.codec_context.skip_frame == "DEFAULT"

        def unexpected_rewind(*args, **kwargs):
            pytest.fail("A forward fast seek must continue from the filtered cursor")

        with monkeypatch.context() as continuing:
            continuing.setattr(reader, "container", SimpleNamespace(seek=unexpected_rewind))
            sampled = reader.seek_fast_preview(.82, normal_check)
        expected = reference.seek(sampled.time, normal_check)
        assert sampled.approximate and sampled.image == expected.image

        exact = reader.seek(.33, normal_check)
        same_picture(exact, reference.seek(.33, normal_check))
        assert not exact.approximate and not reader._fast_cursor
        same_picture(reader.next(normal_check), reference.next(normal_check))
    finally:
        decoder.close()
        reference.close()


@pytest.mark.parametrize("filtered", [False, True])
def test_long_gop_scan_can_deliver_a_decoded_frame_for_the_latest_pointer(
    tmp_path, monkeypatch, filtered,
):
    from poptools.infrastructure.video_scrub import ScrubRequest

    path = make_clip(tmp_path / "moving-pointer.mp4")
    affinity(monkeypatch, 8)
    decoder = PlaybackDecoder()
    reference = VideoReader(str(path))
    check = lambda: None
    original = 1.05 if filtered else 1.201
    request = ScrubRequest(original)
    request.sampled_at -= .1
    request.update(.82)
    try:
        decoder.open(str(path), 0, check)
        reader = decoder.reader
        if filtered:
            reader.seek(1.201, check)  # Force a cold filtered seek back from this cursor.
        picture = reader.seek_for_scrub(original, check, sample=filtered, history_bytes=0,
                                       keep_history=lambda: False,
                                       retarget=request.retarget_from_frame)
        assert request.sampled_target == .82 and request.retargeted_at is not None
        assert picture.time == pytest.approx(.8)
        assert picture.approximate is filtered
        assert picture.image == reference.seek(.82, check).image
        same_picture(reader.seek(original, check), reference.seek(original, check))
        same_picture(reader.next(check), reference.next(check))
    finally:
        decoder.close()
        reference.close()


@pytest.mark.parametrize("kwargs", [
    {"gop": 1}, {"gop": 2}, {"b_frames": 2}, {"size": (320, 180)},
], ids=["all-intra", "short-gop", "b-frames", "small"])
def test_real_ineligible_clips_keep_slice_and_first_frame(tmp_path, monkeypatch, kwargs):
    path = make_clip(tmp_path / "control.mp4", **kwargs)
    affinity(monkeypatch, 8)
    reference = VideoReader(str(path))
    decoder = PlaybackDecoder()
    try:
        _, picture = decoder.open(str(path), 0, lambda: None)
        assert decoder.reader.stream.thread_type.name == "SLICE"
        assert decoder.reader.stream.codec_context.thread_count == 2
        if kwargs.get("b_frames"):
            assert decoder.reader.stream.codec_context.has_b_frames
        same_picture(picture, reference.seek(0, lambda: None))
        assert picture.time == 0
    finally:
        decoder.close()
        reference.close()
