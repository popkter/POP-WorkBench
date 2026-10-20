"""A client-drawn caption backed by the Windows non-client window protocol.

Keep an opaque, rectangular HWND and a one-physical-pixel non-client border.
Windows owns resizing, moving, snapping, the system menu, shadow and rounding;
QML only paints the caption and its controls (as in JetBrains Runtime).
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes

from PySide6.QtCore import QMargins, QPointF, QRectF, Qt
from PySide6.QtGui import QWindow

HTCLIENT, HTCAPTION = 1, 2
HTMINBUTTON, HTMAXBUTTON, HTCLOSE = 8, 9, 20
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17
CAPTION_HITS = (HTMINBUTTON, HTMAXBUTTON, HTCLOSE)


def prepare_windows_frame(window: QWindow) -> None:
    """Tell Qt about the caption removal before it creates the platform window.

    This is the Windows QPA custom-margin property supported by the pinned Qt
    runtime. Without it, Qt still reserves a standard caption and resize frame
    when sizing its backing store, leaving an unpainted strip at the right edge.
    Qt scales these native margins when the window changes monitors/DPI.
    """
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.AdjustWindowRectExForDpi.argtypes = [ctypes.POINTER(wintypes.RECT),
                                              wintypes.DWORD, wintypes.BOOL,
                                              wintypes.DWORD, wintypes.UINT]
    user32.AdjustWindowRectExForDpi.restype = wintypes.BOOL
    rect = wintypes.RECT()
    if not user32.AdjustWindowRectExForDpi(
        ctypes.byref(rect), 0x00CF0000, False, 0, round(window.devicePixelRatio() * 96),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    window.setProperty("_q_windowsCustomMargins", QMargins(
        rect.left + 1, rect.top + 1, 1 - rect.right, 1 - rect.bottom))


class _Margins(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int) for name in ("left", "right", "top", "bottom")]


class _MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


class _TrackMouseEvent(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("hwnd", wintypes.HWND), ("hover_time", wintypes.DWORD)]


class WindowsFrame:
    def __init__(self, window: QWindow) -> None:
        self.window = window
        self.hwnd = int(window.winId())
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)
        self.dwmapi = ctypes.WinDLL("dwmapi", use_last_error=True)
        self.comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
        self._pressed = -1
        self._configure_api()
        # Qt consumes some non-client input before its native event filters.
        # A comctl32 subclass sees the actual HWND protocol and chains safely
        # through Qt's window procedure; it does not replace Qt's WNDPROC.
        self._callback_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
            ctypes.c_ssize_t, ctypes.c_size_t, ctypes.c_size_t)
        self._callback = self._callback_type(self._window_proc)
        self.comctl32.SetWindowSubclass.argtypes = [
            wintypes.HWND, self._callback_type, ctypes.c_size_t, ctypes.c_size_t]
        self.comctl32.SetWindowSubclass.restype = wintypes.BOOL
        self.comctl32.RemoveWindowSubclass.argtypes = [
            wintypes.HWND, self._callback_type, ctypes.c_size_t]
        self.comctl32.RemoveWindowSubclass.restype = wintypes.BOOL
        self.comctl32.DefSubclassProc.argtypes = [
            wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
        self.comctl32.DefSubclassProc.restype = ctypes.c_ssize_t
        if not self.comctl32.SetWindowSubclass(self.hwnd, self._callback, 1, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        window.destroyed.connect(self.detach)
        # Keep Qt's native frame flags as well as the actual HWND styles. A Qt
        # frameless hint makes showMaximized() emulate maximization with a resize
        # instead of letting Windows set WS_MAXIMIZE, breaking restore and Snap.
        style = self.user32.GetWindowLongPtrW(self.hwnd, -16)
        self.user32.SetWindowLongPtrW(self.hwnd, -16, (style & ~0x80000000) | 0x00CF0000)
        self._extend_frame()
        self.user32.SetWindowPos(self.hwnd, None, 0, 0, 0, 0, 0x0037)

    def _configure_api(self) -> None:
        signatures = {
            "GetWindowLongPtrW": ([wintypes.HWND, ctypes.c_int], ctypes.c_ssize_t),
            "SetWindowLongPtrW": (
                [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
            "SetWindowPos": ([wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT], wintypes.BOOL),
            "GetWindowRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            "GetClientRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            "ScreenToClient": ([wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            "ClientToScreen": ([wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
            "IsZoomed": ([wintypes.HWND], wintypes.BOOL),
            "GetDpiForWindow": ([wintypes.HWND], wintypes.UINT),
            "GetSystemMetricsForDpi": ([ctypes.c_int, wintypes.UINT], ctypes.c_int),
            "TrackMouseEvent": ([ctypes.POINTER(_TrackMouseEvent)], wintypes.BOOL),
            "SetCapture": ([wintypes.HWND], wintypes.HWND),
            "GetCapture": ([], wintypes.HWND),
            "ReleaseCapture": ([], wintypes.BOOL),
            "PostMessageW": ([wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
                              ctypes.c_ssize_t], wintypes.BOOL),
            "DefWindowProcW": ([wintypes.HWND, wintypes.UINT, ctypes.c_size_t,
                                ctypes.c_ssize_t], ctypes.c_ssize_t),
            "MonitorFromWindow": ([wintypes.HWND, wintypes.DWORD], wintypes.HANDLE),
            "GetMonitorInfoW": ([wintypes.HANDLE, ctypes.POINTER(_MonitorInfo)], wintypes.BOOL),
            "GetSystemMenu": ([wintypes.HWND, wintypes.BOOL], wintypes.HMENU),
            "EnableMenuItem": ([wintypes.HMENU, wintypes.UINT, wintypes.UINT], wintypes.BOOL),
            "TrackPopupMenu": ([wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, wintypes.HWND, ctypes.c_void_p], wintypes.UINT),
        }
        for name, (args, result) in signatures.items():
            function = getattr(self.user32, name)
            function.argtypes, function.restype = args, result
        self.dwmapi.DwmExtendFrameIntoClientArea.argtypes = [
            wintypes.HWND, ctypes.POINTER(_Margins)]
        self.dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
        self.dwmapi.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
        self.dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long

    def _extend_frame(self) -> None:
        # Do not use a window region or a layered/transparent main window: both
        # bypass DWM's actual compositor clipping and therefore lose its corners.
        policy = ctypes.c_int(2)  # DWMNCRP_ENABLED
        self.dwmapi.DwmSetWindowAttribute(self.hwnd, 2, ctypes.byref(policy), 4)
        corners = ctypes.c_int(2)  # DWMWCP_ROUND; Windows flattens maximized windows.
        self.dwmapi.DwmSetWindowAttribute(self.hwnd, 33, ctypes.byref(corners), 4)
        self.dwmapi.DwmExtendFrameIntoClientArea(self.hwnd, ctypes.byref(_Margins(1, 1, 1, 1)))

    def detach(self, *_args: object) -> None:
        if self.hwnd:
            self.comctl32.RemoveWindowSubclass(self.hwnd, self._callback, 1)
            self.hwnd = 0

    def _window_proc(self, hwnd: int, code: int, wparam: int, lparam: int,
                     _subclass_id: int, _reference: int) -> int:
        if code == 0x0082:  # WM_NCDESTROY: detach before the HWND can be reused.
            self.detach()
        else:
            try:
                msg = wintypes.MSG(hWnd=hwnd, message=code, wParam=wparam, lParam=lparam)
                handled, result = self._handle_message(msg)
                if handled:
                    return result
            except Exception:
                logging.getLogger(__name__).exception("Windows caption message failed: %#x", code)
        return int(self.comctl32.DefSubclassProc(hwnd, code, wparam, lparam))

    def command(self, index: int) -> None:
        commands = (0xF020, 0xF120 if self.user32.IsZoomed(self.hwnd) else 0xF030, 0xF060)
        if self.hwnd and 0 <= index < len(commands) and self._button_enabled(index):
            self.user32.PostMessageW(self.hwnd, 0x0112, commands[index], 0)

    def _button_enabled(self, index: int) -> bool:
        flags = (Qt.WindowType.WindowMinimizeButtonHint, Qt.WindowType.WindowMaximizeButtonHint,
                 Qt.WindowType.WindowCloseButtonHint)
        return bool(self.window.flags() & flags[index])

    def _set_hover(self, index: int) -> None:
        self.window.setProperty("captionHovered", index)

    def _reset_buttons(self) -> None:
        self._pressed = -1
        self.window.setProperty("captionPressed", -1)
        self._set_hover(-1)

    def hit_test(self, x: int, y: int) -> int:
        if self.window.windowState() == Qt.WindowState.WindowFullScreen:
            return HTCLIENT
        rect = wintypes.RECT()
        self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        dpi = self.user32.GetDpiForWindow(self.hwnd)
        control_width = int(self.window.property("captionControlWidth"))
        point = wintypes.POINT(x, y)
        self.user32.ScreenToClient(self.hwnd, ctypes.byref(point))
        actions = self.window.property("titleBarActionsRect")
        if (isinstance(actions, QRectF)
                and actions.contains(QPointF(point.x * 96 / dpi, point.y * 96 / dpi))
                and y > rect.top + 1):
            # Interactive QML toolbar controls must receive client mouse input;
            # treating them as caption would drag/maximize the window on click.
            return HTCLIENT
        if not self.user32.IsZoomed(self.hwnd):
            border = (self.user32.GetSystemMetricsForDpi(32, dpi)
                      + self.user32.GetSystemMetricsForDpi(92, dpi))
            left, right = x < rect.left + border, x >= rect.right - border
            top, bottom = y < rect.top + border, y >= rect.bottom - border
            # The control area extends to the top edge, except the outermost
            # pixel and resize corners. This gives the controls the full band.
            controls_left = rect.right - round(3 * control_width * dpi / 96)
            if left:
                return HTTOPLEFT if top else HTBOTTOMLEFT if bottom else HTLEFT
            if right and (y >= rect.top + border or y <= rect.top + 1):
                return HTTOPRIGHT if top else HTBOTTOMRIGHT if bottom else HTRIGHT
            if top and (x < controls_left or y <= rect.top + 1):
                return HTTOPRIGHT if right else HTTOP
            if bottom:
                return HTBOTTOMRIGHT if right else HTBOTTOM
        if point.y < round(float(self.window.property("titleBarHeight")) * dpi / 96):
            client = wintypes.RECT()
            self.user32.GetClientRect(self.hwnd, ctypes.byref(client))
            # Calculate all boundaries in physical pixels to avoid gaps at
            # fractional scaling (125%, 175%, …).
            for index, hit in enumerate(CAPTION_HITS):
                if (client.right - round((3 - index) * control_width * dpi / 96) <= point.x
                        < client.right - round((2 - index) * control_width * dpi / 96)):
                    return hit
            return HTCAPTION
        return HTCLIENT

    def _system_menu(self, x: int, y: int) -> None:
        menu = self.user32.GetSystemMenu(self.hwnd, False)
        maximized = self.user32.IsZoomed(self.hwnd)
        for command, disabled in ((0xF120, not maximized), (0xF030, maximized),
                                  (0xF000, maximized), (0xF010, maximized)):
            self.user32.EnableMenuItem(menu, command, 1 if disabled else 0)
        command = self.user32.TrackPopupMenu(menu, 0x0102, x, y, 0, self.hwnd, None)
        if command:
            self.user32.PostMessageW(self.hwnd, 0x0112, command, 0)

    def _client_hit(self, packed_position: int) -> int:
        point = wintypes.POINT(ctypes.c_short(packed_position & 0xFFFF).value,
                               ctypes.c_short((packed_position >> 16) & 0xFFFF).value)
        self.user32.ClientToScreen(self.hwnd, ctypes.byref(point))
        return self.hit_test(point.x, point.y)

    def _handle_message(self, msg: wintypes.MSG) -> tuple[bool, int]:
        if not self.hwnd or int(msg.hWnd or 0) != self.hwnd:
            return False, 0
        code = msg.message
        if code == 0x0083:  # WM_NCCALCSIZE: first field is RECT in either form.
            rect = wintypes.RECT.from_address(msg.lParam)
            if self.window.windowState() == Qt.WindowState.WindowFullScreen:
                return True, 0
            if self.user32.IsZoomed(self.hwnd):
                monitor = _MonitorInfo(size=ctypes.sizeof(_MonitorInfo))
                if self.user32.GetMonitorInfoW(
                    self.user32.MonitorFromWindow(self.hwnd, 2), ctypes.byref(monitor),
                ):
                    rect.left, rect.top = monitor.work.left, monitor.work.top
                    rect.right, rect.bottom = monitor.work.right, monitor.work.bottom
            else:
                rect.left += 1
                rect.top += 1
                rect.right -= 1
                rect.bottom -= 1
            return True, 0
        if code == 0x0084:  # WM_NCHITTEST, signed screen coordinates on any monitor.
            x = ctypes.c_short(msg.lParam & 0xFFFF).value
            y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
            return True, self.hit_test(x, y)
        if code in (0x00A0, 0x0200):  # WM_NCMOUSEMOVE / WM_MOUSEMOVE
            hit = (int(msg.wParam) if code == 0x00A0 else
                   self._client_hit(msg.lParam) if self._pressed >= 0 else HTCLIENT)
            index = CAPTION_HITS.index(hit) if hit in CAPTION_HITS else -1
            self._set_hover(index)
            tracking = _TrackMouseEvent(ctypes.sizeof(_TrackMouseEvent),
                                        0x12 if code == 0x00A0 else 0x02, self.hwnd, 0)
            self.user32.TrackMouseEvent(ctypes.byref(tracking))
            if index >= 0:
                # DefWindowProc receives HTMAXBUTTON so Windows 11 can provide
                # its Snap Layout flyout. The visible pixels are still QML.
                if index == 1 and self._pressed < 0:
                    self.user32.DefWindowProcW(self.hwnd, code, msg.wParam, msg.lParam)
                self._set_hover(index)
                return True, 0
        if code == 0x00A1 and msg.wParam in CAPTION_HITS:  # WM_NCLBUTTONDOWN
            self._pressed = CAPTION_HITS.index(msg.wParam)
            if not self._button_enabled(self._pressed):
                self._pressed = -1
                return True, 0
            self.window.setProperty("captionPressed", self._pressed)
            self.user32.SetCapture(self.hwnd)
            return True, 0
        if code in (0x00A2, 0x0202) and self._pressed >= 0:  # NC / captured client release
            pressed = self._pressed
            hit = (msg.wParam if code == 0x00A2 else self._client_hit(msg.lParam))
            self._reset_buttons()
            self.user32.ReleaseCapture()
            if hit == CAPTION_HITS[pressed]:
                self.command(pressed)
            return True, 0
        if code == 0x00A3 and msg.wParam in CAPTION_HITS:
            return True, 0  # No title-bar double-click action on a caption button.
        if code == 0x00A5 and msg.wParam == HTCAPTION:  # WM_NCRBUTTONUP
            self._system_menu(ctypes.c_short(msg.lParam & 0xFFFF).value,
                              ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value)
            return True, 0
        if code == 0x0104 and msg.wParam == 0x20:  # Alt+Space: native system menu
            rect = wintypes.RECT()
            self.user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
            dpi = self.user32.GetDpiForWindow(self.hwnd)
            self._system_menu(rect.left, rect.top + round(
                float(self.window.property("titleBarHeight")) * dpi / 96))
            return True, 0
        if code in (0x02A2, 0x02A3) and self._pressed < 0:
            self._set_hover(-1)
        if code in (0x001F, 0x0215) or (code == 0x0086 and not msg.wParam):
            self._reset_buttons()  # leave, cancel, lost capture or deactivation
            if self.user32.GetCapture() == self.hwnd:
                self.user32.ReleaseCapture()
        if code in (0x031E, 0x031A):  # DWM composition / theme changed
            self._extend_frame()
        return False, 0
