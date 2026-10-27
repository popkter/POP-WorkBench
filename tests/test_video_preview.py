import math
import struct
import threading
import time
from fractions import Fraction
from pathlib import Path

import av
import pytest
from PIL import Image, ImageDraw
from PySide6.QtCore import QMetaObject, QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.video_audio import AudioPlayback
from poptools.infrastructure.video_media import VideoReader, filmstrip, local_video_paths
from poptools.paths import package_root
from poptools.viewmodels.video_preview_controller import VideoPreviewController


def make_video(path, pts=None, audio=False, size=(320, 180)):
    pts = pts or list(range(0, 2000, 40))
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=25)
        stream.width, stream.height = size
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        stream.codec_context.time_base = Fraction(1, 1000)
        stream.codec_context.max_b_frames = 2
        stream.codec_context.gop_size = 12
        sound = output.add_stream("aac", rate=48000) if audio else None
        if sound:
            sound.layout = "stereo"
        for i, timestamp in enumerate(pts):
            image = Image.new("RGB", size, (20 + i * 3 % 220, 40, 90))
            ImageDraw.Draw(image).text((30 + i % 10, 60), f"Video preview / {i:03d}", fill="white")
            frame = av.VideoFrame.from_image(image)
            frame.pts = timestamp
            frame.time_base = Fraction(1, 1000)
            for packet in stream.encode(frame):
                output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
        if sound:
            for i in range(50):
                frame = av.AudioFrame(format="s16", layout="stereo", samples=1920)
                frame.sample_rate = 48000
                frame.pts = i * 1920
                frame.time_base = Fraction(1, 48000)
                frame.planes[0].update(b"".join(
                    struct.pack("<hh", *([int(5000 * math.sin(2 * math.pi * 440
                        * (i * 1920 + sample) / 48000))] * 2)) for sample in range(1920)))
                for packet in sound.encode(frame):
                    output.mux(packet)
            for packet in sound.encode():
                output.mux(packet)
    return path


@pytest.fixture
def clip(tmp_path):
    return make_video(tmp_path / "测试 clip.mp4")


@pytest.mark.parametrize("pts", [None, [0, 40, 80, 160, 200, 320, 360, 400, 560, 600]])
def test_seek_and_reverse_return_actual_frames_with_b_frames_and_vfr(tmp_path, pts):
    path = make_video(tmp_path / "frames.mp4", pts)
    with av.open(str(path)) as container:
        reference = [(float(f.pts * f.time_base), f.to_image().getpixel((0, 0)))
                     for f in container.decode(video=0)]
    reader = VideoReader(str(path))
    try:
        for index in (1, len(reference) // 2, len(reference) - 1):
            timestamp, color = reference[index]
            picture = reader.seek(timestamp + 0.001, lambda: None)
            assert picture.time == pytest.approx(timestamp)
            if index + 1 < len(reference):
                assert picture.end == pytest.approx(reference[index + 1][0])
            assert picture.image.pixelColor(0, 0).getRgb()[:3] == color
            previous = reader.previous(picture.time, lambda: None)
            assert previous.time == pytest.approx(reference[index - 1][0])
            assert reader.next(lambda: None).time == pytest.approx(timestamp)
    finally:
        reader.close()


def test_filmstrip_becomes_contiguous_source_frames_at_high_zoom(clip):
    detailed, pictures = filmstrip(str(clip), 0.2, 0.6, 25 * 100, lambda: None)
    assert detailed
    assert [p.time for p in pictures] == pytest.approx([i / 25 for i in range(5, 15)])
    assert all(p.image.width() <= 200 for p in pictures)
    overview, samples = filmstrip(str(clip), 0, 2, 200, lambda: None)
    assert not overview and len(samples) < len(pictures)


def test_local_paths_accept_unicode_file_urls_and_deduplicate(clip):
    assert local_video_paths([str(clip), QUrl.fromLocalFile(str(clip)).toString(),
                              "https://example.com/test.mp4"]) == [str(clip.resolve())]


def test_latest_file_wins_and_playback_step_and_restore(qapp, qtbot, clip, tmp_path):
    other = make_video(tmp_path / "other.mp4")
    backend = VideoPreviewController(tmp_path / "session")
    try:
        backend.addFiles([str(clip), str(other)])
        backend.selectVideo(1)
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        assert backend.fileName == "other.mp4"
        backend.seek(0.8)
        backend.seek(0.4)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(0.4)
        backend.step(-1)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(0.36)
        backend.togglePlayback()
        qtbot.waitUntil(lambda: backend.position >= 0.6, timeout=4000)
        backend.pause()
        position = backend.position
        backend.requestThumbnails(0.2, 0.6, 2500)
        qtbot.waitUntil(lambda: not backend.thumbnailBusy)
        assert backend.detailed and len(backend.thumbnails) == 10
        backend.requestPreview(0.28)
        assert backend.previewTime == pytest.approx(0.28)
        assert backend.position == position
        backend.requestPreview(0.85)
        backend.requestPreview(1.25)
        qtbot.waitUntil(lambda: not backend.previewBusy)
        assert backend.previewTime == pytest.approx(1.24)
        assert backend.position == position
        backend.selectVideo(0)
        qtbot.waitUntil(lambda: not backend.busy)
        backend.selectVideo(1)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(position)
    finally:
        backend.shutdown()
    restored = VideoPreviewController(tmp_path / "session")
    try:
        assert len(restored.playlist) == 2
        assert restored.playlist[1]["position"] == pytest.approx(position)
    finally:
        restored.shutdown()


def test_corrupt_file_is_recoverable_and_removing_current_clears_media(qapp, qtbot, clip, tmp_path):
    corrupt = tmp_path / "broken.mp4"
    corrupt.write_bytes(b"not video")
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(corrupt), str(clip)])
        qtbot.waitUntil(lambda: not backend.busy)
        assert "无法读取视频" in backend.message and not backend.loaded
        backend.selectVideo(1)
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.removeVideo(0)
        backend.removeVideo(0)
        assert not backend.loaded and backend.frameSource == "" and not backend.playlist
    finally:
        backend.shutdown()


