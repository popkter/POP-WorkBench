"""FFmpeg decoding shared by playback and the visible filmstrip.

Each worker owns its containers. Requests replace pending work and cancellation
is checked between decoded frames; no media work executes on the GUI thread.
"""
from __future__ import annotations

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import av
import psutil
from av.video.reformatter import VideoReformatter
from PySide6.QtCore import QObject, QSize, Signal
from PySide6.QtGui import QImage, QTransform
from PySide6.QtQuick import QQuickImageProvider


class Cancelled(Exception):
    pass


# Progress is allowed to differ slightly from the pointer during decoding, but
# a keyframe several seconds away must never masquerade as a current preview.
SCRUB_PREVIEW_TOLERANCE = 0.12


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
            finally:
                # While idle, the thread must not retain a previous video's
                # cache through its task closure or keep its last decoded frame.
                task = result = None

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
    # A nearby source frame sampled in time, with unchanged image quality.
    approximate: bool = False
    source_frame: av.VideoFrame | None = field(default=None, compare=False, repr=False)


class VideoPictureConverter:
    """Scale decoded frames without owning or advancing their decoder."""

    def __init__(self, origin, fps, rotation, output_height=0, interpolation=None):
        self.origin = origin
        self.fps = fps
        self.rotation = rotation
        self.output_height = output_height
        self.interpolation = interpolation
        self._reformatter = VideoReformatter()
        self._reformat_key = None

    def timestamp(self, frame) -> float:
        if frame.pts is None:
            raise ValueError("视频帧缺少时间戳，无法准确定位")
        return float(frame.pts * frame.time_base) - self.origin

    def picture(self, frame, width=None) -> Picture:
        if width is None:
            scale = (min(1, self.output_height / min(frame.width, frame.height))
                     if self.output_height else 1)
            width = round(frame.width * scale)
        height = max(2, round(frame.height * min(1, width / frame.width)))
        width = max(2, round(frame.width * min(1, width / frame.width)))
        # Reuse only identical conversions. Reconfiguring a cached swscale
        # context across format/colour boundaries can retain different pixels.
        key = (frame.width, frame.height, frame.format.name, frame.colorspace,
               frame.color_range, width, height, self.interpolation)
        if self._reformat_key is not None and key != self._reformat_key:
            self._reformatter = VideoReformatter()
        self._reformat_key = key
        rgb = self._reformatter.reformat(frame, width=width, height=height, format="rgb24",
                                        interpolation=self.interpolation)
        # Borrow the plane only until copy() returns. Avoid a second full-frame
        # Python bytes allocation (about 24 MB per 4K frame).
        image = QImage(memoryview(rgb.planes[0]), width, height, rgb.planes[0].line_size,
                       QImage.Format.Format_RGB888).copy()
        rotation = -getattr(frame, "rotation", 0) or self.rotation
        if rotation:
            image = image.transformed(QTransform().rotate(rotation))
        time = max(0.0, self.timestamp(frame))
        duration = float((getattr(frame, "duration", 0) or 0) * frame.time_base)
        return Picture(time, time + (duration or 1 / self.fps), image)


