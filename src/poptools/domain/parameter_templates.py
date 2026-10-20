from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from poptools.domain.models import ParameterDefinition, ParameterKind, ParameterOption

PLACEHOLDER_PATTERN = re.compile(r"\$\{([^{}]+)\}")
DECLARATION_PATTERN = re.compile(
    r"^[ \t]*(?i:Var|pVal)[ \t]+(?P<id>[^\s:=]+)[ \t]*(?::|=)[ \t]*"
    r"\$\{(?P<definition>[^{}\r\n]+)\}[ \t]*(?:\r?\n|$)",
    re.MULTILINE,
)


@dataclass(frozen=True)
class _ParsedPlaceholder:
    parameter_id: str
    default: str | None
    kind: ParameterKind = ParameterKind.TEXT
    options: tuple[ParameterOption, ...] = ()
    explicit_type: bool = False


def _validate_parameter_id(parameter_id: str) -> None:
    if not parameter_id or not parameter_id.replace("_", "").isalnum():
        raise ValueError(
            f"参数名称“{parameter_id}”只能包含中文、字母、数字或下划线；"
            "如需设置默认值，请使用 ${参数名:默认值}"
        )


def _parse_parameter_name(name: str) -> tuple[str, ParameterKind]:
    parameter_id, type_separator, parameter_type = name.strip().partition("@")
    _validate_parameter_id(parameter_id)
    if not type_separator:
        return parameter_id, ParameterKind.TEXT
    kinds = {kind.value: kind for kind in ParameterKind if kind != ParameterKind.ANDROID_DEVICE}
    kinds.pop("directory")
    kinds["dir"] = ParameterKind.DIRECTORY
    kind = kinds.get(parameter_type.strip())
    if kind is None:
        raise ValueError(
            f"参数“{parameter_id}”使用了不支持的控件类型“{parameter_type.strip()}”"
        )
    return parameter_id, kind


def _parse_choice_options(content: str, *, explicit: bool = False) -> tuple[ParameterOption, ...]:
    parts = content.split("|")
    if (not explicit and len(parts) < 2) or not all("=" in part for part in parts):
        if explicit:
            raise ValueError("选项必须使用“显示文字=实际值”格式，并用 | 分隔")
        return ()

    options: list[ParameterOption] = []
    labels: set[str] = set()
    for part in parts:
        label, _, value = part.partition("=")
        normalized_label = label.strip()
        normalized_value = value.strip()
        if not normalized_label or not normalized_value:
            raise ValueError("下拉选项必须使用“显示文字=实际值”格式，且两侧不能为空")
        if normalized_label in labels:
            raise ValueError(f"下拉选项“{normalized_label}”重复")
        labels.add(normalized_label)
        options.append(ParameterOption(label=normalized_label, value=normalized_value))
    return tuple(options)


