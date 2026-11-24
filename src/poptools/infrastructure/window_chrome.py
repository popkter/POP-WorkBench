"""Size the window once and connect its client-drawn caption to the platform."""

import sys

from PySide6.QtCore import QEvent, QMargins, QObject, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QWindow


def initial_window_size(
    preferred: QSize, minimum: QSize, available: QSize, frame: QMargins,
) -> QSize:
    """Cap the outer window size while respecting the usable client minimum."""
    return QSize(
        max(minimum.width(), min(preferred.width(), int(available.width() * 0.85))
            - frame.left() - frame.right()),
        max(minimum.height(), min(preferred.height(), int(available.height() * 0.85))
            - frame.top() - frame.bottom()),
    )


class WindowChromeController(QObject):
    systemMenuRequested = Signal(float, float)

    def __init__(self, window: QWindow) -> None:
        super().__init__(window)
        self._window = window
        preferred = window.size()
        custom_frame = (sys.platform == "win32" and QGuiApplication.platformName() == "windows"
                        and window.property("customTitleBar"))
        if custom_frame:
            from poptools.infrastructure.windows_frame import prepare_windows_frame

            prepare_windows_frame(window)
        window.create()
        self._frame = None
        if custom_frame:
            from poptools.infrastructure.windows_frame import WindowsFrame

            window.setProperty("modernCaptionControls", sys.getwindowsversion().build >= 22000)
            self._frame = WindowsFrame(window, system_menu_requested=self._request_system_menu)
        window.setProperty("chromeController", self)
        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self.synchronize)
        window.installEventFilter(self)
        self.synchronize()
        screen = window.screen()
        if screen is not None:
            window.resize(initial_window_size(
                preferred, window.minimumSize(), screen.availableGeometry().size(),
                window.frameMargins(),
            ))
        window.show()

    def synchronize(self) -> None:
        self._window.setProperty("nativeTitleBarHeight", max(0, self._window.frameMargins().top()))

    @Slot(int)
    def captionCommand(self, index: int) -> None:
        if self._frame is not None:
            self._frame.command(index)

    def _request_system_menu(self, x: float, y: float) -> None:
        # Open QML after returning from the native non-client message handler.
        QTimer.singleShot(0, lambda: self.systemMenuRequested.emit(x, y))

    @Slot(str)
    def windowCommand(self, command: str) -> None:
        if self._frame is None:
            return
        flags = self._window.flags()
        maximized = self._window.windowState() == Qt.WindowMaximized
        minimized = self._window.windowState() == Qt.WindowMinimized
        commands = {
            "restore": (0xF120, maximized or minimized),
            "move": (0xF010, not maximized and not minimized),
            "resize": (0xF000, not maximized and not minimized
                       and not flags & Qt.MSWindowsFixedSizeDialogHint
                       and self._window.minimumSize() != self._window.maximumSize()),
            "minimize": (0xF020, bool(flags & Qt.WindowMinimizeButtonHint) and not minimized),
            "maximize": (0xF030, bool(flags & Qt.WindowMaximizeButtonHint) and not maximized),
            "close": (0xF060, bool(flags & Qt.WindowCloseButtonHint)),
        }
        code, enabled = commands.get(command, (0, False))
        if enabled:
            self._frame.user32.ReleaseCapture()
            self._frame.user32.PostMessageW(self._frame.hwnd, 0x0112, code, 0)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._window and event.type() in (
            QEvent.Type.Show, QEvent.Type.Resize, QEvent.Type.WindowStateChange,
            QEvent.Type.ScreenChangeInternal, QEvent.Type.DevicePixelRatioChange,
        ):
            self._sync_timer.start(0)
        return False
