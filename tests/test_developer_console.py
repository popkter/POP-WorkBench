from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from PySide6.QtCore import QObject, QUrl, Signal

from poptools.infrastructure.config_store import ConfigStore
from poptools.paths import AppPaths
from poptools.viewmodels.developer_console_controller import DeveloperConsoleController


class FakePythonEnvironment:
    def __init__(self, root: Path) -> None:
        self.paths = SimpleNamespace(python_venv_dir=root / "python", data_dir=root)
        self.config_store = ConfigStore(AppPaths(root))

    def execution_executable(self) -> str:
        return str(self.paths.python_venv_dir / "python.exe")

    def executable(self) -> str:
        return str(self.paths.python_venv_dir / "pip.exe")

    def execution_environment(self) -> dict[str, str]:
        return {}


class FakePowerShellPlugin:
    package = SimpleNamespace(version="7.6.0")

    def __init__(self, root: Path) -> None:
        self.install_directory = root / "powershell"
        self.executable = self.install_directory / "pwsh.exe"

    def is_installed(self) -> bool:
        return True


class FakeSession:
    def __init__(self) -> None:
        self.sizes: list[tuple[int, int]] = []
        self.writes: list[bytes] = []

    def resize(self, columns: int, rows: int) -> None:
        self.sizes.append((columns, rows))

    def write(self, payload: bytes) -> bool:
        self.writes.append(payload)
        return True


class FakeStartedSession:
    last_start: tuple[Path, list[str], Path, dict[str, str], int, int] | None = None

    def __init__(self, _parent: object = None) -> None:
        self.outputReceived = SimpleNamespace(connect=lambda _callback: None)
        self.processExited = SimpleNamespace(connect=lambda _callback: None)
        self.finished = SimpleNamespace(connect=lambda _callback: None)

    def start_process(
        self,
        shell: Path,
        arguments: list[str],
        working_directory: Path,
        environment: dict[str, str],
        *,
        columns: int,
        rows: int,
    ) -> None:
        type(self).last_start = (
            shell, arguments, working_directory, environment, columns, rows
        )


def make_controller(tmp_path: Path) -> DeveloperConsoleController:
    environment = FakePythonEnvironment(tmp_path)
    plugin = FakePowerShellPlugin(tmp_path)
    return DeveloperConsoleController(
        environment,  # type: ignore[arg-type]
        tmp_path,
        plugin,  # type: ignore[arg-type]
    )


def test_powershell_terminal_does_not_require_python_plugin(tmp_path: Path, monkeypatch):
    controller = make_controller(tmp_path)
    monkeypatch.setattr(controller.python_environment, "execution_executable", lambda: None)
    monkeypatch.setattr(controller.python_environment, "executable", lambda: None)
    with patch(
        "poptools.viewmodels.developer_console_controller.ConPtySession", FakeStartedSession
    ):
        assert controller.ensureStarted()
    assert FakeStartedSession.last_start[3]["POPTOOLS_PYTHON"] == ""
    assert FakeStartedSession.last_start[3]["POPTOOLS_PIP"] == ""


