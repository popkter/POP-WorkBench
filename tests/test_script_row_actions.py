"""Selected-row actions share the main page's existing management/run flows."""

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QPoint, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest

from poptools.paths import package_root, resource_path
from test_floating_launcher import create_tool
from test_floating_launcher import launcher as launcher
from test_script_list import evaluate
from test_script_list import script_list as script_list
from test_script_list_interactions import custom_page as custom_page
from test_script_list_interactions import row_for, visual_items

ACTIONS = ("Edit", "Delete", "Share", "Run")


def action_button(row, action):
    return row.findChild(QObject, f"scriptRow{action}_{row.property('toolId')}")


def click_button(window, button):
    point = button.mapToItem(window.contentItem(), button.boundingRect().center()).toPoint()
    QTest.mouseClick(window, Qt.MouseButton.LeftButton, pos=point)


@pytest.mark.gui
@pytest.mark.parametrize("width", [290, 438])
@pytest.mark.parametrize("theme", ["light", "dark", "decade", "zio"])
def test_selected_actions_fit_shrink_title_and_match_theme(script_list, qtbot, width, theme):
    backend, engine, window, view, warnings = script_list
    QFontDatabase.addApplicationFont(str(resource_path("fonts", "MaterialIconsRound-Regular.otf")))
    palette = json.loads((package_root() / "ui/qml/theme/configs/zio.json").read_text("utf-8"))
    evaluate(engine, view, f"Theme.darkMode = {str(theme != 'light').lower()};"
             f"Theme.decadeMode = {str(theme == 'decade').lower()};"
             f"Theme.zioMode = {str(theme == 'zio').lower()};"
             f"Theme.zioPalette = {json.dumps(palette['darkColors'])};")
    window.setColor(evaluate(engine, view, "Theme.surfaceContainerLow")[0])
    window.setWidth(width)
    a = create_tool(backend, "AI桌面卡片模拟 · 很长的脚本名称用于验证按钮出现后的文字省略",
                    kind="powershell")
    b = create_tool(backend, "Android重启", kind="powershell")
    backend.setToolSortMode("name")
    backend.selectTool(b.id)
    qtbot.wait(50)
    row = row_for(view, a.id)
    title = row.findChild(QObject, "scriptRowTitle_" + a.id)
    available_before = title.width()
    assert not row.findChild(QObject, "scriptRowActions_" + a.id).isVisible()
    backend.selectTool(a.id)
    QTest.mouseMove(window, QPoint(width - 1, window.height() - 1))
    qtbot.wait(50)
    assert 0 < title.width() < available_before
    assert title.property("truncated")
    assert not row_for(view, b.id).findChild(QObject, "scriptRowActions_" + b.id).isVisible()
    previous_right = title.mapToItem(row, title.width(), 0).x()
    for action in ACTIONS:
        button = action_button(row, action)
        assert button.isVisible() and button.isEnabled()
        bounds = button.mapRectToItem(row, button.boundingRect())
        assert bounds.left() > previous_right
        assert bounds.right() <= row.width()
        assert bounds.top() >= 0 and bounds.bottom() <= row.height()
        previous_right = bounds.right()
        assert button.property("foregroundColor") == evaluate(engine, view, "Theme.primary")[0]
    output = Path("build/script-row-actions")
    output.mkdir(parents=True, exist_ok=True)
    assert window.grabWindow().save(str(output / f"{theme}-{width}.png"))
    assert not warnings, warnings


@pytest.mark.gui
def test_double_click_on_edit_button_does_not_run_the_row(custom_page, qtbot):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tool = create_tool(backend, "Actions", kind="powershell")
    backend.selectTool(tool.id)
    qtbot.wait(50)
    row = row_for(view, tool.id)
    button = action_button(row, "Edit")
    click_button(window, button)
    point = button.mapToItem(window.contentItem(), button.boundingRect().center()).toPoint()
    QTest.mouseDClick(window, Qt.MouseButton.LeftButton, pos=point)
    qtbot.wait(20)
    assert not runs and not stops
    assert not warnings, warnings


@pytest.mark.gui
def test_row_actions_dispatch_once_without_reselecting_or_losing_parameters(
    custom_page, qtbot, monkeypatch,
):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tool = create_tool(backend, "Actions", kind="powershell", command="echo ${message:default}")
    backend.selectTool(tool.id)
    qtbot.wait(50)
    row = row_for(view, tool.id)
    field = next(item for item in visual_items(window.contentItem())
                 if item.objectName() == "customParameterInput_message").property("item")
    field.setProperty("text", "current edit")
    page = window.findChild(QObject, "customScriptsPage")
    edits, deletes, shares, toasts, selections, double_runs = [], [], [], [], [], []
    page.editRequested.connect(lambda: edits.append(True))
    page.deleteRequested.connect(lambda: deletes.append(True))
    page.toastRequested.connect(lambda message, error: toasts.append((message, error)))
    backend.selectedToolChanged.connect(lambda: selections.append(True))
    view.toolRunRequested.connect(double_runs.append)
    monkeypatch.setattr(backend, "exportSelectedScriptToClipboard",
                        lambda: shares.append(backend.selectedTool["id"]) or True)
    for action in ACTIONS:
        click_button(window, action_button(row, action))
        qtbot.wait(20)
    assert edits == deletes == [True]
    assert backend.registry.get(tool.id) is not None  # Deletion still requests confirmation.
    assert shares == [tool.id]
    assert toasts == [("脚本已复制到剪贴板", False)]
    assert runs == [(tool.id, {"message": "current edit"})]
    assert not stops and not selections and not double_runs
    assert field.property("text") == "current edit"
    assert not warnings, warnings


@pytest.mark.gui
def test_running_row_disables_management_and_run_button_stops(custom_page, qtbot, monkeypatch):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tool = create_tool(backend, "Running", kind="powershell")
    backend.selectTool(tool.id)
    monkeypatch.setattr(backend.execution_coordinator, "running", lambda tid: tid == tool.id)
    backend.execution_coordinator.runningChanged.emit(tool.id, True)
    qtbot.wait(50)
    row = row_for(view, tool.id)
    assert not action_button(row, "Edit").isEnabled()
    assert not action_button(row, "Delete").isEnabled()
    assert action_button(row, "Share").isEnabled()
    run = action_button(row, "Run")
    assert run.property("text") == "停止运行" and run.property("iconName") == "stop"
    click_button(window, run)
    assert stops == [True] and not runs
    assert not warnings, warnings


@pytest.mark.gui
def test_row_run_uses_existing_confirmation(custom_page, qtbot):
    backend, engine, window, view, warnings, runs, stops = custom_page
    tool = create_tool(backend, "Confirm", kind="powershell", command="echo ${message:default}")
    tool.presentation.confirm_before_run = True
    backend.registry.repository.save_tool(tool)
    backend.reloadImportedScripts()
    backend.selectTool(tool.id)
    qtbot.wait(50)
    row = row_for(view, tool.id)
    click_button(window, action_button(row, "Run"))
    assert window.property("confirmations").toVariant() == [{"message": "default"}]
    assert not runs and not stops
    assert not warnings, warnings
