import pytest
from PySide6.QtCore import QMetaObject, QObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.domain.models import ParameterKind
from poptools.domain.parameter_templates import render_template, synchronize_parameters
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, package_root
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels.android_controller import AndroidController
from poptools.viewmodels.app_controller import AppController

BASH_TEMPLATE = '''# 十种参数类型，声明会在执行前移除。
var text=${单行文本@text:示例文本}
var multiline=${多行文本@multiline:多行文本}
var integer=${重试次数@integer:3}
var number=${比例@number:0.5}
var boolean=${启用缓存@boolean:true}
var choice=${下拉框@choice:选项1=1|选项2=2}
var file=${选择文件@file:1}
var dir=${选择目录@dir:2}
var secret=${访问令牌@secret}
var radio=${单选框@radio:选项1=1|选项2=2}
echo "${text} ${multiline} ${integer} ${number} ${boolean} ${choice} ${file} ${dir} ${radio}"
echo "再次引用文件路径：${file}"
if [ -n "${secret}" ]; then
    echo "访问令牌：已填写（隐藏内容）"
fi
'''
INVALID_BASH_TEMPLATE = BASH_TEMPLATE.replace("${访问令牌@secret}", "${访问令牌@secret:1009}")


def test_lowercase_var_declares_exactly_ten_parameters_and_is_removed():
    parameters = synchronize_parameters([BASH_TEMPLATE])
    assert [parameter.id for parameter in parameters] == [
        "text", "multiline", "integer", "number", "boolean", "choice", "file", "dir",
        "secret", "radio",
    ]
    assert [parameter.kind for parameter in parameters] == [
        ParameterKind.TEXT, ParameterKind.MULTILINE, ParameterKind.INTEGER, ParameterKind.NUMBER,
        ParameterKind.BOOLEAN, ParameterKind.CHOICE, ParameterKind.FILE, ParameterKind.DIRECTORY,
        ParameterKind.SECRET, ParameterKind.RADIO,
    ]
    rendered = render_template(BASH_TEMPLATE, {"secret": ""})
    assert "var " not in rendered
    assert 'echo "示例文本 多行文本 3 0.5 true 1 1 2 1"' in rendered
    assert 'echo "再次引用文件路径：1"' in rendered


@pytest.fixture
def editor_backend(qapp, tmp_path):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    coordinator = ExecutionCoordinator(ExecutionManager(paths), 3)
    registry = ToolRegistry(tmp_path / "builtin", JsonToolRepository(paths))
    android = AndroidController(store)
    android.stopAutoRefresh()
    backend = AppController(registry, coordinator, store, android)
    yield backend
    backend._analysis_timer.stop()
    backend._console_refresh_timer.stop()
    backend.deleteLater()
    android.deleteLater()
    coordinator.deleteLater()


@pytest.mark.parametrize("editing", [False, True])
def test_editor_displays_failure_preserves_script_and_allows_retry(editor_backend, editing):
    backend = editor_backend
    if editing:
        assert backend.createCommand("Existing", "", "bash", "echo hello")
    errors = []
    backend.commandSaveFailed.connect(errors.append)
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", backend)
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 900; height: 800; visible: true
    property string script: ""
    property bool editing: false
    CommandEditorDialog {
        id: editor
        objectName: "editor"
        controller: backend
    }
    function openEditor() {
        editor.openForCreate(host.script, "bash")
        editor.editMode = host.editing
    }
    function submitEditor() { editor.submit() }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/EditorErrorsHarness.qml")))
    window = component.create()
    assert window is not None, [error.toString() for error in component.errors()]
    try:
        window.setProperty("script", INVALID_BASH_TEMPLATE)
        window.setProperty("editing", editing)
        assert QMetaObject.invokeMethod(window, "openEditor")
        QTest.qWait(30)
        editor = window.findChild(QObject, "editor")
        label = window.findChild(QObject, "commandEditorSaveError")
        script_field = window.findChild(QObject, "commandEditorScriptText")
        assert QMetaObject.invokeMethod(window, "submitEditor")
        assert editor.property("visible")
        assert label.property("visible")
        assert len(errors) == 1
        assert "访问令牌" in errors[0] and "默认值" in errors[0]
        assert "${访问令牌@secret}" in label.property("text")
        assert "1009" not in label.property("text")
        assert script_field.property("text") == INVALID_BASH_TEMPLATE
        assert len(backend.registry.all()) == (1 if editing else 0)
        if editing:
            assert backend.registry.all()[0].executor.command == "echo hello"
        # Correcting and retrying the same form must succeed without losing other fields.
        script_field.setProperty("text", BASH_TEMPLATE)
        assert QMetaObject.invokeMethod(window, "submitEditor")
        assert not editor.property("visible")
        assert editor.property("saveError") == ""
        assert len(backend.registry.all()) == 1
        assert len(backend.registry.all()[0].parameters) == 10
        assert QMetaObject.invokeMethod(window, "openEditor")
        assert not label.property("visible")
    finally:
        window.close()
        window.deleteLater()
