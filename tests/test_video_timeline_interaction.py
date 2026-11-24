"""Timeline input stays responsive independently of decoder latency."""
import pytest
from PySide6.QtCore import (
    QCoreApplication,
    QEvent,
    QEventLoop,
    QMetaObject,
    QObject,
    QPoint,
    Qt,
    QTimer,
    QUrl,
)
from PySide6.QtGui import QMouseEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.fixture
def timeline(qapp):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 900; height: 480; visible: true
    QtObject {
        id: backend
        objectName: "timelineBackend"
        property real duration: 60
        property real nominalFps: 25
        property real position: 1
        property bool loaded: true
        property bool busy: false
        property bool playing: false
        property bool detailed: false
        property real rate: 1
        property real volume: 1
        property int resolution: 0
        property var resolutionOptions: []
        property var thumbnails: []
        property var playlist: []
        property string fileName: "Timeline test"
        property bool listVisible: false
        property bool previewOptimizing: false
        property real previewTarget: 0
        property real previewTime: 0
        property string previewSource: ""
        property bool previewBusy: false
        property real requested: -1
        property real released: -1
        property int scrubCount: 0
        property int thumbnailRequests: 0
        property int previewRequests: 0
        signal changed()
        signal fitRequested()
        signal zoomRequested(real factor)
        function beginScrub() { busy = true; changed() }
        function scrub(target) { requested = target; scrubCount++; busy = true; changed() }
        function endScrub(target) { released = target; busy = true; changed() }
        function settle() { position = released; busy = false; changed() }
        function requestThumbnails(start, end, scale) { thumbnailRequests++ }
        function requestPreview(target) { previewTarget = target; previewRequests++ }
        function clearPreview() { }
    }
    VideoTimeline {
        objectName: "timeline"
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        anchors.margins: 16; height: implicitHeight
        controller: backend
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/TimelineInteractionTest.qml")))
    window = component.create()
    try:
        assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
        assert QTest.qWaitForWindowExposed(window)
        QTest.qWait(30)
        root = window.findChild(QObject, "timeline")
        backend = window.findChild(QObject, "timelineBackend")
        track = window.findChild(QObject, "videoTimelineTrack")
        bounds = track.mapRectToItem(window.contentItem(), track.boundingRect())
        def point(fraction):
            return QPoint(round(bounds.x() + bounds.width() * fraction), round(bounds.y() + 40))
        yield window, root, backend, track, point
    finally:
        if window:
            QTest.mouseRelease(window, Qt.MouseButton.LeftButton)
            window.close()
            window.deleteLater()
        engine.deleteLater()


def test_pointer_and_timecode_follow_mouse_while_decoder_is_busy(timeline):
    window, root, backend, track, point = timeline
    playhead = window.findChild(QObject, "videoTimelinePlayhead")
    readout = window.findChild(QObject, "videoTimelineTimecode")
    popup = window.findChild(QObject, "videoHoverPreview")
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.1))
    for fraction in [.8, .2, .95, .35] * 3:
        QTest.mouseMove(window, point(fraction), delay=0)
        expected_x = point(fraction).x() - track.mapToScene(track.boundingRect().topLeft()).x()
        assert playhead.property("x") == pytest.approx(expected_x, abs=1)
        assert backend.property("position") == 1  # Decoder has not returned any frame.
        assert readout.property("text").split(" / ")[0] != "00:01.000"
        assert not popup.property("visible")
    assert root.property("dragTime") > 0


def test_release_uses_release_coordinate_and_holds_until_frame_arrives(timeline):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.2))
    # Release at a different coordinate without waiting for the scrub timer.
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point(.75))
    expected = (point(.75).x() - track.mapToScene(track.boundingRect().topLeft()).x())
    expected /= root.property("pixelsPerSecond")
    assert backend.property("released") == pytest.approx(expected)
    assert root.property("playheadTime") == pytest.approx(expected)
    QMetaObject.invokeMethod(backend, "settle")
    assert root.property("dragTime") == -1
    assert root.property("playheadTime") == pytest.approx(expected)


def test_cancel_keeps_requested_position_until_final_frame(timeline):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.2))
    QTest.mouseMove(window, point(.7), delay=0)
    expected = root.property("playheadTime")
    window.findChild(QObject, "videoTimelinePointer").ungrabMouse()
    assert backend.property("released") == pytest.approx(expected)
    assert root.property("playheadTime") == pytest.approx(expected)
    QMetaObject.invokeMethod(backend, "settle")
    assert root.property("playheadTime") == pytest.approx(expected)


