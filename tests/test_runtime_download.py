import shutil
import subprocess
from pathlib import Path

import pytest


def test_official_runtime_download_cache_and_validation(tmp_path):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("PowerShell build helper requires pwsh")
    helper = Path(__file__).resolve().parents[1] / "packaging/runtime-download.ps1"
    script = tmp_path / "check.ps1"
    script.write_text(r'''
param([string]$Helper, [string]$Directory)
$ErrorActionPreference = "Stop"
. $Helper
$script:source = Join-Path $Directory "official.zip"
$script:downloadCount = 0
$script:networkFailure = $false
[IO.File]::WriteAllText($script:source, "official runtime")
$expected = (Get-FileHash -LiteralPath $script:source -Algorithm SHA256).Hash

function Invoke-WebRequest {
    [CmdletBinding()]
    param($Uri, $OutFile, $MaximumRetryCount, $RetryIntervalSec)
    $script:downloadCount++
    if ($script:networkFailure) {
        [IO.File]::WriteAllText($OutFile, "partial transfer")
        throw "network failure"
    }
    Copy-Item -LiteralPath $script:source -Destination $OutFile
}

$target = Join-Path $Directory "cache/runtime.zip"
Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $target -Sha256 $expected
if ($script:downloadCount -ne 1) { throw "Missing archive was not downloaded" }
Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $target -Sha256 $expected
if ($script:downloadCount -ne 1) { throw "Valid cache was downloaded again" }

[IO.File]::WriteAllText($target, "corrupt cache")
Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $target -Sha256 $expected
if ($script:downloadCount -ne 2) { throw "Invalid cache was reused" }
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expected) {
    throw "Downloaded runtime was not activated"
}

$bad = Join-Path $Directory "cache/invalid.zip"
[IO.File]::WriteAllText($script:source, "wrong download")
$rejected = $false
try {
    Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $bad -Sha256 $expected
} catch {
    if ($_.Exception.Message -notmatch "checksum mismatch") { throw }
    $rejected = $true
}
if (-not $rejected -or (Test-Path -LiteralPath $bad)) { throw "Wrong checksum was accepted" }

$script:networkFailure = $true
$rejected = $false
try {
    Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $bad -Sha256 $expected
} catch {
    if ($_.Exception.Message -notmatch "network failure") { throw }
    $rejected = $true
}
if (-not $rejected -or (Test-Path -LiteralPath $bad)) { throw "Partial transfer was accepted" }
if (Get-ChildItem -LiteralPath (Split-Path -Parent $target) -Filter "*.download-*") {
    throw "Incomplete transfer was not cleaned"
}
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expected) {
    throw "A failed download changed the previously verified runtime"
}
Write-Output "PASS: download, cache hit, corrupt cache repair, checksum rejection, transfer cleanup"
''', encoding="utf-8")
    result = subprocess.run(
        [pwsh, "-NoProfile", "-NonInteractive", "-File", str(script),
         "-Helper", str(helper), "-Directory", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