@pytest.mark.parametrize("removal", ["last", "current", "previous"])
@pytest.mark.parametrize("hover_running", [False, True])
def test_removed_video_releases_hover_reader_and_can_be_deleted(
    qapp, qtbot, clip, tmp_path, monkeypatch, removal, hover_running
):
    other = make_video(tmp_path / "remaining.mp4")
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip)] if removal == "last" else [str(clip), str(other)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.requestPreview(0.4)
        qtbot.waitUntil(lambda: not backend.previewBusy)
        assert backend.previewSource
        if hover_running:
            started = threading.Event()

            def slow_preview(target, check):
                started.set()
                while True:
                    check()
                    time.sleep(0.005)

            monkeypatch.setattr(backend._preview_reader, "seek_raw", slow_preview)
            backend.requestPreview(0.8)
            qtbot.waitUntil(started.is_set)
        if removal == "previous":
            backend.selectVideo(1)
            qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.removeVideo(0)

        # Do not shut down the controller: removing the item must release it
        # while the application remains open, including the idle hover reader.
        qtbot.waitUntil(lambda: backend._preview_reader is None, timeout=3000)

        def deleted():
            try:
                clip.unlink(missing_ok=True)
                return True
            except PermissionError:
                return False

        qtbot.waitUntil(deleted, timeout=3000)
        if removal != "last":
            qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
            assert backend.fileName == other.name
            backend.seek(0.8)
            qtbot.waitUntil(lambda: not backend.busy)
            assert backend.position == pytest.approx(0.8)
    finally:
        backend.shutdown()


def test_removing_last_video_cancels_duration_probe(qapp, qtbot, clip, monkeypatch):
    started = threading.Event()
    finished = threading.Event()

    def slow_probe(reader, check):
        started.set()
        try:
            while True:
                check()
                time.sleep(0.005)
        finally:
            finished.set()

    monkeypatch.setattr(VideoReader, "probe_end", slow_probe)
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy and started.is_set())
        backend.removeVideo(0)
        qtbot.waitUntil(finished.is_set, timeout=3000)
        assert backend._metadata_token == -1

        def deleted():
            try:
                clip.unlink(missing_ok=True)
                return True
            except PermissionError:
                return False

        qtbot.waitUntil(deleted, timeout=3000)
    finally:
        backend.shutdown()


@pytest.mark.parametrize('suffix', ['mp4', 'mkv'])
def test_audio_resampling_trims_to_seek_and_stays_bounded(qapp, tmp_path, suffix):
    clip = make_video(tmp_path / f"with-audio.{suffix}", audio=True)
    audio = AudioPlayback()
    try:
        audio._decode(str(clip), 1.5, 0, lambda: None)
        assert audio._finished
        # Half a second plus AAC encoder padding, in interleaved stereo PCM.
        assert 24000 * 4 <= len(audio._buffer) <= 26000 * 4
        assert len(audio._buffer) <= audio.RATE * audio.BYTES_PER_SAMPLE
        assert any(audio._buffer), "Audio decoding must preserve audible PCM, not only silence."
    finally:
        audio.close()


def test_video_with_audio_plays_to_end_and_retains_final_picture(qapp, qtbot, tmp_path):
    clip = make_video(tmp_path / "sound.mp4", audio=True)
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.togglePlayback()
        qtbot.waitUntil(lambda: backend.position > 0.3, timeout=6000)
        qtbot.waitUntil(lambda: not backend.playing, timeout=8000)
        assert backend.position == pytest.approx(1.96)
        assert backend.frameSource
        backend.togglePlayback()
        qtbot.waitUntil(lambda: backend.playing and 0 < backend.position < 0.5, timeout=6000)
    finally:
        backend.shutdown()


def test_packaging_keeps_audio_and_ffmpeg_binaries():
    source = (Path(__file__).resolve().parents[1] / "packaging/poptools.spec").read_text(
        encoding="utf-8")
    scope = {}
    exec(source[source.index("UNUSED_QT_QML_PREFIXES"):source.index("common_datas =")], scope)
    keep = scope["keep_qt_entry"]
    for name in ("PySide6/Qt6Multimedia.dll", "PySide6/QtMultimedia.pyd",
                 "av.libs/avcodec-62-example.dll", "av/video/frame.pyd"):
        assert keep((name, "", ""))


