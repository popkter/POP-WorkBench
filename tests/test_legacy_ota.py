from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

import pytest

from poptools.infrastructure.app_updater import GitHubReleaseClient, update_asset_name

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_TAGS = (
    "v2026-08-17_1.0.0", "v2026-09-03_1.0.8", "v2026-09-10_1.1.0",
)


def load_bridge():
    spec = importlib.util.spec_from_file_location("legacy_ota", ROOT / "packaging/legacy_ota.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def historical_updater(tag):
    result = subprocess.run(
        ["git", "show", f"{tag}:src/poptools/infrastructure/app_updater.py"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
    )
    module = types.ModuleType("historical_updater")
    # dataclasses resolves annotations through sys.modules.
    sys.modules[module.__name__] = module
    exec(compile(result.stdout, f"{tag}/app_updater.py", "exec"), module.__dict__)
    return module


def payload(digest):
    return {
        "tag_name": "v2026-10-21_1.1.5", "draft": False,
        "assets": [
            {"name": name, "browser_download_url": f"https://example.test/{name}",
             "size": 10, "digest": f"sha256:{digest}"}
            for name in ("PopTools.exe", "PopTools-Setup.exe", "PopTools-Clean-Setup.exe")
        ],
    }


@pytest.mark.parametrize("tag", HISTORICAL_TAGS)
def test_real_historical_client_selects_bridge(tag, monkeypatch):
    old = historical_updater(tag)
    monkeypatch.setattr(old, "UPDATE_ASSET_NAME", "PopTools.exe")
    release = old.GitHubReleaseClient.select_latest_release([payload("a" * 64)])
    assert release.asset_name == "PopTools.exe"
    assert release.sha256 == "a" * 64
    assert old.is_newer_version(release.version, tag.removeprefix("v"))


@pytest.mark.parametrize("edition", ["Bundled", "Clean"])
def test_new_client_still_selects_edition_installer(edition):
    name = update_asset_name("win32", edition=edition)
    release = GitHubReleaseClient.select_latest_release(payload("a" * 64), asset_name=name)
    assert release.asset_name == name
    assert name != "PopTools.exe"


def test_bridge_checks_embedded_payload_and_preserves_failure(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "PopTools-Setup.exe").write_bytes(b"corrupt")
    (bundle / "PopTools-Setup.exe.sha256").write_text("a" * 64)
    updates = tmp_path / "updates"
    with pytest.raises(RuntimeError, match="SHA-256"):
        load_bridge().prepare(bundle, tmp_path / "app.exe", updates)
    staging, = updates.iterdir()
    assert (staging / "bridge-error.txt").is_file()
    assert (staging / "PopTools-Setup.exe").read_bytes() == b"corrupt"


@pytest.fixture(scope="module")
def windows_stub(tmp_path_factory):
    if sys.platform != "win32":
        pytest.skip("Windows process/installer integration")
    compiler = Path(os.environ["SYSTEMROOT"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    if not compiler.is_file():
        pytest.skip(".NET Framework compiler unavailable")
    directory = tmp_path_factory.mktemp("ota-stub")
    source = directory / "stub.cs"
    source.write_text(r'''
using System;
using System.IO;
using System.Reflection;
class Stub {
    static int Main(string[] args) {
        string self = Assembly.GetExecutingAssembly().Location;
        if (Path.GetFileName(self) == "PopTools-Setup.exe") {
            File.WriteAllLines(Environment.GetEnvironmentVariable("OTA_ARGUMENTS"), args);
            if (Environment.GetEnvironmentVariable("OTA_FAIL") == "1") return 7;
            string dir = null;
            foreach (string arg in args) if (arg.StartsWith("/DIR=")) dir = arg.Substring(5);
            File.Copy(Environment.GetEnvironmentVariable("OTA_STUB"),
                      Path.Combine(dir, "泡泡工具箱.exe"), true);
            File.WriteAllText(Environment.GetEnvironmentVariable("OTA_INSTALLED"), "installed");
            return 0;
        }
        if (File.Exists(Environment.GetEnvironmentVariable("OTA_INSTALLED"))) {
            File.WriteAllText(Environment.GetEnvironmentVariable("OTA_STARTED"), "started");
            return 0;
        }
        return 9;
    }
}
''', encoding="utf-8-sig")
    executable = directory / "stub.exe"
    subprocess.run([str(compiler), "/nologo", "/target:winexe", f"/out:{executable}",
                    str(source)], check=True, capture_output=True)
    return executable


def powershell():
    return str(Path(os.environ["SYSTEMROOT"]) / "System32/WindowsPowerShell/v1.0/powershell.exe")


@pytest.fixture(scope="module")
def frozen_bridge(windows_stub, tmp_path_factory):
    # Exercise the shipping spec and real one-file bootloader, with a small
    # installer stand-in so the test never touches the user's installed app.
    project = tmp_path_factory.mktemp("ota-frozen")
    packaging = project / "packaging"
    packaging.mkdir()
    for name in ("legacy_ota.py", "legacy_ota.ps1", "legacy_ota.spec"):
        shutil.copyfile(ROOT / "packaging" / name, packaging / name)
    dist = project / "dist"
    dist.mkdir()
    shutil.copyfile(windows_stub, dist / "PopTools-Setup.exe")
    digest = hashlib.sha256(windows_stub.read_bytes()).hexdigest()
    (dist / "PopTools-Setup.exe.sha256").write_text(digest)
    icons = project / "src/poptools/resources/icons"
    icons.mkdir(parents=True)
    shutil.copyfile(ROOT / "src/poptools/resources/icons/app-icon.ico", icons / "app-icon.ico")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         str(packaging / "legacy_ota.spec")],
        cwd=project, capture_output=True, timeout=180,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    return dist / "PopTools.exe"


@pytest.mark.parametrize("tag", HISTORICAL_TAGS)
def test_historical_copy_to_bridge_to_silent_install(
    tag, frozen_bridge, windows_stub, tmp_path, monkeypatch,
):
    target = tmp_path / "自定义 安装目录" / "泡泡工具箱.exe"
    target.parent.mkdir()
    target.write_bytes(b"old single-file application")
    source = tmp_path / "PopTools.exe"
    updates = tmp_path / "data" / "updates"
    updates.mkdir(parents=True)
    (tmp_path / "data" / "settings.json").write_text("preserve user settings")
    for key, value in {
        "POPTOOLS_DATA_DIR": tmp_path / "data", "POPTOOLS_OTA_TEST_NO_DIALOG": "1",
        "OTA_STUB": windows_stub, "OTA_ARGUMENTS": tmp_path / "arguments.txt",
        "OTA_INSTALLED": tmp_path / "installed", "OTA_STARTED": tmp_path / "started",
    }.items():
        monkeypatch.setenv(key, str(value))
    old = historical_updater(tag)
    data = frozen_bridge.read_bytes()
    metadata = payload(hashlib.sha256(data).hexdigest())
    metadata["assets"][0]["size"] = len(data)
    release = old.GitHubReleaseClient.select_latest_release([metadata])
    response = io.BytesIO(data)
    response.headers = {"Content-Length": str(len(data))}
    monkeypatch.setattr(old.urllib.request, "urlopen", lambda *_args, **_kwargs: response)
    assert old.GitHubReleaseClient.download(release, source) == source
    calls = []

    class Process:
        @staticmethod
        def startDetached(program, arguments, working_directory):
            calls.append((program, arguments))
            return True

    monkeypatch.setattr(old, "QProcess", Process)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    # The process to wait for represents the old application, already exited.
    monkeypatch.setattr(old.os, "getpid", lambda: 2147483000)
    assert old.UpdateInstaller.launch(source, target)
    program, arguments = calls[0]
    result = subprocess.run([program, *arguments], capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
    deadline = time.monotonic() + 30
    while not (tmp_path / "started").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (tmp_path / "started").exists(), list(updates.rglob("*"))
    arguments = (tmp_path / "arguments.txt").read_text(encoding="utf-8-sig")
    assert f"/DIR={target.parent}" in arguments
    assert "/VERYSILENT" in arguments
    assert (tmp_path / "data" / "settings.json").read_text() == "preserve user settings"
    deadline = time.monotonic() + 5
    while list(updates.rglob("PopTools-Setup.exe")) and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not list(updates.rglob("PopTools-Setup.exe"))


@pytest.mark.parametrize("failure", ["installer", "locked"])
def test_helper_failure_keeps_payload_and_never_restarts(
    failure, windows_stub, tmp_path, monkeypatch,
):
    staging = tmp_path / "legacy-ota-test"
    staging.mkdir()
    shutil.copyfile(windows_stub, staging / "PopTools-Setup.exe")
    (staging / "apply.ps1").write_text(
        (ROOT / "packaging/legacy_ota.ps1").read_text(encoding="utf-8-sig"),
        encoding="utf-8-sig",
    )
    target = tmp_path / "泡泡工具箱.exe"
    target.write_bytes(b"bridge")
    (staging / "update.json").write_text(json.dumps({
        "target": str(target), "process_id": 2147483000, "timeout_seconds": 0,
    }), encoding="utf-8")
    monkeypatch.setenv("POPTOOLS_OTA_TEST_NO_DIALOG", "1")
    monkeypatch.setenv("OTA_FAIL", "1")
    monkeypatch.setenv("OTA_ARGUMENTS", str(tmp_path / "arguments"))
    monkeypatch.setenv("OTA_STARTED", str(tmp_path / "started"))
    handle = target.open("rb") if failure == "locked" else None
    try:
        result = subprocess.run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
                                 "-File", str(staging / "apply.ps1")],
                                capture_output=True, timeout=15)
    finally:
        if handle:
            handle.close()
    assert result.returncode == 1
    log = (staging / "migration.log").read_text(encoding="utf-8-sig")
    assert ("7" if failure == "installer" else "超时") in log
    assert (staging / "PopTools-Setup.exe").is_file()
    assert not (tmp_path / "started").exists()
    # The retained helper can be retried once Setup succeeds or the lock clears.
    for key, value in {
        "OTA_FAIL": "0", "OTA_STUB": windows_stub,
        "OTA_INSTALLED": tmp_path / "installed", "OTA_STARTED": tmp_path / "started",
    }.items():
        monkeypatch.setenv(key, str(value))
    result = subprocess.run([powershell(), "-NoProfile", "-ExecutionPolicy", "Bypass",
                             "-File", str(staging / "apply.ps1")],
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    deadline = time.monotonic() + 5
    while not (tmp_path / "started").exists() and time.monotonic() < deadline:
        time.sleep(0.1)
    assert (tmp_path / "started").exists()
    assert not (staging / "PopTools-Setup.exe").exists()
