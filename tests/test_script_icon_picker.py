from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, QPoint, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.mark.gui
def test_script_icon_picker_opens_and_selects_an_icon(qapp) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "IconHarness.qml"))
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"

ApplicationWindow {
    width: 360
    height: 320
    visible: true
    ScriptIconPicker {
        x: 20
        y: 20
        onIconSelected: function(iconName) { selectedIcon = iconName }
    }
}
""",
        base_url,
    )
    window = component.create()
    assert isinstance(window, QWindow), [error.toString() for error in component.errors()]
    assert QTest.qWaitForWindowExposed(window)

    picker = window.findChild(QObject, "scriptIconPicker")
    popup = window.findChild(QObject, "scriptIconPickerPopup")
    assert picker is not None
    assert popup is not None

    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(40, 40))
    QGuiApplication.processEvents()
    assert popup.property("opened") is True

    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(92, 92))
    QGuiApplication.processEvents()
    assert picker.property("selectedIcon") == "code"
    assert popup.property("opened") is False
    window.close()
