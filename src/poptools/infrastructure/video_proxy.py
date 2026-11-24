"""Progressive on-disk, intra-frame previews indexed by source timestamps."""
from __future__ import annotations

import bisect
import hashlib
import math
import sqlite3
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import closing, contextmanager
from pathlib import Path

from PySide6.QtCore import QBuffer, QCoreApplication, QIODevice
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import (
    Cancelled,
    Picture,
    VideoPictureConverter,
    VideoReader,
)


class ScrubProxy:
    MAX_FILE_BYTES = 512 * 1024 * 1024
    MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024
    MAX_ENCODING_BYTES = 32 * 1024 * 1024
    MAX_ENCODING_FRAMES = 3
    MAX_OVERVIEW_ENCODING_BYTES = 48 * 1024 * 1024

    def __init__(self, source: str, directory: Path, on_demand=False,
                 full_quality=False, output_height=0, *, reuse_reads=False):
        self.source = source
        self.on_demand = on_demand
        self.full_quality = full_quality
        self.output_height = output_height if full_quality else 0
        self.interpolation = 'BICUBIC' if self.output_height == 600 else None
        self.jpeg_quality = 95 if full_quality else 80
        self.build_disabled = False
        self._pruned = False
        self._coverage = ()
        self._near_frames = ()
        self._read_session = threading.local() if reuse_reads else None
        self.overview_end = None
        if full_quality:
            self.MAX_FILE_BYTES = 1024 * 1024 * 1024
            self.MAX_CACHE_BYTES = 3 * 1024 * 1024 * 1024
        stat = Path(source).stat()
        version = 'v2' if full_quality else 'v1'
        identity = f'{version}:{Path(source).resolve()}:{stat.st_size}:{stat.st_mtime_ns}'
        if full_quality:
            identity += f':height={self.output_height}:jpeg={self.jpeg_quality}'
            if self.interpolation:
                identity += f':interpolation={self.interpolation}'
        key = hashlib.sha256(identity.encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = (directory / f'video-proxy-{version}-{key}.sqlite').resolve()
        self._read_uri = self.path.as_uri() + '?mode=ro'

    def _prune(self):
        files = []
        for path in self.path.parent.glob('video-proxy-v*-*.sqlite'):
            try:
                stat = path.stat()
                files.append((stat.st_mtime, stat.st_size, path))
            except OSError:
                continue  # A concurrent cache owner may have removed it.
        total = sum(size for _, size, _ in files)
        for _, size, path in sorted(files):
            if total <= self.MAX_CACHE_BYTES - self.MAX_FILE_BYTES:
                break
            if path == self.path:
                continue
            try:
                path.unlink()
                total -= size
            except OSError:
                pass  # Another player may still have the cache open.

    def contains_memory(self, target: float) -> bool:
        """Read the committed contiguous prefix without touching disk or images."""
        coverage = self._coverage
        return bool(coverage) and coverage[0] <= target < coverage[1] - 1e-7

    def contains_near_memory(self, target: float, tolerance: float = .12) -> bool:
        """Inspect committed frame times without disk access or image decoding."""
        if not math.isfinite(target) or not math.isfinite(tolerance) or tolerance < 0:
            return False
        frames = self._near_frames
        index = bisect.bisect_right(frames, (target + 1e-7, math.inf)) - 1
        if index >= 0 and target < frames[index][1] - 1e-7:
            return True
        return any(abs(timestamp - target) <= tolerance + 1e-7
                   for timestamp, _ in frames[max(0, index):index + 2])

    def get_nearest(self, target: float, tolerance: float = .12) -> Picture | None:
        """Prefer a covering source interval; otherwise return a marked nearby frame."""
        if not math.isfinite(target) or not math.isfinite(tolerance) or tolerance < 0:
            return None
        return self._read_frame(target, tolerance)

    def get(self, target: float) -> Picture | None:
        return self._read_frame(target, None)

    @contextmanager
    def _reader(self):
        session = self._read_session
        if session is None:
            with closing(sqlite3.connect(self._read_uri, uri=True, timeout=.01)) as db:
                yield db
            return

        # Preserve SQLite's thread affinity. A replaced cache file or a failed
        # query must drop the lease so a later read can see the rebuilt cache.
        db = getattr(session, 'connection', None)
        try:
            stat = self.path.stat()
            identity = (stat.st_dev, stat.st_ino)
            if db is None or identity != session.identity:
                session.connection = None
                if db is not None:
                    db.close()
                db = sqlite3.connect(self._read_uri, uri=True, timeout=.01)
                session.connection = db
                session.identity = identity
            yield db
        except (sqlite3.Error, OSError):
            connection = getattr(session, 'connection', None)
            if connection is not None:
                session.connection = None
                connection.close()
            raise

    def _read_frame(self, target, tolerance):
        picture = None
        try:
            with self._reader() as db:
                # A sparse cache often has a predecessor whose interval does
                # not reach the target. Skip its large JPEG on a cache miss.
                row = db.execute(
                    'SELECT time, end, CASE WHEN end - 0.0000001 > ? THEN jpeg END '
                    'FROM frames WHERE time <= ? ORDER BY time DESC LIMIT 1',
                    (target, target + 1e-7)).fetchone()
                exact = row is not None and row[2] is not None
                if not exact and tolerance is not None:
                    # Search only indexed timestamps in the tolerance window
                    # and fetch a single JPEG. Equal distances favor the past.
                    distance = tolerance + 1e-7
                    row = db.execute(
                        'SELECT time, end, jpeg FROM frames WHERE time = ('
                        'SELECT time FROM frames WHERE time BETWEEN ? AND ? '
                        'ORDER BY abs(time - ?), time LIMIT 1)',
                        (target - distance, target + distance, target)).fetchone()
            if row and (exact or (tolerance is not None
                                  and abs(row[0] - target) <= tolerance + 1e-7)):
                image = QImage.fromData(row[2], 'JPEG')
                if not image.isNull():
                    picture = Picture(row[0], row[1], image, approximate=not exact)
        except (sqlite3.Error, OSError):
            pass
        if (picture is None or picture.approximate) and self.contains_memory(target):
            # A stale/corrupt cache must not repeatedly preempt useful source
            # decoding just because its formerly committed range is remembered.
            self._coverage = ()
        if (picture is None and tolerance is not None
                and self.contains_near_memory(target, tolerance)):
            self._near_frames = ()
        return picture

    def covers(self, start, end):
        try:
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                                         timeout=0.01)) as db:
                rows = db.execute('SELECT time, end FROM frames WHERE end > ? AND time < ? '
                                  'ORDER BY time', (start, end)).fetchall()
            cursor = start
            for left, right in rows:
                if left > cursor + 1e-7:
                    return False
                cursor = max(cursor, right)
            return cursor >= end - 1e-7
        except (sqlite3.Error, OSError):
            return False

    def status(self):
        """Inspect preparation on a worker; no JPEG decoding is required."""
        result = {'complete': False, 'limited': False, 'frames': 0,
                  'seconds': 0.0, 'bytes': 0}
        try:
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                                         timeout=0.01)) as db:
                state = db.execute('SELECT complete FROM state').fetchone()
                row = db.execute('SELECT COUNT(*), COALESCE(SUM(end-time), 0), '
                                 'COALESCE(SUM(LENGTH(jpeg)), 0) FROM frames').fetchone()
            result.update(complete=state == (1,), limited=state == (-1,),
                          frames=row[0], seconds=row[1], bytes=row[2])
        except (sqlite3.Error, OSError):
            pass
        return result

    def warm(self, target, check):
        # Commit the pointed-to neighborhood before doing the backward portion.
        for start, end in ((target, target + 2.5), (max(0, target - 1.5), target)):
            check()
            if (start < end and not self.covers(start, end)
                    and not self.build(check, start=start, end=end)):
                return False
        return True

    @staticmethod
    def _encode_image(image, quality):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not image.save(buffer, 'JPEG', quality):
            raise ValueError('JPEG preview encoding is unavailable')
        return bytes(buffer.data())

    @staticmethod
    def _encoding_bytes(reader, frame, width):
        # Reserve output storage before converting another frame. Include Qt's
        # row padding and rotation, so large frames use only one encoding slot.
        scale = (min(1, width / frame.width) if width is not None else
                 min(1, reader.output_height / min(frame.width, frame.height))
                 if reader.output_height else 1)
        width = max(2, round(frame.width * scale))
        height = max(2, round(frame.height * scale))
        rotation = -getattr(frame, 'rotation', 0) or reader.rotation
        channels = 3
        if rotation % 90:
            angle = math.radians(rotation)
            cosine, sine = abs(math.cos(angle)), abs(math.sin(angle))
            width, height = (math.ceil(width * cosine + height * sine) + 2,
                             math.ceil(width * sine + height * cosine) + 2)
            channels = 4  # Arbitrary rotation can add an alpha channel.
        elif rotation % 180:
            width, height = height, width
        return ((width * channels + 3) // 4 * 4) * height

    def _encoded_frames(self, reader, frame, check, end, select=None, reuse=None, publish=None):
        """Decode on the owner, encode bounded images in parallel, yield in order."""
        if (select is not None and publish is not None and reuse is None
                and QCoreApplication.instance() is not None):
            yield from self._encoded_overview_frames(reader, frame, check, end, select, publish)
            return
        pending = deque()
        pending_bytes = 0
        # Standalone callers can build before creating a Qt application. Keep
        # Qt codec initialization on their owner thread in that case.
        encoder = (ThreadPoolExecutor(max_workers=2, thread_name_prefix='video-proxy-jpeg')
                   if QCoreApplication.instance() is not None else None)
        try:
            while pending or (frame is not None and (end is None or reader.timestamp(frame) < end)):
                while frame is not None and (end is None or reader.timestamp(frame) < end):
                    check()
                    width = (None if self.full_quality else
                             round(960 * frame.width / max(frame.width, frame.height)))
                    required = self._encoding_bytes(reader, frame, width)
                    if pending and (len(pending) >= self.MAX_ENCODING_FRAMES
                                    or pending_bytes + required > self.MAX_ENCODING_BYTES):
                        break
                    successor = reader.raw_next(check)
                    if select is not None and not select(frame, successor):
                        frame = successor
                        continue
                    if reuse and (timestamp := max(0.0, reader.timestamp(frame))) in reuse:
                        frame_end = reuse[timestamp]
                        if successor is None or frame_end == reader.timestamp(successor):
                            # This interval already has a JPEG at the same quality.
                            # Keep it in presentation order for coverage tracking.
                            frame = successor
                            if encoder is None:
                                check()
                                yield timestamp, frame_end, None
                            else:
                                pending.append((timestamp, frame_end, 0, None))
                            continue
                    picture = reader.picture(frame, width)
                    if successor is not None:
                        picture.end = reader.timestamp(successor)
                    size = picture.image.sizeInBytes()
                    check()
                    if publish is not None:
                        publish(picture)
                    if encoder is None:
                        data = self._encode_image(picture.image, self.jpeg_quality)
                        timestamp, frame_end = picture.time, picture.end
                        del picture
                        frame = successor
                        check()
                        yield timestamp, frame_end, data
                        continue
                    future = encoder.submit(self._encode_image, picture.image, self.jpeg_quality)
                    pending.append((picture.time, picture.end, size, future))
                    pending_bytes += size
                    del picture
                    frame = successor
                if not pending:
                    break
                timestamp, frame_end, size, future = pending[0]
                data = self._encoding_result(future, check)
                pending.popleft()
                pending_bytes -= size
                check()
                yield timestamp, frame_end, data
        finally:
            for _, _, _, future in pending:
                if future is not None:
                    future.cancel()
            if encoder is not None:
                encoder.shutdown(wait=True, cancel_futures=True)

    @staticmethod
    def _encoding_result(future, check):
        if future is None:
            return None
        while True:
            check()
            try:
                return future.result(timeout=.02)
            except TimeoutError:
                if future.done():
                    return future.result()

    def _encoded_overview_frames(self, reader, frame, check, end, select, publish):
        """Keep the sparse decoder moving while its selected frames are converted."""
        pending = deque()
        pending_bytes = submitted = next_publication = 0
        stopping = False
        publication = threading.Condition()
        conversion = threading.local()
        settings = (reader.origin, reader.fps, reader.rotation,
                    reader.output_height, reader.interpolation)

        def convert_and_encode(index, raw, width, frame_end):
            nonlocal next_publication
            converter = getattr(conversion, 'converter', None)
            if converter is None:
                converter = conversion.converter = VideoPictureConverter(*settings)
            picture = converter.picture(raw, width)
            if frame_end is not None:
                picture.end = frame_end
            with publication:
                # Scaling can finish out of order. Publish pixels as soon as
                # possible while keeping timestamps in presentation order.
                publication.wait_for(lambda: stopping or index == next_publication)
                if stopping:
                    return None
                publish(picture)
                next_publication += 1
                publication.notify_all()
            data = self._encode_image(picture.image, self.jpeg_quality)
            return picture.time, picture.end, data

        encoder = ThreadPoolExecutor(max_workers=2, thread_name_prefix='video-proxy-jpeg')
        try:
            while frame is not None and (end is None or reader.timestamp(frame) < end):
                successor = reader.raw_next(check)
                if select(frame, successor):
                    width = (None if self.full_quality else
                             round(960 * frame.width / max(frame.width, frame.height)))
                    size = self._encoding_bytes(reader, frame, width)
                    size += sum(plane.buffer_size for plane in frame.planes)
                    while pending and (len(pending) >= self.MAX_ENCODING_FRAMES
                                       or pending_bytes + size > self.MAX_OVERVIEW_ENCODING_BYTES):
                        reserved, future = pending[0]
                        result = self._encoding_result(future, check)
                        pending.popleft()
                        pending_bytes -= reserved
                        check()
                        yield result
                    frame_end = reader.timestamp(successor) if successor is not None else None
                    future = encoder.submit(convert_and_encode, submitted, frame, width, frame_end)
                    pending.append((size, future))
                    pending_bytes += size
                    submitted += 1
                frame = successor
            while pending:
                _, future = pending[0]
                result = self._encoding_result(future, check)
                pending.popleft()
                check()
                yield result
        finally:
            with publication:
                stopping = True
                publication.notify_all()
            for _, future in pending:
                future.cancel()
            encoder.shutdown(wait=True, cancel_futures=True)

    def prepare_overview(self, check, spacing=.18, *, frame_threads=1, publish=None,
                         run_event: threading.Event | None = None):
        """Prepare sparse, full-quality frames without declaring full coverage.

        This worker-only pass stores real source intervals in the shared frames
        table. Its checkpoint is committed independently of full-build state.
        """
        if not math.isfinite(spacing) or spacing <= 0:
            raise ValueError('Overview spacing must be positive and finite')
        if self.build_disabled:
            return False
        db = None
        reader = None
        try:
            check()
            if not self._pruned:
                self._prune()
                self._pruned = True
            db = sqlite3.connect(self.path, timeout=.1)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS frames '
                       '(time REAL PRIMARY KEY, end REAL NOT NULL, jpeg BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS state (complete INTEGER)')
            db.execute('CREATE TABLE IF NOT EXISTS overview_progress '
                       '(id INTEGER PRIMARY KEY CHECK (id=1), spacing REAL NOT NULL, '
                       'next_time REAL NOT NULL, complete INTEGER NOT NULL)')
            db.commit()
            available = dict(db.execute('SELECT time, end FROM frames ORDER BY time'))
            self._near_frames = tuple(sorted(available.items()))
            full_state = db.execute('SELECT complete FROM state').fetchone()
            if full_state in ((1,), (-1,)):
                if full_state == (1,):
                    self.overview_end = max(available.values(), default=None)
                return full_state == (1,)
            progress = db.execute('SELECT spacing, next_time, complete FROM overview_progress '
                                  'WHERE id=1').fetchone()
            if progress and 0 < progress[0] <= spacing + 1e-9:
                spacing = progress[0]
                checkpoint = progress[1]
                if progress[2] in (1, -1):
                    if progress[2] == 1:
                        self.overview_end = max(available.values(), default=None)
                    return progress[2] == 1
            else:
                checkpoint = 0.0
            next_sample = checkpoint
            committed_checkpoint = checkpoint

            def select(frame, successor):
                nonlocal next_sample
                timestamp = reader.timestamp(frame)
                if timestamp + 1e-7 < next_sample and successor is not None:
                    return False
                next_sample = timestamp + spacing
                return True

            def commit(complete=0):
                nonlocal committed_checkpoint
                db.execute('INSERT OR REPLACE INTO overview_progress VALUES (1, ?, ?, ?)',
                           (spacing, checkpoint, complete))
                db.commit()
                committed_checkpoint = checkpoint
                self._near_frames = tuple(sorted(available.items()))

            def check_running():
                check()
                if run_event is None or run_event.is_set():
                    return
                # Leave no write transaction open while the foreground seeks.
                if checkpoint > committed_checkpoint:
                    commit()
                while not run_event.wait(.02):
                    check()
                check()

            check_running()
            reader = VideoReader(self.source)
            if frame_threads > 1:
                reader.stream.thread_type = "FRAME"
            reader.stream.codec_context.thread_count = frame_threads
            reader.output_height = self.output_height
            reader.interpolation = self.interpolation
            frame = reader.seek_raw(checkpoint, check_running)
            size = db.execute('SELECT COALESCE(SUM(LENGTH(jpeg)), 0) FROM frames').fetchone()[0]
            count = 0
            try:
                with closing(self._encoded_frames(
                        reader, frame, check_running, None, select, publish=publish)) as frames:
                    for timestamp, frame_end, data in frames:
                        # Existing exact rows retain both their bytes and intervals.
                        if timestamp not in available:
                            if size + len(data) > self.MAX_FILE_BYTES:
                                commit(-1)
                                return False
                            db.execute('INSERT INTO frames VALUES (?, ?, ?)',
                                       (timestamp, frame_end, data))
                            available[timestamp] = frame_end
                            size += len(data)
                        # Persist only rows accepted from the encoder. Pending
                        # conversions may have sampled much farther ahead.
                        checkpoint = timestamp + spacing
                        count += 1
                        if count == 1 or count % 8 == 0:
                            commit()
            except Cancelled:
                if checkpoint > committed_checkpoint:
                    try:
                        commit()
                    except sqlite3.Error:
                        # Closing the connection rolls back this partial batch.
                        pass
                raise
            commit(1)
            self.overview_end = max(available.values(), default=None)
            self.path.touch()
            return True
        except (OSError, sqlite3.Error):
            self.build_disabled = True
            return False
        finally:
            if db is not None:
                db.close()
            if reader is not None:
                reader.close()

    def build(self, check, start=0, end=None):
        track_coverage = end is None and start == 0 and not self.on_demand
        if not track_coverage:
            # Neighborhood builds can evict any older frame. Only full builds
            # publish a stable prefix, never gaps between sampled neighborhoods.
            self._coverage = ()
            self._near_frames = ()
        if self.build_disabled:
            return False
        db = None
        reader = None
        try:
            check()
            if not self._pruned:
                # Scanning/deleting large caches belongs to this background
                # preparation job, never the GUI's video-open callback.
                self._prune()
                self._pruned = True
            db = sqlite3.connect(self.path, timeout=0.1)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS frames '
                       '(time REAL PRIMARY KEY, end REAL NOT NULL, jpeg BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS state (complete INTEGER)')
            db.commit()
            last = start
            if end is None:
                # A file may already contain disjoint on-demand neighborhoods.
                # Resume only the contiguous prefix, never skip gaps using MAX(end).
                for left, right in db.execute('SELECT time, end FROM frames ORDER BY time'):
                    if left > last + 1e-7:
                        break
                    last = max(last, right)
                if track_coverage:
                    self._coverage = (0.0, last) if last > 0 else ()
                state = db.execute('SELECT complete FROM state').fetchone()
                if state in ((1,), (-1,)):
                    # Restore committed coverage even when no decoding is needed.
                    # A saturated full build must not repeatedly restart decoding.
                    return state == (1,)
            covered_end = last
            reader = VideoReader(self.source)
            reader.stream.codec_context.thread_count = 1
            reader.output_height = self.output_height
            reader.interpolation = self.interpolation
            frame = reader.seek_raw(last or 0, check)
            count = 0
            size = db.execute('SELECT COALESCE(SUM(LENGTH(jpeg)), 0) FROM frames').fetchone()[0]
            # Between overview and full preparation the JPEGs share the same
            # source and size/quality identity. Reuse their intervals in order.
            reuse = {}
            if track_coverage and db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name = 'overview_progress'").fetchone():
                reuse = dict(db.execute('SELECT time, end FROM frames WHERE LENGTH(jpeg) > 0'))
            encoded = (self._encoded_frames(reader, frame, check, end, reuse=reuse) if reuse
                       else self._encoded_frames(reader, frame, check, end))
            with closing(encoded) as frames:
                for timestamp, frame_end, data in frames:
                    if data is None:
                        if timestamp <= covered_end + 1e-7:
                            covered_end = max(covered_end, frame_end)
                        continue
                    previous = db.execute('SELECT LENGTH(jpeg) FROM frames WHERE time = ?',
                                          (timestamp,)).fetchone()
                    replaced = previous[0] if previous else 0
                    if end is not None and len(data) <= self.MAX_FILE_BYTES:
                        # Keep useful recent regions instead of permanently refusing
                        # new positions once a long movie fills the cache budget.
                        while size - replaced + len(data) > self.MAX_FILE_BYTES:
                            old = db.execute('SELECT time, LENGTH(jpeg) FROM frames '
                                             'WHERE time != ? '
                                             'ORDER BY ABS(time - ?) DESC LIMIT 1',
                                             (timestamp, start)).fetchone()
                            if not old:
                                break
                            db.execute('DELETE FROM frames WHERE time = ?', (old[0],))
                            db.execute('DELETE FROM state')
                            size -= old[1]
                    if size - replaced + len(data) > self.MAX_FILE_BYTES:
                        if end is None:
                            db.execute('DELETE FROM state')
                            db.execute('INSERT INTO state VALUES (-1)')
                        db.commit()
                        if track_coverage:
                            self._coverage = (0.0, covered_end) if covered_end > 0 else ()
                        return False
                    db.execute('INSERT OR REPLACE INTO frames VALUES (?, ?, ?)',
                               (timestamp, frame_end, data))
                    if track_coverage and timestamp <= covered_end + 1e-7:
                        covered_end = max(covered_end, frame_end)
                    count += 1
                    size += len(data) - replaced
                    if count == 1 or count % 8 == 0:
                        db.commit()
                        if track_coverage:
                            self._coverage = (0.0, covered_end) if covered_end > 0 else ()
            if end is None:
                db.execute('DELETE FROM state')
                db.execute('INSERT INTO state VALUES (1)')
            db.commit()
            if track_coverage:
                self._coverage = (0.0, covered_end) if covered_end > 0 else ()
            self.path.touch()
            return True
        except (OSError, sqlite3.Error):
            # Read-only/full/unavailable storage must not make video playback
            # fail or repeatedly restart expensive preparation in this session.
            self.build_disabled = True
            return False
        finally:
            if db is not None:
                db.close()
            if reader:
                reader.close()
