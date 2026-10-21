from pathlib import Path

import pytest
from PySide6.QtCore import Property, QMetaObject, QObject, QUrl, Slot
from PySide6.QtGui import QFontDatabase
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow

from poptools.paths import package_root


class PluginBackend(QObject):
    def __init__(self):
        super().__init__()
        self.operations = []

    @Property("QVariantList", constant=True)
    def plugins(self):
        return []

    @Slot(str, str, result=bool)
    def operate(self, plugin, action):
        self.operations.append((plugin, action))
        return True


@pytest.mark.parametrize("dark", [False, True])
def test_uninstall_dialog_style_and_confirmation(qapp, qtbot, dark):
    QFontDatabase.addApplicationFont(
        str(package_root() / "resources/fonts/MaterialIconsRound-Regular.otf")
    )
    backend = PluginBackend()
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("pluginBackend", backend)
    engine.rootContext().setContextProperty("dark", dark)
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"
import "theme"
ApplicationWindow {
    width: 960; height: 720; visible: true
    color: Theme.workspaceBackground
    Binding { target: Theme; property: "darkMode"; value: dark }
    PluginManagerPanel { anchors.fill: parent; backend: pluginBackend }
}
""",
        QUrl.fromLocalFile(str(package_root() / "ui/qml/PluginStyleHarness.qml")),
    )
    window = component.create()
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    try:
        dialog = window.findChild(QObject, "pluginUninstallDialog")
        dialog.setProperty("pluginId", "python")
        dialog.setProperty("pluginName", "Python")
        QMetaObject.invokeMethod(dialog, "open")
        qtbot.waitUntil(lambda: dialog.property("opened"))
        assert dialog.property("width") == 420
        assert dialog.property("topPadding") == 20
        assert not backend.operations
        qtbot.wait(150)
        window.grabWindow().save(str(Path("build") / f"plugin-uninstall-{dark}.png"))
        QMetaObject.invokeMethod(dialog, "reject")
        assert not backend.operations
        QMetaObject.invokeMethod(dialog, "open")
        qtbot.waitUntil(lambda: dialog.property("opened"))
        QMetaObject.invokeMethod(window.findChild(QObject, "confirmPluginUninstall"), "clicked")
        assert backend.operations == [("python", "uninstall")]
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()
