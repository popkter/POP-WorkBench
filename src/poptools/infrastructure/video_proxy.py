"""Progressive on-disk, intra-frame previews indexed by source timestamps."""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Picture, VideoReader


class ScrubProxy:
    MAX_FILE_BYTES = 512 * 1024 * 1024
    MAX_CACHE_BYTES = 2 * 1024 * 1024 * 1024

    def __init__(self, source: str, directory: Path, on_demand=False):
        self.source = source
        self.on_demand = on_demand
        stat = Path(source).stat()
        identity = f'v1:{Path(source).resolve()}:{stat.st_size}:{stat.st_mtime_ns}'
        key = hashlib.sha256(identity.encode()).hexdigest()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = (directory / f'video-proxy-v1-{key}.sqlite').resolve()
        self._prune()

    def _prune(self):
        files = sorted(self.path.parent.glob('video-proxy-v1-*.sqlite'),
                       key=lambda path: path.stat().st_mtime)
        total = sum(path.stat().st_size for path in files)
        for path in files:
            if total <= self.MAX_CACHE_BYTES - self.MAX_FILE_BYTES:
                break
            if path == self.path:
                continue
            try:
                size = path.stat().st_size
                path.unlink()
                total -= size
            except OSError:
                pass  # Another player may still have the cache open.

    def get(self, target: float) -> Picture | None:
        if not self.path.exists():
            return None
        try:
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                                         timeout=0.01)) as db:
                row = db.execute('SELECT time, end, jpeg FROM frames WHERE time <= ? '
                                 'ORDER BY time DESC LIMIT 1', (target + 1e-7,)).fetchone()
            if not row or target >= row[1] - 1e-7:
                return None
            image = QImage.fromData(row[2], 'JPEG')
            return None if image.isNull() else Picture(row[0], row[1], image)
        except (sqlite3.Error, OSError):
            return None

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

    def warm(self, target, check):
        # Commit the pointed-to neighborhood before doing the backward portion.
        for start, end in ((target, target + 2.5), (max(0, target - 1.5), target)):
            check()
            if start < end and not self.covers(start, end):
                self.build(check, start=start, end=end)

    def build(self, check, start=0, end=None):
        db = sqlite3.connect(self.path, timeout=0.1)
        reader = None
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS frames '
                       '(time REAL PRIMARY KEY, end REAL NOT NULL, jpeg BLOB NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS state (complete INTEGER)')
            db.commit()
            if end is None and db.execute('SELECT complete FROM state').fetchone() == (1,):
                return True
            last = start
            if end is None:
                # A file may already contain disjoint on-demand neighborhoods.
                # Resume only the contiguous prefix, never skip gaps using MAX(end).
                for left, right in db.execute('SELECT time, end FROM frames ORDER BY time'):
                    if left > last + 1e-7:
                        break
                    last = max(last, right)
            reader = VideoReader(self.source)
            reader.stream.codec_context.thread_count = 1
            frame = reader.seek_raw(last or 0, check)
            count = 0
            size = db.execute('SELECT COALESCE(SUM(LENGTH(jpeg)), 0) FROM frames').fetchone()[0]
            while frame is not None and (end is None or reader.timestamp(frame) < end):
                check()
                successor = reader.raw_next(check)
                width = round(960 * frame.width / max(frame.width, frame.height))
                picture = reader.picture(frame, width)
                if successor is not None:
                    picture.end = reader.timestamp(successor)
                buffer = QBuffer()
                buffer.open(QIODevice.OpenModeFlag.WriteOnly)
                if not picture.image.save(buffer, 'JPEG', 80):
                    raise ValueError('JPEG preview encoding is unavailable')
                data = bytes(buffer.data())
                previous = db.execute('SELECT LENGTH(jpeg) FROM frames WHERE time = ?',
                                      (picture.time,)).fetchone()
                replaced = previous[0] if previous else 0
                if end is not None and len(data) <= self.MAX_FILE_BYTES:
                    # Keep useful recent regions instead of permanently refusing
                    # new positions once a long movie fills the cache budget.
                    while size - replaced + len(data) > self.MAX_FILE_BYTES:
                        old = db.execute('SELECT time, LENGTH(jpeg) FROM frames WHERE time != ? '
                                         'ORDER BY ABS(time - ?) DESC LIMIT 1',
                                         (picture.time, start)).fetchone()
                        if not old:
                            break
                        db.execute('DELETE FROM frames WHERE time = ?', (old[0],))
                        db.execute('DELETE FROM state')
                        size -= old[1]
                if size - replaced + len(data) > self.MAX_FILE_BYTES:
                    db.commit()
                    return False
                db.execute('INSERT OR REPLACE INTO frames VALUES (?, ?, ?)',
                           (picture.time, picture.end, data))
                count += 1
                size += len(data) - replaced
                if count == 1 or count % 8 == 0:
                    db.commit()
                frame = successor
            if end is None:
                db.execute('DELETE FROM state')
                db.execute('INSERT INTO state VALUES (1)')
            db.commit()
            self.path.touch()
            return True
        finally:
            db.close()
            if reader:
                reader.close()
