import pytest
from PySide6.QtCore import QRect, QRectF, QSize

from poptools.infrastructure.window_placement import card_flight_geometry, staggered_position


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


def test_first_window_is_top_left_and_following_windows_cascade_down_and_right():
    available = QRect(32, 32, 1536, 936)
    size = QSize(440, 680)
    first = staggered_position(available, size, [])
    second = staggered_position(available, size, [QRect(first, size)])
    third = staggered_position(available, size, [QRect(first, size), QRect(second, size)])
    assert first == available.topLeft()
    assert second.x() - first.x() == 32
    assert second.y() - first.y() == 32
    assert third.x() - second.x() == 32
    assert third.y() - second.y() == 32


def test_windows_on_another_monitor_do_not_shift_the_first_window():
    available = QRect(-1280, 0, 1280, 720)
    size = QSize(440, 680)
    assert staggered_position(available, size, [QRect(100, 100, 440, 680)]) == (
        staggered_position(available, size, [])
    )


def test_shared_card_origin_is_not_cropped_or_resized_at_screen_edge():
    source = QRectF(1100, 550, 300, 464)
    target = QRect(32, 32, 440, 680)
    geometry = card_flight_geometry(source, target, QRect(0, 0, 1536, 864), True)
    assert geometry["sourceWidth"] == source.width()
    assert geometry["sourceHeight"] == source.height()
    assert geometry["sourceX"] + geometry["x"] == source.x()
    assert geometry["sourceY"] + geometry["y"] == source.y()


@pytest.mark.parametrize("available", [QRect(0, 0, 1920, 1040),
                                      QRect(-1920, -200, 1920, 1040),
                                      QRect(30, 40, 300, 250)])
def test_flight_surface_contains_source_and_landing_in_logical_coordinates(available):
    source = QRectF(available.right() - 170, available.center().y(), 160, 40)
    size = QSize(min(440, available.width() - 24), min(680, available.height() - 24))
    target = QRect(staggered_position(available, size, []), size)
    geometry = card_flight_geometry(source, target, available)
    overlay = QRect(geometry["x"], geometry["y"], geometry["width"], geometry["height"])
    assert available.contains(overlay)
    assert QRectF(overlay).contains(source)
    assert overlay.contains(target)
    assert geometry["sourceX"] + overlay.x() == source.x()
    assert geometry["targetX"] + overlay.x() == target.x()
    assert geometry["sourceY"] + overlay.y() == source.y()
    assert geometry["targetY"] + overlay.y() == target.y()
    assert card_flight_geometry(QRectF(), target, available) == {}
