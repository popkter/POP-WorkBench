"""The shared output must remain stable when switching custom scripts."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMetaObject, QObject, QRect, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QSignalSpy, QTest

from poptools.domain.models import ExecutorDefinition, ToolDefinition
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, package_root
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.app_controller import AppController


@pytest.fixture
def workspace(qapp, tmp_path, request):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    tools = [ToolDefinition(
        id=f"custom.{index}", section="custom", title=f"Script {index}",
        executor=ExecutorDefinition(kind="python", command="print('hello')"),
    ) for index in range(2)]
    registry = ToolRegistry(tmp_path / "builtin", SimpleNamespace(list_tools=lambda: tools))
    coordinator = ExecutionCoordinator(ExecutionManager(paths, PythonEnvironment(paths, store)), 3)
    if getattr(request, "param", False):
        coordinator.running = lambda tool_id: tool_id == tools[0].id
    android = AndroidController(store)
    android.stopAutoRefresh()
    backend = AppController(registry, coordinator, store, android)
    backend._analysis_timer.stop()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", backend)
    engine.rootContext().setContextProperty("android", android)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host; width: 1100; height: 800; visible: true
    CustomScriptsPage {
        anchors.fill: parent; controller: backend; androidBackend: android
        parentWindow: host; parameterValues: ({})
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ConsoleSelectionHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        yield window, backend, tools
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
        backend._console_refresh_timer.stop()
        backend.deleteLater()
        android.deleteLater()
        coordinator.deleteLater()


@pytest.mark.parametrize("workspace", [False, True], indirect=True,
                         ids=["manual-expand", "already-running"])
def test_switching_scripts_preserves_expanded_console(workspace, qtbot):
    window, backend, tools = workspace
    panel = window.findChild(QObject, "customToolDetailPanel")
    scroll = window.findChild(QObject, "customConsoleScroll")
    output = window.findChild(QObject, "customConsoleText")
    assert output.property("text") == backend.consoleText
    toggle = window.findChild(QObject, "customConsoleToggle")
    if not panel.property("consoleExpanded"):
        assert QMetaObject.invokeMethod(toggle, "clicked")
    backend.console_store.append("", "".join(f"Output line {index}\n" for index in range(1000)))
    qtbot.waitUntil(lambda: panel.property("consoleReveal") == 1)
    qtbot.wait(100)
    flickable = scroll.property("contentItem")
    # Include reading older output, where an unwanted jump to the tail is obvious.
    flickable.setProperty("contentY", 240)
    qtbot.wait(50)
    before = window.grabWindow()
    logical_rect = scroll.mapRectToItem(window.contentItem(), scroll.boundingRect())
    scale = before.devicePixelRatio()
    rect = QRect(round(logical_rect.x() * scale), round(logical_rect.y() * scale),
                 round((logical_rect.width() - 20) * scale), round(logical_rect.height() * scale))
    before = before.copy(rect)
    notifications = QSignalSpy(backend.consoleTextChanged)
    text_changes = QSignalSpy(output.textChanged)
    positions = []
    flickable.contentYChanged.connect(lambda: positions.append(flickable.property("contentY")))

    def find_item(item, name):
        if item.objectName() == name:
            return item
        for child in item.childItems():
            found = find_item(child, name)
            if found is not None:
                return found
        return None

    for index in range(10):
        tool = tools[index % 2]
        row = find_item(window.contentItem(), "scriptRow_" + tool.id)
        assert row is not None
        point = row.mapRectToItem(window.contentItem(), row.boundingRect()).center().toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
        assert backend.selectedTool["id"] == tool.id
        assert window.grabWindow().copy(rect) == before, (text_changes.count(), positions)
        qtbot.wait(25)
        assert panel.property("consoleReveal") == 1
        assert window.grabWindow().copy(rect) == before, (text_changes.count(), positions)
    assert text_changes.count() == 0
    assert not positions
    assert notifications.count() == 0


def test_output_appends_without_replacing_document_and_handles_clear_and_trim(workspace, qtbot):
    window, backend, tools = workspace
    output = window.findChild(QObject, "customConsoleText")
    toggle = window.findChild(QObject, "customConsoleToggle")
    panel = window.findChild(QObject, "customToolDetailPanel")
    assert QMetaObject.invokeMethod(toggle, "clicked")
    qtbot.waitUntil(lambda: panel.property("consoleReveal") == 1)
    backend.clearConsole()
    backend.console_store.append("", "<b>literal output</b>\r\n" * 100)
    quick_document = output.property("textDocument")
    document = quick_document.textDocument()
    assert document.toPlainText().startswith("<b>literal output</b>\n")
    changes = QSignalSpy(document.contentsChange)
    for index in range(10):
        backend.selectTool(tools[index % 2].id)
        backend.console_store.append("", f"next {index}\r\n")
        qtbot.wait(20)
    assert changes.count() > 0
    assert all(changes.at(index)[1] == 0 for index in range(changes.count()))
    assert document.toPlainText().endswith("next 9\n")
    backend.console_store.append("", "z" * (backend.console_store.MAX_CHARS + 1))
    assert document.toPlainText() == "z" * backend.console_store.RETAINED_CHARS
    backend.clearConsole()
    assert document.toPlainText() == ""
    backend.console_store.append("", "new output\n")
    assert document.toPlainText() == "new output\n"
