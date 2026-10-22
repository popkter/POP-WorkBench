from __future__ import annotations

from PySide6.QtCore import Property, QObject, QThread, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from poptools.infrastructure.plugin_service import (
    NAMES,
    PluginPackage,
    PluginService,
    discover_package,
)
from poptools.infrastructure.runtime_environment import RuntimeEnvironment


class RuntimeSelection(QThread):
    result = Signal(str, str, str, str)
    action = "configure"

    def __init__(self, runtime, plugin, provider, executable, scrcpy, parent):
        super().__init__(parent)
        self.runtime, self.plugin, self.provider = runtime, plugin, provider
        self.executable, self.scrcpy = executable, scrcpy

    def run(self):
        try:
            executable, scrcpy, version = (
                self.runtime.validate(self.plugin, self.executable, self.scrcpy)
                if self.provider == "custom" else (self.executable, self.scrcpy, "")
            )
            self.result.emit(executable, scrcpy, version, "")
        except Exception as exc:
            self.result.emit("", "", "", str(exc))


class PluginOperation(QThread):
    progress = Signal(int)
    result = Signal(object, str)

    def __init__(self, service, plugin, action, package, parent=None):
        super().__init__(parent)
        self.service, self.plugin, self.action, self.package = service, plugin, action, package

    def run(self):
        try:
            package = self.package
            if self.action == "check":
                package = discover_package(self.plugin)
            elif self.action == "stop-server":
                self.service._run(
                    [str(self.service.executable("android").with_name("adb.exe")), "kill-server"],
                    self.isInterruptionRequested,
                )
            elif self.action == "uninstall":
                self.service.uninstall(self.plugin)
            else:
                if self.action == "repair":
                    package = PluginPackage(**self.service.record(self.plugin)["package"])
                package = package or discover_package(self.plugin)
                self.service.install(
                    self.plugin, package, self.progress.emit, self.isInterruptionRequested
                )
            self.result.emit(package, "")
        except Exception as exc:
            self.result.emit(None, str(exc))


