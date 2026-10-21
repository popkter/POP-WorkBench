import json

import pytest
from PySide6.QtCore import Qt, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.domain.models import ParameterDefinition, ParameterKind, ToolDefinition
from poptools.domain.parameter_templates import (
    extract_parameter_ids,
    render_template,
    strip_parameter_defaults,
    synchronize_parameters,
    update_parameter_default,
    validate_parameter_value,
)
from poptools.paths import AppPaths, package_root
from poptools.runners.execution_manager import ExecutionManager


@pytest.mark.parametrize("definition,kind,default", [
    ("名称@text:示例", "text", "示例"),
    ("说明@multiline", "multiline", ""),
    ("重试次数@integer:3", "integer", "3"),
    ("比例@number:0.5", "number", "0.5"),
    ("启用缓存@boolean:true", "boolean", True),
    ("启用缓存@boolean:false", "boolean", False),
    ("启用缓存@boolean", "boolean", False),
    ("模式@choice:开启=1|关闭=0", "choice", "1"),
    ("环境@radio:开发=dev|生产=prod", "radio", "dev"),
    ("输入文件@file:./input.txt", "file", "./input.txt"),
    ("输出目录@dir:./output", "directory", "./output"),
    ("访问令牌@secret", "secret", ""),
    ("访问令牌@secret:private", "secret", "private"),
    ("名称:示例", "text", "示例"),
    ("名称=示例", "text", "示例"),
    ("模式:开启=1|关闭=0", "choice", "1"),
    ("开启=1|关闭=0", "choice", "1"),
])
def test_new_and_legacy_syntax(definition, kind, default):
    template = "${" + definition + "}"
    parameter, = synchronize_parameters([template])
    assert parameter.kind == ParameterKind(kind)
    assert parameter.default == default
    assert render_template(template, {}) == (
        str(default).lower() if isinstance(default, bool) else default
    )
    assert extract_parameter_ids([template]) == [parameter.id]


@pytest.mark.parametrize("kind", ["text", "multiline", "secret"])
def test_explicit_text_is_not_inferred_as_a_choice(kind):
    template = "${值@" + kind + "}"
    value = "one=1|two=2\nnext {literal}"
    assert render_template(template, {"值": value}) == value
    parameter, = synchronize_parameters(["${值@" + kind + ":one=1|two=2}"])
    assert parameter.kind.value == kind
    assert parameter.default == "one=1|two=2"


def test_boolean_rendering_preserves_legacy_untyped_values():
    assert render_template("${值}", {"值": True}) == "True"
    assert render_template("${值@boolean}", {"值": True}) == "true"


@pytest.mark.parametrize("prefix", ["Var value = ", "var value=", "VAR value: ", "pVal value: "])
@pytest.mark.parametrize("kind,definition,expected", [
    ("integer", "3", "3"), ("boolean", "false", "false"),
    ("radio", "开发=dev|生产=prod", "dev"),
])
def test_declarations_and_bare_references(prefix, kind, definition, expected):
    template = prefix + "${标题@" + kind + ":" + definition + "}\necho ${value} ${value}"
    parameter, = synchronize_parameters([template])
    assert parameter.id == "value" and parameter.label == "标题"
    assert parameter.kind.value == kind
    assert render_template(template, {}) == f"echo {expected} {expected}"


@pytest.mark.parametrize("template", [
    "${value@integer:3} ${value}", "${value} ${value@integer:3}",
    "Var value = ${标题@integer:3}\necho ${value}",
])
def test_saving_typed_defaults_preserves_type_and_references(template):
    updated = update_parameter_default(template, "value", "0")
    parameter, = synchronize_parameters([updated])
    assert parameter.kind == ParameterKind.INTEGER and parameter.default == "0"
    assert render_template(updated, {}) == ("echo 0" if "Var" in template else "0 0")
    stripped, = synchronize_parameters([strip_parameter_defaults(updated)])
    assert stripped.kind == ParameterKind.INTEGER
    assert synchronize_parameters([update_parameter_default(updated, "value", "")])[0].default == ""


