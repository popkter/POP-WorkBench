$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
& "$env:SystemRoot\System32\chcp.com" 65001 > $null

function global:python {
    if (-not $env:POPTOOLS_PYTHON) { Write-Error '请在设置的插件管理中安装 Python。'; return }
    & $env:POPTOOLS_PYTHON @args
}

function global:pip {
    if (-not $env:POPTOOLS_PIP) { Write-Error '请在设置的插件管理中安装 Python。'; return }
    & $env:POPTOOLS_PIP -m pip @args
}

function global:adb {
    if (-not $env:POPTOOLS_ADB -or -not (Test-Path -LiteralPath $env:POPTOOLS_ADB)) {
        Write-Error '请在设置的插件管理中安装 Android 工具（ADB + scrcpy）。'; return
    }
    & $env:POPTOOLS_ADB @args
}

Import-Module PSReadLine

function ConvertTo-PopToolsAnsiColor {
    param([string]$Color)

    if ($Color -notmatch '^#(?<Red>[0-9A-Fa-f]{2})(?<Green>[0-9A-Fa-f]{2})(?<Blue>[0-9A-Fa-f]{2})$') {
        return $null
    }

    $red = [Convert]::ToInt32($Matches.Red, 16)
    $green = [Convert]::ToInt32($Matches.Green, 16)
    $blue = [Convert]::ToInt32($Matches.Blue, 16)
    return "$([char]27)[38;2;$red;$green;$blue`m"
}

$popToolsColorSources = @{
    Default          = 'POPTOOLS_PS_COLOR_DEFAULT'
    Command          = 'POPTOOLS_PS_COLOR_COMMAND'
    Parameter        = 'POPTOOLS_PS_COLOR_WARNING'
    Keyword          = 'POPTOOLS_PS_COLOR_WARNING'
    String           = 'POPTOOLS_PS_COLOR_STRING'
    Variable         = 'POPTOOLS_PS_COLOR_SEMANTIC'
    Type             = 'POPTOOLS_PS_COLOR_SEMANTIC'
    Member           = 'POPTOOLS_PS_COLOR_SEMANTIC'
    Operator         = 'POPTOOLS_PS_COLOR_OPERATOR'
    Number           = 'POPTOOLS_PS_COLOR_OPERATOR'
    Error            = 'POPTOOLS_PS_COLOR_ERROR'
    Comment          = 'POPTOOLS_PS_COLOR_MUTED'
    InlinePrediction = 'POPTOOLS_PS_COLOR_MUTED'
}
$popToolsColors = @{}
foreach ($entry in $popToolsColorSources.GetEnumerator()) {
    $ansiColor = ConvertTo-PopToolsAnsiColor ([Environment]::GetEnvironmentVariable($entry.Value))
    if ($null -ne $ansiColor) {
        $popToolsColors[$entry.Key] = $ansiColor
    }
}
if ($popToolsColors.Count -gt 0) {
    Set-PSReadLineOption -Colors $popToolsColors
}
# New and restarted sessions apply the saved preference during initialization,
# before PSReadLine begins accepting input.
if ($env:POPTOOLS_PS_HISTORY_LIST_VIEW -eq '1') {
    Set-PSReadLineOption -PredictionSource History
    Set-PSReadLineOption -PredictionViewStyle ListView
} else {
    Set-PSReadLineOption -PredictionSource None
}

# PopTools sends these otherwise-unused key chords to change prediction mode
# without typing commands into the editable line or adding them to history.
Set-PSReadLineKeyHandler -Chord Ctrl+F11 -ScriptBlock {
    Set-PSReadLineOption -PredictionSource History
    Set-PSReadLineOption -PredictionViewStyle ListView
    [Microsoft.PowerShell.PSConsoleReadLine]::InvokePrompt()
}
Set-PSReadLineKeyHandler -Chord Ctrl+F12 -ScriptBlock {
    Set-PSReadLineOption -PredictionSource None
    [Microsoft.PowerShell.PSConsoleReadLine]::InvokePrompt()
}
