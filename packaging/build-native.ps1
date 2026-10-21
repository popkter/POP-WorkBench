param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BuildDirectory = Join-Path $ProjectRoot "build\native-windows-msvc2022"
$InstallDirectory = Join-Path $ProjectRoot "src\poptools\native"
$StagingInstallDirectory = Join-Path $BuildDirectory "install\$Configuration"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ManagedQtRoot = Join-Path $ProjectRoot "build\qt-sdk"

function Install-NativeLibrary {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    try {
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
        return
    }
    catch {
        $CopyError = $_
    }

    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) {
        throw $CopyError
    }

    # Windows does not allow an in-use DLL to be overwritten, but it does allow
    # the loaded file to be renamed. Keep that mapped image alive for the current
    # process and put the new build at the canonical path for the next launch.
    $Backup = "$Destination.previous"
    if (Test-Path -LiteralPath $Backup) {
        try {
            Remove-Item -LiteralPath $Backup -Force
        }
        catch {
            $Backup = "$Destination.previous.$([guid]::NewGuid().ToString('N'))"
        }
    }

    try {
        Move-Item -LiteralPath $Destination -Destination $Backup
    }
    catch {
        throw (
            "Native terminal deployment failed because the existing DLL could not be " +
            "replaced or renamed: $Destination. Close processes using the project DLL " +
            "and retry. Original error: $($_.Exception.Message)"
        )
    }

    try {
        Copy-Item -LiteralPath $Source -Destination $Destination
    }
    catch {
        $DeployError = $_
        if (-not (Test-Path -LiteralPath $Destination)) {
            try {
                Move-Item -LiteralPath $Backup -Destination $Destination
            }
            catch {
                Write-Warning "Could not restore the previous native terminal DLL from $Backup"
            }
        }
        throw $DeployError
    }

    Write-Host "Replaced the in-use native terminal DLL; old image retained at $Backup" `
        -ForegroundColor Yellow
}

# MSBuild adds a mixed-case `Path` entry internally. Some shells (including
# automation hosts) expose the inherited variable as `PATH`, which causes
# MSBuild's case-insensitive environment dictionary to reject the duplicate.
$ProcessPath = [Environment]::GetEnvironmentVariable(
    "PATH",
    [EnvironmentVariableTarget]::Process
)
if ($ProcessPath) {
    Remove-Item Env:PATH -ErrorAction SilentlyContinue
    $env:Path = $ProcessPath
}

function Test-QtPrefix {
    param([string]$Prefix)

    if (-not $Prefix) { return $false }
    $QtConfig = Join-Path $Prefix "lib\cmake\Qt6\Qt6Config.cmake"
    return Test-Path -LiteralPath $QtConfig -PathType Leaf
}

function Find-AqtExecutable {
    $AqtCommand = Get-Command aqt -ErrorAction SilentlyContinue
    if ($AqtCommand) { return $AqtCommand.Source }

    $VenvAqt = Join-Path $ProjectRoot ".venv\Scripts\aqt.exe"
    if (Test-Path -LiteralPath $VenvAqt -PathType Leaf) { return $VenvAqt }
    return ""
}

$CMakeCommand = Get-Command cmake -ErrorAction SilentlyContinue
$CMake = if ($CMakeCommand) { $CMakeCommand.Source } else {
    Join-Path $ProjectRoot ".venv\Scripts\cmake.exe"
}
if (-not (Test-Path -LiteralPath $CMake -PathType Leaf)) {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw (
            "CMake was not found and the project venv is unavailable: $VenvPython. " +
            "Run 'uv sync --extra dev' first."
        )
    }

    Write-Host "CMake was not found. Installing it into the project venv..." -ForegroundColor Yellow
    # uv virtual environments do not necessarily include pip.
    & $VenvPython -m ensurepip --default-pip
    if ($LASTEXITCODE -ne 0) { throw "Failed to bootstrap pip for the CMake installation" }
    & $VenvPython -m pip install "cmake>=3.21,<4"
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to install CMake. Check network access and run 'uv sync --extra dev' again."
    }
    if (-not (Test-Path -LiteralPath $CMake -PathType Leaf)) {
        throw "CMake installation did not produce the expected executable: $CMake"
    }
}

$QtPrefix = ""
if (Test-QtPrefix $env:QT_ROOT_DIR) {
    $QtPrefix = (Resolve-Path -LiteralPath $env:QT_ROOT_DIR).Path
}
if (-not $QtPrefix -and $env:Qt6_DIR) {
    # install-qt-action@v4 sets Qt6_DIR=<prefix>/lib/cmake/Qt6
    $Candidate = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $env:Qt6_DIR))
    if (Test-QtPrefix $Candidate) {
        $QtPrefix = (Resolve-Path -LiteralPath $Candidate).Path
        Write-Host "Qt prefix resolved from Qt6_DIR: $QtPrefix"
    }
}
if (-not $QtPrefix) {
    $QMake = (Get-Command qmake6 -ErrorAction SilentlyContinue).Source
    if (-not $QMake) { $QMake = (Get-Command qmake -ErrorAction SilentlyContinue).Source }
    if ($QMake) {
        $Candidate = (& $QMake -query QT_INSTALL_PREFIX).Trim()
        if (Test-QtPrefix $Candidate) { $QtPrefix = $Candidate }
    }
}
if (-not $QtPrefix) {
    if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
        throw "Qt 6 C++ SDK was not found and the project venv is unavailable: $VenvPython"
    }

    $PySideQtVersion = (& $VenvPython -c "from PySide6.QtCore import qVersion; print(qVersion())").Trim()
    if ($LASTEXITCODE -ne 0 -or $PySideQtVersion -notmatch '^6\.\d+\.\d+$') {
        throw "Could not determine the Qt version used by PySide6."
    }

    # Keep local native builds aligned with the SDK used by GitHub Actions.
    # PySide wheels can be published before the matching standalone Qt SDK is
    # available, so its runtime version is not always downloadable by aqt.
    $QtVersion = if ($env:POPTOOLS_QT_SDK_VERSION) {
        $env:POPTOOLS_QT_SDK_VERSION.Trim()
    }
    else {
        "6.10.3"
    }
    if ($QtVersion -notmatch '^6\.\d+\.\d+$') {
        throw "POPTOOLS_QT_SDK_VERSION must use a full Qt 6 version such as 6.10.3."
    }

    $QtArch = "win64_msvc2022_64"
    $ManagedQtPrefix = Join-Path $ManagedQtRoot "$QtVersion\msvc2022_64"
    if (Test-QtPrefix $ManagedQtPrefix) {
        $QtPrefix = $ManagedQtPrefix
        Write-Host "Using cached Qt $QtVersion SDK (PySide6 runtime: $PySideQtVersion)."
    }
    else {
        $Aqt = Find-AqtExecutable
        if (-not $Aqt) {
            throw (
                "Qt 6 C++ SDK was not found and aqtinstall is unavailable. " +
                "Run 'uv sync --extra dev', set QT_ROOT_DIR/Qt6_DIR, or add qmake to PATH."
            )
        }

        Write-Host (
            "Qt 6 C++ SDK was not found. Downloading Qt $QtVersion ($QtArch) " +
            "to $ManagedQtRoot ..."
        ) -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $ManagedQtRoot -Force | Out-Null
        & $Aqt install-qt windows desktop $QtVersion $QtArch --outputdir $ManagedQtRoot
        if ($LASTEXITCODE -ne 0) { throw "Failed to download Qt $QtVersion C++ SDK" }
        if (-not (Test-QtPrefix $ManagedQtPrefix)) {
            throw "Qt SDK download completed but Qt6Config.cmake was not found under $ManagedQtPrefix"
        }
        $QtPrefix = $ManagedQtPrefix
    }
}

Write-Host "Using Qt prefix: $QtPrefix"
Write-Host "CMake: $CMake"

New-Item -ItemType Directory -Path $BuildDirectory -Force | Out-Null
New-Item -ItemType Directory -Path $InstallDirectory -Force | Out-Null

& $CMake -S (Join-Path $ProjectRoot "native") -B $BuildDirectory `
    "-DCMAKE_BUILD_TYPE=$Configuration" `
    "-DCMAKE_PREFIX_PATH=$QtPrefix"
if ($LASTEXITCODE -ne 0) { throw "Native terminal configure failed" }

# Keep the outer build serialized on Windows. The native project is small, and
# this avoids nested MSBuild/CMake process bursts on restricted build hosts.
& $CMake --build $BuildDirectory --config $Configuration --parallel 1
if ($LASTEXITCODE -ne 0) { throw "Native terminal build failed" }

$CTest = Join-Path (Split-Path -Parent $CMake) "ctest.exe"
if (-not (Test-Path -LiteralPath $CTest -PathType Leaf)) {
    $CTestCommand = Get-Command ctest -ErrorAction SilentlyContinue
    $CTest = if ($CTestCommand) { $CTestCommand.Source } else { "" }
}
if (-not $CTest) { throw "CTest was not found beside CMake" }
& $CTest --test-dir $BuildDirectory --build-config $Configuration --output-on-failure
if ($LASTEXITCODE -ne 0) { throw "Native terminal tests failed" }

if (Test-Path -LiteralPath $StagingInstallDirectory) {
    Remove-Item -LiteralPath $StagingInstallDirectory -Recurse -Force
}
New-Item -ItemType Directory -Path $StagingInstallDirectory -Force | Out-Null

& $CMake --install $BuildDirectory --config $Configuration --prefix $StagingInstallDirectory
if ($LASTEXITCODE -ne 0) { throw "Native terminal install failed" }

$StagedLibrary = Join-Path $StagingInstallDirectory "poptools_terminal.dll"
if (-not (Test-Path -LiteralPath $StagedLibrary -PathType Leaf)) {
    throw "Native terminal install did not produce the expected library: $StagedLibrary"
}
$InstalledLibrary = Join-Path $InstallDirectory "poptools_terminal.dll"
Install-NativeLibrary -Source $StagedLibrary -Destination $InstalledLibrary

Write-Host "Native terminal installed at $InstalledLibrary"