class PluginController(QObject):
    changed = Signal()
    completed = Signal(str, bool, str)

    def __init__(self, service: PluginService, parent=None, runtime=None):
        super().__init__(parent)
        self.service = service
        self.runtime = runtime or (RuntimeEnvironment(service.paths, service=service)
                                   if service else None)
        self._jobs = {}
        self._latest = {}
        self._progress = {}
        self._errors = {}
        self._actions = {}
        self._results = {}
        self.androidPaused = False
        self.busy_check = lambda plugin: False
        self.configuration_busy_check = lambda plugin: self.busy_check(plugin)

    @Property("QVariantList", notify=changed)
    def plugins(self):
        rows = []
        for plugin, name in NAMES.items():
            record = self.service.record(plugin)
            runtime = self.runtime
            provider, custom, scrcpy = runtime.source(plugin)
            managed = provider == "managed"
            version = record.get("package", {}).get("version", "")
            if not managed:
                version = runtime.config.load_config().get(plugin, {}).get("custom_version", "")
            latest = self._latest.get(plugin) if managed else None
            available = self.service.available(plugin) if managed else (
                bool(custom) and runtime.executable(plugin).is_file()
            )
            rows.append(
                {
                    "id": plugin,
                    "name": name,
                    "managed": managed,
                    "provider": provider,
                    "customExecutable": custom,
                    "customScrcpy": scrcpy,
                    "version": version,
                    "latest": latest.version if latest else "",
                    "installed": available,
                    "recorded": bool(record.get("directory")),
                    "busy": plugin in self._jobs,
                    "progress": self._progress.get(plugin, 0),
                    "canUpdate": bool(
                        latest
                        and (
                            not version
                            or tuple(map(int, latest.version.split(".")))
                            > tuple(map(int, version.split(".")))
                        )
                    ),
                    "status": self._errors.get(plugin)
                    or self._actions.get(plugin)
                    or (("本地环境 · 更新和卸载由用户管理" if available
                         else "本地路径不可用，请重新配置") if not managed
                        else ("已安装" if available else "未安装，可安装或选择本地环境")),
                    "path": str(runtime.executable(plugin)),
                }
            )
        return rows

    @Slot(str, str, result=bool)
    def operate(self, plugin, action):
        if action == "stop-server" and plugin != "android":
            return False
        if (
            plugin not in NAMES
            or action not in {"check", "install", "update", "repair", "uninstall", "stop-server"}
            or plugin in self._jobs
        ):
            return False
        if self.service and self.runtime.source(plugin)[0] == "custom":
            self._errors[plugin] = "本地环境由用户管理，应用不执行插件更新或卸载"
            self.changed.emit()
            return False
        reason = self.busy_check(plugin) if action != "check" else ""
        if reason:
            self._errors[plugin] = (
                reason if isinstance(reason, str) else "请先结束正在运行的终端、脚本或投屏任务"
            )
            self.changed.emit()
            return False
        self._errors[plugin] = ""
        if plugin == "android" and action != "check":
            self.androidPaused = True
        self._progress[plugin] = 0
        self._actions[plugin] = {
            "check": "正在检查更新",
            "install": "正在安装",
            "update": "正在更新",
            "repair": "正在修复",
            "uninstall": "正在卸载",
            "stop-server": "正在停止设备服务",
        }[action]
        job = PluginOperation(self.service, plugin, action, self._latest.get(plugin), self)
        self._jobs[plugin] = job
        job.progress.connect(lambda value, p=plugin: self._on_progress(p, value))
        job.result.connect(
            lambda package, error, p=plugin, a=action: self._on_result(p, a, package, error)
        )
        job.finished.connect(lambda p=plugin: self._on_finished(p))
        job.finished.connect(job.deleteLater)
        self.changed.emit()
        job.start()
        return True

    @Slot(str, result=str)
    def browseExecutable(self, current):
        filename, _ = QFileDialog.getOpenFileName(
            None, "选择本地可执行文件", current, "可执行文件 (*.exe);;所有文件 (*)"
        )
        return filename

    @Slot(str, str, str, str, result=bool)
    def configureRuntime(self, plugin, provider, executable, scrcpy):
        if plugin not in NAMES or provider not in {"managed", "custom"} or self._jobs:
            return False
        reason = self.configuration_busy_check(plugin)
        if reason:
            self._errors[plugin] = str(reason)
            self.changed.emit()
            return False
        self._errors[plugin] = ""
        self._actions[plugin] = "正在检测并保存运行环境"
        job = RuntimeSelection(self.runtime, plugin, provider,
                               executable, scrcpy, self)
        self._jobs[plugin] = job
        job.result.connect(self._on_runtime_validated)
        job.finished.connect(self._on_configuration_finished)
        job.finished.connect(job.deleteLater)
        self.changed.emit()
        job.start()
        return True

    @Slot(str, str, str, str)
    def _on_runtime_validated(self, executable, scrcpy, version, error):
        job = self.sender()
        if isinstance(job, RuntimeSelection):
            if job.isInterruptionRequested():
                error = "运行环境检测已取消"
            self._on_runtime_selection(job.plugin, job.provider, executable, scrcpy, version, error)

    @Slot()
    def _on_configuration_finished(self):
        job = self.sender()
        if isinstance(job, RuntimeSelection):
            self._on_finished(job.plugin)

    def _on_runtime_selection(self, plugin, provider, executable, scrcpy, version, error):
        if not error:
            try:
                reason = self.configuration_busy_check(plugin)
                if reason:
                    raise RuntimeError(str(reason))
                self.runtime.config.set_runtime_environment(
                    plugin, provider, executable, scrcpy, version
                )
                if plugin == "android":
                    self.androidPaused = False
            except (OSError, ValueError, RuntimeError) as exc:
                error = str(exc)
        self._on_result(plugin, "configure", None, error)

    def _on_progress(self, plugin, value):
        self._progress[plugin] = value
        self.changed.emit()

    @property
    def mutating(self):
        return any(job.action != "check" for job in self._jobs.values())

    def resumeDiscovery(self):
        if self.mutating:
            return False
        self.androidPaused = False
        self.changed.emit()
        return True

    def _on_result(self, plugin, action, package, error):
        self._errors[plugin] = error
        if package:
            self._latest[plugin] = package
        self._actions.pop(plugin, None)
        self._results[plugin] = (not bool(error), error or "操作完成")
        if plugin == "android" and not error and action in {"install", "update", "repair"}:
            self.androidPaused = False
        self.changed.emit()

    def _on_finished(self, plugin):
        self._jobs.pop(plugin, None)
        success, message = self._results.pop(plugin, (False, "操作未完成"))
        self.completed.emit(plugin, success, message)
        self.changed.emit()

    @Slot(str)
    def cancel(self, plugin):
        if plugin in self._jobs:
            self._jobs[plugin].requestInterruption()

    def operation_state(self, plugin: str) -> tuple[bool, int, str]:
        return (plugin in self._jobs, self._progress.get(plugin, 0),
                self._errors.get(plugin) or self._actions.get(plugin, ""))

    @Slot()
    def shutdown(self):
        for job in list(self._jobs.values()):
            job.requestInterruption()
        for job in list(self._jobs.values()):
            job.wait()
