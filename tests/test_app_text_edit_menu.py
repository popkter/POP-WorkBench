from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QGuiApplication, QWheelEvent, QWindow
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from poptools.paths import package_root


@pytest.mark.gui
def test_left_click_focuses_empty_field_through_menu_overlay(qapp) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "MenuHarness.qml"))
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"

ApplicationWindow {
    width: 320
    height: 180
    visible: true
    TextField {
        id: populatedField
        objectName: "populatedField"
        x: 20
        y: 20
        width: 260
        height: 48
        text: "PopTools"
        AppTextEditMenu { target: populatedField }
    }
    TextField {
        id: emptyField
        objectName: "emptyField"
        x: 20
        y: 92
        width: 260
        height: 48
        placeholderText: "Empty"
        AppTextEditMenu { target: emptyField }
    }
}
""",
        base_url,
    )
    window = component.create()
    assert isinstance(window, QWindow), [error.toString() for error in component.errors()]
    assert QTest.qWaitForWindowExposed(window)

    populated_field = window.findChild(QObject, "populatedField")
    empty_field = window.findChild(QObject, "emptyField")
    assert populated_field is not None
    assert empty_field is not None

    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(60, 42))
    QGuiApplication.processEvents()
    assert populated_field.property("activeFocus") is True

    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=QPoint(60, 114))
    QGuiApplication.processEvents()
    assert empty_field.property("activeFocus") is True
    assert populated_field.property("activeFocus") is False
    window.close()


@pytest.mark.gui
def test_right_click_opens_app_text_edit_menu(qapp) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "MenuHarness.qml"))
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"

ApplicationWindow {
    width: 320
    height: 160
    visible: true
    TextField {
        id: field
        objectName: "editMenuTestField"
        x: 20
        y: 20
        width: 260
        height: 48
        text: "PopTools"
        AppTextEditMenu { target: field }
    }
}
""",
        base_url,
    )
    window = component.create()
    assert isinstance(window, QWindow), [error.toString() for error in component.errors()]
    assert QTest.qWaitForWindowExposed(window)

    QTest.mouseClick(window, Qt.MouseButton.RightButton, pos=QPoint(60, 42))
    QGuiApplication.processEvents()

    menu = window.findChild(QObject, "appTextEditMenu")
    assert menu is not None
    assert menu.property("opened") is True
    window.close()


@pytest.mark.gui
def test_left_click_focuses_field_immediately_after_rapid_wheel_events(qapp) -> None:
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    base_url = QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "MenuHarness.qml"))
    component.setData(
        b"""
import QtQuick
import QtQuick.Controls
import "components"

ApplicationWindow {
    width: 320
    height: 180
    visible: true
    DesktopScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        contentHeight: 600
        Item {
            width: parent.width
            height: 600
            TextField {
                id: field
                objectName: "wheelFocusField"
                x: 20
                y: 60
                width: 260
                height: 48
                text: "PopTools"
                AppTextEditMenu { target: field }
            }
        }
    }
}
""",
        base_url,
    )
    window = component.create()
    assert isinstance(window, QWindow), [error.toString() for error in component.errors()]
    assert QTest.qWaitForWindowExposed(window)

    field = window.findChild(QQuickItem, "wheelFocusField")
    assert field is not None

    wheel_position = QPointF(150, 90)
    for index in range(20):
        wheel = QWheelEvent(
            wheel_position,
            wheel_position,
            QPoint(),
            QPoint(0, 120 if index % 2 else -120),
            Qt.MouseButton.NoButton,
            Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.ScrollUpdate,
            False,
        )
        QGuiApplication.sendEvent(window, wheel)

    wheel_end = QWheelEvent(
        wheel_position,
        wheel_position,
        QPoint(),
        QPoint(),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.ScrollEnd,
        False,
    )
    QGuiApplication.sendEvent(window, wheel_end)

    QGuiApplication.processEvents()
    field_position = field.mapToScene(QPointF(30, 24)).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=field_position)
    QTest.qWait(10)
    assert field.property("activeFocus") is True
    window.close()