@pytest.mark.parametrize("width", [720, 1100])
def test_video_workspace_and_titlebar_render_and_actions_work(qapp, qtbot, clip, width):
    QFontDatabase.addApplicationFont(str(
        package_root() / "resources/fonts/MaterialIconsRound-Regular.otf"))
    backend = VideoPreviewController()
    engine = QQmlEngine()
    engine.addImageProvider("video", backend.images)
    engine.rootContext().setContextProperty("videoBackend", backend)
    component = QQmlComponent(engine)
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 1100; height: 720; visible: true
    property real titleBarHeight: 48
    property int captionControlWidth: 47
    property bool modernCaptionControls: true
    property rect titleBarActionsRect
    property int captionHovered: -1
    property int captionPressed: -1
    WindowTitleBar {
        id: bar
        hostWindow: host
        width: parent.width; height: 48
        videoController: videoBackend
        videoActionsVisible: true
    }
    VideoPreviewWorkspace {
        anchors.top: bar.bottom
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 16
        controller: videoBackend
        actionsInTitleBar: true
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/VideoTestHarness.qml")))
    window = component.create()
    try:
        assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
        assert QTest.qWaitForWindowExposed(window)
        window.setWidth(width)
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy,
                        timeout=10000)

        def assert_thumbnail_track_visible():
            def visual_items(item):
                yield item
                for child in item.childItems():
                    yield from visual_items(child)

            pictures = [item for item in visual_items(window.contentItem())
                        if item.objectName() == "videoTimelineThumbnailPicture"]
            assert pictures, "The timeline must render pictures, not just frame boundary lines."
            qtbot.waitUntil(lambda: all(item.property("implicitWidth") > 0 for item in pictures))
            assert all(item.property("visible") and item.width() > 0 for item in pictures)
            assert all(not item.property("source").isEmpty() for item in pictures)

        backend.zoom(200)
        qtbot.waitUntil(lambda: backend.detailed and not backend.thumbnailBusy, timeout=10000)
        assert_thumbnail_track_visible()
        actions = window.findChild(QObject, "titleBarVideoActions")
        rect = window.property("titleBarActionsRect")
        assert rect.width() == pytest.approx(actions.width())
        assert rect.right() < width - 3 * 47 - 32  # Retain a caption drag area.
        playback = window.findChild(QObject, "videoPlaybackControls")
        play = playback.findChild(QObject, "videoPlayButton")
        assert not actions.findChild(QObject, "videoPlayButton").property("visible")
        assert QMetaObject.invokeMethod(play, "clicked")
        qtbot.waitUntil(lambda: backend.position > 0.1, timeout=4000)
        backend.pause()
        surface = window.findChild(QObject, "videoSurface")
        picture = window.findChild(QObject, "videoPicture")
        surface_bounds = surface.mapRectToItem(window.contentItem(), surface.boundingRect())
        anchor = QPoint(round(surface_bounds.x() + surface.width() * 0.55),
                        round(surface_bounds.y() + surface.height() * 0.55))

        def image_point():
            point = picture.mapFromItem(window.contentItem(), anchor)
            return point.x() / picture.width(), point.y() / picture.height()

        def wheel(delta):
            # QTest's window-system wheel helper receives native screen pixels.
            QTest.wheelEvent(window, QPointF(anchor) * window.devicePixelRatio(), QPoint(0, delta))

        before_zoom = image_point()
        wheel(480)
        qtbot.waitUntil(lambda: surface.property("zoomFactor") > 2)
        assert image_point() == pytest.approx(before_zoom, abs=0.001)
        zoom = surface.property("zoomFactor")
        offset = surface.property("panX"), surface.property("panY")
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=anchor)
        QTest.mouseMove(window, anchor + QPoint(40, 25), delay=30)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=anchor + QPoint(40, 25))
        assert surface.property("panX") == pytest.approx(offset[0] + 40, abs=1)
        assert surface.property("panY") == pytest.approx(offset[1] + 25, abs=1)
        # Capture the rendered viewport, including its current zoom and pan,
        # rather than copying the uncropped source frame from the decoder.
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        expected = window.grabWindow()
        screenshot_button = window.findChild(QObject, "videoScreenshotButton")
        fit_button = window.findChild(QObject, "videoFitPictureButton")
        screenshot_bounds = screenshot_button.mapRectToItem(
            window.contentItem(), screenshot_button.boundingRect())
        fit_bounds = fit_button.mapRectToItem(window.contentItem(), fit_button.boundingRect())
        assert screenshot_bounds.left() >= fit_bounds.right()
        assert screenshot_bounds.right() <= width
        qapp.clipboard().clear()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                         pos=screenshot_bounds.center().toPoint())
        qtbot.waitUntil(lambda: not qapp.clipboard().image().isNull())
        captured = qapp.clipboard().image()
        dpr = window.devicePixelRatio()
        assert captured.width() == pytest.approx(surface.width() * dpr, abs=1)
        assert captured.height() == pytest.approx(surface.height() * dpr, abs=1)
        for fx, fy in ((0.1, 0.1), (0.25, 0.5), (0.5, 0.5), (0.75, 0.5), (0.9, 0.9)):
            actual_color = captured.pixelColor(
                int(captured.width() * fx), int(captured.height() * fy))
            expected_color = expected.pixelColor(
                int((surface_bounds.x() + surface.width() * fx) * dpr),
                int((surface_bounds.y() + surface.height() * fy) * dpr))
            assert actual_color.getRgb() == expected_color.getRgb()
        capture_toast = window.findChild(QObject, "videoCaptureToast")
        qtbot.waitUntil(lambda: capture_toast.property("opened"))
        assert capture_toast.property("message") == "截图已复制到剪贴板"
        assert not capture_toast.property("error")
        assert not backend.playing
        QMetaObject.invokeMethod(capture_toast, "close")
        # Popup overlays (including the playlist) are not part of the video.
        backend.toggleList()
        capture_drawer = window.findChild(QObject, "videoPlaylistDrawer")
        qtbot.waitUntil(lambda: capture_drawer.property("opened"))
        qapp.clipboard().clear()
        assert QMetaObject.invokeMethod(screenshot_button, "clicked")
        qtbot.waitUntil(lambda: not qapp.clipboard().image().isNull())
        assert qapp.clipboard().image() == captured
        backend.closeList()
        QMetaObject.invokeMethod(capture_toast, "close")
        qtbot.waitUntil(lambda: not capture_drawer.property("visible"))
        backend.seek(0.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert surface.property("zoomFactor") == zoom
        assert surface.property("panX") == pytest.approx(offset[0] + 40, abs=1)
        # Strong zoom-out returns to fit without leaving the picture offscreen.
        wheel(-2400)
        qtbot.waitUntil(lambda: surface.property("zoomFactor") == 1)
        assert surface.property("panX") == surface.property("panY") == 0
        wheel(480)
        qtbot.waitUntil(lambda: surface.property("zoomFactor") > 2)
        fit_picture = window.findChild(QObject, "videoFitPictureButton")
        fit_bounds = fit_picture.mapRectToItem(window.contentItem(), fit_picture.boundingRect())
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=fit_bounds.center().toPoint())
        assert surface.property("zoomFactor") == 1
        assert surface.property("panX") == surface.property("panY") == 0
        backend.fit()
        qtbot.waitUntil(lambda: bool(backend.thumbnails) and not backend.detailed
                        and not backend.thumbnailBusy, timeout=10000)
        assert_thumbnail_track_visible()
        # Locating the playhead scrolls the timeline without seeking or fitting.
        timeline_root = window.findChild(QObject, "videoTimeline")
        backend.seek(0.8)
        qtbot.waitUntil(lambda: not backend.busy)
        backend.zoom(20)
        qtbot.waitUntil(lambda: timeline_root.property("viewSpan") < 0.4)
        scale = timeline_root.property("pixelsPerSecond")
        timeline_root.setProperty("viewStart", 0)
        timeline_root.setProperty("followPlayback", False)
        locate = timeline_root.findChild(QObject, "videoLocatePlayheadButton")
        assert QMetaObject.invokeMethod(locate, "clicked")
        assert timeline_root.property("viewStart") == pytest.approx(
            backend.position - timeline_root.property("viewSpan") / 2)
        assert timeline_root.property("pixelsPerSecond") == scale
        assert timeline_root.property("followPlayback")
        assert backend.position == pytest.approx(0.8) and not backend.playing
        backend.fit()
        timeline = window.findChild(QObject, "videoTimelineTrack")
        bounds = timeline.mapRectToItem(window.contentItem(), timeline.boundingRect())

        def at(fraction):
            return QPoint(round(bounds.x() + bounds.width() * fraction), round(bounds.y() + 36))

        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=at(0.8))
        qtbot.waitUntil(lambda: not backend.busy and backend.position >= 1.5)
        selected = backend.position
        QTest.mouseMove(window, at(0.25))
        popup = window.findChild(QObject, "videoHoverPreview")
        qtbot.waitUntil(lambda: popup.property("visible") and bool(backend.previewSource)
                        and not backend.previewBusy)
        assert backend.previewTime == pytest.approx(0.48, abs=0.041)
        assert backend.position == selected  # Hover must not move the main picture.
        surface = window.findChild(QObject, "videoSurface")
        before = (surface.width(), surface.height())
        backend.toggleList()
        drawer = window.findChild(QObject, "videoPlaylistDrawer")
        qtbot.waitUntil(lambda: drawer.property("opened"))
        assert (surface.width(), surface.height()) == before
        backend.closeList()
        qtbot.waitUntil(lambda: not drawer.property("visible"))
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=at(0.2))
        QTest.mouseMove(window, at(0.6), delay=50)
        qtbot.waitUntil(lambda: not backend.busy and 1.1 < backend.position < 1.3)
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=at(0.6))
        qtbot.waitUntil(lambda: not backend.busy)
        assert not backend.playing
        playhead = window.findChild(QObject, "videoTimelinePlayhead")
        assert playhead.property("visible")
        grab = QPoint(round(bounds.x() + playhead.x()), round(bounds.y() + 23))
        destination = QPoint(at(0.35).x(), grab.y())
        previous_frame = backend.frameSource
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=grab)
        QTest.mouseMove(window, destination, delay=50)
        assert not popup.property("visible")
        assert not backend.previewBusy
        assert playhead.x() == pytest.approx(destination.x() - bounds.x(), abs=2)
        qtbot.waitUntil(lambda: not backend.busy and 0.6 < backend.position < 0.8)
        assert backend.frameSource != previous_frame  # Main picture changes before release.
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=destination)
        QTest.mouseMove(window, at(0.4))
        qtbot.waitUntil(lambda: bool(backend.previewSource) and not backend.previewBusy
                        and abs(backend.previewTarget - 0.8) < 0.01)
        assert popup.property("y") + popup.property("height") < bounds.y()
        assert popup.property("y") > bounds.y() - popup.property("height") - 20
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        assert not window.grabWindow().isNull()
        if width == 1100:
            output = Path("build/video-preview.png")
            output.parent.mkdir(exist_ok=True)
            window.grabWindow().save(str(output))
        # Actual timeline gestures preserve the playback state across the
        # asynchronous source-quality seek on release.
        backend.togglePlayback()
        qtbot.waitUntil(lambda: backend.playing)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=at(0.15))
        qtbot.waitUntil(lambda: backend.playing and not backend.busy)
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=at(0.2))
        assert not backend.playing
        QTest.mouseMove(window, at(0.4), delay=50)
        qtbot.waitUntil(lambda: not backend.busy)
        assert not backend.playing
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=at(0.4))
        qtbot.waitUntil(lambda: backend.playing and not backend.busy)
        qtbot.waitUntil(lambda: backend.position > 1.1)
        backend.pause()
        wheel(480)
        qtbot.waitUntil(lambda: surface.property("zoomFactor") > 2)
        backend.selectVideo(0)
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert surface.property("zoomFactor") == 1
        assert not warnings
    finally:
        backend.shutdown()
        if window:
            window.close()
            window.deleteLater()
        engine.deleteLater()

