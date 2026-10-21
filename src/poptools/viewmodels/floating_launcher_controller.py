from __future__ import annotations

import logging
from typing import cast

from PySide6.QtCore import Property, QEvent, QObject, QRect, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QRegion, QScreen, QWindow
from PySide6.QtWidgets import QApplication

from poptools.domain.models import ToolSection
from poptools.viewmodels.app_controller import AppController
from poptools.viewmodels.settings_controller import SettingsController
from poptools.viewmodels.tool_list_model import ToolListModel

logger = logging.getLogger(__name__)


def edge_geometry(
    available: QRect, notch_size: tuple[int, int], panel_size: tuple[int, int], ratio: float,
) -> tuple[QRect, QRect]:
    """Position adjacent windows in logical screen coordinates, including negative origins."""
    width = min(notch_size[0], available.width())
    height = min(notch_size[1], available.height())
    y = available.y() + round(max(0, available.height() - height) * max(0, min(1, ratio)))
    notch = QRect(available.x() + available.width() - width, y, width, height)
    panel_width = min(panel_size[0], max(1, available.width() - width))
    panel_height = min(panel_size[1], available.height())
    panel_y = max(available.y(), min(y, available.y() + available.height() - panel_height))
    return notch, QRect(notch.x() - panel_width, panel_y, panel_width, panel_height)