def _parse_placeholder(content: str) -> _ParsedPlaceholder:
    """Parse current colon syntax while retaining legacy equals syntax."""

    colon_index = content.find(":")
    equals_index = content.find("=")
    if colon_index >= 0 and (equals_index < 0 or colon_index < equals_index):
        name, _, definition = content.partition(":")
        parameter_id, parameter_kind = _parse_parameter_name(name)
        explicit_type = "@" in name
        if parameter_kind in (ParameterKind.CHOICE, ParameterKind.RADIO):
            options = _parse_choice_options(definition, explicit=True)
            return _ParsedPlaceholder(
                parameter_id, options[0].value, parameter_kind, options, True
            )
        options = _parse_choice_options(definition) if (
            not explicit_type or parameter_kind in (ParameterKind.FILE, ParameterKind.DIRECTORY)
        ) else ()
        if options:
            if parameter_kind != ParameterKind.TEXT:
                raise ValueError("文件或文件夹参数不能同时定义为下拉选择框")
            return _ParsedPlaceholder(
                parameter_id,
                options[0].value,
                ParameterKind.CHOICE,
                options,
            )
        _validate_template_default(parameter_id, parameter_kind, definition)
        return _ParsedPlaceholder(parameter_id, definition, parameter_kind, (), explicit_type)

    # Compatibility with templates created before the title/definition separator
    # changed to ':', including ${name=default} and ${on=1|off=0}.
    legacy_options = _parse_choice_options(content) if "@" not in content.partition("=")[0] else ()
    if legacy_options:
        parameter_id = legacy_options[0].label
        _validate_parameter_id(parameter_id)
        return _ParsedPlaceholder(
            parameter_id,
            legacy_options[0].value,
            ParameterKind.CHOICE,
            legacy_options,
        )

    name, separator, default = content.partition("=")
    parameter_id, parameter_kind = _parse_parameter_name(name)
    if parameter_kind in (ParameterKind.CHOICE, ParameterKind.RADIO):
        raise ValueError("选择框必须定义至少一个“显示文字=实际值”选项")
    if separator:
        _validate_template_default(parameter_id, parameter_kind, default)
    return _ParsedPlaceholder(
        parameter_id, default if separator else None, parameter_kind, (), "@" in name
    )


def validate_parameter_value(parameter: ParameterDefinition, value: object) -> object:
    """Validate before execution; keep numeric spelling and multiline content intact."""
    kind = parameter.kind
    if kind == ParameterKind.BOOLEAN:
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            return False
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise ValueError(f"参数“{parameter.label}”必须是 true 或 false")
    if value in (None, ""):
        return value
    if kind == ParameterKind.INTEGER and not re.fullmatch(r"[+-]?[0-9]+", str(value)):
        raise ValueError(f"参数“{parameter.label}”必须是整数")
    if kind == ParameterKind.NUMBER:
        try:
            valid = bool(re.fullmatch(
                r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", str(value)
            )) and Decimal(str(value)).is_finite()
        except InvalidOperation:
            valid = False
        if not valid:
            raise ValueError(f"参数“{parameter.label}”必须是有效数字")
    if kind in (ParameterKind.CHOICE, ParameterKind.RADIO):
        allowed = [option.value if isinstance(option, ParameterOption) else option
                   for option in parameter.options]
        if str(value) not in allowed:
            raise ValueError(f"参数“{parameter.label}”必须选择一个有效选项")
    return value


def _validate_template_default(parameter_id: str, kind: ParameterKind, default: str) -> None:
    if kind == ParameterKind.SECRET and default:
        raise ValueError(
            f"密码参数“{parameter_id}”不能设置默认值，"
            f"请改用 ${{{parameter_id}@secret}} 并在运行前输入"
        )
    validate_parameter_value(ParameterDefinition(id=parameter_id, label=parameter_id, kind=kind),
                             default)


def _parse_declarations(
    template: str,
) -> list[tuple[str, str, str | None, ParameterKind, tuple[ParameterOption, ...]]]:
    declarations: list[
        tuple[str, str, str | None, ParameterKind, tuple[ParameterOption, ...]]
    ] = []
    for match in DECLARATION_PATTERN.finditer(template):
        parameter = _parse_placeholder(match.group("id"))
        definition = _parse_placeholder(match.group("definition"))
        declarations.append(
            (
                parameter.parameter_id,
                definition.parameter_id,
                definition.default,
                definition.kind,
                definition.options,
            )
        )
    return declarations


def _script_body(template: str) -> str:
    """Remove Var metadata lines before a script is executed or scanned."""

    return DECLARATION_PATTERN.sub("", template)


def extract_parameter_ids(templates: Iterable[str]) -> list[str]:
    """Extract unique ${parameter} names in display order."""

    result: list[str] = []
    for template in templates:
        for parameter_id, _, _, _, _ in _parse_declarations(template):
            if parameter_id not in result:
                result.append(parameter_id)
        for match in PLACEHOLDER_PATTERN.finditer(_script_body(template)):
            parameter_id = _parse_placeholder(match.group(1)).parameter_id
            if parameter_id not in result:
                result.append(parameter_id)
    return result


