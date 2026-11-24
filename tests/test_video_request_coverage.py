"""Scrub previews use actual frame intervals for low-rate and VFR media."""
import pytest
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Picture
from poptools.infrastructure.video_scrub import ScrubRequest


def long_picture():
    return Picture(0.0, 0.4, QImage(8, 8, QImage.Format.Format_RGB888))


def test_release_accepts_exact_long_frame_far_from_its_start():
    picture = long_picture()
    request = ScrubRequest(0.3)

    assert request.publish(picture)
    assert request.take_progress() is picture
    assert request.take_progress() is None


def test_pending_long_frame_remains_valid_when_target_moves_within_it():
    picture = long_picture()
    request = ScrubRequest(0.2)

    assert request.publish(picture)
    request.update(0.39)
    assert request.take_progress() is picture


@pytest.mark.parametrize("target", [-0.2, 0.4, 0.55])
def test_pending_long_frame_is_discarded_after_target_leaves_it(target):
    picture = long_picture()
    request = ScrubRequest(0.3)

    assert request.publish(picture)
    request.update(target)
    assert request.take_progress() is None
    assert not request.publish(picture)


def test_nearby_progress_remains_usable_before_exact_frame_arrives():
    picture = Picture(0.0, 0.04, QImage(8, 8, QImage.Format.Format_RGB888))
    request = ScrubRequest(0.1)

    assert request.publish(picture)
    assert request.take_progress() is picture
