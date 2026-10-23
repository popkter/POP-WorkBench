from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from poptools.domain.models import (
    ExecutorDefinition,
    ParameterDefinition,
    ToolDefinition,
    ToolOrigin,
)
from poptools.infrastructure.json_tool_repository import JsonToolRepository
from poptools.paths import AppPaths


def definition():
    return ToolDefinition(
        id="custom.cache", origin="custom", section="custom", title="Before",
        executor=ExecutorDefinition(kind="python", command="print(1)"),
        parameters=[ParameterDefinition(id="value", label="Value", default="original")],
    )


def test_unchanged_catalog_reuses_disk_reads_without_sharing_mutable_models(tmp_path):
    repository = JsonToolRepository(AppPaths(tmp_path))
    repository.save_tool(definition())
    returned = repository.list_tools()[0]
    returned.parameters[0].default = "unsaved"
    returned.executor.command = "unsaved"
    returned.title = "unsaved"
    # A warm refresh must not reopen every script; it still returns disk state.
    with patch.object(Path, "read_text", side_effect=AssertionError("unnecessary disk read")):
        assert repository.list_tools() == [definition()]


def test_reload_detects_external_replacement_with_same_size_and_modified_time(tmp_path):
    repository = JsonToolRepository(AppPaths(tmp_path))
    original = definition()
    repository.save_tool(original)
    assert repository.list_tools() == [original]
    target = repository.paths.custom_dir / f"{original.id}.json"
    before = target.stat()
    replacement = target.with_suffix(".replacement")
    replacement.write_bytes(target.read_bytes().replace(b"Before", b"After!"))
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    replacement.replace(target)
    assert target.stat().st_size == before.st_size
    assert repository.list_tools()[0].title == "After!"
    target.unlink()
    assert repository.list_tools() == []
    repository.save_tool(original)
    assert repository.list_tools() == [original]


def test_cached_script_corruption_is_backed_up_and_not_returned(tmp_path):
    repository = JsonToolRepository(AppPaths(tmp_path))
    repository.save_tool(definition())
    repository.list_tools()
    target = repository.paths.custom_dir / "custom.cache.json"
    target.write_text("invalid JSON", "utf-8")
    assert repository.list_tools() == []
    assert not target.exists()
    backups = list(repository.paths.backups_dir.glob("*.invalid"))
    assert len(backups) == 1
    assert backups[0].read_text("utf-8") == "invalid JSON"
    assert repository.list_tools() == []


def test_migrated_legacy_custom_file_survives_cached_edit_and_delete(tmp_path):
    repository = JsonToolRepository(AppPaths(tmp_path))
    original = definition().model_copy(update={"origin": ToolOrigin.OVERRIDE, "editable": False})
    legacy = repository.paths.custom_dir / "legacy-name.json"
    legacy.write_text(original.model_dump_json(), "utf-8")
    loaded = repository.list_tools()
    assert loaded[0].origin == "custom" and loaded[0].editable
    assert not legacy.exists()
    assert repository.list_tools() == loaded
    loaded[0].title = "Edited"
    repository.save_tool(loaded[0])
    assert repository.list_tools()[0].title == "Edited"
    assert repository.delete_tool(loaded[0].id)
    assert repository.list_tools() == []
