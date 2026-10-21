"""Place independent tool windows without hiding earlier windows at the same origin."""

from collections.abc import Sequence

from PySide6.QtCore import QPoint, QRect, QSize
from PySide6.QtGui import QCursor, QGuiApplication, QWindow


def staggered_position(available: QRect, size: QSize, occupied: Sequence[QRect]) -> QPoint:
    left, top = available.left(), available.top()
    right = max(left, available.right() + 1 - size.width())
    bottom = max(top, available.bottom() + 1 - size.height())
    center = QPoint((left + right) // 2, (top + bottom) // 2)
    nearby = [rect for rect in occupied if rect.intersects(available)]
    step = 32
    candidates = [center]
    # Prefer a familiar down/right cascade, then wrap back up/left at the edge.
    for direction in (1, -1):
        for index in range(1, max(right - left, bottom - top) // step + 2):
            offset = direction * index * step
            candidates.append(QPoint(max(left, min(right, center.x() + offset)),
                                     max(top, min(bottom, center.y() + offset))))
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
    # moving outside the work area or stacking every window at its center.
    return max(candidates, key=clearance)


def place_tool_window(window: QWindow) -> None:
    screen = QGuiApplication.screenAt(QCursor.pos()) or window.screen()
    if screen is None:
        return
    window.setScreen(screen)
    available = screen.availableGeometry()
    margin = min(12, max(0, (min(available.width(), available.height()) - 1) // 2))
    bounds = available.adjusted(margin, margin, -margin, -margin)
    window.resize(min(window.width(), bounds.width()), min(window.height(), bounds.height()))
    occupied = [other.geometry() for other in QGuiApplication.topLevelWindows()
                if other is not window and other.objectName() == "recentToolWindow"
                and other.isVisible() and other.visibility() != QWindow.Visibility.Minimized]
    window.setPosition(staggered_position(bounds, window.size(), occupied))
