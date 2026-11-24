"""Expose bundled Qt DLLs to dynamically loaded QML plugins on Windows."""

import atexit
import os
import sys

if sys.platform == "win32":
    qt_directory = os.path.join(sys._MEIPASS, "PySide6")
    if os.path.isdir(qt_directory):
        atexit.register(os.add_dll_directory(qt_directory).close)