@pytest.mark.parametrize("width", [720, 1100])
def test_dragging_timeline_keeps_player_geometry_stable(qapp, qtbot, clip, monkeypatch, width):
    backend = VideoPreviewController()
    engine = QQmlEngine()
    engine.addImageProvider("video", backend.images)
    engine.rootContext().setContextProperty("videoBackend", backend)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 1100; height: 720; visible: true
    VideoPreviewWorkspace {
        anchors.fill: parent; anchors.margins: 16
        controller: videoBackend; actionsInTitleBar: true
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/VideoLayoutTest.qml")))
    window = component.create()
    release_frame = threading.Event()
    try:
        assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
        window.setWidth(width)
        assert QTest.qWaitForWindowExposed(window)
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        qtbot.waitUntil(lambda: backend._scrub_cache.get(0.4) is not None)
        surface = window.findChild(QObject, "videoSurface")
        picture = window.findChild(QObject, "videoPicture")
        track = window.findChild(QObject, "videoTimelineTrack")

        def geometry():
            with qtbot.waitSignal(window.frameSwapped):
                window.update()
            return [item.mapRectToItem(window.contentItem(), item.boundingRect())
                    for item in (surface, picture, track)]

        baseline = geometry()
        read = backend._scrub_cache.get

        def delayed_frame(target):
            # Hold an actual drag request long enough for the busy layout to render.
            release_frame.wait(5)
            return read(target)

        monkeypatch.setattr(backend._scrub_cache, "get", delayed_frame)
        bounds = baseline[-1]
        for index, fraction in enumerate((0.2, 0.7, 0.4)):
            release_frame.clear()
            point = QPoint(round(bounds.x() + bounds.width() * fraction),
                           round(bounds.y() + 36))
            if index == 0:
                QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point)
            else:
                QTest.mouseMove(window, point, delay=0)
            qtbot.waitUntil(lambda: backend.busy)
            assert geometry() == baseline
            release_frame.set()
            qtbot.waitUntil(lambda: not backend.busy)
            assert geometry() == baseline
        QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point)
        qtbot.waitUntil(lambda: not backend.busy)
        assert geometry() == baseline
    finally:
        release_frame.set()
        if window:
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton)
        backend.shutdown()
        if window:
            window.close()
            window.deleteLater()
        engine.deleteLater()


