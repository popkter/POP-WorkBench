"""Coalesce flying card updates and commit native moves together."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from functools import cache

from PySide6.QtCore import QCoreApplication, QObject, QPoint, QTimer
from PySide6.QtGui import QRegion, QWindow
from shiboken6 import isValid


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


@cache
def _window_api() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.BeginDeferWindowPos.argtypes = [ctypes.c_int]
    user32.BeginDeferWindowPos.restype = ctypes.c_void_p
    user32.DeferWindowPos.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.DeferWindowPos.restype = ctypes.c_void_p
    user32.EndDeferWindowPos.argtypes = [ctypes.c_void_p]
    user32.EndDeferWindowPos.restype = wintypes.BOOL
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HMONITOR
    user32.GetMonitorInfoW.argtypes = [wintypes.HMONITOR, ctypes.POINTER(_MonitorInfo)]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    return user32


def _native_point(point: QPoint, logical_origin: QPoint,
                  physical_origin: QPoint, ratio: float) -> QPoint:
    return physical_origin + QPoint(round((point.x() - logical_origin.x()) * ratio),
                                    round((point.y() - logical_origin.y()) * ratio))


def _move_windows(moves: list[tuple[QWindow, QPoint]]) -> None:
    if not moves:
        return
    if sys.platform == "win32":
        user32 = _window_api()
        begin, defer, end = (user32.BeginDeferWindowPos, user32.DeferWindowPos,
                             user32.EndDeferWindowPos)
        batch = begin(len(moves))
        if batch:
            for window, point in moves:
                info = _MonitorInfo()
                info.size = ctypes.sizeof(info)
                monitor = user32.MonitorFromWindow(int(window.winId()), 2)
                if not window.screen() or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                    # End the valid partial batch before the Qt fallback.
                    end(batch)
                    batch = None
                    break
                # Map absolutely from this monitor's origin. Accumulating rounded
                # logical deltas introduces pixel drift at fractional DPI scales.
                physical = _native_point(point, window.screen().geometry().topLeft(),
                    QPoint(info.monitor.left, info.monitor.top), window.devicePixelRatio())
                batch = defer(batch, int(window.winId()), None,
                              physical.x(), physical.y(), 0, 0,
                              0x0001 | 0x0004 | 0x0010 | 0x0200)
                if not batch:
                    break
            if batch and end(batch):
                return
    for window, point in moves:
        window.setPosition(point)


class CardWindowUpdates(QObject):
    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._pending: dict[int, tuple[QWindow, QPoint, QRegion]] = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.flush)

    def schedule(self, window: QWindow, point: QPoint, mask: QRegion) -> None:
        self._pending[id(window)] = (window, point, mask)
        if not self._timer.isActive():
            self._timer.start(0)

    def flush(self) -> None:
        self._timer.stop()
        pending, self._pending = self._pending, {}
        moves = []
        for window, point, mask in pending.values():
            if not isValid(window) or not window.isVisible():
                continue
            if window.mask() != mask:
                window.setMask(mask)
            if window.position() != point:
                moves.append((window, point))
        _move_windows(moves)

    def finish(self, window: QWindow) -> None:
        # Commit the last flight tick before restoring the normal window layer;
        # otherwise a queued move can overwrite the final landing position.
        update = self._pending.pop(id(window), None)
        if update and isValid(window) and window.isVisible():
            _, point, mask = update
            if window.mask() != mask:
                window.setMask(mask)
            _move_windows([(window, point)])


def card_window_updates() -> CardWindowUpdates:
    app = QCoreApplication.instance()
    assert app is not None
    updates = getattr(app, "_poptools_card_updates", None)
    if updates is None:
        updates = CardWindowUpdates(app)
        setattr(app, "_poptools_card_updates", updates)  # noqa: B010 - Qt wrapper extension
    return updates
