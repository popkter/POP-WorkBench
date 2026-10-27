from types import SimpleNamespace

import pytest
from PySide6.QtCore import QMetaObject, QUrl
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtTest import QTest

from poptools.domain.models import ParameterKind
from poptools.domain.parameter_templates import (
    render_template,
    synchronize_parameters,
    update_parameter_default,
)
from poptools.paths import package_root
from poptools.viewmodels.app_controller import AppController


@pytest.mark.parametrize("suffix", ["", r":C:\日志 folder"])
def test_directory_parameter_parses_and_renders(suffix):
    template = 'Get-ChildItem "${目录@dir' + suffix + '}"'
    parameter, = synchronize_parameters([template])
    assert parameter.id == "目录"
    assert parameter.kind == ParameterKind.DIRECTORY
    assert parameter.default == suffix.removeprefix(":")
    assert render_template(template, {"目录": "D:/日志 folder"}) == (
        'Get-ChildItem "D:/日志 folder"'
    )


@pytest.mark.parametrize("declared", [False, True])
def test_directory_default_round_trip(declared):
    template = (
        'Var path = ${目录@dir:C:/old}\nWrite-Output "${path}"'
        if declared else 'Write-Output "${path@dir:C:/old}"'
    )
    updated = update_parameter_default(template, "path", "D:/new folder")
    parameter, = synchronize_parameters([updated])
    assert parameter.kind == ParameterKind.DIRECTORY
    assert parameter.default == "D:/new folder"
    assert parameter.label == ("目录" if declared else "path")
    assert render_template(updated, {"path": parameter.default}) == (
        'Write-Output "D:/new folder"'
    )
    cleared = update_parameter_default(updated, "path", "")
    assert "@dir}" in cleared
    assert synchronize_parameters([cleared])[0].kind == ParameterKind.DIRECTORY


def test_editing_directory_type_and_rejecting_choices():
    directory = synchronize_parameters(["${path@dir}"])
    assert synchronize_parameters(["${path}"], directory)[0].kind == ParameterKind.TEXT
    assert synchronize_parameters(["${path@file}"], directory)[0].kind == ParameterKind.FILE
    with pytest.raises(ValueError, match="下拉"):
        synchronize_parameters(["${path@dir:one=1|two=2}"])


@pytest.mark.parametrize("cancelled", [False, True])
def test_directory_picker_starts_at_current_folder(monkeypatch, tmp_path, cancelled):
    current = tmp_path / "当前目录"
    current.mkdir()
    selected = "" if cancelled else str(tmp_path / "selected folder")
    calls = []

    def choose(parent, title, start):
        calls.append((title, start))
        return selected

    monkeypatch.setattr(
        "poptools.viewmodels.app_controller.QFileDialog.getExistingDirectory", choose
    )
    assert AppController.chooseParameterDirectory(SimpleNamespace(), str(current)) == selected
    assert calls == [("选择文件夹", str(current))]


@pytest.mark.gui
@pytest.mark.parametrize("surface", ["CommandWorkspace", "CustomToolDetailPanel"])
def test_directory_button_updates_value_and_preserves_it_on_cancel(qapp, surface):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(
        ('''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: host
    width: 700; height: 700; visible: true
    property string nextSelection: "D:/chosen folder"
    property string requestedPath: ""
    property var values: ({})
    SURFACE {
        anchors.fill: parent
        EXTRA_PROPERTIES
        parentWindow: host
        parameterValues: host.values
        controller: ({
            selectedTool: {section: "custom", editable: true, parameters: [
                {id: "path", label: "Path", kind: "directory", default: "C:/initial"}
            ]},
            running: false,
            consoleText: "", statusText: "",
            updateScrcpyGeometry: function() {},
            chooseParameterDirectory: function(path) {
                host.requestedPath = path
                return host.nextSelection
            }
        })
    }
    function currentValue() { return values.path }
}
'''.replace("SURFACE", surface).replace(
            "EXTRA_PROPERTIES",
            "androidBackend: null; displayedTool: controller.selectedTool"
            if surface == "CustomToolDetailPanel" else "",
        )).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/DirectoryParameterHarness.qml")),
    )
    root = component.create()
    assert isinstance(root, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(root)
        QTest.qWait(20)
        def visual_items(item):
            yield item
            for child in item.childItems():
                yield from visual_items(child)

        button = next(child for child in visual_items(root.contentItem())
                      if child.property("text") == "选择文件夹"
                      and child.metaObject().indexOfMethod("clicked()") >= 0)
        assert QMetaObject.invokeMethod(button, "clicked")
        assert root.property("requestedPath") == "C:/initial"
        assert root.property("values").toVariant()["path"] == "D:/chosen folder"
        root.setProperty("nextSelection", "")
        assert QMetaObject.invokeMethod(button, "clicked")
        assert root.property("requestedPath") == "D:/chosen folder"
        assert root.property("values").toVariant()["path"] == "D:/chosen folder"
    finally:
        root.close()
        root.deleteLater()
