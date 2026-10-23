"""Bounded, frame-timestamped JPEG cache for interactive timeline scrubbing."""
from __future__ import annotations

import bisect
import threading
from collections import OrderedDict

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QImage

from poptools.infrastructure.video_media import Picture, VideoReader


class ScrubCache:
    def __init__(self, path: str, budget: int = 48 * 1024 * 1024):
        self.path = path
        self.budget = budget
        self._lock = threading.Lock()
        self._frames = OrderedDict()
        self._times = []
        self._bytes = 0
        self.proxy = None

    def get(self, target: float) -> Picture | None:
        picture = self._memory_get(target)
        if picture is None and self.proxy is not None:
            return self.proxy.get(target)
        return picture

    def contains_memory(self, target: float) -> bool:
        """Check coverage without decoding JPEG or touching disk on the UI thread."""
        with self._lock:
            index = bisect.bisect_right(self._times, target + 1e-7) - 1
            return index >= 0 and target < self._frames[self._times[index]][0] - 1e-7

    def _memory_get(self, target: float) -> Picture | None:
        with self._lock:
            index = bisect.bisect_right(self._times, target + 1e-7) - 1
            if index < 0:
                return None
            timestamp = self._times[index]
            end, data = self._frames[timestamp]
            if target >= end - 1e-7:
                return None
            self._frames.move_to_end(timestamp)
        image = QImage.fromData(data, 'JPEG')
        return None if image.isNull() else Picture(timestamp, end, image)

    def put(self, picture: Picture):
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not picture.image.save(buffer, 'JPEG', 80):
            return
        data = bytes(buffer.data())
        if len(data) > self.budget:
            return
        with self._lock:
            previous = self._frames.pop(picture.time, None)
            if previous:
                self._bytes -= len(previous[1])
            else:
                bisect.insort(self._times, picture.time)
            self._frames[picture.time] = (picture.end, data)
            self._bytes += len(data)
            while self._bytes > self.budget:
                time, (_, old) = self._frames.popitem(last=False)
                self._bytes -= len(old)
                self._times.remove(time)

    def warm(self, target: float, check):
        check()
        if self.proxy is not None and self.proxy.on_demand:
            self.proxy.warm(target, check)
            return
        if self.proxy is not None and self.proxy.get(target) is not None:
            return
        reader = VideoReader(self.path)
        try:
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
                    if self.get(timestamp) is None:
                        width = round(960 * frame.width / max(frame.width, frame.height))
                        picture = reader.picture(frame, width)
                        if successor is not None:
                            picture.end = reader.timestamp(successor)
                        self.put(picture)
                    frame = successor
        finally:
            reader.close()
