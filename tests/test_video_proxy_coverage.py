"""Only committed contiguous proxy frames may preempt foreground source seeks."""
import sqlite3
from contextlib import closing
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Cancelled
from poptools.infrastructure.video_proxy import ScrubProxy


@pytest.fixture
def proxy_fixture(tmp_path, monkeypatch):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'The reader is stubbed; these tests exercise only SQLite coverage')
    proxy = ScrubProxy(str(source), tmp_path / 'cache', full_quality=True)
    image = QImage(8, 8, QImage.Format.Format_RGB888)
    image.fill('red')
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    assert image.save(buffer, 'JPEG', 95)
    jpeg = bytes(buffer.data())
    readers = []

    class Reader:
        def __init__(self, path):
            self.stream = SimpleNamespace(codec_context=SimpleNamespace(thread_count=2))
            self.output_height = 0
            self.targets = []
            self.closed = False
            readers.append(self)

        def seek_raw(self, target, check):
            check()
            self.targets.append(target)
            return None

        def close(self):
            self.closed = True

    monkeypatch.setattr('poptools.infrastructure.video_proxy.VideoReader', Reader)
    return proxy, jpeg, readers


def seed(proxy, jpeg, intervals, state=None):
    with closing(sqlite3.connect(proxy.path)) as db, db:
        db.execute('CREATE TABLE frames '
                   '(time REAL PRIMARY KEY, end REAL NOT NULL, jpeg BLOB NOT NULL)')
        db.execute('CREATE TABLE state (complete INTEGER)')
        db.executemany('INSERT INTO frames VALUES (?, ?, ?)',
                       [(start, end, jpeg) for start, end in intervals])
        if state is not None:
            db.execute('INSERT INTO state VALUES (?)', (state,))


def test_reused_preview_reader_sees_commits_and_recovers_after_failed_query(proxy_fixture):
    transient, jpeg, _ = proxy_fixture
    proxy = ScrubProxy(transient.source, transient.path.parent, full_quality=True,
                       reuse_reads=True)
    assert proxy.get(0) is None
    seed(proxy, jpeg, [(0, .04)])
    first = proxy.get(0)
    assert first is not None
    connection = proxy._read_session.connection

    with closing(sqlite3.connect(proxy.path)) as writer, writer:
        writer.execute('INSERT INTO frames VALUES (?, ?, ?)', (.04, .08, jpeg))
    second = proxy.get(.05)
    assert second is not None and second.time == .04 and second.image == first.image
    assert proxy._read_session.connection is connection

    connection.close()
    assert proxy.get(.05) is None
    assert proxy._read_session.connection is None
    assert proxy.get(.05).image == first.image


def test_coverage_publishes_only_after_first_batch_and_final_commits(proxy_fixture, monkeypatch):
    proxy, jpeg, readers = proxy_fixture
    snapshots = []

    def frames(reader, frame, check, end):
        for index in range(11):
            with closing(sqlite3.connect(proxy.path)) as db:
                committed = db.execute('SELECT COUNT(*) FROM frames').fetchone()[0]
            snapshots.append((committed, proxy._coverage))
            yield index * .04, (index + 1) * .04, jpeg

    monkeypatch.setattr(proxy, '_encoded_frames', frames)
    assert proxy.build(lambda: None)
    assert snapshots[0] == (0, ())
    assert all(row == (1, (0.0, .04)) for row in snapshots[1:8])
    assert all(row == (8, (0.0, .32)) for row in snapshots[8:])
    assert proxy._coverage == pytest.approx((0, .44))
    assert proxy.contains_memory(0) and proxy.contains_memory(.439)
    assert not proxy.contains_memory(-.01) and not proxy.contains_memory(.44)
    assert proxy.get(.02) is not None and readers[0].closed

    def no_io(*args, **kwargs):
        pytest.fail('contains_memory must not perform SQLite or image decoding work')

    monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect', no_io)
    monkeypatch.setattr(QImage, 'fromData', no_io)
    assert proxy.contains_memory(.2) and not proxy.contains_memory(1)


def test_cancellation_keeps_only_previously_committed_coverage(proxy_fixture, monkeypatch):
    proxy, jpeg, readers = proxy_fixture

    def frames(reader, frame, check, end):
        yield 0, .04, jpeg
        yield .04, .08, jpeg
        raise Cancelled()

    monkeypatch.setattr(proxy, '_encoded_frames', frames)
    with pytest.raises(Cancelled):
        proxy.build(lambda: None)
    assert proxy.contains_memory(.02) and not proxy.contains_memory(.06)
    assert proxy.get(.02) is not None and proxy.get(.06) is None
    assert readers[0].closed


