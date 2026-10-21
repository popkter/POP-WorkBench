from __future__ import annotations

import ctypes
import os
import re
import uuid
from typing import Any

from PySide6.QtCore import QObject, QRect, QTimer, Signal
from PySide6.QtGui import QWindow

from poptools.infrastructure.background_process import BackgroundProcess
from poptools.paths import (
    bundled_adb_path,
    bundled_android_tools_dir,
    bundled_scrcpy_path,
)

_SCRCPY_STARTUP_POSITION = -32000
_VIDEO_SIZE_PATTERN = re.compile(r"(?:Texture|Video size):\s*(\d+)x(\d+)", re.IGNORECASE)


def _projection_arguments(
    serial: str, window_title: str, embed: bool | None = None, display_id: int = 0
) -> list[str]:
    """Create a native projection window appropriate for the host platform."""
    arguments = [
        "--serial",
        serial,
        "--window-title",
        window_title,
        "--no-audio",
        f"--display-id={display_id}",
    ]
    if embed is None:
        embed = os.name == "nt"
    if not embed:
        return arguments
    return [
        *arguments,
        "--window-borderless",
        "--no-window-aspect-ratio-lock",
        f"--window-x={_SCRCPY_STARTUP_POSITION}",
        f"--window-y={_SCRCPY_STARTUP_POSITION}",
        "--window-width=1",
        "--window-height=1",
    ]


