"""Cancellable pip preparation and installation using the Qt process loop."""
from __future__ import annotations

import codecs

from PySide6.QtCore import QObject, QTimer, Signal

from poptools.infrastructure.background_process import BackgroundProcess


class PythonDependencyInstall(QObject):
    output = Signal(str)
    completed = Signal(bool, str)
    statusChanged = Signal(str)
    CHECK_TIMEOUT_MS = 20_000
    REPAIR_TIMEOUT_MS = 120_000
    INSTALL_TIMEOUT_MS = 600_000

    def __init__(self, executable: str, packages: list[str], parent=None) -> None:
        super().__init__(parent)
        self.executable = executable
        self.packages = packages
        self._process: BackgroundProcess | None = None
        self._stage = ""
        self._error = ""
        self._stderr = ""
        self._done = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    def start(self) -> None:
        self._start_stage("check", ["-m", "pip", "--version"], self.CHECK_TIMEOUT_MS)

    def _start_stage(self, stage: str, arguments: list[str], timeout: int) -> None:
        if self._done:
            return
        self._stage = stage
        self._stderr = ""
        self._error = ""
        self.statusChanged.emit({"check": "正在检查 pip…", "repair": "正在准备 pip…",
                                 "verify": "正在验证 pip…", "install": "正在安装依赖…"}[stage])
        process = BackgroundProcess(self)
        self._process = process
        stdout_decoder = codecs.getincrementaldecoder("utf-8")("replace")
        stderr_decoder = codecs.getincrementaldecoder("utf-8")("replace")

        def output(payload: bytes, error: bool = False) -> None:
            text = (stderr_decoder if error else stdout_decoder).decode(payload)
            if error:
                self._stderr = (self._stderr + text)[-8000:]
            if text:
                self.output.emit(text)

        def finished(code: int) -> None:
            self._timer.stop()
            self._process = None
            process.deleteLater()
            for decoder in (stdout_decoder, stderr_decoder):
                tail = decoder.decode(b"", final=True)
                if tail:
                    self.output.emit(tail)
            if self._error:
                self._finish(False, self._error)
            elif stage == "check" and code != 0:
                self._start_stage("repair", ["-m", "ensurepip", "--upgrade"],
                                  self.REPAIR_TIMEOUT_MS)
            elif code != 0:
                self._finish(False, self._stderr.strip() or f"退出码 {code}")
            elif stage == "repair":
                self._start_stage("verify", ["-m", "pip", "--version"], self.CHECK_TIMEOUT_MS)
            elif stage in {"check", "verify"}:
                self._start_stage("install", ["-m", "pip", "install", *self.packages],
                                  self.INSTALL_TIMEOUT_MS)
            else:
                self._finish(True, "依赖安装完成")

        process.stdoutReady.connect(output)
        process.stderrReady.connect(lambda payload: output(payload, True))
        process.errorOccurred.connect(self._on_error)
        process.finished.connect(finished)
        self._timer.start(timeout)
        if not process.start(self.executable, arguments, close_stdin=True):
            self._timer.stop()
            self._process = None
            process.deleteLater()
            self._finish(False, self._error or "无法启动 Python")

    def _on_error(self, message: str) -> None:
        if not self._error:
            self._error = message

    def _timeout(self) -> None:
        self._error = "Python 依赖操作超时"
        if self._process:
            self._process.kill()

    def cancel(self) -> None:
        self._timer.stop()
        self._error = "Python 依赖安装已取消"
        if self._process:
            self._process.kill()
        elif not self._done:
            self._finish(False, self._error)

    def shutdown(self) -> None:
        process = self._process
        self.cancel()
        if process is not None:
            process.shutdown()

    def _finish(self, success: bool, message: str) -> None:
        if self._done:
            return
        self._done = True
        self._timer.stop()
        self.completed.emit(success, message)
