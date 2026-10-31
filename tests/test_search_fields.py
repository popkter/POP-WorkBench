import pytest
from PySide6.QtCore import QMetaObject, QObject, Qt
from PySide6.QtTest import QTest

from poptools.domain.models import ToolSection
from test_floating_launcher import create_tool, ids
from test_floating_launcher import launcher as launcher
from test_zio_theme import zio_app as zio_app


def test_search_filters_are_owned_by_each_page_and_floating_launcher(launcher):
    floating, backend, _, _ = launcher
    alpha = create_tool(backend, "甲乙丙丁")
    beta = create_tool(backend, "悬浮窗独立搜索")
    floating.refreshTools()
    backend.setToolSearchQuery("甲乙丙丁")
    assert ids(backend.toolsModel) == [alpha.id]
    assert set(ids(floating.toolsModel)) == {alpha.id, beta.id}

    presets = backend.registry.for_section(ToolSection.PRESET)
    backend.navigate("preset")
    assert len(ids(backend.toolsModel)) == len(presets) > 0
    assert backend.presetSearchQuery == ""
    backend.setToolSearchQuery(presets[0].title)
    preset_matches = ids(backend.toolsModel)
    assert presets[0].id in preset_matches
    backend.navigate("custom")
    assert backend.customScriptSearchQuery == "甲乙丙丁"
    assert ids(backend.toolsModel) == [alpha.id]

    floating.setToolSearchQuery("悬浮窗")
    assert ids(floating.toolsModel) == [beta.id]
    assert ids(backend.toolsModel) == [alpha.id]
    backend.setSectionSearchQuery("preset", "")
    assert ids(backend.toolsModel) == [alpha.id]
    backend.navigate("preset")
    assert len(ids(backend.toolsModel)) == len(presets)
    assert ids(floating.toolsModel) == [beta.id]


@pytest.mark.gui
@pytest.mark.parametrize("theme", ["light", "dark", "decade", "zio"])
def test_search_boxes_clear_independently_and_keep_their_own_text(zio_app, qtbot, theme):
    window, floating, backend, settings, _, warnings = zio_app
    settings.saveThemeMode(theme)
    alpha = create_tool(backend, "甲乙丙丁")
    beta = create_tool(backend, "悬浮窗独立搜索")

    def open_main(method):
        window.showNormal()
        window.requestActivate()
        qtbot.waitUntil(window.isActive)
        assert QMetaObject.invokeMethod(window, method)

    def clear_search(search, host):
        button = search.findChild(QObject, search.objectName() + "ClearButton")
        assert button is not None and button.isVisible()
        assert search.property("rightPadding") >= button.width() + 8
        point = button.mapToItem(host.contentItem(), button.boundingRect().center()).toPoint()
        QTest.mouseClick(host, Qt.MouseButton.LeftButton, pos=point)
        assert search.property("text") == ""
        assert not button.isVisible()
        assert search.hasActiveFocus()

    open_main("openCustomScriptsPage")
    custom_page = window.findChild(QObject, "customScriptsPage")
    custom = custom_page.findChild(QObject, "scriptListSearch")
    preset = window.findChild(QObject, "presetListSearch")
    assert custom.property("text") == ""
    custom.setProperty("text", "甲乙丙丁")
    assert ids(backend.toolsModel) == [alpha.id]
    open_main("openPresetFunctionsPage")
    assert preset.property("text") == ""
    assert len(ids(backend.toolsModel)) > 0
    preset.setProperty("text", "预设页自己的查询")
    assert not ids(backend.toolsModel)
    open_main("openCustomScriptsPage")
    assert custom.property("text") == "甲乙丙丁"
    assert ids(backend.toolsModel) == [alpha.id]

    window.hide()
    qtbot.waitUntil(lambda: floating.visible)
    if not floating.expanded:
        floating.toggleExpanded()
    panel = floating._panel
    qtbot.waitUntil(lambda: panel.property("revealProgress") == 1)
    name = ("zioDockSearch" if theme == "zio" else
            "floatingTitleSearch" if theme == "decade" else "scriptListSearch")
    floating_search = panel.findChild(QObject, name)
    assert floating_search.property("text") == ""
    floating_search.setProperty("text", "悬浮窗")
    assert ids(floating.searchResultsModel) == [beta.id]
    assert custom.property("text") == "甲乙丙丁"
    assert preset.property("text") == "预设页自己的查询"
    assert ids(backend.toolsModel) == [alpha.id]
    clear_search(floating_search, panel)
    assert set(ids(floating.searchResultsModel)) == {alpha.id, beta.id}
    floating_search.setProperty("text", "悬浮窗")

    open_main("openPresetFunctionsPage")
    assert preset.property("text") == "预设页自己的查询"
    clear_search(preset, window)
    assert len(ids(backend.toolsModel)) > 0
    assert custom.property("text") == "甲乙丙丁"
    assert floating_search.property("text") == "悬浮窗"
    open_main("openCustomScriptsPage")
    clear_search(custom, window)
    assert set(ids(backend.toolsModel)) == {alpha.id, beta.id}
    assert preset.property("text") == ""
    assert floating_search.property("text") == "悬浮窗"
    assert not warnings, warnings
