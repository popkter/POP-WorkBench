"""Sparse previews retain real source intervals and never masquerade as a full proxy."""
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Cancelled, VideoPictureConverter, VideoReader
from poptools.infrastructure.video_proxy import ScrubProxy
from test_video_preview import make_video


@pytest.fixture(autouse=True)
def application(qapp):
    return qapp


@pytest.fixture
def overview(tmp_path):
    source = make_video(tmp_path / 'overview.mp4', pts=list(range(0, 1000, 40)), size=(96, 64))
    return ScrubProxy(str(source), tmp_path / 'cache', full_quality=True, output_height=600)


def rows(proxy):
    with closing(sqlite3.connect(proxy.path)) as db:
        return db.execute('SELECT time, end, jpeg FROM frames ORDER BY time').fetchall()


def progress(proxy):
    with closing(sqlite3.connect(proxy.path)) as db:
        return db.execute('SELECT spacing, next_time, complete FROM overview_progress '
                          'WHERE id=1').fetchone()


def jpeg(image):
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'JPEG', 95)
    return bytes(buffer.data())


def seed(proxy, intervals, full_state=None, overview_state=None):
    image = QImage(8, 8, QImage.Format.Format_RGB888)
    image.fill('red')
    data = jpeg(image)
    with closing(sqlite3.connect(proxy.path)) as db, db:
        db.execute('CREATE TABLE frames '
                   '(time REAL PRIMARY KEY, end REAL NOT NULL, jpeg BLOB NOT NULL)')
        db.execute('CREATE TABLE state (complete INTEGER)')
        db.executemany('INSERT INTO frames VALUES (?, ?, ?)',
                       [(left, right, data) for left, right in intervals])
        if full_state is not None:
            db.execute('INSERT INTO state VALUES (?)', (full_state,))
        if overview_state is not None:
            db.execute('CREATE TABLE overview_progress '
                       '(id INTEGER PRIMARY KEY, spacing REAL, next_time REAL, complete INTEGER)')
            db.execute('INSERT INTO overview_progress VALUES (1, ?, ?, ?)', overview_state)
    return data


@pytest.mark.parametrize("threads", [1, 4])
def test_sparse_overview_keeps_true_intervals_without_claiming_full_prefix(overview, threads):
    published = []

    def publish(picture):
        if not published:
            assert overview.get(picture.time) is None
        published.append(picture)

    assert overview.prepare_overview(lambda: None, frame_threads=threads, publish=publish)
    stored = rows(overview)
    assert [(picture.time, picture.end, jpeg(picture.image)) for picture in published] == stored
    assert overview.overview_end == pytest.approx(stored[-1][1])
    assert [row[0] for row in stored] == pytest.approx(
        [0, .2, .4, .6, .8, .96])
    assert all(right - left == pytest.approx(.04) for left, right, _ in stored)
    assert overview.get(.08) is None
    nearby = overview.get_nearest(.13)
    assert nearby.approximate and nearby.time == pytest.approx(.2)
    assert nearby.end == pytest.approx(.24)
    exact = overview.get_nearest(.21)
    assert not exact.approximate and exact.time == pytest.approx(.2)
    assert not overview.contains_memory(.02)
    assert not overview.status()['complete']
    with closing(sqlite3.connect(overview.path)) as db:
        assert db.execute('SELECT complete FROM state').fetchone() is None
    assert progress(overview)[2] == 1


