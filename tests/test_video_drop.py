import pytest
from PySide6.QtCore import QCoreApplication, QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.paths import package_root
from poptools.viewmodels.video_preview_controller import VideoPreviewController


@pytest.mark.parametrize('suffix', ['.mp4', '.txt'])
@pytest.mark.parametrize('kind', ['text', 'multiline'])
@pytest.mark.parametrize('start,end', [((20, 20), (20, 20)), ((20, 20), (150, 150)),
                                      ((150, 150), (20, 20)), ((150, 150), (150, 150))])
def test_video_drop_routes_around_parameter_editor(qapp, tmp_path, start, end, suffix, kind):
    path = tmp_path / ('test file' + suffix)
    path.touch()
    backend = VideoPreviewController()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty('videoBackend', backend)
    engine.rootContext().setContextProperty('parameterKind', kind)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 600; height: 400; visible: true
    property int opened: 0
    readonly property string pathText: field.item ? field.item.text : ""
    QtObject { id: parameterBackend; property bool running: false }
    ParameterField {
        id: field
        x: 100; y: 100; width: 200; height: 100
        parameter: ({ id: "input", label: "Input", kind: parameterKind, default: "" })
        controller: parameterBackend
        parameterValues: ({})
    }
    ApplicationVideoDropArea {
        parent: Overlay.overlay
        controller: videoBackend
        hitTestRoot: host.contentItem
        onVideoDropped: urls => host.opened++
    }
}
''', QUrl.fromLocalFile(str(package_root() / 'ui/qml/DropHarness.qml')))
    window = component.create()
    try:
        assert window, [e.toString() for e in component.errors()]
        assert QTest.qWaitForWindowExposed(window)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        enter = QDragEnterEvent(QPoint(*start), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QCoreApplication.sendEvent(window, enter)
        move = QDragMoveEvent(QPoint(*end), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QCoreApplication.sendEvent(window, move)
        drop = QDropEvent(QPointF(*end), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        QCoreApplication.sendEvent(window, drop)
        in_field = end == (150, 150)
        assert drop.isAccepted() == (in_field or suffix == '.mp4')
        assert window.property('opened') == (1 if not in_field and suffix == '.mp4' else 0)
        assert window.property('pathText') == (str(path) if in_field else '')
    finally:
        if window:
            window.close()
            window.deleteLater()
        backend.shutdown()
