"""Reusing the reader's scaler preserves pixels and independent image ownership."""
import weakref
from fractions import Fraction
from types import SimpleNamespace

import av
import pytest
from PIL import Image, ImageDraw
from PySide6.QtGui import QImage, QTransform

from poptools.infrastructure import video_media
from poptools.infrastructure.video_media import VideoReader


@pytest.fixture
def make_reader(monkeypatch):
    # Decoding is irrelevant here: exercise the real reader lifecycle and scaler
    # with native VideoFrames, without encoding or opening a media fixture.
    class Container:
        def __init__(self):
            stream = SimpleNamespace(
                codec_context=SimpleNamespace(thread_count=2), thread_type="SLICE",
                width=96, height=64, start_time=0, time_base=Fraction(1, 1000),
                average_rate=25, duration=1000, metadata={},
            )
            self.streams = SimpleNamespace(video=[stream], audio=[])
            self.close_error = None
            self.closed = False

        def decode(self, stream):
            return iter(())

        def close(self):
            self.closed = True
            error, self.close_error = self.close_error, None
            if error:
                raise error

    monkeypatch.setattr(video_media.av, "open", lambda path: Container())
    readers = []

    def create():
        reader = VideoReader("metadata-only")
        readers.append(reader)
        return reader

    try:
        yield create
    finally:
        for reader in readers:
            reader.close()


def native_frame(size, index, pixel_format, colorspace, color_range):
    image = Image.new("RGB", size, (30 + index * 17, 90, 160))
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 7):
        draw.line((x, 0, size[0] - x, size[1] - 1), fill=(190, index * 21, 40))
    draw.rectangle((index + 3, 7, index + 25, 27), fill="white")
    source = av.VideoFrame.from_image(image)
    frame = source if pixel_format == "rgb24" else source.reformat(format=pixel_format)
    frame.colorspace = colorspace
    frame.color_range = color_range
    frame.pts, frame.time_base = index * 40, Fraction(1, 1000)
    return frame


def fresh_image(frame, size, rotation, interpolation=None):
    # Compare the original per-frame path using the same interpolation policy.
    rgb = frame.reformat(width=size[0], height=size[1], format="rgb24",
                         interpolation=interpolation)
    image = QImage(memoryview(rgb.planes[0]), *size, rgb.planes[0].line_size,
                   QImage.Format.Format_RGB888).copy()
    return image.transformed(QTransform().rotate(rotation)) if rotation else image


@pytest.mark.parametrize("rotation", [0, 90])
@pytest.mark.parametrize("interpolation", [None, "BICUBIC"])
def test_reused_scaler_matches_fresh_frames_across_parameter_changes(
    make_reader, rotation, interpolation
):
    reader = make_reader()
    reader.rotation = rotation
    reader.interpolation = interpolation
    # Repeated parameters exercise reuse; transitions cover size, YUV/RGB,
    # colorspace/range metadata, odd row strides and explicit thumbnail width.
    cases = [
        ((96, 64), "yuv420p", 1, 1, 0, None, (96, 64)),
        ((96, 64), "yuv420p", 1, 1, 0, None, (96, 64)),
        ((96, 64), "yuv420p", 5, 2, 32, None, (48, 32)),
        ((96, 64), "yuv422p", 6, 1, 32, None, (48, 32)),
        ((120, 80), "yuv444p", 1, 2, 40, None, (60, 40)),
        ((98, 66), "nv12", 5, 1, 33, None, (49, 33)),
        ((96, 64), "rgb24", 1, 2, 0, None, (96, 64)),
        ((96, 64), "gray", 5, 1, 16, 45, (45, 30)),
        ((96, 64), "yuv420p", 1, 1, 0, None, (96, 64)),
    ]
    retained = []
    previous_parameters = previous_reformatter = None
    for index, (size, pixel_format, space, color_range, height, width, output) in enumerate(cases):
        frame = native_frame(size, index, pixel_format, space, color_range)
        reader.output_height = height
        expected = fresh_image(frame, output, rotation, interpolation)
        actual = reader.picture(frame, width)
        assert actual.image == expected
        assert actual.time == pytest.approx(index * .04)
        assert actual.end == pytest.approx((index + 1) * .04)
        parameters = (size, pixel_format, space, color_range, output, interpolation)
        if parameters == previous_parameters:
            assert reader._reformatter is previous_reformatter
        else:
            assert reader._reformatter is not previous_reformatter
        previous_parameters, previous_reformatter = parameters, reader._reformatter
        retained.append((actual.image, expected))
    reader.close()
    assert reader._reformatter is None
    assert reader._reformat_key is None
    # Later conversions and reader teardown cannot invalidate already-published
    # QImages, even if the scaler's internal storage was reused or resized.
    assert all(actual == expected for actual, expected in retained)


@pytest.mark.parametrize("changes,output_height,width,interpolation,expected_size", [
    ({"size": (120, 64)}, 32, None, None, (60, 32)),
    ({"size": (96, 80)}, 32, None, None, (38, 32)),
    ({"pixel_format": "yuv422p"}, 32, None, None, (48, 32)),
    ({"colorspace": 5}, 32, None, None, (48, 32)),
    ({"color_range": 2}, 32, None, None, (48, 32)),
    ({}, 48, None, None, (72, 48)),
    ({}, 32, 60, None, (60, 40)),
    ({}, 32, None, "BICUBIC", (48, 32)),
], ids=["input-width", "input-height", "format", "colorspace", "color-range",
        "output-height", "explicit-width", "interpolation"])
def test_each_conversion_boundary_replaces_scaler_without_changing_pixels(
    make_reader, changes, output_height, width, interpolation, expected_size
):
    reader = make_reader()
    reader.output_height = 32
    parameters = {"size": (96, 64), "pixel_format": "yuv420p",
                  "colorspace": 1, "color_range": 1}
    reader.picture(native_frame(index=0, **parameters))
    previous = reader._reformatter
    reader.picture(native_frame(index=1, **parameters))
    assert reader._reformatter is previous
    reader.output_height, reader.interpolation = output_height, interpolation
    parameters.update(changes)
    frame = native_frame(index=2, **parameters)
    actual = reader.picture(frame, width)
    assert reader._reformatter is not previous
    assert actual.image == fresh_image(frame, expected_size, 0, interpolation)


@pytest.mark.parametrize("close_error", [False, True])
def test_scalers_belong_to_one_reader_and_are_released_on_close(
    make_reader, monkeypatch, close_error
):
    real_reformatter = video_media.VideoReformatter

    class TrackedReformatter:
        def __init__(self):
            self.scaler = real_reformatter()

        def reformat(self, frame, **kwargs):
            assert isinstance(frame, av.VideoFrame)
            return self.scaler.reformat(frame, **kwargs)

    monkeypatch.setattr(video_media, "VideoReformatter", TrackedReformatter)
    first, second = make_reader(), make_reader()
    assert first._reformatter is not second._reformatter
    first_ref, second_ref = weakref.ref(first._reformatter), weakref.ref(second._reformatter)
    frame = native_frame((96, 64), 1, "yuv420p", 1, 1)
    first.picture(frame)
    if close_error:
        first.container.close_error = OSError("container close failed")
        with pytest.raises(OSError, match="container close failed"):
            first.close()
    else:
        first.close()
    assert first.container.closed and first._reformatter is None
    assert first._reformat_key is None
    assert first_ref() is None
    assert second_ref() is not None
    assert second.picture(frame).image == fresh_image(frame, (96, 64), 0)
    second.close()
    assert second_ref() is None
