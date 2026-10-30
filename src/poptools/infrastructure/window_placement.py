"""Place independent tool windows without hiding earlier windows at the same origin."""

import ctypes
import sys
from collections.abc import Sequence
from ctypes import wintypes
from math import floor

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QRegion, QWindow


def sync_launcher_card_layers(launchers: Sequence[QWindow] | None = None) -> None:
    """Maintain only the launcher's native topmost layer, without reordering cards."""
    if launchers is None:
        launchers = [window for window in QGuiApplication.topLevelWindows()
                     if window.objectName() in {"floatingScriptPanelWindow", "zioDockWindow"}]
    for launcher in dict.fromkeys(launchers):
        if launcher.isVisible():
            _set_native_topmost(launcher, True)


def _set_native_topmost(window: QWindow, topmost: bool, *, raise_window: bool = False) -> None:
    if sys.platform != "win32":
        if bool(window.flags() & Qt.WindowStaysOnTopHint) != topmost:
            window.setFlag(Qt.WindowStaysOnTopHint, topmost)
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    style = user32.GetWindowLongW
    style.argtypes = [wintypes.HWND, ctypes.c_int]
    style.restype = wintypes.LONG
    if bool(style(int(window.winId()), -20) & 0x8) == topmost and not raise_window:
        return
    position = user32.SetWindowPos
    position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, wintypes.UINT]
    position.restype = wintypes.BOOL
    # Do not activate, move, resize or change owner ordering.
    position(int(window.winId()), -1 if topmost else -2, 0, 0, 0, 0, 0x0213)


