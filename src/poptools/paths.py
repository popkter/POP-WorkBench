from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

ANDROID_TOOLS_DIR_ENV = "POPTOOLS_ANDROID_TOOLS_DIR"
_managed_paths: AppPaths | None = None


def configure_plugin_paths(paths: AppPaths) -> None:
    global _managed_paths
    _managed_paths = paths


def plugin_record(paths: AppPaths, plugin: str) -> dict:
    record_file = paths.plugins_dir / plugin / "installed.json"
    if not record_file.exists():
        return {}
    record = json.loads(record_file.read_text(encoding="utf-8"))
    directory = record.get("directory", "")
    if directory and (Path(directory).name != directory or directory in {".", ".."}):
        raise ValueError("插件安装记录包含无效目录")
    return record


def managed_plugin_directory(paths: AppPaths, plugin: str) -> Path:
    record = plugin_record(paths, plugin)
    return paths.plugins_dir / plugin / record.get("directory", "missing")


def platform_key() -> str:
    machine = platform.machine().lower()
    architecture = "arm64" if machine in {"arm64", "aarch64"} else "x64"
    if sys.platform == "win32":
        return f"windows-{architecture}"
    if sys.platform == "darwin":
        return f"macos-{architecture}"
    raise RuntimeError(f"不支持的平台：{sys.platform}/{machine}")


def _android_tool_name(name: str) -> str:
    return f"{name}.exe" if sys.platform == "win32" else name


def package_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "poptools"
    return Path(__file__).resolve().parent


def resource_path(*parts: str) -> Path:
    return package_root().joinpath("resources", *parts)


def installed_runtime_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        return Path(sys.executable).resolve().parent.joinpath("runtime", *parts)
    return package_root().joinpath("runtime", *parts)


def bundled_android_tools_dir() -> Path:
    if sys.platform == "win32" and _managed_paths is not None:
        from poptools.infrastructure.runtime_environment import RuntimeEnvironment

        runtime = RuntimeEnvironment(_managed_paths)
        if runtime.source("android")[0] == "custom":
            return runtime.scrcpy_executable().parent
        return managed_plugin_directory(_managed_paths, "android") / "runtime"
    override = os.environ.get(ANDROID_TOOLS_DIR_ENV)
    if override:
        return Path(override)
    installed = installed_runtime_path("scrcpy")
    if installed.is_dir():
        return installed
    return resource_path("scrcpy")


def bundled_adb_path() -> Path:
    if sys.platform == "win32" and _managed_paths is not None:
        from poptools.infrastructure.runtime_environment import RuntimeEnvironment

        return RuntimeEnvironment(_managed_paths).executable("android")
    return bundled_android_tools_dir() / _android_tool_name("adb")


def bundled_scrcpy_path() -> Path:
    if sys.platform == "win32" and _managed_paths is not None:
        from poptools.infrastructure.runtime_environment import RuntimeEnvironment

        return RuntimeEnvironment(_managed_paths).scrcpy_executable()
    return bundled_android_tools_dir() / _android_tool_name("scrcpy")


