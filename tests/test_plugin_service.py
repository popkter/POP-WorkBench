from __future__ import annotations

import hashlib
import io
import json
import shutil
import sys
import zipfile
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from poptools.infrastructure import plugin_service as plugins
from poptools.infrastructure.app_updater import update_asset_name
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.plugin_service import PluginPackage, PluginService
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.paths import AppPaths, plugin_record


@pytest.fixture
def service(tmp_path, monkeypatch):
    service = PluginService(AppPaths(tmp_path))
    monkeypatch.setattr(plugins.psutil, "process_iter", lambda *args: [])
    monkeypatch.setattr(service, "_run", lambda args, cancelled: "")
    return service


def runtime(tmp_path, plugin="powershell"):
    source = tmp_path / f"source-{plugin}"
    source.mkdir(exist_ok=True)
    (source / plugins.EXECUTABLES[plugin]).write_bytes(b"executable")
    if plugin == "android":
        for name in ("adb.exe", "scrcpy-server", "SDL3.dll"):
            (source / name).write_bytes(b"file")
    return source


def package(version="7.6.3"):
    return PluginPackage(version, "https://example.test/runtime.zip", "a" * 64)


def bundled_seed(service, plugin, source, version):
    seed = service.paths.plugins_dir / plugin / "seed"
    seed.mkdir()
    shutil.copytree(source, seed / "runtime")
    (seed / "package.json").write_text(json.dumps({
        **asdict(package(version)), "replace_managed": True,
    }))
    return seed


def test_install_update_uninstall_preserves_user_data(service, tmp_path):
    source = runtime(tmp_path)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "keep.py"
    script.write_text("print(1)")
    service.install("powershell", package(), source=source)
    first = service.directory("powershell")
    assert service.available("powershell")
    service.install("powershell", package("7.6.6"), source=source)
    assert service.record("powershell")["package"]["version"] == "7.6.6"
    assert not first.exists()
    service.uninstall("powershell")
    assert not service.available("powershell")
    assert service.record("powershell") == {"removed": True}
    assert script.read_text() == "print(1)"


def test_validation_failure_keeps_previous_install(service, tmp_path, monkeypatch):
    source = runtime(tmp_path)
    service.install("powershell", package(), source=source)
    previous = service.record("powershell")

    def fail(*args):
        raise RuntimeError("invalid binary")

    monkeypatch.setattr(service, "_run", fail)
    with pytest.raises(RuntimeError, match="invalid binary"):
        service.install("powershell", package("7.6.6"), source=source)
    assert service.record("powershell") == previous
    assert not list(service.paths.plugins_dir.glob("*/*/.pending"))


def test_cancel_keeps_previous(service, tmp_path):
    source = runtime(tmp_path)
    service.install("powershell", package(), source=source)
    previous = service.record("powershell")
    with pytest.raises(RuntimeError, match="取消"):
        service.install("powershell", package("7.6.6"), source=source, cancelled=lambda: True)
    assert service.record("powershell") == previous


@pytest.mark.parametrize(
    "name", ["../escape.exe", "C:/escape.exe", "..\\escape.exe", "/escape.exe"]
)
def test_rejects_archive_traversal(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(name, "bad")
    with pytest.raises(ValueError, match="不安全"):
        PluginService._extract(archive, tmp_path / "out")


def test_checksum_failure_never_activates(service, monkeypatch):
    response = io.BytesIO(b"corrupted package")
    response.headers = {}
    monkeypatch.setattr(plugins.urllib.request, "urlopen", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="校验失败"):
        service.install("powershell", package())
    assert service.record("powershell") == {}


@pytest.mark.parametrize("inner", ["", "tools"])
def test_verified_download_and_extraction(service, monkeypatch, inner):
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, "w") as archive:
        archive.writestr(f"{inner}/pwsh.exe" if inner else "pwsh.exe", b"binary")
        archive.writestr(
            f"{inner}/Modules/module.txt" if inner else "Modules/module.txt", b"module"
        )
    data = contents.getvalue()
    response = io.BytesIO(data)
    response.headers = {"Content-Length": str(len(data))}
    monkeypatch.setattr(plugins.urllib.request, "urlopen", lambda *args, **kwargs: response)
    candidate = PluginPackage(
        "7.6.6", "https://example.test/pwsh.zip", hashlib.sha256(data).hexdigest(), inner=inner
    )
    service.install("powershell", candidate)
    assert service.executable("powershell").read_bytes() == b"binary"
    directory = service.directory("powershell")
    assert (directory / "runtime/Modules/module.txt").read_bytes() == b"module"
    assert not (directory / "download.zip").exists()
    assert not (directory / "unpacked").exists()
    assert not (directory / ".pending").exists()


