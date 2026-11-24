"""Bounded, frame-timestamped image cache for interactive timeline scrubbing."""
from __future__ import annotations

import bisect
import threading
import time
from collections import OrderedDict

from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import SCRUB_PREVIEW_TOLERANCE, Picture, VideoReader


class ScrubRequest:
    """One moving target and one pending image, even when the GUI is busy."""

    def __init__(self, target):
        self._lock = threading.Lock()
        self._target = self.sampled_target = target
        self.sampled_at = time.monotonic()
        self.retargeted_at: float | None = None
        self.from_source = False
        self.random_access = False
        self.displayed_preview = False
        self._progress = None
        self._notified = False

    @property
    def target(self):
        with self._lock:
            return self._target

    def update(self, target):
        with self._lock:
            self._target = target

    def sample(self):
        with self._lock:
            self.sampled_target = self._target
            self.sampled_at = time.monotonic()
            self.retargeted_at = None
            return self.sampled_target

    def retarget_from_frame(self, start, end, filtered):
        """Finish a slow scan early if its decoded frame can serve newer input."""
        now = time.monotonic()
        if now - self.sampled_at < .055:
            return None
        with self._lock:
            target = self._target
            if target == self.sampled_target:
                return None
            covered = (abs(start - target) <= SCRUB_PREVIEW_TOLERANCE if filtered
                       else start <= target + 1e-7 < end)
            if covered:
                self.sampled_target = target
                self.retargeted_at = now
                return target
        return None

    def publish(self, picture):
        with self._lock:
            if not self._matches_target(picture, self._target):
                return False
            self._progress = (self._target, picture)
            if self._notified:
                return False
            self._notified = True
            return True

    def take_progress(self):
        with self._lock:
            pending, self._progress = self._progress, None
            self._notified = False
            if (pending is not None
                    and self._matches_target(pending[1], self._target)):
                return pending[1]
            return None

    @staticmethod
    def _matches_target(picture, target):
        # Long VFR frames remain exact even far from their starting timestamp.
        return (picture.time <= target < picture.end
                or abs(picture.time - target) <= SCRUB_PREVIEW_TOLERANCE)


class ScrubCache:
    def __init__(self, path: str, budget: int = 192 * 1024 * 1024, output_height: int = 0):
        self.output_height = output_height
        self.path = path
        self.budget = budget
        self._lock = threading.Lock()
        self._frames = OrderedDict()
        self._times = []
        self._bytes = 0

    def get(self, target: float) -> Picture | None:
        return self._memory_get(target)

    def contains_memory(self, target: float, *, allow_approximate: bool = True) -> bool:
        """Check coverage without copying images on the UI thread."""
        with self._lock:
            index = bisect.bisect_right(self._times, target + 1e-7) - 1
            if index < 0:
                return False
            end, _, approximate = self._frames[self._times[index]]
            return target < end - 1e-7 and (allow_approximate or not approximate)

    def _memory_get(self, target: float) -> Picture | None:
        with self._lock:
            index = bisect.bisect_right(self._times, target + 1e-7) - 1
            if index < 0:
                return None
            timestamp = self._times[index]
            end, data, approximate = self._frames[timestamp]
            if target >= end - 1e-7:
                return None
            self._frames.move_to_end(timestamp)
        return Picture(timestamp, end, QImage(data), approximate=approximate)

    def get_nearest(self, target: float, tolerance: float) -> Picture | None:
        """Only the fast-drag cache may use nearby real frames, never exact seeks."""
        with self._lock:
            timestamp = self._nearest_time(target)
            if timestamp is None or abs(timestamp - target) > tolerance:
                return None
            end, data, _ = self._frames[timestamp]
            self._frames.move_to_end(timestamp)
        return Picture(timestamp, end, QImage(data), approximate=True)

    def _nearest_time(self, target):
        index = bisect.bisect_left(self._times, target)
        candidates = self._times[max(0, index - 1):index + 1]
        return min(candidates, key=lambda value: abs(value - target)) if candidates else None

    def contains_near_memory(self, target, tolerance):
        with self._lock:
            timestamp = self._nearest_time(target)
            return timestamp is not None and abs(timestamp - target) <= tolerance

    def put(self, picture: Picture):
        # QImage is implicitly shared: no JPEG encode/decode on the seek path.
        data = QImage(picture.image)
        size = data.sizeInBytes()
        with self._lock:
            previous = self._frames.pop(picture.time, None)
            if previous:
                self._bytes -= previous[1].sizeInBytes()
            else:
                bisect.insort(self._times, picture.time)
            self._frames[picture.time] = (picture.end, data, picture.approximate)
            self._bytes += size
            while self._bytes > self.budget:
                time, (_, old, _) = self._frames.popitem(last=False)
                self._bytes -= old.sizeInBytes()
                self._times.remove(time)

    def warm(self, target: float, check):
        check()
        reader = VideoReader(self.path)
        try:
            reader.output_height = self.output_height
            warmed_bytes = 0
            # Reserve CPU for the main player instead of multiplying AUTO pools.
            reader.stream.thread_type = 'SLICE'
            reader.stream.codec_context.thread_count = 2
            # Make the pointer's frame available first, then fill its neighbors.
            for start, stop in ((target, target + 2.5), (max(0, target - 1.5), target)):
                frame = reader.seek_raw(start, check)
                while frame is not None and reader.timestamp(frame) < stop:
                    check()
                    successor = reader.raw_next(check)
                    timestamp = max(0, reader.timestamp(frame))
                    if not self.contains_memory(timestamp):
                        picture = reader.picture(frame)
                        warmed_bytes += picture.image.sizeInBytes()
                        if warmed_bytes > self.budget // 2:
                            return
                        if successor is not None:
                            picture.end = reader.timestamp(successor)
                        self.put(picture)
                    frame = successor
        finally:
            reader.close()
