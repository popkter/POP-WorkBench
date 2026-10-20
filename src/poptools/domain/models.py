from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

LEGACY_TOOL_IDS = {
    "online.colors": "preset.colors",
    "local.android.scrcpy": "preset.android.scrcpy",
}


class ToolOrigin(StrEnum):
    BUILTIN = "builtin"
    OVERRIDE = "override"
    CUSTOM = "custom"


class ToolSection(StrEnum):
    PRESET = "preset"
    CUSTOM = "custom"


class ExecutorKind(StrEnum):
    INTERNAL = "internal"
    PROCESS = "process"
    PYTHON = "python"
    POWERSHELL = "powershell"
    BASH = "bash"
    BATCH = "batch"
    URL = "url"


class AndroidDeviceMode(StrEnum):
    AUTO = "auto"
    USE = "use"
    NONE = "none"


class ParameterKind(StrEnum):
    TEXT = "text"
    MULTILINE = "multiline"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHOICE = "choice"
    RADIO = "radio"
    FILE = "file"
    DIRECTORY = "directory"
    ANDROID_DEVICE = "android_device"
    SECRET = "secret"


class ParameterOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    value: str


class ParameterDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    kind: ParameterKind = ParameterKind.TEXT
    required: bool = False
    default: Any = ""
    placeholder: str = ""
    options: list[str | ParameterOption] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value or not value.replace("_", "").isalnum():
            raise ValueError("parameter id must be alphanumeric with optional underscores")
        return value


class ExecutorDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ExecutorKind
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: str | None = None
    timeout_seconds: int | None = Field(default=300, ge=1, le=86400)
    encoding: str = "utf-8"
    env: dict[str, str] = Field(default_factory=dict)
    requirements: list[str] = Field(default_factory=list)
    android_device_mode: AndroidDeviceMode = AndroidDeviceMode.AUTO


class PresentationDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    icon: str = "terminal"
    order: int = 100
    confirm_before_run: bool = False
    output_mode: str = "console"


class ToolDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    schema_version: int = 1
    id: str
    revision: int = Field(default=1, ge=1)
    origin: ToolOrigin = ToolOrigin.BUILTIN
    section: ToolSection
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    editable: bool = True
    enabled: bool = True
    executor: ExecutorDefinition
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    presentation: PresentationDefinition = Field(default_factory=PresentationDefinition)

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_definition(cls, value: Any) -> Any:
        """Accept v1 identifiers/sections while exposing only preset/custom."""
        if not isinstance(value, dict):
            return value
        legacy_id = value.get("id")
        if legacy_id in LEGACY_TOOL_IDS:
            value = {**value, "id": LEGACY_TOOL_IDS[legacy_id]}
        section = value.get("section")
        if section == "online":
            value = {**value, "section": ToolSection.PRESET.value}
        elif section == "local":
            origin = value.get("origin", ToolOrigin.BUILTIN.value)
            migrated = (
                ToolSection.PRESET
                if origin == ToolOrigin.BUILTIN.value
                else ToolSection.CUSTOM
            )
            value = {**value, "section": migrated.value}
        return value

    @field_validator("id")
    @classmethod
    def validate_tool_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}", value):
            raise ValueError(
                "tool id must start with an ASCII letter or digit and contain only "
                "letters, digits, dots, underscores, or hyphens"
            )
        return value

    def to_qml(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
