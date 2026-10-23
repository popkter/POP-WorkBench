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


def make_video(path, pts=None, audio=False):
    pts = pts or list(range(0, 2000, 40))
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=25)
        stream.width, stream.height = 320, 180
        stream.pix_fmt = "yuv420p"
        stream.time_base = Fraction(1, 1000)
        stream.codec_context.time_base = Fraction(1, 1000)
        stream.codec_context.max_b_frames = 2
        stream.codec_context.gop_size = 12
        sound = output.add_stream("aac", rate=48000) if audio else None
        if sound:
            sound.layout = "stereo"
        for i, timestamp in enumerate(pts):
            image = Image.new("RGB", (320, 180), (20 + i * 3 % 220, 40, 90))
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
                frame.planes[0].update(bytes(1920 * 4))
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


def test_audio_resampling_trims_to_seek_and_stays_bounded(qapp, tmp_path):
    clip = make_video(tmp_path / "with-audio.mp4", audio=True)
    audio = AudioPlayback()
    try:
        audio._decode(str(clip), 1.5, 0, lambda: None)
        assert audio._finished
        # Half a second plus AAC encoder padding, in interleaved stereo PCM.
        assert 24000 * 4 <= len(audio._buffer) <= 26000 * 4
        assert len(audio._buffer) <= audio.RATE * audio.BYTES_PER_SAMPLE
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
        playhead = window.findChild(QObject, "videoTimelinePlayhead")
        assert playhead.property("visible")
        grab = QPoint(round(bounds.x() + playhead.x()), round(bounds.y() + 23))
        destination = QPoint(at(0.35).x(), grab.y())
        previous_frame = backend.frameSource
        QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=grab)
        QTest.mouseMove(window, destination, delay=50)
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