class FloatingLauncherController(QObject):
    stateChanged = Signal()
    settingsRequested = Signal()
    toolSortModeChanged = Signal()
    drawerGeometryChanged = Signal()

    def __init__(
        self, app: QApplication, app_controller: AppController, settings: SettingsController,
    ) -> None:
        super().__init__(app)
        self._app = app
        self._backend = app_controller
        self._settings = settings
        self._model = ToolListModel()
        self._main_window: QWindow | None = None
        self._notch: QWindow | None = None
        self._panel: QWindow | None = None
        self._drawer_mode = False
        self._drawer_progress = 0.0
        self._drawer_animating = False
        self._drawer_tip_offset = 0
        self._screen: QScreen | None = None
        self._screen_name, self._ratio = settings.config_store.floating_launcher_position()
        self._notch_size = (44, 108)
        self._panel_size = (360, 480)
        self._visible = False
        self._expanded = False
        self._dragging = False
        self._drag_pointer_offset = 0
        self._menu_open = False
        self._quitting = False
        self._shortcut_tools: dict[str, bool] = {}
        self._capacity_requested = False
        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(300)
        self._collapse_timer.timeout.connect(self._collapse_if_outside)
        self._reconcile_timer = QTimer(self)
        self._reconcile_timer.setSingleShot(True)
        self._reconcile_timer.timeout.connect(self.reconcile)
        app.installEventFilter(self)
        app.applicationStateChanged.connect(self._schedule_reconcile)
        app.focusWindowChanged.connect(self._schedule_reconcile)
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self._screen_removed)
        app.aboutToQuit.connect(self.shutdown)
        for screen in app.screens():
            self._screen_added(screen)
        settings.floatingLauncherEnabledChanged.connect(self.reconcile)
        app_controller.customToolsChanged.connect(self.refreshTools)
        app_controller.toolSortModeChanged.connect(self.toolSortModeChanged)
        coordinator = app_controller.execution_coordinator
        coordinator.started.connect(self._on_started)
        coordinator.finished.connect(self._on_finished)
        coordinator.capacityRequested.connect(self._on_capacity)
        self.refreshTools()

    @Property(QObject, constant=True)
    def toolsModel(self) -> ToolListModel:
        return self._model

    @Property(bool, notify=stateChanged)
    def visible(self) -> bool:
        return self._visible

    @Property(bool, notify=stateChanged)
    def expanded(self) -> bool:
        return self._expanded

    @Property(bool, notify=stateChanged)
    def dragging(self) -> bool:
        return self._dragging

    @Property(int, notify=drawerGeometryChanged)
    def drawerTipOffset(self) -> int:
        return self._drawer_tip_offset

    @Property(str, notify=toolSortModeChanged)
    def toolSortMode(self) -> str:
        return cast(str, self._backend.toolSortMode)

    @Property(str, notify=toolSortModeChanged)
    def toolSortModeLabel(self) -> str:
        return cast(str, self._backend.toolSortModeLabel)

    @Slot(str, result=bool)
    def setToolSortMode(self, mode: str) -> bool:
        return self._backend.setToolSortMode(mode)

    @Slot(str)
    def setToolSearchQuery(self, query: str) -> None:
        self._model.set_filter(query)

    @Slot()
    def refreshTools(self) -> None:
        tools = self._backend.sorted_custom_tools(
            self._backend.registry.for_section(ToolSection.CUSTOM)
        )
        running = {tool.id for tool in tools
                   if self._backend.execution_coordinator.running(tool.id)
                   or tool.id in self._shortcut_tools}
        tools.sort(key=lambda tool: tool.id not in running)
        self._model.set_tools(tools, running_ids=running)

    def attach_main_window(self, window: QWindow) -> None:
        self._main_window = window
        if not self._screen_name:
            self._screen = window.screen()
        self.reposition()
        self._schedule_reconcile()

    @Slot(QObject, QObject, int, int, int, int)
    def attachWindows(
        self, notch: QObject, panel: QObject, width: int, height: int,
        panel_width: int, panel_height: int,
    ) -> None:
        self._drawer_mode = False
        self._notch = cast(QWindow, notch)
        self._panel = cast(QWindow, panel)
        self._notch_size = (width, height)
        self._panel_size = (panel_width, panel_height)
        self.reposition()

    @Slot(QObject, int, int, int, int)
    def attachDrawerWindow(
        self, window: QObject, tip_width: int, tip_height: int,
        panel_width: int, panel_height: int,
    ) -> None:
        self._drawer_mode = True
        self._notch = self._panel = cast(QWindow, window)
        self._notch_size = (tip_width, tip_height)
        self._panel_size = (panel_width, panel_height)
        self.reposition()

    @Slot(float)
    def setDrawerProgress(self, progress: float) -> None:
        self._drawer_progress = max(0.0, min(1.0, progress))
        if self._drawer_mode:
            self.reposition()

    @Slot(bool)
    def setDrawerAnimating(self, animating: bool) -> None:
        self._drawer_animating = animating
        if self._drawer_mode:
            self.reposition()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QWindow) and event.type() in {
            QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange,
            QEvent.Type.FocusIn, QEvent.Type.FocusOut,
        }:
            self._schedule_reconcile()
        return False

    def _schedule_reconcile(self, *_args: object) -> None:
        if not self._quitting:
            self._reconcile_timer.start(0)

    def _is_launcher_window(self, window: QWindow) -> bool:
        current: QWindow | None = window
        while current is not None:
            if (current in (self._notch, self._panel)
                    or current.property("keepsFloatingLauncherVisible")):
                return True
            current = current.transientParent()
        return False

    def _ordinary_window_active(self) -> bool:
        if self._app.applicationState() != Qt.ApplicationState.ApplicationActive:
            return False
        modal = self._app.activeModalWidget()
        if modal is not None:
            handle = modal.windowHandle()
            return handle is None or not self._is_launcher_window(handle)
        focus = self._app.focusWindow()
        if focus is not None and focus.isVisible() and self._is_launcher_window(focus):
            return False
        return any(
            window.isVisible() and window.isActive()
            and window.visibility() != QWindow.Visibility.Minimized
            and not self._is_launcher_window(window)
            for window in self._app.topLevelWindows()
        )

    @Slot()
    def reconcile(self) -> None:
        visible = (
            not self._quitting and self._main_window is not None
            and bool(self._settings.floatingLauncherEnabled) and not self._ordinary_window_active()
        )
        if visible == self._visible:
            return
        self._visible = visible
        if not visible:
            self.collapse()
        else:
            self.reposition()
        self.stateChanged.emit()

    @Slot()
    def toggleExpanded(self) -> None:
        if not self._visible or self._dragging:
            return
        if self._expanded:
            self.collapse()
        else:
            self.refreshTools()
            self.reposition()
            self._expanded = True
            self.stateChanged.emit()

    @Slot()
    def collapse(self) -> None:
        self._collapse_timer.stop()
        self._menu_open = False
        if self._expanded:
            self._expanded = False
            self.stateChanged.emit()

    @Slot(bool)
    def setMenuOpen(self, opened: bool) -> None:
        self._menu_open = opened
        self.pointerChanged()

    def _pointer_inside(self) -> bool:
        point = QCursor.pos()
        if self._drawer_mode and self._panel is not None:
            return (self._panel.isVisible()
                    and self._panel.mask().contains(point - self._panel.position()))
        return any(window is not None and window.isVisible() and window.geometry().contains(point)
                   for window in (self._notch, self._panel))

    @Slot()
    def pointerChanged(self) -> None:
        if not self._expanded or self._dragging or self._menu_open or self._pointer_inside():
            self._collapse_timer.stop()
        elif not self._collapse_timer.isActive():
            self._collapse_timer.start()

    def _collapse_if_outside(self) -> None:
        if not self._dragging and not self._menu_open and not self._pointer_inside():
            self.collapse()

    @Slot()
    def beginDrag(self) -> None:
        if not self._drawer_mode:
            self.collapse()
        if self._notch is not None:
            self._drag_pointer_offset = (QCursor.pos().y() - self._notch.y()
                                         - self._drawer_tip_offset)
        self._dragging = True
        self.stateChanged.emit()

    @Slot()
    def updateDrag(self) -> None:
        if self._dragging and self._notch is not None:
            # Window moves can generate MouseArea events whose local positions
            # still refer to the old geometry. Read an independent screen position.
            self.dragTo(QCursor.pos().y() - self._drag_pointer_offset)

    @Slot(int)
    def dragTo(self, global_y: int) -> None:
        if not self._dragging or self._screen is None:
            return
        available = self._screen.availableGeometry()
        travel = max(1, available.height() - self._notch_size[1])
        ratio = max(0.0, min(1.0, (global_y - available.y()) / travel))
        if ratio == self._ratio:
            return
        self._ratio = ratio
        self.reposition()

    @Slot()
    def endDrag(self) -> None:
        self.updateDrag()
        self._dragging = False
        self._screen_name = self._screen.name() if self._screen else ""
        try:
            self._settings.config_store.set_floating_launcher_position(
                self._screen_name, self._ratio,
            )
        except OSError:
            logger.exception("无法保存悬浮入口位置")
        self.stateChanged.emit()

    @Slot()
    def openSettings(self) -> None:
        self.collapse()
        self.settingsRequested.emit()

    @Slot(str)
    def launchTool(self, tool_id: str) -> None:
        tool = self._backend.registry.get(tool_id)
        if (tool is None or tool.section != ToolSection.CUSTOM
                or self._backend.execution_coordinator.running(tool_id)
                or tool_id in self._shortcut_tools):
            return
        self.collapse()
        self._shortcut_tools[tool_id] = False
        self._capacity_requested = False
        accepted = self._backend.open_custom_tool_shortcut(tool_id)
        if accepted is not True:
            tracked = self._shortcut_tools.pop(tool_id, None)
            if accepted is False and tracked is not None and not self._capacity_requested:
                self._backend.recentToolDialogRequested.emit(tool_id)
        self.refreshTools()

    def _on_started(self, tool_id: str) -> None:
        if tool_id in self._shortcut_tools:
            self._shortcut_tools[tool_id] = True

    def _on_finished(self, tool_id: str, exit_code: int) -> None:
        started = self._shortcut_tools.pop(tool_id, None)
        if started is False and exit_code != 0:
            self._backend.recentToolDialogRequested.emit(tool_id)
        self.refreshTools()

    def _on_capacity(self, *_args: str) -> None:
        # Capacity dialogs belong to the main window, including launches from the compact window.
        if self._shortcut_tools:
            self._capacity_requested = True
        if self._main_window is not None and not self._ordinary_window_active():
            self._main_window.showNormal()
            self._main_window.raise_()
            self._main_window.requestActivate()

    def _screen_added(self, screen: QScreen) -> None:
        screen.availableGeometryChanged.connect(self.reposition)
        screen.geometryChanged.connect(self.reposition)
        screen.logicalDotsPerInchChanged.connect(self.reposition)
        self.reposition()

    def _screen_removed(self, screen: QScreen) -> None:
        if self._screen is screen:
            self._screen = None
        QTimer.singleShot(0, self.reposition)

    def reposition(self, *_args: object) -> None:
        if self._quitting:
            return
        screens = self._app.screens()
        if self._screen not in screens:
            self._screen = next((s for s in screens if s.name() == self._screen_name), None)
            if self._screen is None:
                self._screen = self._app.primaryScreen()
        if self._screen is None or self._notch is None or self._panel is None:
            return
        notch, panel = edge_geometry(
            self._screen.availableGeometry(), self._notch_size, self._panel_size, self._ratio,
        )
        if self._drawer_mode:
            exposed_width = int(panel.width() * self._drawer_progress + 0.5)
            surface_offset = panel.width() - exposed_width
            tip_offset = notch.y() - panel.y()
            # Keep the native backing surface stable during the animation.
            # Resizing it on every frame can leave stale/clipped textures in DWM.
            geometry = QRect(panel.x(), panel.y(), notch.width() + panel.width(), panel.height())
            if self._panel.geometry() != geometry:
                self._panel.setGeometry(geometry)
            mask = QRegion(QRect(surface_offset, tip_offset, notch.width(), notch.height()))
            if exposed_width:
                mask |= QRegion(QRect(surface_offset + notch.width(), 0,
                                      exposed_width, panel.height()))
            if self._drawer_animating:
                # DWM applies native regions independently of the Qt render frame.
                # A moving region can crop the preceding frame; let Qt clip the
                # slide, then restore the precise input region after the final swap.
                mask = QRegion(QRect(0, 0, geometry.width(), geometry.height()))
            if self._panel.mask() != mask:
                self._panel.setMask(mask)
            if tip_offset != self._drawer_tip_offset:
                self._drawer_tip_offset = tip_offset
                self.drawerGeometryChanged.emit()
            return
        self._notch.setGeometry(notch)
        self._panel.setGeometry(panel)

    @Slot()
    def shutdown(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        self._visible = False
        self.collapse()
        self._reconcile_timer.stop()
        self._app.removeEventFilter(self)
        self.stateChanged.emit()
        for window in (self._notch, self._panel):
            if window is not None:
                window.hide()
