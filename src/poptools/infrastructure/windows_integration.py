from __future__ import annotations

import ctypes
import sys

from PySide6.QtGui import QColor

APP_USER_MODEL_ID = "PopTools.ZhangPaopaoToolbox"
_WM_SETICON = 0x0080
_ICON_SMALL = 0
_ICON_BIG = 1
_IMAGE_ICON = 1
_LR_LOADFROMFILE = 0x0010
_GCLP_HICON = -14
_GCLP_HICONSM = -34
_NATIVE_ICON_HANDLES: list[int] = []
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWCP_ROUND = 2
_DWMWA_BORDER_COLOR = 34
_DWMWA_CAPTION_COLOR = 35
_DWMWA_TEXT_COLOR = 36


def configure_windows_app_identity() -> None:
    if sys.platform != "win32":
        return
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    result = shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    if result != 0:
        raise OSError(result, "无法设置 Windows 应用标识")


def apply_windows_window_icon(window_id: int, icon_path: str) -> None:
    if sys.platform != "win32":
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    hwnd = ctypes.c_void_p(window_id)
    user32.LoadImageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_uint,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.LoadImageW.restype = ctypes.c_void_p
    user32.SendMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_size_t,
        ctypes.c_ssize_t,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SetClassLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetClassLongPtrW.restype = ctypes.c_ssize_t
    large = user32.LoadImageW(None, icon_path, _IMAGE_ICON, 0, 0, _LR_LOADFROMFILE)
    small = user32.LoadImageW(None, icon_path, _IMAGE_ICON, 16, 16, _LR_LOADFROMFILE)
    if not large or not small:
        raise OSError(ctypes.get_last_error(), "无法加载 Windows 应用图标")
    _NATIVE_ICON_HANDLES.extend((int(large), int(small)))
    user32.SendMessageW(hwnd, _WM_SETICON, _ICON_BIG, large)
    user32.SendMessageW(hwnd, _WM_SETICON, _ICON_SMALL, small)
    user32.SetClassLongPtrW(hwnd, _GCLP_HICON, large)
    user32.SetClassLongPtrW(hwnd, _GCLP_HICONSM, small)


def apply_windows_title_bar_theme(
    window_id: int,
    *,
    dark_mode: bool,
    background_color: QColor | None = None,
    foreground_color: QColor | None = None,
) -> None:
    """Match the native caption and frame to the navigation rail's palette."""
    if sys.platform != "win32":
        return
    dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
    dwmapi.DwmSetWindowAttribute.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_uint,
    ]
    dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
    enabled = ctypes.c_int(dark_mode)
    # Older Windows versions may not support this attribute; their native
    # title bar remains usable with the system's default appearance.
    dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(window_id),
        _DWMWA_USE_IMMERSIVE_DARK_MODE,
        ctypes.byref(enabled),
        ctypes.sizeof(enabled),
    )
    corner_preference = ctypes.c_int(_DWMWCP_ROUND)
    dwmapi.DwmSetWindowAttribute(
        ctypes.c_void_p(window_id), _DWMWA_WINDOW_CORNER_PREFERENCE,
        ctypes.byref(corner_preference), ctypes.sizeof(corner_preference),
    )
    for attribute, color in (
        (_DWMWA_CAPTION_COLOR, background_color),
        (_DWMWA_BORDER_COLOR, background_color),
        (_DWMWA_TEXT_COLOR, foreground_color),
    ):
        if color is None:
            continue
        color_ref = ctypes.c_uint(color.red() | (color.green() << 8) | (color.blue() << 16))
        dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(window_id), attribute, ctypes.byref(color_ref), ctypes.sizeof(color_ref)
        )
