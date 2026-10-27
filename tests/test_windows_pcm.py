from __future__ import annotations

import ctypes
import sys

import pytest
from PySide6.QtMultimedia import QAudioFormat, QtAudio

from poptools.infrastructure import windows_pcm


def pcm_format():
    fmt = QAudioFormat()
    fmt.setSampleRate(48000)
    fmt.setChannelCount(2)
    fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    return fmt


class Device:
    def __init__(self):
        self.headers = []
        self.closed = 0
        self.opened = 0
        self.position = 0
        self.time_kind = 2
        self.write_error = 0
        self.reset_error = 0
        self.unprepare_error = 0
        self.close_error = 0

    def waveOutOpen(self, handle, *_):
        handle._obj.value = 123
        self.opened += 1
        return 0

    def waveOutPrepareHeader(self, handle, header, size):
        return 0

    def waveOutUnprepareHeader(self, handle, header, size):
        if self.unprepare_error:
            return self.unprepare_error
        if header._obj in self.headers:
            self.headers.remove(header._obj)
        return 0

    def waveOutWrite(self, handle, header, size):
        if not self.write_error:
            self.headers.append(header._obj)
        return self.write_error

    def waveOutGetPosition(self, handle, position, size):
        position._obj.kind = self.time_kind
        position._obj.value = self.position
        return 0

    def waveOutReset(self, handle):
        if self.reset_error:
            return self.reset_error
        for header in self.headers:
            header.flags |= 1
        self.position = 0
        return 0

    def waveOutClose(self, handle):
        assert not self.headers, "device buffers must be released before closing"
        if self.close_error:
            return self.close_error
        self.closed += 1
        return 0


@pytest.fixture
def sink(monkeypatch):
    device = Device()
    monkeypatch.setattr(windows_pcm, "_api", lambda: device)
    sink = windows_pcm.WindowsPcmSink(pcm_format())
    assert sink.start() is sink
    yield sink, device
    sink.stop()


def test_queue_is_bounded_and_preserves_pcm_until_driver_returns_buffers(sink):
    output, device = sink
    output.setBufferSize(19200)
    output.setVolume(.5)
    assert output.write(b"\x00\x40" * 20000) == 19200
    assert output.bytesFree() == 0
    assert output.write(bytes(400)) == 0
    assert len(device.headers) == 5
    for header in device.headers:
        assert ctypes.string_at(header.data, header.length) == b"\x00\x20" * (header.length // 2)
    device.headers[0].flags |= 1
    assert output.bytesFree() == 3840
    assert len(device.headers) == 4
    output.reset()
    assert output.bytesFree() == 19200
    assert output.state() == QtAudio.State.IdleState
    assert not device.headers
    assert output.start() is output
    assert device.opened == 1
    output.stop()
    output.stop()
    assert device.closed == 1
    assert output.state() == QtAudio.State.StoppedState


@pytest.mark.parametrize(("kind", "value"), [(2, 48000), (4, 192000), (1, 1000)])
def test_playback_clock_accepts_driver_time_formats(sink, kind, value):
    output, device = sink
    device.time_kind, device.position = kind, value
    assert output.processedUSecs() == 1_000_000


def test_playback_clock_handles_counter_wrap_and_reset(sink):
    output, device = sink
    device.position = (1 << 32) - 10
    before = output.processedUSecs()
    device.position = 10
    assert output.processedUSecs() > before
    output.reset()
    device.position = 0
    assert output.processedUSecs() == 0


def test_write_failure_releases_prepared_memory_and_reports_error(sink):
    output, device = sink
    device.write_error = 1
    assert output.write(bytes(3840)) == -1
    assert not output._buffers and not device.headers
    assert output.error() == QtAudio.Error.IOError


@pytest.mark.parametrize("failure", ["reset", "unprepare", "close"])
def test_driver_release_failure_keeps_buffers_alive_until_retry_succeeds(sink, qtbot, failure):
    output, device = sink
    assert output.write(bytes(3840)) == 3840
    setattr(device, f"{failure}_error", 1)
    output.stop()
    assert output in output._pending_close
    assert device.closed == 0
    if failure != "close":
        assert output._buffers and device.headers
        header, data = output._buffers[0]
        assert ctypes.string_at(header.data, header.length) == data.raw[:header.length]
    setattr(device, f"{failure}_error", 0)
    qtbot.waitUntil(lambda: device.closed == 1)
    assert not output._buffers and not device.headers
    assert output not in output._pending_close


def test_failed_write_and_unprepare_can_still_release_buffer_after_reset(sink, qtbot):
    output, device = sink
    device.write_error = device.unprepare_error = 1
    assert output.write(bytes(3840)) == -1
    assert output._buffers and not device.headers
    output.stop()
    assert output in output._pending_close
    device.unprepare_error = 0
    qtbot.waitUntil(lambda: device.closed == 1)
    assert not output._buffers and output not in output._pending_close


@pytest.mark.skipif(sys.platform != "win32", reason="Windows audio device reuse")
def test_audio_resume_reuses_device_and_releases_it_after_idle_or_device_change(
        qapp, qtbot, tmp_path, monkeypatch):
    import wave

    from poptools.infrastructure.video_audio import AudioPlayback, QMediaDevices

    path = tmp_path / "silence.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setparams((2, 2, 48000, 0, "NONE", "not compressed"))
        stream.writeframes(bytes(48000 * 4))

    native = Device()
    monkeypatch.setattr(windows_pcm, "_api", lambda: native)

    class OutputDevice:
        identity = b"first"

        def id(self):
            return self.identity

        def isNull(self):
            return False

        def isFormatSupported(self, _):
            return True

    device = OutputDevice()
    monkeypatch.setattr(QMediaDevices, "defaultAudioOutput", lambda: device)
    audio = AudioPlayback()
    try:
        audio.start(str(path), 0, 0, 1)
        first = audio.sink
        assert first is not None and not audio.error
        audio.stop()
        assert audio.sink is None and native.closed == 0
        audio.start(str(path), .1, 0, 1)
        assert audio.sink is first and native.opened == 1
        assert not audio._idle_timer.isActive()
        audio.stop()

        # A newly selected default device must not inherit the old open handle.
        device.identity = b"second"
        audio.start(str(path), .2, 0, 1)
        assert audio.sink is not first and native.closed == 1 and native.opened == 2
        audio._idle_timer.setInterval(10)
        audio.stop()
        qtbot.waitUntil(lambda: audio._idle_sink is None)
        assert native.closed == 2

        audio.start(str(path), .3, 0, 1)
        assert native.opened == 3
    finally:
        audio.close()
    assert native.closed == 3
    assert not audio._idle_timer.isActive()


@pytest.mark.hardware
@pytest.mark.skipif(sys.platform != "win32", reason="Windows audio lifecycle")
def test_real_audio_restart_does_not_accumulate_windows_handles(qapp, qtbot):
    import psutil
    from PySide6.QtMultimedia import QMediaDevices

    if QMediaDevices.defaultAudioOutput().isNull():
        pytest.skip("No audio output device on this host")
    process = psutil.Process()
    samples = []
    for _ in range(25):
        output = windows_pcm.WindowsPcmSink(pcm_format())
        try:
            assert output.start() is output
            assert output.write(bytes(38400)) == 38400
            qtbot.wait(25)
            assert output.processedUSecs() > 0
        finally:
            output.stop()
        qtbot.wait(20)
        samples.append(process.num_handles())
    # Ignore lazy system-audio initialization; steady restarts must stay bounded.
    assert samples[-1] <= samples[5] + 3, samples
