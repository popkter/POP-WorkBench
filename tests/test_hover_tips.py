import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.mark.gui
def test_hover_tips_loads_and_opens_with_custom_component(qapp, qtbot) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "HoverTipsHarness.qml"))
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"

ApplicationWindow {
    width: 320
    height: 180
    visible: true

    Rectangle {
        x: 120
        y: 80
        width: 80
        height: 40

        HoverTips {
            objectName: "hoverTips"
            visible: false
            text: "Custom tip"
            delay: 0
        }
    }
}
""",
        base_url,
    )

    window = component.create()
    assert isinstance(window, QWindow), [error.toString() for error in component.errors()]
    assert QTest.qWaitForWindowExposed(window)
    QTest.qWait(20)

    tips = window.findChild(QObject, "hoverTips")
    assert tips is not None
    tips.setProperty("visible", True)
    qtbot.waitUntil(lambda: tips.property("opened") is True, timeout=1000)
    assert tips.property("opened") is True
    assert tips.property("text") == "Custom tip"

    window.close()
    window.deleteLater()
