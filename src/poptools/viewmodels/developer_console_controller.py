from __future__ import annotations

import codecs
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import (
    Property,
    QObject,
    QTimer,
    QUrl,
    Signal,
    Slot,
)

from poptools.infrastructure.conpty import ConPtySession
from poptools.infrastructure.managed_powershell import ManagedPowerShell
from poptools.infrastructure.plugin_service import PluginService
from poptools.infrastructure.python_environment import PythonEnvironment
from poptools.paths import bundled_adb_path, resource_path
from poptools.viewmodels.plugin_controller import PluginController

logger = logging.getLogger(__name__)


@dataclass
class TerminalTabState:
    tab_id: str
    shell_title: str
    working_directory: Path
    custom_title: str | None = None
    group_id: str = ""
    session: ConPtySession | None = None
    output: str = ""
    exit_code: int = 0
    restart_pending: bool = False
    intentional_stop: bool = False
    directory_report_tail: bytes = b""
    output_decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")(errors="replace")
    )

    @property
    def title(self) -> str:
        return self.custom_title or self.shell_title


@dataclass
class TerminalGroup:
    title: str
    color: str
    collapsed: bool = False


class DeveloperConsoleController(QObject):
    """Native terminal backed by Windows ConPTY or a macOS POSIX PTY."""

    OUTPUT_HISTORY_LIMIT = 131_072
    GROUP_COLORS = ("slate", "blue", "red", "amber", "green", "pink", "purple", "teal")
    # xterm/ConPTY sequences for Ctrl+F11 and Ctrl+F12. The PowerShell profile
    # handles these chords internally, so toggling never echoes a command.
    POWER_SHELL_HISTORY_LIST_VIEW_COMMAND = "\x1b[23;5~"
    POWER_SHELL_HISTORY_DISABLED_COMMAND = "\x1b[24;5~"
    TERMINAL_SYNTAX_COLOR_DEFAULTS = {
        "default": "#E5E7EB",
        "command": "#66AFFF",
        "warning": "#FFCE66",
        "string": "#29AF6F",
        "semantic": "#6F42C1",
        "operator": "#159B95",
        "error": "#FF8585",
        "muted": "#728298",
    }
    _HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")
    _DIRECTORY_REPORT = re.compile(
        rb"\x1b\]7;(?P<uri>[^\x00-\x1f\x7f]{0,8192})(?:\x07|\x1b\\)"
        rb"|(?P<partial>\x1b\]7;[^\x00-\x1f\x7f]{0,8192}\x1b?|\x1b\]7|\x1b\]|\x1b)\Z"
    )

    outputChanged = Signal()
    terminalData = Signal(str, str)
    terminalSnapshotData = Signal(str, str)
    terminalResetRequested = Signal(str)
    terminalSessionRemoved = Signal(str)
    runningChanged = Signal()
    pluginStateChanged = Signal()
    pluginInstallPromptRequested = Signal(str, str)
    pluginInstallFinished = Signal(bool, str)
    terminalAccessGranted = Signal()
    terminalTabsChanged = Signal()
    terminalGroupCreatedByDrop = Signal(str)
    powerShellHistoryListViewEnabledChanged = Signal()
    terminalTabLayoutChanged = Signal()
    terminalSidebarWidthChanged = Signal()

    def __init__(
        self,
        python_environment: PythonEnvironment,
        working_directory: Path | None = None,
        powershell_plugin: ManagedPowerShell | None = None,
        parent: QObject | None = None,
        *, plugin_manager: PluginController | None = None,
    ) -> None:
        super().__init__(parent)
        self.python_environment = python_environment
        self._terminal_tab_layout = python_environment.config_store.terminal_tab_layout()
        self._terminal_sidebar_width = python_environment.config_store.terminal_sidebar_width()
        self.working_directory = self._normalize_working_directory(working_directory)
        self._tabs: list[TerminalTabState] = []
        self._groups: dict[str, TerminalGroup] = {}
        self._closing_tabs: dict[str, TerminalTabState] = {}
        self._active_tab_id = ""
        self._next_tab_number = 1
        self._terminal_ready = False
        self._terminal_columns = 120
        self._terminal_rows = 30
        self._terminal_syntax_colors = self.TERMINAL_SYNTAX_COLOR_DEFAULTS.copy()
        self._power_shell_history_list_view_enabled = (
            python_environment.config_store.terminal_history_list_view_enabled()
        )
        self._shutdown_pending = False
        self._plugin_manager = plugin_manager
        self._owns_plugin_manager = False
        self._plugin = powershell_plugin
        if self._plugin is None and sys.platform == "win32":
            if self._plugin_manager is None:
                self._plugin_manager = PluginController(
                    PluginService(python_environment.paths), self,
                )
                self._owns_plugin_manager = True
            self._plugin = ManagedPowerShell(
                self._plugin_manager.service, self._plugin_manager.runtime,
            )
        self._managed_terminal_install_requested = False
        if self._plugin_manager is not None:
            self._plugin_manager.changed.connect(self.pluginStateChanged)
            self._plugin_manager.completed.connect(self.onManagedPluginCompleted)
        self._restore_open_terminal_groups()
        if not self._tabs:
            self._create_tab(activate=True)

    @Property(str, notify=outputChanged)
    def output(self) -> str:
        tab = self._active_tab()
        return tab.output if tab is not None else ""

    @Property(str, notify=terminalTabLayoutChanged)
    def terminalTabLayout(self) -> str:
        return self._terminal_tab_layout

    @Property(int, notify=terminalSidebarWidthChanged)
    def terminalSidebarWidth(self) -> int:
        return self._terminal_sidebar_width

    @Slot(str)
    def setTerminalTabLayout(self, layout: str) -> None:
        if layout not in ("horizontal", "vertical") or layout == self._terminal_tab_layout:
            return
        self.python_environment.config_store.set_terminal_tab_layout(
            layout, self._terminal_sidebar_width)
        self._terminal_tab_layout = layout
        self.terminalTabLayoutChanged.emit()

    @Slot(int)
    def setTerminalSidebarWidth(self, width: int) -> None:
        width = max(140, min(360, width))
        if width == self._terminal_sidebar_width:
            return
        self.python_environment.config_store.set_terminal_tab_layout(
            self._terminal_tab_layout, width)
        self._terminal_sidebar_width = width
        self.terminalSidebarWidthChanged.emit()

    @Property(bool, notify=runningChanged)
    def running(self) -> bool:
        tab = self._active_tab()
        return tab is not None and tab.session is not None

    @Property(list, notify=terminalTabsChanged)
    def terminalTabs(self) -> list[dict[str, object]]:
        return [
            {
                "tabId": tab.tab_id,
                "title": tab.title,
                "hasCustomTitle": tab.custom_title is not None,
                "active": tab.tab_id == self._active_tab_id,
                "running": tab.session is not None,
                "groupId": tab.group_id,
            }
            for tab in self._tabs
        ]

    @Property(list, notify=terminalTabsChanged)
    def terminalTabGroups(self) -> list[dict[str, object]]:
        active = self._active_tab()
        return [
            {
                "groupId": group_id,
                "title": group.title,
                "color": group.color,
                "collapsed": group.collapsed,
                "active": active is not None and active.group_id == group_id,
            }
            for group_id, group in self._groups.items()
        ]

    @Property(str, notify=terminalTabsChanged)
    def activeTerminalTabId(self) -> str:
        return self._active_tab_id

    @Property(bool, notify=terminalTabsChanged)
    def canCreateTerminalTab(self) -> bool:
        return True

    @Property(str, notify=pluginStateChanged)
    def pythonExecutable(self) -> str:
        return self.python_environment.execution_executable() or "不可用"

    @Property(str, constant=True)
    def environmentDirectory(self) -> str:
        return str(self.python_environment.paths.python_venv_dir)

    @Property(bool, notify=pluginStateChanged)
    def pluginInstalled(self) -> bool:
        return self._plugin is None or self._plugin.is_installed()

    @Property(bool, notify=pluginStateChanged)
    def pluginInstalling(self) -> bool:
        return (self._plugin_manager.operation_state("powershell")[0]
                if self._plugin_manager else False)

    @Property(int, notify=pluginStateChanged)
    def pluginInstallProgress(self) -> int:
        return self._plugin_manager.operation_state("powershell")[1] if self._plugin_manager else 0

    @Property(str, notify=pluginStateChanged)
    def pluginInstallStatus(self) -> str:
        return self._plugin_manager.operation_state("powershell")[2] if self._plugin_manager else ""

    @Property(str, notify=pluginStateChanged)
    def pluginVersion(self) -> str:
        return self._plugin.package.version if self._plugin is not None else "macOS Shell"

    @Property(str, notify=pluginStateChanged)
    def pluginDirectory(self) -> str:
        return str(self._plugin.install_directory) if self._plugin is not None else ""

    @Property(str, constant=True)
    def terminalName(self) -> str:
        return self._terminal_name()

    @Property(bool, notify=powerShellHistoryListViewEnabledChanged)
    def powerShellHistoryListViewEnabled(self) -> bool:
        return self._power_shell_history_list_view_enabled

    @staticmethod
    def _terminal_name() -> str:
        return "PowerShell 7" if sys.platform == "win32" else "macOS Shell"

    @staticmethod
    def _default_tab_title() -> str:
        return "PowerShell" if sys.platform == "win32" else "macOS Shell"

    @Property(int, constant=True)
    def windowsBuildNumber(self) -> int:
        if sys.platform != "win32":
            return 0
        return int(sys.getwindowsversion().build)

    @Slot(result=bool)
    def requestTerminalAccess(self) -> bool:
        if self._plugin is None:
            self.terminalAccessGranted.emit()
            return True
        if self.pluginInstalled:
            self.terminalAccessGranted.emit()
            return True
        self.pluginInstallPromptRequested.emit(
            self.pluginVersion,
            self.pluginDirectory,
        )
        return False

    @Slot(result=bool)
    def installPowerShellPlugin(self) -> bool:
        if self._plugin_manager:
            self._managed_terminal_install_requested = self._plugin_manager.operate(
                "powershell", "install"
            )
            return self._managed_terminal_install_requested
        if self._plugin is None:
            self.terminalAccessGranted.emit()
            return True
        if self.pluginInstalled:
            self.pluginInstallFinished.emit(True, "PowerShell 7 插件已安装。")
            self.terminalAccessGranted.emit()
            return True
        self.pluginInstallFinished.emit(False, "插件管理器不可用")
        return False

    @Slot(result=bool)
    def cancelPowerShellPluginInstall(self) -> bool:
        if self._plugin_manager:
            self._plugin_manager.cancel("powershell")
            return True
        return False

    def onManagedPluginCompleted(self, plugin, success, message):
        if plugin == "powershell" and self._managed_terminal_install_requested:
            self._managed_terminal_install_requested = False
            self.pluginInstallFinished.emit(success, message)
            if success and self.pluginInstalled:
                self.terminalAccessGranted.emit()

    @Slot(result=bool)
    def ensureStarted(self) -> bool:
        tab = self._active_tab()
        if tab is None:
            return False
        return self._ensure_tab_started(tab)

    def _ensure_tab_started(self, tab: TerminalTabState) -> bool:
        if self._plugin_manager and self._plugin_manager.mutating:
            self._append_to_tab(tab, "插件正在变更，请等待操作完成后再打开终端。\n")
            return False
        if tab not in self._tabs or self._shutdown_pending:
            return False
        if tab.session is not None:
            return True
        if not self.pluginInstalled:
            message = "PowerShell 不可用，请在设置中安装插件或指定有效的本地环境。\n"
            if not tab.output.endswith(message):
                self._append_to_tab(tab, message)
            return False
        python_executable = self.python_environment.execution_executable()
        pip_executable = self.python_environment.executable()
        if self._plugin is None:
            shell = Path(os.environ.get("SHELL") or "/bin/zsh")
            arguments = ["-i"]
        else:
            shell = self._plugin.executable
            # Keep PowerShell's normal startup behavior so the four standard
            # $PROFILE scopes are loaded before the PopTools bootstrap script.
            arguments = [
                "-NoLogo",
                "-NoExit",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(resource_path("tools", "powershell-terminal-profile.ps1")),
            ]
        environment = self._terminal_environment()
        environment.update(
            {
                "POPTOOLS_PYTHON": python_executable or "",
                "POPTOOLS_PIP": pip_executable or "",
                "PYTHONUTF8": "1",
                "PYTHONIOENCODING": "utf-8",
                "PYTHONUNBUFFERED": "1",
                "TERM": "xterm-256color",
            }
        )
        if self._plugin is not None:
            environment["POPTOOLS_PS_HISTORY_LIST_VIEW"] = (
                "1" if self._power_shell_history_list_view_enabled else "0"
            )
            environment.update(
                {
                    f"POPTOOLS_PS_COLOR_{name.upper()}": color
                    for name, color in self._terminal_syntax_colors.items()
                }
            )

        tab.shell_title = self._default_tab_title()
        session = ConPtySession(self)
        tab.output_decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        tab.directory_report_tail = b""
        session.outputReceived.connect(self._on_terminal_output)
        session.processExited.connect(self._on_process_exited)
        session.finished.connect(self._on_session_finished)
        tab.session = session
        tab.intentional_stop = False
        tab.exit_code = 0
        try:
            session.start_process(
                shell,
                arguments,
                tab.working_directory,
                environment,
                columns=self._terminal_columns,
                rows=self._terminal_rows,
            )
        except Exception as exc:
            tab.session = None
            session.dispose()
            session.deleteLater()
            self._append_to_tab(tab, f"终端启动失败：{exc}\r\n")
            self.terminalTabsChanged.emit()
            self.runningChanged.emit()
            return False
        self.terminalTabsChanged.emit()
        self.runningChanged.emit()
        return True

    def _terminal_environment(self) -> dict[str, str]:
        environment = self.python_environment.execution_environment()
        environment.pop("POPTOOLS_ADB", None)
        adb_executable = bundled_adb_path()
        if adb_executable.is_file():
            environment["POPTOOLS_ADB"] = str(adb_executable)
            environment["PATH"] = os.pathsep.join(
                (str(adb_executable.parent), environment.get("PATH", ""))
            )
        return environment

    @Slot("QVariantMap")
    def configureTerminalSyntaxColors(self, colors: dict[str, object]) -> None:
        """Store theme colors for PowerShell sessions created after this call."""
        self._terminal_syntax_colors = {
            name: self._normalized_terminal_color(colors.get(name), fallback)
            for name, fallback in self.TERMINAL_SYNTAX_COLOR_DEFAULTS.items()
        }

    @classmethod
    def _normalized_terminal_color(cls, value: object, fallback: str) -> str:
        color = value if isinstance(value, str) else ""
        return color.upper() if cls._HEX_COLOR_PATTERN.fullmatch(color) else fallback

    @Slot(bool, result=bool)
    def setPowerShellHistoryListViewEnabled(self, enabled: bool) -> bool:
        if self._plugin is None:
            return False
        enabled = bool(enabled)
        changed = enabled != self._power_shell_history_list_view_enabled
        if changed:
            self.python_environment.config_store.set_terminal_history_list_view_enabled(enabled)
        self._power_shell_history_list_view_enabled = enabled
        command = (
            self.POWER_SHELL_HISTORY_LIST_VIEW_COMMAND
            if enabled
            else self.POWER_SHELL_HISTORY_DISABLED_COMMAND
        ).encode("utf-8")
        wrote = False
        for tab in self._tabs:
            if tab.session is not None:
                wrote = tab.session.write(command) or wrote
        if not wrote:
            tab = self._active_tab()
            if tab is not None:
                wrote = self._ensure_tab_started(tab)
        if changed:
            self.powerShellHistoryListViewEnabledChanged.emit()
        return wrote

    @Slot(str, result=bool)
    def writeInput(self, data: str) -> bool:
        tab = self._active_tab()
        if tab is None:
            return False
        return self._write_input_to_tab(tab, data)

    @Slot(str, str, result=bool)
    def writeInputToTab(self, tab_id: str, data: str) -> bool:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return False
        return self._write_input_to_tab(tab, data)

    @Slot("QVariantList", result=str)
    def formatDroppedPaths(self, urls: list[object]) -> str:
        """Return local file URLs as safely quoted PowerShell arguments."""
        quoted_paths: list[str] = []
        for value in urls:
            url = value if isinstance(value, QUrl) else QUrl(str(value))
            if not url.isLocalFile():
                continue
            path = url.toLocalFile()
            if not path:
                continue
            quoted_paths.append("'" + path.replace("'", "''") + "'")
        if not quoted_paths:
            return ""
        # PSReadLine's current buffer is owned by the child process. Prefixing
        # a separator safely appends arguments, and is harmless at an empty prompt.
        return " " + " ".join(quoted_paths)

    @Slot(str, str, result=bool)
    def updateTerminalTitle(self, tab_id: str, title: str) -> bool:
        # Keep the slot connected for native terminal compatibility, but do not
        # let shell-reported paths replace the stable default tab title.
        return self._tab_by_id(tab_id) is not None

    @Slot(str, str, result=bool)
    def renameTerminalTab(self, tab_id: str, title: str) -> bool:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return False
        custom_title = title.strip() or None
        if tab.custom_title == custom_title:
            return True
        tab.custom_title = custom_title
        self.terminalTabsChanged.emit()
        return True

    @Slot(str, result=bool)
    def resetTerminalTabTitle(self, tab_id: str) -> bool:
        return self.renameTerminalTab(tab_id, "")

    @Slot(int, result=bool)
    def activateRelativeTerminalTab(self, offset: int) -> bool:
        active = self._active_tab()
        visible = [tab for tab in self._tabs if self._is_tab_visible(tab) or tab is active]
        if not visible:
            return False
        current_index = visible.index(active) if active is not None else 0
        target = visible[(current_index + offset) % len(visible)]
        if target is active:
            return True
        return self.activateTerminalTab(target.tab_id)

    def _write_input_to_tab(self, tab: TerminalTabState, data: str) -> bool:
        if tab is None or not self._ensure_tab_started(tab) or tab.session is None:
            return False
        return tab.session.write(data.encode("utf-8"))

    @Slot(int, int)
    def resizeTerminal(self, columns: int, rows: int) -> None:
        self._terminal_columns = max(2, columns)
        self._terminal_rows = max(1, rows)
        for tab in self._tabs:
            if tab.session is not None:
                tab.session.resize(self._terminal_columns, self._terminal_rows)

    @Slot()
    def terminalReady(self) -> None:
        self._terminal_ready = True
        for tab in self._tabs:
            self.terminalResetRequested.emit(tab.tab_id)
            if tab.output:
                self.terminalSnapshotData.emit(tab.tab_id, tab.output)
        self.ensureStarted()

    @Slot()
    def terminalDetached(self) -> None:
        self._terminal_ready = False

    @Slot()
    def clear(self) -> None:
        self.writeInput("\x0c")

    @Slot(result=bool)
    def interrupt(self) -> bool:
        """Send Ctrl+C to stop the foreground command without closing the session."""
        return self.writeInput("\x03")

    @Slot()
    def restart(self) -> None:
        tab = self._active_tab()
        if tab is None:
            return
        if tab.session is None:
            self.ensureStarted()
            return
        tab.restart_pending = True
        tab.intentional_stop = True
        tab.session.stop_process()

    @Slot()
    def stop(self) -> None:
        for tab in (*self._tabs, *self._closing_tabs.values()):
            tab.restart_pending = False
            tab.intentional_stop = True
            if tab.session is not None:
                tab.session.stop_process()

    @Slot()
    def shutdown(self) -> None:
        self._shutdown_pending = True
        self._save_open_terminal_groups()
        self.stop()
        tabs = (*self._tabs, *self._closing_tabs.values())
        for tab in tabs:
            session = tab.session
            if session is None:
                continue
            if not session.wait(3_000):
                session.dispose()
                session.wait(2_000)
            if tab.session is session:
                session.dispose()
                tab.session = None
        if self._owns_plugin_manager and self._plugin_manager:
            self._plugin_manager.shutdown()

    def _save_open_terminal_groups(self) -> None:
        groups: list[dict[str, object]] = []
        for group_id, members in groupby(self._tabs, key=lambda tab: tab.group_id):
            group = self._groups.get(group_id)
            if group is None:
                continue
            tabs = list(members)
            for tab in tabs:
                if isinstance(tab.session, ConPtySession):
                    directory = tab.session.posix_working_directory()
                    if directory is not None:
                        tab.working_directory = directory
            groups.append({
                "title": group.title,
                "color": group.color,
                "tabs": [
                    {
                        "title": tab.custom_title,
                        "directory": str(tab.working_directory),
                        "active": tab.tab_id == self._active_tab_id,
                    }
                    for tab in tabs
                ],
            })
        try:
            self.python_environment.config_store.set_open_terminal_groups(groups)
        except OSError:
            logger.warning("Could not save open terminal groups", exc_info=True)

    def _restore_open_terminal_groups(self) -> None:
        for saved in self.python_environment.config_store.open_terminal_groups():
            if not isinstance(saved, dict) or not isinstance(saved.get("tabs"), list):
                continue
            members = [member for member in saved["tabs"] if isinstance(member, dict)]
            if not members:
                continue
            group_id = uuid4().hex
            title, color = saved.get("title"), saved.get("color")
            self._groups[group_id] = TerminalGroup(
                title=title[:60] if isinstance(title, str) else "",
                color=color if isinstance(color, str) and color in self.GROUP_COLORS
                else self.GROUP_COLORS[0],
                collapsed=True,
            )
            for member in members:
                directory = member.get("directory")
                path = (
                    Path(directory)
                    if isinstance(directory, str) and "\x00" not in directory
                    else self.working_directory
                )
                tab = self._create_tab(
                    activate=member.get("active") is True, emit=False,
                    working_directory=path if path.is_absolute() else self.working_directory,
                )
                tab.group_id = group_id
                title = member.get("title")
                if isinstance(title, str):
                    tab.custom_title = title
        if self._tabs and not self._active_tab_id:
            self._active_tab_id = self._tabs[0].tab_id

    def active_session_titles(self) -> list[str]:
        return [tab.title for tab in (*self._tabs, *self._closing_tabs.values())
                if tab.session is not None]

    @Slot(result=bool)
    def createTerminalTab(self) -> bool:
        tab = self._create_tab(activate=True)
        self._show_started_tab(tab)
        return True

    def _show_started_tab(self, tab: TerminalTabState) -> None:
        self._display_active_tab()
        if self._terminal_ready:
            QTimer.singleShot(0, lambda: self._ensure_tab_started(tab))

    @Slot("QVariantList", result=str)
    def createTerminalGroup(self, tab_ids: list[str]) -> str:
        members = self._selected_tabs(tab_ids)
        if not members:
            return ""
        bounds = self._group_bounds(members[0].group_id)
        index = bounds[0] if bounds is not None else self._tabs.index(members[0])
        return self._create_terminal_group(members, index)

    def _create_terminal_group(self, members: list[TerminalTabState], index: int) -> str:
        group_id = uuid4().hex
        color = self.GROUP_COLORS[len(self._groups) % len(self.GROUP_COLORS)]
        self._groups[group_id] = TerminalGroup("", color)
        self._place_tabs(members, index, group_id)
        return group_id

    @Slot("QVariantList", str, result=bool)
    def addTabsToTerminalGroup(self, tab_ids: list[str], group_id: str) -> bool:
        bounds = self._group_bounds(group_id)
        members = [tab for tab in self._selected_tabs(tab_ids) if tab.group_id != group_id]
        if bounds is None or not members:
            return False
        self._place_tabs(members, bounds[1], group_id)
        return True

    @Slot("QVariantList")
    def removeTabsFromTerminalGroups(self, tab_ids: list[str]) -> None:
        members = self._selected_tabs(tab_ids)
        for group_id in dict.fromkeys(tab.group_id for tab in members if tab.group_id):
            bounds = self._group_bounds(group_id)
            if bounds is not None:
                self._place_tabs(
                    [tab for tab in members if tab.group_id == group_id],
                    bounds[1], "", emit=False,
                )
        self.terminalTabsChanged.emit()

    @Slot(str, str, str)
    def editTerminalGroup(self, group_id: str, title: str, color: str) -> None:
        group = self._groups.get(group_id)
        if group is not None and color in self.GROUP_COLORS:
            group.title = title.strip()[:60]
            group.color = color
            self.terminalTabsChanged.emit()

    @Slot(str)
    def toggleTerminalGroup(self, group_id: str) -> None:
        group = self._groups.get(group_id)
        if group is None:
            return
        group.collapsed = not group.collapsed
        active = self._active_tab()
        if group.collapsed and active is not None and active.group_id == group_id:
            index = self._tabs.index(active)
            candidates = self._tabs[index + 1:] + self._tabs[:index][::-1]
            target = next((tab for tab in candidates if self._is_tab_visible(tab)), None)
            if target is not None:
                self.activateTerminalTab(target.tab_id)
                return
        self.terminalTabsChanged.emit()

    @Slot(str, result=bool)
    def createTerminalTabInGroup(self, group_id: str) -> bool:
        bounds = self._group_bounds(group_id)
        if bounds is None:
            return False
        tab = self._create_tab(activate=False, emit=False)
        self._place_tabs([tab], bounds[1], group_id, emit=False)
        return self.activateTerminalTab(tab.tab_id)

    @Slot(str)
    def ungroupTerminalGroup(self, group_id: str) -> None:
        if self._groups.pop(group_id, None) is None:
            return
        for tab in self._tabs:
            if tab.group_id == group_id:
                tab.group_id = ""
        self.terminalTabsChanged.emit()

    @Slot("QVariantList", str, str, int, bool, result=bool)
    def moveTerminalItems(
        self, tab_ids: list[str], group_id: str, target_id: str,
        position: int, target_is_group: bool,
    ) -> bool:
        tabs = (
            [tab for tab in self._tabs if tab.group_id == group_id]
            if group_id else self._selected_tabs(tab_ids)
        )
        target = self._tab_by_id(target_id)
        if not tabs or target is None or target in tabs:
            return False
        target_group = target.group_id
        index = self._tabs.index(target)
        if (
            position == 0 and not target_is_group and not target_group and not group_id
            and all(not tab.group_id for tab in tabs)
        ):
            new_group_id = self._create_terminal_group([target, *tabs], index)
            self.terminalGroupCreatedByDrop.emit(new_group_id)
            return True
        destination = target_group
        bounds = self._group_bounds(target_group)
        if group_id or target_is_group:
            if bounds is not None:
                index = bounds[0] if position < 0 else bounds[1]
            else:
                index += int(position >= 0)
            if group_id or position != 0:
                destination = group_id
        else:
            index += int(position >= 0)
            if position > 0 and bounds is not None and index == bounds[1]:
                destination = ""
        self._place_tabs(tabs, index, destination)
        return True

    @Slot(str, result=bool)
    def closeTerminalGroup(self, group_id: str) -> bool:
        if group_id not in self._groups:
            return False
        tabs = [tab for tab in self._tabs if tab.group_id == group_id]
        self._close_tabs(tabs)
        return True

    def _selected_tabs(self, tab_ids: list[str]) -> list[TerminalTabState]:
        ids = set(tab_ids)
        return [tab for tab in self._tabs if tab.tab_id in ids]

    def _is_tab_visible(self, tab: TerminalTabState) -> bool:
        group = self._groups.get(tab.group_id)
        return group is None or not group.collapsed

    def _group_bounds(self, group_id: str) -> tuple[int, int] | None:
        if not group_id:
            return None
        indices = [index for index, tab in enumerate(self._tabs) if tab.group_id == group_id]
        return (indices[0], indices[-1] + 1) if indices else None

    def _place_tabs(
        self, tabs: list[TerminalTabState], index: int, group_id: str, *, emit: bool = True,
    ) -> None:
        ids = {tab.tab_id for tab in tabs}
        index = sum(tab.tab_id not in ids for tab in self._tabs[:index])
        self._tabs = [tab for tab in self._tabs if tab.tab_id not in ids]
        self._tabs[index:index] = tabs
        for tab in tabs:
            if tab.group_id != group_id and group_id and tab.tab_id == self._active_tab_id:
                self._groups[group_id].collapsed = False
            tab.group_id = group_id
        self._remove_empty_groups()
        if emit:
            self.terminalTabsChanged.emit()

    def _remove_empty_groups(self) -> None:
        occupied = {tab.group_id for tab in self._tabs}
        self._groups = {key: group for key, group in self._groups.items() if key in occupied}

    @Slot(str, result=bool)
    def openTerminalAtDirectory(self, directory: str) -> bool:
        target = self._normalize_working_directory(Path(directory))
        active = self._active_tab()
        if active is not None and active.session is None and not active.output:
            active.working_directory = target
            if self._terminal_ready:
                QTimer.singleShot(0, lambda: self._ensure_tab_started(active))
            return True
        tab = self._create_tab(activate=True, working_directory=target)
        if self._terminal_ready:
            self._display_active_tab()
            QTimer.singleShot(0, lambda: self._ensure_tab_started(tab))
        return True

    @Slot(str, result=bool)
    def activateTerminalTab(self, tab_id: str) -> bool:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return False
        if tab.tab_id == self._active_tab_id:
            return True
        if tab.group_id:
            self._groups[tab.group_id].collapsed = False
        self._active_tab_id = tab.tab_id
        self.terminalTabsChanged.emit()
        self.runningChanged.emit()
        self.outputChanged.emit()
        self._show_started_tab(tab)
        return True

    @Slot(str, result=bool)
    def closeTerminalTab(self, tab_id: str) -> bool:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return False
        self._close_tabs([tab])
        return True

    def _close_tabs(self, tabs: list[TerminalTabState]) -> None:
        if not tabs:
            return
        ids = {tab.tab_id for tab in tabs}
        active = self._active_tab()
        was_active = active is not None and active.tab_id in ids
        if was_active and active is not None:
            index = self._tabs.index(active)
            candidates = [tab for tab in self._tabs[index + 1:] + self._tabs[:index][::-1]
                          if tab.tab_id not in ids]
            active = next((tab for tab in candidates if self._is_tab_visible(tab)),
                          candidates[0] if candidates else None)
            self._active_tab_id = active.tab_id if active is not None else ""
            if active is not None and active.group_id:
                self._groups[active.group_id].collapsed = False
        self._tabs = [tab for tab in self._tabs if tab.tab_id not in ids]
        self._remove_empty_groups()
        for tab in tabs:
            tab.output = ""
            tab.directory_report_tail = b""
            self.terminalSessionRemoved.emit(tab.tab_id)
            if tab.session is not None:
                tab.intentional_stop = True
                tab.restart_pending = False
                self._closing_tabs[tab.tab_id] = tab
                tab.session.stop_process()
        if any(tab.group_id for tab in tabs):
            self._save_open_terminal_groups()
        self.terminalTabsChanged.emit()
        self.runningChanged.emit()
        self.outputChanged.emit()
        if was_active:
            if active is not None:
                self._show_started_tab(active)
            else:
                self._display_active_tab()

    @Slot(str, result=bool)
    def closeOtherTerminalTabs(self, tab_id: str) -> bool:
        if self._tab_by_id(tab_id) is None:
            return False
        self._close_tabs([tab for tab in self._tabs if tab.tab_id != tab_id])
        return True

    @Slot(str, result=bool)
    def closeTerminalTabsToRight(self, tab_id: str) -> bool:
        tab = self._tab_by_id(tab_id)
        if tab is None:
            return False
        index = self._tabs.index(tab)
        self._close_tabs(self._tabs[index + 1 :])
        return True

    @Slot(bytes)
    def _on_terminal_output(self, payload: bytes) -> None:
        tab = self._tab_for_session(self.sender())
        if tab is not None and tab.tab_id not in self._closing_tabs:
            self._track_terminal_directory(tab, payload)
            self._append_to_tab(tab, tab.output_decoder.decode(payload, final=False))

    def _track_terminal_directory(self, tab: TerminalTabState, payload: bytes) -> None:
        data = tab.directory_report_tail + payload
        tab.directory_report_tail = b""
        for match in self._DIRECTORY_REPORT.finditer(data):
            partial = match["partial"]
            if partial is not None:
                tab.directory_report_tail = partial
                continue
            url = QUrl.fromEncoded(match["uri"], QUrl.ParsingMode.StrictMode)
            if not url.isLocalFile() or url.hasQuery() or url.hasFragment():
                continue
            directory = url.toLocalFile()
            if "\x00" not in directory and (path := Path(directory)).is_absolute():
                tab.working_directory = path

    @Slot(int)
    def _on_process_exited(self, exit_code: int) -> None:
        tab = self._tab_for_session(self.sender())
        if tab is not None:
            tab.exit_code = exit_code

    @Slot()
    def _on_session_finished(self) -> None:
        sender = self.sender()
        if not isinstance(sender, ConPtySession):
            return
        session = sender
        tab = self._tab_for_session(session)
        if tab is None:
            session.dispose()
            session.deleteLater()
            return
        tab_id = tab.tab_id
        tab.session = None
        session.dispose()
        session.deleteLater()
        if tab_id in self._closing_tabs:
            self._closing_tabs.pop(tab_id, None)
            return
        self._append_to_tab(tab, tab.output_decoder.decode(b"", final=True))
        restart_pending = tab.restart_pending
        tab.restart_pending = False
        if not restart_pending and not tab.intentional_stop and not self._shutdown_pending:
            self._append_to_tab(
                tab,
                f"\r\nPowerShell 会话已结束（退出码 {tab.exit_code}）。\r\n",
            )
        tab.intentional_stop = False
        self.terminalTabsChanged.emit()
        if tab.tab_id == self._active_tab_id:
            self.runningChanged.emit()
        if restart_pending and not self._shutdown_pending:
            tab.output = ""
            if tab.tab_id == self._active_tab_id:
                self.terminalResetRequested.emit(tab.tab_id)
                self.outputChanged.emit()
            QTimer.singleShot(0, lambda: self._ensure_tab_started(tab))

    def _append(self, text: str) -> None:
        tab = self._active_tab()
        if tab is not None:
            self._append_to_tab(tab, text)

    def _append_to_tab(self, tab: TerminalTabState, text: str) -> None:
        if not text:
            return
        tab.output = (tab.output + text)[-self.OUTPUT_HISTORY_LIMIT :]
        if self._terminal_ready:
            self.terminalData.emit(tab.tab_id, text)

    def _create_tab(
        self,
        *,
        activate: bool,
        emit: bool = True,
        working_directory: Path | None = None,
    ) -> TerminalTabState:
        tab_number = self._next_tab_number
        self._next_tab_number += 1
        tab = TerminalTabState(
            tab_id=f"terminal-{tab_number}",
            shell_title=self._default_tab_title(),
            working_directory=self._normalize_working_directory(working_directory),
        )
        self._tabs.append(tab)
        if activate:
            self._active_tab_id = tab.tab_id
        if emit:
            self.terminalTabsChanged.emit()
            self.runningChanged.emit()
            self.outputChanged.emit()
        return tab

    def _active_tab(self) -> TerminalTabState | None:
        return self._tab_by_id(self._active_tab_id)

    def _tab_by_id(self, tab_id: str) -> TerminalTabState | None:
        return next((tab for tab in self._tabs if tab.tab_id == tab_id), None)

    def _tab_for_session(self, session: object) -> TerminalTabState | None:
        return next(
            (tab for tab in (*self._tabs, *self._closing_tabs.values()) if tab.session is session),
            None,
        )

    @staticmethod
    def _normalize_working_directory(directory: Path | None) -> Path:
        candidate = (directory or Path.home()).expanduser()
        try:
            candidate = candidate.resolve()
        except OSError:
            candidate = Path.home().resolve()
        return candidate if candidate.is_dir() else Path.home().resolve()

    def _display_active_tab(self) -> None:
        # The native terminal keeps an independent libvterm screen for every
        # tab, so switching tabs only changes the visible session. Replaying a
        # truncated ANSI byte stream here would corrupt terminal state.
        return
