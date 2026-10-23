"""FFmpeg decoding shared by playback and the visible filmstrip.

Each worker owns its containers. Requests replace pending work and cancellation
is checked between decoded frames; no media work executes on the GUI thread.
"""
from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import av
from PySide6.QtCore import QObject, QSize, Signal
from PySide6.QtGui import QImage, QTransform
from PySide6.QtQuick import QQuickImageProvider


class Cancelled(Exception):
    pass


class LatestWorker(QObject):
    completed = Signal(int, object)
    failed = Signal(int, str)

    def __init__(self, name: str):
        super().__init__()
        self._condition = threading.Condition()
        self._serial = 0
        self._job = None
        self._closed = False
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()

    def submit(self, task: Callable) -> int:
        with self._condition:
            self._serial += 1
            self._job = (self._serial, task)
            self._condition.notify()
            return self._serial

    def cancel(self) -> None:
        with self._condition:
            self._serial += 1
            self._job = None
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._job is not None or self._closed)
                if self._closed:
                    return
                serial, task = self._job
                self._job = None

            def check(serial=serial):
                if self._closed or serial != self._serial:
                    raise Cancelled()

            try:
                result = task(check)
                check()
                self.completed.emit(serial, result)
            except Cancelled:
                pass
            except Exception as exc:
                if not self._closed and serial == self._serial:
                    self.failed.emit(serial, str(exc))

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._job = None
            self._condition.notify_all()
        self._thread.join(timeout=3)


class VideoImages(QQuickImageProvider):
    """Copies are implicitly shared by Qt; evict by bytes, not frame count."""

    def __init__(self):
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._lock = threading.Lock()
        self._images: OrderedDict[str, QImage] = OrderedDict()
        self._bytes = 0
        self._sequence = 0
        self._live = QImage()

    def put(self, image: QImage, live: bool = False) -> str:
        with self._lock:
            self._sequence += 1
            key = str(self._sequence)
            if live:
                self._live = image
                return "image://video/live/" + key
            self._images[key] = image
            self._bytes += image.sizeInBytes()
            while self._bytes > 80 * 1024 * 1024 and len(self._images) > 1:
                _, old = self._images.popitem(last=False)
                self._bytes -= old.sizeInBytes()
            return "image://video/" + key

    def clear(self) -> None:
        with self._lock:
            self._images.clear()
            self._bytes = 0
            self._live = QImage()

    def requestImage(self, identifier: str, size: QSize, requestedSize: QSize) -> QImage:
        with self._lock:
            image = (self._live if identifier.startswith("live/")
                     else self._images.get(identifier, QImage()))
            if identifier in self._images:
                self._images.move_to_end(identifier)
            size.setWidth(image.width())
            size.setHeight(image.height())
            return image


@dataclass
class Picture:
    time: float
    end: float
    image: QImage