def test_hover_move_during_release_seek_is_served_after_frame_arrives(timeline, qtbot):
    window, root, backend, _, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.2))
    QTest.mouseMove(window, point(.6), delay=0)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point(.6))
    QTest.mouseMove(window, point(.8), delay=0)
    assert backend.property("busy") and root.property("hovering")
    assert root.property("dragTime") >= 0
    target = root.property("hoverTime")
    assert backend.property("previewRequests") == 0

    QMetaObject.invokeMethod(backend, "settle")
    qtbot.waitUntil(lambda: backend.property("previewRequests") == 1)
    assert backend.property("previewTarget") == pytest.approx(target)


def test_drag_defers_thumbnails_and_hover_requests(timeline, qtbot):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.2))
    count = backend.property("thumbnailRequests")
    root.setProperty("pixelsPerSecond", root.property("pixelsPerSecond") * 2)
    qtbot.wait(160)
    assert backend.property("thumbnailRequests") == count
    assert backend.property("previewRequests") == 0
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point(.4))
    qtbot.waitUntil(lambda: backend.property("thumbnailRequests") > count)


def test_drag_clamps_at_video_boundaries(timeline):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.2))
    QTest.mouseMove(window, point(-.01), delay=0)
    assert root.property("playheadTime") == 0
    QTest.mouseMove(window, point(1.01), delay=0)
    assert root.property("playheadTime") == pytest.approx(60, abs=.001)


def test_duration_probe_and_view_pan_do_not_detach_pointer(timeline):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.4))
    root.setProperty("pixelsPerSecond", root.property("pixelsPerSecond") * 2)
    root.setProperty("viewStart", 10)
    playhead = window.findChild(QObject, "videoTimelinePlayhead")
    expected_x = point(.4).x() - track.mapToScene(track.boundingRect().topLeft()).x()
    assert playhead.property("x") == pytest.approx(expected_x, abs=1)
    backend.setProperty("duration", 65)
    assert playhead.property("x") == pytest.approx(expected_x, abs=1)
    assert root.property("viewStart") == 10


def test_hover_preview_never_covers_timeline_in_short_window(timeline, qtbot):
    window, root, backend, track, point = timeline
    window.setHeight(240)
    qtbot.wait(30)
    bounds = track.mapRectToItem(window.contentItem(), track.boundingRect())
    target = QPoint(round(bounds.center().x()), round(bounds.y() + 40))
    QTest.mouseMove(window, target, delay=0)
    popup = window.findChild(QObject, "videoHoverPreview")
    if popup.property("visible"):
        assert popup.property("y") + popup.property("height") < bounds.y()
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=target)
    assert backend.property("busy")
    assert root.property("dragTime") >= 0


def test_continuous_moves_are_submitted_without_an_extra_timer_tick(timeline):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.1))
    initial = backend.property("scrubCount")
    moves = [0]
    swaps = [0]
    loop = QEventLoop()
    move_timer = QTimer()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    def swapped():
        swaps[0] += 1
    def move():
        moves[0] += 1
        QTest.mouseMove(window, point(.1 + .8 * moves[0] / 60), delay=0)
        if moves[0] == 60:
            move_timer.stop()
            loop.quit()
    window.frameSwapped.connect(swapped)
    move_timer.timeout.connect(move)
    move_timer.start(16)
    deadline.start(4000)
    try:
        loop.exec()
        dispatches = backend.property("scrubCount") - initial
        assert moves[0] == 60
        # A one-shot 16 ms timer falls into a two-animation-tick cadence (~30 Hz).
        # Next-turn dispatch should preserve at least 3/4 of 60 Hz input.
        assert dispatches >= 45
    finally:
        move_timer.stop()
        deadline.stop()
        window.frameSwapped.disconnect(swapped)


def test_move_burst_submits_only_latest_target_and_release_discards_pending(timeline, qtbot):
    window, root, backend, track, point = timeline
    QTest.mousePress(window, Qt.MouseButton.LeftButton, pos=point(.1))
    initial = backend.property("scrubCount")
    # QTest.mouseMove may pump events even with delay=0, splitting a large loop
    # across render ticks. Direct delivery keeps this entire burst in one batch.
    for index in range(100):
        position = point(.2 + .6 * index / 99)
        event = QMouseEvent(QEvent.Type.MouseMove, position, window.mapToGlobal(position),
                            Qt.MouseButton.NoButton, Qt.MouseButton.LeftButton,
                            Qt.KeyboardModifier.NoModifier)
        QCoreApplication.sendEvent(window, event)
    assert backend.property("scrubCount") == initial
    latest = root.property("playheadTime")
    qtbot.waitUntil(lambda: backend.property("scrubCount") > initial)
    assert backend.property("scrubCount") == initial + 1
    assert backend.property("requested") == pytest.approx(latest)
    QTest.mouseMove(window, point(.5), delay=0)
    QTest.mouseRelease(window, Qt.MouseButton.LeftButton, pos=point(.6))
    assert not root.property("scrubPending")
    count = backend.property("scrubCount")
    qtbot.wait(80)
    assert backend.property("scrubCount") == count
