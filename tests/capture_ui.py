from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import cast

from PySide6.QtCore import QMetaObject, QObject, QTimer, QUrl
from PySide6.QtGui import QColor, QFont, QFontDatabase, QImage, QWindow
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication

from poptools.infrastructure.android_device_service import AndroidDevice, AndroidDeviceService
from poptools.infrastructure.app_updater import UpdateRelease
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.infrastructure.system_tray import SystemTrayController
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.infrastructure.window_chrome import WindowChromeController
from poptools.infrastructure.windows_integration import apply_windows_title_bar_theme
from poptools.native_terminal import register_terminal_type
from poptools.paths import AppPaths, package_root, resource_path
from poptools.runners import ExecutionCoordinator, ExecutionManager
from poptools.viewmodels import (
    AndroidController,
    AppController,
    DeveloperConsoleController,
    JiraFeishuController,
    PresetController,
    SettingsController,
    UpdateController,
)


def grab_native_window_frame(window: QWindow) -> QImage:
    """Capture the target's native frame even when another window overlaps it."""
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    signatures = (
        (user32.GetWindowRect, [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)], ctypes.c_int),
        (user32.GetWindowDC, [ctypes.c_void_p], ctypes.c_void_p),
        (user32.ReleaseDC, [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_int),
        (user32.PrintWindow, [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint], ctypes.c_int),
        (gdi32.CreateCompatibleDC, [ctypes.c_void_p], ctypes.c_void_p),
        (gdi32.CreateCompatibleBitmap,
         [ctypes.c_void_p, ctypes.c_int, ctypes.c_int], ctypes.c_void_p),
        (gdi32.SelectObject, [ctypes.c_void_p, ctypes.c_void_p], ctypes.c_void_p),
        (gdi32.DeleteObject, [ctypes.c_void_p], ctypes.c_int),
        (gdi32.DeleteDC, [ctypes.c_void_p], ctypes.c_int),
    )
    for function, argument_types, result_type in signatures:
        function.argtypes = argument_types
        function.restype = result_type
    hwnd = ctypes.c_void_p(int(window.winId()))
    frame = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(frame)):
        raise OSError(ctypes.get_last_error(), "Cannot get the preview window frame")
    source_dc = user32.GetWindowDC(hwnd)
    memory_dc = gdi32.CreateCompatibleDC(source_dc)
    bitmap = gdi32.CreateCompatibleBitmap(
        source_dc, frame.right - frame.left, frame.bottom - frame.top
    )
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        if not user32.PrintWindow(hwnd, memory_dc, 2):  # PW_RENDERFULLCONTENT
            raise OSError(ctypes.get_last_error(), "Cannot capture the preview window frame")
        return QImage.fromHBITMAP(bitmap).copy()
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(hwnd, source_dc)


