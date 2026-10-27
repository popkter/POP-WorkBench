import platform
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
SRC = ROOT / "src"
PACKAGE = SRC / "poptools"
PYPROJECT = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
APP_VERSION = re.search(r'(?m)^version\s*=\s*"([^"]+)"', PYPROJECT).group(1)
BUILD_VERSION_FILE = PACKAGE / "_build_version.py"
BUILD_VERSION_TEXT = (
    BUILD_VERSION_FILE.read_text(encoding="utf-8")
    if BUILD_VERSION_FILE.is_file()
    else ""
)
BUILD_VERSION_MATCH = re.search(r"(\d{4})-(\d{2})-(\d{2})_", BUILD_VERSION_TEXT)
BUNDLE_VERSION = (
    "".join(BUILD_VERSION_MATCH.groups()) if BUILD_VERSION_MATCH else "1"
)

windows_version_info = None
if sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo,
        StringFileInfo,
        StringStruct,
        StringTable,
        VarFileInfo,
        VarStruct,
        VSVersionInfo,
    )

    # Windows may use EXE metadata for the sender name of tray notifications.
    # Keep the legacy filename for OTA compatibility, but give it the new brand.
    windows_version = tuple(int(part) for part in APP_VERSION.split("."))
    windows_version = (windows_version + (0, 0, 0, 0))[:4]
    windows_version_info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=windows_version, prodvers=windows_version),
        kids=[
            StringFileInfo([
                StringTable("080404B0", [
                    StringStruct("FileDescription", "泡泡的工作台 · Pop’s Workbench"),
                    StringStruct("ProductName", "泡泡的工作台 · Pop’s Workbench"),
                    StringStruct("FileVersion", APP_VERSION),
                    StringStruct("ProductVersion", APP_VERSION),
                    StringStruct("OriginalFilename", "泡泡工具箱.exe"),
                ]),
            ]),
            VarFileInfo([VarStruct("Translation", [0x0804, 1200])]),
        ],
    )


UNUSED_QT_QML_PREFIXES = (
    "pyside6/qml/qt3d/",
    "pyside6/qml/qtcharts/",
    "pyside6/qml/qtdatavisualization/",
    "pyside6/qml/qtgraphs/",
    "pyside6/qml/qtlocation/",
    "pyside6/qml/qtmultimedia/",
    "pyside6/qml/qtpositioning/",
    "pyside6/qml/qtquick/pdf/",
    "pyside6/qml/qtquick/scene3d/",
    "pyside6/qml/qtquick/virtualkeyboard/",
    "pyside6/qml/qtquick3d/",
    "pyside6/qml/qtspatialaudio/",
    "pyside6/qml/qttexttospeech/",
)
UNUSED_CONTROL_STYLE_PREFIXES = (
    "pyside6/qml/qtquick/controls/fluentwinui3/",
    "pyside6/qml/qtquick/controls/fusion/",
    "pyside6/qml/qtquick/controls/imagine/",
    "pyside6/qml/qtquick/controls/macos/",
    "pyside6/qml/qtquick/controls/material/",
    "pyside6/qml/qtquick/controls/universal/",
)
UNUSED_QT_BINARY_PREFIXES = (
    "pyside6/qt63d",
    "pyside6/qt6charts",
    "pyside6/qt6datavisualization",
    "pyside6/qt6graphs",
    "pyside6/qt6location",
    "pyside6/qt6pdf",
    "pyside6/qt6quick3d",
    "pyside6/qt6spatialaudio",
    "pyside6/qt6texttospeech",
    "pyside6/qt6virtualkeyboard",
)
UNUSED_CONTROL_STYLE_BINARIES = (
    "pyside6/qt6quickcontrols2fluentwinui3",
    "pyside6/qt6quickcontrols2fusion",
    "pyside6/qt6quickcontrols2imagine",
    "pyside6/qt6quickcontrols2macos",
    "pyside6/qt6quickcontrols2material",
    "pyside6/qt6quickcontrols2universal",
)


def keep_qt_entry(entry):
    destination = entry[0].replace("\\", "/").lower()
    destination = destination.replace("pyside6/qt/qml/", "pyside6/qml/")
    # The user guide uses native Qt Quick controls, so no browser runtime is needed.
    if any(token in destination for token in ("webengine", "webchannel", "webview")):
        return False
    if destination.startswith(("pyside6/resources/", "pyside6/qt/resources/")):
        filename = destination.rsplit("/", 1)[-1]
        if filename == "icudtl.dat" or "devtools" in filename or ".debug." in filename or filename.startswith("v8_context_snapshot"):
            return False
    # Qt uses the Windows ICU compatibility DLLs from System32. Build-machine
    # tools such as Poppler may prepend incompatible ICU DLLs to PATH, which
    # PyInstaller would otherwise collect beside the application.
    if destination == "icuuc.dll" or destination == "icuin.dll" or (
        destination.startswith("icudt") and destination.endswith(".dll")
    ):
        return False
    if destination.startswith(UNUSED_QT_QML_PREFIXES + UNUSED_CONTROL_STYLE_PREFIXES):
        return False
    if destination.startswith(UNUSED_QT_BINARY_PREFIXES + UNUSED_CONTROL_STYLE_BINARIES):
        return False
    if destination.startswith("pyside6/plugins/platforminputcontexts/qtvirtualkeyboard"):
        return False
    if destination.startswith("pyside6/plugins/qmltooling/"):
        return False
    if "/designer/" in destination or destination.startswith("pyside6/qml/qtquick/tooling/"):
        return False
    if "/qtwebengine_locales/" in destination:
        return destination.endswith(("/en-us.pak", "/zh-cn.pak"))
    if destination.startswith("pyside6/translations/"):
        return destination.endswith(("_en.qm", "_zh_cn.qm"))
    return True

