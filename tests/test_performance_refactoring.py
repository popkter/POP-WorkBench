from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest
from PySide6.QtCore import QPersistentModelIndex, QTimer
from PySide6.QtTest import QAbstractItemModelTester

from poptools.domain.models import ExecutorDefinition, ExecutorKind, ToolDefinition
from poptools.infrastructure.background_process import BackgroundProcess
from poptools.infrastructure.config_store import ConfigStore
from poptools.infrastructure.python_dependency_install import PythonDependencyInstall
from poptools.infrastructure.tool_analysis import ToolAnalysisService
from poptools.paths import AppPaths
from poptools.viewmodels.tool_list_model import ToolListModel


def tool(tool_id="custom.a", command="print(1)"):
    return ToolDefinition(id=tool_id, section="custom", title=tool_id,
                          executor=ExecutorDefinition(kind="python", command=command))


def test_configuration_cache_detaches_and_reloads_external_changes(tmp_path):
    paths = AppPaths(tmp_path)
    store = ConfigStore(paths)
    store.load_config()
    with patch("poptools.infrastructure.config_store.json.loads", wraps=json.loads) as parse:
        first = store.load_config()
        first["app"]["theme"] = "dark"
        assert store.load_config()["app"]["theme"] == "system"
        assert parse.call_count == 0
        other = ConfigStore(paths)
        other.set_theme_mode("dark")
        assert store.theme_mode() == "dark"
    paths.config_file.write_text("broken", encoding="utf-8")
    assert store.theme_mode() == "system"
    assert list(paths.backups_dir.glob("*.corrupt"))


def test_tool_usage_is_one_atomic_save(tmp_path):
    store = ConfigStore(AppPaths(tmp_path))
    store.load_config()
    with patch.object(store.files, "write", wraps=store.files.write) as write:
        store.record_tool_use("custom.a")
        assert write.call_count == 1
    store.record_tool_use("custom.b")
    store.record_tool_use("custom.a")
    assert store.recent_tools() == ["custom.a", "custom.b"]
    assert store.tool_usage_counts() == {"custom.a": 2, "custom.b": 1}


def test_list_reorder_preserves_identity_and_emits_only_changed_roles(qapp):
    model = ToolListModel()
    tester = QAbstractItemModelTester(model, QAbstractItemModelTester.FailureReportingMode.Warning)
    a, b = tool(), tool("custom.b")
    model.set_tools([a, b], a.id)
    selected = QPersistentModelIndex(model.index(0))
    resets, changes = [], []
    model.modelReset.connect(lambda: resets.append(1))
    model.dataChanged.connect(lambda start, end, roles: changes.append(roles))
    model.set_tools([a, b], a.id)
    assert not resets and not changes
    model.set_tools([b, a], a.id, {a.id})
    assert not resets
    assert selected.row() == 1
    assert selected.data(model.IdRole) == a.id
    assert changes == [[model.RunningRole]]
    assert model.count == 2
    model.set_tools([b], b.id)
    assert not selected.isValid()
    assert model.count == 1
    assert tester.model() is model


def test_changed_kind_updates_filter_counts_without_reset(qapp):
    model = ToolListModel()
    original = tool()
    model.set_tools([original])
    notifications, resets = [], []
    model.countChanged.connect(lambda: notifications.append(model.countForKind("python")))
    model.modelReset.connect(lambda: resets.append(1))
    changed = original.model_copy(deep=True)
    changed.executor.kind = ExecutorKind.POWERSHELL
    model.set_tools([changed])
    assert notifications == [0]
    assert not resets


def test_analysis_cache_invalidates_content_and_referenced_file(tmp_path):
    service = ToolAnalysisService()
    source = tmp_path / "external.py"
    source.write_text("print(1)", encoding="utf-8")
    definition = tool(command=str(source))
    from poptools.infrastructure import tool_analysis
    with patch.object(tool_analysis, "analyze_adb", wraps=tool_analysis.analyze_adb) as analyze:
        assert not service.analyze(definition).uses_adb
        assert not service.analyze(definition).uses_adb
        assert analyze.call_count == 1
        source.write_text("import subprocess\nsubprocess.run(['adb', 'devices'])", encoding="utf-8")
        assert service.analyze(definition).uses_adb
        assert analyze.call_count == 2
        definition.executor.command = "print(2)"
        assert not service.analyze(definition).uses_adb
        assert analyze.call_count == 3


@pytest.mark.parametrize("repair", [False, True])
def test_dependency_install_stages_keep_event_loop_responsive(qapp, qtbot, monkeypatch, repair):
    launches = []
    original = BackgroundProcess.start

    def start(process, executable, arguments, **kwargs):
        launches.append(arguments)
        code = 1 if repair and len(launches) == 1 else 0
        script = f"import time; time.sleep(.08); raise SystemExit({code})"
        return original(process, sys.executable, ["-c", script], **kwargs)

    monkeypatch.setattr(BackgroundProcess, "start", start)
    job = PythonDependencyInstall(sys.executable, ["example"], qapp)
    beats = []
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: beats.append(1))
    timer.start()
    with qtbot.waitSignal(job.completed, timeout=5000) as result:
        job.start()
    timer.stop()
    assert result.args[0]
    assert len(beats) >= 5
    assert launches[-1] == ["-m", "pip", "install", "example"]
    assert len(launches) == (4 if repair else 2)
    job.deleteLater()
    qtbot.wait(30)


@pytest.mark.parametrize("action", ["cancel", "timeout", "shutdown"])
def test_dependency_install_cancels_without_starting_next_stage(qapp, qtbot, monkeypatch, action):
    original = BackgroundProcess.start
    launches = []

    def start(process, executable, arguments, **kwargs):
        launches.append(arguments)
        return original(process, sys.executable, ["-c", "import time; time.sleep(5)"], **kwargs)

    monkeypatch.setattr(BackgroundProcess, "start", start)
    job = PythonDependencyInstall(sys.executable, ["example"], qapp)
    job.CHECK_TIMEOUT_MS = 50 if action == "timeout" else 2000
    with qtbot.waitSignal(job.completed, timeout=3000) as result:
        job.start()
        if action == "cancel":
            QTimer.singleShot(50, job.cancel)
        elif action == "shutdown":
            QTimer.singleShot(50, job.shutdown)
    assert not result.args[0]
    assert ("超时" if action == "timeout" else "取消") in result.args[1]
    assert len(launches) == 1
    job.deleteLater()
    qtbot.wait(30)
