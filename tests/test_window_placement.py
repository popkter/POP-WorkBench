import pytest
from PySide6.QtCore import QRect, QSize

from poptools.infrastructure.window_placement import staggered_position


@pytest.mark.parametrize("available,size", [
    (QRect(12, 12, 1896, 1016), QSize(440, 680)),
    (QRect(-1268, -88, 1256, 696), QSize(440, 680)),
    (QRect(20, 30, 300, 250), QSize(276, 226)),
])
def test_successive_windows_stay_inside_work_area_and_have_distinct_origins(available, size):
    occupied = []
    for _ in range(3):
        point = staggered_position(available, size, occupied)
        rect = QRect(point, size)
        assert available.contains(rect)
        assert all(point != other.topLeft() for other in occupied)
        occupied.append(rect)


def test_first_window_is_centered_and_second_is_offset_down_and_right():
    available = QRect(0, 0, 1600, 1000)
    size = QSize(440, 680)
    first = staggered_position(available, size, [])
    second = staggered_position(available, size, [QRect(first, size)])
    assert first.x() == 580 and first.y() == 160
    assert second.x() - first.x() == 32
    assert second.y() - first.y() == 32


def test_windows_on_another_monitor_do_not_shift_the_first_window():
    available = QRect(-1280, 0, 1280, 720)
    size = QSize(440, 680)
    assert staggered_position(available, size, [QRect(100, 100, 440, 680)]) == (
        staggered_position(available, size, [])
    )