@pytest.mark.parametrize("width", [720, 1100])
def test_playlist_stays_inside_offset_workspace_and_switches_files(
        qapp, qtbot, tmp_path, monkeypatch, width):
    from PySide6.QtWidgets import QFileDialog

    clips = [make_video(tmp_path / name) for name in ("first.mp4", "second.mp4", "third.mp4")]
    chosen = [str(path) for path in clips[:2]]
    monkeypatch.setattr(QFileDialog, "getOpenFileNames", lambda *args: (chosen, ""))
    backend = VideoPreviewController()
    engine = QQmlEngine()
    engine.addImageProvider("video", backend.images)
    engine.rootContext().setContextProperty("videoBackend", backend)
    component = QQmlComponent(engine)
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 1100; height: 760; visible: true
    VideoToolbar { controller: videoBackend; x: 48; y: 8; chrome: true }
    Item {
        x: 260; y: 48; width: parent.width - x - 16; height: parent.height - y - 16
        VideoPreviewWorkspace {
            objectName: "workspace"
            anchors.fill: parent
            controller: videoBackend
            actionsInTitleBar: true
        }
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/PlaylistTestHarness.qml")))
    window = component.create()

    def visual_items(item):
        yield item
        for child in item.childItems():
            yield from visual_items(child)

    def click(item):
        bounds = item.mapRectToItem(window.contentItem(), item.boundingRect())
        assert 0 <= bounds.left() < bounds.right() <= window.width()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=bounds.center().toPoint())

    def row(index):
        return next(item for item in visual_items(window.contentItem())
                    if item.objectName() == "videoPlaylistRow" and item.property("index") == index)

    try:
        assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
        assert QTest.qWaitForWindowExposed(window)
        window.setWidth(width)
        click(window.findChild(QObject, "videoOpenButton"))
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        assert len(backend.playlist) == 2
        # Opening several files must reveal how to switch between them.
        assert backend.listVisible
        drawer = window.findChild(QObject, "videoPlaylistDrawer")
        qtbot.waitUntil(lambda: drawer.property("opened"))
        playlist = window.findChild(QObject, "videoPlaylist")
        workspace = window.findChild(QObject, "workspace")
        bounds = playlist.mapRectToItem(window.contentItem(), playlist.boundingRect())
        workspace_bounds = workspace.mapRectToItem(window.contentItem(), workspace.boundingRect())
        assert bounds.right() <= workspace_bounds.right() + 1
        assert bounds.left() >= workspace_bounds.left()
        surface = window.findChild(QObject, "videoSurface")
        surface_bounds = surface.mapRectToItem(window.contentItem(), surface.boundingRect())
        drawer_content = drawer.property("contentItem")
        drawer_bounds = drawer_content.mapRectToItem(
            window.contentItem(), drawer_content.boundingRect())
        assert drawer.property("height") == pytest.approx(surface.height())
        assert drawer_bounds.top() - drawer.property("topPadding") == pytest.approx(
            surface_bounds.top())
        assert drawer_bounds.right() + drawer.property("rightPadding") == pytest.approx(
            surface_bounds.right())
        click(row(1))
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend.fileName == "second.mp4"
        assert not backend.listVisible
        backend.seek(0.8)
        qtbot.waitUntil(lambda: not backend.busy)
        click(window.findChild(QObject, "videoPlaylistButton"))
        qtbot.waitUntil(lambda: drawer.property("opened"))
        click(row(0))
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend.fileName == "first.mp4"
        click(window.findChild(QObject, "videoPlaylistButton"))
        qtbot.waitUntil(lambda: drawer.property("opened"))
        click(row(1))
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend.position == pytest.approx(0.8)
        # Append from the list without replacing or interrupting the current video.
        click(window.findChild(QObject, "videoPlaylistButton"))
        qtbot.waitUntil(lambda: drawer.property("opened"))
        chosen[:] = [str(clips[2])]
        click(window.findChild(QObject, "videoPlaylistAddButton"))
        assert len(backend.playlist) == 3
        assert backend.fileName == "second.mp4" and backend.position == pytest.approx(0.8)
        with qtbot.waitSignal(window.frameSwapped):
            window.update()
        third_row = row(2)
        click(third_row.findChild(QObject, "videoPlaylistRemoveButton"))
        assert len(backend.playlist) == 2 and backend.fileName == "second.mp4"
        QTest.keyClick(window, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not backend.listVisible)
        click(window.findChild(QObject, "videoPlaylistButton"))
        qtbot.waitUntil(lambda: drawer.property("opened"))
        click(row(0))
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend.fileName == "first.mp4"
        click(window.findChild(QObject, "videoPlaylistButton"))
        qtbot.waitUntil(lambda: drawer.property("opened"))
        first_row = row(0)
        click(first_row.findChild(QObject, "videoPlaylistRemoveButton"))
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert backend.fileName == "second.mp4" and len(backend.playlist) == 1
        assert backend.position == pytest.approx(0.8)
        QTest.mouseClick(window, Qt.MouseButton.LeftButton,
                         pos=workspace_bounds.topLeft().toPoint() + QPoint(5, 5))
        qtbot.waitUntil(lambda: not backend.listVisible)
        assert not warnings
    finally:
        backend.shutdown()
        if window:
            window.close()
            window.deleteLater()
        engine.deleteLater()

