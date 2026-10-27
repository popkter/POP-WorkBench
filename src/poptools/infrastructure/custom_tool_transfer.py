from __future__ import annotations

import json
from typing import Any

from poptools.domain.models import ExecutorKind, ToolDefinition, ToolOrigin, ToolSection
from poptools.domain.parameter_templates import strip_parameter_defaults

TRANSFER_FORMAT = "poptools.custom-script"
TRANSFER_FORMAT_VERSION = 1


def encode_custom_tool(tool: ToolDefinition) -> str:
    if tool.section != ToolSection.CUSTOM:
        raise ValueError("只能分享客制脚本")
    # Sanitize a detached export, never the local tool or its persisted defaults.
    shared = tool.model_dump(mode="json")
    for parameter in shared["parameters"]:
        parameter.pop("default", None)
    executor = shared["executor"]
    executor["command"] = strip_parameter_defaults(executor["command"])
    executor["args"] = [strip_parameter_defaults(value) for value in executor["args"]]
    executor["env"] = {
        name: strip_parameter_defaults(value) for name, value in executor["env"].items()
    }
    if executor["cwd"] is not None:
        executor["cwd"] = strip_parameter_defaults(executor["cwd"])
    payload = {
        "format": TRANSFER_FORMAT,
        "format_version": TRANSFER_FORMAT_VERSION,
        "tool": shared,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def decode_custom_tool(text: str) -> ToolDefinition:
    if not text.strip():
        raise ValueError("剪贴板中没有可导入的脚本")
    try:
        payload: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("剪贴板内容不是有效的脚本 JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("剪贴板内容不是单个客制脚本")
    if "format" in payload:
        if payload.get("format") != TRANSFER_FORMAT:
            raise ValueError("剪贴板内容不是泡泡的工作台客制脚本")
        if payload.get("format_version") != TRANSFER_FORMAT_VERSION:
            raise ValueError("此脚本分享格式版本暂不支持")
        payload = payload.get("tool")
    if not isinstance(payload, dict):
        raise ValueError("剪贴板中的脚本数据不完整")

    try:
        tool = ToolDefinition.model_validate(payload)
    except Exception as exc:
        raise ValueError("剪贴板中的脚本格式无效") from exc
    if tool.section != ToolSection.CUSTOM:
        raise ValueError("只能导入客制脚本")
    if tool.executor.kind == ExecutorKind.INTERNAL:
        raise ValueError("客制脚本不能使用应用内部运行方式")
    if not tool.executor.command.strip():
        raise ValueError("导入的脚本命令不能为空")

    return tool.model_copy(
        update={
            "origin": ToolOrigin.CUSTOM,
            "section": ToolSection.CUSTOM,
            "editable": True,
            "enabled": True,
        }
    )
