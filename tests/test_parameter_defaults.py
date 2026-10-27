from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPointF, Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.domain.models import ParameterKind, ToolDefinition
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, package_root
from poptools.viewmodels.app_controller import AppController

TEXT_KINDS = ["text", "file", "directory", "multiline", "integer", "number", "secret"]


@pytest.mark.parametrize("kind", TEXT_KINDS)
@pytest.mark.parametrize("value", ["", "new value", "first\nsecond {literal}"])
def test_defaults_persist_without_changing_other_parameters(tmp_path, kind, value):
    if kind in ("integer", "number") and value:
        value = "3" if kind == "integer" else "0.5"
    repository = JsonToolRepository(AppPaths(tmp_path / "data"))
    registry = ToolRegistry(tmp_path / "builtin", repository)
    tool = ToolDefinition.model_validate({
        "id": "custom.test", "title": "Test", "origin": "custom", "section": "custom",
        "editable": True,
        "executor": {"kind": "powershell", "command": "echo ${first} ${second}"},
        "parameters": [
            {"id": "first", "label": "First", "kind": kind, "default": "old"},
            {"id": "second", "label": "Second", "default": "keep"},
        ],
    })
    repository.save_tool(tool)
    registry.reload()
    registry.set_parameter_default(tool.id, "first", value)
    restored = ToolRegistry(tmp_path / "builtin", repository).get(tool.id)
    assert restored.parameters[0].default == value
    assert restored.parameters[0].kind == ParameterKind(kind)
    assert restored.parameters[1].default == "keep"


@pytest.mark.parametrize("command", ['echo "${令牌@secret}"',
                                     'Var token = ${令牌@secret}\necho "${token}"'])
def test_secret_default_can_be_saved(tmp_path, command):
    repository = JsonToolRepository(AppPaths(tmp_path / "data"))
    registry = ToolRegistry(tmp_path / "builtin", repository)
    tool = registry.create_custom(title="Secret", description="", kind="powershell",
                                  command=command)
    from poptools.infrastructure.custom_tool_transfer import encode_custom_tool

    parameter_id = tool.parameters[0].id
    registry.set_parameter_default(tool.id, parameter_id, "private-token")
    restored = ToolRegistry(tmp_path / "builtin", repository).get(tool.id)
    assert restored.parameters[0].default == "private-token"
    assert "@secret:private-token" in restored.executor.command
    assert "private-token" not in encode_custom_tool(restored)
    registry.set_parameter_default(tool.id, parameter_id, "")
    assert registry.get(tool.id).parameters[0].default == ""


@pytest.mark.parametrize("kind,value", [("integer", "1.5"), ("number", "NaN")])
def test_invalid_numeric_default_is_not_persisted(tmp_path, kind, value):
    repository = JsonToolRepository(AppPaths(tmp_path / "data"))
    registry = ToolRegistry(tmp_path / "builtin", repository)
    tool = registry.create_custom(title="Number", description="", kind="powershell",
                                  command="echo ${值@" + kind + ":3}")
    with pytest.raises(ValueError):
        registry.set_parameter_default(tool.id, "值", value)
    assert registry.get(tool.id).parameters[0].default == "3"


def test_builtin_default_is_saved_as_local_override(tmp_path):
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    source = builtin / "tool.json"
    original = ('{"id":"preset.test","title":"Test","section":"preset","editable":false,'
                '"executor":{"kind":"process","command":"echo","args":["${path}"]},'
                '"parameters":[{"id":"path","label":"Path","kind":"directory"}]}')
    source.write_text(original, encoding="utf-8")
    registry = ToolRegistry(builtin, JsonToolRepository(AppPaths(tmp_path / "data")))
    updated = registry.set_parameter_default("preset.test", "path", "D:/folder")
    assert updated.origin.value == "override"
    assert updated.parameters[0].default == "D:/folder"
    assert source.read_text(encoding="utf-8") == original


def test_controller_save_does_not_reset_form():
    updated = SimpleNamespace(id="tool")
    controller = SimpleNamespace(
        _selected=SimpleNamespace(id="tool"), running=False,
        registry=SimpleNamespace(set_parameter_default=lambda *args: updated),
        _append_console=lambda message: None,
        append_tool_console=lambda *args: None,
        execution_coordinator=SimpleNamespace(running=lambda _: False),
    )
    controller.update_tool_parameter_default = lambda *args: (
        AppController.update_tool_parameter_default(controller, *args)
    )
    # No refresh method: saving must not notify a tool selection change.
    assert AppController.setParameterDefault(controller, "path", "new")
    assert controller._selected is updated


@pytest.mark.gui
@pytest.mark.parametrize("kind", TEXT_KINDS)
@pytest.mark.parametrize("surface", ["CommandWorkspace", "CustomToolDetailPanel"])
def test_text_parameter_save_button(qapp, kind, surface):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        ('''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 700; height: 700; visible: true
    property string savedId: ""
    property string savedValue: "unset"
    SURFACE {
        anchors.fill: parent
        EXTRA_PROPERTIES
        parentWindow: host
        parameterValues: ({})
        controller: ({
            selectedTool: {parameters: [
                {id: "input", label: "Input", kind: "KIND", default: "old"}
            ]},
            running: false,
            consoleText: "", statusText: "",
            updateScrcpyGeometry: function() {},
            setParameterDefault: function(id, value) {
                host.savedId = id; host.savedValue = value; return true
            }
        })
    }
}
'''.replace("KIND", kind).replace("SURFACE", surface).replace(
            "EXTRA_PROPERTIES",
            "androidBackend: null; displayedTool: controller.selectedTool"
            if surface == "CustomToolDetailPanel" else "",
        )).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/DefaultsHarness.qml")),
    )
    root = component.create()
    assert isinstance(root, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(root)

        def items(item):
            yield item
            for child in item.childItems():
                yield from items(child)

        button = next(item for item in items(root.contentItem())
                      if item.property("text") == "设为默认值"
                      and item.metaObject().indexOfMethod("clicked()") >= 0)
        assert button.isVisible()
        field = button.parentItem()
        for value in ["new value", ""]:
            field.setProperty("text", value)
            position = button.mapToScene(QPointF(button.width() / 2, button.height() / 2))
            QTest.mouseClick(root, Qt.MouseButton.LeftButton, pos=position.toPoint())
            assert root.property("savedId") == "input"
            assert root.property("savedValue") == value
        if kind in ("file", "directory"):
            picker = next(item for item in field.childItems()
                          if item.property("text") in ("选择文件", "选择文件夹")
                          and item.metaObject().indexOfMethod("clicked()") >= 0)
            assert button.x() + button.width() <= picker.x()
            assert picker.isVisible()
    finally:
        root.close()
        root.deleteLater()