def test_terminal_output_is_routed_to_its_own_native_session(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    routed: list[tuple[str, str]] = []
    controller.terminalData.connect(lambda tab_id, text: routed.append((tab_id, text)))
    controller._terminal_ready = True

    first = controller._tabs[0]
    controller._append_to_tab(first, "first")
    assert controller.createTerminalTab()
    second = controller._tabs[1]
    controller._append_to_tab(second, "second")

    assert routed == [(first.tab_id, "first"), (second.tab_id, "second")]


def test_switching_tabs_does_not_replay_truncated_ansi_history(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    resets: list[str] = []
    snapshots: list[tuple[str, str]] = []
    controller.terminalResetRequested.connect(resets.append)
    controller.terminalSnapshotData.connect(
        lambda tab_id, text: snapshots.append((tab_id, text))
    )
    controller._terminal_ready = True

    first = controller._tabs[0]
    first.output = "\x1b[31mred"
    assert controller.createTerminalTab()
    second = controller._tabs[1]
    assert controller.activateTerminalTab(first.tab_id)
    assert controller.activateTerminalTab(second.tab_id)

    assert resets == []
    assert snapshots == []


def test_resize_updates_every_running_terminal_tab(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    assert controller.createTerminalTab()
    sessions = [FakeSession(), FakeSession()]
    for tab, session in zip(controller._tabs, sessions, strict=True):
        tab.session = session  # type: ignore[assignment]

    controller.resizeTerminal(132, 42)

    assert [session.sizes for session in sessions] == [[(132, 42)], [(132, 42)]]


def test_closing_tab_removes_native_terminal_session(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    removed: list[str] = []
    controller.terminalSessionRemoved.connect(removed.append)
    controller._terminal_ready = True
    tab_id = controller._active_tab_id

    assert controller.closeTerminalTab(tab_id)

    assert removed == [tab_id]


def test_interrupt_sends_ctrl_c_to_active_terminal_without_stopping_session(
    tmp_path: Path,
) -> None:
    controller = make_controller(tmp_path)
    session = FakeSession()
    controller._tabs[0].session = session  # type: ignore[assignment]

    assert controller.interrupt()

    assert session.writes == [b"\x03"]
    assert controller._tabs[0].session is session


def test_embedded_powershell_loads_user_profile(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    FakeStartedSession.last_start = None

    with patch(
        "poptools.viewmodels.developer_console_controller.ConPtySession",
        FakeStartedSession,
    ):
        assert controller.ensureStarted()

    assert FakeStartedSession.last_start is not None
    arguments = FakeStartedSession.last_start[1]
    assert "-NoProfile" not in arguments
    assert arguments[:2] == ["-NoLogo", "-NoExit"]
    assert arguments[-2] == "-File"
    assert arguments[-1].endswith("powershell-terminal-profile.ps1")


def test_terminal_syntax_colors_are_added_to_powershell_environment(
    tmp_path: Path,
) -> None:
    controller = make_controller(tmp_path)
    controller.configureTerminalSyntaxColors(
        {
            "command": "#123abc",
            "warning": "invalid",
            "string": "#ABCDEF",
        }
    )
    FakeStartedSession.last_start = None

    with patch(
        "poptools.viewmodels.developer_console_controller.ConPtySession",
        FakeStartedSession,
    ):
        assert controller.ensureStarted()

    assert FakeStartedSession.last_start is not None
    environment = FakeStartedSession.last_start[3]
    assert environment["POPTOOLS_PS_COLOR_COMMAND"] == "#123ABC"
    assert environment["POPTOOLS_PS_COLOR_WARNING"] == "#FFCE66"
    assert environment["POPTOOLS_PS_COLOR_STRING"] == "#ABCDEF"
    assert environment["POPTOOLS_PS_COLOR_DEFAULT"] == "#E5E7EB"
    assert environment["POPTOOLS_PS_COLOR_MUTED"] == "#728298"


def test_powershell_profile_configures_psreadline_syntax_colors() -> None:
    profile = (
        Path(__file__).parents[1]
        / "src"
        / "poptools"
        / "resources"
        / "tools"
        / "powershell-terminal-profile.ps1"
    ).read_text(encoding="utf-8")

    assert "Set-PSReadLineOption -Colors $popToolsColors" in profile
    assert "POPTOOLS_PS_COLOR_COMMAND" in profile
    assert "POPTOOLS_PS_COLOR_WARNING" in profile
    assert "POPTOOLS_PS_COLOR_MUTED" in profile
    assert "Set-PSReadLineOption -PredictionSource None" in profile
    assert "Set-PSReadLineKeyHandler -Chord Ctrl+F11" in profile
    assert "Set-PSReadLineOption -PredictionSource History" in profile
    assert "Set-PSReadLineOption -PredictionViewStyle ListView" in profile
    assert "Set-PSReadLineKeyHandler -Chord Ctrl+F12" in profile
    assert profile.count("[Microsoft.PowerShell.PSConsoleReadLine]::InvokePrompt()") == 2


def test_power_shell_history_toggle_configures_psreadline_list_view(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    session = FakeSession()
    controller._tabs[0].session = session  # type: ignore[assignment]

    assert controller.setPowerShellHistoryListViewEnabled(True)

    assert controller.powerShellHistoryListViewEnabled
    assert session.writes == [b"\x1b[23;5~"]


def test_power_shell_history_toggle_disables_prediction(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    session = FakeSession()
    controller._tabs[0].session = session  # type: ignore[assignment]
    controller._power_shell_history_list_view_enabled = True

    assert controller.setPowerShellHistoryListViewEnabled(False)

    assert not controller.powerShellHistoryListViewEnabled
    assert session.writes == [b"\x1b[24;5~"]


@pytest.mark.parametrize("enabled", [True, False])
def test_history_preference_survives_terminal_and_app_lifecycle(
    tmp_path, qtbot, monkeypatch, enabled,
):
    class Session(QObject):
        outputReceived = Signal(bytes)
        processExited = Signal(int)
        finished = Signal()

        def start_process(self, shell, arguments, directory, environment, **size):
            self.environment = environment

        def write(self, payload):
            return True

        def stop_process(self):
            self.finished.emit()

        def dispose(self):
            pass

        def wait(self, timeout):
            return True

    monkeypatch.setattr("poptools.viewmodels.developer_console_controller.ConPtySession", Session)
    store = ConfigStore(AppPaths(tmp_path))
    store.set_terminal_history_list_view_enabled(not enabled)
    controller = make_controller(tmp_path)
    controller.terminalReady()
    assert controller.setPowerShellHistoryListViewEnabled(enabled)
    saved = store.paths.config_file.read_bytes()
    assert ConfigStore(store.paths).terminal_history_list_view_enabled() is enabled

    def check_session():
        qtbot.waitUntil(lambda: controller.running)
        assert controller.powerShellHistoryListViewEnabled is enabled
        assert controller._active_tab().session.environment["POPTOOLS_PS_HISTORY_LIST_VIEW"] == (
            "1" if enabled else "0"
        )

    controller.restart()
    check_session()
    assert controller.createTerminalTab()
    check_session()
    for tab in list(controller.terminalTabs):
        assert controller.closeTerminalTab(tab["tabId"])
    assert not controller.terminalTabs
    assert controller.powerShellHistoryListViewEnabled is enabled
    assert controller.createTerminalTab()
    check_session()
    controller.shutdown()

    restored = make_controller(tmp_path)
    try:
        assert restored.powerShellHistoryListViewEnabled is enabled
        assert restored.ensureStarted()
        assert restored._active_tab().session.environment["POPTOOLS_PS_HISTORY_LIST_VIEW"] == (
            "1" if enabled else "0"
        )
        assert store.paths.config_file.read_bytes() == saved
    finally:
        restored.shutdown()


@pytest.mark.parametrize("app", [{}, None, {"terminal_history_list_view_enabled": "false"}])
def test_history_preference_defaults_to_disabled_for_old_or_invalid_config(tmp_path, app):
    store = ConfigStore(AppPaths(tmp_path))
    store.save_config({"app": app})
    assert not store.terminal_history_list_view_enabled()
    store.set_terminal_history_list_view_enabled(True)
    assert ConfigStore(store.paths).terminal_history_list_view_enabled()


@pytest.mark.parametrize("enabled", [True, False])
def test_powershell_profile_applies_history_preference_before_input(enabled):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    if os.name != "nt" or shell is None:
        pytest.skip("PowerShell bootstrap requires Windows")
    profile = (Path(__file__).parents[1] / "src/poptools/resources/tools"
               / "powershell-terminal-profile.ps1")
    command = r'''
$global:options = @{}
function Import-Module { param($Name) }
function Set-PSReadLineOption {
    param($Colors, $PredictionSource, $PredictionViewStyle)
    foreach ($name in @('PredictionSource', 'PredictionViewStyle')) {
        if ($PSBoundParameters.ContainsKey($name)) {
            $global:options[$name] = $PSBoundParameters[$name]
        }
    }
}
function Set-PSReadLineKeyHandler { param($Chord, $ScriptBlock) }
. 'PROFILE'
$global:options | ConvertTo-Json -Compress
'''.replace("PROFILE", str(profile).replace("'", "''"))
    result = subprocess.run(
        [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", command],
        env={**os.environ, "POPTOOLS_PS_HISTORY_LIST_VIEW": "1" if enabled else "0"},
        capture_output=True, encoding="utf-8", check=True, timeout=15,
    )
    options = json.loads(result.stdout)
    assert options == ({"PredictionSource": "History", "PredictionViewStyle": "ListView"}
                       if enabled else {"PredictionSource": "None"})


def test_terminal_defaults_to_user_home_directory(tmp_path: Path) -> None:
    environment = FakePythonEnvironment(tmp_path)
    plugin = FakePowerShellPlugin(tmp_path)
    controller = DeveloperConsoleController(
        environment,  # type: ignore[arg-type]
        powershell_plugin=plugin,  # type: ignore[arg-type]
    )
    FakeStartedSession.last_start = None

    with patch(
        "poptools.viewmodels.developer_console_controller.ConPtySession",
        FakeStartedSession,
    ):
        assert controller.ensureStarted()

    assert FakeStartedSession.last_start is not None
    assert FakeStartedSession.last_start[2] == Path.home()


def test_terminal_uses_requested_tab_working_directory(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    FakeStartedSession.last_start = None
    with patch(
        "poptools.viewmodels.developer_console_controller.ConPtySession",
        FakeStartedSession,
    ):
        assert controller.openTerminalAtDirectory(str(tmp_path))
        assert controller.ensureStarted()

    assert FakeStartedSession.last_start is not None
    assert FakeStartedSession.last_start[2] == tmp_path.resolve()


def test_opening_directory_with_running_terminal_creates_tab(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    controller._tabs[0].session = FakeSession()  # type: ignore[assignment]
    target = tmp_path / "nested"
    target.mkdir()

    assert controller.openTerminalAtDirectory(str(target))
    assert len(controller._tabs) == 2
    assert controller._tabs[1].working_directory == target.resolve()


def test_dropped_paths_are_quoted_as_powershell_arguments(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    plain = QUrl.fromLocalFile(str(tmp_path / "plain.txt"))
    spaced = QUrl.fromLocalFile(str(tmp_path / "folder name" / "a'b.txt"))

    result = controller.formatDroppedPaths(
        [plain, "https://example.com/ignored.txt", spaced]
    )

    assert result == (
        f" '{plain.toLocalFile()}' "
        f"'{spaced.toLocalFile().replace(chr(39), chr(39) * 2)}'"
    )
    assert "\r" not in result
    assert "\n" not in result


def test_terminal_title_stays_stable_until_manually_renamed(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    tab_id = controller.activeTerminalTabId
    default_title = controller._default_tab_title()

    assert controller.updateTerminalTitle(tab_id, "project shell")
    assert controller.terminalTabs[0]["title"] == default_title
    assert controller.renameTerminalTab(tab_id, "  build logs  ")
    assert controller.terminalTabs[0]["title"] == "build logs"
    assert controller.terminalTabs[0]["hasCustomTitle"] is True

    assert controller.updateTerminalTitle(tab_id, "changed by shell")
    assert controller.terminalTabs[0]["title"] == "build logs"
    assert controller.resetTerminalTabTitle(tab_id)
    assert controller.terminalTabs[0]["title"] == default_title
    assert controller.terminalTabs[0]["hasCustomTitle"] is False


def test_terminal_tabs_have_no_application_limit(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)

    for _ in range(12):
        assert controller.createTerminalTab()

    assert len(controller.terminalTabs) == 13
    assert controller.canCreateTerminalTab is True
    controller._active_tab().output = "already used"  # type: ignore[union-attr]
    assert controller.openTerminalAtDirectory(str(tmp_path / "more"))
    assert len(controller.terminalTabs) == 14


def test_relative_terminal_tab_switching_wraps_at_both_ends(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    first_id = controller.activeTerminalTabId
    assert controller.createTerminalTab()
    second_id = controller.activeTerminalTabId
    assert controller.createTerminalTab()
    third_id = controller.activeTerminalTabId

    assert controller.activateRelativeTerminalTab(1)
    assert controller.activeTerminalTabId == first_id
    assert controller.activateRelativeTerminalTab(-1)
    assert controller.activeTerminalTabId == third_id
    assert controller.activateTerminalTab(first_id)
    assert controller.activateRelativeTerminalTab(1)
    assert controller.activeTerminalTabId == second_id


def test_bulk_terminal_tab_close_operations_keep_requested_tab(tmp_path: Path) -> None:
    controller = make_controller(tmp_path)
    first_id = controller.activeTerminalTabId
    assert controller.createTerminalTab()
    second_id = controller.activeTerminalTabId
    assert controller.createTerminalTab()
    third_id = controller.activeTerminalTabId

    assert controller.closeTerminalTabsToRight(second_id)
    assert [tab["tabId"] for tab in controller.terminalTabs] == [first_id, second_id]

    assert controller.createTerminalTab()
    assert controller.closeOtherTerminalTabs(second_id)
    assert [tab["tabId"] for tab in controller.terminalTabs] == [second_id]
    assert controller.activeTerminalTabId == second_id
    assert controller._tab_by_id(third_id) is None

def test_last_terminal_tab_can_close_and_stays_empty(tmp_path, qtbot):
    controller = make_controller(tmp_path)
    stopped = []
    tab = controller._tabs[0]
    tab.session = SimpleNamespace(stop_process=lambda: stopped.append(True))
    controller._terminal_ready = True
    assert controller.closeTerminalTab(tab.tab_id)
    assert stopped == [True]
    assert controller.terminalTabs == []
    assert controller.activeTerminalTabId == ""
    assert not controller.running
    assert not controller.ensureStarted()
    controller.terminalDetached()
    controller.terminalReady()
    qtbot.wait(10)
    assert controller.terminalTabs == []
    assert not controller._ensure_tab_started(tab)
    with patch(
        "poptools.viewmodels.developer_console_controller.ConPtySession", FakeStartedSession
    ):
        assert controller.createTerminalTab()
        qtbot.waitUntil(lambda: controller.running)
    assert len(controller.terminalTabs) == 1
    assert controller.activeTerminalTabId != tab.tab_id
