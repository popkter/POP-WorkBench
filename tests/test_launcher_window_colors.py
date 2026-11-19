import pytest
from PySide6.QtQml import QQmlEngine, QQmlExpression

from test_floating_launcher import create_tool
from test_floating_launcher import launcher as launcher
from test_zio_theme import zio_app as zio_app


@pytest.mark.gui
@pytest.mark.parametrize("style,accent", [("zio", "#d9ae48"), ("decade", "#f12786")])
def test_real_launcher_colors_ignore_application_theme(zio_app, qtbot, style, accent):
    main, controller, backend, settings, _, warnings = zio_app
    create_tool(backend, "原有悬浮窗样式", command="echo hello")
    settings.saveFloatingLauncherStyle(style)
    panel = controller._panel
    qtbot.waitUntil(lambda: panel.isVisible() and panel.property("revealProgress") == 1)

    def items(item):
        yield item
        for child in item.childItems():
            yield from items(child)

    for mode in ("light", "dark"):
        for material in ("material3", "glass"):
            settings.saveThemeMode(mode)
            settings.saveThemeStyle(material)
            qtbot.wait(100)
            panel = controller._panel
            frame = panel.grabWindow()
            checked = []
            for item in items(panel.contentItem()):
                if item.isVisible() and item.metaObject().indexOfProperty("_visualPalette") >= 0:
                    checked.append(item.objectName() or item.metaObject().className())
                    context = QQmlEngine.contextForObject(item)
                    color = QQmlExpression(context, item, "_visualPalette.primary").evaluate()[0]
                    glass = QQmlExpression(context, item, "_visualPalette.glassMode").evaluate()[0]
                    assert color.name() == accent, checked[-1]
                    assert not glass, checked[-1]
            assert checked
            assert frame.save(f".tmp-launcher-{style}-{mode}-{material}.png")
            assert main.property("chromeBackgroundColor").name() != "#191813"
    assert not warnings, warnings
