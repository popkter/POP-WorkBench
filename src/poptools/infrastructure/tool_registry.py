from __future__ import annotations

import json
import uuid
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path

from poptools.domain.models import (
    AndroidDeviceMode,
    ExecutorDefinition,
    ExecutorKind,
    ParameterKind,
    PresentationDefinition,
    ToolDefinition,
    ToolOrigin,
    ToolSection,
)
from poptools.domain.parameter_templates import (
    synchronize_parameters,
    update_parameter_default,
    validate_parameter_value,
)
from poptools.domain.repositories import ToolRepository


class ToolRegistry:
    def __init__(self, builtin_dir: Path, repository: ToolRepository) -> None:
        self.builtin_dir = builtin_dir
        self.repository = repository
        self._builtin: dict[str, ToolDefinition] = {}
        self._tools: dict[str, ToolDefinition] = {}
        self.reload()

    def reload(self) -> None:
        self._builtin = {tool.id: tool for tool in self._load_builtin()}
        effective = {
            tool_id: tool for tool_id, tool in self._builtin.items()
            if tool.enabled or tool.section != ToolSection.PRESET
        }
        for tool in self.repository.list_tools():
            # Local overrides cannot restore removed or hidden built-in presets.
            if tool.section == ToolSection.PRESET and tool.id not in effective:
                continue
            effective[tool.id] = tool
        self._tools = effective

    def all(self) -> list[ToolDefinition]:
        return sorted(
            (tool for tool in self._tools.values() if tool.enabled),
            key=lambda tool: (tool.section.value, tool.presentation.order, tool.title),
        )

    def for_section(self, section: ToolSection | str) -> list[ToolDefinition]:
        section_value = ToolSection(section)
        return [tool for tool in self.all() if tool.section == section_value]

    def get(self, tool_id: str) -> ToolDefinition | None:
        return self._tools.get(tool_id)

    def update_tool(
        self,
        tool_id: str,
        *,
        title: str,
        description: str,
        kind: ExecutorKind | str,
        command: str,
        args: list[str],
        icon: str | None = None,
        android_device_mode: str | None = None,
    ) -> ToolDefinition:
        current = self._tools[tool_id]
        executor = current.executor.model_copy(
            update={"kind": ExecutorKind(kind), "command": command.strip(), "args": args}
        )
        if android_device_mode is not None:
            executor.android_device_mode = AndroidDeviceMode(android_device_mode)
        parameters = synchronize_parameters(
            [executor.command, *executor.args, *executor.env.values()],
            current.parameters,
        )
        origin = ToolOrigin.CUSTOM if current.origin == ToolOrigin.CUSTOM else ToolOrigin.OVERRIDE
        presentation = current.presentation
        if icon is not None:
            presentation = presentation.model_copy(
                update={"icon": icon.strip() or "terminal"}
            )
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "origin": origin,
                "section": ToolSection.CUSTOM if origin == ToolOrigin.CUSTOM else current.section,
                "title": title.strip() or current.title,
                "description": description.strip(),
                "executor": executor,
                "parameters": parameters,
                "presentation": presentation,
            }
        )
        self.repository.save_tool(updated)
        self.reload()
        return self._tools[tool_id]

    def save_override(
        self,
        tool_id: str,
        *,
        title: str,
        description: str,
        kind: ExecutorKind | str,
        command: str,
        args: list[str],
        icon: str | None = None,
    ) -> ToolDefinition:
        """Compatibility alias for callers created before repository abstraction."""

        return self.update_tool(
            tool_id,
            title=title,
            description=description,
            kind=kind,
            command=command,
            args=args,
            icon=icon,
        )

    def create_custom(
        self,
        *,
        title: str,
        description: str,
        kind: ExecutorKind | str,
        command: str,
        icon: str = "terminal",
        android_device_mode: str = "auto",
    ) -> ToolDefinition:
        normalized_command = command.strip()
        if not normalized_command:
            raise ValueError("命令内容不能为空")
        tool_id = f"custom.{uuid.uuid4().hex}"
        parameters = synchronize_parameters([normalized_command])
        tool = ToolDefinition(
            id=tool_id,
            origin=ToolOrigin.CUSTOM,
            section=ToolSection.CUSTOM,
            title=title.strip() or "未命名命令",
            description=description.strip(),
            editable=True,
            executor=ExecutorDefinition(
                kind=ExecutorKind(kind), command=normalized_command,
                android_device_mode=AndroidDeviceMode(android_device_mode),
            ),
            parameters=parameters,
            presentation=PresentationDefinition(icon=icon.strip() or "terminal"),
        )
        self.repository.save_tool(tool)
        self.reload()
        return self._tools[tool_id]

    def import_custom(self, tool: ToolDefinition) -> ToolDefinition:
        if tool.origin != ToolOrigin.CUSTOM or tool.section != ToolSection.CUSTOM:
            raise ValueError("只能导入客制脚本")
        self.repository.save_tool(tool)
        self.reload()
        return self._tools[tool.id]

    def set_parameter_default(
        self, tool_id: str, parameter_id: str, default: str
    ) -> ToolDefinition:
        current = self._tools[tool_id]
        parameter = next((item for item in current.parameters if item.id == parameter_id), None)
        if parameter is None:
            raise ValueError("参数不存在")
        if parameter.kind == ParameterKind.SECRET:
            raise ValueError("密码参数不能保存默认值")
        if parameter.kind in (
            ParameterKind.CHOICE, ParameterKind.RADIO,
            ParameterKind.BOOLEAN, ParameterKind.ANDROID_DEVICE
        ):
            raise ValueError("此参数不是文本输入框")
        validate_parameter_value(parameter, default)
        # Metadata supports every literal value, including multiline text and braces.
        # Keep editable script placeholders in sync where the syntax can represent it.
        command = current.executor.command
        if current.editable:
            with suppress(ValueError):
                command = update_parameter_default(command, parameter_id, default)
        updated = current.model_copy(
            update={
                "revision": current.revision + 1,
                "origin": (ToolOrigin.CUSTOM if current.origin == ToolOrigin.CUSTOM
                           else ToolOrigin.OVERRIDE),
                "executor": current.executor.model_copy(update={"command": command}),
                "parameters": [
                    item.model_copy(update={"default": default})
                    if item.id == parameter_id else item
                    for item in current.parameters
                ],
            }
        )
        self.repository.save_tool(updated)
        self.reload()
        return self._tools[tool_id]

    def reset(self, tool_id: str) -> bool:
        changed = self.repository.remove_override(tool_id)
        self.reload()
        return changed

    def delete(self, tool_id: str) -> bool:
        current = self._tools.get(tool_id)
        if current is None or current.section != ToolSection.CUSTOM:
            return False
        if current.origin == ToolOrigin.CUSTOM:
            changed = self.repository.delete_tool(tool_id)
        else:
            deleted = current.model_copy(
                update={
                    "revision": current.revision + 1,
                    "origin": ToolOrigin.OVERRIDE,
                    "enabled": False,
                }
            )
            self.repository.save_tool(deleted)
            changed = True
        self.reload()
        return changed

    def _load_builtin(self) -> Iterable[ToolDefinition]:
        for file_path in sorted(self.builtin_dir.glob("*.json")):
            raw = json.loads(file_path.read_text(encoding="utf-8"))
            entries = raw if isinstance(raw, list) else [raw]
            for entry in entries:
                tool = ToolDefinition.model_validate(entry)
                yield tool
