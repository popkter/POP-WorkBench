from __future__ import annotations

import logging
import os
import runpy
import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QColor, QFont, QFontDatabase, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtWidgets import QApplication

from poptools import __version__
from poptools.application import build_components
from poptools.infrastructure.app_logging import configure_application_logging
from poptools.infrastructure.app_updater import apply_pending_update
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_environment import prepare_managed_python
from poptools.infrastructure.single_instance import SingleInstanceLock
from poptools.infrastructure.system_tray import SystemTrayController
from poptools.infrastructure.window_chrome import WindowChromeController
from poptools.infrastructure.windows_integration import (
    apply_windows_title_bar_theme,
    apply_windows_window_icon,
    configure_windows_app_identity,
)
from poptools.native_terminal import register_terminal_type
from poptools.paths import AppPaths, package_root, prepare_bundled_android_tools, resource_path
from poptools.viewmodels.floating_launcher_controller import FloatingLauncherController


def _run_worker(arguments: list[str]) -> int:
    if not arguments:
        print("worker script is required", file=sys.stderr)
        return 2
    script = Path(arguments[0]).resolve()
    sys.argv = [str(script), *arguments[1:]]
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        print(f"worker failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _run_worker_code(arguments: list[str]) -> int:
    if not arguments:
        print("worker source is required", file=sys.stderr)
        return 2
    source = arguments[0]
    sys.argv = ["<poptools-inline>", *arguments[1:]]
    namespace = {"__name__": "__main__", "__file__": "<poptools-inline>", "__package__": None}
    try:
        exec(compile(source, "<poptools-inline>", "exec"), namespace)
    except SystemExit as exc:
        return int(exc.code or 0)
    except Exception as exc:
        print(f"worker failed: {exc}", file=sys.stderr)
        return 1
    return 0


def _terminal_working_directory(arguments: list[str]) -> Path | None:
    if "--terminal" not in arguments:
        return None
    try:
        index = arguments.index("--cwd")
        candidate = Path(arguments[index + 1]).expanduser().resolve()
    except (ValueError, IndexError, OSError):
        return Path.home().resolve()
    return candidate if candidate.is_dir() else Path.home().resolve()


def _prepare_installed_runtime() -> int:
    paths = AppPaths.from_environment()
    try:
        paths.ensure()
        if sys.platform == "win32":
            from poptools.infrastructure.plugin_service import PluginService
            service = PluginService(paths)
            service.migrate()
            service.seed()
        else:
            prepare_bundled_android_tools(paths)
            prepare_managed_python(paths)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"runtime preparation failed: {exc}", file=sys.stderr)
        paths.logs_dir.mkdir(parents=True, exist_ok=True)
        (paths.logs_dir / "plugin-preparation.log").write_text(str(exc), encoding="utf-8")
        return 1
    return 0


