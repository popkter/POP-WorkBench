"""Cached static Android analysis with file and tool revision invalidation."""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from poptools.domain.adb_detection import AdbAnalysis, analyze_adb, split_command
from poptools.domain.models import ToolDefinition
from poptools.paths import resolve_tool_source


class ToolAnalysisService:
    def __init__(self, capacity: int = 256) -> None:
        self._capacity = capacity
        self._cache: OrderedDict[str, tuple[ToolDefinition, object, AdbAnalysis]] = OrderedDict()

    @staticmethod
    def _dependency(tool: ToolDefinition) -> object:
        source = tool.executor.command
        if "\n" in source or tool.executor.android_device_mode.value != "auto":
            return None
        words = split_command(source)
        if not words:
            return None
        first = words[1] if words[0] in {"&", ".", "call"} and len(words) > 1 else words[0]
        if Path(first).suffix.casefold() not in {".py", ".ps1", ".sh", ".bat", ".cmd"}:
            return None
        path = resolve_tool_source(first)
        try:
            stat = path.stat()
            return str(path), stat.st_mtime_ns, stat.st_size, stat.st_ino
        except OSError:
            return str(path), None

    def analyze(self, tool: ToolDefinition) -> AdbAnalysis:
        dependency = self._dependency(tool)
        entry = self._cache.get(tool.id)
        if entry is not None and entry[0] == tool and entry[1] == dependency:
            self._cache.move_to_end(tool.id)
            return entry[2]
        result = analyze_adb(tool, resolve_tool_source)
        self._cache[tool.id] = tool.model_copy(deep=True), dependency, result
        self._cache.move_to_end(tool.id)
        while len(self._cache) > self._capacity:
            self._cache.popitem(last=False)
        return result
