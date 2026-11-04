"""Native tray menus must keep their raster bitmap when QML uses DWM glass."""

import ctypes
import os
import sys

import pytest
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from poptools.infrastructure.system_tray import SystemTrayController


@pytest.mark.gui
@pytest.mark.skipif(sys.platform != "win32", reason="Windows QPA window styles")
@pytest.mark.parametrize("setting", [None, "0", "1"])
def test_tray_popups_keep_raster_bitmap_without_disabling_glass(
    qapp, qtbot, monkeypatch, setting,
):
    if qapp.platformName() != "windows":
        pytest.skip("Requires native Windows HWNDs")
    variable = "QT_QPA_DISABLE_REDIRECTION_SURFACE"
    if setting is None:
        monkeypatch.delenv(variable, raising=False)
    else:
        monkeypatch.setenv(variable, setting)
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", lambda: False)
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user.GetWindowLongPtrW.restype = ctypes.c_ssize_t

    def no_bitmap(menu):
        return bool(user.GetWindowLongPtrW(ctypes.c_void_p(int(menu.winId())), -20) & 0x00200000)

    tray = SystemTrayController(qapp)
    menus = (tray._menu, tray._preset_menu, tray._recent_menu)
    for menu in menus:
        qtbot.addWidget(menu)
    try:
        assert all(not no_bitmap(menu) for menu in menus)
        assert os.environ.get(variable) == setting
        # A later ordinary HWND must still inherit the QPA switch. The fix
        # must not globally turn off the setting used by the D3D glass window.
        ordinary = QMenu()
        qtbot.addWidget(ordinary)
        assert no_bitmap(ordinary) == (setting == "1")
        tray._build_preset_menu()
        tray._build_recent_menu()
        assert len(tray._menu.actions()) == 5
        assert tray._preset_menu.actions()[0].text() == "(暂无预置功能)"
        assert tray._recent_menu.actions()[0].text() == "(暂无最近使用)"
    finally:
        tray.deleteLater()
