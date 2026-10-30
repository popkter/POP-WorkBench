import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest

from poptools.infrastructure import foreground_window as module


@pytest.mark.parametrize("handle,thread_id", [(0, 1), (0x123456789, 0), (0x123456789, 7)])
def test_native_foreground_handles_transition_and_destroyed_windows(monkeypatch, handle, thread_id):
    def process_id(window, output):
        assert window == handle
        ctypes.cast(output, ctypes.POINTER(wintypes.DWORD)).contents.value = 123
        return thread_id

    def ancestor(window, flags):
        assert window == handle and flags == 3
        return 0x987654321

    api = SimpleNamespace(GetForegroundWindow=lambda: handle,
                          GetWindowThreadProcessId=process_id, GetAncestor=ancestor)
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(module, "_user32", lambda: api)
    result = module.foreground_window()
    if handle and thread_id:
        assert result == module.ForegroundWindow(handle, 123, 0x987654321)
    else:
        assert result is None


def test_other_platforms_do_not_load_windows_api(monkeypatch):
    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(module, "_user32", lambda: pytest.fail("Windows API loaded"))
    assert module.foreground_window() is None
    assert module.window_under_cursor() is None


def test_hit_test_uses_actual_root_window_at_negative_screen_coordinates(monkeypatch):
    def cursor(output):
        point = ctypes.cast(output, ctypes.POINTER(wintypes.POINT)).contents
        point.x, point.y = -1600, -250
        return True

    def hit(point):
        assert (point.x, point.y) == (-1600, -250)
        return 123

    def root(handle, flags):
        assert handle == 123 and flags == 2
        return 456

    monkeypatch.setattr(module, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(module, "_user32", lambda: SimpleNamespace(
        WindowFromPoint=hit, GetAncestor=root, GetCursorPos=cursor))
    assert module.window_under_cursor() == 456