@pytest.mark.parametrize('size,choices', [
    ((3840, 2160), [0, 720, 1080, 1440, 2160]),
    ((1440, 2560), [0, 720, 1080, 1440]),
    ((640, 360), [0]),
])
def test_native_resolution_choices_and_output(qapp, qtbot, tmp_path, size, choices):
    clip = make_video(tmp_path / 'quality.mp4', pts=[0, 40, 80], size=size)
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        assert backend.resolution == 0
        assert [row['value'] for row in backend.resolutionOptions] == choices
        assert (backend.images._live.width(), backend.images._live.height()) == size
        for resolution in choices[1:] + [0]:
            backend.setResolution(resolution)
            qtbot.waitUntil(lambda: not backend.busy, timeout=10000)
            scale = min(1, resolution / min(size)) if resolution else 1
            assert backend.images._live.width() == round(size[0] * scale)
            assert backend.images._live.height() == round(size[1] * scale)
            assert backend.position == 0
        backend.setResolution(9999)
        assert backend.resolution == 0
    finally:
        backend.shutdown()


def test_forward_seeking_reuses_decoder_without_losing_frame_accuracy(clip):
    reader = VideoReader(str(clip))
    try:
        assert reader.seek(0.4, lambda: None).time == pytest.approx(0.4)
        iterator = reader._frames
        for target in (0.41, 0.48, 0.65, 0.95):
            picture = reader.seek(target, lambda: None)
            assert picture.time <= target < picture.end + 1e-7
            assert reader._frames is iterator
        assert reader.seek(0.2, lambda: None).time == pytest.approx(0.2)
        assert reader._frames is not iterator
    finally:
        reader.close()

@pytest.mark.parametrize('pts', [None, [0, 40, 80, 160, 200, 320, 360, 400, 560, 600]])
def test_scrub_cache_preserves_frame_intervals_and_memory_budget(tmp_path, pts):
    from poptools.infrastructure.video_scrub import ScrubCache
    path = make_video(tmp_path / 'cache.mp4', pts=pts)
    cache = ScrubCache(str(path))
    cache.warm(0, lambda: None)
    reader = VideoReader(str(path))
    try:
        for target in (0.05, 0.1, 0.18, 0.39, 0.57):
            expected = reader.seek(target, lambda: None)
            cached = cache.get(target)
            assert cached is not None and cached.time == pytest.approx(expected.time)
            assert cached.time <= target < cached.end
        cache.budget = 4096
        for time in (0, 0.04, 0.16, 0.32, 0.56):
            cache.put(reader.seek(time, lambda: None))
        assert cache._bytes <= cache.budget
        assert cache._times == sorted(cache._frames)
    finally:
        reader.close()


