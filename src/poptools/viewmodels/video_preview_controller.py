from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtWidgets import QFileDialog

from poptools.infrastructure.video_audio import AudioPlayback
from poptools.infrastructure.video_media import (
    LatestWorker,
    Picture,
    PlaybackDecoder,
    VideoImages,
    VideoReader,
    filmstrip,
    local_video_paths,
)
from poptools.infrastructure.video_proxy import ScrubProxy
from poptools.infrastructure.video_scrub import ScrubCache


class VideoPreviewController(QObject):
    changed = Signal()
    positionChanged = Signal()
    frameChanged = Signal()
    playlistChanged = Signal()
    thumbnailsChanged = Signal()
    zoomRequested = Signal(float)
    fitRequested = Signal()
    previewChanged = Signal()

    def __init__(self, data_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.images = VideoImages()
        self._decoder = PlaybackDecoder()
        self._worker = LatestWorker("video-playback")
        self._cache_worker = LatestWorker("video-scrub-cache")
        self._proxy_worker = LatestWorker("video-scrub-proxy")
        self._proxy_worker.completed.connect(self._proxy_finished)
        self._proxy_worker.failed.connect(self._proxy_finished)
        self._proxy_token = -1
        self._proxy_busy = False
        self._proxy_directory = data_dir / "video-preview-cache" if data_dir else None
        self._scrub_cache = None
        self._cache_center = -10.0
        self._metadata_worker = LatestWorker("video-duration")
        self._metadata_worker.completed.connect(self._duration_received)
        self._metadata_token = -1
        self._thumb_worker = LatestWorker("video-filmstrip")
        self._preview_worker = LatestWorker("video-hover")
        self._preview_worker.completed.connect(self._preview_received)
        self._preview_worker.failed.connect(self._preview_failed)
        self._preview_token = -1
        self._preview_reader = None
        self._preview_key = None
        self._generation = 0
        self._preview_source = ""
        self._preview_time = self._preview_target = 0.0
        self._preview_busy = False
        self._worker.completed.connect(self._received)
        self._worker.failed.connect(self._failed)
        self._thumb_worker.completed.connect(self._thumbnails_received)
        self._thumb_worker.failed.connect(self._thumbnails_failed)
        self._audio = AudioPlayback(self)
        self._token = self._thumb_token = -1
        self._kind = ""
        self._playlist: list[dict] = []
        self._index = -1
        self._info: dict = {}
        self._position = 0.0
        self._source = ""
        self._message = ""
        self._busy = self._playing = self._closed = False
        self._list_visible = False
        self._rate = 1.0
        self._volume = 0.8
        self._resolution = 0
        self._thumbnails: list[dict] = []
        self._detailed = False
        self._thumb_busy = False
        self._next: Picture | None = None
        self._decode_pending = self._eof = False
        self._resume_after_seek = False
        self._scrub_active = False
        self._scrub_resume = False
        self._queued_scrub = None
        self._clock_start = self._clock_position = 0.0
        self._last_clock = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(8)
        self._timer.timeout.connect(self._tick)
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save)
        self._session = data_dir / "video-preview.json" if data_dir else None
        self._restore()

    @Property("QVariantList", notify=playlistChanged)
    def playlist(self):
        return [dict(item, selected=i == self._index) for i, item in enumerate(self._playlist)]

    @Property("QVariantList", notify=thumbnailsChanged)
    def thumbnails(self):
        return self._thumbnails

    @Property(bool, notify=changed)
    def playing(self):
        return self._playing

    @Property(bool, notify=changed)
    def busy(self):
        return self._busy

    @Property(bool, notify=thumbnailsChanged)
    def thumbnailBusy(self):
        return self._thumb_busy

    @Property(bool, notify=thumbnailsChanged)
    def detailed(self):
        return self._detailed

    @Property(bool, notify=changed)
    def loaded(self):
        return bool(self._info)

    @Property(float, notify=changed)
    def duration(self):
        return self._info.get("duration", 0.0)

    @Property(float, notify=changed)
    def nominalFps(self):
        return self._info.get("fps", 30.0)

    @Property(float, notify=positionChanged)
    def position(self):
        return self._position

    @Property(str, notify=frameChanged)
    def frameSource(self):
        return self._source

    @Property(str, notify=changed)
    def fileName(self):
        return self._playlist[self._index]["name"] if self._index >= 0 else "视频预览"

    @Property(str, notify=changed)
    def message(self):
        return self._message

    @Property(bool, notify=changed)
    def listVisible(self):
        return self._list_visible

    @Property(float, notify=changed)
    def rate(self):
        return self._rate

    @Property(float, notify=changed)
    def volume(self):
        return self._volume

    @Property(int, notify=changed)
    def resolution(self):
        return self._resolution

    @Property(bool, notify=changed)
    def previewOptimizing(self):
        return self._proxy_busy

    def _proxy_finished(self, token, result):
        if token == self._proxy_token and not self._closed:
            self._proxy_busy = False
            self.changed.emit()

    @Property("QVariantList", notify=changed)
    def resolutionOptions(self):
        limit = min(self._info.get("width", 0), self._info.get("height", 0))
        return [{"label": "原生", "value": 0}] + [
            {"label": label, "value": size}
            for size, label in ((720, "720P"), (1080, "1080P"), (1440, "2K"), (2160, "4K"))
            if size <= limit]

    @Slot(int)
    def setResolution(self, value):
        if not self.loaded or value not in [row["value"] for row in self.resolutionOptions]:
            return
        resume = self._playing
        self._resolution = value
        self.seek(self._position)
        self._resume_after_seek = resume

    @Property(str, notify=previewChanged)
    def previewSource(self):
        return self._preview_source

    @Property(float, notify=previewChanged)
    def previewTime(self):
        return self._preview_time

    @Property(float, notify=previewChanged)
    def previewTarget(self):
        return self._preview_target

    @Property(bool, notify=previewChanged)
    def previewBusy(self):
        return self._preview_busy

    @Slot(float)
    def requestPreview(self, position):
        if not self.loaded or self._closed:
            return
        self._preview_worker.cancel()
        self._preview_token = -1
        target = max(0, min(position, self.duration - 0.000001))
        self._preview_target = target
        # At frame zoom the visible range is already decoded: reuse its images.
        if self._detailed:
            for row in self._thumbnails:
                if row["start"] <= target < row["end"]:
                    self._preview_source = row["source"]
                    self._preview_time = row["time"]
                    self._preview_busy = False
                    self.previewChanged.emit()
                    return
        self._preview_busy = True
        self._preview_source = ""
        path = self._playlist[self._index]["path"]
        key = (path, self._generation)

        def task(check):
            if self._preview_key != key or self._preview_reader is None:
                if self._preview_reader:
                    self._preview_reader.close()
                self._preview_reader = None
                self._preview_reader = VideoReader(path)
                self._preview_key = key
            frame = self._preview_reader.seek_raw(target, check)
            return self._preview_reader.picture(frame, 480) if frame is not None else None

        self._preview_token = self._preview_worker.submit(task)
        self.previewChanged.emit()

    def _preview_received(self, token, picture):
        if token != self._preview_token or self._closed:
            return
        self._preview_busy = False
        if picture is not None:
            self._preview_source = self.images.put(picture.image)
            self._preview_time = picture.time
        self.previewChanged.emit()

    def _preview_failed(self, token, message):
        if token == self._preview_token:
            self._preview_busy = False
            self._preview_source = ""
            self.previewChanged.emit()

    @Slot()
    def clearPreview(self):
        self._preview_worker.cancel()
        self._preview_token = -1
        self._preview_source = ""
        self._preview_busy = False
        self.previewChanged.emit()

    @Slot()
    def chooseFiles(self):
        files, _ = QFileDialog.getOpenFileNames(
            None, "打开视频", "", "视频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.mts)")
        if files:
            self.addFiles(files)

    @Slot("QStringList")
    def addFiles(self, values):
        paths = local_video_paths(values)
        existing = {item["path"] for item in self._playlist}
        previous_count = len(self._playlist)
        for path in paths:
            if path not in existing:
                self._playlist.append({"path": path, "name": Path(path).name, "position": 0.0})
                existing.add(path)
        self.playlistChanged.emit()
        if not paths:
            self._message = "请拖入本地视频文件（MP4、MOV、MKV、AVI、WebM 等）"
            self.changed.emit()
        elif self._index < 0:
            self.selectVideo(next(i for i, item in enumerate(self._playlist)
                                  if item["path"] == paths[0]))
        if len(self._playlist) > max(1, previous_count):
            self._list_visible = True
            self.changed.emit()
        self._save()

    def _remember(self):
        if self._index >= 0:
            self._playlist[self._index]["position"] = self._position

    @Slot(int)
    def selectVideo(self, index):
        if not 0 <= index < len(self._playlist) or self._closed:
            return
        self.pause()
        self.clearPreview()
        self._remember()
        self._index = index
        self._proxy_worker.cancel()
        self._proxy_token = -1
        self._proxy_busy = False
        self._cache_worker.cancel()
        self._scrub_cache = ScrubCache(self._playlist[index]["path"])
        self._cache_center = -10.0
        self._resolution = 0
        self._generation += 1
        self._metadata_worker.cancel()
        self._metadata_token = -1
        self._info = {}
        self._source = ""
        self._thumbnails = []
        self._thumb_worker.cancel()
        self._thumb_token = -1
        self._thumb_busy = False
        self._busy = True
        self._message = ""
        item = self._playlist[index]
        self._position = float(item.get("position", 0))
        self._kind = "open"
        target = self._position
        self._token = self._worker.submit(lambda check: self._decoder.open(
            item["path"], target, check))
        self.changed.emit()
        self.positionChanged.emit()
        self.frameChanged.emit()
        self.thumbnailsChanged.emit()
        self.playlistChanged.emit()

    @Slot(int)
    def removeVideo(self, index):
        if not 0 <= index < len(self._playlist):
            return
        current = index == self._index
        if current:
            self.pause()
            self.clearPreview()
        self._playlist.pop(index)
        if index < self._index:
            self._index -= 1
        elif current:
            self._index = -1
            if self._playlist:
                self.selectVideo(min(index, len(self._playlist) - 1))
            else:
                self._proxy_worker.cancel()
                self._proxy_token = -1
                self._proxy_busy = False
                self._cache_worker.cancel()
                self._scrub_cache = None
                self._worker.cancel()
                self._token = -1
                self._worker.submit(lambda check: self._decoder.close())
                self._thumb_worker.cancel()
                self._thumb_token = -1
                self._info = {}
                self._source = ""
                self._position = 0
                self._thumbnails = []
                self._busy = self._thumb_busy = False
                self.images.clear()
                self.frameChanged.emit()
                self.positionChanged.emit()
                self.thumbnailsChanged.emit()
        self.playlistChanged.emit()
        self.changed.emit()
        self._save()

    @Slot()
    def toggleList(self):
        self._list_visible = not self._list_visible
        self.changed.emit()

    @Slot()
    def closeList(self):
        if self._list_visible:
            self._list_visible = False
            self.changed.emit()

    @Slot(float)
    def zoom(self, factor):
        self.zoomRequested.emit(factor)

    @Slot()
    def fit(self):
        self.fitRequested.emit()

    @Slot(float)
    def setRate(self, rate):
        if rate not in (0.25, 0.5, 1.0, 1.5, 2.0):
            return
        resume = self._playing
        self.pause()
        self._rate = rate
        self.changed.emit()
        if resume:
            self.togglePlayback()

    @Slot(float)
    def setVolume(self, volume):
        self._volume = max(0, min(1, volume))
        self._audio.set_volume(self._volume)
        self.changed.emit()

    @Slot(float)
    def seek(self, position):
        self._seek(position, fast=False)

    def _seek(self, position, fast=False):
        if not self.loaded or self._closed:
            return
        if self._playing:
            self.pause()
        self._resume_after_seek = False
        self._queued_scrub = None
        target = max(0, min(position, self.duration - 0.000001))
        self._busy = True
        self._kind = "seek"
        resolution = self._resolution
        cache = self._scrub_cache if fast else None
        if fast and cache and abs(target - self._cache_center) > 1:
            self._cache_center = target
            self._cache_worker.submit(lambda check: cache.warm(target, check))

        def task(check):
            if cache:
                picture = cache.get(target)
                if picture is not None:
                    return picture
            self._decoder.reader.output_height = resolution
            if cache:
                reader = self._decoder.reader
                width = round(960 * reader.stream.width
                              / max(reader.stream.width, reader.stream.height))
                picture = reader.seek(target, check, width=width)
                check()
                if picture is not None:
                    cache.put(picture)
                return picture
            return self._decoder.reader.seek(target, check)

        self._token = self._worker.submit(task)
        self.changed.emit()

    @Slot(float)
    def scrub(self, position):
        # Coalesce uncached targets so long-GOP decoding can finish. A known
        # memory hit can preempt obsolete decoding without starving the view.
        if (self._busy and self._kind == "seek"
                and not (self._scrub_cache and self._scrub_cache.contains_memory(position))):
            self._queued_scrub = position
        else:
            self._seek(position, fast=True)

    @Slot()
    def beginScrub(self):
        if not self.loaded or self._closed or self._scrub_active:
            return
        resume = self._playing or self._resume_after_seek
        self.pause()
        self._scrub_active = True
        self._scrub_resume = resume

    @Slot(float)
    def endScrub(self, position):
        if not self._scrub_active:
            return
        resume = self._scrub_resume
        self._scrub_active = self._scrub_resume = False
        # Final source-quality positioning replaces all queued drag previews.
        self._seek(position, fast=False)
        self._resume_after_seek = resume

    @Slot(int)
    def step(self, direction):
        if not self.loaded or self._busy:
            return
        self.pause()
        self._busy = True
        self._kind = "seek"
        position = self._position

        def task(check):
            reader = self._decoder.reader
            if direction < 0:
                return reader.previous(position, check)
            reader.seek(position, check)
            return reader.next(check)

        self._token = self._worker.submit(task)
        self.changed.emit()

    @Slot()
    def togglePlayback(self):
        if self._playing:
            self.pause()
            return
        if not self.loaded or self._busy:
            return
        if self._position >= self.duration - 1 / self.nominalFps - 0.000001:
            self.seek(0)
            self._resume_after_seek = True
            return
        self._start_playback()

    def _start_playback(self):
        self._playing = True
        self._eof = False
        self._next = None
        self._clock_position = self._position
        self._clock_start = time.monotonic()
        self._last_clock = self._position
        if self._info.get("audio"):
            self._audio.start(self._playlist[self._index]["path"], self._position,
                              self._info.get("origin", 0), self._rate)
        self._request_next(reposition=True)
        self._timer.start()
        self.changed.emit()

    @Slot()
    def pause(self):
        self._scrub_active = self._scrub_resume = False
        self._resume_after_seek = False
        self._queued_scrub = None
        self._playing = False
        self._timer.stop()
        self._audio.stop()
        if self._kind == "next":
            self._worker.cancel()
            self._token = -1
        self._next = None
        self._decode_pending = False
        self._remember()
        self._save()
        self.changed.emit()

    def _request_next(self, reposition=False):
        self._decode_pending = True
        self._kind = "next"
        position = self._position

        def task(check):
            if reposition:
                self._decoder.reader.seek(position, check)
            return self._decoder.reader.next(check)

        self._token = self._worker.submit(task)

    def _tick(self):
        self._audio.pump()
        elapsed = self._audio.elapsed()
        now = time.monotonic()
        if elapsed is not None:
            clock = self._clock_position + elapsed
            self._clock_start = now - (clock - self._clock_position) / self._rate
        else:
            clock = self._clock_position + (now - self._clock_start) * self._rate
        self._last_clock = clock
        if self._audio.error and self._message != self._audio.error:
            self._message = self._audio.error
            self.changed.emit()
        if self._next and self._next.time <= clock + 0.002:
            self._show(self._next)
            self._next = None
        if not self._next and not self._decode_pending and not self._eof:
            self._request_next()
        if self._eof and not self._next and clock >= self.duration:
            self.pause()

    def _show(self, picture):
        if picture is None:
            return
        self._position = picture.time
        self._source = self.images.put(picture.image, live=True)
        self.frameChanged.emit()
        self.positionChanged.emit()

    def _received(self, token, result):
        if token != self._token or self._closed:
            return
        if self._kind == "open":
            self._info, picture = result
            self._show(picture)
            self._busy = False
            self.changed.emit()
            self.fitRequested.emit()
            self._save()
            path = self._playlist[self._index]["path"]
            if self._proxy_directory and max(self._info["width"], self._info["height"]) >= 1280:
                try:
                    # Long movies need caches near the user's position, not hours
                    # of competing sequential decode starting at the opening credits.
                    on_demand = (self.duration > 300 or Path(path).stat().st_size >= 2 * 1024**3)
                    proxy = ScrubProxy(path, self._proxy_directory, on_demand=on_demand)
                    self._scrub_cache.proxy = proxy
                    if not on_demand:
                        self._proxy_busy = True
                        self._proxy_token = self._proxy_worker.submit(proxy.build)
                except OSError:
                    pass  # Read-only/full cache storage must not prevent playback.
            cache = self._scrub_cache
            target = self._position
            self._cache_center = target
            self._cache_worker.submit(lambda check: cache.warm(target, check))

            def probe(check):
                reader = VideoReader(path)
                try:
                    reader.probe_end(check)
                    return reader.duration
                finally:
                    reader.close()

            self._metadata_token = self._metadata_worker.submit(probe)
        elif self._kind == "next":
            self._next = result
            self._eof = result is None
            self._decode_pending = False
            return
        else:
            self._show(result)
            if self._queued_scrub is not None:
                target, self._queued_scrub = self._queued_scrub, None
                self._seek(target, fast=True)
                return
            self._busy = False
            self._remember()
            self._save_timer.start()
            if self._resume_after_seek:
                self._resume_after_seek = False
                self._start_playback()
        self.changed.emit()

    def _duration_received(self, token, duration):
        if (token == self._metadata_token and self.loaded and not self._closed
                and duration > self.duration):
            self._info["duration"] = duration
            self.changed.emit()

    def _failed(self, token, message):
        if token != self._token or self._closed:
            return
        self.pause()
        self._busy = False
        self._message = "无法读取视频：" + message
        self.changed.emit()

    @Slot(float, float, float)
    def requestThumbnails(self, start, end, pixels_per_second):
        if not self.loaded or pixels_per_second <= 0 or end <= start:
            return
        path = self._playlist[self._index]["path"]
        start, end = max(0, start), min(self.duration, end)
        self._thumb_busy = True
        self.thumbnailsChanged.emit()
        self._thumb_token = self._thumb_worker.submit(
            lambda check: filmstrip(path, start, end, pixels_per_second, check))

    def _thumbnails_received(self, token, result):
        if token != self._thumb_token or self._closed:
            return
        detailed, pictures = result
        rows = []
        for item in pictures:
            if detailed:
                picture = item
                start, end = picture.time, picture.end
            else:
                start, end, picture = item
            rows.append({"start": start, "end": end, "time": picture.time,
                         "source": self.images.put(picture.image)})
        self._thumbnails = rows
        self._detailed = detailed
        self._thumb_busy = False
        self.thumbnailsChanged.emit()

    def _thumbnails_failed(self, token, message):
        if token == self._thumb_token:
            self._thumb_busy = False
            self._message = "时间轴画面读取失败：" + message
            self.thumbnailsChanged.emit()
            self.changed.emit()

    def _restore(self):
        if not self._session or not self._session.exists():
            return
        try:
            saved = json.loads(self._session.read_text(encoding="utf-8"))
            for item in saved.get("playlist", [])[:200]:
                if isinstance(item, dict) and Path(item.get("path", "")).is_file():
                    self._playlist.append({"path": item["path"],
                                           "name": Path(item["path"]).name,
                                           "position": max(0, float(item.get("position", 0)))})
        except (OSError, ValueError, TypeError, AttributeError):
            self._playlist = []

    def _save(self):
        if not self._session:
            return
        try:
            self._session.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._session.with_suffix(".tmp")
            temporary.write_text(json.dumps({"playlist": self._playlist}, ensure_ascii=False),
                                 encoding="utf-8")
            temporary.replace(self._session)
        except OSError:
            pass

    @Slot()
    def shutdown(self):
        if self._closed:
            return
        self.pause()
        self._save_timer.stop()
        self._closed = True
        self._worker.cancel()
        # Close the container on its owning worker before stopping the thread.
        done = threading.Event()

        def close(check):
            self._decoder.close()
            done.set()

        self._worker.submit(close)
        done.wait(3)
        self._worker.close()
        self._thumb_worker.close()
        self._cache_worker.close()
        self._proxy_worker.close()
        self._metadata_worker.close()
        preview_done = threading.Event()

        def close_preview(check):
            if self._preview_reader:
                self._preview_reader.close()
            preview_done.set()

        self._preview_worker.submit(close_preview)
        preview_done.wait(3)
        self._preview_worker.close()
        self._audio.close()