def prepare_bundled_android_tools(paths: AppPaths) -> Path:
    """Use installed tools, with legacy archive extraction as a fallback."""

    installed = installed_runtime_path("scrcpy")
    if sys.platform == "win32" and installed.is_dir():
        required_files = ("adb.exe", "scrcpy.exe", "scrcpy-server", "SDL3.dll")
        if not all((installed / name).is_file() for name in required_files):
            raise ValueError("安装目录中的 scrcpy 运行时不完整")
        os.environ[ANDROID_TOOLS_DIR_ENV] = str(installed)
        return installed

    vendor_dir = resource_path("vendor")
    manifest_name = (
        "scrcpy-manifest.json"
        if sys.platform == "win32"
        else f"scrcpy-manifest-{platform_key()}.json"
    )
    manifest_file = vendor_dir / manifest_name
    if not manifest_file.is_file():
        raise FileNotFoundError("内置 scrcpy 清单不存在")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("内置 scrcpy 清单格式错误")

    archive = vendor_dir / str(manifest.get("archive", ""))
    expected_checksum = str(manifest.get("sha256", "")).lower()
    if not archive.is_file() or _sha256(archive) != expected_checksum:
        raise ValueError("内置 scrcpy 发行包校验失败")

    version = str(manifest.get("version", "unknown"))
    release_name = f"scrcpy-{version}-{platform_key()}-{expected_checksum[:12]}"
    target = paths.runtime_dir / release_name
    if _android_tools_are_ready(target, manifest):
        os.environ[ANDROID_TOOLS_DIR_ENV] = str(target)
        return target

    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    staging = paths.runtime_dir / f".{release_name}.{uuid.uuid4().hex}"
    try:
        if archive.name.endswith(".zip"):
            with zipfile.ZipFile(archive) as package:
                package.extractall(staging)
        elif archive.name.endswith((".tar.gz", ".tgz")):
            _extract_tar_safely(archive, staging)
        else:
            raise ValueError(f"不支持的 scrcpy 归档格式：{archive.name}")
        extracted = staging / str(
            manifest.get("directory") or f"scrcpy-win64-v{version}"
        )
        required_files = tuple(
            str(name)
            for name in manifest.get(
                "required_files",
                ("adb.exe", "scrcpy.exe", "scrcpy-server", "SDL3.dll"),
            )
        )
        if not all((extracted / name).is_file() for name in required_files):
            raise ValueError("内置 scrcpy 发行包缺少必要文件")
        for name in manifest.get("executables", ()):
            executable = extracted / str(name)
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        shutil.copy2(vendor_dir / "scrcpy-LICENSE.txt", extracted / "LICENSE.txt")
        shutil.copy2(manifest_file, extracted / "manifest.json")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(extracted, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    os.environ[ANDROID_TOOLS_DIR_ENV] = str(target)
    return target


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _android_tools_are_ready(directory: Path, manifest: dict[str, object]) -> bool:
    manifest_file = directory / "manifest.json"
    required_files = tuple(
        str(name)
        for name in manifest.get(
            "required_files",
            ("adb.exe", "scrcpy.exe", "scrcpy-server", "SDL3.dll"),
        )
    )
    if not all((directory / name).is_file() for name in required_files):
        return False
    try:
        installed = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(installed == manifest)


def _extract_tar_safely(archive: Path, destination: Path) -> None:
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            resolved = (destination / member.name).resolve()
            if os.path.commonpath((root, resolved)) != str(root):
                raise ValueError("scrcpy 发行包包含不安全路径")
        package.extractall(destination)


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path

    @classmethod
    def from_environment(cls) -> AppPaths:
        override = os.environ.get("POPTOOLS_DATA_DIR")
        data_dir = Path(override) if override else Path(user_data_path("PopTools", appauthor=False))
        return cls(data_dir=data_dir)

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def overrides_dir(self) -> Path:
        return self.data_dir / "tools" / "overrides"

    @property
    def custom_dir(self) -> Path:
        return self.data_dir / "tools" / "custom"

    @property
    def scripts_dir(self) -> Path:
        return self.data_dir / "scripts"

    @property
    def themes_dir(self) -> Path:
        return self.data_dir / "themes"

    @property
    def outputs_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def runtime_dir(self) -> Path:
        return self.data_dir / "runtime"

    @property
    def python_dir(self) -> Path:
        return self.data_dir / "python"

    @property
    def python_runtime_dir(self) -> Path:
        if sys.platform == "win32" and plugin_record(self, "python"):
            return managed_plugin_directory(self, "python") / "runtime"
        return self.python_dir / "runtime"

    @property
    def python_venv_dir(self) -> Path:
        if sys.platform == "win32" and plugin_record(self, "python"):
            return managed_plugin_directory(self, "python") / "env"
        return self.python_dir / "venv"

    @property
    def plugins_dir(self) -> Path:
        return self.data_dir / "plugins"

    @property
    def updates_dir(self) -> Path:
        return self.data_dir / "updates"

    @property
    def powershell_plugin_dir(self) -> Path:
        return self.plugins_dir / "powershell"

    def ensure(self) -> None:
        for path in (
            self.data_dir,
            self.overrides_dir,
            self.custom_dir,
            self.scripts_dir,
            self.themes_dir,
            self.outputs_dir,
            self.backups_dir,
            self.logs_dir,
            self.runtime_dir,
            self.plugins_dir,
            self.updates_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
