import pytest
from PySide6.QtCore import QPoint, QRect, QRectF, QSize

from poptools.infrastructure.window_placement import (
    card_flight_geometry,
    card_pack_mask,
    staggered_position,
    zio_card_geometry,
)


@pytest.mark.parametrize("available", [QRect(0, 0, 1920, 1040),
                                       QRect(-1920, -300, 1920, 1040), QRect(20, 10, 600, 500)])
@pytest.mark.parametrize("slot", [0.05, 0.5, 0.95])
def test_zio_cards_align_with_slot_and_stay_above_dock(available, slot):
    dock = QRectF(available.x() + 16, available.bottom() - 223, available.width() - 32, 208)
    source = QRectF(available.x() + available.width() * slot - 36, dock.y() + 58, 72, 104)
    card = zio_card_geometry(available, QSize(314, 486), source, dock)
    assert available.contains(card)
    assert card.bottom() < dock.top() - 15
    expected_x = round(source.center().x() - card.width() / 2)
    assert card.x() == max(available.x() + 16,
                           min(available.right() - 15 - card.width(), expected_x))


@pytest.mark.parametrize("offset", [QPoint(0, 0), QPoint(-1920, -400)])
def test_pack_occlusion_never_cuts_the_body_outside_the_pack(offset):
    pack = QRectF(1000, 200, 300, 464).translated(offset)
    opening = QRectF(1000, 200, 300, 60).translated(offset)
    # A card halfway out/in has a full-height exposed side, not a flying header.
    surface = QRect(800, 150, 440, 680).translated(offset)
    mask = card_pack_mask(surface, pack, opening)
    assert mask.contains(QPoint(50, 400))  # Card body left of the pack.
    assert not mask.contains(QPoint(300, 400))  # Body actually inside the pack.
    assert mask.contains(QPoint(300, 70))  # Exposed head in the pack.
    assert mask.contains(QPoint(300, 20))  # Above the lip, including above the old head.
    # Once clear of the pack, no native clipping at all, in either direction.
    assert card_pack_mask(QRect(200, 150, 440, 680).translated(offset), pack, opening).isEmpty()
    # Final handoff exactly preserves the exposed head and excludes shadow margins.
    packed = QRect(930, 92, 440, 680).translated(offset)
    assert card_pack_mask(packed, pack, opening).boundingRect() == QRect(70, 108, 300, 60)


def test_card_clears_the_upper_lip_without_clearing_the_left_edge():
    pack = QRectF(1000, 800, 300, 464)
    opening = QRectF(1000, 800, 300, 60)
    # A fully extracted card above the sleeve is complete, even while its right
    # half overlaps the pack horizontally. The old vertical strip clipped it.
    assert card_pack_mask(QRect(800, 100, 440, 680), pack, opening).isEmpty()


def test_card_body_is_visible_to_the_right_when_returning_into_a_left_hand_pack():
    pack = QRectF(1000, 200, 300, 464)
    opening = QRectF(1000, 200, 300, 60)
    mask = card_pack_mask(QRect(1160, 150, 440, 680), pack, opening)
    assert mask.contains(QPoint(300, 400))  # Body remains visible outside the right edge.
    assert not mask.contains(QPoint(50, 400))  # Body already inside the pack is covered.
    assert mask.contains(QPoint(50, 70))  # The exposed card header remains visible.
    assert card_pack_mask(QRect(1400, 150, 440, 680), pack, opening).isEmpty()


def test_cards_without_pack_origin_have_no_native_mask():
    assert card_pack_mask(QRect(0, 0, 440, 680), QRectF(), QRectF()).isEmpty()


def test_fully_occluded_surface_does_not_remove_its_native_mask():
    surface = QRect(100, 400, 200, 300)
    mask = card_pack_mask(surface, QRectF(0, 0, 500, 900), QRectF(0, 0, 500, 60))
    assert not mask.isEmpty()
    assert not mask.intersects(QRect(QPoint(), surface.size()))


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


@pytest.mark.parametrize("available", [QRect(32, 32, 1856, 976),
                                       QRect(-1888, -168, 1856, 976)])
def test_decade_first_card_centers_and_following_cards_cascade_right(available):
    size = QSize(314, 486)
    occupied = []
    center = QPoint(available.x() + (available.width() - size.width()) // 2,
                    available.y() + (available.height() - size.height()) // 2)
    for index in range(6):
        point = staggered_position(available, size, occupied, centered=True)
        assert point == center + QPoint(32 * index, 32 * index)
        card = QRect(point, size)
        assert available.contains(card)
        occupied.append(card)


@pytest.mark.parametrize("available,size", [
    (QRect(32, 32, 1856, 976), QSize(314, 486)),
    (QRect(-1268, -88, 1256, 696), QSize(314, 486)),
    (QRect(20, 30, 300, 250), QSize(220, 180)),
])
def test_centered_cascade_wraps_inside_work_area_and_keeps_distinct_positions(available, size):
    occupied = []
    for _ in range(12):
        point = staggered_position(available, size, occupied, centered=True)
        card = QRect(point, size)
        assert available.contains(card)
        assert all(point != other.topLeft() for other in occupied)
        occupied.append(card)


def test_cards_on_other_screens_do_not_displace_the_center():
    available = QRect(-1920, -200, 1920, 1040)
    size = QSize(314, 486)
    point = staggered_position(available, size, [QRect(500, 300, 314, 486)], centered=True)
    assert point == staggered_position(available, size, [], centered=True)


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