common_datas = [
    (str(ROOT / "THIRD_PARTY_NOTICES.md"), "."),
    (str(ROOT / "native" / "third_party" / "libvterm" / "LICENSE"), "licenses/libvterm"),
    (str(PACKAGE / "ui" / "qml"), "poptools/ui/qml"),
    (str(PACKAGE / "resources" / "tools"), "poptools/resources/tools"),
    (str(PACKAGE / "resources" / "python"), "poptools/resources/python"),
    (str(PACKAGE / "resources" / "fonts"), "poptools/resources/fonts"),
    (str(PACKAGE / "resources" / "help"), "poptools/resources/help"),
    (str(PACKAGE / "resources" / "icons" / "app-icon-ui.png"), "poptools/resources/icons"),
    # QML uses these directly; they must also exist in the frozen application.
    *[(str(icon), "poptools/resources/icons")
      for icon in sorted((PACKAGE / "resources" / "icons").glob("*.svg"))],
]

vendor = PACKAGE / "resources" / "vendor"
python_vendor = vendor / "python"
machine = platform.machine().lower()
architecture = "arm64" if machine in {"arm64", "aarch64"} else "x64"
if sys.platform == "darwin":
    scrcpy_manifest = vendor / f"scrcpy-manifest-macos-{architecture}.json"
    python_manifest = python_vendor / f"python-runtime-macos-{architecture}.json"
    icon_file = PACKAGE / "resources" / "icons" / "app-icon.png"
    runtime_icon_file = icon_file
    hiddenimports = []
    platform_binaries = [
        (str(PACKAGE / "native" / "libpoptools_terminal.dylib"), "poptools/native"),
    ]
else:
    scrcpy_manifest = vendor / "scrcpy-manifest.json"
    python_manifest = python_vendor / "python-runtime.json"
    icon_file = PACKAGE / "resources" / "icons" / "app-icon.ico"
    runtime_icon_file = icon_file
    hiddenimports = collect_submodules("wexpect")
    platform_binaries = [
        (str(PACKAGE / "native" / "poptools_terminal.dll"), "poptools/native"),
    ]

import json

scrcpy_package = vendor / json.loads(scrcpy_manifest.read_text(encoding="utf-8"))["archive"]
python_package = python_vendor / json.loads(python_manifest.read_text(encoding="utf-8"))["file"]
vendor_datas = [
    (str(vendor / "scrcpy-LICENSE.txt"), "poptools/resources/vendor"),
    (str(scrcpy_manifest), "poptools/resources/vendor"),
    (str(python_vendor / "PYTHON-LICENSE.txt"), "poptools/resources/vendor/python"),
    (str(python_manifest), "poptools/resources/vendor/python"),
]
if sys.platform == "win32":
    vendor_datas.append(
        (str(vendor / "powershell-plugin.json"), "poptools/resources/vendor")
    )
else:
    vendor_datas.extend(
        [
            (str(scrcpy_package), "poptools/resources/vendor"),
            (str(python_package), "poptools/resources/vendor/python"),
        ]
    )
datas = [
    *common_datas,
    *vendor_datas,
    (str(runtime_icon_file), "poptools/resources/icons"),
    *copy_metadata("av"),
]

analysis = Analysis(
    [str(PACKAGE / "main.py")],
    pathex=[str(SRC)],
    binaries=platform_binaries,
    datas=datas,
    hiddenimports=hiddenimports + collect_submodules("av"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "mypy",
        "pytest",
        "ruff",
        "PIL",
        "PyInstaller",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtWebChannel",
        "PySide6.QtWebView",
    ],
    noarchive=False,
    optimize=1,
)
analysis.binaries = [entry for entry in analysis.binaries if keep_qt_entry(entry)]
analysis.datas = [entry for entry in analysis.datas if keep_qt_entry(entry)]
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="泡泡工具箱",
    version=windows_version_info,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    icon=str(icon_file),
)

collected = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=sys.platform == "win32",
    name="泡泡工具箱",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collected,
        name="泡泡的工作台.app",
        icon=str(icon_file),
        bundle_identifier="com.poptools.toolbox",
        info_plist={
            "CFBundleDisplayName": "泡泡的工作台 · Pop’s Workbench",
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": BUNDLE_VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
        },
    )
