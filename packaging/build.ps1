param(
    [ValidateSet("Bundled", "Clean", "Both")]
    [string]$Edition = "Both",
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [switch]$KeepRunningApp,
    [string]$VersionOverride = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PythonVendorDir = Join-Path $ProjectRoot "src\poptools\resources\vendor\python"
$PythonManifestPath = Join-Path $PythonVendorDir "python-runtime.json"
$PythonManifest = Get-Content -LiteralPath $PythonManifestPath -Raw | ConvertFrom-Json
$PythonRuntimePackage = Join-Path $PythonVendorDir $PythonManifest.file
$PythonRuntimeInnerDirectory = if ($PythonManifest.directory) {
    [string]$PythonManifest.directory
} else {
    "tools"
}
$ScrcpyVendorDir = Join-Path $ProjectRoot "src\poptools\resources\vendor"
$ScrcpyManifestPath = Join-Path $ScrcpyVendorDir "scrcpy-manifest.json"
$ScrcpyManifest = Get-Content -LiteralPath $ScrcpyManifestPath -Raw | ConvertFrom-Json
$ScrcpyRuntimePackage = Join-Path $ScrcpyVendorDir $ScrcpyManifest.archive
$ScrcpyRuntimeInnerDirectory = if ($ScrcpyManifest.directory) {
    [string]$ScrcpyManifest.directory
} else {
    "scrcpy-win64-v$($ScrcpyManifest.version)"
}

function Find-UvExecutable {
    $UvCommand = Get-Command "uv" -ErrorAction SilentlyContinue
    if ($UvCommand) { return $UvCommand.Source }

    $Candidates = @(
        (Join-Path $ProjectRoot ".venv\Scripts\uv.exe"),
        (Join-Path $ProjectRoot "tools\uv.exe"),
        (Join-Path $env:USERPROFILE ".local\bin\uv.exe"),
        (Join-Path $env:USERPROFILE "scoop\shims\uv.exe"),
        (Join-Path $env:USERPROFILE "scoop\apps\uv\current\uv.exe"),
        (Join-Path $env:USERPROFILE ".cargo\bin\uv.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\uv\uv.exe")
    )
    return $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

function Remove-SingleFileOutput {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }

    try {
        Remove-Item -LiteralPath $Path -Force
        return
    }
    catch {
        $NormalizedPath = [IO.Path]::GetFullPath($Path)
        $LockingProcesses = @(
            Get-Process | ForEach-Object {
                try {
                    if ([string]::Equals(
                        [IO.Path]::GetFullPath($_.Path),
                        $NormalizedPath,
                        [StringComparison]::OrdinalIgnoreCase
                    )) {
                        $_
                    }
                }
                catch {
                    # Access to unrelated system process paths can be denied.
                }
            }
        )

        if ($LockingProcesses.Count -eq 0) { throw }
        $ProcessSummary = ($LockingProcesses | ForEach-Object {
            "$($_.ProcessName) (PID $($_.Id))"
        }) -join ", "
        if ($KeepRunningApp) {
            throw (
                "The previous build is still running: $ProcessSummary. " +
                "Close it or omit -KeepRunningApp so the build can stop it automatically."
            )
        }

        Write-Host "Stopping previous build: $ProcessSummary" -ForegroundColor Yellow
        $LockingProcesses | Stop-Process -Force
        $LockingProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
        for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
            try {
                Remove-Item -LiteralPath $Path -Force
                return
            }
            catch {
                if ($Attempt -eq 20) { throw }
                Start-Sleep -Milliseconds 250
            }
        }
    }
}

function Remove-OneFolderOutput {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return }
    $PackagedExe = Join-Path $Path "泡泡工具箱.exe"
    $NormalizedExe = [IO.Path]::GetFullPath($PackagedExe)
    $RunningProcesses = @(
        Get-Process | ForEach-Object {
            try {
                if ([string]::Equals(
                    [IO.Path]::GetFullPath($_.Path),
                    $NormalizedExe,
                    [StringComparison]::OrdinalIgnoreCase
                )) {
                    $_
                }
            }
            catch {
                # Access to unrelated system process paths can be denied.
            }
        }
    )
    if ($RunningProcesses.Count -gt 0) {
        $ProcessSummary = ($RunningProcesses | ForEach-Object {
            "$($_.ProcessName) (PID $($_.Id))"
        }) -join ", "
        if ($KeepRunningApp) {
            throw (
                "The previous build is still running: $ProcessSummary. " +
                "Close it or omit -KeepRunningApp so the build can stop it automatically."
            )
        }
        Write-Host "Stopping previous build: $ProcessSummary" -ForegroundColor Yellow
        $RunningProcesses | Stop-Process -Force
        $RunningProcesses | Wait-Process -Timeout 10 -ErrorAction SilentlyContinue
    }
    for ($Attempt = 1; $Attempt -le 20; $Attempt++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force
            return
        }
        catch {
            if ($Attempt -eq 20) { throw }
            Start-Sleep -Milliseconds 250
        }
    }
}

