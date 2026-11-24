"""Fast scrubbing may sample time, but must retain source pixels and exact seeking."""
from fractions import Fraction
from types import SimpleNamespace

import av
import pytest
from PIL import Image, ImageDraw
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import (
    SCRUB_PREVIEW_TOLERANCE,
    Cancelled,
    Picture,
    VideoReader,
)


@pytest.fixture(params=[
    list(range(0, 1200, 40)),
    [0, 40, 80, 160, 200, 320, 360, 400, 560, 600, 960, 1000],
], ids=["b-frames", "vfr"])
def source_frames(tmp_path, request):
    path = tmp_path / "fast-preview.mp4"
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=25)
        stream.width, stream.height = 96, 64
        stream.pix_fmt = "yuv420p"
        stream.time_base = stream.codec_context.time_base = Fraction(1, 1000)
        stream.codec_context.max_b_frames = 2
        stream.codec_context.gop_size = 125
        stream.codec_context.options = {
            "x264-params": "b-adapt=0:b-pyramid=none:scenecut=0",
        }
        for index, timestamp in enumerate(request.param):
            image = Image.new("RGB", (96, 64), (30 + index * 5, 40, 90))
            ImageDraw.Draw(image).text((8 + index % 8, 12), str(index), fill="white")
            frame = av.VideoFrame.from_image(image)
            frame.pts, frame.time_base = timestamp, Fraction(1, 1000)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    reader = VideoReader(str(path))
    try:
        pictures = []
        while (picture := reader.next(lambda: None)) is not None:
            pictures.append(picture)
    finally:
        reader.close()
    with av.open(str(path)) as container:
        container.streams.video[0].codec_context.skip_frame = "NONREF"
        retained = {float(frame.pts * frame.time_base)
                    for frame in container.decode(video=0)}
    assert retained < {picture.time for picture in pictures}, "Fixture needs skipped B frames"
    return path, pictures, retained


def test_fast_preview_has_identical_pixels_to_default_at_the_same_pts(source_frames):
    path, reference, retained = source_frames
    reader = VideoReader(str(path))
    by_time = {picture.time: picture for picture in reference}
    try:
        for timestamp in sorted(retained, reverse=True):
            target = timestamp + .001
            actual = reader.seek_fast_preview(target, lambda: None)
            assert actual.approximate
            assert actual.time == pytest.approx(timestamp)
            assert actual.image == by_time[actual.time].image
            assert actual.image.size() == by_time[actual.time].image.size()
            assert (abs(actual.time - target) <= SCRUB_PREVIEW_TOLERANCE
                    or actual.time <= target < actual.end)
            assert reader.stream.codec_context.skip_frame == "DEFAULT"
            assert reader._fast_cursor
            assert reader.timestamp(reader._cursor_frame) == actual.time
    finally:
        reader.close()


def test_filtered_scrub_does_not_remember_skipped_frame_intervals(source_frames):
    path, _, retained = source_frames
    reader = VideoReader(str(path))
    target = sorted(retained)[-2] + .001
    try:
        sampled = reader.seek_for_scrub(target, lambda: None, sample=True,
                                       history_bytes=1024**2, keep_history=lambda: True)
        assert sampled.approximate
        assert reader.take_recent_seek_picture(target, lambda: None) is None
    finally:
        reader.close()


def test_exact_seek_and_playback_recover_b_frames_and_vfr_after_fast_preview(source_frames):
    path, reference, retained = source_frames
    reader = VideoReader(str(path))
    skipped = [(index, picture) for index, picture in enumerate(reference[:-1])
               if picture.time not in retained]
    try:
        for index, expected in reversed(skipped):
            reader.seek_fast_preview(expected.time + .001, lambda: None)
            actual = reader.seek(expected.time + .001, lambda: None)
            assert not actual.approximate
            assert actual.time == expected.time
            assert actual.end == reference[index + 1].time
            assert actual.image == expected.image
            following = reader.next(lambda: None)
            assert following.time == reference[index + 1].time
            assert following.image == reference[index + 1].image
    finally:
        reader.close()


@pytest.mark.parametrize("cancel_at", [2, 5])
def test_cancellation_restores_decode_policy_and_exact_cursor(source_frames, cancel_at):
    path, reference, _ = source_frames
    reader = VideoReader(str(path))
    checks = 0

    def cancel():
        nonlocal checks
        checks += 1
        if checks == cancel_at:
            raise Cancelled()

    try:
        with pytest.raises(Cancelled):
            reader.seek_fast_preview(.57, cancel)
        assert reader.stream.codec_context.skip_frame == "DEFAULT"
        assert reader._cursor_frame is reader._pending is None
        assert not reader._fast_cursor
        expected = reference[1]
        actual = reader.seek(expected.time + .001, lambda: None)
        assert actual.time == expected.time
        assert actual.image == expected.image
    finally:
        reader.close()


