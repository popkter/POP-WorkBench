"""Runtime integration checks, run in a fresh Qt process by test_runtime_environment."""

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools import paths as path_module
from poptools.domain.models import ToolDefinition
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.managed_powershell import ManagedPowerShell
from poptools.infrastructure.plugin_service import PluginService
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.runtime_environment import RuntimeEnvironment
from poptools.paths import AppPaths, package_root
from poptools.runners.execution_manager import ExecutionManager
from poptools.viewmodels.plugin_controller import PluginController


@pytest.fixture
def runtime(tmp_path):
    return RuntimeEnvironment(AppPaths(tmp_path / "data"))


def test_local_python_uses_selected_interpreter_and_not_managed_dependencies(runtime, tmp_path):
    environment = PythonEnvironment(runtime.paths, runtime.config)
    environment.managed_executable.parent.mkdir(parents=True, exist_ok=True)
    environment.managed_executable.touch()
    environment.managed_runtime_executable.parent.mkdir(parents=True, exist_ok=True)
    environment.managed_runtime_executable.touch()
    environment.managed_site_packages.mkdir(parents=True, exist_ok=True)
    python = tmp_path / "local venv/Scripts/python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    (python.parent.parent / "pyvenv.cfg").touch()
    runtime.config.set_runtime_environment("python", "custom", str(python))
    assert environment.state().available
    assert environment.execution_executable() == str(python)
    assert environment.execution_site_packages() is None
    values = environment.execution_environment({
        "PATH": "system", "PYTHONPATH": "managed", "PYTHONHOME": "old",
        "POPTOOLS_PYTHON_SITE_PACKAGES": "old", "VIRTUAL_ENV": "old",
    })
    assert values["PATH"].split(path_module.os.pathsep)[0] == str(python.parent)
    assert values["VIRTUAL_ENV"] == str(python.parent.parent)
    assert "PYTHONPATH" not in values and "PYTHONHOME" not in values
    assert "POPTOOLS_PYTHON_SITE_PACKAGES" not in values
    python.unlink()
    assert not environment.ensure_ready().available
    assert environment.execution_executable() is None
    assert ConfigStore(runtime.paths).python_environment() == ("custom", str(python))


def test_probe_real_python(runtime):
    executable, projection, version = runtime.validate("python", sys.executable)
    assert Path(executable) == Path(sys.executable)
    assert not projection
    assert version.startswith(f"{sys.version_info.major}.{sys.version_info.minor}.")


def test_script_and_terminal_consumers_use_selected_paths(runtime, tmp_path, monkeypatch, qapp):
    from poptools.viewmodels.developer_console_controller import DeveloperConsoleController

    shell = tmp_path / "local pwsh/pwsh.exe"
    shell.parent.mkdir()
    shell.touch()
    adb = tmp_path / "local adb/adb.exe"
    adb.parent.mkdir()
    adb.touch()
    runtime.config.set_runtime_environment("powershell", "custom", str(shell))
    runtime.config.set_runtime_environment("python", "custom", sys.executable)
    runtime.config.set_runtime_environment("android", "custom", str(adb))
    monkeypatch.setattr(path_module, "_managed_paths", runtime.paths)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("PYTHONPATH", "old-managed-environment")
    monkeypatch.setenv("POPTOOLS_PYTHON_SITE_PACKAGES", "old-managed-environment")
    environment = PythonEnvironment(runtime.paths, runtime.config)
    manager = ExecutionManager(runtime.paths, environment)
    tool = ToolDefinition(id="custom.test", title="Test", section="custom",
                          executor={"kind": "powershell", "command": "echo hello"})
    assert manager._build_launch(tool, {})[0] == str(shell)
    values = manager._build_environment(tool, {}, tmp_path)
    assert values.value("POPTOOLS_ADB") == str(adb)
    assert str(Path(sys.executable).parent) in values.value("PATH")
    assert not values.contains("PYTHONPATH")
    assert not values.contains("POPTOOLS_PYTHON_SITE_PACKAGES")
    python_tool = tool.model_copy(update={"executor": tool.executor.model_copy(
        update={"kind": "python", "command": "print('hello')"}
    )})
    assert manager._build_launch(python_tool, {})[0] == sys.executable
    plugin = ManagedPowerShell(PluginService(runtime.paths))
    terminal = DeveloperConsoleController(environment, powershell_plugin=plugin)
    try:
        assert terminal.pluginInstalled and plugin.executable == shell
        values = terminal._terminal_environment()
        assert values["POPTOOLS_ADB"] == str(adb)
        assert str(Path(sys.executable).parent) in values["PATH"]
        assert "old-managed-environment" not in values.get("PYTHONPATH", "")
    finally:
        terminal.shutdown()


@pytest.mark.parametrize("plugin,output", [
    ("powershell", "POPTOOLS_PWSH:7.6.6"),
    ("android", "Android Debug Bridge version 1.0.41\nVersion 36.0.0"),
])
def test_probe_and_android_path_routing(runtime, tmp_path, monkeypatch, plugin, output):
    executable = tmp_path / "本地 环境/tool.exe"
    executable.parent.mkdir()
    executable.touch()
    monkeypatch.setattr(runtime, "_probe", lambda *args: output)
    path, _, version = runtime.validate(plugin, str(executable))
    runtime.config.set_runtime_environment(plugin, "custom", path, version=version)
    assert runtime.executable(plugin) == executable
    if plugin == "android":
        monkeypatch.setattr(path_module, "_managed_paths", runtime.paths)
        monkeypatch.setattr(sys, "platform", "win32")
        assert path_module.bundled_adb_path() == executable
        assert not path_module.bundled_scrcpy_path().is_file()
        scrcpy = tmp_path / "scrcpy/scrcpy.exe"
        scrcpy.parent.mkdir()
        scrcpy.touch()
        (scrcpy.parent / "scrcpy-server").touch()
        runtime.config.set_runtime_environment(plugin, "custom", path, str(scrcpy))
        assert path_module.bundled_scrcpy_path() == scrcpy
        assert path_module.bundled_android_tools_dir() == scrcpy.parent


