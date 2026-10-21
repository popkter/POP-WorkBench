from __future__ import annotations

import codecs
import os
import re
import shlex
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices

from poptools.domain.models import ExecutorKind, ParameterKind, ToolDefinition
from poptools.domain.parameter_templates import render_template, validate_parameter_value
from poptools.infrastructure.background_process import BackgroundProcess
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.paths import AppPaths, bundled_adb_path, package_root, resource_path

ANSI_ESCAPE_PATTERN = re.compile(
    r"\x1B(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1B\\))"
)


class ExecutionManager(QObject):
    output = Signal(str)
    started = Signal()
    runningChanged = Signal(bool)
    finished = Signal(int)

    def __init__(
        self, paths: AppPaths, python_environment: PythonEnvironment | None = None
    ) -> None:
        super().__init__()
        self.paths = paths
        self.python_environment = python_environment or PythonEnvironment(paths, ConfigStore(paths))
        self._process: BackgroundProcess | None = None
        self._encoding = "utf-8"
        self._stdout_decoder: codecs.IncrementalDecoder | None = None
        self._stderr_decoder: codecs.IncrementalDecoder | None = None
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)
        self._timed_out = False
        self._timeout_milliseconds: int | None = None
        self._output_dir: Path | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.running

    @property
    def active(self) -> bool:
        """Whether a launch is starting or running and still owns this manager."""
        return self._process is not None

    def start(self, tool: ToolDefinition, values: dict[str, Any]) -> bool:
        if self.running:
            self.output.emit("已有任务正在运行，请先停止。\n")
            return False
        values = dict(values)
        try:
            for parameter in tool.parameters:
                values[parameter.id] = validate_parameter_value(
                    parameter, values.get(parameter.id, parameter.default)
                )
        except ValueError as exc:
            self.output.emit(f"{exc}\n")
            return False
        missing = [
            parameter.label
            for parameter in tool.parameters
            if parameter.required and values.get(parameter.id) in (None, "")
        ]
        if missing:
            self.output.emit(f"缺少必填参数：{', '.join(missing)}\n")
            return False
        if tool.executor.kind == ExecutorKind.URL:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self._resolve_source(tool.executor.command)))
            )
            self.output.emit("已使用默认浏览器打开结果。\n")
            self.started.emit()
            self.finished.emit(0)
            return True
        if tool.executor.kind == ExecutorKind.INTERNAL:
            self.output.emit("该功能由应用内部服务执行。\n")
            self.started.emit()
            self.finished.emit(0)
            return True

        output_dir = self.paths.outputs_dir / uuid.uuid4().hex
        self._output_dir = output_dir
        launch = self._build_launch(tool, values, output_dir)
        if launch is None:
            self._cleanup_empty_output_dir()
            return False
        program, arguments = launch
        output_dir.mkdir(parents=True, exist_ok=True)

        process = BackgroundProcess(self)
        environment = self._build_environment(tool, values, output_dir)
        process.stdoutReady.connect(self._read_stdout)
        process.stderrReady.connect(self._read_stderr)
        process.started.connect(self._on_started)
        process.errorOccurred.connect(self._on_error)
        process.finished.connect(self._on_finished)
        self._process = process
        self._encoding = tool.executor.encoding
        self._stdout_decoder = codecs.getincrementaldecoder(self._encoding)(errors="replace")
        self._stderr_decoder = codecs.getincrementaldecoder(self._encoding)(errors="replace")
        self._timed_out = False
        self._timeout_milliseconds = (
            tool.executor.timeout_seconds * 1000
            if tool.executor.timeout_seconds is not None
            else None
        )
        if tool.executor.kind == ExecutorKind.BATCH:
            pass
        elif tool.executor.kind == ExecutorKind.PYTHON and arguments[:1] in (
            ["-c"],
            ["--worker-code"],
        ):
            self.output.emit(f"> {program} [内联 Python 脚本]\n")
        else:
            self.output.emit(f"> {self._format_launch_for_log(tool, program, arguments, values)}\n")
        started = process.start(
            program,
            arguments,
            cwd=tool.executor.cwd or str(output_dir),
            environment={key: environment.value(key) for key in environment.keys()},  # noqa: SIM118
            close_stdin=tool.executor.kind == ExecutorKind.BATCH,
        )
        if not started:
            self._process = None
            self.runningChanged.emit(False)
            self._cleanup_empty_output_dir()
            self.finished.emit(-1)
            return False
        return True

    def stop(self) -> None:
        if self._process is None:
            return
        pid = self._process.process_id
        if os.name == "nt" and pid:
            QProcess.startDetached("taskkill", ["/PID", str(pid), "/T", "/F"])
        else:
            self._process.terminate()
        QTimer.singleShot(2000, self._kill_if_running)

    def _build_launch(
        self,
        tool: ToolDefinition,
        values: dict[str, Any],
        output_dir: Path | None = None,
    ) -> tuple[str, list[str]] | None:
        executor = tool.executor
        if executor.kind == ExecutorKind.PROCESS:
            command_parts = self._split_command(executor.command)
            if not command_parts:
                self.output.emit("命令内容不能为空\n")
                return None
            rendered_command = self._render(command_parts[0], values)
            arguments = self._render_args([*command_parts[1:], *executor.args], values)
        else:
            rendered_command = self._render(executor.command, values)
            arguments = self._render_args(executor.args, values)
        if executor.kind == ExecutorKind.PROCESS:
            program = self._resolve_program(rendered_command)
        elif executor.kind == ExecutorKind.PYTHON:
            command_parts = self._split_command(rendered_command)
            if not command_parts:
                self.output.emit("命令内容不能为空\n")
                return None
            program = self.python_environment.execution_executable()
            if not program:
                self.output.emit("Python 插件不可用，请在设置的插件管理中安装。\n")
                return None
            source = self._resolve_source(command_parts[0])
            if source.is_file():
                arguments = self._render_args([*command_parts[1:], *executor.args], values)
                arguments = [str(source), *arguments]
            else:
                arguments = ["-c", rendered_command, *arguments]
        elif executor.kind == ExecutorKind.POWERSHELL:
            if sys.platform == "win32":
                from poptools.infrastructure.plugin_service import PluginService
                service = PluginService(self.paths)
                program = (
                    str(service.executable("powershell"))
                    if service.available("powershell") else None
                )
                if not program:
                    self.output.emit("请在设置的插件管理中安装 PowerShell。\n")
                    return None
            else:
                program = shutil.which("pwsh") or shutil.which("powershell")
            utf8_setup = (
                "$OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            )
            arguments = [
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                utf8_setup + rendered_command,
            ]
        elif executor.kind == ExecutorKind.BASH:
            program = self._find_bash()
            arguments = ["-lc", rendered_command]
        elif executor.kind == ExecutorKind.BATCH:
            program = shutil.which("cmd")
            batch_source = self._resolve_source(rendered_command)
            if "\n" not in rendered_command and batch_source.is_file():
                batch_file = batch_source
            else:
                batch_dir = output_dir or self.paths.outputs_dir / uuid.uuid4().hex
                batch_dir.mkdir(parents=True, exist_ok=True)
                batch_file = batch_dir / "command.bat"
                batch_text = rendered_command.replace("\r\n", "\n").replace("\r", "\n")
                batch_file.write_text(batch_text, encoding="utf-8", newline="\r\n")
            arguments = ["/d", "/q", "/c", str(batch_file)]
        else:
            program = None
        if not program:
            self.output.emit(f"运行环境不可用：{executor.kind.value}\n")
            return None
        return str(program), arguments

    def _build_environment(
        self,
        tool: ToolDefinition,
        values: dict[str, Any],
        output_dir: Path,
    ) -> QProcessEnvironment:
        environment = QProcessEnvironment.systemEnvironment()
        environment.insert("PYTHONUTF8", "1")
        environment.insert("PYTHONIOENCODING", "utf-8")
        environment.insert("PYTHONUNBUFFERED", "1")
        environment.insert("NO_COLOR", "1")
        environment.insert("TERM", "dumb")
        environment.insert("POPTOOLS_OUTPUT_DIR", str(output_dir))
        environment.insert("POPTOOLS_EXECUTABLE", sys.executable)
        environment.insert("POPTOOLS_RESOURCE_ROOT", str(package_root() / "resources"))
        environment.insert("POPTOOLS_FROZEN", "1" if getattr(sys, "frozen", False) else "0")
        adb = self._resolve_program("adb")
        if adb:
            environment.insert("POPTOOLS_ADB", adb)
            current_path = environment.value("PATH")
            environment.insert("PATH", f"{Path(adb).parent}{os.pathsep}{current_path}")
        for key, value in tool.executor.env.items():
            environment.insert(key, self._render(value, values))
        if tool.executor.kind == ExecutorKind.PYTHON:
            self._configure_managed_python_environment(environment)
        selected_device = str(values.get("__android_device__", "")).strip()
        if selected_device:
            environment.insert("ANDROID_SERIAL", selected_device)
        return environment

    def _configure_managed_python_environment(
        self, environment: QProcessEnvironment
    ) -> None:
        values = {key: environment.value(key) for key in environment.keys()}  # noqa: SIM118
        for key, value in self.python_environment.execution_environment(values).items():
            environment.insert(key, value)

    def _resolve_program(self, command: str) -> str | None:
        if command.lower() == "adb":
            bundled = bundled_adb_path()
            if bundled.exists():
                return str(bundled)
            if sys.platform == "win32":
                self.output.emit("请在设置的插件管理中安装 Android 工具（ADB + scrcpy）。\n")
                return None
            prepared = sorted(
                (
                    candidate
                    for candidate in self.paths.runtime_dir.glob(
                        f"scrcpy-*/{bundled_adb_path().name}"
                    )
                    if candidate.is_file()
                ),
                key=lambda candidate: candidate.stat().st_mtime,
                reverse=True,
            )
            if prepared:
                return str(prepared[0])
        path = Path(command)
        if path.is_absolute() and path.exists():
            return str(path)
        return shutil.which(command)

    def _resolve_source(self, source: str) -> Path:
        path = Path(source)
        if path.is_absolute():
            return path
        candidate = Path(resource_path(source))
        return candidate if candidate.exists() else package_root() / source

    def _find_bash(self) -> str | None:
        candidates = (
            shutil.which("bash"),
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
        )
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(candidate)
        return None

    def _render_args(self, templates: list[str], values: dict[str, Any]) -> list[str]:
        rendered: list[str] = []
        for template in templates:
            if template.startswith("?") and ":" in template:
                parameter, payload = template[1:].split(":", 1)
                if not values.get(parameter):
                    continue
                template = payload
            rendered.append(self._render(template, values))
        return rendered

    @staticmethod
    def _render(template: str, values: dict[str, Any]) -> str:
        return render_template(template, values)

    @staticmethod
    def _split_command(command: str) -> list[str]:
        lexer = shlex.shlex(command, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        lexer.escape = ""
        return list(lexer)

    def _read_stdout(self, payload: bytes) -> None:
        self.output.emit(self._clean_output(payload, self._stdout_decoder))

    def _read_stderr(self, payload: bytes) -> None:
        self.output.emit(self._clean_output(payload, self._stderr_decoder))

    def _clean_output(
        self,
        payload: bytes,
        decoder: codecs.IncrementalDecoder | None = None,
    ) -> str:
        if decoder is None:
            text = payload.decode(self._encoding, "replace")
        else:
            text = decoder.decode(payload, final=False)
        return ANSI_ESCAPE_PATTERN.sub("", text)

    def _on_error(self, message: str) -> None:
        self.output.emit(f"启动失败：{message}\n")

    def _on_started(self) -> None:
        if self._timeout_milliseconds is not None:
            self._timeout_timer.start(self._timeout_milliseconds)
        self.started.emit()
        self.runningChanged.emit(True)

    def _on_finished(self, exit_code: int) -> None:
        process = self._process
        if process is None:
            return
        self._timeout_timer.stop()
        self._flush_decoder(self._stdout_decoder)
        self._flush_decoder(self._stderr_decoder)
        if self._timed_out:
            self.output.emit(f"\n任务因超时结束，退出码：{exit_code}\n")
        else:
            self.output.emit(f"\n任务结束，退出码：{exit_code}\n")
        self._process = None
        self._stdout_decoder = None
        self._stderr_decoder = None
        self._timeout_milliseconds = None
        self._cleanup_empty_output_dir()
        process.deleteLater()
        self.runningChanged.emit(False)
        self.finished.emit(exit_code)

    def _cleanup_empty_output_dir(self) -> None:
        output_dir = self._output_dir
        self._output_dir = None
        if output_dir is None:
            return
        try:
            output_dir.rmdir()
        except OSError:
            # Preserve files intentionally written by the executed tool.
            pass

    def _flush_decoder(self, decoder: codecs.IncrementalDecoder | None) -> None:
        if decoder is None:
            return
        text = decoder.decode(b"", final=True)
        if text:
            self.output.emit(ANSI_ESCAPE_PATTERN.sub("", text))

    def _on_timeout(self) -> None:
        if not self.running:
            return
        self._timed_out = True
        self.output.emit("任务已达到运行超时，正在停止进程。\n")
        self.stop()

    @staticmethod
    def _format_launch_for_log(
        tool: ToolDefinition,
        program: str,
        arguments: list[str],
        values: dict[str, Any],
    ) -> str:
        if tool.executor.kind == ExecutorKind.POWERSHELL:
            return subprocess.list2cmdline([program, "[内联 PowerShell 脚本]"])
        command = subprocess.list2cmdline([program, *arguments])
        secret_values = {
            str(values.get(parameter.id, parameter.default))
            for parameter in tool.parameters
            if parameter.kind == ParameterKind.SECRET
            and values.get(parameter.id, parameter.default) not in (None, "")
        }
        for secret in sorted(secret_values, key=len, reverse=True):
            command = command.replace(secret, "***")
        return command

    def _kill_if_running(self) -> None:
        if self.running and self._process is not None:
            self._process.kill()
