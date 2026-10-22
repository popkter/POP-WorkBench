"""Resolve user-selected executables without giving plugin storage ownership of them."""

from __future__ import annotations

import json
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

from poptools.infrastructure.config_store import ConfigStore
from poptools.paths import AppPaths


@lru_cache(maxsize=16)
def runtime_for(paths: AppPaths) -> RuntimeEnvironment:
    """Reuse adapters; ConfigStore invalidates snapshots on external file changes."""
    return RuntimeEnvironment(paths)


class RuntimeEnvironment:
    def __init__(self, paths: AppPaths, config: ConfigStore | None = None, service=None):
        self.paths = paths
        self.config = config or ConfigStore(paths)
        from poptools.infrastructure.plugin_service import PluginService
        self.service = service or PluginService(paths)

    def source(self, plugin: str) -> tuple[str, str, str]:
        return self.config.runtime_environment(plugin)

    def executable(self, plugin: str) -> Path:
        provider, executable, _ = self.source(plugin)
        if provider == "custom":
            return Path(executable) if executable else self.paths.plugins_dir / "missing"
        path = self.service.executable(plugin)
        return path.with_name("adb.exe") if plugin == "android" else path

    def scrcpy_executable(self) -> Path:
        provider, _, scrcpy = self.source("android")
        if provider == "custom":
            return Path(scrcpy) if scrcpy else self.paths.plugins_dir / "missing/scrcpy.exe"
        return self.service.executable("android")

    def _local_file(self, value: str) -> Path:
        path = Path(value.strip().strip('"')).expanduser()
        if not value.strip() or not path.is_absolute() or not path.is_file():
            raise ValueError("请选择存在的可执行文件，需使用完整路径")
        # A configured path must never refer to a directory OTA/plugin cleanup owns.
        if path.resolve().is_relative_to(self.paths.plugins_dir.resolve()):
            raise ValueError("本地环境必须位于应用插件目录之外")
        return path.absolute()

    @staticmethod
    def _probe(path: Path, arguments: list[str]) -> str:
        environment = {
            key: value for key, value in os.environ.items()
            if not key.upper().startswith(("PYTHON", "POPTOOLS_PYTHON"))
            and key.upper() != "VIRTUAL_ENV"
        }
        result = subprocess.run(
            [str(path), *arguments], capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15, check=False, env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise ValueError("运行环境检测失败：" + (result.stderr or result.stdout).strip()[-500:])
        return result.stdout + result.stderr

    def validate(self, plugin: str, executable: str, scrcpy: str = "") -> tuple[str, str, str]:
        self.source(plugin)
        path = self._local_file(executable)
        if plugin == "python":
            output = self._probe(path, ["-I", "-c", (
                "import json,sys,platform; print(json.dumps({"
                "'version':list(sys.version_info[:3]),'implementation':platform.python_implementation()}))"
            )])
            data = json.loads(output.strip())
            if data["implementation"] != "CPython" or tuple(data["version"]) < (3, 11):
                raise ValueError("请选择 CPython 3.11 或更高版本，可使用虚拟环境")
            version = ".".join(map(str, data["version"]))
        elif plugin == "powershell":
            output = self._probe(path, ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command",
                                        "'POPTOOLS_PWSH:' + $PSVersionTable.PSVersion.ToString()"])
            match = re.search(r"POPTOOLS_PWSH:(\d+\.\d+(?:\.\d+)?)", output)
            if not match or int(match[1].split(".")[0]) < 7:
                raise ValueError("请选择 PowerShell 7 或更高版本的 pwsh.exe")
            version = match[1]
        else:
            output = self._probe(path, ["version"])
            match = re.search(r"Android Debug Bridge version\s+([\d.]+)", output)
            if not match:
                raise ValueError("请选择 Android platform-tools 中的 adb.exe")
            version = match[1]
        scrcpy_path = ""
        if plugin == "android" and scrcpy.strip():
            candidate = self._local_file(scrcpy)
            if not (candidate.parent / "scrcpy-server").is_file():
                raise ValueError("scrcpy 所在目录缺少 scrcpy-server，请选择完整发行包中的程序")
            if not re.search(r"scrcpy\s+\d", self._probe(candidate, ["--version"]), re.I):
                raise ValueError("请选择有效的 scrcpy 可执行文件")
            scrcpy_path = str(candidate)
        return str(path), scrcpy_path, version
