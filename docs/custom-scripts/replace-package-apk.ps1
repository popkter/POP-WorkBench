# PopTool 自定义工具：按包名替换 APK；脚本类型选择 PowerShell。
# 参数通过 PopTool 替换，请将完整内容粘贴到脚本编辑器。
# 参数只接受单行文本；不要粘贴包含换行的内容。
$packageName = @'
${目标包名:com.zeekr.speech.daemon}
'@
$replacementPath = @'
${替换APK文件@file:C:/Users/Guangyou.Yu/Documents/Code/ZeekrSpeechService_lfs/app/build/outputs/apk/release/ZeekrSpeechService_super_eva20_fa_signed.apk}
'@

$ErrorActionPreference = 'Stop'
$adbPath = $null
$deviceArgs = @()

function Invoke-Adb {
    param([string[]]$AdbArgs)
    $output = @(& $adbPath @deviceArgs @AdbArgs 2>&1)
    $code = $LASTEXITCODE
    $message = ($output | ForEach-Object { $_.ToString() }) -join "`n"
    if ($code -ne 0) {
        $commandText = (@($deviceArgs) + @($AdbArgs)) -join ' '
        if ([string]::IsNullOrWhiteSpace($message)) {
            $message = '设备未返回错误文字。'
        }
        throw "adb 失败（退出码 $code）`n命令：adb $commandText`n$message"
    }
    return $message.Trim()
}

try {
    $packageName = $packageName.Trim()
    if ($packageName -notmatch '^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)+$') {
        throw '目标包名无效，例如：com.example.app。'
    }
    $file = Get-Item -LiteralPath $replacementPath -ErrorAction Stop
    if ($file.PSIsContainer -or $file.Extension -ine '.apk' -or $file.Length -eq 0) {
        throw '请选择存在且非空的 APK 文件。'
    }
    $replacementPath = $file.FullName
    $localHash = (Get-FileHash -LiteralPath $replacementPath -Algorithm SHA256).Hash.ToLowerInvariant()
    # PopTool 会传入插件 ADB 路径；未提供时只取 PATH 中的第一个结果。
    if (-not [string]::IsNullOrWhiteSpace($env:POPTOOLS_ADB)) {
        $adbPath = $env:POPTOOLS_ADB
        if (-not (Test-Path -LiteralPath $adbPath -PathType Leaf)) {
            throw "PopTool 提供的 ADB 文件不存在：$adbPath"
        }
    }
    else {
        $adbPath = (Get-Command adb -CommandType Application -ErrorAction Stop |
            Select-Object -First 1).Source
    }
    Write-Host "使用 ADB：$adbPath"
    $devices = Invoke-Adb -AdbArgs @('devices')
    $entries = @($devices -split '\r?\n' | Where-Object {
        $_ -match '^\S+\s+(device|offline|unauthorized|recovery|sideload|bootloader)\b'
    })
    if (-not [string]::IsNullOrWhiteSpace($env:ANDROID_SERIAL)) {
        $selectedSerial = $env:ANDROID_SERIAL.Trim()
        $selectedPattern = '^' + [regex]::Escape($selectedSerial) + '\s+device\s*$'
        if (@($entries | Where-Object { $_ -match $selectedPattern }).Count -ne 1) {
            throw "PopTool 选定的设备未在线或未授权：$selectedSerial`n$devices"
        }
    }
    else {
        if ($entries.Count -ne 1 -or $entries[0] -notmatch '^(\S+)\s+device\s*$') {
            throw "请在 PopTool 中选择目标设备，或只连接一台已授权且正常在线的设备。`n$devices"
        }
        $selectedSerial = $Matches[1]
    }
    $deviceArgs = @('-s', $selectedSerial)
    Write-Host "目标设备：$selectedSerial"
    # 车机可能使用用户 10 等非零用户；pm path 默认查询用户 0。
    $androidUser = Invoke-Adb -AdbArgs @('shell', 'am', 'get-current-user')
    if ($androidUser -notmatch '^\d+$') {
        throw "无法确定当前 Android 用户：$androidUser"
    }
    Write-Host "Android 用户：$androidUser；目标包名：$packageName"
    $pathOutput = Invoke-Adb -AdbArgs @('shell', 'pm', 'path', '--user', $androidUser, $packageName)
    $apkPaths = @($pathOutput -split '\r?\n' | Where-Object {
        $_.StartsWith('package:')
    } | ForEach-Object { $_.Substring(8).Trim() })
    if ($apkPaths.Count -eq 0) { throw "未找到包：$packageName。$pathOutput" }
    if ($apkPaths.Count -ne 1) { throw '目标包含多个 APK（split APK），此脚本仅支持单 APK 替换。' }
    $targetPath = $apkPaths[0]
    if ($targetPath -notmatch '^/[A-Za-z0-9_./+=@~-]+\.apk$' -or $targetPath -match '/\.\.?/') {
        throw "目标路径包含不支持的字符：$targetPath"
    }
    Write-Host "设备上的目标：$targetPath"
    Write-Host "本地替换文件：$replacementPath"

    # 使用设备现有写权限，直接覆盖目标 APK。
    $null = Invoke-Adb -AdbArgs @('shell', "test -w '$targetPath'")
    $null = Invoke-Adb -AdbArgs @('shell', 'am', 'force-stop', '--user', $androidUser, $packageName)

    # 第二个参数是完整目标文件路径，因此包 B 自动使用包 A 的文件名。
    Write-Host (Invoke-Adb -AdbArgs @('push', $replacementPath, $targetPath))
    $null = Invoke-Adb -AdbArgs @('shell', "chmod 0644 '$targetPath' && restorecon '$targetPath'")
    $remoteHash = Invoke-Adb -AdbArgs @('shell', "sha256sum '$targetPath'")
    if (($remoteHash -split '\s+')[0].ToLowerInvariant() -ne $localHash) {
        throw '覆盖后的 APK 与本地文件 SHA256 不一致。'
    }
    $null = Invoke-Adb -AdbArgs @('shell', 'sync')
    Write-Host "替换完成，文件名和路径保持为：$targetPath"
    Write-Host '请手动重启设备，使系统重新扫描 APK。'
    exit 0
}
catch {
    Write-Host "替换失败：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
