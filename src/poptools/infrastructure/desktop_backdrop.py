"""Windows-owned Desktop Acrylic. No capture, polling or application-owned backdrop frames."""
from __future__ import annotations

import ctypes
import os
import sys
import weakref
from ctypes import wintypes
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QMargins, QObject, QTimer, Slot
from PySide6.QtGui import QWindow
from PySide6.QtQuick import QQuickWindow
from shiboken6 import isValid

if TYPE_CHECKING:
    from poptools.infrastructure.windows_frame import WindowsCardFrame

# Public dwmapi.h values; Desktop Acrylic requires Windows 11 build 22621.
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMSBT_NONE = 1
DWMSBT_TRANSIENTWINDOW = 3


def prepare_system_backdrops() -> None:
    """Allocate alpha/DirectComposition surfaces before creating any app HWND."""
    if sys.platform != "win32":
        return
    QQuickWindow.setDefaultAlphaBuffer(True)
    if (os.environ.get("QT_QUICK_BACKEND") != "software"
            and os.environ.get("QSG_RHI_BACKEND", "d3d11") in ("d3d11", "d3d12")):
        # Without this the opaque HWND bitmap covers DWM's system backdrop.
        # Qt applies this global switch to all top-level windows, including
        # QWidget menus: _TrayMenu restores its required raster bitmap on show.
        os.environ.setdefault("QT_QPA_DISABLE_REDIRECTION_SURFACE", "1")


class _Margins(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ("left", "right", "top", "bottom")]


class WindowsBackdrop:
    def __init__(self) -> None:
        self.dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        self.dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        self.dwm.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND, ctypes.POINTER(_Margins)]
        self.dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long

    def apply(self, hwnd: int, enabled: bool, dark: bool, custom_frame: bool) -> str:
        theme = ctypes.c_int(dark)
        self.dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(theme), ctypes.sizeof(theme))
        kind = ctypes.c_int(DWMSBT_TRANSIENTWINDOW if enabled else DWMSBT_NONE)
        result = self.dwm.DwmSetWindowAttribute(
            hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(kind), ctypes.sizeof(kind))
        if result < 0:
            return f"系统 Acrylic 设置失败：0x{result & 0xffffffff:08X}"
        # Negative margins expose the compositor's backdrop across the client.
        # Return the existing custom caption's one-pixel frame when disabled.
        margin = -1 if enabled else 1 if custom_frame else 0
        result = self.dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(
            _Margins(margin, margin, margin, margin)))
        if result < 0:
            if enabled:
                kind.value = DWMSBT_NONE
                self.dwm.DwmSetWindowAttribute(
                    hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ctypes.byref(kind), ctypes.sizeof(kind))
            return f"系统背景扩展失败：0x{result & 0xffffffff:08X}"
        return ""


@dataclass
class _Target:
    window: QWindow
    dark: bool


class SystemBackdropController(QObject):
    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._supported = sys.platform == "win32" and sys.getwindowsversion().build >= 22621
        self._native = WindowsBackdrop() if self._supported else None
        self._targets: dict[int, _Target] = {}
        self._observed: weakref.WeakSet[QWindow] = weakref.WeakSet()
        self._pending_reapply = False
        self._card_frames: dict[int, WindowsCardFrame] = {}

    @Property(bool, constant=True)
    def cardFramesSupported(self) -> bool:
        return (self._supported and os.environ.get("QT_QUICK_BACKEND") != "software"
                and os.environ.get("QSG_RHI_BACKEND", "d3d11") in ("d3d11", "d3d12"))

    @Slot(QObject)
    def prepareCardWindow(self, window: QObject) -> None:
        if not isinstance(window, QWindow) or not self.cardFramesSupported:
            return
        from poptools.infrastructure.windows_frame import WindowsCardFrame, prepare_windows_frame

        key = id(window)
        if window.property("nativeCardFrame"):
            if key not in self._card_frames:
                prepare_windows_frame(window, border=0, native_style=0x00040000)
                window.create()
                frame = WindowsCardFrame(window)
                self._card_frames[key] = frame
                window.destroyed.connect(lambda: self._card_frames.pop(key, None))
        else:
            old_frame = self._card_frames.pop(key, None)
            if old_frame is not None:
                old_frame.detach()
                window.setProperty("_q_windowsCustomMargins", QMargins())

    @Slot()
    def _surface_changed(self) -> None:
        if not self._pending_reapply:
            self._pending_reapply = True
            QTimer.singleShot(0, self._reapply)

    @Slot()
    def _reapply(self) -> None:
        self._pending_reapply = False
        if self._native is None:
            return
        for hwnd, target in list(self._targets.items()):
            if isValid(target.window):
                self._native.apply(
                    hwnd, True, target.dark, bool(target.window.property("customTitleBar")))

    @Property(bool, constant=True)
    def supported(self) -> bool:
        return self._supported

    @Slot(QObject, bool, bool, result=str)
    def configure(self, window: QObject, enabled: bool, dark: bool) -> str:
        if not isinstance(window, QWindow):
            return "无法取得窗口的系统背景目标"
        if not self._supported or self._native is None:
            return "系统 Acrylic 需要 Windows 11 22H2 或更新版本" if enabled else ""
        if enabled and (os.environ.get("QT_QUICK_BACKEND") == "software"
                        or os.environ.get("QSG_RHI_BACKEND", "d3d11") not in ("d3d11", "d3d12")):
            return "系统 Acrylic 需要 Direct3D 图形后端，当前使用实色背景"
        # Do not create an HWND before WindowChromeController prepares its frame.
        if not enabled:
            for hwnd, tracked in list(self._targets.items()):
                if tracked.window is window:
                    error = self._native.apply(
                        hwnd, False, dark, bool(window.property("customTitleBar")))
                    if not error:
                        self._targets.pop(hwnd, None)
                    return error
            return ""
        if window.property("nativeCardFrame"):
            self.prepareCardWindow(window)
        hwnd = int(window.winId())
        target = self._targets.get(hwnd)
        if target is not None and target.dark == dark:
            return ""
        error = self._native.apply(hwnd, True, dark, bool(window.property("customTitleBar")))
        if error:
            return error
        self._targets[hwnd] = _Target(window, dark)
        if window not in self._observed:
            self._observed.add(window)
            color_changed = getattr(window, "colorChanged", None)
            if color_changed is not None:
                color_changed.connect(self._surface_changed)
            self._surface_changed()
            owner = weakref.ref(self)
            window_ref = weakref.ref(window)

            def forget() -> None:
                controller = owner()
                if controller is not None:
                    for key, state in list(controller._targets.items()):
                        if state.window is window_ref():
                            controller._targets.pop(key, None)

            window.destroyed.connect(forget)
        return ""

    @Slot(QObject)
    def release(self, window: QObject) -> None:
        if isValid(window):
            self.configure(window, False, False)

    @Slot()
    def shutdown(self) -> None:
        if self._native is not None:
            for hwnd, target in list(self._targets.items()):
                if isValid(target.window):
                    self._native.apply(
                        hwnd, False, target.dark, bool(target.window.property("customTitleBar")))
        self._targets.clear()
        for frame in self._card_frames.values():
            frame.detach()
        self._card_frames.clear()