@pytest.mark.parametrize("validation_fails", [False, True])
def test_powershell_download_does_not_rename_locked_directory(
    service, tmp_path, monkeypatch, validation_fails
):
    service.install("powershell", package(), source=runtime(tmp_path))
    previous = service.record("powershell")
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, "w") as archive:
        archive.writestr("pwsh.exe", b"updated binary")
    data = contents.getvalue()
    response = io.BytesIO(data)
    response.headers = {}
    monkeypatch.setattr(plugins.urllib.request, "urlopen", lambda *args, **kwargs: response)

    def deny_directory_rename(path, destination):
        raise PermissionError(13, "[WinError 5] Access is denied", str(path))

    monkeypatch.setattr(Path, "rename", deny_directory_rename)
    candidate = PluginPackage(
        "7.6.6", "https://example.test/pwsh.zip", hashlib.sha256(data).hexdigest()
    )
    if validation_fails:
        def fail(*args):
            raise RuntimeError("invalid binary")

        monkeypatch.setattr(service, "_run", fail)
        with pytest.raises(RuntimeError, match="invalid binary"):
            service.install("powershell", candidate)
        assert service.record("powershell") == previous
        assert service.executable("powershell").read_bytes() == b"executable"
    else:
        service.install("powershell", candidate)
        assert service.executable("powershell").read_bytes() == b"updated binary"
        assert service.record("powershell")["package"]["version"] == "7.6.6"
    assert not list(service.paths.plugins_dir.glob("*/*/.pending"))


def test_busy_process_and_duplicate_operation_blocked(service, tmp_path, monkeypatch):
    source = runtime(tmp_path)
    service.install("powershell", package(), source=source)
    process = SimpleNamespace(
        info={"exe": str(service.executable("powershell")), "name": "pwsh.exe"}
    )
    monkeypatch.setattr(plugins.psutil, "process_iter", lambda *args: [process])
    with pytest.raises(RuntimeError, match="正在使用"):
        service.uninstall("powershell")
    assert service.available("powershell")
    lock = service._guard("powershell")
    with lock, pytest.raises(RuntimeError, match="正在进行"):
        service.install("powershell", package(), source=source)


def test_recovery_removes_only_uncommitted_install(service, tmp_path):
    source = runtime(tmp_path)
    service.install("powershell", package(), source=source)
    active = service.directory("powershell")
    (active / ".pending").touch()  # Crash immediately after atomic activation.
    stale = active.parent / "7.6.6-abandoned"
    stale.mkdir()
    (stale / ".pending").touch()
    service.recover()
    assert active.exists()
    assert not stale.exists()


def test_removed_bundled_plugin_is_not_reseeded(service, tmp_path):
    source = runtime(tmp_path, "android")
    service.install("android", package("4.0"), source=source)
    service.uninstall("android")
    seed = service.paths.plugins_dir / "android/seed"
    seed.mkdir()
    (seed / "package.json").write_text(json.dumps(asdict(package("4.0"))))
    service.seed()
    assert not seed.exists()
    assert service.record("android") == {"removed": True}


@pytest.mark.parametrize("plugin,version", [
    ("python", "3.13.14"), ("android", "4.0"), ("powershell", "7.6.6"),
])
def test_same_version_bundled_runtime_keeps_environment_and_dependencies(
    service, tmp_path, monkeypatch, plugin, version,
):
    source = runtime(tmp_path, plugin)
    service.install(plugin, package(version), source=source)
    old = service.directory(plugin)
    if plugin == "python":
        python = old / "env/Scripts/python.exe"
        python.parent.mkdir(parents=True)
        python.touch()
    marker = old / "installed-dependency"
    marker.write_text("keep")
    record = service.record(plugin)
    seed = bundled_seed(service, plugin, source, version)
    monkeypatch.setattr(
        service, "install", lambda *args, **kwargs: pytest.fail("must reuse runtime")
    )
    monkeypatch.setattr(service, "_stop_managed_adb", lambda: pytest.fail("must keep ADB running"))
    service.seed()
    assert service.record(plugin) == record
    assert marker.read_text() == "keep"
    assert not seed.exists()