class VideoReader:
    def __init__(self, path: str):
        self.container = av.open(path)
        try:
            if not self.container.streams.video:
                raise ValueError("此文件没有可播放的视频轨道")
            self.stream = self.container.streams.video[0]
            self.stream.thread_type = "AUTO"
            self.origin = float((self.stream.start_time or 0) * self.stream.time_base)
            self.fps = float(self.stream.average_rate or 30)
            self.fps = self.fps if 0 < self.fps < 1000 else 30
            duration = self.stream.duration
            self.duration = (float(duration * self.stream.time_base) if duration is not None
                             else float(self.container.duration or 0) / av.time_base)
            if self.duration <= 0:
                raise ValueError("无法读取视频时长，请使用完整的本地视频文件")
            self.rotation = float(self.stream.metadata.get("rotate", 0))
            self._frames = iter(self.container.decode(self.stream))
            self._pending = None
        except Exception:
            self.container.close()
            raise

    def close(self):
        self.container.close()

    def info(self) -> dict:
        return {"duration": self.duration, "fps": self.fps,
                "width": self.stream.width, "height": self.stream.height,
                "audio": bool(self.container.streams.audio), "origin": self.origin}

    def timestamp(self, frame) -> float:
        if frame.pts is None:
            raise ValueError("视频帧缺少时间戳，无法准确定位")
        return float(frame.pts * frame.time_base) - self.origin

    def raw_next(self, check):
        check()
        if self._pending is not None:
            frame, self._pending = self._pending, None
            return frame
        return next(self._frames, None)

    def picture(self, frame, width=1280) -> Picture:
        height = max(2, round(frame.height * min(1, width / frame.width)))
        width = max(2, round(frame.width * min(1, width / frame.width)))
        rgb = frame.reformat(width=width, height=height, format="rgb24")
        image = QImage(bytes(rgb.planes[0]), width, height, rgb.planes[0].line_size,
                       QImage.Format.Format_RGB888).copy()
        rotation = -getattr(frame, "rotation", 0) or self.rotation
        if rotation:
            image = image.transformed(QTransform().rotate(rotation))
        time = max(0.0, self.timestamp(frame))
        duration = float((getattr(frame, "duration", 0) or 0) * frame.time_base)
        return Picture(time, time + (duration or 1 / self.fps), image)

    def seek_raw(self, target: float, check):
        """Return the frame covering target, retaining its successor for playback."""
        target = max(0.0, target)
        self.container.seek(int((target + self.origin) / self.stream.time_base),
                            stream=self.stream, backward=True, any_frame=False)
        self._frames = iter(self.container.decode(self.stream))
        self._pending = None
        selected = None
        for frame in self._frames:
            check()
            if self.timestamp(frame) > target + 1e-7 and selected is not None:
                self._pending = frame
                return selected
            selected = frame
            if self.timestamp(frame) > target + 1e-7:
                return frame
        return selected

    def seek(self, target: float, check) -> Picture | None:
        frame = self.seek_raw(target, check)
        return self.picture(frame) if frame is not None else None

    def next(self, check) -> Picture | None:
        frame = self.raw_next(check)
        return self.picture(frame) if frame is not None else None

    def probe_end(self, check):
        # Some VFR containers under-report duration. Decode the last GOP, not the
        # entire file, so the final presentation frames remain reachable.
        frame = self.seek_raw(max(0, self.duration - 0.001), check)
        while frame is not None:
            check()
            timestamp = self.timestamp(frame)
            length = float((getattr(frame, "duration", 0) or 0) * frame.time_base)
            self.duration = max(self.duration, timestamp + (length or 1 / self.fps))
            frame = self.raw_next(check)

    def previous(self, target: float, check) -> Picture | None:
        # Start earlier and decode in presentation order, including B frames/VFR.
        distance = max(0.25, 3 / self.fps)
        while True:
            start = max(0, target - distance)
            frame = self.seek_raw(start, check)
            previous = None
            while frame is not None and self.timestamp(frame) < target - 1e-7:
                previous = frame
                frame = self.raw_next(check)
            if previous is not None:
                self._pending = frame
                return self.picture(previous)
            if start == 0:
                return self.seek(0, check)
            distance *= 2


class PlaybackDecoder:
    def __init__(self):
        self.reader: VideoReader | None = None

    def open(self, path: str, position: float, check):
        self.close()
        self.reader = VideoReader(path)
        self.reader.probe_end(check)
        picture = self.reader.seek(min(position, self.reader.duration - 0.000001), check)
        if picture is None:
            raise ValueError("视频中没有可解码的画面")
        return self.reader.info(), picture

    def close(self):
        if self.reader:
            self.reader.close()
            self.reader = None


def filmstrip(path: str, start: float, end: float, pixels_per_second: float, check):
    reader = VideoReader(path)
    try:
        pictures = []
        detailed = pixels_per_second / reader.fps >= 64
        if detailed:
            frame = reader.seek_raw(start, check)
            while frame is not None and reader.timestamp(frame) < end and len(pictures) < 200:
                check()
                pictures.append(reader.picture(frame, 200))
                frame = reader.raw_next(check)
            for left, right in zip(pictures, pictures[1:], strict=False):
                left.end = right.time
            if pictures and frame is not None:
                pictures[-1].end = reader.timestamp(frame)
        else:
            interval = max(0.001, 112 / pixels_per_second)
            target = start
            while target < end and len(pictures) < 200:
                check()
                frame = reader.seek_raw(target, check)
                if frame is None:
                    break
                picture = reader.picture(frame, 200)
                # Overview cells occupy sampling intervals, selection uses actual PTS.
                pictures.append((target, min(end, target + interval), picture))
                target += interval
        return detailed, pictures
    finally:
        reader.close()


VIDEO_SUFFIXES = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".ts", ".mts"}


def local_video_paths(values: list[str]) -> list[str]:
    from PySide6.QtCore import QUrl
    result = []
    for value in values:
        url = QUrl(value)
        path = Path(url.toLocalFile() if url.isLocalFile() else value)
        if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES:
            resolved = str(path.resolve())
            if resolved not in result:
                result.append(resolved)
    return result