def synchronize_parameters(
    templates: Iterable[str],
    existing: Sequence[ParameterDefinition] = (),
) -> list[ParameterDefinition]:
    """Derive controls from templates while retaining legacy parameter metadata."""

    existing_by_id = {parameter.id: parameter for parameter in existing}
    parameters: list[ParameterDefinition] = []
    parsed: dict[str, tuple[str, _ParsedPlaceholder, bool]] = {}
    materialized_templates = list(templates)

    for template in materialized_templates:
        for parameter_id, label, default, kind, options in _parse_declarations(template):
            current_declaration = parsed.get(parameter_id)
            declaration = (
                label, _ParsedPlaceholder(parameter_id, default, kind, options, True), True
            )
            if current_declaration is not None and current_declaration != declaration:
                raise ValueError(f"参数“{parameter_id}”设置了多个不同的声明")
            parsed[parameter_id] = declaration

    for template in materialized_templates:
        for match in PLACEHOLDER_PATTERN.finditer(_script_body(template)):
            placeholder = _parse_placeholder(match.group(1))
            parameter_id = placeholder.parameter_id
            if parameter_id not in parsed:
                parsed[parameter_id] = (parameter_id, placeholder, False)
            else:
                label, current, declared = parsed[parameter_id]
                # Bare references can reuse any inline or declared definition.
                if not placeholder.explicit_type and placeholder.default is None:
                    continue
                if (not declared and not current.explicit_type
                        and current.default is None and not current.options):
                    parsed[parameter_id] = (label, placeholder, declared)
                    continue
                if current.kind != placeholder.kind:
                    raise ValueError(f"参数“{parameter_id}”设置了多个不同的控件类型")
                if current.options != placeholder.options:
                    raise ValueError(f"参数“{parameter_id}”设置了多个不同的选项")
                if (current.default is not None and placeholder.default is not None
                        and current.default != placeholder.default):
                    raise ValueError(f"参数“{parameter_id}”设置了多个不同的默认值")
                if current.default is None:
                    parsed[parameter_id] = (label, placeholder, declared)

    for parameter_id, (label, definition, declared) in parsed.items():
        default, kind, options = definition.default, definition.kind, definition.options
        resolved_default: object = default or ""
        if kind == ParameterKind.BOOLEAN:
            resolved_default = validate_parameter_value(
                ParameterDefinition(id=parameter_id, label=label, kind=kind), default
            )
        existing_parameter = existing_by_id.get(parameter_id)
        if existing_parameter is not None:
            # Default, choice kind and options are derived from the current
            # template. They must be replaced rather than only filled in, or an
            # edited `${name:first=1|second=2}` keeps rendering as a choice after
            # it becomes `${name:value}`.
            updates: dict[str, object] = {
                "default": resolved_default,
                "options": list(options),
            }
            if declared:
                updates["label"] = label
            if kind != ParameterKind.TEXT or definition.explicit_type or declared:
                updates["kind"] = kind
            elif existing_parameter.kind in (
                ParameterKind.CHOICE, ParameterKind.RADIO,
                ParameterKind.FILE, ParameterKind.DIRECTORY
            ):
                updates["kind"] = ParameterKind.TEXT
            parameters.append(existing_parameter.model_copy(update=updates))
            continue
        parameters.append(
            ParameterDefinition(
                id=parameter_id,
                label=label,
                required=True,
                default=resolved_default,
                placeholder=f"请输入{parameter_id}",
                kind=kind,
                options=list(options),
            )
        )
    return parameters