@pytest.mark.parametrize("plugin", ["python", "android", "powershell"])
def test_same_version_incomplete_runtime_is_repaired(service, tmp_path, plugin):
    source = runtime(tmp_path, plugin)
    service.install(plugin, package("7.0"), source=source)
    old = service.directory(plugin)
    service.executable(plugin).unlink()
    bundled_seed(service, plugin, source, "7.0")
    service.seed()
    assert service.directory(plugin) != old
    assert service.available(plugin)
    assert not old.exists()


@pytest.mark.parametrize("failure", ["", "freeze", "install", "check", "validation"])
def test_bundled_python_version_change_migrates_before_commit_and_can_retry(
    service, tmp_path, monkeypatch, failure,
):
    source = runtime(tmp_path, "python")
    service.install("python", package("3.13.14"), source=source)
    old = service.directory("python")
    old_python = old / "env/Scripts/python.exe"
    old_python.parent.mkdir(parents=True)
    old_python.touch()
    old_dependency = old / "installed-dependency"
    old_dependency.write_text("keep until commit")
    record = service.record("python")
    seed = bundled_seed(service, "python", source, "3.14.7")
    external = tmp_path / "external/python.exe"
    external.parent.mkdir()
    external.write_text("user-owned")
    config = ConfigStore(service.paths)
    config.set_runtime_environment("python", "custom", str(external))
    selection = config.load_config()
    failing = [failure]
    commands = []
    requirements = "library-one==1.0\nlibrary-two==2.0\n"

    def execute(args, cancelled):
        commands.append(args)
        assert service.record("python") == record
        assert old_dependency.read_text() == "keep until commit"
        assert args[0] != str(external)
        if args[1:3] == ["-m", "pip"]:
            phase = args[3]
        elif args[1:3] == ["-m", "venv"]:
            phase = "venv"
        else:
            phase = "validation"
        if phase == failing[0]:
            raise RuntimeError("migration failed during " + phase)
        if phase == "freeze":
            assert args[0] == str(old_python)
            return requirements
        if "install" in args:
            assert Path(args[-1]).read_text() == requirements
        return ""

    monkeypatch.setattr(service, "_run", execute)
    if failure:
        with pytest.raises(RuntimeError, match="migration failed"):
            service.seed()
        assert service.record("python") == record
        assert old_dependency.read_text() == "keep until commit"
        assert seed.exists()
        assert not list(service.paths.plugins_dir.glob("*/*/.pending"))
        failing[0] = ""
    service.seed()
    new = service.directory("python")
    assert new != old and not old.exists() and not seed.exists()
    assert service.record("python")["package"]["version"] == "3.14.7"
    assert (new / "migrated-requirements.txt").read_text() == requirements
    assert any(args[1:4] == ["-m", "pip", "install"] for args in commands)
    assert any(args[1:4] == ["-m", "pip", "check"] for args in commands)
    assert config.load_config() == selection
    assert external.read_text() == "user-owned"


@pytest.mark.parametrize("plugin", ["python", "android", "powershell"])
def test_full_upgrade_replaces_managed_runtime_but_preserves_external_choice(
    service, tmp_path, plugin,
):
    source = runtime(tmp_path, plugin)
    service.install(plugin, package("7.0"), source=source)
    old = service.directory(plugin)
    (old / "old-dependency.txt").touch()
    external = tmp_path / "external" / plugins.EXECUTABLES[plugin]
    external.parent.mkdir()
    external.write_text("user-owned")
    config = ConfigStore(service.paths)
    config.set_runtime_environment(plugin, "custom", str(external))
    seed = service.paths.plugins_dir / plugin / "seed"
    seed.mkdir()
    shutil.copytree(source, seed / "runtime")
    (seed / "package.json").write_text(json.dumps({
        **asdict(package("7.1")), "replace_managed": True,
    }))
    service.seed()
    assert service.record(plugin)["package"]["version"] == "7.1"
    assert not old.exists() and not seed.exists()
    assert external.read_text() == "user-owned"
    assert config.runtime_environment(plugin)[:2] == ("custom", str(external))


def test_failed_replacement_keeps_old_runtime_and_seed_for_retry(service, tmp_path, monkeypatch):
    source = runtime(tmp_path)
    service.install("powershell", package(), source=source)
    old = service.directory("powershell")
    seed = service.paths.plugins_dir / "powershell/seed"
    (seed / "runtime").mkdir(parents=True)
    (seed / "runtime/pwsh.exe").touch()
    (seed / "package.json").write_text(json.dumps({
        **asdict(package("7.6.6")), "replace_managed": True,
    }))

    def fail(*args):
        raise RuntimeError("invalid runtime")

    monkeypatch.setattr(service, "_run", fail)
    with pytest.raises(RuntimeError, match="invalid runtime"):
        service.seed()
    assert old.exists() and service.directory("powershell") == old
    assert seed.exists()


