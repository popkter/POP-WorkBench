"""Place independent tool windows without hiding earlier windows at the same origin."""

import ctypes
import sys
from collections.abc import Sequence
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QCursor, QGuiApplication, QRegion, QWindow


def set_card_flight_layer(window: QWindow, flying: bool) -> None:
    """Keep a flying card above the topmost pack without replacing its HWND."""
    if sys.platform != "win32":
        if flying:
            window.raise_()
        return
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    position = user32.SetWindowPos
    position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, wintypes.UINT]
    position.restype = wintypes.BOOL
    topmost = flying or bool(window.flags() & Qt.WindowStaysOnTopHint)
    # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE: do not steal the pack's focus,
    # resize the native surface, or recreate it via a Qt window-flags change.
    position(int(window.winId()), -1 if topmost else -2, 0, 0, 0, 0, 0x0013)


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


def staggered_position(available: QRect, size: QSize, occupied: Sequence[QRect]) -> QPoint:
    left, top = available.left(), available.top()
    right = max(left, available.right() + 1 - size.width())
    bottom = max(top, available.bottom() + 1 - size.height())
    nearby = [rect for rect in occupied if rect.intersects(available)]
    step = 32
    candidates = [QPoint(left, top)]
    # Start at the padded top-left, then cascade down/right within the work area.
    for index in range(1, max(right - left, bottom - top) // step + 2):
        offset = index * step
        candidates.append(QPoint(min(right, left + offset), min(bottom, top + offset)))
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


def place_tool_window(window: QWindow, origin: QPoint | None = None) -> None:
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
    window.setPosition(staggered_position(bounds, window.size(), occupied))
