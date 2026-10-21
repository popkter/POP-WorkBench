"""Composition root for the desktop application.

The UI entry point should only deal with Qt lifecycle and presentation wiring.
All concrete adapters are assembled here so that controllers can be reused by
tests and future frontends without duplicating application construction.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, configure_plugin_paths, resource_path
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels import (
    AndroidController,
    AppController,
    DeveloperConsoleController,
    JiraFeishuController,
    PresetController,
    SettingsController,
    UpdateController,
)


@dataclass
class ApplicationComponents:
    """Long-lived application services and view models.

    This object is deliberately a simple data holder.  It makes ownership and
    construction explicit while keeping the existing Qt signals and controller
    APIs unchanged.
    """

    paths: AppPaths
    config_store: ConfigStore
    tool_registry: ToolRegistry
    execution_manager: ExecutionManager
    execution_coordinator: ExecutionCoordinator
    android_controller: AndroidController
    app_controller: AppController
    settings_controller: SettingsController
    preset_controller: PresetController
    jira_feishu_controller: JiraFeishuController
    developer_console_controller: DeveloperConsoleController
    update_controller: UpdateController


def plugin_usage_reason(plugin, terminal, execution, app) -> str:
    if plugin == "powershell":
        tabs = [tab.title for tab in terminal._tabs if tab.session is not None]
        if tabs:
            return "请先停止终端会话：" + "、".join(tabs)
    # Scripts can invoke any plugin through PATH, including after their initial launch.
    if any(worker.active for worker in execution._executions.values()):
        return "请先结束正在运行的脚本，脚本可能调用插件工具"
    if plugin == "android" and execution._scrcpy.active:
        return "请先结束正在运行或启动中的投屏任务"
    if (plugin == "android" and getattr(app, "_scrcpy_displays", None)
            and app._scrcpy_displays.loading):
        return "请先等待屏幕列表查询完成"
    if plugin == "python":
        if app._python_doctor_process is not None:
            return "请先等待 Python 依赖诊断完成"
        if app._python_package_install is not None:
            return "请先等待 Python 依赖安装完成"
    return ""


def build_components(
    paths: AppPaths, terminal_working_directory: Path | None = None
) -> ApplicationComponents:
    """Build the application graph from concrete infrastructure adapters."""

    paths.ensure()
    if sys.platform == "win32":
        configure_plugin_paths(paths)
    config_store = ConfigStore(paths)
    config_store.load_config()
    python_environment = PythonEnvironment(paths, config_store)
    tool_repository = JsonToolRepository(paths)
    tool_registry = ToolRegistry(resource_path("tools"), tool_repository)
    execution_manager = ExecutionManager(paths, python_environment)
    execution_coordinator = ExecutionCoordinator(
        execution_manager,
        config_store.max_parallel(),
    )
    android_controller = AndroidController(config_store)
    app_controller = AppController(
        tool_registry,
        execution_coordinator,
        config_store,
        android_controller,
    )
    settings_controller = SettingsController(
        config_store, python_environment, execution_coordinator
    )
    preset_controller = PresetController(paths)
    jira_feishu_controller = JiraFeishuController(paths.data_dir)
    developer_console_controller = DeveloperConsoleController(
        python_environment, working_directory=terminal_working_directory
    )
    update_controller = UpdateController(config_store)
    if sys.platform == "win32":
        from poptools.infrastructure.managed_powershell import ManagedPowerShell
        manager = settings_controller.pluginManager
        developer_console_controller._plugin = ManagedPowerShell(manager.service)
        developer_console_controller._plugin_manager = manager
        manager.changed.connect(developer_console_controller.pluginStateChanged)
        manager.changed.connect(android_controller.refreshPluginAvailability)
        manager.completed.connect(developer_console_controller.onManagedPluginCompleted)
        execution_coordinator.plugin_mutation_active = lambda: manager.mutating
        android_controller.plugin_discovery_allowed = lambda: (
            not manager.mutating and not manager.androidPaused
        )
        android_controller.resume_plugin_discovery = manager.resumeDiscovery
        app_controller.plugin_mutation_active = lambda: manager.mutating
        manager.busy_check = lambda plugin: plugin_usage_reason(
            plugin, developer_console_controller, execution_coordinator, app_controller
        )
        from PySide6.QtCore import QCoreApplication
        if QCoreApplication.instance():
            QCoreApplication.instance().aboutToQuit.connect(manager.shutdown)
    settings_controller.scriptsImported.connect(app_controller.reloadImportedScripts)
    settings_controller.consoleMessage.connect(app_controller.appendConsoleMessage)
    return ApplicationComponents(
        paths=paths,
        config_store=config_store,
        tool_registry=tool_registry,
        execution_manager=execution_manager,
        execution_coordinator=execution_coordinator,
        android_controller=android_controller,
        app_controller=app_controller,
        settings_controller=settings_controller,
        preset_controller=preset_controller,
        jira_feishu_controller=jira_feishu_controller,
        developer_console_controller=developer_console_controller,
        update_controller=update_controller,
    )
