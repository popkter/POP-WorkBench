from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication, QImage
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
from poptools.infrastructure.video_scrub import ScrubCache, ScrubRequest


class VideoPreviewController(QObject):
    changed = Signal()
    positionChanged = Signal()
    frameChanged = Signal()
    playlistChanged = Signal()
    thumbnailsChanged = Signal()
    resolutionOptionsChanged = Signal()
    zoomRequested = Signal(float)
    fitRequested = Signal()
    previewChanged = Signal()
    _scrubFrameReady = Signal(object)
    _coldScrubStarted = Signal(object)

    def __init__(self, data_dir: Path | None = None, parent=None):
        super().__init__(parent)
        self.images = VideoImages()
        self._decoder = PlaybackDecoder()
        self._worker = LatestWorker("video-playback")
        self._cache_worker = LatestWorker("video-scrub-cache")
        self._cache_worker.completed.connect(self._cached_scrub_preview_received)
        self._cache_worker.failed.connect(self._cached_scrub_preview_failed)
        self._cached_scrub_preview_token = -1
        self._proxy_worker = LatestWorker("video-preview-prepare")
        self._proxy_worker.completed.connect(self._proxy_finished)
        self._proxy_worker.failed.connect(self._proxy_failed)
        self._proxy = None
        self._proxy_token = -1
        self._proxy_busy = self._proxy_ready = self._proxy_exhausted = False
        self._proxy_overview_only = self._proxy_overview_attempted = False
        self._overview_run: threading.Event | None = None
        self._proxy_directory = data_dir / "video-preview-cache" if data_dir else None
        self._preview_pixels = (0, 0)
        self._preview_active = True
        self._cache_timer = QTimer(self)
        self._cache_timer.setSingleShot(True)
        self._cache_timer.setInterval(150)
        self._cache_timer.timeout.connect(self._warm_scrub_cache)
        self._scrub_prepare_timer = QTimer(self)
        self._scrub_prepare_timer.setSingleShot(True)
        self._scrub_prepare_timer.setInterval(350)
        self._scrub_prepare_timer.timeout.connect(self._prepare_scrub_proxy)
        self._proxy_progress_timer = QTimer(self)
        self._proxy_progress_timer.setInterval(80)
        self._proxy_progress_timer.timeout.connect(self._use_prepared_scrub)
        self._scrub_cache = None
        self._drag_cache = None
        self._cache_center = -10.0
        self._metadata_worker = LatestWorker("video-duration")
        self._metadata_worker.completed.connect(self._duration_received)
        self._metadata_worker.failed.connect(self._duration_failed)
        self._metadata_token = -1
        self._metadata_pending = None
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
        self._thumbnail_request = None
        self._deferred_thumbnails = None
        self._next: Picture | None = None
        self._paused_successor: Picture | None = None
        self._displayed_playback_frame: Picture | None = None
        self._decode_pending = self._eof = False
        self._resume_after_seek = False
        self._scrub_active = False
        self._scrub_resume = False
        self._queued_scrub = None
        self._scrub_request = None
        self._refine_request = None
        self._scrub_fast = False
        self._scrub_source_slow = False
        self._last_scrub_input = None
        self._last_fast_scrub_at = None
        self._approximate_frame = False
        self._scrub_refine_timer = QTimer(self)
        self._scrub_refine_timer.setSingleShot(True)
        self._scrub_refine_timer.setInterval(80)
        self._scrub_refine_timer.timeout.connect(self._refine_stationary_scrub)
        self._scrubFrameReady.connect(self._scrub_progress)
        self._coldScrubStarted.connect(self._schedule_scrub_preparation)
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

    @Property(bool, notify=frameChanged)
    def previewApproximate(self):
        return self._approximate_frame

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

    @Property(bool, notify=changed)
    def previewReady(self):
        return self._proxy_ready

    def _proxy_finished(self, token, result):
        if token != self._proxy_token or self._closed:
            return
        self._proxy_busy = False
        self._proxy_progress_timer.stop()
        self._overview_run = None
        overview_only, self._proxy_overview_only = self._proxy_overview_only, False
        if overview_only:
            self._proxy_overview_attempted = True
            # A complete sparse pass has already read the last real frame.
            # Use that endpoint instead of decoding the last GOP separately.
            duration = self._proxy.overview_end if result else None
            if duration is not None and self._metadata_pending is not None:
                self._metadata_pending = None
                self._info["duration"] = max(self.duration, duration)
        else:
            self._proxy_ready = bool(result) and not self._proxy.on_demand
            self._proxy_exhausted = not result
        self._use_prepared_scrub()
        if overview_only:
            if self._scrub_active and not self._detailed:
                self._ensure_proxy_preparation()
            elif self._preview_active:
                self._cache_timer.start()
        self.changed.emit()

    def _proxy_failed(self, token, message):
        if token == self._proxy_token and not self._closed:
            self._proxy_busy = False
            self._proxy_progress_timer.stop()
            self._overview_run = None
            self._proxy_exhausted = True
            if self._proxy_overview_only:
                self._proxy_overview_only = False
                self._cache_timer.start()
            self.changed.emit()

    def _stop_preparation(self, keep_proxy=False):
        self._cache_timer.stop()
        self._cache_worker.cancel()
        self._cached_scrub_preview_token = -1
        if not keep_proxy:
            self._scrub_prepare_timer.stop()
            self._proxy_progress_timer.stop()
            self._proxy_worker.cancel()
            if self._overview_run is not None:
                self._overview_run.set()
                self._overview_run = None
            self._proxy_token = -1
            self._proxy_busy = False
            self._proxy_overview_only = False
        if self._metadata_token != -1:
            self._metadata_worker.cancel()
            self._metadata_token = -1

    @Slot(float, float)
    def setPreviewViewport(self, width, height):
        pixels = (max(0, width), max(0, height))
        if pixels != self._preview_pixels:
            self._paused_successor = None
        self._preview_pixels = pixels
        if self.loaded:
            self._configure_proxy()

    @Slot(bool)
    def setPreviewActive(self, active):
        self._preview_active = active
        if not active:
            self._pause_preview()
            self._defer_thumbnails()
        elif self.loaded:
            if self._approximate_frame and not self._busy:
                target = (self._last_scrub_input[1] if self._last_scrub_input is not None
                          else self._position)
                self._seek(target, fast=False)
            elif not self._busy and not self._playing:
                self._refine_paused_playback_frame()
            if self._deferred_thumbnails and not self._busy:
                pending, self._deferred_thumbnails = self._deferred_thumbnails, None
                self.requestThumbnails(*pending)
            self._cache_timer.start()

    def _viewport_output_height(self):
        width, height = self._info["width"], self._info["height"]
        short, long = min(width, height), max(width, height)
        # Fit the source aspect ratio, including display scale and picture zoom.
        # The long viewport edge is conservative for rotated/portrait media.
        needed = max(self._preview_pixels) * short / long
        cap = min(short, self._resolution or short)
        # Small and ultrawide canvases need fewer pixels. Keep a conservative
        # floor with sharper downscaling so screen-recording text stays legible.
        output = next((size for size in (600, 720, 1080, 1440, 2160, 4320)
                       if size >= needed), short) if needed else cap
        return min(cap, output)

    def _configure_proxy(self):
        if not self._proxy_directory or not self.loaded:
            return
        output = self._viewport_output_height()
        if self._proxy and self._proxy.output_height == output:
            return
        self._stop_preparation()
        self._proxy_ready = self._proxy_exhausted = False
        self._proxy_overview_attempted = False
        self._drag_cache = ScrubCache(self._playlist[self._index]["path"],
                                     budget=64 * 1024 * 1024, output_height=output)
        try:
            self._proxy = ScrubProxy(self._playlist[self._index]["path"],
                                     self._proxy_directory, full_quality=True,
                                     output_height=output, on_demand=self.duration > 300,
                                     reuse_reads=True)
            self._cache_timer.start()
        except OSError:
            self._proxy = None
        self.changed.emit()

    @Property("QVariantList", notify=resolutionOptionsChanged)
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
        self._configure_proxy()
        self._cache_worker.cancel()
        self._scrub_cache = ScrubCache(self._playlist[self._index]["path"],
                                       output_height=value)
        self._cache_center = -10.0
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
                    # A cached frame can replace a queued clearPreview cleanup.
                    # It does not need to keep any source container open.
                    self._preview_worker.submit(self._close_preview_reader)
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
        # Cancellation only discards work/results; the idle hover reader still
        # owns the source file. Close it on the same worker that decodes it.
        self._preview_worker.submit(self._close_preview_reader)
        self._preview_source = ""
        self._preview_busy = False
        self.previewChanged.emit()

    def _close_preview_reader(self, check):
        reader, self._preview_reader = self._preview_reader, None
        self._preview_key = None
        if reader is not None:
            reader.close()

    @Slot()
    def chooseFiles(self):
        files, _ = QFileDialog.getOpenFileNames(
            None, "打开视频", "", "视频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.ts *.mts)")
        if files:
            self.addFiles(files)

    @Slot("QStringList", result=bool)
    def acceptsVideoDrop(self, values):
        return bool(local_video_paths(values))

    @Slot("QStringList")
    def openDroppedFiles(self, values):
        paths = local_video_paths(values)
        if not paths:
            return
        self.addFiles(paths)
        index = next(i for i, item in enumerate(self._playlist) if item["path"] == paths[0])
        if self._index != index:
            self.selectVideo(index)

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
        self._save_timer.start()

    def _remember(self):
        if self._index >= 0:
            self._playlist[self._index]["position"] = self._position

    @Slot(int)
    def selectVideo(self, index):
        if not 0 <= index < len(self._playlist) or self._closed:
            return
        self._pause_preview()
        self.clearPreview()
        self._remember()
        self._index = index
        self._stop_preparation()
        self._proxy = None
        self._proxy_ready = self._proxy_exhausted = False
        self._proxy_overview_attempted = False
        self._drag_cache = None
        self._cache_timer.stop()
        self._thumbnail_request = self._deferred_thumbnails = None
        self._cache_worker.cancel()
        self._scrub_cache = ScrubCache(self._playlist[index]["path"])
        self._cache_center = -10.0
        self._resolution = 0
        self._generation += 1
        self._metadata_worker.cancel()
        self._metadata_token = -1
        self._metadata_pending = None
        self._info = {}
        self._source = ""
        self._displayed_playback_frame = None
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
        self.resolutionOptionsChanged.emit()
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
            self._pause_preview()
            self.clearPreview()
        self._playlist.pop(index)
        if index < self._index:
            self._index -= 1
        elif current:
            self._index = -1
            if self._playlist:
                self.selectVideo(min(index, len(self._playlist) - 1))
            else:
                self._metadata_worker.cancel()
                self._metadata_token = -1
                self._metadata_pending = None
                self._cache_worker.cancel()
                self._scrub_cache = None
                self._drag_cache = None
                self._proxy = None
                self._proxy_ready = False
                self._worker.cancel()
                self._token = -1
                self._worker.submit(lambda check: self._decoder.close())
                self._thumb_worker.cancel()
                self._thumb_token = -1
                self._info = {}
                self._source = ""
                self._displayed_playback_frame = None
                self._position = 0
                self._thumbnails = []
                self._busy = self._thumb_busy = False
                self.images.clear()
                self.resolutionOptionsChanged.emit()
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

    @Slot(QImage, result=bool)
    def copyViewportImage(self, image):
        if image.isNull():
            return False
        QGuiApplication.clipboard().setImage(image)
        return True

    @Slot(float)
    def setRate(self, rate):
        if rate not in (0.25, 0.5, 1.0, 1.5, 2.0):
            return
        resume = self._playing
        self._pause_preview()
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

    def _can_sample_scrub(self):
        return (self._scrub_fast and not self._detailed
                and self._last_scrub_input is not None
                and time.monotonic() - self._last_scrub_input[0] < .08)

    def _seek(self, position, fast=False, *, suspend_overview=False):
        if not self.loaded or self._closed:
            return
        self._paused_successor = None
        if self._playing:
            self._pause_preview()
        self._resume_after_seek = False
        self._scrub_refine_timer.stop()
        self._queued_scrub = None
        target = max(0, min(position, self.duration - 0.000001))
        self._busy = True
        self._kind = "seek"
        resolution = self._resolution
        cache = self._scrub_cache
        preview_cache = self._drag_cache
        drag_cache = preview_cache if fast else None
        release_preview = None
        if not fast and preview_cache and not (cache and cache.contains_memory(target)):
            candidate = preview_cache.get(target)
            if candidate is not None and not candidate.approximate:
                release_preview = candidate
        fast_sampling = fast and self._can_sample_scrub()
        expensive_random_seek = self._info.get("expensive_random_seek")
        history_bytes = self._info.get("seek_history_bytes", 0)
        retain_history = (history_bytes and fast and self._scrub_active
                          and not self._scrub_resume and not self._proxy_ready)
        proxy = self._proxy
        # This mailbox is owned by this seek. Pointer updates replace its one
        # target; new seeks invalidate progress from the previous mailbox.
        request = ScrubRequest(target) if fast else None
        self._scrub_request = request
        refine = None if fast else ScrubRequest(target)
        self._refine_request = refine
        keep_proxy = (fast and self._scrub_active and not self._detailed
                      and proxy is not None and not proxy.on_demand)
        overview_run = self._overview_run
        suspend_overview = suspend_overview and overview_run is not None
        if suspend_overview:
            overview_run.clear()
            self._proxy_progress_timer.stop()
        elif keep_proxy and overview_run is not None:
            overview_run.set()
            if not self._proxy_progress_timer.isActive():
                self._proxy_progress_timer.start()
        self._stop_preparation(keep_proxy=keep_proxy or suspend_overview)
        if expensive_random_seek:
            self._defer_thumbnails()
        if (keep_proxy and self._scrub_source_slow
                and not self._proxy_busy and not self._proxy_ready
                and not self._proxy_exhausted and not self._scrub_prepare_timer.isActive()):
            self._start_scrub_prepare_timer()

        def task(check):
            reader = self._decoder.reader
            reader.output_height = resolution
            reader.interpolation = None
            if drag_cache:
                picture = drag_cache.get(target)
                if picture is not None and (fast_sampling or not picture.approximate):
                    return picture
            if cache:
                picture = cache.get(target)
                if picture is not None:
                    if history_bytes and not fast:
                        reader.clear_seek_history()
                    if drag_cache:
                        # Keep drag uploads at the viewport's pixel budget even
                        # when the exact cache contains a native release frame.
                        image = picture.image
                        short = min(image.width(), image.height())
                        if 0 < drag_cache.output_height < short:
                            scale = drag_cache.output_height / short
                            image = image.scaled(round(image.width() * scale),
                                                 round(image.height() * scale),
                                                 Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)
                            check()
                            picture = Picture(picture.time, picture.end, image)
                        drag_cache.put(picture)
                    return picture
            if history_bytes and not fast:
                picture = reader.take_recent_seek_picture(target, check)
                if picture is not None:
                    if cache:
                        cache.put(picture)
                    return picture
            if proxy and release_preview is None:
                picture = proxy.get_nearest(target, .12) if fast_sampling else proxy.get(target)
                check()
                if picture is not None:
                    # Lossy intra previews never enter the exact source cache.
                    if fast:
                        if drag_cache:
                            drag_cache.put(picture)
                        return picture
                    # The correct timestamp can display while the source
                    # decoder prepares the requested output resolution.
                    if refine.publish(picture):
                        self._scrubFrameReady.emit(refine)
            if request is not None:
                if (drag_cache and fast_sampling
                        and not reader.can_seek_exact_forward(target)):
                    picture = drag_cache.get_nearest(target, .12)
                    if picture is not None:
                        return picture
                # Finish one cold seek while the mailbox retains the latest
                # pointer target. Retargeting every few decoded frames can
                # starve output indefinitely on long-GOP sources.
                request.from_source = True
                request.random_access = not reader.can_seek_exact_forward(target)
                if request.random_access:
                    self._coldScrubStarted.emit(request)
                if drag_cache:
                    reader.output_height = drag_cache.output_height
                    reader.interpolation = (
                        "BICUBIC" if drag_cache.output_height == 600 else None)
                if retain_history:
                    retarget = request.retarget_from_frame if (
                        expensive_random_seek and request.random_access) else None
                    picture = reader.seek_for_scrub(
                        target, check, sample=fast_sampling, history_bytes=history_bytes,
                        keep_history=lambda: abs(request.target - target) <= .12,
                        retarget=retarget)
                elif fast_sampling:
                    picture = reader.seek_fast_preview(target, check)
                else:
                    picture = reader.seek(target, check)
            else:
                picture = reader.seek(target, check)
            check()
            destination = drag_cache or cache
            if (destination and picture is not None
                    and (not picture.approximate or drag_cache is not None)):
                destination.put(picture)
            return picture

        self._token = self._worker.submit(task)
        if release_preview is not None:
            # The previous drag may still be unwinding inside the decoder.
            self._show(release_preview)
        self.changed.emit()

    @Slot(float)
    def scrub(self, position):
        if not self.loaded or self._closed:
            return
        position = max(0, min(position, self.duration - 0.000001))
        now = time.monotonic()
        previous = self._last_scrub_input
        self._scrub_fast = (previous is not None and now - previous[0] < .15
                            and abs(position - previous[1]) > 4 * max(.001, now - previous[0]))
        self._last_scrub_input = (now, position)
        if self._scrub_fast:
            previous_fast = self._last_fast_scrub_at
            self._last_fast_scrub_at = now
            if previous_fast is not None and now - previous_fast < .1:
                self._prepare_early_overview()
        request = self._scrub_request
        if (self._proxy_ready and self._scrub_active and self._can_sample_scrub()
                and self._drag_cache is not None and (not self._busy or request is not None)):
            # A viewport-sized image already in memory can follow the new
            # target without waiting for an older disk read. During cold drag,
            # let the source decoder keep its cursor for the next cache miss.
            picture = self._drag_cache.get(position)
            if picture is not None and not picture.approximate:
                self._scrub_refine_timer.stop()
                if request is not None:
                    self._worker.cancel()
                    self._token = -1
                    self._scrub_request = None
                    self._busy = False
                    self.changed.emit()
                if self._position != picture.time or self._approximate_frame:
                    self._show(picture)
                return
            if (request is not None and not request.from_source
                    and now - request.sampled_at >= .04):
                # An older JPEG read can still be in progress. Present an
                # in-memory neighbour at the current pointer while the worker
                # finishes, then let the mailbox request the latest position.
                picture = picture or self._drag_cache.get_nearest(position, .12)
                if picture is not None:
                    request.update(position)
                    self._show_cached_scrub_preview(request, picture)
                    return
        if self._busy and request is not None:
            if self._can_read_cache_alongside_source(request):
                request.update(position)
                self._preview_cached_scrub(request)
                return
            # Let a bounded cache read finish while keeping only the newest
            # target. Cancelling every JPEG read at 60 Hz can starve presentation.
            # A ready frame may still preempt a much slower source GOP.
            ready = request.from_source and self._cached_scrub_ready(position)
            if not ready:
                request.update(position)
                return
        self._seek(position, fast=True)

    def _can_read_cache_alongside_source(self, request):
        return (self._scrub_active and not self._proxy_ready and request.from_source
                and request.random_access and self._info.get("expensive_random_seek")
                and self._drag_cache is not None and self._can_sample_scrub())

    def _preview_cached_scrub(self, request):
        target = request.target
        cache, proxy = self._drag_cache, self._proxy
        picture = cache.get(target) or cache.get_nearest(target, .12)
        if picture is not None:
            self._show_cached_scrub_preview(request, picture)
        elif (self._cached_scrub_preview_token == -1 and proxy is not None
              and proxy.contains_near_memory(target, .12)):
            self._read_cached_scrub_preview(request, target, cache, proxy)

    def _read_cached_scrub_preview(self, request, target, cache, proxy):
        # Idle prefetch is suspended during a drag. Its worker can read the
        # proxy while the foreground reader keeps advancing the source GOP.
        def task(check):
            picture = proxy.get_nearest(target, .12)
            check()
            if picture is not None:
                cache.put(picture)
            return request, picture

        self._cached_scrub_preview_token = self._cache_worker.submit(task)

    def _cached_scrub_preview_received(self, token, result):
        if token != self._cached_scrub_preview_token:
            return
        self._cached_scrub_preview_token = -1
        request, picture = result
        if picture is None or request is not self._scrub_request or not self._scrub_active:
            return
        target = request.target
        if picture.time <= target < picture.end:
            self._show_cached_scrub_preview(request, picture)
        elif self._can_sample_scrub() and abs(picture.time - target) <= .12:
            self._show_cached_scrub_preview(
                request, Picture(picture.time, picture.end, picture.image, approximate=True))

    def _cached_scrub_preview_failed(self, token, _message):
        if token == self._cached_scrub_preview_token:
            self._cached_scrub_preview_token = -1

    def _show_cached_scrub_preview(self, request, picture):
        request.displayed_preview = True
        if self._position != picture.time or self._approximate_frame != picture.approximate:
            self._show(picture)

    def _cached_scrub_ready(self, target):
        sampling = self._can_sample_scrub()
        if any(cache and cache.contains_memory(target, allow_approximate=sampling)
               for cache in (self._scrub_cache, self._drag_cache)):
            return True
        if sampling and self._drag_cache and self._drag_cache.contains_near_memory(target, .12):
            return True
        return self._proxy and (self._proxy.contains_memory(target)
                                or (sampling and self._proxy.contains_near_memory(target, .12)))

    def _scrub_progress(self, request):
        picture = request.take_progress()
        if (request in (self._scrub_request, self._refine_request)
                and picture is not None and not self._closed):
            self._show(picture)

    @Slot()
    def beginScrub(self):
        if not self.loaded or self._closed or self._scrub_active:
            return
        resume = self._playing or self._resume_after_seek
        keep_overview = self._proxy_overview_only and not self._detailed
        self._pause_preview(keep_proxy=keep_overview)
        self._scrub_active = True
        self._scrub_resume = resume
        self._last_scrub_input = None
        self._last_fast_scrub_at = None
        self._scrub_fast = False
        self._scrub_source_slow = False
        self._cache_timer.stop()
        if keep_overview:
            self._proxy_progress_timer.start()
        self._defer_thumbnails()

    def _defer_thumbnails(self):
        if self._thumb_busy:
            self._deferred_thumbnails = self._thumbnail_request
            self._thumb_worker.cancel()
            self._thumb_token = -1
            self._thumb_busy = False
            self.thumbnailsChanged.emit()

    @Slot(float)
    def endScrub(self, position):
        if not self._scrub_active:
            return
        resume = self._scrub_resume
        self._scrub_active = self._scrub_resume = False
        # Resolve the source frame while a matching preview can display.
        self._seek(position, fast=False, suspend_overview=not resume)
        self._resume_after_seek = resume

    def _refine_stationary_scrub(self):
        if (self._scrub_active and not self._playing and not self._busy
                and self._last_scrub_input is not None
                and time.monotonic() - self._last_scrub_input[0] >= .075):
            self._seek(self._last_scrub_input[1], fast=False, suspend_overview=True)

    @Slot(int)
    def step(self, direction):
        if not self.loaded or self._busy:
            return
        self._pause_preview()
        self._busy = True
        self._kind = "seek"
        position = self._position

        def task(check):
            reader = self._decoder.reader
            reader.output_height = self._resolution
            reader.interpolation = None
            if direction < 0:
                return reader.previous(position, check)
            reader.seek_raw(position, check)
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
        self._scrub_refine_timer.stop()
        self._stop_preparation()
        self._playing = True
        self._eof = False
        self._next, self._paused_successor = self._paused_successor, None
        self._clock_position = self._position
        self._clock_start = time.monotonic()
        self._last_clock = self._position
        if self._info.get("audio"):
            self._audio.start(self._playlist[self._index]["path"], self._position,
                              self._info.get("origin", 0), self._rate)
        if self._next is None:
            self._request_next(reposition=True)
        elif self._kind == "pause_frame":
            self._worker.cancel()
            self._token = -1
        self._timer.start()
        self.changed.emit()

    @Slot()
    def pause(self):
        self._pause_preview(keep_successor=True)
        if self._preview_active:
            self._refine_paused_playback_frame()

    def _pause_preview(self, *, keep_proxy=False, keep_successor=False):
        if not keep_successor:
            self._paused_successor = None
        elif self._playing:
            # The decoder is already positioned beyond this buffered frame.
            # Retain one viewport-sized successor only while the source and
            # output size are unchanged, so resume can avoid a GOP seek.
            next_picture = self._next
            self._paused_successor = (
                next_picture if next_picture is not None and not self._decode_pending
                and next_picture.source_frame is not None else None)
        self._scrub_refine_timer.stop()
        self._stop_preparation(keep_proxy=keep_proxy)
        self._scrub_request = None
        self._refine_request = None
        self._scrub_active = self._scrub_resume = False
        self._resume_after_seek = False
        self._queued_scrub = None
        self._playing = False
        self._timer.stop()
        self._audio.stop()
        if self._kind in ("next", "pause_frame"):
            self._worker.cancel()
            self._token = -1
        self._next = None
        self._decode_pending = False
        self._remember()
        self._save_timer.start()
        if self.loaded and not self._closed and self._preview_active:
            self._cache_timer.start()
        self.changed.emit()

    def _refine_paused_playback_frame(self):
        displayed = self._displayed_playback_frame
        if displayed is None or self._closed or self._busy or self._playing:
            return
        height = self._resolution
        self._kind = "pause_frame"
        self._cache_timer.stop()

        def task(check):
            check()
            reader = self._decoder.reader
            reader.output_height = height
            reader.interpolation = None
            picture = reader.picture(displayed.source_frame)
            picture.end = displayed.end
            return picture

        self._token = self._worker.submit(task)

    def _request_next(self, reposition=False):
        self._decode_pending = True
        self._kind = "next"
        position = self._position
        height = self._resolution
        viewport_only = False
        source_width = self._info.get("width", 0)
        source_height = self._info.get("height", 0)
        source_short = min(source_width, source_height)
        if height == 0 and source_short >= 1440 and max(self._preview_pixels) > 0:
            viewport = self._viewport_output_height()
            if viewport * 2 <= source_short:
                height = viewport
                viewport_only = True

        def task(check):
            reader = self._decoder.reader
            reader.output_height = height
            reader.interpolation = "BICUBIC" if height == 600 else None
            if reposition:
                reader.seek_raw(position, check)
            if not viewport_only:
                return reader.next_for_time(self._last_clock, check)
            picture = reader.next_for_time(self._last_clock, check, retain_source=True)
            frame = picture.source_frame if picture is not None else None
            if frame is not None and frame.width * source_height != frame.height * source_width:
                # A stream can change aspect ratio after opening. Its previous
                # viewport budget may no longer cover all visible pixels.
                reader.output_height = 0
                reader.interpolation = None
                native = reader.picture(frame)
                native.end = picture.end
                return native
            return picture

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
        self._displayed_playback_frame = picture if picture.source_frame is not None else None
        self._position = picture.time
        self._approximate_frame = picture.approximate
        self._source = self.images.put(picture.image, live=True)
        self.frameChanged.emit()
        self.positionChanged.emit()

    def _received(self, token, result):
        if token != self._token or self._closed:
            return
        if self._kind == "open":
            self._info, picture = result
            self.resolutionOptionsChanged.emit()
            if self._scrub_cache is not None:
                self._scrub_cache.put(picture)
            self._show(picture)
            self._busy = False
            self.changed.emit()
            self.fitRequested.emit()
            self._save_timer.start()
            path = self._playlist[self._index]["path"]
            self._configure_proxy()
            self._cache_center = self._position
            self._metadata_pending = path
            if self._preview_active:
                self._cache_timer.start()
                if self._can_prepare_overview():
                    # Start the sparse pass on the next event turn. The first
                    # pointer gesture can arrive before the idle timer fires.
                    QTimer.singleShot(0, self._warm_scrub_cache)
        elif self._kind == "next":
            self._next = result
            self._eof = result is None
            self._decode_pending = False
            return
        elif self._kind == "pause_frame":
            self._show(result)
            if self._preview_active:
                self._cache_timer.start()
            return
        else:
            request = self._scrub_request
            if (request is not None and request.from_source and request.random_access
                    and self._scrub_active
                    and time.monotonic() - request.sampled_at >= .06):
                self._scrub_source_slow = True
            if request is not None and request.target != request.sampled_target:
                # Fast cached results have a freshness bound. A cold source
                # seek can be slower: present its accurate sampled frame once,
                # then immediately service the latest target without backlog.
                if (result is not None and not request.displayed_preview
                        and (request.from_source
                             or time.monotonic() - request.sampled_at <= .1)
                        and (result.time <= request.sampled_target < result.end
                             or (result.approximate
                                 and abs(result.time - request.sampled_target) <= .12))):
                    self._show(result)
                self._seek(request.target, fast=True)
                return
            self._scrub_request = None
            self._refine_request = None
            self._show(result)
            if result is not None and result.approximate and self._scrub_active:
                self._scrub_refine_timer.start()
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
            elif self._overview_run is not None:
                self._overview_run.set()
                if self._scrub_active and not self._proxy_progress_timer.isActive():
                    self._proxy_progress_timer.start()
            if not self._scrub_active:
                if self._deferred_thumbnails:
                    pending, self._deferred_thumbnails = self._deferred_thumbnails, None
                    self.requestThumbnails(*pending)
                if not self._playing:
                    self._cache_timer.start()
        self.changed.emit()

    def _warm_scrub_cache(self):
        if (self._closed or not self.loaded or not self._preview_active or self._playing
                or self._busy or self._scrub_active):
            return
        proxy = self._proxy
        if self._can_prepare_overview() and self._metadata_token == -1:
            self._ensure_proxy_preparation(overview_only=True)
            return
        if self._metadata_pending is not None:
            if self._metadata_token == -1:
                path = self._metadata_pending

                def probe(check):
                    check()
                    reader = VideoReader(path)
                    try:
                        reader.probe_end(check)
                        return reader.duration
                    finally:
                        reader.close()

                self._metadata_token = self._metadata_worker.submit(probe)
            return
        cache, target = self._scrub_cache, self._position
        if proxy and not self._proxy_exhausted and not self._proxy_ready:
            self._ensure_proxy_preparation()
            return
        if cache:
            self._cache_worker.submit(lambda check: cache.warm(target, check))

    def _prepare_scrub_proxy(self):
        # A sustained overview drag can build useful future frames. Exact frame
        # navigation and long-video neighborhoods retain foreground priority.
        request = self._scrub_request
        if (request is not None and request.from_source and request.random_access
                and time.monotonic() - request.sampled_at >= .06):
            self._scrub_source_slow = True
        if (self._closed or not self.loaded or not self._preview_active
                or not self._scrub_active or self._playing or self._detailed
                or not self._scrub_source_slow
                or self._proxy is None or self._proxy.on_demand):
            return
        self._ensure_proxy_preparation()

    def _schedule_scrub_preparation(self, request):
        if (not self._closed and request is self._scrub_request and self._scrub_active
                and self._preview_active and not self._detailed and self._proxy is not None
                and not self._proxy.on_demand and not self._proxy_ready
                and not self._proxy_busy and not self._proxy_exhausted
                and not self._scrub_prepare_timer.isActive()):
            # Schedule while decoding is still in progress; a multi-second GOP
            # must not postpone cache preparation until that cold seek finishes.
            self._start_scrub_prepare_timer()

    def _start_scrub_prepare_timer(self):
        # Large long-GOP sources benefit from starting the sparse cache while
        # the foreground reader is still serving an expensive random seek.
        early = self._info.get("expensive_random_seek") and self._can_sample_scrub()
        self._scrub_prepare_timer.start(120 if early else 350)

    def _prepare_early_overview(self):
        # Two recent fast moves on an identified, expensive source justify
        # preparing the overview while the first random decode is in flight.
        if (self._scrub_active and self._preview_active and not self._detailed
                and self._can_prepare_overview()):
            self._ensure_proxy_preparation(overview_only=True)

    def _can_prepare_overview(self):
        return (self._proxy is not None and not self._proxy.on_demand
                and not self._proxy_overview_attempted and not self._proxy_ready
                and not self._proxy_exhausted
                and self._info.get("overview_decode_threads", 1) > 1)

    def _ensure_proxy_preparation(self, *, overview_only=False):
        proxy, target = self._proxy, self._position
        if (proxy is None or self._proxy_busy or self._proxy_ready or self._proxy_exhausted):
            return
        self._scrub_prepare_timer.stop()
        self._proxy_busy = True
        self._proxy_overview_only = overview_only
        # A single slow mouse event shouldn't choose a much slower full build
        # in the middle of a fast drag. The latest input must still be recent.
        now = time.monotonic()
        recent_fast = self._last_fast_scrub_at is not None and now - self._last_fast_scrub_at < .25
        recent_input = self._last_scrub_input is not None and now - self._last_scrub_input[0] < .08
        overview = (
            not self._proxy_overview_attempted and self._scrub_active and not self._detailed
            and (self._can_sample_scrub() or (recent_fast and recent_input))
        )
        overview_threads = self._info.get("overview_decode_threads", 1)
        drag_cache = self._drag_cache
        overview_run = threading.Event() if overview_only else None
        if overview_run is not None:
            overview_run.set()
        self._overview_run = overview_run

        def prepare(check):
            if proxy.on_demand:
                return proxy.warm(target, check)
            if overview_only or overview:
                # Reach all regions sooner at unchanged spatial quality. The
                # complete state still belongs to the subsequent exact build.
                # The converted image can satisfy a drag immediately, while
                # the JPEG and its database entry are still being prepared.
                publish = drag_cache.put if drag_cache and overview_threads > 1 else None
                prepared = proxy.prepare_overview(
                    check, frame_threads=overview_threads, publish=publish, run_event=overview_run)
                if overview_only:
                    return prepared
                check()
            return proxy.build(check)

        self._proxy_token = self._proxy_worker.submit(prepare)
        if self._scrub_active:
            self._proxy_progress_timer.start()
        self.changed.emit()

    def _use_prepared_scrub(self):
        request = self._scrub_request
        if (not self._closed and self._scrub_active and self._busy
                and request is not None and request.from_source):
            if self._can_read_cache_alongside_source(request):
                self._preview_cached_scrub(request)
            elif self._cached_scrub_ready(request.target):
                # A commit can finish after the pointer stops. Resolve its
                # position without waiting for the old source seek.
                self._seek(request.target, fast=True)

    def _duration_received(self, token, duration):
        if token != self._metadata_token or not self.loaded or self._closed:
            return
        self._metadata_token = -1
        self._metadata_pending = None
        if duration > self.duration:
            self._info["duration"] = duration
            self.changed.emit()
        self._cache_timer.start()

    def _duration_failed(self, token, message):
        if token != self._metadata_token or self._closed:
            return
        # Duration refinement is optional. A bad tail must not prevent cache
        # preparation or repeatedly reopen the same undecodable media.
        self._metadata_token = -1
        self._metadata_pending = None
        if self.loaded:
            self._cache_timer.start()

    def _failed(self, token, message):
        if token != self._token or self._closed:
            return
        self._pause_preview()
        self._busy = False
        self._message = "无法读取视频：" + message
        self.changed.emit()

    @Slot(float, float, float)
    def requestThumbnails(self, start, end, pixels_per_second):
        if not self.loaded or pixels_per_second <= 0 or end <= start:
            return
        self._thumbnail_request = (start, end, pixels_per_second)
        if self._scrub_active or self._busy or not self._preview_active:
            self._deferred_thumbnails = self._thumbnail_request
            return
        path = self._playlist[self._index]["path"]
        start, end = max(0, start), min(self.duration, end)
        self._thumb_busy = True
        self.thumbnailsChanged.emit()
        reuse_gop = bool(self._info.get("expensive_random_seek"))
        self._thumb_token = self._thumb_worker.submit(
            lambda check: filmstrip(path, start, end, pixels_per_second, check,
                                   reuse_gop=reuse_gop))

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
        self._pause_preview()
        self._displayed_playback_frame = None
        self._save_timer.stop()
        self._save()
        self._cache_timer.stop()
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
            try:
                self._close_preview_reader(check)
            finally:
                preview_done.set()

        self._preview_worker.submit(close_preview)
        preview_done.wait(3)
        self._preview_worker.close()
        self._audio.close()
