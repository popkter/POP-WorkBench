from __future__ import annotations

import logging
import os
from typing import cast

from PySide6.QtCore import (
    Property,
    QEvent,
    QObject,
    QRect,
    QRectF,
    Qt,
    QTimer,
    Signal,
    Slot,
)
from PySide6.QtGui import QCursor, QRegion, QScreen, QWindow
from PySide6.QtWidgets import QApplication

from poptools.domain.models import ToolSection
from poptools.infrastructure.foreground_window import foreground_window, window_under_cursor
from poptools.infrastructure.window_placement import sync_launcher_card_layers
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


def dock_geometry(available: QRect, size: tuple[int, int]) -> QRect:
    """A centered bottom Dock inside the work area, in logical coordinates."""
    margin = min(16, max(0, (min(available.width(), available.height()) - 1) // 2))
    width = min(size[0], max(1, available.width() - margin * 2))
    height = min(size[1], max(1, available.height() - margin * 2))
    return QRect(available.x() + (available.width() - width) // 2,
                 available.y() + available.height() - margin - height, width, height)


def decade_pack_geometry(
    available: QRect, closed_size: tuple[int, int], pack_size: tuple[int, int], ratio: float,
) -> tuple[QRect, QRect]:
    """Keep Decade on the left edge with a continuous vertical position."""
    margin = min(16, max(0, (min(available.width(), available.height()) - 1) // 2))
    bounds = available.adjusted(margin, margin, -margin, -margin)
    width = min(closed_size[0], bounds.width())
    height = min(closed_size[1], bounds.height())
    closed_y = bounds.top() + round(max(0, bounds.height() - height)
                                    * max(0.0, min(1.0, ratio)))
    closed = QRect(bounds.left(), closed_y,
                   width, height)
    pack_width = min(pack_size[0], bounds.width())
    pack_height = min(pack_size[1], bounds.height())
    pack_y = max(bounds.top(), min(closed_y, bounds.bottom() + 1 - pack_height))
    pack = QRect(bounds.left(), pack_y,
                 pack_width, pack_height)
    return closed, pack


class FloatingLauncherController(QObject):
    stateChanged = Signal()
    settingsRequested = Signal()
    toolSortModeChanged = Signal()
    drawerGeometryChanged = Signal()
    cardsChanged = Signal()
    dockScreenChanged = Signal()
    recallAllCardsRequested = Signal()

    def __init__(
        self, app: QApplication, app_controller: AppController, settings: SettingsController,
    ) -> None:
        super().__init__(app)
        self._app = app
        self._backend = app_controller
        self._settings = settings
        self._model = ToolListModel()
        self._search_results = ToolListModel()
        self._search_query = ""
        self._main_window: QWindow | None = None
        self._notch: QWindow | None = None
        self._panel: QWindow | None = None
        self._dock_mode = False
        self._dock_screen_geometry: tuple[str, QRect] | None = None
        self._drawer_mode = False
        self._drawer_progress = 0.0
        self._drawer_animating = False
        self._drawer_tip_offset = 0
        self._screen: QScreen | None = None
        self._screen_name, self._ratio = settings.config_store.floating_launcher_position()
        self._dock_screen_name = settings.config_store.floating_dock_screen()
        self._notch_size = (44, 108)
        self._panel_size = (360, 480)
        self._visible = False
        self._expanded = False
        self._pinned = False
        self._dragging = False
        self._drag_pointer_offset = 0
        self._menu_open = False
        self._quitting = False
        self._card_origin: tuple[str, QRectF] | None = None
        self._activation_serial = 0
        self._activation_owner: tuple[int, int] | None = None
        self._requesting_tool: str | None = None
        self._browsing_cards = False
        self._open_cards: set[str] = set()
        self._returning_cards: set[str] = set()
        self._reconcile_timer = QTimer(self)
        self._reconcile_timer.setSingleShot(True)
        self._reconcile_timer.timeout.connect(self.reconcile)
        # Startup activation can remain cached in Qt without any FocusOut or
        # applicationStateChanged signal. Recheck native ownership at low cost;
        # ordinary Qt focus events still reconcile immediately.
        self._foreground_timer = QTimer(self)
        self._foreground_timer.setInterval(250)
        self._foreground_timer.timeout.connect(self.reconcile)
        app.installEventFilter(self)
        app.applicationStateChanged.connect(self._schedule_reconcile)
        app.focusWindowChanged.connect(self._schedule_reconcile)
        app.screenAdded.connect(self._screen_added)
        app.screenRemoved.connect(self._screen_removed)
        app.aboutToQuit.connect(self.shutdown)
        for screen in app.screens():
            self._screen_added(screen)
        settings.floatingLauncherEnabledChanged.connect(self.reconcile)
        settings.themeChanged.connect(self._update_card_filter)
        self._tools_refresh_timer = QTimer(self)
        self._tools_refresh_timer.setSingleShot(True)
        self._tools_refresh_timer.timeout.connect(self.refreshTools)
        self._model.countChanged.connect(self.reposition)
        app_controller.customToolsChanged.connect(self._schedule_tools_refresh)
        app_controller.toolSortModeChanged.connect(self.toolSortModeChanged)
        coordinator = app_controller.execution_coordinator
        coordinator.runningChanged.connect(self._schedule_tools_refresh)
        self.refreshTools()

    @Property(QObject, constant=True)
    def toolsModel(self) -> ToolListModel:
        return self._model

    @Property(QObject, constant=True)
    def searchResultsModel(self) -> ToolListModel:
        return self._search_results

    @Property("QStringList", notify=cardsChanged)
    def returningCardIds(self) -> list[str]:
        return sorted(self._returning_cards)

    @Property("QStringList", notify=cardsChanged)
    def openCardIds(self) -> list[str]:
        return sorted(self._open_cards)

    @Property(int, notify=cardsChanged)
    def openCardCount(self) -> int:
        return len(self._open_cards)

    @Slot()
    def _update_card_filter(self) -> None:
        self._model.set_excluded_ids(set())
        self._search_results.set_excluded_ids(set())
        self._model.set_filter("" if self._settings.themeMode == "decade" else self._search_query)

    @Slot(str, result=bool)
    def isCardOpen(self, tool_id: str) -> bool:
        return tool_id in self._open_cards

    @Slot(str, bool)
    def setCardOpen(self, tool_id: str, opened: bool) -> None:
        if opened:
            self._open_cards.add(tool_id)
        else:
            self._open_cards.discard(tool_id)
            self._returning_cards.discard(tool_id)
        self._update_card_filter()
        self.cardsChanged.emit()

    @Slot(str, result=bool)
    def beginCardReturn(self, tool_id: str) -> bool:
        if (self._settings.themeMode not in ("decade", "zio") or not self._visible
                or tool_id not in self._open_cards):
            return False
        self._returning_cards.add(tool_id)
        self.cardsChanged.emit()
        return True

    @Property(bool, notify=stateChanged)
    def visible(self) -> bool:
        return self._visible

    @Property(bool, notify=stateChanged)
    def expanded(self) -> bool:
        return self._expanded

    @Property(bool, notify=stateChanged)
    def pinned(self) -> bool:
        return self._pinned

    @Slot()
    def togglePinned(self) -> None:
        self._pinned = not self._pinned
        self.stateChanged.emit()
        self.reconcile()

    @Slot()
    def recallAllCards(self) -> None:
        self.recallAllCardsRequested.emit()

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
        self._search_query = query
        self._search_results.set_filter(query)
        self._model.set_filter("" if self._settings.themeMode == "decade" else query)

    @Slot()
    def _schedule_tools_refresh(self, *_args: object) -> None:
        if not self._quitting and not self._tools_refresh_timer.isActive():
            self._tools_refresh_timer.start(0)

    @Slot()
    def refreshTools(self) -> None:
        self._tools_refresh_timer.stop()
        tools = self._backend.sorted_custom_tools(
            self._backend.registry.for_section(ToolSection.CUSTOM)
        )
        running = {tool.id for tool in tools
                   if self._backend.execution_coordinator.running(tool.id)}
        if self._settings.themeMode != "zio":
            tools.sort(key=lambda tool: tool.id not in running)
        self._model.set_tools(tools, running_ids=running)
        self._search_results.set_tools(tools, running_ids=running)

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
        self._dock_mode = False
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
        if self._dock_mode:
            self._drawer_animating = False
        self._dock_mode = False
        self._screen = None
        self._drawer_mode = True
        self._notch = self._panel = cast(QWindow, window)
        self._notch_size = (tip_width, tip_height)
        self._panel_size = (panel_width, panel_height)
        self.reposition()

    @Slot(QObject, int, int)
    def attachDockWindow(self, window: QObject, width: int, height: int) -> None:
        self._dock_mode = True
        self._drawer_animating = False
        self._drawer_mode = False
        self._notch = self._panel = cast(QWindow, window)
        self._panel_size = (width, height)
        self._screen = next((screen for screen in self._app.screens()
                             if screen.name() == (self._dock_screen_name or self._screen_name)),
                            self._screen)
        self.reposition()

    @Slot(result=QRectF)
    def dockLaunchOrigin(self) -> QRectF:
        if self._panel is None or not self._dock_mode:
            return QRectF()
        geometry = self._panel.geometry()
        return QRectF(geometry.center().x() - 36, geometry.top() + 20, 72, 104)

    @Slot(result=QRectF)
    def collapsedCardOrigin(self) -> QRectF:
        if self._panel is None or self._screen is None:
            return QRectF()
        if self._dock_mode:
            geometry = self._panel.geometry()
            return QRectF(geometry.center().x() - 24, geometry.bottom() + 1 - 48, 48, 48)
        geometry_fn = (decade_pack_geometry if self._settings.themeMode == "decade"
                       else edge_geometry)
        closed, _ = geometry_fn(self._screen.availableGeometry(), self._notch_size,
                                self._panel_size, self._ratio)
        return QRectF(closed)

    @Slot(float)
    def setDrawerProgress(self, progress: float) -> None:
        self._drawer_progress = max(0.0, min(1.0, progress))
        if (self._drawer_mode or self._dock_mode) and not self._drawer_animating:
            self.reposition()

    @Slot(bool)
    def setDrawerAnimating(self, animating: bool) -> None:
        if self._drawer_animating == animating:
            return
        self._drawer_animating = animating
        if self._drawer_mode or self._dock_mode:
            self.reposition()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QWindow) and event.type() in {
            QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WindowStateChange,
            QEvent.Type.FocusIn, QEvent.Type.FocusOut, QEvent.Type.ZOrderChange,
        }:
            self._schedule_reconcile()
        return False

    def _schedule_reconcile(self, *_args: object) -> None:
        if not self._quitting:
            self._reconcile_timer.start(0)

    def _is_launcher_window(self, window: QWindow) -> bool:
        current: QWindow | None = window
        while current is not None:
            if current in (self._notch, self._panel):
                return True
            current = current.transientParent()
        return False

    def _ordinary_window_active(self) -> bool:
        native = foreground_window() if self._app.platformName() == "windows" else None
        if native is not None:
            if native.process_id != os.getpid():
                return True
            windows = {int(window.winId()): window for window in self._app.topLevelWindows()
                       if window.isVisible()}
            # Only the launcher and its owned popups belong to its focus group.
            window = windows.get(native.handle)
            if window is None:
                window = windows.get(native.root_owner)
            # Unwrapped native dialogs of this process count as ordinary windows.
            return window is None or not self._is_launcher_window(window)
        if self._app.applicationState() != Qt.ApplicationState.ApplicationActive:
            return True
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
        self._sync_activation_focus()
        if not self._quitting:
            sync_launcher_card_layers([window for window in (self._notch, self._panel)
                                       if window is not None])
        enabled = (
            not self._quitting and self._main_window is not None
            and bool(self._settings.floatingLauncherEnabled)
        )
        if enabled and self._app.platformName() == "windows":
            self._foreground_timer.setInterval(50 if self._expanded and not self._pinned else 250)
            if not self._foreground_timer.isActive():
                self._foreground_timer.start()
        else:
            self._foreground_timer.stop()
        if self._browsing_cards and not self._pointer_inside():
            self._browsing_cards = False
        browsing = (self._browsing_cards and self._card_window_active())
        if (enabled and not self._pinned and not self._dragging
                and self._expanded and self._ordinary_window_active() and not browsing):
            self.collapse()
        main_visible = (self._main_window is not None and self._main_window.isVisible()
                        and self._main_window.visibility() != QWindow.Visibility.Minimized)
        visible = enabled and not main_visible
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
            self.reposition()
            if self._panel is not None:
                self._panel.requestActivate()
            self._expanded = True
            self.stateChanged.emit()

    @Slot()
    def collapse(self) -> None:
        self._browsing_cards = False
        self._menu_open = False
        if self._expanded:
            self._expanded = False
            self.stateChanged.emit()

    @Slot(bool)
    def setMenuOpen(self, opened: bool) -> None:
        self._menu_open = opened
        self._schedule_reconcile()

    def _pointer_inside(self) -> bool:
        point = QCursor.pos()
        hit = window_under_cursor()
        if (hit is not None and not any(window is not None and int(window.winId()) == hit
                                        for window in (self._notch, self._panel))):
            # A flight can briefly cover the source under the stationary cursor.
            # It belongs to this browsing gesture, not an outside pointer move.
            flight = self._browsing_cards and any(
                window.objectName() == "recentToolWindow" and int(window.winId()) == hit
                and window.property("nativeFlightActive")
                for window in self._app.topLevelWindows()
            )
            if not flight:
                return False
        if (self._drawer_mode or self._dock_mode) and self._panel is not None:
            return (self._panel.isVisible()
                    and self._panel.mask().contains(point - self._panel.position()))
        return any(window is not None and window.isVisible() and window.geometry().contains(point)
                   for window in (self._notch, self._panel))

    @Slot()
    def pointerChanged(self) -> None:
        # A drawn card may own focus while the user keeps browsing the launcher.
        # Moving away ends that browsing session; focus still governs dismissal.
        self._schedule_reconcile()

    def _card_window_active(self) -> bool:
        owner = self._foreground_identity()
        return owner is not None and owner[0] == os.getpid() and any(
            window.objectName() == "recentToolWindow" and int(window.winId()) == owner[1]
            and window.isVisible() for window in self._app.topLevelWindows()
        )

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
        if self._dragging and self._dock_mode:
            screen = self._app.screenAt(QCursor.pos())
            if screen is not None and screen is not self._screen:
                self._screen = screen
                self.reposition()
            return
        if self._dragging and self._notch is not None:
            # Window moves can generate MouseArea events whose local positions
            # still refer to the old geometry. Read an independent screen position.
            self.dragTo(QCursor.pos().y() - self._drag_pointer_offset)

    @Slot(int)
    def dragTo(self, global_y: int) -> None:
        if not self._dragging or self._screen is None:
            return
        available = self._screen.availableGeometry()
        if self._drawer_mode and self._settings.themeMode == "decade":
            top, _ = decade_pack_geometry(available, self._notch_size, self._panel_size, 0)
            bottom, _ = decade_pack_geometry(available, self._notch_size, self._panel_size, 1)
            travel = max(1, bottom.y() - top.y())
            ratio = max(0.0, min(1.0, (global_y - top.y()) / travel))
        else:
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
        if self._dock_mode:
            self._dock_screen_name = self._screen.name() if self._screen else ""
            try:
                self._settings.config_store.set_floating_dock_screen(self._dock_screen_name)
            except OSError:
                logger.exception("无法保存腰带 Dock 所在屏幕")
            self.stateChanged.emit()
            return
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

    @Slot(str, QRectF)
    def launchToolFrom(self, tool_id: str, source: QRectF) -> None:
        self._card_origin = (tool_id, QRectF(source))
        try:
            self.launchTool(tool_id)
        finally:
            self._card_origin = None

    @Slot(str, result=QRectF)
    def cardLaunchOrigin(self, tool_id: str) -> QRectF:
        if self._card_origin and self._card_origin[0] == tool_id:
            return QRectF(self._card_origin[1])
        return QRectF()

    @Slot(str)
    def launchTool(self, tool_id: str) -> None:
        tool = self._backend.registry.get(tool_id)
        if tool is None or tool.section != ToolSection.CUSTOM:
            return
        # All floating presentations open the same independent execution window.
        if self._expanded and self._pointer_inside():
            self._browsing_cards = True
        self._sync_activation_focus()
        self._requesting_tool = tool_id
        try:
            self._backend.recentToolDialogRequested.emit(tool_id)
        finally:
            self._requesting_tool = None

    def _foreground_identity(self) -> tuple[int, int] | None:
        native = foreground_window() if self._app.platformName() == "windows" else None
        if native is not None:
            return native.process_id, native.handle
        focus = self._app.focusWindow()
        return (os.getpid(), int(focus.winId())) if focus is not None else None

    def _sync_activation_focus(self) -> None:
        owner = self._foreground_identity()
        if owner == self._activation_owner:
            return
        # Cards created by the same burst may receive focus while the next shell
        # is incubating. That is our own handoff, not a later user activation.
        handoff = next((window for window in self._app.topLevelWindows()
                        if owner is not None and owner[0] == os.getpid()
                        and window.objectName() == "recentToolWindow"
                        and int(window.winId()) == owner[1]
                        and window.property("floatingActivationToken") == self._activation_serial
                        and window.property("floatingFocusHandoff")), None)
        if handoff is not None:
            handoff.setProperty("floatingFocusHandoff", False)
        else:
            self._activation_serial += 1
        self._activation_owner = owner

    @Slot(str, result=int)
    def cardLaunchToken(self, tool_id: str) -> int:
        return self._activation_serial if self._requesting_tool == tool_id else -1

    @Slot(int, result=bool)
    def canActivateCard(self, token: int) -> bool:
        # Discard an asynchronous floating request after the user changes focus.
        # Requests from the main window retain their existing activation behavior.
        self._sync_activation_focus()
        return token < 0 or token == self._activation_serial

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
            screen_name = (self._dock_screen_name or self._screen_name
                           if self._dock_mode else self._screen_name)
            self._screen = next((s for s in screens if s.name() == screen_name), None)
            if self._screen is None:
                self._screen = self._app.primaryScreen()
        if self._screen is None or self._notch is None or self._panel is None:
            return
        if self._dock_mode:
            screen_geometry = (self._screen.name(), self._screen.availableGeometry())
            screen_changed = screen_geometry != self._dock_screen_geometry
            self._dock_screen_geometry = screen_geometry
            geometry = dock_geometry(screen_geometry[1], self._panel_size)
            changed = self._panel.geometry() != geometry
            if changed:
                self._panel.setGeometry(geometry)
            # The transparent space above the collapsed buckle must pass input through.
            diameter = min(48, geometry.width(), geometry.height())
            mask = QRegion(QRect((geometry.width() - diameter) // 2,
                                 geometry.height() - diameter, diameter, diameter), QRegion.Ellipse)
            if self._drawer_progress > 0 or self._drawer_animating:
                card_width = min(max(88, (geometry.width() - 68) // 84 * 84 + 4),
                                 max(88, self._model.count * 84 + 4))
                mask |= QRegion(QRect((geometry.width() - card_width) // 2, 0, card_width, 126))
                mask |= QRegion(QRect(0, 132, geometry.width(), 40))
            if self._panel.mask() != mask:
                self._panel.setMask(mask)
            if screen_changed:
                self.dockScreenChanged.emit()
            return
        geometry_fn = (decade_pack_geometry if self._drawer_mode
                       and self._settings.themeMode == "decade" else edge_geometry)
        notch, panel = geometry_fn(
            self._screen.availableGeometry(), self._notch_size, self._panel_size, self._ratio,
        )
        if self._drawer_mode:
            if self._settings.themeMode == "decade":
                geometry = panel.united(notch)
                if self._panel.geometry() != geometry:
                    self._panel.setGeometry(geometry)
                mask = QRegion(notch.translated(-geometry.topLeft()))
                if self._drawer_progress > 0 or self._drawer_animating:
                    mask |= QRegion(panel.translated(-geometry.topLeft()))
                if self._panel.mask() != mask:
                    self._panel.setMask(mask)
                tip_offset = notch.y() - geometry.y()
                if tip_offset != self._drawer_tip_offset:
                    self._drawer_tip_offset = tip_offset
                    self.drawerGeometryChanged.emit()
                return
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
        self._foreground_timer.stop()
        self._tools_refresh_timer.stop()
        self._app.removeEventFilter(self)
        self.stateChanged.emit()
        for window in (self._notch, self._panel):
            if window is not None:
                window.hide()
