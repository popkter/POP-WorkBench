from __future__ import annotations

import shlex

from PySide6.QtCore import QObject, QTimer, Signal, Slot

from poptools.infrastructure.background_process import BackgroundProcess
from poptools.infrastructure.python_dependency_install import PythonDependencyInstall
from poptools.infrastructure.python_doctor import (
    PythonDoctor,
    PythonDoctorResult,
    pip_package_names,
)


class PythonDependencyController(QObject):
    consoleMessage = Signal(str)
    pythonDoctorWarning = Signal(str)
    pythonDoctorInstallSuggestion = Signal(str)
    pythonDependencyInstallFinished = Signal(bool, str)
    installStatusChanged = Signal(str)

    def __init__(self, environment, doctor: PythonDoctor, parent=None):
        super().__init__(parent)
        self.environment = environment
        self._python_doctor = doctor
        self._python_doctor_command = ""
        self._python_doctor_process = None
        self._python_package_install = None
        self.plugin_mutation_active = lambda: False

    def check(self, command: str) -> bool:
        if getattr(self, "plugin_mutation_active", lambda: False)():
            self.pythonDoctorWarning.emit("插件正在变更，请等待操作完成后再检查依赖。")
            return False
        if self._python_doctor_process is not None:
            self.consoleMessage.emit("Python Doctor：正在检查依赖，请稍候。\n")
            return False
        self._python_doctor_command = command
        plan = self._python_doctor.prepare(command)
        if plan.immediate_result is not None:
            self._report_python_doctor_result(plan.immediate_result)
            return True
        executable = self.environment.executable()
        if not executable:
            self._report_python_doctor_result(
                PythonDoctorResult(
                    checked_modules=plan.checked_modules,
                    environment_error="Python 插件不可用，请在设置的插件管理中安装或修复",
                )
            )
            return True
        if not plan.modules_to_check:
            self._report_python_doctor_result(
                PythonDoctorResult(checked_modules=plan.checked_modules),
                executable,
            )
            return True

        process = BackgroundProcess(self)
        self._python_doctor_process = process
        stdout = bytearray()
        stderr = bytearray()
        errors: list[str] = []
        timed_out = [False]
        timeout = QTimer(process)
        timeout.setSingleShot(True)

        def stop_on_timeout() -> None:
            timed_out[0] = True
            process.kill()

        def finish(exit_code: int) -> None:
            self._python_doctor_process = None
            timeout.stop()
            if timed_out[0]:
                result = PythonDoctorResult(
                    checked_modules=plan.checked_modules,
                    environment_error="依赖检查超时",
                )
            else:
                error_text = stderr.decode("utf-8", "replace")
                if errors:
                    error_text = "\n".join([error_text, *errors]).strip()
                result = self._python_doctor.complete_probe(
                    plan,
                    exit_code,
                    stdout.decode("utf-8", "replace"),
                    error_text,
                )
            self._report_python_doctor_result(result, executable)
            process.deleteLater()

        process.stdoutReady.connect(stdout.extend)
        process.stderrReady.connect(stderr.extend)
        process.errorOccurred.connect(errors.append)
        process.finished.connect(finish)
        timeout.timeout.connect(stop_on_timeout)
        self.consoleMessage.emit("Python Doctor：正在异步检查依赖…\n")
        started = process.start(
            executable,
            ["-c", self._python_doctor.probe_source(), *plan.modules_to_check],
        )
        timeout.start(20_000)
        return started

    def _report_python_doctor_result(
        self,
        result: PythonDoctorResult,
        executable: str | None = None,
    ) -> None:
        executable = executable or self.environment.executable()
        if result.environment_error:
            message = f"Python Doctor 无法检查所选环境：{result.environment_error}"
            self.consoleMessage.emit(f"{message}\n")
            self.pythonDoctorWarning.emit(
                f"Python 环境无法完成检查。\n\n{result.environment_error}\n\n"
                "请确认应用专属 Python 环境已准备完成。"
            )
        elif result.missing_modules:
            modules = "、".join(result.missing_modules)
            package_names = " ".join(pip_package_names(result.missing_modules))
            install_command = f'"{executable}" -m pip install {package_names}'
            message = f"Python Doctor 发现缺失依赖：{modules}"
            self.consoleMessage.emit(f"{message}\n> {install_command}\n")
            self.pythonDoctorWarning.emit(
                f"当前 Python 环境缺少以下依赖模块：{modules}\n\n"
                "是否确认使用应用内 Python 环境安装？"
            )
            self.pythonDoctorInstallSuggestion.emit(package_names)
        elif result.syntax_error:
            message = f"Python Doctor 无法完成检查，脚本存在语法错误：{result.syntax_error}"
            self.consoleMessage.emit(f"{message}\n")
            self.pythonDoctorWarning.emit(
                f"脚本已创建，但 Python Doctor 无法完成依赖检查。\n\n{result.syntax_error}"
            )
        else:
            self.consoleMessage.emit("Python Doctor：未发现缺失依赖。\n")

    @Slot(str, result=bool)
    def installPythonDependencies(self, package_text: str) -> bool:
        """Install packages into the interpreter currently used by user scripts."""
        if getattr(self, "plugin_mutation_active", lambda: False)():
            self.pythonDependencyInstallFinished.emit(False, "插件正在变更，请稍后重试。")
            return False
        if self._python_package_install is not None:
            return False
        executable = self.environment.executable()
        if not executable:
            message = "Python 插件不可用，请先在设置的插件管理中安装。"
            self.consoleMessage.emit(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False
        try:
            packages = shlex.split(package_text.strip(), posix=False)
        except ValueError as exc:
            message = f"包名格式无效：{exc}"
            self.consoleMessage.emit(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False
        packages = [package.strip().strip('"') for package in packages if package.strip()]
        if not packages or any(package.startswith("-") for package in packages):
            message = "请填写有效的 pip 包名，不要填写命令选项。"
            self.consoleMessage.emit(f"Python 依赖安装失败：{message}\n")
            self.pythonDependencyInstallFinished.emit(False, message)
            return False

        job = PythonDependencyInstall(executable, packages, self)
        self._python_package_install = job
        job.output.connect(self.consoleMessage)
        job.statusChanged.connect(self.installStatusChanged)

        def finish(success: bool, message: str) -> None:
            self._python_package_install = None
            self.consoleMessage.emit(message + "\n")
            self.pythonDependencyInstallFinished.emit(success, message)
            job.deleteLater()
            if success and self._python_doctor_command:
                self.check(self._python_doctor_command)

        job.completed.connect(finish)
        job.start()
        return True

    @Slot()
    def cancelInstall(self) -> None:
        if self._python_package_install is not None:
            self._python_package_install.cancel()

    def usage_reason(self) -> str:
        if self._python_doctor_process is not None:
            return "请先等待 Python 依赖诊断完成"
        if self._python_package_install is not None:
            return "请先等待 Python 依赖安装完成"
        return ""

    def shutdown(self) -> None:
        if self._python_package_install is not None:
            self._python_package_install.shutdown()
        if self._python_doctor_process is not None:
            self._python_doctor_process.shutdown()
