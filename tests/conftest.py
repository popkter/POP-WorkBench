import atexit
import os
import sys
from pathlib import Path

import PySide6

if sys.platform == "win32":
    # QML plugins load their Qt DLL dependencies at runtime. Make the PySide6
    # wheel's DLLs available even when the native build uses a separate Qt SDK.
    qt_dll_directory = Path(PySide6.__file__).resolve().parent
    atexit.register(os.add_dll_directory(str(qt_dll_directory)).close)

# Keep QML tests aligned with the application startup configuration.  GitHub
# Actions installs a standalone Qt SDK for the native build, and that SDK can
# otherwise make QtQuick.Controls auto-select its Windows style instead of the
# Basic style shipped with the PySide runtime used by the tests.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

# pytest-qt waits for frameSwapped using temporary event loops. Keep rendering
# on the GUI thread so a late render-thread callback cannot reach a deleted loop.
os.environ.setdefault("QSG_RENDER_LOOP", "basic")
