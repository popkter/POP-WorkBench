import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QRegion, QWindow
from PySide6.QtTest import QTest

from poptools.infrastructure import card_window_updates as module


def test_updates_coalesce_per_window_and_commit_together(qapp, qtbot, monkeypatch):
    updates = module.CardWindowUpdates(qapp)
    windows = [QWindow(), QWindow()]
    batches = []
    monkeypatch.setattr(module, "_move_windows", lambda moves: batches.append(moves))
    try:
        for window in windows:
            window.resize(100, 100)
            window.show()
        updates.schedule(windows[0], QPoint(100, 100), QRegion(0, 0, 20, 20))
        updates.schedule(windows[0], QPoint(120, 130), QRegion(0, 0, 40, 40))
        updates.schedule(windows[1], QPoint(200, 200), QRegion())
        assert not batches
        qtbot.waitUntil(lambda: len(batches) == 1)
        assert batches[0] == [(windows[0], QPoint(120, 130)), (windows[1], QPoint(200, 200))]
        assert windows[0].mask() == QRegion(0, 0, 40, 40)
        updates.schedule(windows[0], QPoint(150, 150), QRegion())
        updates.finish(windows[0])
        assert batches[-1] == [(windows[0], QPoint(150, 150))]
        qtbot.wait(10)
        assert sum(len(batch) for batch in batches) == 3  # No late replay after finishing.
        windows[1].hide()
        updates.schedule(windows[1], QPoint(300, 300), QRegion())
        updates.flush()
        assert sum(len(batch) for batch in batches) == 3
    finally:
        for window in windows:
            window.close()
        updates.deleteLater()


def test_native_batch_updates_qt_geometry_and_preserves_size(qapp, qtbot):
    windows = [QWindow(), QWindow()]
    try:
        for window in windows:
            window.setFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint)
            window.resize(100, 80)
            window.show()
            assert QTest.qWaitForWindowExposed(window)
        targets = [window.position() + QPoint(25, 30) for window in windows]
        module._move_windows(list(zip(windows, targets, strict=True)))
        qtbot.waitUntil(lambda: all(w.position() == p
                                   for w, p in zip(windows, targets, strict=True)))
        assert all(w.width() == 100 and w.height() == 80 for w in windows)
    finally:
        for window in windows:
            window.close()


@pytest.mark.parametrize("logical,physical", [(QPoint(0, 0), QPoint(0, 0)),
                                            (QPoint(-1280, -300), QPoint(-1920, -450))])
@pytest.mark.parametrize("ratio", [1, 1.25, 1.5, 2])
def test_absolute_native_coordinates_do_not_accumulate_rounding(logical, physical, ratio):
    target = logical + QPoint(32, 32)
    expected = physical + QPoint(round(32 * ratio), round(32 * ratio))
    assert module._native_point(target, logical, physical, ratio) == expected
