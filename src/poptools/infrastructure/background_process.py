from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class BackgroundProcess(QObject):
    """Run a child process through Qt's event loop without worker-thread races."""

    started = Signal()
    stdoutReady = Signal(bytes)
    stderrReady = Signal(bytes)
    errorOccurred = Signal(str)
    finished = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._close_stdin = False

    @property
    def running(self) -> bool:
        return (
            self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning
        )

    @property
    def process_id(self) -> int:
        return int(self._process.processId()) if self._process is not None else 0

    def start(
        self,
        program: str,
        arguments: Sequence[str],
        *,
        cwd: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
        close_stdin: bool = False,
    ) -> bool:
        if self._process is not None:
            self.errorOccurred.emit("进程已启动")
            return False

        process = QProcess(self)
        process.setProgram(program)
        process.setArguments(list(arguments))
        if cwd is not None:
            process.setWorkingDirectory(str(cwd))
        if environment is not None:
            process_environment = QProcessEnvironment()
            for key, value in environment.items():
                process_environment.insert(key, value)
            process.setProcessEnvironment(process_environment)
        process.readyReadStandardOutput.connect(self._read_stdout)
        process.readyReadStandardError.connect(self._read_stderr)
        process.started.connect(self._on_started)
        process.errorOccurred.connect(self._on_error)
        process.finished.connect(self._on_finished)
        self._process = process
        self._close_stdin = close_stdin
        process.start()
        return True

    def terminate(self) -> None:
        if self.running and self._process is not None:
            self._process.terminate()

    def kill(self) -> None:
        if self.running and self._process is not None:
            self._process.kill()

    def shutdown(self) -> None:
        """Reap a child before the application event loop exits."""
        process = self._process
        if process is not None:
            process.kill()
            process.waitForFinished(1000)

    def _read_stdout(self) -> None:
        if self._process is None:
            return
        payload = bytes(self._process.readAllStandardOutput().data())
        if payload:
            self.stdoutReady.emit(payload)

    def _read_stderr(self) -> None:
        if self._process is None:
            return
        payload = bytes(self._process.readAllStandardError().data())
        if payload:
            self.stderrReady.emit(payload)

    def _on_error(self, error: QProcess.ProcessError) -> None:
        process = self._process
        if process is None:
            return
        self.errorOccurred.emit(process.errorString())
        if error == QProcess.ProcessError.FailedToStart:
            self._process = None
            process.deleteLater()
            self.finished.emit(-1)

    def _on_started(self) -> None:
        if self._process is None:
            return
        if self._close_stdin:
            self._process.closeWriteChannel()
        self.started.emit()

    def _on_finished(self, exit_code: int, _status: QProcess.ExitStatus) -> None:
        process = self._process
        if process is None:
            return
        self._read_stdout()
        self._read_stderr()
        self._process = None
        process.deleteLater()
        self.finished.emit(exit_code)
