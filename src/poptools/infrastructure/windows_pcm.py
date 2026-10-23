"""Bounded Windows PCM output with explicit buffer and device ownership.

Qt 6.11.1's WASAPI worker leaves an MMCSS handle behind on each restart on Windows.
waveOut gives this short-lived preview stream deterministic reset/close semantics.
All methods run on the GUI thread; Windows owns playback of prepared buffers.
"""
from __future__ import annotations

import ctypes
import warnings
from collections import deque

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtMultimedia import QAudioFormat, QtAudio

# The application targets Python 3.11. This C routine scales only our stream;
# waveOutSetVolume can affect other streams on some Windows audio drivers.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import audioop


class _Format(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("tag", ctypes.c_ushort), ("channels", ctypes.c_ushort),
        ("rate", ctypes.c_uint32), ("byte_rate", ctypes.c_uint32),
        ("alignment", ctypes.c_ushort), ("bits", ctypes.c_ushort),
        ("extra", ctypes.c_ushort),
    ]


class _Header(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_void_p), ("length", ctypes.c_uint32),
        ("recorded", ctypes.c_uint32), ("user", ctypes.c_size_t),
        ("flags", ctypes.c_uint32), ("loops", ctypes.c_uint32),
        ("next", ctypes.c_void_p), ("reserved", ctypes.c_size_t),
    ]


class _Time(ctypes.Structure):
    # MMTIME's largest union member is an 8-byte SMPTE value.
    _fields_ = [("kind", ctypes.c_uint32), ("value", ctypes.c_uint32),
                ("padding", ctypes.c_uint32)]


def _api():
    api = ctypes.WinDLL("winmm")
    api.waveOutOpen.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32,
                               ctypes.POINTER(_Format), ctypes.c_size_t,
                               ctypes.c_size_t, ctypes.c_uint32]
    for name in ("waveOutPrepareHeader", "waveOutUnprepareHeader", "waveOutWrite"):
        getattr(api, name).argtypes = [ctypes.c_void_p, ctypes.POINTER(_Header), ctypes.c_uint]
    for name in ("waveOutReset", "waveOutClose"):
        getattr(api, name).argtypes = [ctypes.c_void_p]
    api.waveOutGetPosition.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Time), ctypes.c_uint]
    return api


