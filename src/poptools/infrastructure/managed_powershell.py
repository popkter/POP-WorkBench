"""Compatibility facade for terminal callers; storage belongs to PluginService."""

from types import SimpleNamespace

from poptools.infrastructure.plugin_service import PluginService, discover_package
from poptools.infrastructure.runtime_environment import RuntimeEnvironment


class ManagedPowerShell:
    def __init__(self, service: PluginService):
        self.service = service

    @property
    def package(self):
        runtime = RuntimeEnvironment(self.service.paths)
        if runtime.source("powershell")[0] == "custom":
            version = runtime.config.load_config().get("powershell", {}).get("custom_version", "7")
            return SimpleNamespace(version=version)
        return SimpleNamespace(
            version=self.service.record("powershell").get("package", {}).get("version", "7")
        )

    @property
    def install_directory(self):
        if RuntimeEnvironment(self.service.paths).source("powershell")[0] == "custom":
            return self.executable.parent
        return self.service.directory("powershell") or self.service.paths.powershell_plugin_dir

    @property
    def executable(self):
        return RuntimeEnvironment(self.service.paths).executable("powershell")

    def is_installed(self):
        return self.executable.is_file()

    def install(self, progress=None):
        if RuntimeEnvironment(self.service.paths).source("powershell")[0] == "custom":
            raise RuntimeError("本地 PowerShell 由用户管理")
        self.service.install(
            "powershell", discover_package("powershell"), progress or (lambda _: None)
        )
        return self.executable
