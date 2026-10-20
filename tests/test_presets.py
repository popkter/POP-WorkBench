import pytest

from poptools.domain.models import ToolDefinition, ToolOrigin, ToolSection
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.infrastructure.tool_registry import ToolRegistry
from poptools.paths import AppPaths, resource_path
from poptools.viewmodels.tool_list_model import ToolListModel


def test_only_retained_presets_are_registered(tmp_path):
    registry = ToolRegistry(resource_path("tools"), JsonToolRepository(AppPaths(tmp_path)))

    presets = registry.for_section(ToolSection.PRESET)
    assert {tool.id: tool.executor.command for tool in presets} == {
        "preset.android.scrcpy": "scrcpy",
        "preset.android.recording": "recording",
        "preset.colors": "colors",
    }


@pytest.mark.parametrize("tool_id", ["preset.android.input_text", "preset.jira_feishu"])
def test_removed_or_hidden_preset_override_does_not_restore_tool(tmp_path, tool_id):
    repository = JsonToolRepository(AppPaths(tmp_path))
    registry = ToolRegistry(resource_path("tools"), repository)
    removed = ToolDefinition.model_validate({
        "id": tool_id,
        "title": "Legacy preset",
        "origin": "override",
        "section": "preset",
        "executor": {"kind": "python", "command": "removed-runner.py"},
    })
    repository.save_tool(removed)
    retained = registry.get("preset.colors").model_copy(
        update={"title": "Local palette", "origin": ToolOrigin.OVERRIDE}
    )
    repository.save_tool(retained)
    custom = registry.create_custom(
        title="My script", description="", kind="powershell", command="echo hello",
    )

    restarted = ToolRegistry(resource_path("tools"), repository)

    assert restarted.get(removed.id) is None
    assert restarted.get(retained.id).title == "Local palette"
    assert restarted.get(custom.id) == custom
    assert len(restarted.for_section(ToolSection.PRESET)) == 3


def test_keyboard_navigation_respects_search_and_kind_filters(tmp_path):
    registry = ToolRegistry(resource_path("tools"), JsonToolRepository(AppPaths(tmp_path)))
    tools = registry.for_section(ToolSection.PRESET)
    model = ToolListModel()
    model.set_tools(tools, selected_id=tools[0].id)

    assert model.adjacentToolId(-1, "all") == tools[0].id
    assert model.adjacentToolId(1, "all") == tools[1].id
    model.set_filter(tools[-1].title)
    assert model.adjacentToolId(1, "all") == tools[-1].id
    assert model.adjacentToolId(1, "not-an-executor") == ""
    model.set_filter("no script matches this query")
    assert model.adjacentToolId(-1, "all") == ""

