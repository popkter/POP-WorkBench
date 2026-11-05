from __future__ import annotations

import ctypes
import os
import sys
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING

from PySide6.QtCore import Property, QObject, Qt, Signal, Slot
from PySide6.QtGui import QIcon, QShowEvent, QWindow
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from poptools.infrastructure.windows_integration import disable_windows_system_backdrop
from poptools.paths import resource_path

if TYPE_CHECKING:
    from poptools.viewmodels.app_controller import AppController


def create_app_icon() -> QIcon:
    icon_name = "app-icon.ico" if sys.platform == "win32" else "app-icon.png"
    icon = QIcon(str(resource_path("icons", icon_name)))
    if icon.isNull():
        raise RuntimeError("应用图标资源无法加载")
    return icon


@contextmanager
def _raster_menu_surface():
    """Scope the QPA switch across creation, recreation and native show."""
    setting = "QT_QPA_DISABLE_REDIRECTION_SURFACE"
    previous = os.environ.pop(setting, None) if sys.platform == "win32" else None
    try:
        yield
    finally:
        if sys.platform == "win32" and previous is not None:
            os.environ[setting] = previous


class _TrayMenu(QMenu):
    """Use Qt's original menu painting, independently of the QML Glass theme."""

    def __init__(self, title: str = "") -> None:
        super().__init__(title)
        self._surface_scope: AbstractContextManager | None = None
        self.aboutToShow.connect(self._prepare_popup_surface)
        self.ensurePolished()
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        if sys.platform == "win32":
            # Qt's fade/scroll helpers allocate separate raster HWNDs outside
            # the menu's lifetime. QML transitions are unaffected by these flags.
            QApplication.setEffectEnabled(Qt.UIEffect.UI_AnimateMenu, False)
            QApplication.setEffectEnabled(Qt.UIEffect.UI_FadeMenu, False)
            # Qt's QPA switch affects raster popups too, not just D3D windows.
            # Allocate the menu HWND with its ordinary GDI bitmap, before the
            # first popup. Changing this native style after creation is rejected
            # by Windows. No event loop runs while the setting is overridden.
            with _raster_menu_surface():
                self.winId()

    def setVisible(self, visible: bool) -> None:
        if not visible or sys.platform != "win32":
            super().setVisible(visible)
            return
        # A theme, screen or native parent change can destroy the HWND after
        # construction. QMenu::popup/exec call this virtual method on every show.
        with _raster_menu_surface():
            self.ensurePolished()
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
            self.winId()
            super().setVisible(True)

    def _prepare_popup_surface(self) -> None:
        # QMenu can change screens/recreate its HWND *before* setVisible().
        # Keep the override through that whole synchronous popup preparation.
        if sys.platform == "win32" and self._surface_scope is None:
            self._surface_scope = _raster_menu_surface()
            self._surface_scope.__enter__()
            # QMenu creates a window for screen metrics before aboutToShow.
            # If that was a replacement HWND, it may already have inherited
            # the D3D-only flag. Recreate it while hidden; changing this flag
            # in place cannot restore the bitmap on Windows.
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
            hwnd = int(self.winId())
            if user32.GetWindowLongPtrW(hwnd, -20) & 0x00200000:
                self.destroy()
                self.winId()

    def _finish_popup_surface(self) -> None:
        scope, self._surface_scope = self._surface_scope, None
        if scope is not None:
            scope.__exit__(None, None, None)

    def showEvent(self, event: QShowEvent) -> None:
        try:
            super().showEvent(event)
            # Apply after Qt has created and polished the popup's native window.
            disable_windows_system_backdrop(int(self.winId()))
            self.update()
        finally:
            self._finish_popup_surface()


class SystemTrayController(QObject):
    quittingChanged = Signal()

    def __init__(
        self,
        app: QApplication,
    ) -> None:
        super().__init__(app)
        self._app = app
        self._app_controller: AppController | None = None
        self._window: QWindow | None = None
        self._quitting = False
        self._notified = False
        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        self.icon = create_app_icon()
        self._tray = QSystemTrayIcon(self.icon, self)
        self._tray.setToolTip("泡泡的工作台")
        self._menu = _TrayMenu()
        self._show_action = self._menu.addAction("显示主界面")
        self._show_action.triggered.connect(self.show_window)
        self._preset_menu = _TrayMenu("预置功能")
        self._preset_menu.aboutToShow.connect(self._build_preset_menu)
        self._menu.addMenu(self._preset_menu)
        self._recent_menu = _TrayMenu("最近使用")
        self._recent_menu.aboutToShow.connect(self._build_recent_menu)
        self._menu.addMenu(self._recent_menu)
        self._menu.addSeparator()
        self._exit_action = self._menu.addAction("退出")
        self._exit_action.triggered.connect(self.quit_application)
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        if self._available:
            self._app.setQuitOnLastWindowClosed(False)
            self._tray.show()

    @Property(bool, constant=True)
    def available(self) -> bool:
        return self._available

    @Property(bool, notify=quittingChanged)
    def quitting(self) -> bool:
        return self._quitting

    def attach_window(self, window: QWindow) -> None:
        self._window = window

    def set_app_controller(self, app_controller: AppController) -> None:
        self._app_controller = app_controller

    @Slot()
    def notify_hidden(self) -> None:
        if not self._available or self._notified:
            return
        self._notified = True
        self._tray.showMessage(
            "泡泡的工作台 已最小化到托盘",
            "右键托盘图标可直接使用预置功能，也可显示主界面或退出。",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

    @Slot()
    def show_window(self) -> None:
        if self._window is None:
            return
        if self._window.windowStates() & Qt.WindowState.WindowMinimized:
            self._window.setWindowStates(
                self._window.windowStates() & ~Qt.WindowState.WindowMinimized)
        self._window.setVisible(True)
        self._window.raise_()
        self._window.requestActivate()

    @Slot()
    def quit_application(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self.quittingChanged.emit()
        self._tray.hide()
        if self._window is not None:
            self._window.close()
        self._app.quit()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.show_window()

    def _build_recent_menu(self) -> None:
        self._recent_menu.clear()
        if self._app_controller is None:
            self._recent_menu.addAction("(暂无最近使用)").setEnabled(False)
            return
        recent = self._app_controller.getRecentTools()
        if not recent:
            self._recent_menu.addAction("(暂无最近使用)").setEnabled(False)
            return
        for item in recent:
            tool_id = item["toolId"]
            title = item["title"]
            action = self._recent_menu.addAction(title)
            action.triggered.connect(
                lambda checked=False, tid=tool_id: self._app_controller.openRecentToolFromTray(tid)
            )

    def _build_preset_menu(self) -> None:
        self._preset_menu.clear()
        if self._app_controller is None:
            self._preset_menu.addAction("(暂无预置功能)").setEnabled(False)
            return
        presets = self._app_controller.getPresetTools()
        if not presets:
            self._preset_menu.addAction("(暂无预置功能)").setEnabled(False)
            return
        for item in presets:
            tool_id = item["toolId"]
            title = item["title"]
            action = self._preset_menu.addAction(title)
            action.triggered.connect(
                lambda checked=False, tid=tool_id: self._app_controller.openPresetToolFromTray(tid)
            )