def test_seed_stops_only_application_owned_adb(service, tmp_path, monkeypatch):
    service.install("android", package("4.0"), source=runtime(tmp_path, "android"))
    calls = []
    owned = SimpleNamespace(info={"exe": str(service.executable("android").with_name("adb.exe"))},
                            terminate=lambda: calls.append("owned"), wait=lambda **kwargs: None)
    external = SimpleNamespace(info={"exe": str(tmp_path / "external/adb.exe")},
                               terminate=lambda: pytest.fail("external ADB must not be stopped"))
    monkeypatch.setattr(plugins.psutil, "process_iter", lambda *args: [owned, external])
    service._stop_managed_adb()
    assert calls == ["owned"]


def test_cleanup_cannot_remove_external_environment(service, tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="插件目录之外"):
        service._remove_directory("python", external)
    assert (external / "keep.txt").read_text() == "keep"


def test_python_dependency_migration_failure_preserves_old_environment(
    service, tmp_path, monkeypatch
):
    source = runtime(tmp_path, "python")
    service.install("python", package("3.13.14"), source=source)
    previous = service.directory("python")
    executable = previous / "env/Scripts/python.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    calls = []

    def execute(args, cancelled):
        calls.append(args)
        if "freeze" in args:
            return "incompatible-library==1.0\n"
        if "install" in args:
            raise RuntimeError("incompatible-library is unavailable")
        return ""

    monkeypatch.setattr(service, "_run", execute)
    with pytest.raises(RuntimeError, match="incompatible-library"):
        service.install("python", package("3.14.7"), source=source)
    assert service.directory("python") == previous
    assert any("venv" in args for args in calls)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows clean edition")
def test_clean_frozen_python_never_uses_host_python(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    environment = PythonEnvironment(AppPaths(tmp_path), ConfigStore(AppPaths(tmp_path)))
    assert not environment.ensure_ready().available
    assert environment.execution_executable() is None
    assert not (tmp_path / "python").exists()


def test_record_rejects_outside_directory(service):
    root = service.paths.plugins_dir / "python"
    root.mkdir(parents=True)
    (root / "installed.json").write_text('{"directory":"../escape"}')
    with pytest.raises(ValueError):
        plugin_record(service.paths, "python")


def test_windows_update_asset_keeps_edition():
    assert update_asset_name("win32", edition="Clean") == "PopTools-Clean-Setup.exe"
    assert update_asset_name("win32", edition="Bundled") == "PopTools-Setup.exe"
    assert update_asset_name("darwin", "arm64", "Clean") == "PopTools-macos-arm64.zip"


def test_controller_finishes_before_notifying_consumers(service, monkeypatch, qtbot):
    from poptools.viewmodels.plugin_controller import PluginController

    monkeypatch.setattr(
        "poptools.viewmodels.plugin_controller.discover_package", lambda _: package()
    )
    controller = PluginController(service)
    notifications = []
    controller.completed.connect(
        lambda plugin, success, message: notifications.append(
            (plugin, success, controller.mutating)
        )
    )
    assert controller.operate("powershell", "check")
    qtbot.waitUntil(lambda: bool(notifications))
    assert notifications == [("powershell", True, False)]
    assert not controller._jobs
    assert controller.plugins[2]["latest"] == "7.6.3"


def test_controller_blocks_mutations_during_active_tasks(service, qtbot):
    from poptools.viewmodels.plugin_controller import PluginController

    controller = PluginController(service)
    controller.busy_check = lambda _: True
    assert not controller.operate("python", "uninstall")
    assert "请先结束" in controller.plugins[0]["status"]


def test_migration_failure_keeps_legacy_runtime(service, tmp_path, monkeypatch):
    legacy = tmp_path / "old-app/runtime/python"
    legacy.mkdir(parents=True)
    (legacy / "python.exe").touch()
    (legacy / "manifest.json").write_text(
        json.dumps(
            {"version": "3.13.14", "sha256": "a" * 64, "url": "https://example.test/python.nupkg"}
        )
    )

    def fail(*args):
        raise RuntimeError("dependency migration failed")

    monkeypatch.setattr(service, "_run", fail)
    with pytest.raises(RuntimeError, match="dependency migration failed"):
        service.migrate(tmp_path / "old-app")
    assert (legacy / "python.exe").exists()
    assert not service.record("python")