class ScrcpyController(QObject):
    """Run the bundled scrcpy client and host its native window inside PopTools."""

    output = Signal(str)
    started = Signal()
    runningChanged = Signal(bool)
    finished = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: BackgroundProcess | None = None
        self._started = False
        self._host_window: QWindow | None = None
        self._scrcpy_window = 0
        self._host_rect = QRect()
        self._host_visible = False
        self._window_title = ""
        self._embed_attempts = 0
        self._synced_window = 0
        self._synced_rect = QRect()
        self._synced_visible = False
        self._video_aspect_ratio: float | None = None
        self._dimension_output_tail = ""
        self._embed_timer = QTimer(self)
        self._embed_timer.setInterval(10)
        self._embed_timer.timeout.connect(self._try_embed_window)

    @property
    def running(self) -> bool:
        return self._started

    @property
    def active(self) -> bool:
        return self._process is not None

    def attach_window(self, window: QWindow) -> None:
        self._host_window = window

    def start(self, serial: str, display_id: int = 0) -> bool:
        if self.active:
            return False
        scrcpy = bundled_scrcpy_path()
        adb = bundled_adb_path()
        server = bundled_android_tools_dir() / "scrcpy-server"
        missing = [path.name for path in (scrcpy, adb, server) if not path.is_file()]
        if missing:
            self.output.emit(f"内置投屏组件不完整：{', '.join(missing)}\n")
            return False
        if not serial:
            self.output.emit("请先选择已连接的 Android 设备。\n")
            return False
        if self._host_window is None:
            self.output.emit("投屏区域尚未准备好，请稍后重试。\n")
            return False

        self._window_title = f"PopTools-scrcpy-{uuid.uuid4().hex}"
        process = BackgroundProcess(self)
        process.stdoutReady.connect(self._read_output)
        process.stderrReady.connect(self._read_error)
        process.started.connect(self._on_started)
        process.errorOccurred.connect(self._on_error)
        process.finished.connect(self._on_finished)
        self._process = process
        self._started = False
        self._scrcpy_window = 0
        self._embed_attempts = 0
        self._video_aspect_ratio = None
        self._dimension_output_tail = ""
        self._reset_synced_geometry()
        environment = dict(os.environ)
        environment["ADB"] = str(adb)
        environment["SCRCPY_SERVER_PATH"] = str(server)
        environment["PATH"] = f"{scrcpy.parent}{os.pathsep}{environment.get('PATH', '')}"
        accepted = process.start(
            str(scrcpy),
            _projection_arguments(serial, self._window_title, display_id=display_id),
            cwd=scrcpy.parent,
            environment=environment,
        )
        if not accepted:
            self._process = None
            process.deleteLater()
            return False
        self.output.emit(f"正在连接设备 {serial} 的屏幕 {display_id} 并启动应用内投屏…\n")
        return True

    def stop(self) -> None:
        process = self._process
        if process is None:
            return
        self._embed_timer.stop()
        if self._scrcpy_window:
            _show_window(self._scrcpy_window, False)
            _close_window(self._scrcpy_window)
        else:
            process.terminate()
        # Delayed cleanup must never terminate a replacement projection session.
        QTimer.singleShot(500, lambda: process.terminate() if self._process is process else None)
        QTimer.singleShot(2500, lambda: process.kill() if self._process is process else None)

    def set_geometry(self, rect: QRect, visible: bool) -> None:
        self._host_rect = QRect(rect)
        self._host_visible = visible
        self._sync_embedded_window()

    def _try_embed_window(self) -> None:
        process = self._process
        if process is None:
            self._embed_timer.stop()
            return
        if self._scrcpy_window:
            if _is_window(self._scrcpy_window):
                return
            # SDL may replace its startup window when the video renderer is
            # initialized. Resume discovery instead of retaining a dead HWND
            # and leaving only the QML placeholder visible.
            self._scrcpy_window = 0
            self._embed_attempts = 0
            self._reset_synced_geometry()
            self._embed_timer.setInterval(10)
        self._embed_attempts += 1
        handle = _find_process_window(process.process_id, self._window_title)
        if handle:
            # The window starts offscreen. Wait until SDL has shown it so a
            # short-lived pre-renderer window is not mistaken for the final
            # video window, then hide and embed it in one event-loop turn.
            _show_window(handle, False)
            self._scrcpy_window = handle
            self._reset_synced_geometry()
            if self._host_window is None or not _embed_window(
                handle, int(self._host_window.winId())
            ):
                self.output.emit("无法将 scrcpy 窗口嵌入应用。\n")
                self.stop()
                return
            self._sync_embedded_window()
            self._embed_timer.setInterval(250)
            self.output.emit("投屏已连接。\n")
        elif self._embed_attempts >= 1000:
            self._embed_timer.stop()
            self.output.emit("等待 scrcpy 投屏窗口超时。\n")
            self.stop()

    def _sync_embedded_window(self) -> None:
        if not self._scrcpy_window or self._host_window is None:
            return
        scale = self._host_window.devicePixelRatio()
        rect = QRect(
            round(self._host_rect.x() * scale),
            round(self._host_rect.y() * scale),
            round(self._host_rect.width() * scale),
            round(self._host_rect.height() * scale),
        )
        rect = self._fit_rect_to_video(rect)
        visible = self._host_visible and not rect.isEmpty()
        if (
            self._synced_window == self._scrcpy_window
            and self._synced_rect == rect
            and self._synced_visible == visible
            and _embedded_window_state_matches(self._scrcpy_window, rect, visible)
        ):
            return
        _move_window(self._scrcpy_window, rect, visible)
        self._synced_window = self._scrcpy_window
        self._synced_rect = QRect(rect)
        self._synced_visible = visible

    def _reset_synced_geometry(self) -> None:
        self._synced_window = 0
        self._synced_rect = QRect()
        self._synced_visible = False

    def _fit_rect_to_video(self, host_rect: QRect) -> QRect:
        aspect_ratio = self._video_aspect_ratio
        if aspect_ratio is None or host_rect.isEmpty():
            return QRect(host_rect)

        width = host_rect.width()
        height = max(1, round(width / aspect_ratio))
        if height > host_rect.height():
            height = host_rect.height()
            width = max(1, round(height * aspect_ratio))
        return QRect(
            host_rect.x() + (host_rect.width() - width) // 2,
            host_rect.y() + (host_rect.height() - height) // 2,
            width,
            height,
        )

    def _update_video_dimensions(self, text: str) -> None:
        combined = self._dimension_output_tail + text
        self._dimension_output_tail = combined[-160:]
        matches = list(_VIDEO_SIZE_PATTERN.finditer(combined))
        if not matches:
            return
        width = int(matches[-1].group(1))
        height = int(matches[-1].group(2))
        if width <= 0 or height <= 0:
            return
        aspect_ratio = width / height
        if self._video_aspect_ratio == aspect_ratio:
            return
        self._video_aspect_ratio = aspect_ratio
        self._reset_synced_geometry()
        self._sync_embedded_window()

    def _on_started(self) -> None:
        self._started = True
        if os.name == "nt":
            self._embed_timer.start()
        else:
            self.output.emit("投屏已在独立窗口中打开。\n")
        self.started.emit()
        self.runningChanged.emit(True)

    def _read_output(self, payload: bytes) -> None:
        text = payload.decode("utf-8", "replace")
        self._update_video_dimensions(text)
        self.output.emit(text)

    def _read_error(self, payload: bytes) -> None:
        text = payload.decode("utf-8", "replace")
        self._update_video_dimensions(text)
        self.output.emit(text)

    def _on_error(self, message: str) -> None:
        self.output.emit(f"投屏启动失败：{message}\n")

    def _on_finished(self, exit_code: int) -> None:
        self._finalize(exit_code)

    def _finalize(self, exit_code: int) -> None:
        process = self._process
        if process is None:
            return
        self._embed_timer.stop()
        self._process = None
        was_started = self._started
        self._started = False
        self._scrcpy_window = 0
        self._video_aspect_ratio = None
        self._dimension_output_tail = ""
        self._reset_synced_geometry()
        process.deleteLater()
        if was_started:
            self.runningChanged.emit(False)
        self.finished.emit(exit_code)

    def _terminate_if_running(self) -> None:
        if self._process is not None:
            self._process.terminate()

    def _kill_if_running(self) -> None:
        if self._process is not None:
            self._process.kill()