class VideoReader(VideoPictureConverter):
    def __init__(self, path: str):
        self.container = av.open(path)
        try:
            if not self.container.streams.video:
                raise ValueError("此文件没有可播放的视频轨道")
            self.stream = self.container.streams.video[0]
            # Bound CPU use across playback, timeline and cache workers, and
            # avoid FRAME threading's extra startup/seek buffering latency.
            self.stream.thread_type = "SLICE"
            self.stream.codec_context.thread_count = 2
            origin = float((self.stream.start_time or 0) * self.stream.time_base)
            fps = float(self.stream.average_rate or 30)
            fps = fps if 0 < fps < 1000 else 30
            duration = self.stream.duration
            self.duration = (float(duration * self.stream.time_base) if duration is not None
                             else float(self.container.duration or 0) / av.time_base)
            if self.duration <= 0:
                raise ValueError("无法读取视频时长，请使用完整的本地视频文件")
            super().__init__(origin, fps, float(self.stream.metadata.get("rotate", 0)))
            self._frames = iter(self.container.decode(self.stream))
            self._pending = None
            self._cursor_frame = None
            self._fast_cursor = False
            self._sampling_fast = False
            self._first_gop = None
            self._seek_history = OrderedDict()
            self._seek_history_bytes = 0
            self._seek_history_limit = 0
            self._keep_seek_history = None
            self._scrub_retarget = None
            self._retargeted_scrub_position = None
        except Exception:
            self.container.close()
            raise

    def close(self):
        try:
            self.container.close()
        finally:
            self.clear_seek_history()
            self._reformatter = None
            self._reformat_key = None

    def info(self) -> dict:
        return {"duration": self.duration, "fps": self.fps,
                "width": self.stream.width, "height": self.stream.height,
                "audio": bool(self.container.streams.audio), "origin": self.origin}

    def raw_next(self, check):
        check()
        if self._fast_cursor and not self._sampling_fast:
            # The next exact frame may be a B frame omitted by fast sampling.
            # Restore the last displayed PTS before advancing normally.
            position = self.timestamp(self._cursor_frame)
            self._discard_fast_cursor()
            self.seek_raw(position, check)
        if self._pending is not None:
            frame, self._pending = self._pending, None
        else:
            frame = next(self._frames, None)
        if frame is not None:
            self._cursor_frame = frame
        return frame

    def _discard_fast_cursor(self):
        self._fast_cursor = False
        self._pending = self._cursor_frame = None
        self._frames = iter(())

    def seek_raw(self, target: float, check):
        """Return the frame covering target, retaining its successor for playback."""
        self._retargeted_scrub_position = None
        if self._fast_cursor and not self._sampling_fast:
            self._discard_fast_cursor()
        target = max(0.0, target)
        # Reuse the current decode cursor for nearby forward movement. Seeking
        # each pointer update would repeatedly decode the same GOP.
        selected = self._cursor_frame
        if not self._can_reuse_forward(target):
            self.container.seek(int((target + self.origin) / self.stream.time_base),
                                stream=self.stream, backward=True, any_frame=False)
            self._frames = iter(self.container.decode(self.stream))
            self._pending = None
            self._cursor_frame = selected = None
        remember = self._seek_history_limit and not self._sampling_fast
        retarget = self._scrub_retarget
        start = (self.timestamp(selected)
                 if (remember or retarget) and selected is not None else -1)
        while True:
            frame = self.raw_next(check)
            if frame is None:
                return selected
            check()
            timestamp = self.timestamp(frame)
            if (remember and 0 <= start < timestamp and 0 <= target - start <= .8
                    and self._keep_seek_history()):
                self._remember_seek_frame(start, timestamp, selected)
            newer = (retarget(start, timestamp, self._sampling_fast)
                     if retarget is not None and 0 <= start < timestamp else None)
            if (selected is not None
                    and (timestamp > target + 1e-7 or newer is not None)):
                self._retargeted_scrub_position = newer
                self._pending = frame
                self._cursor_frame = selected
                return selected
            selected = frame
            start = timestamp
            if timestamp > target + 1e-7:
                return frame

    def seek(self, target: float, check, width=None) -> Picture | None:
        frame = self.seek_raw(target, check)
        if frame is None:
            return None
        picture = self.picture(frame, width)
        if self._pending is not None:
            picture.end = self.timestamp(self._pending)
        return picture

    def seek_for_scrub(self, target, check, *, sample, history_bytes, keep_history, retarget=None):
        """Reuse or remember nearby exact source frames during a scrub."""
        picture = self._recent_seek_picture(target, check)
        if picture is not None:
            return picture
        self._seek_history_limit = history_bytes
        self._keep_seek_history = keep_history
        self._scrub_retarget = retarget
        try:
            seek = self.seek_fast_preview if sample else self.seek
            return seek(target, check)
        finally:
            self._seek_history_limit = 0
            self._keep_seek_history = None
            self._scrub_retarget = self._retargeted_scrub_position = None

    def _remember_seek_frame(self, start, end, frame):
        size = sum(plane.buffer_size for plane in frame.planes)
        if size > self._seek_history_limit:
            return
        previous = self._seek_history.pop(start, None)
        if previous is not None:
            self._seek_history_bytes -= previous[2]
        self._seek_history[start] = (end, frame, size)
        self._seek_history_bytes += size
        while self._seek_history_bytes > self._seek_history_limit:
            _, (_, _, size) = self._seek_history.popitem(last=False)
            self._seek_history_bytes -= size

    def take_recent_seek_picture(self, target, check):
        """Use a verified source interval without moving the decode cursor."""
        try:
            return self._recent_seek_picture(target, check)
        finally:
            self.clear_seek_history()

    def _recent_seek_picture(self, target, check):
        for start, (end, frame, _) in reversed(self._seek_history.items()):
            if start <= target + 1e-7 < end:
                check()
                picture = self.picture(frame)
                picture.end = end
                return picture
        return None

    def clear_seek_history(self):
        self._seek_history.clear()
        self._seek_history_bytes = 0

    def _can_reuse_forward(self, target: float) -> bool:
        if self._cursor_frame is None:
            return False
        current = self.timestamp(self._cursor_frame)
        if 0 <= target - current <= 1:
            return True
        return (self._first_gop is not None
                and self._first_gop[0] <= current <= target < self._first_gop[1])

    def can_seek_exact_forward(self, target: float) -> bool:
        # The controller uses this as a fast-path hint. A multi-second forward
        # walk may still need a background cache even when it can reuse a GOP.
        return (not self._fast_cursor and self._cursor_frame is not None
                and 0 <= target - self.timestamp(self._cursor_frame) <= 1)

    def seek_fast_preview(self, target: float, check) -> Picture | None:
        """Sample a nearby reference frame without changing its decoded pixels.

        Non-reference frames may be omitted only during fast pointer motion.
        Retain the filtered cursor for subsequent fast requests. Exact requests
        restart decoding so the skipped B frames remain available.
        """
        codec = self.stream.codec_context
        if codec.name not in {"h264", "hevc"}:
            return self.seek(target, check)
        target = max(0.0, target)
        check()
        if not self._fast_cursor and self._can_reuse_forward(target):
            return self.seek(target, check)
        original_skip = codec.skip_frame
        try:
            codec.skip_frame = "NONREF"
            self._sampling_fast = True
            if not self._fast_cursor:
                self._discard_fast_cursor()
            self._fast_cursor = True
            frame = self.seek_raw(target, check)
            if self._retargeted_scrub_position is not None:
                target = self._retargeted_scrub_position
            if frame is None:
                self._discard_fast_cursor()
                return None
            if (self._pending is not None
                    and abs(self.timestamp(self._pending) - target)
                    < abs(self.timestamp(frame) - target)):
                frame = self._pending
                self._pending = None
                self._cursor_frame = frame
            timestamp = self.timestamp(frame)
            duration = float((getattr(frame, "duration", 0) or 0) * frame.time_base)
            covers_target = duration > 0 and timestamp <= target < timestamp + duration
            if (abs(timestamp - target) > SCRUB_PREVIEW_TOLERANCE
                    and not covers_target):
                # A filtered successor cannot establish coverage of the skipped
                # interval. Decode normally when no sufficiently close frame exists.
                codec.skip_frame = "DEFAULT"
                self._sampling_fast = False
                self._discard_fast_cursor()
                return self.seek(target, check)
            check()
            picture = self.picture(frame)
            # Do not stretch a reference frame across omitted non-reference frames.
            picture.end = picture.time + max(0.0, duration)
            picture.approximate = True
            check()
            return picture
        except Cancelled:
            # A cache hit can replace a seek while it is still walking a long
            # GOP. Keep its filtered cursor for the next forward fast request;
            # exact seeks and playback still restore the unfiltered cursor.
            if self._fast_cursor and (self._first_gop is None or self._cursor_frame is None):
                self._discard_fast_cursor()
            raise
        except Exception:
            if self._fast_cursor:
                self._discard_fast_cursor()
            raise
        finally:
            codec.skip_frame = original_skip
            self._sampling_fast = False

    def next(self, check) -> Picture | None:
        frame = self.raw_next(check)
        return self.picture(frame) if frame is not None else None

    def next_for_time(self, target, check, *, retain_source=False) -> Picture | None:
        """Skip expired playback frames before RGB conversion/upload.

        Use a clock snapshot: chasing a moving audio clock can starve output on
        a machine decoding slower than real time. Retain the successor for VFR.
        """
        frame = self.raw_next(check)
        if frame is None:
            return None
        successor = None
        if self.timestamp(frame) < target:
            while True:
                successor = self.raw_next(check)
                if successor is None or self.timestamp(successor) > target:
                    self._pending = successor
                    self._cursor_frame = frame
                    break
                frame = successor
        picture = self.picture(frame)
        if successor is not None:
            picture.end = self.timestamp(successor)
        if retain_source and 0 < self.output_height < min(frame.width, frame.height):
            picture.source_frame = frame
        return picture

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
        overview_threads = self._configure_interactive_threads(self.reader, check)
        picture = self.reader.seek(min(position, self.reader.duration - 0.000001), check)
        if picture is None:
            raise ValueError("视频中没有可解码的画面")
        info = self.reader.info()
        if overview_threads:
            info["expensive_random_seek"] = True
            info["overview_decode_threads"] = overview_threads
        codec = self.reader.stream.codec_context
        if overview_threads and self.reader._first_gop is not None:
            budget, divisor = 240 * 1024**2, 16
        elif (codec.name == "h264" and codec.has_b_frames
              and min(info["width"], info["height"]) >= 1440):
            # Keep the exact intervals just behind a paused drag's decoder.
            # A short backward release can then avoid replaying an entire GOP.
            budget, divisor = 48 * 1024**2, 48
        else:
            return info, picture
        try:
            info["seek_history_bytes"] = min(budget, psutil.virtual_memory().available // divisor)
        except (OSError, psutil.Error):
            pass
        return info, picture

    @staticmethod
    def _configure_interactive_threads(reader, check) -> int:
        """Configure the foreground reader and return the sparse overview budget."""
        # Large P-frame screen recordings can require decoding hundreds of
        # frames per seek. Parallelize only the interactive reader, before its
        # codec opens; background readers retain their existing CPU limits.
        stream = reader.stream
        codec = stream.codec_context
        if (codec.name != "h264" or codec.has_b_frames
                or min(stream.width, stream.height) < 1440):
            return 0
        try:
            process = psutil.Process()
            available = (len(process.cpu_affinity()) if hasattr(process, "cpu_affinity")
                         else os.cpu_count() or 1)
        except (psutil.Error, OSError, NotImplementedError):
            return 0  # Keep the conservative default when the CPU budget is unknown.
        threads = min(4, available // 2)
        if threads >= 2 and PlaybackDecoder._has_long_gop(reader, check):
            stream.thread_type = "FRAME"
            codec.thread_count = threads
            # Leave room for foreground decoding, JPEG encoding and rendering.
            return 4 if available >= 12 else 2 if available >= 8 else 1
        return 0

    @staticmethod
    def _has_long_gop(reader, check, *, indexed=False):
        """Detect a long first GOP and record any safely inspected prefix."""
        stream = reader.stream
        long_gop = False
        reader._first_gop = None
        try:
            packets = iter(reader.container.demux(stream))
            first_keyframe = None
            previous_timestamp = None
            ordered_pts = True
            size = 0
            for _ in range(120):
                check()
                packet = next(packets, None)
                if packet is None:
                    break
                size += packet.size
                if size > 8 * 1024 * 1024:
                    break
                pts = packet.pts if packet.pts is not None else packet.dts
                if packet.pts is None:
                    ordered_pts = False
                if pts is None:
                    continue
                timestamp = float(pts * (packet.time_base or stream.time_base))
                if previous_timestamp is not None and timestamp <= previous_timestamp:
                    ordered_pts = False
                previous_timestamp = timestamp
                if first_keyframe is None:
                    if packet.is_keyframe:
                        first_keyframe = timestamp
                    continue
                elapsed = timestamp - first_keyframe
                if packet.is_keyframe or elapsed >= 1:
                    long_gop = elapsed > 1 if packet.is_keyframe else True
                    if long_gop and ordered_pts:
                        end = timestamp if packet.is_keyframe else PlaybackDecoder._first_gop_end(
                            packets, timestamp, size, stream.time_base, check)
                        if end is not None:
                            if indexed and not packet.is_keyframe:
                                end = PlaybackDecoder._indexed_gop_end(
                                    reader, first_keyframe, end, check)
                            origin = float((stream.start_time or 0) * stream.time_base)
                            reader._first_gop = (first_keyframe - origin, end - origin)
                    break
        except Cancelled:
            raise
        except Exception:
            # Optional packet evidence must never prevent ordinary playback.
            long_gop = False
            reader._first_gop = None
        finally:
            reader._discard_fast_cursor()
            try:
                reader.container.seek(stream.start_time or 0, stream=stream,
                                      backward=True, any_frame=False)
                reader._frames = iter(reader.container.decode(stream))
            except Exception:
                long_gop = False
                reader._first_gop = None
        return long_gop

    @staticmethod
    def _first_gop_end(packets, end, size, time_base, check):
        # Extra compressed lookahead is optional. A partial index is useful,
        # and neither file size nor GOP duration can grow the initial work.
        deadline = time.monotonic() + .012
        for _ in range(720):
            if time.monotonic() >= deadline:
                break
            check()
            try:
                packet = next(packets, None)
            except Exception:
                return None
            if packet is None:
                break
            if packet.pts is None:
                return None if packet.size else end
            size += packet.size
            timestamp = float(packet.pts * (packet.time_base or time_base))
            if timestamp <= end:
                return None
            if size > 24 * 1024 * 1024:
                break
            end = timestamp
            if packet.is_keyframe:
                break
        return end

    @staticmethod
    def _indexed_gop_end(reader, start, inspected_end, check):
        """Extend an ordered MP4 GOP using the demuxer's verified seek index."""
        container, stream = reader.container, reader.stream
        if not stream.frames or "mp4" not in container.format.name.split(","):
            return inspected_end
        first_pts = round(start / stream.time_base)
        try:
            check()
            container.seek(first_pts + 1, stream=stream, backward=False, any_frame=False)
            boundary = next(container.demux(stream), None)
            if (boundary is None or not boundary.is_keyframe or boundary.pts is None
                    or boundary.pts != boundary.dts):
                return inspected_end
            end = float(boundary.pts * stream.time_base)
            if end <= inspected_end:
                return inspected_end
            check()
            container.seek(boundary.pts - 1, stream=stream, backward=True, any_frame=False)
            anchor = next(container.demux(stream), None)
            if (anchor is not None and anchor.is_keyframe
                    and anchor.pts == anchor.dts == first_pts):
                return end
        except (OSError, ValueError):
            pass
        return inspected_end

    def close(self):
        if self.reader:
            self.reader.close()
            self.reader = None


def filmstrip(path: str, start: float, end: float, pixels_per_second: float, check,
              *, reuse_gop: bool = False):
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
            if reuse_gop:
                PlaybackDecoder._has_long_gop(reader, check, indexed=True)
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