@pytest.mark.parametrize("definition", [
    "值@unknown", "值@choice", "值@radio:开发", "值@choice:a=1|a=2",
    "值@integer:0.5", "值@number:NaN", "值@boolean:yes",
])
def test_invalid_definitions_are_rejected(definition):
    with pytest.raises(ValueError):
        synchronize_parameters(["${" + definition + "}"])


@pytest.mark.parametrize("template", [
    "${值@integer:3} ${值@number:3}",
    "${值@integer:3} ${值@integer:4}",
    "${值@choice:a=1|b=2} ${值@choice:a=1|c=2}",
])
def test_conflicting_definitions_are_rejected(template):
    with pytest.raises(ValueError):
        synchronize_parameters([template])


@pytest.mark.parametrize("kind", list(ParameterKind))
def test_explicit_text_resets_existing_metadata_kind(kind):
    existing = [ParameterDefinition(id="值", label="Value", kind=kind)]
    parameter, = synchronize_parameters(["${值@text:普通内容}"], existing)
    assert parameter.kind == ParameterKind.TEXT
    assert not parameter.options


def test_typed_controls_survive_save_reload_and_sharing(tmp_path):
    from poptools.infrastructure.custom_tool_transfer import decode_custom_tool, encode_custom_tool
    from poptools.infrastructure.json_tool_repository import JsonToolRepository
    from poptools.infrastructure.tool_registry import ToolRegistry

    repository = JsonToolRepository(AppPaths(tmp_path))
    registry = ToolRegistry(tmp_path / "builtin", repository)
    command = ("${名称@text:示例} ${说明@multiline} ${次数@integer:3} ${比例@number:0.5} "
               "${开关@boolean:false} ${模式@choice:开启=1|关闭=0} "
               "${环境@radio:开发=dev|生产=prod} ${文件@file:./input.txt} "
               "${目录@dir:./output} ${令牌@secret:private-token}")
    tool = registry.create_custom(title="Test", description="", kind="powershell", command=command)
    restored = ToolRegistry(tmp_path / "builtin", repository).get(tool.id)
    assert restored == tool
    encoded = encode_custom_tool(restored)
    assert "private-token" not in encoded
    shared = decode_custom_tool(encoded)
    parameters = synchronize_parameters([shared.executor.command])
    assert [p.kind for p in parameters] == [p.kind for p in tool.parameters]
    assert all(p.default in ("", False) for p in parameters
               if p.kind not in (ParameterKind.CHOICE, ParameterKind.RADIO))
    assert parameters[5].options == tool.parameters[5].options
    assert parameters[6].options == tool.parameters[6].options


@pytest.mark.parametrize("kind,value,valid", [
    ("integer", "-3", True), ("integer", "0", True), ("integer", "1.5", False),
    ("integer", "abc", False), ("integer", True, False),
    ("number", "0.5", True), ("number", "-1e3", True), ("number", ".5", True),
    ("number", "inf", False), ("number", "NaN", False), ("number", "1_000", False),
    ("boolean", "false", True), ("boolean", False, True), ("boolean", "0", False),
])
def test_value_validation(kind, value, valid):
    parameter = ParameterDefinition(id="value", label="值", kind=kind)
    if valid:
        result = validate_parameter_value(parameter, value)
        assert result is False if kind == "boolean" else result == value
    else:
        with pytest.raises(ValueError):
            validate_parameter_value(parameter, value)