def render_template(template: str, values: dict[str, object]) -> str:
    definitions = {parameter.id: parameter for parameter in synchronize_parameters([template])}

    def replace(match: re.Match[str]) -> str:
        placeholder = _parse_placeholder(match.group(1))
        parameter = definitions[placeholder.parameter_id]
        value = values.get(parameter.id, parameter.default)
        if parameter.kind == ParameterKind.BOOLEAN:
            value = validate_parameter_value(parameter, value)
            return str(value).lower()
        return str(value)

    return PLACEHOLDER_PATTERN.sub(replace, _script_body(template))


def strip_parameter_defaults(template: str) -> str:
    """Remove literal defaults for sharing, retaining types and choice definitions."""
    def replace(match: re.Match[str]) -> str:
        placeholder = _parse_placeholder(match.group(1))
        # Choice values define the control, rather than the sender's saved input.
        if placeholder.options or placeholder.default is None:
            return match.group(0)
        name = match.group(1).split(":", 1)[0].split("=", 1)[0].strip()
        return "${" + name + "}"

    # Includes Var/pVal definitions without removing their labels or declarations.
    return PLACEHOLDER_PATTERN.sub(replace, template)


def update_parameter_default(template: str, parameter_id: str, default: str) -> str:
    """Persist a text parameter default back into its placeholder definition."""

    _validate_parameter_id(parameter_id)
    if any(character in default for character in "{}\r\n"):
        raise ValueError("默认值不能包含花括号或换行")

    replacements: list[tuple[int, int, str]] = []
    declaration_ranges: list[tuple[int, int]] = []
    declaration_found = False
    for match in DECLARATION_PATTERN.finditer(template):
        declaration_ranges.append(match.span())
        declared_parameter = _parse_placeholder(match.group("id"))
        if declared_parameter.parameter_id != parameter_id:
            continue
        definition = _parse_placeholder(match.group("definition"))
        if definition.kind == ParameterKind.SECRET:
            raise ValueError("密码参数不能保存默认值")
        if definition.options:
            raise ValueError("选择框不能通过文本默认值按钮修改")
        definition_name = match.group("definition").split(":", 1)[0].split("=", 1)[0].strip()
        replacement = f"{definition_name}:{default}" if default else definition_name
        parsed_replacement = _parse_placeholder(replacement)
        if parsed_replacement.options:
            raise ValueError("该默认值会被识别成选择框，请修改字符串内容")
        start, end = match.span("definition")
        replacements.append((start, end, replacement))
        declaration_found = True

    if not declaration_found:
        inline_definitions = [
            _parse_placeholder(match.group(1)) for match in PLACEHOLDER_PATTERN.finditer(template)
            if not any(start <= match.start() < end for start, end in declaration_ranges)
        ]
        has_definition = any(item.parameter_id == parameter_id
                             and (item.explicit_type or item.default is not None)
                             for item in inline_definitions)
        for match in PLACEHOLDER_PATTERN.finditer(template):
            if any(start <= match.start() < end for start, end in declaration_ranges):
                continue
            placeholder = _parse_placeholder(match.group(1))
            if placeholder.parameter_id != parameter_id:
                continue
            if has_definition and not placeholder.explicit_type and placeholder.default is None:
                continue
            if placeholder.kind == ParameterKind.SECRET:
                raise ValueError("密码参数不能保存默认值")
            if placeholder.options:
                raise ValueError("选择框不能通过文本默认值按钮修改")
            placeholder_name = match.group(1).split(":", 1)[0].split("=", 1)[0].strip()
            replacement = f"{placeholder_name}:{default}" if default else placeholder_name
            parsed_replacement = _parse_placeholder(replacement)
            if parsed_replacement.options:
                raise ValueError("该默认值会被识别成选择框，请修改字符串内容")
            start, end = match.span(1)
            replacements.append((start, end, replacement))

    if not replacements:
        raise ValueError(f"脚本中没有找到参数“{parameter_id}”的文本模板")

    updated = template
    for start, end, replacement in reversed(replacements):
        updated = updated[:start] + replacement + updated[end:]
    return updated