@pytest.mark.parametrize("fail_first", [False, True])
def test_overview_converts_frames_concurrently_and_publishes_in_order(
    overview, monkeypatch, fail_first
):
    second_converted = threading.Event()
    published, workers = [], set()
    original = VideoPictureConverter.picture

    def convert(self, frame, width=None):
        workers.add(threading.get_ident())
        timestamp = self.timestamp(frame)
        if timestamp == 0:
            assert second_converted.wait(3)
            if fail_first:
                raise ValueError("First preview failed to convert")
        picture = original(self, frame, width)
        if timestamp == .2:
            second_converted.set()
        return picture

    monkeypatch.setattr(VideoPictureConverter, "picture", convert)
    if fail_first:
        with pytest.raises(ValueError, match="First preview failed to convert"):
            overview.prepare_overview(lambda: None, frame_threads=4, publish=published.append)
        assert not published and not rows(overview)
    else:
        assert overview.prepare_overview(lambda: None, frame_threads=4, publish=published.append)
        assert [(picture.time, picture.end, jpeg(picture.image)) for picture in published] == rows(
            overview)
    assert len(workers) == 2


def test_near_lookup_prefers_real_vfr_coverage_and_enforces_tolerance(overview, monkeypatch):
    seed(overview, [(0, .4), (.5, .54)], overview_state=(.1, .6, 1))
    assert overview.prepare_overview(lambda: None)
    covered = overview.get_nearest(.39, .01)
    assert covered.time == 0 and covered.end == .4 and not covered.approximate
    assert overview.get_nearest(.45, .04) is None
    nearby = overview.get_nearest(.46, .04)
    assert nearby.time == .5 and nearby.approximate
    assert not overview.get_nearest(.52, 0).approximate

    def no_io(*args, **kwargs):
        pytest.fail('Near memory hints must not touch disk or decode JPEG')

    monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect', no_io)
    monkeypatch.setattr(QImage, 'fromData', no_io)
    assert overview.contains_near_memory(.39, .01)
    assert not overview.contains_near_memory(.45, .04)
    assert overview.contains_near_memory(.46, .04)
    assert overview.contains_near_memory(.52, 0)
    assert not overview.contains_near_memory(.8)


def test_overview_preserves_existing_rows_and_exact_coverage_hint(overview):
    original = seed(overview, [(0, .04)])
    overview._coverage = (0, .04)
    assert overview.prepare_overview(lambda: None)
    assert rows(overview)[0] == (0, .04, original)
    assert overview._coverage == (0, .04)
    assert not overview.get_nearest(.02).approximate
    assert not overview.contains_memory(.13)


def test_sparse_nearest_prefers_earlier_timestamp_when_distances_tie(overview):
    seed(overview, [(.125, .15625), (.375, .40625)])
    assert overview.get(.25) is None
    earlier = overview.get_nearest(.25, .125)
    assert earlier.approximate and earlier.time == .125
    assert overview.get_nearest(.251, .125).time == .375


def test_cancellation_checkpoint_does_not_skip_speculatively_encoded_samples(
        overview, tmp_path):
    def cancel_after_first_commit():
        if overview._near_frames:
            raise Cancelled()

    with pytest.raises(Cancelled):
        overview.prepare_overview(cancel_after_first_commit)
    assert [row[0] for row in rows(overview)] == [0]
    assert progress(overview) == (.18, .18, 0)
    assert overview.contains_near_memory(.02, 0)
    assert not overview.contains_near_memory(.24, 0)
    assert not any(thread.name.startswith('video-proxy-jpeg') for thread in threading.enumerate())

    reopened = ScrubProxy(overview.source, overview.path.parent,
                         full_quality=True, output_height=600)
    assert not reopened.contains_near_memory(.02)
    assert reopened.prepare_overview(lambda: None)
    fresh = ScrubProxy(overview.source, tmp_path / 'fresh', full_quality=True, output_height=600)
    assert fresh.prepare_overview(lambda: None)
    assert rows(reopened) == rows(fresh)
    assert reopened.overview_end == pytest.approx(fresh.overview_end)
    assert progress(reopened)[2] == 1
    assert not reopened.status()['complete']


