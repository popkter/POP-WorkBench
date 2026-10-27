from pathlib import Path

import pytest
from PySide6.QtCore import QMetaObject, QObject, Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.paths import AppPaths, package_root
from poptools.viewmodels.settings_controller import SettingsController


@pytest.mark.gui
@pytest.mark.parametrize("size", [(1362, 1024), (960, 720), (700, 600)])
def test_native_guide_navigation_theme_close_and_reopen(qapp, qtbot, tmp_path, size):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    controller = SettingsController(store, PythonEnvironment(paths, store))
    controller.saveThemeMode("light")
    engine = QQmlEngine()
    engine.rootContext().setContextProperty("backend", controller)
    component = QQmlComponent(engine)
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"
import "theme"
ApplicationWindow {
    id: window; width: 1362; height: 1024; visible: true
    Binding { target: Theme; property: "darkMode"; value: backend.darkTheme }
    UserGuideDialog { id: guide; controller: backend; parentWindow: window }
    function reopen() { guide.open() }
    Component.onCompleted: guide.open()
}
""",
        QUrl.fromLocalFile(str(package_root() / "ui/qml/GuideHarness.qml")),
    )
    window = component.create()
    assert window is not None, [e.toString() for e in component.errors()]
    try:
        window.setWidth(size[0])
        window.setHeight(size[1])
        qtbot.wait(80)
        dialog = window.findChild(QObject, "userGuideDialog")
        qtbot.waitUntil(lambda: dialog.property("opened"))
        assert dialog.property("width") <= size[0] - 24
        assert dialog.property("height") <= size[1] - 24
        assert dialog.property("padding") == 24
        background = dialog.property("background")
        assert isinstance(background, QQuickItem)
        light_color = background.property("fillColor")
        controller.saveThemeMode("dark")
        qtbot.wait(30)
        assert background.property("fillColor") != light_color
        controller.saveThemeMode("light")
        for index in range(6):
            dialog.setProperty("sectionIndex", index)
            qtbot.wait(30)
            scroll = window.findChild(QObject, "guideScroll")
            assert scroll.property("height") > 100
            assert scroll.property("contentHeight") > 0
            if index == 2:
                editor = window.findChild(QObject, "guideTemplateEditor")
                assert editor is not None
                editor.setProperty("text", "echo ${name:hello}")
                qtbot.waitUntil(
                    lambda: (
                        window.findChild(QObject, "guideTemplateResult").property("text")
                        == "echo hello"
                    )
                )
        assert QMetaObject.invokeMethod(dialog, "finishGuide")
        qtbot.waitUntil(lambda: not dialog.property("visible"))
        assert controller.userGuideSeen
        assert QMetaObject.invokeMethod(window, "reopen")
        qtbot.waitUntil(lambda: dialog.property("opened"))
        assert dialog.property("sectionIndex") == 0
        QTest.keyClick(window, Qt.Key.Key_Escape)
        qtbot.waitUntil(lambda: not dialog.property("visible"))
    finally:
        window.close()
        window.deleteLater()
        engine.deleteLater()


def test_guide_content_copy_and_preview_use_application_parser(qapp, tmp_path):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    controller = SettingsController(store, PythonEnvironment(paths, store))
    sections = controller.userGuideSections
    assert [s["id"] for s in sections] == [
        "features",
        "start",
        "syntax",
        "templates",
        "tips",
        "plugins",
    ]
    templates = [c["code"] for c in sections[3]["cards"] if "code" in c]
    assert len(templates) == 3
    assert "1 <= count <= 100" in templates[2]
    controller.copyGuideText(templates[1])
    assert QGuiApplication.clipboard().text() == templates[1]
    example = 'Var logs = ${日志目录@dir}\necho "${logs}" ${开关:开启=1|关闭=0}'
    result = controller.previewGuideTemplate(example, {"logs": "C:/My Logs", "开关": "0"})
    assert result["result"] == 'echo "C:/My Logs" 0'
    assert not result["error"]
    assert controller.previewGuideTemplate("echo ${invalid-name}", {})["error"]


def test_release_excludes_browser_runtime_on_windows_and_macos():
    root = Path(__file__).resolve().parents[1]
    source = (root / "packaging/poptools.spec").read_text(encoding="utf-8")
    scope = {}
    exec(source[source.index("UNUSED_QT_QML_PREFIXES") : source.index("common_datas =")], scope)
    keep = scope["keep_qt_entry"]
    for name in (
        "PySide6/Qt6WebEngineCore.dll",
        "PySide6/QtWebEngineProcess.exe",
        "PySide6/resources/qtwebengine_devtools_resources.debug.pak",
        "PySide6/resources/icudtl.dat",
        "PySide6/Qt/resources/v8_context_snapshot.bin",
        "PySide6/Qt/lib/QtWebEngineCore.framework/Helpers/QtWebEngineProcess.app",
    ):
        assert not keep((name, "", ""))
    assert keep(("PySide6/Qt6Quick.dll", "", ""))
    assert keep(("poptools/resources/help/guide.json", "", ""))