def main() -> int:
    if "--migrate-plugins" in sys.argv:
        from poptools.infrastructure.plugin_service import PluginService
        try:
            directory = Path(sys.argv[sys.argv.index("--migrate-plugins") + 1])
            PluginService(AppPaths.from_environment()).migrate(directory)
            return 0
        except Exception as exc:
            print(f"Plugin migration failed: {exc}", file=sys.stderr)
            logs = AppPaths.from_environment().logs_dir
            logs.mkdir(parents=True, exist_ok=True)
            (logs / "plugin-migration.log").write_text(str(exc), encoding="utf-8")
            return 1
    if "--prepare-runtime" in sys.argv:
        return _prepare_installed_runtime()

    if "--worker-code" in sys.argv:
        index = sys.argv.index("--worker-code")
        return _run_worker_code(sys.argv[index + 1 :])

    if "--worker" in sys.argv:
        index = sys.argv.index("--worker")
        return _run_worker(sys.argv[index + 1 :])

    terminal_directory = _terminal_working_directory(sys.argv[1:])

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    configure_windows_app_identity()
    QCoreApplication.setOrganizationName("PopTools")
    QCoreApplication.setApplicationName("泡泡工具箱")
    QCoreApplication.setApplicationVersion(__version__)
    paths = AppPaths.from_environment()
    logging_session = configure_application_logging(paths)
    logger = logging.getLogger(__name__)
    logger.info("应用正在启动")
    instance_lock = SingleInstanceLock(paths.data_dir / "poptools.lock")
    if not instance_lock.try_acquire():
        logger.info("已有实例运行，转为激活现有窗口")
        payload = {"action": "activate"}
        if terminal_directory is not None:
            payload = {"action": "open_terminal", "cwd": str(terminal_directory)}
        instance_lock.activate_running_instance(payload)
        logging_session.close()
        return 0

    try:
        app = QApplication(sys.argv)
        pending_update_result = apply_pending_update(
            ConfigStore(paths),
            __version__,
        )
        if pending_update_result == "launched":
            logger.info("已启动待安装更新，当前进程即将退出")
            return 0
        if pending_update_result == "failed":
            logger.warning("待安装更新启动失败，将打开当前版本供用户重试")
        elif pending_update_result == "invalid":
            logger.warning("待安装更新无效，已清除记录")
        elif pending_update_result == "stale":
            logger.info("待安装更新已应用或已过期，已清除记录")
        register_terminal_type()
        if not instance_lock.start_activation_server():
            logger.error("无法启动单实例激活服务")
            return 1
        app.setFont(QFont("Microsoft YaHei UI" if sys.platform == "win32" else "PingFang SC", 10))

        icon_font = resource_path("fonts", "MaterialIconsRound-Regular.otf")
        if icon_font.exists():
            QFontDatabase.addApplicationFont(str(icon_font))

        tray_controller = SystemTrayController(app)
        app.commitDataRequest.connect(
            lambda _session_manager: tray_controller.quit_application()
        )
        app.setWindowIcon(tray_controller.icon)

        python_setup_error = ""
        if sys.platform == "win32":
            from poptools.infrastructure.plugin_service import PluginService
            service = PluginService(paths)
            try:
                service.recover()
                service.migrate()
                service.seed()
            except (OSError, RuntimeError, ValueError) as exc:
                python_setup_error = str(exc)
                logger.exception("插件初始化失败，保留现有环境")
        else:
            prepare_bundled_android_tools(paths)
        if sys.platform != "win32" and getattr(sys, "frozen", False):
            try:
                prepare_managed_python(paths)
            except (OSError, RuntimeError, ValueError) as exc:
                python_setup_error = str(exc)
                logger.exception("Python 环境初始化失败")
        components = build_components(paths, terminal_working_directory=terminal_directory)
        controller = components.app_controller
        android_controller = components.android_controller
        settings_controller = components.settings_controller
        preset_controller = components.preset_controller
        jira_feishu_controller = components.jira_feishu_controller
        developer_console_controller = components.developer_console_controller
        update_controller = components.update_controller
        video_preview_controller = components.video_preview_controller
        app.aboutToQuit.connect(video_preview_controller.shutdown)
        app.aboutToQuit.connect(developer_console_controller.shutdown)
        app.aboutToQuit.connect(update_controller.shutdown)
        app.aboutToQuit.connect(jira_feishu_controller.shutdown)
        tray_controller.set_app_controller(controller)
        floating_controller = FloatingLauncherController(app, controller, settings_controller)
        if python_setup_error:
            settings_controller.setStatus(f"运行环境初始化失败：{python_setup_error}")

        engine = QQmlApplicationEngine()
        engine.addImageProvider("video", video_preview_controller.images)
        engine.rootContext().setContextProperty("videoPreviewController", video_preview_controller)
        engine.rootContext().setContextProperty("appController", controller)
        engine.rootContext().setContextProperty("settingsController", settings_controller)
        engine.rootContext().setContextProperty("presetController", preset_controller)
        engine.rootContext().setContextProperty(
            "jiraFeishuController", jira_feishu_controller
        )
        engine.rootContext().setContextProperty(
            "developerConsoleController", developer_console_controller
        )
        engine.rootContext().setContextProperty("androidController", android_controller)
        engine.rootContext().setContextProperty("trayController", tray_controller)
        engine.rootContext().setContextProperty("updateController", update_controller)
        engine.rootContext().setContextProperty("floatingController", floating_controller)
        qml_file = package_root() / "ui" / "qml" / "Main.qml"
        engine.load(QUrl.fromLocalFile(str(qml_file)))
        if not engine.rootObjects():
            logger.error("QML 主窗口加载失败：%s", qml_file)
            return 1
        window = cast(QWindow, engine.rootObjects()[0])
        _window_chrome = WindowChromeController(window)
        window.setIcon(tray_controller.icon)
        apply_windows_window_icon(
            int(window.winId()), str(resource_path("icons", "app-icon.ico"))
        )
        def sync_title_bar_theme() -> None:
            apply_windows_title_bar_theme(
                int(window.winId()),
                dark_mode=settings_controller.darkTheme,
                background_color=cast(QColor, window.property("chromeBackgroundColor")),
                foreground_color=cast(QColor, window.property("chromeForegroundColor")),
            )

        sync_title_bar_theme()
        for property_name in ("chromeBackgroundColor", "chromeForegroundColor"):
            getattr(window, f"{property_name}Changed").connect(sync_title_bar_theme)
        tray_controller.attach_window(window)
        floating_controller.attach_main_window(window)

        def handle_activation(payload: dict[str, object]) -> None:
            tray_controller.show_window()
            if payload.get("action") != "open_terminal":
                return
            directory = payload.get("cwd")
            if isinstance(directory, str):
                window.setProperty("developerSelected", True)
                developer_console_controller.openTerminalAtDirectory(directory)
                if not developer_console_controller.pluginInstalled:
                    developer_console_controller.requestTerminalAccess()

        instance_lock.set_activation_handler(handle_activation)
        controller.attach_window(window)
        if terminal_directory is not None:
            window.setProperty("developerSelected", True)
            if developer_console_controller.pluginInstalled:
                developer_console_controller.ensureStarted()
            else:
                developer_console_controller.requestTerminalAccess()
        exit_code = app.exec()
        logger.info("应用正常退出，退出码：%s", exit_code)
        return exit_code
    finally:
        instance_lock.release()
        logging_session.close()


if __name__ == "__main__":
    raise SystemExit(main())
