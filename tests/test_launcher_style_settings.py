import pytest

from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.theme_catalog import ThemeCatalog
from poptools.paths import AppPaths, package_root
from test_floating_launcher import launcher as launcher


@pytest.mark.parametrize("legacy", ["decade", "zio"])
def test_legacy_theme_migrates_to_launcher_style(tmp_path, legacy):
    store = ConfigStore(AppPaths(tmp_path))
    data = store.load_config()
    data["app"]["theme"] = legacy
    store.save_config(data)
    assert store.floating_launcher_style() == legacy
    assert store.theme_mode() == "dark"
    restored = ConfigStore(store.paths)
    assert restored.floating_launcher_style() == legacy
    with pytest.raises(ValueError):
        restored.set_theme_mode(legacy)


@pytest.mark.parametrize("mode", ["light", "dark", "system"])
@pytest.mark.parametrize("style", ["default", "decade", "zio"])
def test_launcher_style_is_independent_of_color_scheme(launcher, mode, style):
    controller, _, settings, _ = launcher
    assert settings.saveThemeMode(mode)
    assert settings.saveThemeStyle("glass")
    dark = settings.darkTheme
    assert settings.saveFloatingLauncherStyle(style)
    assert settings.themeMode == mode
    assert settings.darkTheme == dark
    assert settings.themeStyle == "glass"
    assert settings.floatingLauncherStyle == style
    assert settings.saveThemeMode("light" if mode != "light" else "dark")
    assert settings.floatingLauncherStyle == style
    assert controller.visible
    assert settings.saveFloatingLauncherStyle("off")
    assert not settings.floatingLauncherEnabled and not controller.visible
    assert settings.floatingLauncherStyle == style
    assert settings.saveFloatingLauncherStyle(style)
    assert settings.floatingLauncherEnabled and controller.visible


def test_theme_catalog_no_longer_offers_launcher_styles():
    catalog = ThemeCatalog(package_root() / "ui/qml/theme/configs")
    catalog.refresh()
    assert not {"decade", "zio"}.intersection(i["value"] for i in catalog.theme_items())
