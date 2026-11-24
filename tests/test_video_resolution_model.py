"""Scrub busy notifications must not rebuild the resolution ComboBox model."""
import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.paths import package_root
from poptools.viewmodels.video_preview_controller import VideoPreviewController
from test_video_preview import make_video


@pytest.mark.gui
def test_scrubbing_keeps_resolution_model_stable_but_media_changes_refresh_it(
        qapp, qtbot, tmp_path):
    pts = [0, 40, 80, 120, 160, 200]
    hd = make_video(tmp_path / "hd.mp4", size=(1280, 720), pts=pts)
    full_hd = make_video(tmp_path / "full-hd.mp4", size=(1920, 1080), pts=pts)
    backend = VideoPreviewController()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("videoBackend", backend)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 650; height: 100; visible: true
    VideoToolbar {
        anchors.centerIn: parent
        controller: videoBackend
        mode: "playback"
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ResolutionModelTest.qml")))
    window = component.create()
    try:
        assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
        assert QTest.qWaitForWindowExposed(window)
        selector = window.findChild(QObject, "videoResolutionSelector")
        backend.addFiles([str(hd), str(full_hd)])
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert selector.property("count") == 2
        models, options, state = [], [], []
        selector.modelChanged.connect(lambda: models.append(True))
        backend.resolutionOptionsChanged.connect(lambda: options.append(True))
        backend.changed.connect(lambda: state.append(True))
        backend.beginScrub()
        for index in range(20):
            backend.scrub((index % 5) * .04)
            qtbot.waitUntil(lambda: not backend.busy)
        backend.endScrub(.16)
        qtbot.waitUntil(lambda: not backend.busy)
        assert len(state) >= 20  # Exercise the frequent notifications that caused churn.
        assert not models and not options
        backend.setResolution(720)
        qtbot.waitUntil(lambda: not backend.busy)
        assert selector.property("currentIndex") == 1
        assert not models and not options  # Selection changes only the selected index.

        backend.selectVideo(1)
        qtbot.waitUntil(lambda: backend.loaded and not backend.busy)
        assert models and options
        assert selector.property("count") == 3
        assert selector.property("currentIndex") == 0
        assert [row["value"] for row in backend.resolutionOptions] == [0, 720, 1080]
        backend.removeVideo(0)
        backend.removeVideo(0)
        assert not backend.loaded
        assert selector.property("count") == 1
        assert [row["value"] for row in backend.resolutionOptions] == [0]
    finally:
        backend.shutdown()
        if window:
            window.close()
            window.deleteLater()
        engine.deleteLater()
