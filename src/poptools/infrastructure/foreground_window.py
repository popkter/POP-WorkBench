"""Read Windows foreground ownership without activating or creating any window."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from functools import lru_cache
from typing import NamedTuple


class ForegroundWindow(NamedTuple):
    handle: int
    process_id: int
    root_owner: int


@lru_cache(maxsize=1)
def _user32() -> ctypes.WinDLL:
    api = ctypes.WinDLL("user32", use_last_error=True)
    api.GetForegroundWindow.argtypes = []
    api.GetForegroundWindow.restype = wintypes.HWND
    api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    api.GetWindowThreadProcessId.restype = wintypes.DWORD
    api.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    api.GetAncestor.restype = wintypes.HWND
    return api


def foreground_window() -> ForegroundWindow | None:
    if sys.platform != "win32":
        return None
    api = _user32()
    handle = api.GetForegroundWindow()
    if not handle:
        # Windows may return NULL during activation changes. Let Qt handle this
        # sample rather than treating an indeterminate foreground as another app.
        return None
    process_id = wintypes.DWORD()
    if not api.GetWindowThreadProcessId(handle, ctypes.byref(process_id)):
        return None
    return ForegroundWindow(int(handle), process_id.value, int(api.GetAncestor(handle, 3) or 0))
