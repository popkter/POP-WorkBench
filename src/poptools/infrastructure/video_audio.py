"""FFmpeg PCM decoding; Qt is used only for the system audio device."""
from __future__ import annotations

import threading
import time

import av
from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSink, QMediaDevices

from poptools.infrastructure.video_media import LatestWorker


class AudioPlayback(QObject):
    RATE = 48000
    BYTES_PER_SAMPLE = 4  # Interleaved stereo, signed 16 bit.

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = LatestWorker("video-audio")
        self.worker.failed.connect(self._failed)
        self.sink = None
        self.output = None
        self._lock = threading.Lock()
        self._buffer = bytearray()
        self._finished = False
        self._token = 0
        self.rate = 1.0
        self.volume = 0.8
        self.error = ""

    def _failed(self, token, message):
        if token == self._token:
            self.error = "音频解码失败：" + message
            self.stop()

    def start(self, path: str, position: float, origin: float, rate: float):
        self.stop()
        self.error = ""
        device = QMediaDevices.defaultAudioOutput()
        fmt = QAudioFormat()
        fmt.setSampleRate(round(self.RATE * rate))
        fmt.setChannelCount(2)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        if device.isNull() or not device.isFormatSupported(fmt):
            self.error = "当前音频设备不可用或不支持此倍速，继续播放画面"
            return
        self.rate = rate
        self.sink = QAudioSink(device, fmt, self)
        self.sink.setBufferSize(self.RATE * self.BYTES_PER_SAMPLE // 5)
        self.sink.setVolume(self.volume)
        self.output = self.sink.start()
        if self.output is None:
            self.error = "无法打开音频设备，继续播放画面"
            self.stop()
            return
        with self._lock:
            self._finished = False
        self._token = self.worker.submit(
            lambda check: self._decode(path, position, origin, check))

    def _decode(self, path, position, origin, check):
        def append(data):
            offset = 0
            while offset < len(data):
                check()
                with self._lock:
                    check()
                    free = self.RATE * self.BYTES_PER_SAMPLE - len(self._buffer)
                    count = min(free, len(data) - offset)
                    self._buffer.extend(data[offset:offset + count])
                    offset += count
                if not count:
                    time.sleep(0.01)

        with av.open(path) as container:
            stream = container.streams.audio[0]
            container.seek(int((position + origin) / stream.time_base), stream=stream,
                           backward=True)
            resampler = av.AudioResampler(format="s16", layout="stereo", rate=self.RATE)
            cursor = 0

            def write(frame):
                nonlocal cursor
                check()
                timestamp = float(frame.pts * frame.time_base) if frame.pts is not None else (
                    position + origin + cursor / self.RATE)
                start = round((timestamp - origin - position) * self.RATE)
                stop = start + frame.samples
                if stop <= cursor:
                    return
                while start > cursor:
                    gap = min(start - cursor, self.RATE // 10)
                    append(bytes(gap * self.BYTES_PER_SAMPLE))
                    cursor += gap
                trim = max(0, cursor - start)
                data = bytes(frame.planes[0])[:frame.samples * self.BYTES_PER_SAMPLE]
                append(data[trim * self.BYTES_PER_SAMPLE:])
                cursor = stop

            for frame in container.decode(stream):
                check()
                for pcm in resampler.resample(frame):
                    write(pcm)
            for pcm in resampler.resample(None):
                write(pcm)
            with self._lock:
                check()
                self._finished = True

    def pump(self):
        if not self.sink or not self.output:
            return
        with self._lock:
            count = min(self.sink.bytesFree(), len(self._buffer))
            if count > 0:
                written = self.output.write(bytes(self._buffer[:count]))
                if written > 0:
                    del self._buffer[:written]
        if self.sink.error() not in (QAudio.Error.NoError, QAudio.Error.UnderrunError):
            self.error = "音频设备已断开，继续播放画面"
            self.stop()

    def elapsed(self) -> float | None:
        if not self.sink:
            return None
        with self._lock:
            if self._finished and not self._buffer and self.sink.state() == QAudio.State.IdleState:
                return None
        return self.sink.processedUSecs() / 1_000_000 * self.rate

    def set_volume(self, value):
        self.volume = value
        if self.sink:
            self.sink.setVolume(value)

    def stop(self):
        self.worker.cancel()
        self._token = -1
        if self.sink:
            self.sink.stop()
            self.sink.deleteLater()
            self.sink = None
        self.output = None
        with self._lock:
            self._buffer.clear()

    def close(self):
        self.stop()
        self.worker.close()
