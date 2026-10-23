import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("shell", ["powershell", "pwsh"])
def test_official_runtime_download_cache_and_validation(tmp_path, shell):
    executable = shutil.which(shell)
    if not executable:
        pytest.skip(f"PowerShell build helper requires {shell}")
    helper = Path(__file__).resolve().parents[1] / "packaging/runtime-download.ps1"
    script = tmp_path / "check.ps1"
    script.write_text(r'''
param([string]$Helper, [string]$Directory)
$ErrorActionPreference = "Stop"
# Use this shell's utility module even when launched from a different PS version.
Import-Module (Join-Path $PSHOME "Modules/Microsoft.PowerShell.Utility") -ErrorAction Stop
. $Helper
$script:source = Join-Path $Directory "official.zip"
$script:downloadCount = 0
$script:networkFailure = $false
$script:transientFailures = 0
$script:sleepCount = 0
[IO.File]::WriteAllText($script:source, "official runtime")
$expected = (Get-FileHash -LiteralPath $script:source -Algorithm SHA256).Hash

function Invoke-WebRequest {
    [CmdletBinding()]
    # Deliberately accept only parameters supported by Windows PowerShell 5.1.
    param($Uri, $OutFile, [switch]$UseBasicParsing)
    if (-not $UseBasicParsing) { throw "Basic parsing must be enabled" }
    $script:downloadCount++
    if ($script:networkFailure -or $script:transientFailures -gt 0) {
        if ($script:transientFailures -gt 0) { $script:transientFailures-- }
        [IO.File]::WriteAllText($OutFile, "partial transfer")
        throw "network failure"
    }
    Copy-Item -LiteralPath $script:source -Destination $OutFile
}

function Start-Sleep {
    param([int]$Seconds)
    if ($Seconds -ne 3) { throw "Unexpected retry interval" }
    $script:sleepCount++
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
if ($script:downloadCount -ne 3) { throw "Checksum mismatch should not be retried" }

[IO.File]::WriteAllText($script:source, "official runtime")
$script:transientFailures = 2
Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $bad -Sha256 $expected
if ($script:downloadCount -ne 6 -or $script:sleepCount -ne 2) {
    throw "Transient download failure was not retried"
}
if ((Get-FileHash -LiteralPath $bad -Algorithm SHA256).Hash -ne $expected) {
    throw "Retry did not replace the partial download"
}
Remove-Item -LiteralPath $bad

$script:networkFailure = $true
$rejected = $false
try {
    Get-VerifiedRuntime -Uri "https://example.test/official.zip" -Destination $bad -Sha256 $expected
} catch {
    if ($_.Exception.Message -notmatch "network failure") { throw }
    $rejected = $true
}
if (-not $rejected -or (Test-Path -LiteralPath $bad)) { throw "Partial transfer was accepted" }
if ($script:downloadCount -ne 10 -or $script:sleepCount -ne 5) {
    throw "Persistent failure did not stop after three retries"
}
if (Get-ChildItem -LiteralPath (Split-Path -Parent $target) -Filter "*.download-*") {
    throw "Incomplete transfer was not cleaned"
}
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expected) {
    throw "A failed download changed the previously verified runtime"
}
Write-Output "PASS: download, cache, checksum rejection, retries, transfer cleanup"
''', encoding="utf-8")
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-File", str(script),
         "-Helper", str(helper), "-Directory", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
