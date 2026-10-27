"""Standalone bridge for clients which replace their EXE with PopTools.exe.

Keep this entry point independent of poptools and Qt. The release build embeds
the matching Bundled installer and its checksum in a PyInstaller one-file EXE.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path


def prepare(bundle: Path, target: Path, updates: Path) -> Path:
    updates.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="legacy-ota-", dir=updates)).resolve()
    try:
        installer = staging / "PopTools-Setup.exe"
        shutil.copyfile(bundle / installer.name, installer)
        expected = (bundle / "PopTools-Setup.exe.sha256").read_text("ascii").split()[0]
        with installer.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if len(expected) != 64 or actual != expected.lower():
            raise ValueError("内置安装包 SHA-256 校验失败")
        # Windows PowerShell 5.1 requires a BOM for Chinese string literals.
        (staging / "apply.ps1").write_text(
            (bundle / "legacy_ota.ps1").read_text(encoding="utf-8-sig"),
            encoding="utf-8-sig",
        )
        config = {
            "target": str(target.resolve()),
            "process_id": os.getpid(),
            "timeout_seconds": 90,
        }
        (staging / "update.json").write_text(json.dumps(config), encoding="utf-8")
    except Exception as exc:
        (staging / "bridge-error.txt").write_text(str(exc), encoding="utf-8")
        raise RuntimeError(f"{exc}\n更新文件和日志：{staging}") from exc
    return staging


def main() -> int:
    staging = None
    try:
        if sys.platform != "win32" or not getattr(sys, "frozen", False):
            raise RuntimeError("兼容升级程序仅支持 Windows 发布版本")
        bundle = Path(sys._MEIPASS)
        data = Path(os.environ.get("POPTOOLS_DATA_DIR") or (
            Path(os.environ["LOCALAPPDATA"]) / "PopTools"
        ))
        staging = prepare(bundle, Path(sys.executable), data / "updates")
        powershell = (Path(os.environ["SYSTEMROOT"]) / "System32"
                      / "WindowsPowerShell" / "v1.0" / "powershell.exe")
        env = os.environ.copy()
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        # Do not pass PyInstaller's private DLL search directory to Setup or
        # the installed application (both run after this one-file app exits).
        ctypes.windll.kernel32.SetDllDirectoryW(None)
        with (staging / "helper.log").open("ab") as output:
            subprocess.Popen(
                [str(powershell), "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-ExecutionPolicy", "Bypass", "-File", str(staging / "apply.ps1")],
                cwd=staging, env=env, stdin=subprocess.DEVNULL,
                stdout=output, stderr=output,
                creationflags=subprocess.CREATE_NO_WINDOW,
                close_fds=True,
            )
        return 0
    except Exception as exc:
        message = f"无法启动兼容升级：{exc}"
        if staging is not None:
            # Still show the error if the disk is full or read-only.
            with suppress(OSError):
                (staging / "bridge-error.txt").write_text(str(exc), encoding="utf-8")
            message += f"\n更新文件和日志：{staging}"
        if sys.platform == "win32":
            ctypes.windll.user32.MessageBoxW(
                None, message, "泡泡的工作台更新失败", 0x10
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