def test_execution_rejects_invalid_input_before_launch(qapp, tmp_path, monkeypatch):
    manager = ExecutionManager(AppPaths(tmp_path))
    tool = ToolDefinition(id="custom.test", title="Test", section="custom",
                          executor={"kind": "powershell", "command": "echo ${次数@integer:3}"},
                          parameters=synchronize_parameters(["${次数@integer:3}"]))
    output = []
    manager.output.connect(output.append)
    monkeypatch.setattr(manager, "_build_launch", lambda *args: pytest.fail("must not launch"))
    assert not manager.start(tool, {"次数": "1.5"})
    assert "整数" in "".join(output)
    assert not manager.active


@pytest.mark.parametrize("surface", ["CommandWorkspace", "CustomToolDetailPanel"])
def test_typed_controls_and_radio_selection(qapp, surface):
    parameters = synchronize_parameters([
        "${环境@radio:开发=dev|生产=prod} ${开关@boolean:false} "
        "${整数@integer:0} ${数字@number:0} ${密码@secret} ${说明@multiline}"
    ])
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    source = '''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 700; height: 900; visible: true
    property var values: ({})
    SURFACE {
        anchors.fill: parent
        EXTRA_PROPERTIES
        parentWindow: host
        parameterValues: host.values
        controller: ({
            selectedTool: {parameters: PARAMETERS}, running: false,
            consoleText: "", statusText: "", updateScrcpyGeometry: function() {}
        })
    }
}
'''.replace("SURFACE", surface).replace("EXTRA_PROPERTIES",
        "androidBackend: null; displayedTool: controller.selectedTool"
        if surface == "CustomToolDetailPanel" else "").replace(
            "PARAMETERS", json.dumps([p.model_dump(mode="json") for p in parameters]))
    component.setData(source.encode(), QUrl.fromLocalFile(
        str(package_root() / "ui/qml/TypedParametersHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        QTest.qWait(30)

        def items(item):
            yield item
            for child in item.childItems():
                yield from items(child)

        controls = list(items(window.contentItem()))
        values = window.property("values").toVariant()
        assert values["环境"] == "dev" and values["开关"] is False
        assert values["整数"] == "0" and values["数字"] == "0"
        radio = next(item for item in controls if item.property("text") == "生产")
        point = radio.mapToScene(radio.boundingRect().center()).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
        assert window.property("values").toVariant()["环境"] == "prod"
        developer = next(item for item in controls if item.property("text") == "开发")
        assert not developer.property("checked") and radio.property("checked")
        checkbox = next(item for item in controls
                        if item.metaObject().indexOfProperty("tristate") >= 0)
        point = checkbox.mapToScene(checkbox.boundingRect().center()).toPoint()
        QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)
        assert window.property("values").toVariant()["开关"] is True
        password = next(item for item in controls
                        if item.property("placeholderText") == "请输入密码")
        password.setProperty("text", "private-token")
        assert password.property("displayText") != "private-token"
        assert any(child.isVisible() for child in password.childItems()
                       if child.property("text") == "设为默认值")
        multiline = next(item for item in controls
                         if item.property("placeholderText") == "请输入说明")
        multiline.setProperty("text", "first\nsecond")
        assert window.property("values").toVariant()["说明"] == "first\nsecond"
        number_fields = [item for item in controls if item.property("text") == "0"
                         and item.metaObject().indexOfProperty("acceptableInput") >= 0]
        assert len(number_fields) == 2
        for field in number_fields:
            field.setProperty("text", "abc")
            assert not field.property("acceptableInput")
    finally:
        window.close()
        window.deleteLater()


@pytest.mark.parametrize("values", [{}, {"token": "override-token"}, {"token": ""}])
def test_secret_defaults_are_masked_in_launch_log(values):
    tool = ToolDefinition(
        id="custom.secret", title="Secret", section="custom",
        executor={"kind": "process", "command": "echo"},
        parameters=[ParameterDefinition(id="token", label="Token", kind=ParameterKind.SECRET,
                                        default="private-token")],
    )
    value = values.get("token", "private-token")
    message = ExecutionManager._format_launch_for_log(tool, "echo", [value], values)
    if value:
        assert value not in message
        assert "***" in message