class WindowsPcmSink:
    """Small QAudioSink-compatible surface for stereo signed 16-bit PCM."""

    # A driver error must never free memory that Windows still owns. Keep failed
    # closures alive until a later reset/close succeeds, including during shutdown.
    _pending_close: set[WindowsPcmSink] = set()

    def __init__(self, fmt: QAudioFormat):
        if fmt.channelCount() != 2 or fmt.sampleFormat() != QAudioFormat.SampleFormat.Int16:
            raise ValueError("Windows PCM output requires signed 16-bit stereo")
        self._api = _api()
        self._format = QAudioFormat(fmt)
        self._handle = ctypes.c_void_p()
        self._buffers = deque()
        self._queued_bytes = 0
        self._capacity = fmt.sampleRate() * 4 // 5
        self._volume = 1.0
        self._error = QtAudio.Error.NoError
        self._last_position = 0
        self._position_wrap = 0
        self._dirty = False
        self._retry_scheduled = False

    def format(self):
        return QAudioFormat(self._format)

    def setBufferSize(self, value):
        self._capacity = max(4, int(value) // 4 * 4)

    def setVolume(self, value):
        self._volume = max(0.0, min(1.0, value))

    def volume(self):
        return self._volume

    def start(self):
        if self._handle.value:
            self.reset()
            return self if self._error == QtAudio.Error.NoError else None
        rate = self._format.sampleRate()
        fmt = _Format(1, 2, rate, rate * 4, 4, 16, 0)
        result = self._api.waveOutOpen(
            ctypes.byref(self._handle), 0xFFFFFFFF, ctypes.byref(fmt), 0, 0, 0,
        )
        self._error = QtAudio.Error.OpenError if result else QtAudio.Error.NoError
        return None if result else self

    def _reap(self, reset=False):
        while self._buffers and (reset or self._buffers[0][0].flags & 1):  # WHDR_DONE
            header, data = self._buffers[0]
            if self._api.waveOutUnprepareHeader(
                self._handle, ctypes.byref(header), ctypes.sizeof(header),
            ):
                self._error = QtAudio.Error.IOError
                break  # Keep the backing memory alive while Windows owns it.
            self._buffers.popleft()
            self._queued_bytes -= header.length

    def bytesFree(self):
        self._reap()
        return max(0, self._capacity - self._queued_bytes) if self._handle.value else 0

    def write(self, payload):
        count = min(len(payload), self.bytesFree()) // 4 * 4
        if not count:
            return 0
        pcm = payload[:count]
        if self._volume != 1:
            pcm = audioop.mul(pcm, 2, self._volume)
        written = 0
        # Refill completed 20 ms blocks while other blocks remain queued. One
        # large block would empty the device between GUI-thread pump callbacks.
        chunk_size = max(4, self._format.sampleRate() // 50 * 4)
        for offset in range(0, count, chunk_size):
            chunk = pcm[offset:offset + chunk_size]
            data = ctypes.create_string_buffer(chunk)
            header = _Header(ctypes.cast(data, ctypes.c_void_p), len(chunk))
            size = ctypes.sizeof(header)
            if self._api.waveOutPrepareHeader(self._handle, ctypes.byref(header), size):
                self._error = QtAudio.Error.IOError
                return written or -1
            self._buffers.append((header, data))
            self._queued_bytes += len(chunk)
            self._dirty = True
            if self._api.waveOutWrite(self._handle, ctypes.byref(header), size):
                # A failed write never transfers this buffer to the device.
                if not self._api.waveOutUnprepareHeader(
                    self._handle, ctypes.byref(header), size,
                ):
                    self._buffers.pop()
                    self._queued_bytes -= len(chunk)
                self._error = QtAudio.Error.IOError
                return written or -1
            written += len(chunk)
        return written

    def processedUSecs(self):
        if not self._handle.value:
            return 0
        position = _Time(2, 0, 0)  # TIME_SAMPLES
        if self._api.waveOutGetPosition(
            self._handle, ctypes.byref(position), ctypes.sizeof(position),
        ):
            self._error = QtAudio.Error.IOError
            return 0
        if position.value < self._last_position:
            self._position_wrap += 1 << 32
        self._last_position = position.value
        value = self._position_wrap + position.value
        if position.kind == 2:
            return value * 1_000_000 // self._format.sampleRate()
        if position.kind == 4:  # TIME_BYTES
            return value * 1_000_000 // (self._format.sampleRate() * 4)
        if position.kind == 1:  # TIME_MS
            return value * 1000
        self._error = QtAudio.Error.IOError
        return 0

    def state(self):
        self._reap()
        if not self._handle.value:
            return QtAudio.State.StoppedState
        return QtAudio.State.ActiveState if self._buffers else QtAudio.State.IdleState

    def error(self):
        return self._error

    def reset(self):
        if self._handle.value and self._dirty:
            if self._api.waveOutReset(self._handle):
                self._error = QtAudio.Error.IOError
                return
            # A successful reset also permits releasing a prepared buffer whose
            # waveOutWrite failed, which need not have received WHDR_DONE.
            self._reap(reset=True)
            self._dirty = bool(self._buffers)
        self._last_position = self._position_wrap = 0

    def stop(self):
        self.reset()
        self._reap()
        if self._handle.value and not self._buffers:
            if not self._api.waveOutClose(self._handle):
                self._handle = ctypes.c_void_p()
            else:
                self._error = QtAudio.Error.IOError
        if self._handle.value:
            self._pending_close.add(self)
            if QCoreApplication.instance() is not None and not self._retry_scheduled:
                self._retry_scheduled = True
                QTimer.singleShot(100, self._retry_close)
        else:
            self._pending_close.discard(self)

    def _retry_close(self):
        self._retry_scheduled = False
        self.stop()

    def deleteLater(self):
        self.stop()

    def __del__(self):
        if getattr(self, "_handle", None) and self._handle.value:
            self.stop()
