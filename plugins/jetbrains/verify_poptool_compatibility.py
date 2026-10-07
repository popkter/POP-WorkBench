"""Generate compatibility expectations from the existing PopTool implementation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "src"))
from poptools.domain.models import ParameterDefinition, ParameterKind  # noqa: E402
from poptools.domain.parameter_templates import render_template, synchronize_parameters  # noqa: E402

cases = [
    "${名称}", "${名称:你好}", "${旧格式=默认值}", "${路径@file:C:/中文 空格/a.txt}",
    "${目录@dir:D:/logs}", "${模式:开启=1|关闭=0}", "${on=1|off=0}",
    "Var internal = ${显示名称:默认值}\nWrite-Output '${internal}'",
    "pVal file: ${文件@file}\n${file}",
    "Var mode = ${模式:开启=1|关闭=0}\n${mode}",
    "${名称} ${名称:同一默认值}", "${名称:同一默认值} ${名称}",
    "${值:a=b:c}", "${旧值=a:b}", "${空值:}",
    "${值:1} ${值:2}", "${值@file} ${值@dir}", "${a@bad}",
    "Var a = ${标签:1}\nVar a = ${标签:2}\n${a}",
    "${模式:A=1|A=2}", "${文件@file:A=1|B=2}", "${bad-id}",
    "  Var logs = ${日志@dir:C:/logs}\r\n${logs}",
]
rows = []
for template in cases:
    values = {"名称": "中文\n空格 ' \" $ " + chr(92), "internal": "覆盖", "file": "a b.txt", "mode": "0"}
    try:
        parameters = synchronize_parameters([template])
        rows.append({"template": template, "values": values, "parameters": [p.model_dump(mode="json") for p in parameters], "rendered": render_template(template, values)})
    except ValueError:
        rows.append({"template": template, "error": True})

for kind in ParameterKind:
    if kind in (ParameterKind.CHOICE, ParameterKind.FILE, ParameterKind.DIRECTORY):
        continue
    existing = [ParameterDefinition(id="value", label="保留标签", kind=kind, required=False, default="old")]
    parameters = synchronize_parameters(["${value:new}"], existing)
    rows.append({"template": "${value:new}", "existing": [p.model_dump(mode="json") for p in existing], "parameters": [p.model_dump(mode="json") for p in parameters], "values": {}, "rendered": "new"})

destination = Path(sys.argv[1])
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Generated {len(rows)} cases from PopTool's actual parser: {destination}")