def test_cancelled_overview_preserves_rows_written_after_last_batch(overview, monkeypatch):
    encoded_frames = overview._encoded_frames

    def stop_after_three(*args, **kwargs):
        with closing(encoded_frames(*args, **kwargs)) as frames:
            for count, row in enumerate(frames, 1):
                yield row
                if count == 3:
                    raise Cancelled()

    with monkeypatch.context() as interrupted:
        interrupted.setattr(overview, '_encoded_frames', stop_after_three)
        with pytest.raises(Cancelled):
            overview.prepare_overview(lambda: None)

    assert [row[0] for row in rows(overview)] == pytest.approx([0, .2, .4])
    assert progress(overview) == pytest.approx((.18, .58, 0))
    assert overview.contains_near_memory(.42, 0)
    assert not overview.contains_near_memory(.62, 0)
    assert not overview.status()['complete']
    assert overview.prepare_overview(lambda: None)
    assert [row[0] for row in rows(overview)] == pytest.approx([0, .2, .4, .6, .8, .96])


def test_paused_overview_commits_current_rows_and_resumes_same_decoder(overview, monkeypatch, qtbot):
    encode = overview._encoded_frames
    running = threading.Event()
    running.set()
    readers = []

    def pause_after_third(reader, frame, check, *args, **kwargs):
        readers.append(reader)
        with closing(encode(reader, frame, check, *args, **kwargs)) as frames:
            for count, row in enumerate(frames, 1):
                yield row
                if count == 3:
                    running.clear()
                    check()

    monkeypatch.setattr(overview, '_encoded_frames', pause_after_third)
    with ThreadPoolExecutor(max_workers=1) as worker:
        future = worker.submit(overview.prepare_overview, lambda: None, run_event=running)
        try:
            qtbot.waitUntil(lambda: not running.is_set() and len(rows(overview)) == 3)
            assert not future.done()
            assert progress(overview) == pytest.approx((.18, .58, 0))
            with closing(sqlite3.connect(overview.path, timeout=.1)) as db:
                db.execute('BEGIN IMMEDIATE')
                db.rollback()
        finally:
            running.set()
        assert future.result(2)
    assert len(readers) == 1
    assert [row[0] for row in rows(overview)] == pytest.approx([0, .2, .4, .6, .8, .96])


def test_full_build_after_overview_fills_gaps_instead_of_skipping_to_last_sample(
        overview, monkeypatch, tmp_path):
    assert overview.prepare_overview(lambda: None)
    sparse = {row[0]: row[2] for row in rows(overview)}
    seeks = []
    conversions = []
    seek = VideoReader.seek_raw
    picture = VideoReader.picture

    def record(reader, target, check):
        seeks.append(target)
        return seek(reader, target, check)

    def record_picture(reader, frame, width):
        conversions.append(reader.timestamp(frame))
        return picture(reader, frame, width)

    monkeypatch.setattr(VideoReader, 'seek_raw', record)
    monkeypatch.setattr(VideoReader, 'picture', record_picture)
    assert overview.build(lambda: None)
    assert seeks[0] == pytest.approx(.04)
    full = rows(overview)
    assert len(full) == 25
    assert conversions == [row[0] for row in full if row[0] not in sparse]
    assert overview.status()['complete'] and overview.contains_memory(.08)
    assert not overview.get_nearest(.08).approximate
    fresh = ScrubProxy(overview.source, tmp_path / 'full', full_quality=True, output_height=600)
    assert fresh.build(lambda: None)
    assert full == rows(fresh)


@pytest.mark.parametrize('state,expected', [(1, True), (-1, False)])
def test_existing_full_terminal_state_exits_without_decoding(
        overview, monkeypatch, state, expected):
    seed(overview, [(0, .04)], full_state=state)
    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader',
                        lambda *args: pytest.fail('Terminal full cache must not be decoded again'))
    assert overview.prepare_overview(lambda: None) is expected
    assert overview.contains_near_memory(.02, 0)
    assert not overview.contains_memory(.02)


def test_overview_complete_is_resumable_without_repeating_decode(overview, monkeypatch):
    assert overview.prepare_overview(lambda: None)
    reopened = ScrubProxy(overview.source, overview.path.parent,
                         full_quality=True, output_height=600)
    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader',
                        lambda *args: pytest.fail('Completed overview must not restart decoding'))
    assert reopened.prepare_overview(lambda: None)
    assert reopened.contains_near_memory(.08)
    assert not reopened.status()['complete']


