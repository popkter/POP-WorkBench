"""Windows optional runtimes, independent from the interpreter hosting the app."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
import urllib.request
import uuid
import zipfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path

import psutil
from PySide6.QtCore import QLockFile

from poptools.paths import AppPaths, installed_runtime_path, plugin_record, resource_path

NAMES = {"python": "Python", "android": "Android 工具（ADB + scrcpy）", "powershell": "PowerShell"}
EXECUTABLES = {"python": "python.exe", "android": "scrcpy.exe", "powershell": "pwsh.exe"}
_locks: dict[str, threading.Lock] = {}
_lock_guard = threading.Lock()


class _OperationLock:
    """Serialize both threads and installer/application processes; reclaim dead owners."""

    def __init__(self, root: Path, thread_lock: threading.Lock):
        self.root = root
        self.thread_lock = thread_lock
        self.file_lock = None

    def acquire(self, blocking=False):
        if not self.thread_lock.acquire(blocking=blocking):
            return False
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            self.file_lock = QLockFile(str(self.root / ".operation.lock"))
            self.file_lock.setStaleLockTime(0)
            if self.file_lock.tryLock(0):
                return True
        except Exception:
            self.thread_lock.release()
            raise
        self.thread_lock.release()
        return False

    def release(self):
        self.file_lock.unlock()
        self.thread_lock.release()

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("插件操作正在进行")
        return self

    def __exit__(self, *_):
        self.release()


@dataclass(frozen=True)
class PluginPackage:
    version: str
    url: str
    digest: str
    algorithm: str = "sha256"
    inner: str = ""


def _request(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "PopTools-Plugin-Manager"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def discover_package(plugin: str) -> PluginPackage:
    if plugin == "python":
        base = "https://api.nuget.org/v3-flatcontainer/python"
        versions = json.loads(_request(base + "/index.json"))["versions"]
        stable = [v for v in versions if re.fullmatch(r"3\.\d+\.\d+", v)]
        version = max(stable, key=lambda v: tuple(map(int, v.split("."))))
        url = f"{base}/{version}/python.{version}.nupkg"
        registration = json.loads(
            _request(f"https://api.nuget.org/v3/registration5-semver1/python/{version}.json")
        )
        catalog = json.loads(_request(registration["catalogEntry"]))
        if catalog.get("packageHashAlgorithm", "").upper() != "SHA512":
            raise ValueError("Python 官方包缺少 SHA512 校验信息")
        digest = base64.b64decode(catalog["packageHash"], validate=True).hex()
        if len(digest) != 128:
            raise ValueError("Python 官方包校验信息无效")
        return PluginPackage(version, url, digest, "sha512", "tools")
    repository = {"android": "Genymobile/scrcpy", "powershell": "PowerShell/PowerShell"}[plugin]
    release = json.loads(_request(f"https://api.github.com/repos/{repository}/releases/latest"))
    if release.get("prerelease") or release.get("draft"):
        raise ValueError("官方未提供稳定版本")
    version = release["tag_name"].removeprefix("v")
    filename = (
        f"scrcpy-win64-v{version}.zip"
        if plugin == "android"
        else f"PowerShell-{version}-win-x64.zip"
    )
    assets = {a["name"]: a for a in release["assets"]}
    asset = assets[filename]
    digest = str(asset.get("digest") or "").removeprefix("sha256:")
    if not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
        checksum = assets.get("SHA256SUMS.txt") or assets.get("hashes.sha256")
        if not checksum:
            raise ValueError("官方发行包缺少校验信息，请稍后重试")
        contents = _request(checksum["browser_download_url"]).decode("utf-8-sig")
        match = re.search(r"(?mi)^([a-f0-9]{64})\s+\*?" + re.escape(filename) + r"\s*$", contents)
        if not match:
            raise ValueError("官方校验清单中找不到发行包")
        digest = match[1]
    return PluginPackage(
        version,
        asset["browser_download_url"],
        digest.lower(),
        inner=f"scrcpy-win64-v{version}" if plugin == "android" else "",
    )


class PluginService:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def record(self, plugin: str) -> dict:
        if plugin not in NAMES:
            raise ValueError("未知插件")
        return plugin_record(self.paths, plugin)

    def directory(self, plugin: str) -> Path | None:
        record = self.record(plugin)
        directory = record.get("directory")
        return self.paths.plugins_dir / plugin / directory if directory else None

    def executable(self, plugin: str) -> Path:
        directory = self.directory(plugin)
        return (
            (directory or self.paths.plugins_dir / plugin / "missing")
            / "runtime"
            / EXECUTABLES[plugin]
        )

    def available(self, plugin: str) -> bool:
        return self.executable(plugin).is_file()

    def _installed_runtime_ready(self, plugin: str) -> bool:
        directory = self.directory(plugin)
        if directory is None or not self.available(plugin):
            return False
        if plugin == "python":
            return (directory / "env/Scripts/python.exe").is_file()
        if plugin == "android":
            return all((directory / "runtime" / name).is_file()
                       for name in ("adb.exe", "scrcpy-server", "SDL3.dll"))
        return True

    def _write(self, plugin: str, record: dict) -> None:
        root = self.paths.plugins_dir / plugin
        root.mkdir(parents=True, exist_ok=True)
        temporary = root / f".record-{uuid.uuid4().hex}.json"
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(root / "installed.json")

    def _guard(self, plugin: str) -> _OperationLock:
        key = str((self.paths.plugins_dir / plugin).resolve())
        with _lock_guard:
            lock = _locks.setdefault(key, threading.Lock())
        return _OperationLock(Path(key), lock)

    def _remove_directory(self, plugin: str, directory: Path, *, ignore_errors=False) -> None:
        root = (self.paths.plugins_dir / plugin).resolve()
        target = directory.resolve()
        if (not root.is_relative_to(self.paths.plugins_dir.resolve())
                or target == root or not target.is_relative_to(root)):
            raise ValueError("拒绝清理应用插件目录之外的文件")
        shutil.rmtree(directory, ignore_errors=ignore_errors)

    def assert_unused(self, plugin: str) -> None:
        root = (self.paths.plugins_dir / plugin).resolve()
        for process in psutil.process_iter(["exe", "name"]):
            try:
                executable = process.info.get("exe")
                if executable and Path(executable).resolve().is_relative_to(root):
                    raise RuntimeError(
                        f"{NAMES[plugin]} 正在使用，请先结束相关任务（{process.info['name']}）"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    def _stop_managed_adb(self) -> None:
        """Stop only the daemon whose executable belongs to this app's old runtime."""
        executable = self.executable("android").with_name("adb.exe").resolve()
        for process in psutil.process_iter(["exe"]):
            try:
                current = process.info.get("exe")
                if not current or Path(current).resolve() != executable:
                    continue
                process.terminate()
                try:
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            except psutil.NoSuchProcess:
                continue

    @staticmethod
    def _extract(archive: Path, destination: Path) -> None:
        with zipfile.ZipFile(archive) as package:
            for member in package.infolist():
                name = member.filename.replace("\\", "/")
                target = (destination / name).resolve()
                if (
                    ":" in name
                    or not target.is_relative_to(destination.resolve())
                    or (member.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError("插件包包含不安全路径")
            package.extractall(destination)

    @staticmethod
    def _run(args: list[str], cancelled: Callable[[], bool]) -> str:
        # communicate(timeout) drains pipes while allowing cooperative cancellation.
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.upper().startswith(("PYTHON", "POPTOOLS_PYTHON"))
            and key.upper() != "VIRTUAL_ENV"
        }
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            env=environment,
            cwd=str(Path(args[0]).resolve().parent),
        )
        while True:
            try:
                stdout, stderr = process.communicate(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if cancelled():
                    children = psutil.Process(process.pid).children(recursive=True)
                    for child in children:
                        with suppress(psutil.NoSuchProcess):
                            child.kill()
                    process.kill()
                    process.communicate()
                    raise RuntimeError("插件操作已取消") from None
        if process.returncode:
            raise RuntimeError((stderr or stdout).strip()[-6000:])
        return stdout

    def install(
        self,
        plugin: str,
        package: PluginPackage,
        progress: Callable[[int], None] = lambda _: None,
        cancelled: Callable[[], bool] = lambda: False,
        source: Path | None = None,
        legacy_python: Path | None = None,
    ) -> None:
        self.record(plugin)
        lock = self._guard(plugin)
        if not lock.acquire(blocking=False):
            raise RuntimeError("插件操作正在进行")
        target: Path | None = None
        committed = False
        try:
            self.assert_unused(plugin)
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", package.version):
                raise ValueError("插件版本无效")
            root = self.paths.plugins_dir / plugin
            root.mkdir(parents=True, exist_ok=True)
            # The venv is created at its final path; moving it breaks Windows launchers.
            target = root / f"{package.version}-{uuid.uuid4().hex[:12]}"
            target.mkdir()
            (target / ".pending").touch()
            runtime = target / "runtime"
            progress(1)
            if source is not None:
                shutil.copytree(source, runtime)
            else:
                if package.algorithm not in {"sha256", "sha512"}:
                    raise ValueError("不支持的插件校验算法")
                archive = target / "download.zip"
                digest = hashlib.new(package.algorithm)
                request = urllib.request.Request(
                    package.url, headers={"User-Agent": "PopTools-Plugin-Manager"}
                )
                with (
                    urllib.request.urlopen(request, timeout=30) as response,
                    archive.open("wb") as output,
                ):
                    total = int(response.headers.get("Content-Length") or 0)
                    count = 0
                    while chunk := response.read(1024 * 1024):
                        if cancelled():
                            raise RuntimeError("插件操作已取消")
                        output.write(chunk)
                        digest.update(chunk)
                        count += len(chunk)
                        progress(min(65, int(count * 65 / total)) if total else 5)
                if digest.hexdigest().lower() != package.digest.lower():
                    raise ValueError("插件下载校验失败")
                # Flat archives (PowerShell) already have the runtime layout. Extract
                # at the final path so Windows scanners holding directory handles
                # cannot make a subsequent directory rename fail with WinError 5.
                extracted = target / "unpacked" if package.inner else runtime
                self._extract(archive, extracted)
                inner = (extracted / package.inner).resolve()
                if not inner.is_relative_to(extracted.resolve()):
                    raise ValueError("插件目录无效")
                if package.inner:
                    inner.rename(runtime)
                    shutil.rmtree(extracted)
                archive.unlink()
            progress(75)
            required = [EXECUTABLES[plugin]]
            if plugin == "android":
                required += ["adb.exe", "scrcpy-server", "SDL3.dll"]
            if not all((runtime / name).is_file() for name in required):
                raise ValueError("插件缺少必要运行文件")
            if cancelled():
                raise RuntimeError("插件操作已取消")
            if plugin == "python":
                old = self.directory(plugin)
                previous = legacy_python or (old / "env/Scripts/python.exe" if old else None)
                dependencies = ""
                if previous and previous.is_file():
                    dependencies = self._run([str(previous), "-m", "pip", "freeze"], cancelled)
                self._run(
                    [str(runtime / "python.exe"), "-m", "venv", str(target / "env")], cancelled
                )
                python = str(target / "env/Scripts/python.exe")
                if dependencies.strip():
                    requirements = target / "migrated-requirements.txt"
                    requirements.write_text(dependencies, encoding="utf-8")
                    self._run([python, "-m", "pip", "install", "-r", str(requirements)], cancelled)
                self._run([python, "-m", "pip", "check"], cancelled)
                self._run([python, "-c", "import sys,ssl; print(sys.version)"], cancelled)
            else:
                self._run([str(runtime / EXECUTABLES[plugin]), "--version"], cancelled)
            if cancelled():
                raise RuntimeError("插件操作已取消")
            self.assert_unused(plugin)
            self._write(
                plugin, {"directory": target.name, "package": asdict(package), "removed": False}
            )
            committed = True
            (target / ".pending").unlink(missing_ok=True)
            for previous in root.iterdir():
                if previous.is_dir() and previous != target and previous.name != "seed":
                    self._remove_directory(plugin, previous, ignore_errors=True)
            progress(100)
        finally:
            if target and not committed:
                self._remove_directory(plugin, target, ignore_errors=True)
            lock.release()

    def uninstall(self, plugin: str) -> None:
        self.record(plugin)
        lock = self._guard(plugin)
        if not lock.acquire(blocking=False):
            raise RuntimeError("插件操作正在进行")
        try:
            self.assert_unused(plugin)
            previous = self.record(plugin)
            # Write the tombstone before deleting so an interrupted uninstall cannot reseed.
            self._write(plugin, {"removed": True})
            root = self.paths.plugins_dir / plugin
            try:
                for entry in root.iterdir():
                    if entry.is_dir():
                        self._remove_directory(plugin, entry)
            except OSError:
                # Keep a repair/uninstall entry if Windows denied a deletion.
                self._write(plugin, previous)
                raise
        finally:
            lock.release()

    def recover(self) -> None:
        for plugin in NAMES:
            root = self.paths.plugins_dir / plugin
            if root.exists():
                lock = self._guard(plugin)
                if not lock.acquire():
                    continue
                try:
                    active = self.directory(plugin)
                    for entry in root.iterdir():
                        if entry.is_dir() and entry != active and (entry / ".pending").is_file():
                            self._remove_directory(plugin, entry, ignore_errors=True)
                finally:
                    lock.release()

    def migrate(self, application_directory: Path | None = None) -> None:
        """Import old installs before the installer is allowed to delete runtime/."""
        for plugin, old_name in (("python", "python"), ("android", "scrcpy")):
            if self.record(plugin):
                continue
            source = (
                application_directory / "runtime" / old_name
                if application_directory
                else installed_runtime_path(old_name)
            )
            if plugin == "python" and not source.is_dir():
                source = self.paths.data_dir / "python/runtime"
            if plugin == "android" and not source.is_dir():
                candidates = sorted(self.paths.runtime_dir.glob("scrcpy-*"))
                source = candidates[-1] if candidates else source
            if not (source / EXECUTABLES[plugin]).is_file():
                continue
            manifest = resource_path(
                "vendor",
                "python/python-runtime.json" if plugin == "python" else "scrcpy-manifest.json",
            )
            if (source / "manifest.json").is_file():
                manifest = source / "manifest.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            url = data.get("url") or (
                f"https://github.com/Genymobile/scrcpy/releases/download/v{data['version']}/"
                f"scrcpy-win64-v{data['version']}.zip"
            )
            self.install(
                plugin,
                PluginPackage(
                    data["version"],
                    url,
                    data["sha256"],
                    inner="tools" if plugin == "python" else f"scrcpy-win64-v{data['version']}",
                ),
                source=source,
                legacy_python=self.paths.data_dir / "python/venv/Scripts/python.exe"
                if plugin == "python"
                else None,
            )
        if not self.record("powershell"):
            for candidate in sorted(
                self.paths.powershell_plugin_dir.glob("*/plugin.json"), reverse=True
            ):
                data = json.loads(candidate.read_text(encoding="utf-8"))
                if (candidate.parent / "pwsh.exe").is_file():
                    self.install(
                        "powershell",
                        PluginPackage(data["version"], data["source"], data["sha256"]),
                        source=candidate.parent,
                    )
                    break

    def seed(self) -> None:
        for plugin in NAMES:
            root = self.paths.plugins_dir / plugin / "seed"
            if not root.exists():
                continue
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            replace = data.pop("replace_managed", False)
            record = self.record(plugin)
            same_version = record.get("package", {}).get("version") == data.get("version")
            keep_installed = same_version and self._installed_runtime_ready(plugin)
            if (replace and not keep_installed) or not record:
                if replace and plugin == "android":
                    self._stop_managed_adb()
                # Python always migrates the application's existing environment;
                # the selected external interpreter is never used as the source.
                self.install(plugin, PluginPackage(**data), source=root / "runtime")
            # Failed preparation leaves the seed intact so startup can retry.
            self._remove_directory(plugin, root)