def zio_card_geometry(available: QRect, size: QSize, source: QRectF, dock: QRectF) -> QRect:
    """Align a card above its Dock slot, keeping the whole card in the work area."""
    margin = min(16, max(0, (min(available.width(), available.height()) - 1) // 2))
    bounds = available.adjusted(margin, margin, -margin, -margin)
    dock_top = dock.top() if not dock.isEmpty() else source.top() - 20
    bottom = min(bounds.bottom() + 1, floor(dock_top) - 16)
    width = min(size.width(), max(1, bounds.width()))
    height = min(size.height(), max(1, bottom - bounds.top()))
    x = max(bounds.left(), min(bounds.right() + 1 - width,
                               round(source.center().x() - width / 2)))
    y = max(bounds.top(), bottom - height)
    return QRect(x, y, width, height)


def set_card_flight_layer(window: QWindow, flying: bool) -> None:
    """Draw above the pack only while flying, then restore the explicit pin."""
    if sys.platform != "win32":
        if flying:
            window.raise_()
        return
    _set_native_topmost(window, flying or bool(window.flags() & Qt.WindowStaysOnTopHint),
                        raise_window=flying)


def card_pack_mask(surface: QRect, pack: QRectF, opening: QRectF) -> QRegion:
    """Occlude only the part of a full card still behind the stationary pack.

    An empty result means no native mask. The following cards cover the body
    below the exposed head, but nothing above or left of that stationary corner.
    """
    if pack.isEmpty() or opening.isEmpty():
        return QRegion()
    offset = surface.topLeft()
    local_surface = QRect(QPoint(), surface.size())
    # At handoff cover shadow margins as well, preserving the exact exposed head.
    packed_position = QPoint(round(pack.center().x() - surface.width() / 2),
                             round(pack.center().y() - surface.height() / 2))
    if offset == packed_position:
        visible = QRegion(opening.toAlignedRect().translated(-offset).intersected(local_surface))
        return visible if not visible.isEmpty() else QRegion(-1, -1, 1, 1)
    # A sleeve corner, not an infinite vertical strip: a card pulled upwards
    # must emerge above the lip as well as to its left. Extend below the surface
    # so a card still inside the pack cannot leak beneath its short viewport.
    cover = QRectF(pack.x(), opening.bottom(), pack.width(),
                   max(0.0, surface.y() + surface.height() - opening.bottom())).toAlignedRect()
    if not cover.intersects(surface):
        return QRegion()
    visible = QRegion(local_surface).subtracted(QRegion(cover.translated(-offset)))
    # QWindow interprets an empty region as "remove mask", not "hide all".
    return visible if not visible.isEmpty() else QRegion(-1, -1, 1, 1)


def staggered_position(
    available: QRect, size: QSize, occupied: Sequence[QRect], *, centered: bool = False,
) -> QPoint:
    left, top = available.left(), available.top()
    right = max(left, available.right() + 1 - size.width())
    bottom = max(top, available.bottom() + 1 - size.height())
    nearby = [rect for rect in occupied if rect.intersects(available)]
    step = 32
    start_x = (left + right) // 2 if centered else left
    start_y = (top + bottom) // 2 if centered else top
    candidates = [QPoint(start_x, start_y)]
    # Centered cards cascade toward the right, away from Decade's left-hand pack.
    for index in range(1, max(right - left, bottom - top) // step + 2):
        offset = index * step
        candidates.append(QPoint(min(right, start_x + offset), min(bottom, start_y + offset)))
    if centered:
        # Fill the center/right side before falling back to the rest of a small screen.
        for y in [*range(top, bottom + 1, step), bottom]:
            for x in [*range(start_x, right + 1, step), right]:
                candidates.append(QPoint(x, y))
    # Manually moved windows may occupy the diagonal; use the rest of the desktop too.
    for y in [*range(top, bottom + 1, step), bottom]:
        for x in [*range(left, right + 1, step), right]:
            candidates.append(QPoint(x, y))

    def clearance(point: QPoint) -> int:
        return min((max(abs(point.x() - rect.x()), abs(point.y() - rect.y()))
                    for rect in nearby), default=step)

    for point in candidates:
        if clearance(point) >= step:
            return point
    # On a small screen choose the most distinct reachable origin rather than
    # moving outside the work area or stacking every window at the same origin.
    return max(candidates, key=clearance)


def card_flight_geometry(
    source: QRectF, target: QRect, available: QRect, preserve_source: bool = False,
) -> dict[str, int | float]:
    """Flight coordinates and safe path bounds on the originating screen."""
    if not preserve_source:
        source = source.intersected(QRectF(available))
    if source.isEmpty():
        return {}
    bounds = source.toAlignedRect().united(target).adjusted(-64, -64, 64, 64)
    if not preserve_source:
        bounds = bounds.intersected(available)
    return {"x": bounds.x(), "y": bounds.y(), "width": bounds.width(), "height": bounds.height(),
            "sourceX": source.x() - bounds.x(), "sourceY": source.y() - bounds.y(),
            "sourceWidth": source.width(), "sourceHeight": source.height(),
            "targetX": target.x() - bounds.x(), "targetY": target.y() - bounds.y(),
            "targetWidth": target.width(), "targetHeight": target.height(),
            "preserveSource": preserve_source,
            "screenLeft": available.x(), "screenTop": available.y(),
            "screenRight": available.x() + available.width(),
            "screenBottom": available.y() + available.height()}


def place_tool_window(
    window: QWindow, origin: QPoint | None = None, *, centered: bool = False,
) -> None:
    point = origin if origin is not None else QCursor.pos()
    screen = QGuiApplication.screenAt(point) or window.screen()
    if screen is None:
        return
    window.setScreen(screen)
    available = screen.availableGeometry()
    margin = min(32, max(0, (min(available.width(), available.height()) - 1) // 2))
    bounds = available.adjusted(margin, margin, -margin, -margin)
    window.resize(min(window.width(), bounds.width()), min(window.height(), bounds.height()))
    occupied = []
    for other in QGuiApplication.topLevelWindows():
        if (other is window or other.objectName() != "recentToolWindow"
                or not other.isVisible() or other.visibility() == QWindow.Visibility.Minimized):
            continue
        # A card in flight already owns its landing position. Rapidly opening
        # another card must not select that same position while it is moving.
        destination = other.property("cardPlacementRect")
        occupied.append(destination.toAlignedRect() if isinstance(destination, QRectF)
                        else other.geometry())
    window.setPosition(staggered_position(bounds, window.size(), occupied, centered=centered))
