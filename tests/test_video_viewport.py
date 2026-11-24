"""The preview cache receives the canvas pixel budget, independent of its images."""
import math

import pytest
from PySide6.QtCore import QMetaObject, QObject, QUrl, Slot
from PySide6.QtGui import QImage
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.video_media import Picture, VideoReader
from poptools.paths import package_root
from poptools.viewmodels.video_preview_controller import VideoPreviewController
from test_video_preview import make_video


class ViewportRecorder(VideoPreviewController):
    def __init__(self):
        super().__init__()
        self.viewport_calls = []
        self.activity_calls = []

    @Slot(bool)
    def setPreviewActive(self, active):
        self.activity_calls.append(active)

    @Slot(int, int)
    def setPreviewViewport(self, width, height):
        self.viewport_calls.append((width, height))


@pytest.fixture
def workspace(qapp):
    backend = ViewportRecorder()
    engine = QQmlEngine()
    engine.addImageProvider("video", backend.images)
    engine.rootContext().setContextProperty("videoBackend", backend)
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 1100; height: 720; visible: true
    VideoPreviewWorkspace {
        objectName: "workspace"
        anchors.fill: parent; anchors.margins: 16
        controller: videoBackend
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ViewportReportTest.qml")))
    window = component.create()
    try:
        assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
        assert QTest.qWaitForWindowExposed(window)
        root = window.findChild(QObject, "workspace")
        surface = window.findChild(QObject, "videoSurface")
        yield window, root, surface, backend
        assert not warnings
    finally:
        backend.shutdown()
        if window:
            window.close()
            window.deleteLater()
        engine.deleteLater()


def expected_pixels(root, surface):
    scale = root.property("previewDevicePixelRatio") * surface.property("zoomFactor")
    return (math.ceil(surface.property("width") * scale),
            math.ceil(surface.property("height") * scale))


def test_viewport_reports_physical_pixels_and_coalesces_resize_zoom(workspace, qtbot):
    window, root, surface, backend = workspace
    qtbot.waitUntil(lambda: bool(backend.viewport_calls))
    assert backend.viewport_calls[-1] == expected_pixels(root, surface)
    assert root.property("previewDevicePixelRatio") == window.devicePixelRatio()
    backend.viewport_calls.clear()
    for width, zoom in [(1000, 1.5), (900, 2), (800, 2.5)]:
        window.setWidth(width)
        surface.setProperty("zoomFactor", zoom)
        qtbot.wait(30)
        assert not backend.viewport_calls  # No cache rebuild per resize event.
    qtbot.waitUntil(lambda: bool(backend.viewport_calls))
    assert backend.viewport_calls == [expected_pixels(root, surface)]
    backend.viewport_calls.clear()
    surface.setProperty("zoomFactor", 1)
    timeline = window.findChild(QObject, "videoTimeline")
    assert QMetaObject.invokeMethod(timeline, "scrubStarting")
    assert backend.viewport_calls == [expected_pixels(root, surface)]


def test_proxy_image_dimensions_do_not_resize_canvas_or_pixel_budget(workspace, qtbot):
    window, root, surface, backend = workspace
    picture = window.findChild(QObject, "videoPicture")
    qtbot.waitUntil(lambda: bool(backend.viewport_calls))
    expected = expected_pixels(root, surface)
    geometry = (surface.property("width"), surface.property("height"),
                picture.property("width"), picture.property("height"))
    backend.viewport_calls.clear()
    for width, height in [(3840, 2160), (1920, 1080), (3840, 2160)]:
        image = QImage(width, height, QImage.Format.Format_RGB888)
        image.fill("red")
        backend._show(Picture(0, .04, image))
        qtbot.waitUntil(lambda: picture.property("progress") == 1)
        assert geometry == (surface.property("width"), surface.property("height"),
                            picture.property("width"), picture.property("height"))
        assert expected_pixels(root, surface) == expected
    qtbot.wait(250)
    assert not backend.viewport_calls


def test_workspace_visibility_reports_activity_and_defers_hidden_viewports(workspace, qtbot):
    window, root, surface, backend = workspace
    qtbot.waitUntil(lambda: bool(backend.viewport_calls))
    assert backend.activity_calls and backend.activity_calls[-1] is True
    backend.activity_calls.clear()
    backend.viewport_calls.clear()
    root.setProperty("visible", False)
    assert backend.activity_calls == [False]
    window.setWidth(800)
    surface.setProperty("zoomFactor", 2)
    qtbot.wait(250)
    assert not backend.viewport_calls
    root.setProperty("visible", True)
    assert backend.activity_calls == [False, True]
    qtbot.waitUntil(lambda: bool(backend.viewport_calls))
    assert backend.viewport_calls[-1] == expected_pixels(root, surface)


@pytest.fixture
def budget_controller(qapp, tmp_path):
    # Only the file identity is needed to construct a proxy. No media is opened
    # and inactive preview preparation cannot decode this metadata-only source.
    source = tmp_path / "metadata-only.mp4"
    source.write_bytes(b"proxy identity")
    backend = VideoPreviewController(tmp_path / "session")
    backend._preview_active = False
    backend._playlist = [{"path": str(source), "name": source.name, "position": 0.0}]
    backend._index = 0
    backend._info = {"width": 5120, "height": 1600, "duration": 20, "fps": 30}
    try:
        yield backend
        assert backend._decoder.reader is None
    finally:
        backend.shutdown()


@pytest.mark.parametrize("source_size,rotation,viewport,expected", [
    ((5120, 1600), 0, (1068, 600), 600),
    ((5120, 1600), 0, (2136, 1200), 720),
    ((5120, 1600), 0, (3204, 1800), 1080),
    ((1600, 5120), 0, (600, 1068), 600),
    ((1600, 5120), 0, (1068, 600), 600),
    ((5120, 1600), 90, (600, 1068), 600),
    ((5120, 1600), 180, (1068, 600), 600),
    ((5120, 1600), 270, (2136, 1200), 720),
    ((1600, 5120), 90, (1068, 600), 600),
    ((1600, 5120), 270, (3204, 1800), 1080),
], ids=["ultrawide", "double-dpi-or-zoom", "larger-viewport", "portrait-canvas",
        "portrait-in-landscape", "rotate-90", "rotate-180", "rotate-270-scaled",
        "rotated-portrait", "rotated-portrait-large"])
def test_proxy_pixel_budget_covers_painted_source_without_decode(
    budget_controller, source_size, rotation, viewport, expected
):
    backend = budget_controller
    width, height = source_size
    backend._info.update(width=width, height=height)
    backend.setPreviewViewport(*viewport)
    assert backend._proxy.output_height == expected
    assert backend._drag_cache.output_height == expected

    output_scale = expected / min(source_size)
    generated = (round(width * output_scale), round(height * output_scale))
    displayed_source = source_size
    if rotation % 180:
        generated = generated[::-1]
        displayed_source = source_size[::-1]
    painted_scale = min(viewport[0] / displayed_source[0],
                        viewport[1] / displayed_source[1])
    painted = tuple(length * painted_scale for length in displayed_source)
    assert all(actual >= math.ceil(needed)
               for actual, needed in zip(generated, painted, strict=True))
    if source_size == (5120, 1600) and rotation == 0 and viewport == (1068, 600):
        assert generated == (1920, 600)
        assert painted == pytest.approx((1068, 333.75))
    assert [row["value"] for row in backend.resolutionOptions] == [0, 720, 1080, 1440]


@pytest.mark.parametrize("resolution,expected", [(0, 1600), (720, 720),
                                                 (1080, 1080), (1440, 1440)])
def test_proxy_budget_respects_native_and_explicit_resolution_caps(
    budget_controller, monkeypatch, resolution, expected
):
    backend = budget_controller
    # Exercise the public option without scheduling an unrelated source seek.
    monkeypatch.setattr(backend, "seek", lambda position: None)
    backend.setPreviewViewport(10000, 6000)
    backend.setResolution(resolution)
    assert backend.resolution == resolution
    assert backend._proxy.output_height == expected
    assert backend._drag_cache.output_height == expected
    assert backend._proxy.output_height <= min(backend._info["width"], backend._info["height"])
    assert 600 not in [row["value"] for row in backend.resolutionOptions]
    backend.setResolution(600)
    assert backend.resolution == resolution
    assert backend._proxy.output_height == expected


def test_large_video_playback_adjusts_to_viewport_and_restores_frame_on_pause(
        qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / "playback-size.mp4", size=(1920, 1440))
    backend = VideoPreviewController()
    try:
        backend.setPreviewViewport(800, 600)
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.togglePlayback()
        qtbot.waitUntil(lambda: backend.images._live.height() == 600)
        assert backend._displayed_playback_frame.source_frame.height == 1440

        backend.setPreviewViewport(3000, 2200)
        qtbot.waitUntil(lambda: backend.images._live.height() == 1440)
        assert backend.playing and backend._displayed_playback_frame is None

        backend.setPreviewViewport(800, 600)
        qtbot.waitUntil(lambda: backend.images._live.height() == 600
                        and backend._next is not None and backend._next.source_frame is not None)
        position = backend.position
        successor = backend._next

        def no_seek(*args, **kwargs):
            pytest.fail("Pausing and continuing with a buffered frame must not seek")

        monkeypatch.setattr(backend._decoder.reader, "seek_raw", no_seek)
        backend.pause()
        assert not backend.playing and not backend.busy
        qtbot.waitUntil(lambda: backend.images._live.height() == 1440)
        assert backend._displayed_playback_frame is None
        reference = VideoReader(str(path))
        try:
            expected = reference.seek(position, lambda: None)
            assert backend.position == expected.time == position
            assert backend.images._live == expected.image
        finally:
            reference.close()

        resumed = []
        backend.frameChanged.connect(lambda: resumed.append(backend.position))
        backend.togglePlayback()
        qtbot.waitUntil(lambda: bool(resumed))
        assert backend.playing
        assert resumed[0] == successor.time > position
        assert backend._paused_successor is None
    finally:
        backend.shutdown()