def sampled_reader(previous, successor, original_skip="DEFAULT"):
    """Use deterministic packet durations for sparse/VFR boundary cases."""
    reader = VideoReader.__new__(VideoReader)
    codec = SimpleNamespace(name="h264", skip_frame=original_skip)
    reader.stream = SimpleNamespace(codec_context=codec)
    reader.origin = 0
    reader._pending = reader._cursor_frame = None
    reader._frames = iter(())
    reader._fast_cursor = reader._sampling_fast = False
    reader._retargeted_scrub_position = None

    def seek_raw(target, check):
        check()
        assert codec.skip_frame == "NONREF"
        reader._cursor_frame, reader._pending = previous, successor
        return previous

    reader.seek_raw = seek_raw
    reader.picture = lambda frame: Picture(reader.timestamp(frame), 99, QImage())
    return reader


def sample(timestamp, duration=40):
    return SimpleNamespace(pts=timestamp, duration=duration, time_base=Fraction(1, 1000))


def test_fast_preview_chooses_nearest_frame_without_filling_skipped_intervals():
    reader = sampled_reader(sample(0), sample(120))
    actual = reader.seek_fast_preview(.09, lambda: None)
    assert actual.time == pytest.approx(.12)
    assert actual.end == pytest.approx(.16)
    assert actual.approximate


def test_unknown_duration_does_not_claim_coverage():
    reader = sampled_reader(sample(0, 0), sample(120, 0))
    actual = reader.seek_fast_preview(.09, lambda: None)
    assert actual.time == actual.end == pytest.approx(.12)
    assert actual.approximate


def test_sparse_preview_falls_back_to_default_without_claiming_skipped_coverage():
    reader = sampled_reader(sample(0), sample(800), original_skip="BIDIR")
    expected = Picture(.36, .4, QImage())

    def exact_seek(target, check):
        assert target == .38
        assert reader.stream.codec_context.skip_frame == "DEFAULT"
        assert reader._cursor_frame is reader._pending is None
        return expected

    reader.seek = exact_seek
    assert reader.seek_fast_preview(.38, lambda: None) is expected
    assert not expected.approximate
    assert reader.stream.codec_context.skip_frame == "BIDIR"
    assert reader._cursor_frame is reader._pending is None


def test_real_long_frame_duration_can_cover_distant_vfr_target():
    reader = sampled_reader(sample(0, 700), sample(800))
    actual = reader.seek_fast_preview(.38, lambda: None)
    assert actual.time == 0
    assert actual.end == pytest.approx(.7)
    assert actual.approximate


def test_other_codecs_keep_exact_decode():
    reader = VideoReader.__new__(VideoReader)
    reader.stream = SimpleNamespace(codec_context=SimpleNamespace(name="vp9"))
    expected = Picture(.36, .4, QImage())
    reader.seek = lambda target, check: expected
    assert reader.seek_fast_preview(.38, lambda: None) is expected


def test_forward_fast_requests_reuse_filtered_cursor(source_frames):
    path, _, retained = source_frames
    reader = VideoReader(str(path))
    container = reader.container
    seeks = []

    def seek(*args, **kwargs):
        seeks.append(args)
        return container.seek(*args, **kwargs)

    reader.container = SimpleNamespace(seek=seek, decode=container.decode, close=container.close)
    try:
        for timestamp in sorted(retained)[:3]:
            picture = reader.seek_fast_preview(timestamp + .001, lambda: None)
            assert picture.approximate
            assert picture.time == pytest.approx(timestamp)
        assert len(seeks) == 1
    finally:
        reader.close()


def test_existing_normal_forward_cursor_keeps_exact_sequential_decoding(source_frames):
    path, reference, _ = source_frames
    reader = VideoReader(str(path))
    try:
        reader.seek(reference[1].time, lambda: None)
        iterator = reader._frames
        actual = reader.seek_fast_preview(reference[2].time, lambda: None)
        assert not actual.approximate
        assert actual.image == reference[2].image
        assert reader._frames is iterator
        assert not reader._fast_cursor
    finally:
        reader.close()


@pytest.mark.parametrize("operation", ["next", "raw_next", "next_for_time", "previous", "seek_raw"])
def test_normal_frame_operations_restore_frames_after_fast_cursor(source_frames, operation):
    path, reference, retained = source_frames
    reader = VideoReader(str(path))
    index = next(index for index, picture in enumerate(reference[1:-1], 1)
                 if picture.time in retained and reference[index + 1].time not in retained)
    timestamp = reference[index].time
    try:
        sampled = reader.seek_fast_preview(timestamp + .001, lambda: None)
        assert sampled.approximate and reader._fast_cursor
        if operation == "next":
            actual = reader.next(lambda: None)
        elif operation == "raw_next":
            actual = reader.picture(reader.raw_next(lambda: None))
        elif operation == "next_for_time":
            actual = reader.next_for_time(timestamp, lambda: None)
        elif operation == "previous":
            actual = reader.previous(timestamp, lambda: None)
        else:
            actual = reader.picture(reader.seek_raw(reference[index + 1].time, lambda: None))
        expected = reference[index - 1 if operation == "previous" else index + 1]
        assert not actual.approximate and not reader._fast_cursor
        assert actual.time == expected.time
        assert actual.image == expected.image
    finally:
        reader.close()