def test_cached_drag_restores_native_picture_on_release(qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / 'native.mp4', size=(1280, 720))
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        qtbot.waitUntil(lambda: backend._scrub_cache.get(0.8) is not None, timeout=10000)
        seek = backend._decoder.reader.seek
        def no_source_seek(*args):
            raise AssertionError('A cached drag must not decode the source GOP again')
        monkeypatch.setattr(backend._decoder.reader, 'seek', no_source_seek)
        backend.scrub(0.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert not backend.message
        assert backend.position == pytest.approx(0.8)
        assert backend.images._live.width() == 960
        monkeypatch.setattr(backend._decoder.reader, 'seek', seek)
        backend.seek(0.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1280
        assert backend.resolution == 0
    finally:
        backend.shutdown()

@pytest.mark.parametrize('rate', [0.25, 0.5, 1, 1.5, 2])
def test_real_audio_output_accepts_pcm_at_all_playback_rates(qapp, qtbot, tmp_path, rate):
    from PySide6.QtMultimedia import QMediaDevices
    if QMediaDevices.defaultAudioOutput().isNull():
        pytest.skip('No system audio output is available on this test host')
    path = make_video(tmp_path / 'tone.mp4', audio=True)
    audio = AudioPlayback()
    try:
        audio.set_volume(0.1)
        audio.start(str(path), 1.5, 0, rate)
        assert not audio.error and audio.sink is not None
        assert audio.sink.format().sampleRate() == 48000
        def output_has_started():
            audio.pump()
            return audio.sink is not None and audio.sink.processedUSecs() > 20000
        qtbot.waitUntil(output_has_started, timeout=5000)
        assert not audio.error
        audio.set_volume(0)
        assert audio.sink.volume() == 0
        audio.stop()
        assert audio.sink is None and not audio._buffer
    finally:
        audio.close()

@pytest.mark.parametrize('pts', [None, [0, 40, 80, 160, 200, 320, 360, 400, 560, 600]])
def test_disk_proxy_preserves_timestamps_and_survives_reopen(tmp_path, pts, monkeypatch):
    from poptools.infrastructure.video_proxy import ScrubProxy
    path = make_video(tmp_path / 'proxy-source.mp4', pts=pts)
    directory = tmp_path / 'previews'
    proxy = ScrubProxy(str(path), directory)
    assert proxy.build(lambda: None)
    reopened = ScrubProxy(str(path), directory)
    reader = VideoReader(str(path))
    try:
        for target in (0.05, 0.18, 0.39, 0.57):
            actual = reopened.get(target)
            assert actual is not None
            assert actual.time == pytest.approx(reader.seek(target, lambda: None).time)
    finally:
        reader.close()
    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader',
                        lambda path: pytest.fail('Complete proxies must not decode again'))
    assert reopened.build(lambda: None)
    previous = reopened.path
    path.touch()
    assert ScrubProxy(str(path), directory).path != previous


def test_proxy_cancellation_resumes_and_cache_size_is_bounded(tmp_path):
    from poptools.infrastructure.video_media import Cancelled
    from poptools.infrastructure.video_proxy import ScrubProxy
    path = make_video(tmp_path / 'cancel.mp4')
    proxy = ScrubProxy(str(path), tmp_path / 'previews')
    checks = 0
    def cancel():
        nonlocal checks
        checks += 1
        if checks > 60:
            raise Cancelled()
    with pytest.raises(Cancelled):
        proxy.build(cancel)
    assert proxy.build(lambda: None)
    assert proxy.get(1.8) is not None
    capped = ScrubProxy(str(path), tmp_path / 'small-previews')
    capped.MAX_FILE_BYTES = 100
    assert not capped.build(lambda: None)
    assert capped.get(0.2) is None


def test_on_demand_proxy_preserves_gaps_and_reuses_bounded_neighborhoods(tmp_path):
    import sqlite3

    from poptools.infrastructure.video_proxy import ScrubProxy

    path = make_video(tmp_path / 'regions.mkv', pts=list(range(0, 8000, 40)))
    proxy = ScrubProxy(str(path), tmp_path / 'regions', on_demand=True)
    proxy.warm(5, lambda: None)
    assert proxy.get(5.1) is not None
    assert proxy.get(0.2) is None  # A late seek must not decode/cache the whole prefix.
    reopened = ScrubProxy(str(path), tmp_path / 'regions', on_demand=True)
    assert reopened.get(5.1) is not None
    assert reopened.covers(5, 7.5)
    assert not reopened.covers(0, 7.5)
    assert reopened.build(lambda: None)
    assert reopened.get(0.2) is not None  # Whole-clip construction must fill earlier gaps.
    reopened.MAX_FILE_BYTES = 20_000
    assert reopened.build(lambda: None, start=7, end=7.16)
    assert reopened.get(7.1) is not None
    with sqlite3.connect(reopened.path) as db:
        assert db.execute('SELECT SUM(LENGTH(jpeg)) FROM frames').fetchone()[0] <= 20_000
        assert db.execute('SELECT complete FROM state').fetchone() is None


def test_uncached_drag_remembers_preview_and_release_restores_native(qapp, qtbot, tmp_path,
                                                                   monkeypatch):
    from poptools.infrastructure.video_scrub import ScrubCache

    path = make_video(tmp_path / 'cold-drag.mp4', size=(1280, 720))
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        backend._cache_worker.cancel()
        backend._scrub_cache = ScrubCache(str(path))
        backend._cache_center = .8
        backend.beginScrub()
        backend.scrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 960
        seek = backend._decoder.reader.seek
        monkeypatch.setattr(backend._decoder.reader, 'seek',
                            lambda *a, **k: pytest.fail('Repeated drag must use cached preview'))
        backend.scrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.position == pytest.approx(.8)
        monkeypatch.setattr(backend._decoder.reader, 'seek', seek)
        backend.endScrub(.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1280
    finally:
        backend.shutdown()


def test_long_video_uses_neighborhoods_without_full_proxy_job(qapp, qtbot, tmp_path, monkeypatch):
    path = make_video(tmp_path / 'long-duration.mp4', size=(1280, 720))
    backend = VideoPreviewController(tmp_path / 'session')
    original_open = backend._decoder.open

    def open_long(*args):
        info, picture = original_open(*args)
        info['duration'] = 3600
        return info, picture

    monkeypatch.setattr(backend._decoder, 'open', open_long)
    monkeypatch.setattr(backend._proxy_worker, 'submit',
                        lambda *args: pytest.fail('Long movies must not start a whole-file proxy'))
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        assert backend._scrub_cache.proxy.on_demand
        assert not backend.previewOptimizing
        qtbot.waitUntil(lambda: backend._scrub_cache.proxy.get(.4) is not None, timeout=10000)
    finally:
        backend.shutdown()


def test_cached_drag_preempts_obsolete_slow_decode(qapp, qtbot, clip, monkeypatch):
    from poptools.infrastructure.video_scrub import ScrubCache

    backend = VideoPreviewController()
    started = threading.Event()
    try:
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend._cache_worker.cancel()
        cache = ScrubCache(str(clip))
        reader = VideoReader(str(clip))
        try:
            cache.put(reader.seek(.4, lambda: None))
        finally:
            reader.close()
        backend._scrub_cache = cache
        backend._cache_center = .8
        seek = backend._decoder.reader.seek

        def slow_seek(target, check, **kwargs):
            started.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                check()
                time.sleep(.005)
            return seek(target, check, **kwargs)

        monkeypatch.setattr(backend._decoder.reader, 'seek', slow_seek)
        backend.beginScrub()
        backend.scrub(1.2)
        qtbot.waitUntil(started.is_set)
        backend.scrub(.4)
        qtbot.waitUntil(lambda: not backend.busy, timeout=1000)
        assert backend.position == pytest.approx(.4)
        assert backend._queued_scrub is None
    finally:
        backend.shutdown()


def test_controller_uses_persistent_proxy_and_keeps_native_output(qapp, qtbot, tmp_path):
    path = make_video(tmp_path / 'hd.mp4', size=(1280, 720))
    backend = VideoPreviewController(tmp_path / 'session')
    try:
        backend.addFiles([str(path)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy, timeout=10000)
        qtbot.waitUntil(lambda: not backend.previewOptimizing, timeout=15000)
        assert backend._scrub_cache.proxy.get(1.8) is not None
        assert backend.images._live.width() == 1280
        backend.scrub(1.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 960
        assert backend.position == pytest.approx(1.8)
        backend.seek(1.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.images._live.width() == 1280
    finally:
        backend.shutdown()

@pytest.mark.parametrize('was_playing', [False, True])
def test_timeline_interaction_restores_prior_playback_state(qapp, qtbot, clip, was_playing):
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        if was_playing:
            backend.togglePlayback()
        backend.beginScrub()
        assert not backend.playing
        backend.scrub(0.4)
        backend.scrub(0.6)
        qtbot.waitUntil(lambda: not backend.busy)
        assert not backend.playing
        backend.endScrub(0.8)
        qtbot.waitUntil(lambda: not backend.busy)
        assert backend.playing == was_playing
        assert backend.position == pytest.approx(0.8, abs=0.04)
        if was_playing:
            qtbot.waitUntil(lambda: backend.position > 1.0)
    finally:
        backend.shutdown()


def test_explicit_pause_or_file_switch_cancels_scrub_resume(qapp, qtbot, clip, tmp_path):
    other = make_video(tmp_path / 'other-scrub.mp4')
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip), str(other)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        for cancel in (backend.pause, lambda: backend.selectVideo(1)):
            backend.togglePlayback()
            backend.beginScrub()
            backend.scrub(0.4)
            cancel()
            backend.endScrub(1.0)
            qtbot.waitUntil(lambda: not backend.busy)
            assert not backend.playing
        assert backend.fileName == other.name and backend.position == 0
    finally:
        backend.shutdown()


def test_scrubbing_to_end_does_not_restart_video(qapp, qtbot, clip):
    backend = VideoPreviewController()
    try:
        backend.addFiles([str(clip)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        backend.togglePlayback()
        backend.beginScrub()
        backend.endScrub(backend.duration)
        qtbot.waitUntil(lambda: not backend.busy and not backend.playing)
        assert backend.position == pytest.approx(1.96)
    finally:
        backend.shutdown()