def main() -> int:
    output_path = Path(sys.argv[1] if len(sys.argv) > 1 else "implementation.png").resolve()
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    app = QApplication(sys.argv)
    register_terminal_type()
    system_font = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "msyh.ttc"
    if system_font.exists():
        QFontDatabase.addApplicationFont(str(system_font))
    app.setFont(QFont("Microsoft YaHei UI", 10))
    icon_font = resource_path("fonts", "MaterialIconsRound-Regular.otf")
    if icon_font.exists():
        QFontDatabase.addApplicationFont(str(icon_font))

    paths = AppPaths.from_environment()
    config_store = ConfigStore(paths)
    config_store.load_config()
    repository = JsonToolRepository(paths)
    registry = ToolRegistry(resource_path("tools"), repository)
    if os.environ.get("POPTOOLS_CAPTURE_GRID_SAMPLE") == "1":
        samples = (
            ("挂载设备", "使用 Remount 挂载 Android 设备", "batch"),
            ("同步时间到设备", "同步电脑时间并校准设备时钟", "powershell"),
            ("点亮 EX-G 屏幕", "唤醒并点亮测试设备屏幕", "python"),
            ("开启点按位置", "显示设备触摸点与坐标", "batch"),
            ("清除本地 CRASH 计数", "清理本地崩溃统计数据", "powershell"),
            ("发送文本到 ASR", "向语音识别服务发送测试文本", "python"),
            ("打开系统设置", "快速打开 Android 系统设置", "batch"),
            ("监听设备进程", "持续观察目标进程运行状态", "powershell"),
            ("查看进程 dumpsys 信息", "读取进程诊断与内存信息", "batch"),
            ("设置台架环境", "配置台架设备与网络参数", "python"),
            ("导出设备日志", "收集并导出当前设备日志", "powershell"),
            ("检查网络连接", "验证设备网络与服务连通性", "batch"),
        )
        for title, description, kind in samples:
            registry.create_custom(
                title=title,
                description=description,
                kind=kind,
                command="Write-Output preview",
            )
    python_environment = PythonEnvironment(paths, config_store)
    execution = ExecutionManager(paths, python_environment)
    coordinator = ExecutionCoordinator(execution, config_store.max_parallel())
    device_service = None
    if os.environ.get("POPTOOLS_CAPTURE_ANDROID_DEVICES"):
        class CaptureDeviceService(AndroidDeviceService):
            def refresh(self) -> None:
                self._set_devices([
                    AndroidDevice(serial, model=f"Android_{index + 1}")
                    for index, serial in enumerate(
                        os.environ["POPTOOLS_CAPTURE_ANDROID_DEVICES"].split(",")
                    )
                ])

        device_service = CaptureDeviceService()
    android_controller = AndroidController(config_store, device_service)
    controller = AppController(registry, coordinator, config_store, android_controller)
    settings_controller = SettingsController(config_store, python_environment, coordinator)
    if os.environ.get("POPTOOLS_CAPTURE_DIALOG") == "settings":
        settings_controller.markUserGuideSeen()
    if os.environ.get("POPTOOLS_CAPTURE_GRID_SAMPLE") == "1":
        settings_controller.markUserGuideSeen()
    preset_controller = PresetController()
    jira_feishu_controller = JiraFeishuController(paths.data_dir)
    developer_console_controller = DeveloperConsoleController(python_environment)
    app.aboutToQuit.connect(developer_console_controller.shutdown)
    app.aboutToQuit.connect(jira_feishu_controller.shutdown)
    capture_terminal_tabs = int(os.environ.get("POPTOOLS_CAPTURE_TERMINAL_TABS", "1"))
    for _ in range(max(1, capture_terminal_tabs) - 1):
        developer_console_controller.createTerminalTab()
    update_controller = UpdateController(config_store, auto_check_enabled=False)
    capture_update_status = os.environ.get("POPTOOLS_CAPTURE_UPDATE_STATUS")
    if capture_update_status == "latest":
        update_controller._set_state("idle", "当前已是最新版本")
    elif capture_update_status == "checking":
        update_controller._set_state("checking", "正在检查更新…")
    if len(sys.argv) > 2 and sys.argv[2] in {"developer", "powershell-plugin", "update"}:
        settings_controller.markUserGuideSeen()
    if len(sys.argv) > 2 and sys.argv[2] == "update":
        update_controller._on_check_completed(
            UpdateRelease(
                version="99.0.0",
                tag="v99.0.0",
                name="泡泡工具箱 99.0.0（界面预览）",
                notes="新增应用内自动更新功能。\n\n修复已知问题并优化启动性能。",
                page_url="https://github.com/popkter/PopToolProject/releases/tag/v0.2.0",
                asset_url="https://example.test/app.exe",
                asset_name="泡泡工具箱.exe",
                asset_size=191_000_000,
            ),
            "",
        )
    capture_theme = os.environ.get("POPTOOLS_CAPTURE_THEME", "").strip()
    if capture_theme:
        settings_controller.saveThemeMode(capture_theme)
    capture_theme_style = os.environ.get("POPTOOLS_CAPTURE_THEME_STYLE", "").strip()
    if capture_theme_style:
        settings_controller.saveThemeStyle(capture_theme_style)
    settings_controller.scriptsImported.connect(controller.reloadImportedScripts)
    settings_controller.consoleMessage.connect(controller.appendConsoleMessage)
    tray_controller = SystemTrayController(app)
    if len(sys.argv) > 2 and sys.argv[2] not in {"developer", "powershell-plugin", "update"}:
        controller.navigate(sys.argv[2])
    if len(sys.argv) > 3:
        if sys.argv[3] == "__dynamic__":
            tool = registry.create_custom(
                title="ADB 密码命令",
                description="使用动态密码参数执行 ADB 命令",
                kind="powershell",
                command="adb shell ${输入密码}",
            )
            controller.selectTool(tool.id)
        else:
            controller.selectTool(sys.argv[3])
    engine = QQmlApplicationEngine()
    qml_warnings: list[str] = []
    engine.warnings.connect(
        lambda warnings: qml_warnings.extend(warning.toString() for warning in warnings)
    )
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
    if os.environ.get("POPTOOLS_CAPTURE_JIRA_LONG_JQL") == "1":
        jira_feishu_controller.updateField(
            "jira",
            "jql_filter",
            "\n".join(
                f'AND summary ~ "scroll verification line {index:02d}"'
                for index in range(1, 25)
            ),
        )
    engine.load(QUrl.fromLocalFile(str(package_root() / "ui" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("\n".join(qml_warnings), file=sys.stderr)
        return 1
    window = cast(QWindow, engine.rootObjects()[0])
    _window_chrome = WindowChromeController(window)
    window.setIcon(tray_controller.icon)
    apply_windows_title_bar_theme(
        int(window.winId()),
        dark_mode=settings_controller.darkTheme,
        background_color=cast(QColor, window.property("chromeBackgroundColor")),
        foreground_color=cast(QColor, window.property("chromeForegroundColor")),
    )
    if len(sys.argv) > 3 and sys.argv[3] != "__dynamic__":
        QTimer.singleShot(350, lambda: controller.selectTool(sys.argv[3]))
    if os.environ.get("POPTOOLS_CAPTURE_JIRA_OUTPUT_MAX") == "1":
        jira_workspace = window.findChild(QObject, "jiraFeishuWorkspace")
        if jira_workspace is not None:
            QTimer.singleShot(
                250,
                lambda: jira_workspace.setProperty("outputExpanded", True),
            )
    if len(sys.argv) > 2 and sys.argv[2] == "developer":
        if os.environ.get("POPTOOLS_CAPTURE_EMPTY_TERMINAL") == "1":
            def close_preview_tabs() -> None:
                for tab in developer_console_controller.terminalTabs:
                    developer_console_controller.closeTerminalTab(tab["tabId"])

            QTimer.singleShot(400, close_preview_tabs)
        window.setProperty("developerSelected", True)
        if os.environ.get("POPTOOLS_CAPTURE_TERMINAL_MENU") == "1":
            def open_terminal_menu() -> None:
                menu = window.findChild(QObject, "terminalContextMenu")
                if menu is None:
                    return
                menu.setProperty("x", 620)
                menu.setProperty("y", 100)
                QMetaObject.invokeMethod(menu, "open")

            QTimer.singleShot(650, open_terminal_menu)
        if os.environ.get("POPTOOLS_CAPTURE_TERMINAL_SAMPLE") == "faint":
            QTimer.singleShot(
                400,
                lambda: developer_console_controller._append(
                    "\r\nnormal text  \x1b[97;2;3mhint: adb shell\x1b[0m\r\n"
                ),
            )
    elif len(sys.argv) > 2 and sys.argv[2] == "powershell-plugin":
        QTimer.singleShot(100, developer_console_controller.requestTerminalAccess)
    tray_controller.attach_window(window)
    controller.attach_window(window)
    capture_size = os.environ.get("POPTOOLS_CAPTURE_SIZE", "")
    if "x" in capture_size:
        capture_width, capture_height = capture_size.lower().split("x", maxsplit=1)
        window.setWidth(int(capture_width))
        window.setHeight(int(capture_height))
        window.setX(0)
        window.setY(0)
    if os.environ.get("POPTOOLS_CAPTURE_WINDOW_FRAME") == "1":
        window.setPosition(60, 60)
        window.raise_()
        window.requestActivate()
        if os.environ.get("POPTOOLS_CAPTURE_COMPOSITED_FRAME") == "1" and sys.platform == "win32":
            user32 = ctypes.WinDLL("user32")
            user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_uint]
            user32.SetWindowPos(int(window.winId()), ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0013)
    capture_primary_nav_width = os.environ.get("POPTOOLS_CAPTURE_PRIMARY_NAV_WIDTH", "")
    if capture_primary_nav_width:
        window.setProperty("primaryNavWidth", int(capture_primary_nav_width))
        QMetaObject.invokeMethod(window, "clampPanelWidths")
    if os.environ.get("POPTOOLS_CAPTURE_COMPACT_PRIMARY_NAV") == "1":
        window.setProperty("compactPrimaryNav", True)
    if os.environ.get("POPTOOLS_CAPTURE_CUSTOM_DRAWER") == "1":
        custom_tools = registry.for_section("custom")
        if custom_tools:
            controller.selectTool(custom_tools[0].id)
            if os.environ.get("POPTOOLS_CAPTURE_CLOSING_DRAWER") == "1":
                custom_scripts_page = window.findChild(QObject, "customScriptsPage")
                QTimer.singleShot(
                    1400,
                    lambda: custom_scripts_page is not None
                    and QMetaObject.invokeMethod(custom_scripts_page, "closeDrawer"),
                )
    capture_dialog = os.environ.get("POPTOOLS_CAPTURE_DIALOG")
    if capture_dialog == "user-guide":
        QTimer.singleShot(250, lambda: QMetaObject.invokeMethod(window, "openUserGuideDialog"))
        if os.environ.get("POPTOOLS_CAPTURE_GUIDE_PREVIEW") == "1":
            def show_guide_preview() -> None:
                window.findChild(QObject, "userGuideDialog").setProperty("sectionIndex", 2)

            def scroll_guide_preview() -> None:
                scroll = window.findChild(QObject, "guideScroll")
                scroll.setProperty(
                    "contentY", max(0, scroll.property("contentHeight") - scroll.property("height"))
                )

            QTimer.singleShot(500, show_guide_preview)
            QTimer.singleShot(800, scroll_guide_preview)
    if capture_dialog == "script-editor":
        QTimer.singleShot(250, lambda: QMetaObject.invokeMethod(window, "openCommandEditorForEdit"))
    if capture_dialog == "delete-script":
        QTimer.singleShot(250, lambda: QMetaObject.invokeMethod(window, "openDeleteCommandDialog"))
    if capture_dialog == "confirm-run":
        QTimer.singleShot(250, lambda: window.openConfirmRunDialog({}))
    if capture_dialog == "recent-tool":
        QTimer.singleShot(450, lambda: controller.recentToolDialogRequested.emit(
            controller.selectedTool["id"]
        ))
    if os.environ.get("POPTOOLS_CAPTURE_DEVICE_MENU") == "1":
        def open_device_menu() -> None:
            selector = next((item for item in window.findChildren(QObject, "toolDeviceSelector")
                             if item.property("visible")), None)
            if selector is not None:
                QMetaObject.invokeMethod(selector, "openDeviceMenu")

        QTimer.singleShot(650, open_device_menu)
    if capture_dialog == "settings":
        window.openSettingsDialog()
        if os.environ.get("POPTOOLS_CAPTURE_SETTINGS_BOTTOM") == "1":
            def scroll_settings_to_bottom() -> None:
                settings_dialog = window.findChild(QObject, "settingsDialog")
                if settings_dialog is None:
                    return
                QMetaObject.invokeMethod(settings_dialog, "scrollToBottom")
                if os.environ.get("POPTOOLS_CAPTURE_UPDATE_DEBUG") == "1":
                    update_button = settings_dialog.findChild(
                        QObject, "updateCheckButton"
                    )
                    if update_button is not None:
                        print(
                            "update-button:",
                            update_button.property("text"),
                            update_button.property("latestState"),
                            update_button.property("iconSpinning"),
                            update_controller.state,
                            update_controller.status,
                        )
                    if qml_warnings:
                        print("\n".join(qml_warnings))

            QTimer.singleShot(300, scroll_settings_to_bottom)
        if os.environ.get("POPTOOLS_CAPTURE_SETTINGS_UPDATE_AVAILABLE") == "1":
            def complete_manual_update_check() -> None:
                settings_dialog = window.findChild(QObject, "settingsDialog")
                if settings_dialog is None:
                    return
                settings_dialog.setProperty("manualUpdateCheckPending", True)
                update_controller._check_is_manual = True
                update_controller._on_check_completed(
                    UpdateRelease(
                        version="99.0.0",
                        tag="v99.0.0",
                        name="泡泡工具箱 99.0.0",
                        notes="用于界面验证的更新说明。",
                        page_url="https://example.test/release",
                        asset_url="https://example.test/PopTools.exe",
                        asset_name="PopTools.exe",
                        asset_size=100,
                    ),
                    "",
                )

            QTimer.singleShot(350, complete_manual_update_check)
    if capture_dialog == "update":
        QTimer.singleShot(250, lambda: QMetaObject.invokeMethod(window, "queueUpdateDialog"))
    if capture_dialog == "custom-import":
        def open_custom_import_dialog() -> None:
            dialog = window.findChild(QObject, "customScriptImportDialog")
            if dialog is not None:
                dialog.openForReplacement(
                    {
                        "title": "APK 本地签名",
                        "existingTitle": "APK 本地签名",
                    }
                )

        QTimer.singleShot(250, open_custom_import_dialog)

    def capture() -> None:
        if os.environ.get("POPTOOLS_CAPTURE_QML_WARNINGS") == "1" and qml_warnings:
            print("\n".join(qml_warnings), file=sys.stderr)
        target_window = window
        if capture_dialog == "recent-tool":
            target_window = next(
                (item for item in app.allWindows() if item.objectName() == "recentToolWindow"),
                window,
            )
        screen = target_window.screen() or app.primaryScreen()
        if os.environ.get("POPTOOLS_CAPTURE_COMPOSITED_FRAME") == "1":
            # PrintWindow captures rectangular surface pixels before DWM clips
            # the corners. Capture the composed desktop to verify real rounding
            # and the system shadow, keeping a small margin around the window.
            frame = target_window.frameGeometry()
            image = screen.grabWindow(
                0, frame.x() - 12, frame.y() - 12, frame.width() + 24, frame.height() + 24,
            ).toImage()
        elif os.environ.get("POPTOOLS_CAPTURE_WINDOW_FRAME") == "1":
            if sys.platform == "win32":
                image = grab_native_window_frame(target_window)
            else:
                frame = target_window.frameGeometry()
                image = screen.grabWindow(
                    0, frame.x(), frame.y(), frame.width(), frame.height()
                ).toImage()
        else:
            image = (target_window.grabWindow()
                     if capture_dialog == "recent-tool" and isinstance(target_window, QQuickWindow)
                     else screen.grabWindow(target_window.winId()).toImage())
        if image.isNull() or not image.save(str(output_path)):
            app.exit(2)
            return
        app.quit()

    QTimer.singleShot(1500, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