function Expand-VerifiedRuntime {
    param(
        [Parameter(Mandatory = $true)][string]$Archive,
        [Parameter(Mandatory = $true)][string]$InnerDirectory,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $Staging = Join-Path $ProjectRoot ("build\runtime-" + [guid]::NewGuid().ToString("N"))
    try {
        New-Item -ItemType Directory -Path $Staging -Force | Out-Null
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($Archive, $Staging)
        $Source = Join-Path $Staging $InnerDirectory
        if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
            throw "Runtime package does not contain the expected directory: $InnerDirectory"
        }
        if (Test-Path -LiteralPath $Destination) {
            Remove-Item -LiteralPath $Destination -Recurse -Force
        }
        Copy-Item -LiteralPath $Source -Destination $Destination -Recurse
    }
    finally {
        if (Test-Path -LiteralPath $Staging) {
            Remove-Item -LiteralPath $Staging -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

if ($Edition -ne "Clean") {
    if (-not (Test-Path -LiteralPath $PythonRuntimePackage)) {
        New-Item -ItemType Directory -Path $PythonVendorDir -Force | Out-Null
        Write-Host "Downloading the private Python runtime package..."
        Invoke-WebRequest -Uri $PythonManifest.url -OutFile $PythonRuntimePackage
    }
    $PythonRuntimePackageHash = (Get-FileHash -LiteralPath $PythonRuntimePackage -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($PythonRuntimePackageHash -ne $PythonManifest.sha256) {
        throw "Private Python runtime package checksum mismatch: $PythonRuntimePackage"
    }
    if (-not (Test-Path -LiteralPath $ScrcpyRuntimePackage -PathType Leaf)) {
        throw "Bundled scrcpy package is missing: $ScrcpyRuntimePackage"
    }
    $ScrcpyRuntimePackageHash = (Get-FileHash -LiteralPath $ScrcpyRuntimePackage -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($ScrcpyRuntimePackageHash -ne $ScrcpyManifest.sha256) {
        throw "Bundled scrcpy package checksum mismatch: $ScrcpyRuntimePackage"
    }
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "Project venv is missing: $VenvPython"
}

$ActualPrefix = & $VenvPython -c "import pathlib,sys; print(pathlib.Path(sys.prefix).resolve())"
$ExpectedPrefix = (Resolve-Path (Join-Path $ProjectRoot ".venv")).Path
if ($ActualPrefix.Trim() -ne $ExpectedPrefix) {
    throw "Build must use the project .venv. Actual prefix: $ActualPrefix"
}

Push-Location $ProjectRoot
$TestWorkspace = Join-Path $ProjectRoot ("build\pytest-" + [guid]::NewGuid().ToString("N"))
try {
    # A venv created by uv records the uv version in pyvenv.cfg, but it does not
    # contain uv.exe. Only require a package installer when dependencies are missing.
    $PrevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # uv creates intentionally minimal virtual environments without pip.
        # The application developer console exposes a managed `pip` command,
        # so tests and builds must also work in a freshly created uv venv.
        & $VenvPython -c "import pip" 2>$null
        $PipMissing = ($LASTEXITCODE -ne 0)
        if ($PipMissing) {
            Write-Host "pip not found in the project venv, bootstrapping with ensurepip..." -ForegroundColor Yellow
            & $VenvPython -m ensurepip --default-pip 2>&1 | ForEach-Object { Write-Host "  $_" }
            if ($LASTEXITCODE -ne 0) { throw "Failed to bootstrap pip in the project venv" }
            Write-Host "pip bootstrapped." -ForegroundColor Green
        }

        # Ensure dev dependencies (pytest, pyinstaller, etc.) are installed.
        & $VenvPython -c "import aqt, cmake, pytest, PyInstaller" 2>$null
        $DevMissing = ($LASTEXITCODE -ne 0)

        if ($DevMissing) {
            $UvExe = Find-UvExecutable
            if (-not $UvExe) {
                Write-Host "uv executable not found; using pip inside the project venv." -ForegroundColor Yellow
            }
        }

        if ($DevMissing) {
            Write-Host "Dev dependencies not found, installing..." -ForegroundColor Yellow
            if ($UvExe) {
                & $UvExe pip install --python $VenvPython -e ".[dev]" 2>&1 | ForEach-Object { Write-Host "  $_" }
            }
            else {
                & $VenvPython -m pip install -e ".[dev]" 2>&1 | ForEach-Object { Write-Host "  $_" }
            }
            if ($LASTEXITCODE -ne 0) { throw "Failed to install dev dependencies" }
            Write-Host "Dev dependencies installed." -ForegroundColor Green
        }

        # Recent setuptools releases can omit pkg_resources, but wexpect still imports it.
        # Ensure it's available at both build time (PyInstaller analysis) and runtime.
        & $VenvPython -c "import pkg_resources" 2>$null
        $PkgResourcesMissing = ($LASTEXITCODE -ne 0)
        if ($PkgResourcesMissing) {
            Write-Host "pkg_resources not found, installing setuptools<70..." -ForegroundColor Yellow
            if (-not $UvExe) { $UvExe = Find-UvExecutable }
            if ($UvExe) {
                & $UvExe pip install --python $VenvPython "setuptools<70" 2>&1 | ForEach-Object { Write-Host "  $_" }
            }
            else {
                & $VenvPython -m pip install "setuptools<70" 2>&1 | ForEach-Object { Write-Host "  $_" }
            }
            if ($LASTEXITCODE -ne 0) { throw "Failed to install setuptools<70" }
            Write-Host "setuptools downgraded (pkg_resources now available)." -ForegroundColor Green
        }
    }
    finally {
        $ErrorActionPreference = $PrevEAP
    }

    & (Join-Path $PSScriptRoot "build-native.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Failed to build the native terminal component" }

    $OneFolderOutput = Join-Path $ProjectRoot "dist\泡泡工具箱"
    $LegacySingleFileOutput = Join-Path $ProjectRoot "dist\泡泡工具箱.exe"
    $LegacyPortableArchive = Join-Path $ProjectRoot "dist\泡泡工具箱-windows-x64.zip"
    $LegacyPortableChecksum = "$LegacyPortableArchive.sha256"
    $InstallerOutput = Join-Path $ProjectRoot "dist\泡泡工具箱-Setup.exe"
    $InstallerChecksum = "$InstallerOutput.sha256"
    Remove-OneFolderOutput $OneFolderOutput
    Remove-SingleFileOutput $LegacySingleFileOutput
    Remove-Item -LiteralPath $LegacyPortableArchive -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $LegacyPortableChecksum -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $InstallerOutput -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $InstallerChecksum -Force -ErrorAction SilentlyContinue

    if (-not $SkipTests) {
        $PytestBaseTemp = Join-Path $TestWorkspace "tmp"
        $PytestCacheDir = Join-Path $TestWorkspace "cache"
        $TestResultsDir = Join-Path $ProjectRoot "build\test-results"
        $JunitReport = Join-Path $TestResultsDir "pytest.xml"
        New-Item -ItemType Directory -Path $TestWorkspace -Force | Out-Null
        New-Item -ItemType Directory -Path $TestResultsDir -Force | Out-Null
        $TestFiles = @(
            Get-ChildItem -LiteralPath (Join-Path $ProjectRoot "tests") -Recurse -File `
                -ErrorAction SilentlyContinue |
                Where-Object {
                    $_.Name -match '^test_.*\.py$' -or $_.Name -match '.*_test\.py$'
                }
        )
        if ($TestFiles.Count -eq 0) {
            Write-Host "No pytest test files found; skipping test stage." -ForegroundColor Yellow
        }
        else {
            & $VenvPython -m pytest "--basetemp=$PytestBaseTemp" -o "cache_dir=$PytestCacheDir" `
                "--junitxml=$JunitReport" --tb=long -ra
            $TestExitCode = $LASTEXITCODE
            if ($TestExitCode -ne 0) {
                throw "Tests failed with exit code $TestExitCode. JUnit report: $JunitReport"
            }
        }
    }

    $PyprojectPath = Join-Path $ProjectRoot "pyproject.toml"
    $PyprojectContent = Get-Content -LiteralPath $PyprojectPath -Raw
    if ($PyprojectContent -notmatch '(?m)^version\s*=\s*"([^"\r\n]+)"\s*$') {
        throw "Could not find the project version in pyproject.toml"
    }
    $BaseVersion = $Matches[1]
    if ($VersionOverride) {
        $BuildVersion = $VersionOverride.Trim().TrimStart("v")
        if ($BuildVersion -notmatch '^(\d{4}-\d{2}-\d{2})_(\d+\.\d+\.\d+)$') {
            throw "VersionOverride must use YYYY-MM-DD_x.x.x, for example 2026-08-17_0.2.0"
        }
        $BuildDate = $Matches[1]
        $EffectiveBaseVersion = $Matches[2]
        if ($EffectiveBaseVersion -ne $BaseVersion) {
            throw "VersionOverride semantic version $EffectiveBaseVersion does not match pyproject.toml version $BaseVersion"
        }
        try {
            [datetime]::ParseExact(
                $BuildDate,
                "yyyy-MM-dd",
                [System.Globalization.CultureInfo]::InvariantCulture
            ) | Out-Null
        }
        catch {
            throw "VersionOverride contains an invalid calendar date: $BuildVersion"
        }
    }
    else {
        $BuildDate = Get-Date -Format "yyyy-MM-dd"
        $BuildVersion = "${BuildDate}_$BaseVersion"
        $EffectiveBaseVersion = $BaseVersion
    }

    # Inno Setup requires VersionInfoVersion to contain four numeric parts.
    # Keep the user-facing build version above, including date and prerelease
    # suffix, for AppVersion and the application runtime.
    $VersionCore = ($EffectiveBaseVersion -split "-", 2)[0]
    $VersionParts = @($VersionCore -split "\.")
    $InvalidVersionPart = $VersionParts | Where-Object { $_ -notmatch '^\d+$' }
    if ($VersionParts.Count -gt 4 -or $InvalidVersionPart) {
        throw "Project version must start with a numeric version such as 0.2.0 or 0.2.0-alpha"
    }
    while ($VersionParts.Count -lt 4) { $VersionParts += "0" }
    $VersionInfoVersion = $VersionParts -join "."
    $VersionFile = Join-Path $ProjectRoot "src\poptools\_build_version.py"
    $VersionContent = "# Auto-generated by build.ps1 — do not commit.`n__build_version__ = '$BuildVersion'"
    [System.IO.File]::WriteAllText(
        $VersionFile,
        $VersionContent,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "Build version: $BuildVersion"

    & $VenvPython -m PyInstaller --noconfirm --clean "packaging\poptools.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed" }

    $BuiltExe = Join-Path $OneFolderOutput "泡泡工具箱.exe"
    if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
        throw "PyInstaller one-folder entry point is missing: $BuiltExe"
    }
    if ($Edition -ne "Clean") {
        $RuntimeOutput = Join-Path $ProjectRoot "build\plugin-seeds"
        New-Item -ItemType Directory -Path $RuntimeOutput -Force | Out-Null
        Expand-VerifiedRuntime `
            -Archive $PythonRuntimePackage `
            -InnerDirectory $PythonRuntimeInnerDirectory `
            -Destination (Join-Path $RuntimeOutput "python")
        Expand-VerifiedRuntime `
            -Archive $ScrcpyRuntimePackage `
            -InnerDirectory $ScrcpyRuntimeInnerDirectory `
            -Destination (Join-Path $RuntimeOutput "scrcpy")
        Copy-Item -LiteralPath $PythonManifestPath `
            -Destination (Join-Path $RuntimeOutput "python\manifest.json")
        Copy-Item -LiteralPath (Join-Path $PythonVendorDir "PYTHON-LICENSE.txt") `
            -Destination (Join-Path $RuntimeOutput "python\LICENSE.txt")
        Copy-Item -LiteralPath $ScrcpyManifestPath `
            -Destination (Join-Path $RuntimeOutput "scrcpy\manifest.json")
        Copy-Item -LiteralPath (Join-Path $ScrcpyVendorDir "scrcpy-LICENSE.txt") `
            -Destination (Join-Path $RuntimeOutput "scrcpy\LICENSE.txt")
        if (-not (Test-Path -LiteralPath (Join-Path $RuntimeOutput "python\python.exe"))) {
            throw "Prepared Python runtime is missing python.exe"
        }
        foreach ($RequiredScrcpyFile in @("adb.exe", "scrcpy.exe", "scrcpy-server", "SDL3.dll")) {
            if (-not (Test-Path -LiteralPath (Join-Path $RuntimeOutput "scrcpy\$RequiredScrcpyFile"))) {
                throw "Prepared scrcpy runtime is missing $RequiredScrcpyFile"
            }
        }
        $PythonSeed = @{version=$PythonManifest.version; url=$PythonManifest.url; digest=$PythonManifest.sha256; algorithm="sha256"; inner="tools"}
        $AndroidSeed = @{version=$ScrcpyManifest.version; url="https://github.com/Genymobile/scrcpy/releases/download/v$($ScrcpyManifest.version)/$($ScrcpyManifest.archive)"; digest=$ScrcpyManifest.sha256; algorithm="sha256"; inner=$ScrcpyRuntimeInnerDirectory}
        [IO.File]::WriteAllText((Join-Path $RuntimeOutput "python-package.json"), ($PythonSeed | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
        [IO.File]::WriteAllText((Join-Path $RuntimeOutput "android-package.json"), ($AndroidSeed | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
    }
    Write-Host (
        "Application core created at dist\泡泡工具箱; optional plugin seeds prepared separately"
    )

    if (-not $SkipInstaller) {
        $InnoCompiler = (Get-Command "ISCC.exe" -ErrorAction SilentlyContinue).Source
        if (-not $InnoCompiler) {
            $InnoCompiler = @(
                (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
                (Join-Path ([Environment]::GetFolderPath("ProgramFilesX86")) "Inno Setup 6\ISCC.exe"),
                (Join-Path ([Environment]::GetFolderPath("ProgramFiles")) "Inno Setup 6\ISCC.exe")
            ) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        }
        if (-not $InnoCompiler) {
            throw "Inno Setup 6 was not found; the required Windows installer cannot be created."
        }
        else {
            $Editions = if ($Edition -eq "Both") { @("Bundled", "Clean") } else { @($Edition) }
            foreach ($BuildEdition in $Editions) {
                $OutputName = if ($BuildEdition -eq "Clean") { "PopTools-Clean-Setup" } else { "PopTools-Setup" }
                $MetadataFile = Join-Path $ProjectRoot "build\edition-$BuildEdition.json"
                [IO.File]::WriteAllText($MetadataFile, (@{edition=$BuildEdition} | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
                & $InnoCompiler "/DEdition=$BuildEdition" "/DOutputName=$OutputName" "/DMyAppVersion=$BuildVersion" "/DMyAppVersionInfoVersion=$VersionInfoVersion" "packaging\poptools.iss"
                if ($LASTEXITCODE -ne 0) { throw "Inno Setup $BuildEdition build failed" }
                $InstallerOutput = Join-Path $ProjectRoot "dist\$OutputName.exe"
                $InstallerChecksum = "$InstallerOutput.sha256"
                $InstallerHash = (Get-FileHash -LiteralPath $InstallerOutput -Algorithm SHA256).Hash.ToLowerInvariant()
                [System.IO.File]::WriteAllText(
                    $InstallerChecksum,
                    "$InstallerHash  $OutputName.exe`n",
                    [System.Text.UTF8Encoding]::new($false)
                )
                Write-Host "Per-user $BuildEdition installer created: $InstallerOutput"
                Write-Host "Installer checksum created: $InstallerChecksum"
            }
            if ($Edition -ne "Clean") {
                # Old clients only recognize PopTools.exe and copy it over their
                # entry point. Ship a bridge, never a renamed Inno installer.
                & $VenvPython -m PyInstaller --noconfirm --clean "packaging\legacy_ota.spec"
                if ($LASTEXITCODE -ne 0) { throw "Legacy OTA bridge build failed" }
                $BridgeOutput = Join-Path $ProjectRoot "dist\PopTools.exe"
                $BridgeHash = (Get-FileHash -LiteralPath $BridgeOutput -Algorithm SHA256).Hash.ToLowerInvariant()
                [IO.File]::WriteAllText("$BridgeOutput.sha256", "$BridgeHash  PopTools.exe`n", [Text.UTF8Encoding]::new($false))
                Write-Host "Legacy OTA bridge created: $BridgeOutput"
            }
        }
    }
}
finally {
    if (Test-Path -LiteralPath $TestWorkspace) {
        Remove-Item -LiteralPath $TestWorkspace -Recurse -Force -ErrorAction SilentlyContinue
    }
    Pop-Location
}
