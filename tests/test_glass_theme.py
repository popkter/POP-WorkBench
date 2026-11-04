import json

import pytest
from PySide6.QtCore import QMetaObject, QObject, QPoint, Qt, QUrl, Slot
from PySide6.QtGui import QColor
from PySide6.QtQml import QQmlComponent, QQmlEngine
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.theme_catalog import ThemeCatalog
from poptools.paths import AppPaths, package_root


def test_glass_catalog_and_independent_mode_persist(tmp_path):
    catalog = ThemeCatalog(package_root() / "ui/qml/theme/configs")
    catalog.refresh()
    assert catalog.contains("glass")
    data = json.loads(catalog.config_json("glass"))
    assert data["name"] == "Glass"
    assert data["colors"]["textPrimary"] == "#0b0f17"
    assert data["darkColors"]["textPrimary"] == "#f3f6fa"
    store = ConfigStore(AppPaths(tmp_path))
    for mode in ("light", "dark", "system", "decade", "zio"):
        store.set_theme_mode(mode)
        store.set_theme_style("glass")
        reloaded = ConfigStore(AppPaths(tmp_path))
        assert reloaded.theme_mode() == mode
        assert reloaded.theme_style() == "glass"


@pytest.mark.gui
def test_glass_render_switch_and_background_mapping(qapp, qtbot):
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    component = QQmlComponent(engine)
    config = json.loads((package_root() / "ui/qml/theme/configs/glass.json")
                        .read_text(encoding="utf-8"))
    code = '''
import QtQuick
import "components"
import "theme"
Window {
    id: host; width: 420; height: 280; visible: true; color: "#202030"
    property bool glass: true
    property bool dark: false
    property bool mechanical: false
    property var config: CONFIG
    readonly property Item glassBackgroundSource: scene
    readonly property color primary: Theme.primary
    readonly property color textColor: Theme.textPrimary
    Binding { target: Theme; property: "darkMode"; value: host.dark }
    Binding { target: Theme; property: "glassMode"; value: host.glass && !host.mechanical }
    Binding { target: Theme; property: "glassPalette"
        value: host.dark ? host.config.darkColors : host.config.colors }
    Binding { target: Theme; property: "glassMaterial"; value: host.config.material }
    Rectangle {
        id: scene; objectName: "scene"; anchors.fill: parent; color: "#226699"
        Rectangle { x: 200; width: 100; height: parent.height; color: "#bb3388" }
    }
    Item {
        id: container; x: 60; y: 30; width: 300; height: 200
        GlassSurface {
            id: panel; objectName: "glassSurface"
            x: 10; y: 15; width: 260; height: 170; cornerRadius: 22
        }
        Text { anchors.centerIn: parent; text: "Glass"; color: Theme.textPrimary }
    }
}
'''.replace("CONFIG", json.dumps(config))
    component.setData(code.encode(), QUrl.fromLocalFile(
        str(package_root() / "ui/qml/GlassHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        QTest.qWait(120)
        panel = window.findChild(QQuickItem, "glassSurface")
        assert panel.property("visible")
        assert panel.property("sourcePosition").x() == 70
        panel.parentItem().setX(80)
        assert panel.property("sourcePosition").x() == 90
        light = window.grabWindow()
        assert not light.isNull()
        scene = window.findChild(QQuickItem, "scene")
        scene.setProperty("color", "#44aa22")
        QTest.qWait(60)
        changed_backdrop = window.grabWindow()
        sample = round(120 * light.devicePixelRatio())
        assert light.pixelColor(sample, sample) != changed_backdrop.pixelColor(sample, sample)
        if panel.property("effectsAvailable"):
            optical = next(obj for obj in panel.findChildren(QObject)
                           if obj.metaObject().indexOfProperty("shaderStatus") >= 0)
            assert optical.property("shaderStatus") == 0, optical.property("shaderLog")
        window.setProperty("dark", True)
        QTest.qWait(60)
        dark = window.grabWindow()
        sample = round(120 * light.devicePixelRatio())
        assert light.pixelColor(sample, sample) != dark.pixelColor(sample, sample)
        assert window.property("textColor").name() == "#f3f6fa"
        window.setProperty("mechanical", True)
        assert not panel.property("visible")
        window.setProperty("mechanical", False)
        window.setProperty("glass", False)
        window.setProperty("dark", False)
        assert not panel.property("visible")
        assert window.property("primary").name() == "#1677ff"
        assert window.property("textColor").name() == "#0b0f17"
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()



def _luminance(color):
    channels = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                for value in (color.redF(), color.greenF(), color.blueF())]
    return sum(value * weight for value, weight in
               zip(channels, (0.2126, 0.7152, 0.0722), strict=True))


def _contrast(first, second):
    low, high = sorted((_luminance(first), _luminance(second)))
    return (high + 0.05) / (low + 0.05)


@pytest.mark.gui
def test_color_picker_repaints_round_corners_after_resize(qapp, qtbot):
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData(b'''
import QtQuick
import "components"
Window {
    width: 400; height: 650; visible: true; color: "magenta"
    QtObject {
        id: utilities
        signal screenColorPicked(string color)
        signal screenColorPickingCancelled()
    }
    InteractiveColorPicker {
        anchors.fill: parent; utilities: utilities; background: Item {}
    }
}
''', QUrl.fromLocalFile(str(package_root() / "ui/qml/ColorCornerHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        canvas = window.findChild(QQuickItem, "saturationValueCanvas")
        for width in (400, 1200, 400):
            window.setWidth(width)
            qtbot.wait(100)
            frame = window.grabWindow()
            dpr = frame.devicePixelRatio()
            def sample(x, y, frame=frame, dpr=dpr):
                point = canvas.mapToItem(window.contentItem(), x, y)
                return frame.pixelColor(round(point.x() * dpr), round(point.y() * dpr))
            assert sample(0, 0) == QColor("magenta")
            # A fixed-radius corner must not stretch with the canvas texture.
            assert sample(12, canvas.height() - 2).lightness() < 15
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.gui
def test_main_dialog_async_open_and_cached_reopen(qapp, qtbot):
    main = (package_root() / "ui/qml/Main.qml").read_text(encoding="utf-8")
    helpers = main.split("    function openCommandEditorForCreate", 1)[1].split(
        "    function importCustomScriptFromClipboard", 1)[0]
    loaders = main.split("    Loader {\n        id: deleteCommandDialogLoader", 1)[1].split(
        "    Loader {\n        id: pythonDoctorDialogLoader", 1)[0]
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    component = QQmlComponent(engine)
    source = '''
import QtQuick
import QtQuick.Controls
import "components"
ApplicationWindow {
    id: window; width: 1000; height: 800; visible: true
    readonly property var cachedEditor: commandEditorDialogLoader.item
    function openBlankEditor() { openCommandEditorForCreate() }
    QtObject {
        id: appController
        property var selectedTool: ({title: "Test", executor: {command: "echo test"}})
        function previewAndroidDetection(command, mode) { return "" }
    }
    function openCommandEditorForCreateHELPERS
    Loader { id: deleteCommandDialogLoaderLOADERS
}
'''.replace("HELPERS", helpers).replace("LOADERS", loaders)
    component.setData(source.encode(), QUrl.fromLocalFile(
        str(package_root() / "ui/qml/DialogPreloadHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        # Request before idle preload: the pending request must survive incubation.
        assert QMetaObject.invokeMethod(window, "openCommandEditorForEdit", Qt.DirectConnection)
        qtbot.waitUntil(lambda: window.property("cachedEditor") is not None)
        editor = window.property("cachedEditor")
        qtbot.waitUntil(lambda: editor.property("visible"))
        assert editor.property("editMode")
        QMetaObject.invokeMethod(editor, "close", Qt.DirectConnection)
        qtbot.waitUntil(lambda: not editor.property("visible"))
        QMetaObject.invokeMethod(window, "openBlankEditor", Qt.DirectConnection)
        qtbot.waitUntil(lambda: editor.property("visible"))
        assert window.property("cachedEditor") is editor
        assert not editor.property("editMode")
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.gui
@pytest.mark.parametrize("dark", [False, True])
def test_popup_glass_samples_live_page_without_sampling_its_overlay(qapp, qtbot, dark):
    config = json.loads((package_root() / "ui/qml/theme/configs/glass.json").read_text())
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda messages: warnings.extend(m.toString() for m in messages))
    component = QQmlComponent(engine)
    component.setData('''
import QtQuick
import "components"
import "theme"
Window {
    id: host; width: 420; height: 300; visible: true
    property var config: CONFIG
    readonly property Item popupBackgroundSource: page
    readonly property bool glassBackgroundReady: true
    readonly property bool systemBackdropTinted: true
    readonly property color textColor: Theme.textPrimary
    Binding { target: Theme; property: "glassMode"; value: true }
    Binding { target: Theme; property: "darkMode"; value: DARK }
    Binding { target: Theme; property: "glassPalette"
        value: DARK ? host.config.darkColors : host.config.colors }
    Binding { target: Theme; property: "glassMaterial"; value: host.config.material }
    property bool stripes: false
    Rectangle {
        id: page; objectName: "page"; anchors.fill: parent; color: "#ee3344"
        Repeater {
            model: host.stripes ? 105 : 0
            Rectangle { required property int index; x: index * 4; width: 4
                height: page.height; color: index % 2 ? "white" : "black" }
        }
    }
    Item {
        x: 60; y: 50; width: 300; height: 180
        AppPopupSurface { objectName: "popupSurface"; anchors.fill: parent; cornerRadius: 16 }
        Rectangle { x: 40; y: 30; width: 50; height: 24; color: "#00ff00" }
    }
}
'''.replace("CONFIG", json.dumps(config)).replace("DARK", str(dark).lower()).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/PagePopupGlassHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        qtbot.wait(150)
        popup = window.findChild(QQuickItem, "popupSurface")
        page = window.findChild(QQuickItem, "page")
        assert popup.property("usesPageBackground")
        assert popup.property("backgroundSource") is page

        def sample(x, y):
            frame = window.grabWindow()
            dpr = frame.devicePixelRatio()
            return frame.pixelColor(round(x * dpr), round(y * dpr))

        before = sample(200, 140)
        page.setProperty("color", QColor("#228844"))
        qtbot.wait(80)
        after = sample(200, 140)
        assert before != after  # The popup follows page content without a new open.
        assert sample(120, 90) == QColor("#00ff00")  # Foreground stays sharp.
        assert _contrast(window.property("textColor"), after) >= 4.5
        page.setProperty("color", QColor("white"))
        qtbot.wait(80)
        assert _contrast(window.property("textColor"), sample(200, 140)) >= 4.5
        window.setProperty("stripes", True)
        qtbot.wait(100)
        # Fine page detail should dissolve into a uniform tone under the frost.
        colors = [sample(x, 160).red() for x in range(160, 240, 2)]
        assert max(colors) - min(colors) <= 6
        QTest.mouseMove(window, QPoint(180, 150))
        qtbot.wait(200)
        first_hover = window.grabWindow()
        QTest.mouseMove(window, QPoint(270, 180))
        qtbot.wait(200)
        assert window.grabWindow() == first_hover  # No mouse-driven lens movement.
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.gui
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("scaled_card", [False, True])
def test_floating_card_combo_popup_blocks_underlying_content(qapp, qtbot, dark, scaled_card):
    config = json.loads((package_root() / "ui/qml/theme/configs/glass.json").read_text())
    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    component = QQmlComponent(engine)
    component.setData('''
import QtQuick
import "components"
import "theme"
Window {
    id: host; width: 320; height: 360; visible: true
    property color scene: "white"
    property var config: CONFIG
    readonly property bool glassBackgroundReady: true
    readonly property bool systemBackdropTinted: true
    readonly property Item popupBackground: combo.popup.background
    readonly property bool popupOpened: combo.popup.opened
    readonly property int selectedIndex: combo.currentIndex
    readonly property color ink: Theme.textPrimary
    Binding { target: Theme; property: "glassMode"; value: true }
    Binding { target: Theme; property: "darkMode"; value: DARK }
    Binding { target: Theme; property: "glassPalette"
        value: DARK ? host.config.darkColors : host.config.colors }
    Binding { target: Theme; property: "glassMaterial"; value: host.config.material }
    Rectangle { anchors.fill: parent; color: host.scene }
    Item {
        x: SCALED ? 120 : 20; y: SCALED ? 290 : 30
        width: 240; height: 44; scale: SCALED ? 0.78 : 1
        transformOrigin: Item.TopLeft
        AppComboBox { id: combo; anchors.fill: parent; model: ["A", "B", "C"] }
    }
    function openCombo() { combo.popup.open() }
}
'''.replace("CONFIG", json.dumps(config)).replace("DARK", str(dark).lower())
        .replace("SCALED", str(scaled_card).lower()).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/CardComboHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        QMetaObject.invokeMethod(window, "openCombo", Qt.DirectConnection)
        qtbot.waitUntil(lambda: window.property("popupOpened"))
        qtbot.wait(200)
        background = window.property("popupBackground")
        assert not background.property("usesPageBackground")
        rect = background.mapRectToItem(window.contentItem(), background.boundingRect())
        assert rect.left() >= 7 and rect.right() <= window.width() - 7
        assert rect.top() >= 7 and rect.bottom() <= window.height() - 7
        if scaled_card:
            assert rect.width() == pytest.approx(240 * 0.78, abs=1)
            assert rect.bottom() < 290  # Open upward when the field is near the bottom.
        point = background.mapToItem(window.contentItem(), background.width() - 18, 75)
        def sample():
            frame = window.grabWindow()
            dpr = frame.devicePixelRatio()
            return frame.pixelColor(round(point.x() * dpr), round(point.y() * dpr))
        light = sample()
        window.setProperty("scene", QColor("black"))
        qtbot.wait(100)
        dark_background = sample()
        assert max(abs(a - b) for a, b in zip(light.getRgb()[:3],
                                             dark_background.getRgb()[:3], strict=True)) <= 10
        assert _contrast(window.property("ink"), light) >= 4.5
        assert _contrast(window.property("ink"), dark_background) >= 4.5
        QTest.mouseClick(window, Qt.LeftButton, pos=QPoint(
            round(rect.center().x()), round(rect.top() + 6 + 48 * 1.5)))
        qtbot.waitUntil(lambda: not window.property("popupOpened"))
        assert window.property("selectedIndex") == 1
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.gui
@pytest.mark.parametrize("dark", [False, True])
def test_glass_tooltip_blocks_underlying_content(qapp, qtbot, dark):
    config = json.loads((package_root() / "ui/qml/theme/configs/glass.json").read_text())
    engine = QQmlEngine()
    component = QQmlComponent(engine)
    component.setData('''
import QtQuick
import "components"
import "theme"
Window {
    id: host; width: 360; height: 240; visible: true
    property color scene: "white"
    property bool showTooltip: false
    property var config: CONFIG
    color: scene
    readonly property bool glassBackgroundReady: true
    readonly property bool systemBackdropTinted: true
    readonly property Item tipBackground: tip.background
    readonly property bool tipOpened: tip.opened
    readonly property color tipTextColor: Theme.textPrimary
    Binding { target: Theme; property: "glassMode"; value: true }
    Binding { target: Theme; property: "darkMode"; value: DARK }
    Binding { target: Theme; property: "glassPalette"
        value: DARK ? host.config.darkColors : host.config.colors }
    Binding { target: Theme; property: "glassMaterial"; value: host.config.material }
    Item {
        x: 90; y: 150; width: 180; height: 32
        HoverTips { id: tip; text: "Tooltip readability"; delay: 0; visible: host.showTooltip }
    }
}
'''.replace("CONFIG", json.dumps(config)).replace("DARK", str(dark).lower()).encode(),
        QUrl.fromLocalFile(str(package_root() / "ui/qml/GlassTooltipHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [error.toString() for error in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        window.setProperty("showTooltip", True)
        qtbot.waitUntil(lambda: window.property("tipOpened"))
        qtbot.wait(250)  # Finish the tooltip's entrance fade.
        background = window.property("tipBackground")
        assert background.width() > 0
        point = background.mapToItem(window.contentItem(), 14, 5)

        def sample():
            frame = window.grabWindow()
            dpr = frame.devicePixelRatio()
            return frame.pixelColor(round(point.x() * dpr), round(point.y() * dpr))

        light = sample()
        window.setProperty("scene", QColor("black"))
        qtbot.wait(80)
        dark_background = sample()
        # 97% opacity lets at most ~8/255 of the scene's white/black change
        # through. Low-opacity glass previously let underlying text dominate.
        assert max(abs(a - b) for a, b in zip(light.getRgb()[:3],
                                             dark_background.getRgb()[:3], strict=True)) <= 10
        assert _contrast(window.property("tipTextColor"), light) >= 4.5
        assert _contrast(window.property("tipTextColor"), dark_background) >= 4.5
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


@pytest.mark.gui
@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("desktop_color", ["#ffffff", "#000000", "#e52640"])
def test_glass_readability_over_extreme_desktops(qapp, qtbot, dark, desktop_color):
    """Measure transparent control overlays against light/dark system material tones."""
    class NativeBackdropStub(QObject):
        @Slot(QObject, bool, bool, result=str)
        def configure(self, window, active, dark):
            return ""

        @Slot(QObject)
        def release(self, window):
            pass

    engine = QQmlEngine()
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    backend = NativeBackdropStub()
    engine.rootContext().setContextProperty("systemBackdropController", backend)
    # Representative DWM material tones. The external pixels are owned by DWM
    # and tested by the composed-desktop proof, not by QQuickWindow.grabWindow().
    tones = ({"#ffffff": "#444953", "#000000": "#181c24", "#e52640": "#542f3c"}
             if dark else
             {"#ffffff": "#f4f6fa", "#000000": "#aeb6c2", "#e52640": "#ef9aa8"})
    config = json.loads((package_root() / "ui/qml/theme/configs/glass.json").read_text())
    component = QQmlComponent(engine)
    source = '''
import QtQuick
import "components"
import "theme"
Window {
    id: host; width: 320; height: 260; visible: true
    property var config: CONFIG
    readonly property bool glassBackgroundReady: desktop.ready
    readonly property bool systemBackdropTinted: true
    readonly property Item glassBackgroundSource: null
    Binding { target: Theme; property: "glassMode"; value: true }
    Binding { target: Theme; property: "darkMode"; value: DARK }
    Binding { target: Theme; property: "glassPalette";
        value: DARK ? host.config.darkColors : host.config.colors }
    Binding { target: Theme; property: "glassMaterial"; value: host.config.material }
    DesktopBackground {
        id: desktop; anchors.fill: parent; hostWindow: host
    }
    Rectangle { anchors.fill: parent; color: "BACKDROP_COLOR" }
    GlassSurface { x: 20; y: 40; width: 280; height: 100 }
    PrimaryButton { x: 20; y: 170; width: 120; height: 44; text: ""; iconName: "" }
    AppSwitch { x: 180; y: 170; checked: true }
    AppCheckBox { x: 250; y: 170; checked: true }
}
'''.replace("CONFIG", json.dumps(config)).replace("DARK", str(dark).lower())
    source = source.replace("BACKDROP_COLOR", tones[desktop_color])
    component.setData(source.encode(), QUrl.fromLocalFile(
        str(package_root() / "ui/qml/GlassContrastHarness.qml")))
    window = component.create()
    assert isinstance(window, QQuickWindow), [e.toString() for e in component.errors()]
    try:
        assert QTest.qWaitForWindowExposed(window)
        QTest.qWait(150)
        rendered = window.grabWindow()
        dpr = rendered.devicePixelRatio()
        def sample(x, y):
            return rendered.pixelColor(round(x * dpr), round(y * dpr))
        palette = config["darkColors" if dark else "colors"]
        ink = QColor(palette["textSecondary"])
        for point in ((10, 15), (100, 90)):
            color = sample(*point)
            assert _contrast(ink, color) >= 4.5, (desktop_color, dark, color.name())
            if dark:
                assert _luminance(color) < 0.10, color.name()
            else:
                assert _luminance(color) > 0.40, color.name()
        assert _contrast(QColor(palette["primaryForeground"]), sample(80, 192)) >= 4.5
        assert not warnings, warnings
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()
