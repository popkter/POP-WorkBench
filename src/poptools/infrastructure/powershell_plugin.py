"""Legacy import facade; all package installation belongs to PluginService."""
from poptools.infrastructure.managed_powershell import ManagedPowerShell
from poptools.infrastructure.plugin_service import PluginService
from poptools.paths import AppPaths


class PowerShellPlugin(ManagedPowerShell):
    def __init__(self, paths: AppPaths):
        super().__init__(PluginService(paths))