def _user32() -> Any:
    return ctypes.WinDLL("user32", use_last_error=True)


def _find_process_window(process_id: int, title: str) -> int:
    if os.name != "nt" or not process_id:
        return 0
    user32 = _user32()
    # The title is a UUID, so looking it up directly avoids running a Python
    # callback from EnumWindows. Only accept a window SDL has shown: before the
    # renderer is ready, SDL may create and destroy a hidden window with the
    # same title.
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    handle = user32.FindWindowW(None, title)
    if not handle or not _is_window_visible(int(handle)):
        return 0
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
    window_pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(window_pid))
    return int(handle) if window_pid.value == process_id else 0


def _is_window(handle: int) -> bool:
    if os.name != "nt" or not handle:
        return False
    user32 = _user32()
    user32.IsWindow.argtypes = [ctypes.c_void_p]
    user32.IsWindow.restype = ctypes.c_bool
    return bool(user32.IsWindow(handle))


def _is_window_visible(handle: int) -> bool:
    if os.name != "nt" or not handle:
        return False
    user32 = _user32()
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_bool
    return bool(user32.IsWindowVisible(handle))


def _embedded_window_state_matches(handle: int, expected: QRect, visible: bool) -> bool:
    """Check whether scrcpy changed its own embedded window geometry."""
    if os.name != "nt" or not handle:
        return True
    user32 = _user32()

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(RECT)]
    user32.GetWindowRect.restype = ctypes.c_bool
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.ClientToScreen.argtypes = [ctypes.c_void_p, ctypes.POINTER(POINT)]
    user32.ClientToScreen.restype = ctypes.c_bool

    actual = RECT()
    parent = user32.GetParent(handle)
    parent_origin = POINT()
    if (
        not parent
        or not user32.GetWindowRect(handle, ctypes.byref(actual))
        or not user32.ClientToScreen(parent, ctypes.byref(parent_origin))
    ):
        return False

    actual_rect = QRect(
        actual.left - parent_origin.x,
        actual.top - parent_origin.y,
        actual.right - actual.left,
        actual.bottom - actual.top,
    )
    return actual_rect == expected and _is_window_visible(handle) == visible


def _embed_window(child: int, parent: int) -> bool:
    if os.name != "nt" or not child or not parent:
        return False
    user32 = _user32()
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    user32.SetParent.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    user32.SetParent.restype = ctypes.c_void_p
    style = int(get_style(child, -16))
    style &= ~(0x80000000 | 0x00C00000 | 0x00040000 | 0x00080000 | 0x00030000)
    style |= 0x40000000
    set_style(child, -16, style)
    ctypes.set_last_error(0)
    previous_parent = user32.SetParent(child, parent)
    return bool(previous_parent) or ctypes.get_last_error() == 0


def _move_window(handle: int, rect: QRect, visible: bool) -> None:
    if os.name != "nt" or not handle:
        return
    user32 = _user32()
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_bool

    if not visible:
        _show_window(handle, False)
        return
    user32.SetWindowPos(
        handle,
        0,
        rect.x(),
        rect.y(),
        max(1, rect.width()),
        max(1, rect.height()),
        # Keep the embedded child in its current z-order and avoid forcing a
        # non-client frame refresh on every geometry update. Reapplying either
        # while the host receives mouse focus causes SDL's surface to flash.
        0x0004 | 0x0010 | 0x0040,
    )


def _show_window(handle: int, visible: bool) -> None:
    if os.name == "nt" and handle:
        user32 = _user32()
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.ShowWindow(handle, 5 if visible else 0)


def _hide_window_from_taskbar(handle: int) -> bool:
    """Hide a top-level window and turn it into a non-taskbar tool window."""
    if os.name != "nt" or not handle:
        return False
    user32 = _user32()
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    set_style.restype = ctypes.c_ssize_t
    user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = ctypes.c_bool

    _show_window(handle, False)
    extended_style = int(get_style(handle, -20))
    extended_style = (extended_style | 0x00000080) & ~0x00040000
    set_style(handle, -20, extended_style)
    # Apply the changed non-client style without moving, resizing or showing it.
    return bool(user32.SetWindowPos(handle, 0, 0, 0, 0, 0, 0x0037))


def _close_window(handle: int) -> None:
    if os.name != "nt" or not handle:
        return
    user32 = _user32()
    user32.PostMessageW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    user32.PostMessageW.restype = ctypes.c_bool
    user32.PostMessageW(handle, 0x0010, 0, 0)
