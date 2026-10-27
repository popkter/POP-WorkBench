"""Exercise MSVC setup with PATH sizes that break inherited cmd environments."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows MSVC environment"),
]


@pytest.mark.parametrize("path_length", [7100, 10000])
def test_msvc_setup_preserves_long_paths_and_is_repeatable(tmp_path, path_length):
    vswhere = Path(os.environ.get("PROGRAMFILES(X86)", "")) / (
        "Microsoft Visual Studio/Installer/vswhere.exe"
    )
    if not vswhere.is_file():
        pytest.skip("Visual Studio Installer is unavailable")
    installation = subprocess.run(
        [str(vswhere), "-latest", "-prerelease", "-products", "*", "-requires",
         "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"],
        capture_output=True, check=True,
    )
    if not installation.stdout.strip():
        pytest.skip("MSVC x64 tools are unavailable")

    script = tmp_path / "check-msvc.ps1"
    script.write_text(
        r"""
param($BuildScript, $TargetLength)
$ErrorActionPreference = 'Stop'
$Ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $BuildScript, [ref]$null, [ref]$null)
$Function = $Ast.Find({ param($Node)
    $Node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
    $Node.Name -eq 'Initialize-MsvcEnvironment'
}, $true)
Invoke-Expression $Function.Extent.Text
$Sentinel = 'C:\build-tools-' + [char]0x4e2d + [char]0x6587
$Entries = @("$env:SystemRoot\System32", $Sentinel)
for ($Index = 0; ($Entries -join ';').Length -lt [int]$TargetLength; $Index++) {
    $Entries += ('C:\build-path-padding-' + $Index.ToString('000') + '\' + ('x' * 28))
}
$env:Path = $Entries -join ';'
$env:VSCMD_ARG_TGT_ARCH = ''
$env:INCLUDE = 'C:\stale-include;' * 600
$env:LIB = 'C:\stale-library;' * 600
$env:__VSCMD_PREINIT_PATH = $env:Path
Initialize-MsvcEnvironment
foreach ($Entry in $Entries) {
    if ($Entry -notin ($env:Path -split ';')) { throw 'Original PATH entry was lost' }
}
$FirstPath = $env:Path
Initialize-MsvcEnvironment
if ($env:Path -cne $FirstPath) { throw 'Repeated initialization changed PATH' }
if ($env:VSCMD_ARG_TGT_ARCH -ne 'x64') { throw 'Expected x64 compiler target' }
$Source = Join-Path $PSScriptRoot 'probe.c'
$Executable = Join-Path $PSScriptRoot 'probe.exe'
Set-Content -LiteralPath $Source -Value 'int main(void) { return 0; }' -Encoding ASCII
& (Get-Command cl.exe).Source /nologo $Source "/Fe$Executable" "/Fo$PSScriptRoot\probe.obj"
if ($LASTEXITCODE -ne 0) { throw 'C compiler/linker probe failed' }
& $Executable
if ($LASTEXITCODE -ne 0) { throw 'Compiled probe failed' }
""",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
         str(ROOT / "packaging/build-native.ps1"), str(path_length)],
        cwd=tmp_path, capture_output=True, timeout=60,
    )
    assert result.returncode == 0, (result.stdout + result.stderr).decode(errors="replace")
