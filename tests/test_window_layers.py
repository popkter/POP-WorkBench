import ctypes
import sys
from ctypes import wintypes

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QWindow

from poptools.infrastructure.window_placement import (
    set_card_flight_layer,
    sync_launcher_card_layers,
)


@pytest.mark.gui
@pytest.mark.skipif(sys.platform != "win32", reason="Checks native Windows Z order")
@pytest.mark.parametrize("launcher_name", ["floatingScriptPanelWindow", "zioDockWindow"])
def test_launcher_topmost_and_cards_follow_their_own_pin(qapp, launcher_name):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    get_next = user32.GetWindow
    get_next.argtypes = [wintypes.HWND, wintypes.UINT]
    get_next.restype = wintypes.HWND
    get_style = user32.GetWindowLongW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = wintypes.LONG

    def above(front, back):
        handle = int(front.winId())
        while handle:
            handle = get_next(handle, 2)
            if handle == int(back.winId()):
                return True
        return False

    def topmost(window):
        return bool(get_style(int(window.winId()), -20) & 0x8)

    launcher, first, second, ordinary = [QWindow() for _ in range(4)]
    launcher.setObjectName(launcher_name)
    launcher.setFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
    for index, card in enumerate((first, second)):
        card.setFlags(Qt.Window | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        card.setObjectName("recentToolWindow")
        card.setGeometry(300 + index * 32, 250 + index * 32, 200, 180)
    launcher.setGeometry(300, 250, 200, 180)
    ordinary.setGeometry(300, 250, 200, 180)
    try:
        launcher.show()
        sync_launcher_card_layers([launcher])
        assert topmost(launcher)
        for card in (first, second):
            card.show()
        native_ids = [window.winId() for window in (launcher, first, second)]
        geometries = [window.geometry() for window in (launcher, first, second)]
        second.raise_()
        launcher.raise_()
        sync_launcher_card_layers([launcher])
        assert above(launcher, first) and above(launcher, second)
        assert above(second, first)
        assert not topmost(first) and not topmost(second) and topmost(launcher)
        assert not first.flags() & Qt.WindowStaysOnTopHint
        launcher.requestActivate()
        launcher.raise_()
        sync_launcher_card_layers([launcher])
        assert above(launcher, first) and above(launcher, second)
        ordinary.show()
        ordinary.raise_()
        assert above(ordinary, first) and above(ordinary, second)
        foreground = user32.GetForegroundWindow
        foreground.argtypes = []
        foreground.restype = wintypes.HWND
        active_handle = foreground()
        sync_launcher_card_layers([launcher])
        assert foreground() == active_handle
        assert above(launcher, ordinary)
        assert not topmost(first) and not topmost(second)
        second.raise_()
        assert above(second, ordinary)
        ordinary.raise_()
        assert above(ordinary, second)
        first.setFlag(Qt.WindowStaysOnTopHint, True)
        sync_launcher_card_layers([launcher])
        assert topmost(first) and not topmost(second)
        for flying in (True, False, True, False):
            set_card_flight_layer(second, flying)
            set_card_flight_layer(first, flying)
            assert topmost(second) == flying and topmost(first)
            if flying:
                assert above(second, launcher) and above(first, launcher)
            assert not second.flags() & Qt.WindowStaysOnTopHint
        assert native_ids == [window.winId() for window in (launcher, first, second)]
        assert geometries == [window.geometry() for window in (launcher, first, second)]
        launcher.hide()
        sync_launcher_card_layers([launcher])
        assert topmost(first) and not topmost(second)
        launcher.show()
        sync_launcher_card_layers([launcher])
        assert topmost(launcher) and not topmost(second)
    finally:
        for window in (launcher, first, second, ordinary):
            window.close()
            window.destroy()