@pytest.mark.parametrize("plugin,output", [
    ("powershell", "POPTOOLS_PWSH:5.1.0"), ("android", "some other executable"),
    ("python", '{"version":[3,10,0],"implementation":"CPython"}'),
])
def test_invalid_versions_rejected(runtime, tmp_path, monkeypatch, plugin, output):
    path = tmp_path / "tool.exe"
    path.touch()
    monkeypatch.setattr(runtime, "_probe", lambda *args: output)
    with pytest.raises(ValueError):
        runtime.validate(plugin, str(path))


def test_local_path_must_be_external_and_scrcpy_complete(runtime, tmp_path, monkeypatch):
    path = runtime.paths.plugins_dir / "powershell/local/pwsh.exe"
    path.parent.mkdir(parents=True)
    path.touch()
    with pytest.raises(ValueError, match="插件目录之外"):
        runtime.validate("powershell", str(path))
    with pytest.raises(ValueError, match="完整路径"):
        runtime.validate("python", "missing.exe")
    path = tmp_path / "adb.exe"
    path.touch()
    scrcpy = tmp_path / "scrcpy.exe"
    scrcpy.touch()
    monkeypatch.setattr(runtime, "_probe", lambda *args: "Android Debug Bridge version 1.0.41")
    with pytest.raises(ValueError, match="scrcpy-server"):
        runtime.validate("android", str(path), str(scrcpy))


def test_configuration_validation_persists_and_local_mode_rejects_plugin_operations(
    runtime, monkeypatch, qtbot,
):
    controller = PluginController(PluginService(runtime.paths))
    monkeypatch.setattr(RuntimeEnvironment, "validate", lambda *args: (sys.executable, "", "3.11"))
    assert controller.configureRuntime("python", "custom", sys.executable, "")
    qtbot.waitUntil(lambda: not controller._jobs)
    row = controller.plugins[0]
    assert not row["managed"] and row["installed"]
    assert row["version"] == "3.11"
    for action in ("check", "install", "update", "repair", "uninstall"):
        assert not controller.operate("python", action)
    assert runtime.config.python_environment() == ("custom", sys.executable)

    def reject(*args):
        raise ValueError("invalid environment")

    monkeypatch.setattr(RuntimeEnvironment, "validate", reject)
    assert controller.configureRuntime("python", "custom", "invalid.exe", "")
    qtbot.waitUntil(lambda: not controller._jobs)
    assert runtime.config.python_environment() == ("custom", sys.executable)
    assert "invalid environment" in controller.plugins[0]["status"]
    controller.configuration_busy_check = lambda _: "请先停止终端"
    assert not controller.configureRuntime("python", "managed", "", "")
    assert runtime.config.python_environment()[0] == "custom"
    controller.configuration_busy_check = lambda _: ""
    assert controller.configureRuntime("python", "managed", "", "")
    qtbot.waitUntil(lambda: not controller._jobs)
    assert runtime.config.python_environment()[0] == "managed"


@pytest.mark.parametrize("plugin", ["python", "powershell", "android"])
def test_runtime_dialog_and_external_management_controls(runtime, qtbot, plugin):
    runtime.config.set_runtime_environment(plugin, "custom", sys.executable)
    backend = PluginController(PluginService(runtime.paths))
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda values: warnings.extend(v.toString() for v in values))
    component = QQmlComponent(engine)
    engine.rootContext().setContextProperty("contextBackend", backend)
    component.setData(b'''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    width: 800; height: 850; visible: true
    PluginManagerPanel { anchors.fill: parent; backend: contextBackend }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/RuntimeTest.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        def items(item):
            yield item
            for child in item.childItems():
                yield from items(child)

        button = next((item for item in items(window.contentItem())
                       if item.objectName() == "configureRuntime_" + plugin), None)
        assert button is not None
        QMetaObject.invokeMethod(button, "clicked")
        dialog = window.findChild(QObject, "runtimeEnvironmentDialog")
        qtbot.waitUntil(lambda: dialog.property("opened"))
        assert dialog.property("pluginId") == plugin
        assert window.findChild(QObject, "runtimeSource").property("currentIndex") == 1
        assert window.findChild(QObject, "runtimeExecutable").property("text") == sys.executable
        managed_actions = [child for child in button.parentItem().childItems()
                           if child.property("text") in
                           ("安装", "检查更新", "更新", "修复", "卸载")]
        assert managed_actions and not any(child.isVisible() for child in managed_actions)
        window.findChild(QObject, "runtimeSource").setProperty("currentIndex", 0)
        QMetaObject.invokeMethod(window.findChild(QObject, "saveRuntimeEnvironment"), "clicked")
        qtbot.waitUntil(lambda: not dialog.property("visible"))
        assert runtime.config.runtime_environment(plugin)[0] == "managed"
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