def test_resume_recovers_committed_prefix_without_crossing_sparse_gap(proxy_fixture, monkeypatch):
    proxy, jpeg, readers = proxy_fixture
    seed(proxy, jpeg, [(0, .04), (.04, .08), (.16, .2)])

    def frames(reader, frame, check, end):
        assert proxy.contains_memory(.06) and not proxy.contains_memory(.18)
        raise Cancelled()
        yield  # Keep this a generator so closing follows the production path.

    monkeypatch.setattr(proxy, '_encoded_frames', frames)
    with pytest.raises(Cancelled):
        proxy.build(lambda: None)
    assert readers[0].targets == pytest.approx([.08])
    assert proxy._coverage == pytest.approx((0, .08))


@pytest.mark.parametrize('state,complete', [(1, True), (-1, False)])
def test_completed_or_limited_file_restores_prefix_without_decoding(proxy_fixture, monkeypatch,
                                                                  state, complete):
    proxy, jpeg, readers = proxy_fixture
    seed(proxy, jpeg, [(0, .04), (.04, .08), (.16, .2)], state)
    assert not proxy.contains_memory(.02)
    assert proxy.build(lambda: None) is complete
    assert not readers
    assert proxy.contains_memory(.06) and not proxy.contains_memory(.12)
    assert not proxy.contains_memory(.18)


def test_new_sparse_frames_do_not_turn_gaps_into_coverage(proxy_fixture, monkeypatch):
    proxy, jpeg, _ = proxy_fixture
    monkeypatch.setattr(proxy, '_encoded_frames',
                        lambda *args: (row for row in [(0, .04, jpeg), (.08, .12, jpeg)]))
    assert proxy.build(lambda: None)
    assert proxy.contains_memory(.02)
    assert not proxy.contains_memory(.06) and not proxy.contains_memory(.1)
    assert proxy.get(.1) is not None


@pytest.mark.parametrize('kind', ['partial', 'on-demand'])
def test_neighborhood_build_clears_coverage_before_possible_eviction(
        proxy_fixture, monkeypatch, kind):
    proxy, jpeg, _ = proxy_fixture
    seed(proxy, jpeg, [(0, .04), (.04, .08)], state=1)
    assert proxy.build(lambda: None) and proxy.contains_memory(.02)
    if kind == 'on-demand':
        proxy.on_demand = True
        assert proxy.build(lambda: None)
    else:
        proxy.MAX_FILE_BYTES = len(jpeg)

        def frames(*args):
            assert not proxy.contains_memory(.02)
            yield .5, .54, jpeg

        monkeypatch.setattr(proxy, '_encoded_frames', frames)
        assert proxy.build(lambda: None, start=.5, end=.54)
        assert proxy.get(.5) is not None
    assert proxy._coverage == ()


@pytest.mark.parametrize('failure', ['missing-row', 'gap', 'bad-jpeg', 'database', 'missing-file'])
def test_known_coverage_miss_is_invalidated_to_avoid_repeated_preemption(
        proxy_fixture, monkeypatch, failure):
    proxy, jpeg, _ = proxy_fixture
    seed(proxy, jpeg, [(0, .04), (.04, .08)], state=1)
    assert proxy.build(lambda: None) and proxy.contains_memory(.05)
    assert proxy.get(.2) is None and proxy.contains_memory(.05)
    if failure == 'missing-row':
        with closing(sqlite3.connect(proxy.path)) as db, db:
            db.execute('DELETE FROM frames')
    elif failure == 'gap':
        with closing(sqlite3.connect(proxy.path)) as db, db:
            db.execute('UPDATE frames SET end=.045 WHERE time=.04')
    elif failure == 'bad-jpeg':
        with closing(sqlite3.connect(proxy.path)) as db, db:
            db.execute('UPDATE frames SET jpeg=?', (b'broken',))
    elif failure == 'database':
        def unavailable(*args, **kwargs):
            raise sqlite3.OperationalError('database unavailable')
        monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect', unavailable)
    else:
        proxy.path.unlink()
    assert proxy.get(.05) is None
    assert not proxy.contains_memory(.05) and not proxy.contains_memory(.01)


def test_failed_commit_never_publishes_uncommitted_frames(proxy_fixture, monkeypatch):
    proxy, jpeg, _ = proxy_fixture
    connect = sqlite3.connect

    class FailedBatch(sqlite3.Connection):
        commits = 0

        def commit(self):
            self.commits += 1
            if self.commits == 3:
                raise sqlite3.OperationalError('commit failed')
            return super().commit()

    monkeypatch.setattr('poptools.infrastructure.video_proxy.sqlite3.connect',
                        lambda *args, **kwargs: connect(*args, factory=FailedBatch, **kwargs))
    monkeypatch.setattr(proxy, '_encoded_frames', lambda *args:
                        ((index * .04, (index + 1) * .04, jpeg) for index in range(9)))
    assert not proxy.build(lambda: None)
    assert proxy.build_disabled
    assert proxy.contains_memory(.02) and not proxy.contains_memory(.06)
    with closing(connect(proxy.path)) as db:
        assert db.execute('SELECT COUNT(*) FROM frames').fetchone()[0] == 1
