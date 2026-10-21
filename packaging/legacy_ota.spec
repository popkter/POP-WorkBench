# PyInstaller supplies the spec evaluation globals.
# ruff: noqa: F821
from pathlib import Path

ROOT = Path(SPECPATH).parent
installer = ROOT / "dist" / "PopTools-Setup.exe"
checksum = installer.with_suffix(".exe.sha256")
if not installer.is_file() or not checksum.is_file():
    raise RuntimeError("Build the matching Bundled installer before the legacy OTA bridge")

a = Analysis(
    [str(ROOT / "packaging" / "legacy_ota.py")],
    pathex=[], binaries=[],
    datas=[(str(installer), "."), (str(checksum), "."),
           (str(ROOT / "packaging" / "legacy_ota.ps1"), ".")],
    hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=["PySide6"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    name="PopTools", debug=False, strip=False, upx=False, console=False,
    icon=str(ROOT / "src" / "poptools" / "resources" / "icons" / "app-icon.ico"),
)