def test_overview_budget_counts_all_existing_frames_and_stops_retrying(overview, monkeypatch):
    existing = seed(overview, [(.4, .44)])
    reader = VideoReader(overview.source)
    try:
        reader.output_height = 600
        reader.interpolation = 'BICUBIC'
        first_bytes = jpeg(reader.seek(0, lambda: None).image)
    finally:
        reader.close()
    overview.MAX_FILE_BYTES = len(existing) + len(first_bytes)
    assert not overview.prepare_overview(lambda: None)
    stored = rows(overview)
    assert sum(len(row[2]) for row in stored) <= overview.MAX_FILE_BYTES
    assert next(row for row in stored if row[0] == .4)[2] == existing
    assert progress(overview)[2] == -1
    assert not overview.status()['complete'] and not overview.status()['limited']
    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader',
                        lambda *args: pytest.fail('Limited overview must not restart decoding'))
    assert not overview.prepare_overview(lambda: None)


def test_frame_larger_than_budget_leaves_readable_empty_overview(overview):
    overview.MAX_FILE_BYTES = 1
    assert not overview.prepare_overview(lambda: None)
    assert rows(overview) == [] and progress(overview) == (.18, 0.0, -1)
    assert overview.get_nearest(0) is None and not overview.contains_near_memory(0)


@pytest.mark.parametrize('size,output_height,expected', [
    ((96, 64), 600, (96, 64)), ((800, 640), 600, (750, 600)),
    ((800, 640), 0, (800, 640)),
])
def test_overview_keeps_native_or_requested_dimensions_and_identical_jpeg95(
        tmp_path, size, output_height, expected):
    path = make_video(tmp_path / 'quality.mp4', pts=[0, 40, 80, 120], size=size)
    proxy = ScrubProxy(str(path), tmp_path / 'quality-cache', full_quality=True,
                       output_height=output_height)
    assert proxy.prepare_overview(lambda: None)
    reader = VideoReader(str(path))
    try:
        reader.output_height = output_height
        reader.interpolation = proxy.interpolation
        for timestamp, end, data in rows(proxy):
            expected_picture = reader.seek(timestamp + .001, lambda: None)
            assert end == pytest.approx(expected_picture.end)
            assert data == jpeg(expected_picture.image)
            image = QImage.fromData(data, 'JPEG')
            assert (image.width(), image.height()) == expected
    finally:
        reader.close()


def test_failed_commit_preserves_previous_checkpoint_and_near_snapshot(overview, monkeypatch):
    connect = sqlite3.connect

    class FailedBatch(sqlite3.Connection):
        commits = 0

        def commit(self):
            self.commits += 1
            if self.commits == 3:
                raise sqlite3.OperationalError('Commit failed')
            return super().commit()

    monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect',
                        lambda *args, **kwargs: connect(*args, factory=FailedBatch, **kwargs))
    assert not overview.prepare_overview(lambda: None)
    assert overview.build_disabled and progress(overview) == (.18, .18, 0)
    assert [row[0] for row in rows(overview)] == [0]
    assert overview.contains_near_memory(.02, 0)
    assert not overview.contains_near_memory(.24, 0)


def test_missing_near_frame_invalidates_memory_hint(overview):
    assert overview.prepare_overview(lambda: None)
    assert overview.contains_near_memory(.08)
    with closing(sqlite3.connect(overview.path)) as db, db:
        db.execute('DELETE FROM frames')
    assert overview.get_nearest(.08) is None
    assert not overview.contains_near_memory(.08)


@pytest.mark.parametrize('spacing', [0, -.1, float('nan'), float('inf')])
def test_overview_rejects_invalid_spacing(overview, spacing):
    with pytest.raises(ValueError, match='spacing'):
        overview.prepare_overview(lambda: None, spacing)
