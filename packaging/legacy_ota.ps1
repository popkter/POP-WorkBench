# Run from an independent directory after the legacy updater replaces the app.
$ErrorActionPreference = 'Stop'
$staging = $PSScriptRoot
$log = Join-Path $staging 'migration.log'
$setup = Join-Path $staging 'PopTools-Setup.exe'
try {
    $config = Get-Content -LiteralPath (Join-Path $staging 'update.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    $target = [IO.Path]::GetFullPath([string]$config.target)
    $directory = Split-Path -Parent $target
    $application = Join-Path $directory '泡泡工具箱.exe'
    $deadline = [DateTime]::UtcNow.AddSeconds([double]$config.timeout_seconds)
    # Both the Python child and the one-file bootloader can hold the target.
    # An exclusive writable handle also detects other outstanding file users.
    while ($true) {
        $bridge = Get-Process -Id $config.process_id -ErrorAction SilentlyContinue
        $running = @(Get-Process | Where-Object {
            try { $_.Path -and [string]::Equals($_.Path, $target, [StringComparison]::OrdinalIgnoreCase) }
            catch { $false }
        })
        $unlocked = $false
        if (-not $bridge -and $running.Count -eq 0) {
            try {
                $handle = [IO.File]::Open($target, [IO.FileMode]::Open, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
                $handle.Dispose()
                $unlocked = $true
            } catch [IO.IOException] {}
        }
        if ($unlocked) { break }
        if ([DateTime]::UtcNow -ge $deadline) { throw '等待旧程序退出或解除文件占用超时，请关闭程序后重试。' }
        Start-Sleep -Milliseconds 250
    }
    'Starting legacy OTA installation' | Out-File -LiteralPath $log -Encoding utf8
    $arguments = @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART',
        ('/DIR="' + $directory + '"'), ('/LOG="' + (Join-Path $staging 'setup.log') + '"'))
    $installer = Start-Process -FilePath $setup -ArgumentList $arguments -WindowStyle Hidden -Wait -PassThru
    if ($installer.ExitCode -ne 0) { throw "安装失败，退出码：$($installer.ExitCode)" }
    if (-not (Test-Path -LiteralPath $application -PathType Leaf)) { throw '安装后未找到应用入口。' }
    $env:PYINSTALLER_RESET_ENVIRONMENT = '1'
    Start-Process -FilePath $application -WorkingDirectory $directory
} catch {
    $message = "升级失败：$($_.Exception.Message)`r`n更新文件和日志：$staging`r`n可运行此目录中的 apply.ps1 重试。"
    $message | Out-File -LiteralPath $log -Encoding utf8 -Append
    if ($env:POPTOOLS_OTA_TEST_NO_DIALOG -ne '1') {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($message, '泡泡工具箱更新失败') | Out-Null
    }
    exit 1
}
# Delete only this run's files; never recursively remove a computed directory.
foreach ($name in @('PopTools-Setup.exe', 'update.json', 'setup.log', 'migration.log', 'apply.ps1')) {
    Remove-Item -LiteralPath (Join-Path $staging $name) -Force -ErrorAction SilentlyContinue
}
# helper.log remains available for diagnostics; its redirected handle stays open
# until PowerShell exits. No recursive deletion of the staging directory.
