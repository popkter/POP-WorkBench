import os

# Keep QML tests aligned with the application startup configuration.  GitHub
# Actions installs a standalone Qt SDK for the native build, and that SDK can
# otherwise make QtQuick.Controls auto-select its Windows style instead of the
# Basic style shipped with the PySide runtime used by the tests.
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

# pytest-qt waits for frameSwapped using temporary event loops. Keep rendering
# on the GUI thread so a late render-thread callback cannot reach a deleted loop.
os.environ.setdefault("QSG_RENDER_LOOP", "basic")
