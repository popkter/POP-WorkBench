from types import SimpleNamespace as State

from poptools.application.bootstrap import plugin_usage_reason
from poptools.runners.execution_coordinator import ExecutionCoordinator
from poptools.viewmodels.app_controller import AppController
from poptools.viewmodels.developer_console_controller import DeveloperConsoleController
from poptools.viewmodels.plugin_controller import PluginController
from poptools.viewmodels.python_dependency_controller import PythonDependencyController


def test_plugin_occupation_is_scoped_to_runtime():
    terminal = State(_tabs=[State(title="PowerShell 1", session=object())], _closing_tabs={})
    execution = State(_executions={}, _scrcpy=State(active=False))
    app = State(_python_doctor_process=None, _python_package_install=None)
    terminal.active_session_titles = lambda: (
        DeveloperConsoleController.active_session_titles(terminal)
    )
    execution.plugin_usage_reason = lambda plugin: ExecutionCoordinator.plugin_usage_reason(
        execution, plugin,
    )
    app._scrcpy_displays = State(loading=False)
    app.python_usage_reason = lambda: PythonDependencyController.usage_reason(app)
    app.plugin_usage_reason = lambda plugin: AppController.plugin_usage_reason(app, plugin)

    def reason(plugin):
        return plugin_usage_reason(plugin, terminal, execution, app)

    assert "PowerShell 1" in reason("powershell")
    assert not reason("python")
    assert not reason("android")
    terminal._tabs[0].session = None
    assert not reason("powershell")
    execution._scrcpy.active = True
    assert "投屏" in reason("android")
    assert not reason("python")
    assert not reason("powershell")
    app._python_doctor_process = object()
    assert "诊断" in reason("python")
    app._python_doctor_process = None
    app._python_package_install = object()
    assert "安装" in reason("python")
    assert not reason("powershell")
    execution._executions["script"] = State(active=True)
    assert all("脚本" in reason(plugin) for plugin in ("python", "android", "powershell"))


def test_plugin_controller_reports_specific_occupation(qapp):
    controller = PluginController(None)
    controller.busy_check = lambda plugin: "请先停止终端会话：PowerShell 1"
    assert not controller.operate("powershell", "update")
    assert controller._errors["powershell"] == "请先停止终端会话：PowerShell 1"
    assert not controller._jobs
