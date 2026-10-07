param([Parameter(Mandatory=$true)][string]$IdePath)
$ErrorActionPreference='Stop'
& "$PSScriptRoot/build.ps1" -IdePath $IdePath -Test
$taskIde=(Resolve-Path -LiteralPath $IdePath).Path
$taskSmoke=Join-Path $PSScriptRoot ('build/smoke-'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
$taskPlugin=Join-Path $taskSmoke 'plugins/poptool-scripts/lib'
$taskClasses=Join-Path $taskSmoke 'classes'
$taskProject=Join-Path $taskSmoke 'project'
New-Item -ItemType Directory -Force -Path $taskPlugin,$taskClasses,$taskProject | Out-Null
New-Item -ItemType Directory -Force -Path "$taskSmoke/config" | Out-Null
# Disable unrelated AI indexing/downloads only in the isolated test instance.
[IO.File]::WriteAllText("$taskSmoke/config/disabled_plugins.txt",'com.google.tools.ij.aiplugin')
Copy-Item "$PSScriptRoot/build/classes/*" $taskClasses -Recurse -Force
Copy-Item "$PSScriptRoot/build/test-classes/com/poptools/scripts/IntegrationSmoke*.class" "$taskClasses/com/poptools/scripts" -Force
$taskDescriptor=Join-Path $taskClasses 'META-INF/plugin.xml'
$taskXml=Get-Content -LiteralPath $taskDescriptor -Raw
$taskXml=$taskXml.Replace('</extensions>','<postStartupActivity implementation="com.poptools.scripts.IntegrationSmoke"/></extensions>')
[IO.File]::WriteAllText($taskDescriptor,$taskXml,[Text.UTF8Encoding]::new($false))
& "$taskIde/jbr/bin/jar.exe" --create --file "$taskPlugin/poptool-scripts.jar" -C $taskClasses .
if($LASTEXITCODE -ne 0){throw 'Smoke JAR packaging failed.'}
$taskOptions=Join-Path $taskSmoke 'studio.vmoptions'
$taskReport=Join-Path $taskSmoke 'report.txt'
$taskJvm=@(Get-Content "$taskIde/bin/studio64.exe.vmoptions") + @(
    "-Didea.config.path=$taskSmoke/config",
    "-Didea.system.path=$taskSmoke/system",
    "-Didea.plugins.path=$taskSmoke/plugins",
    "-Didea.log.path=$taskSmoke/log",
    "-Dpoptool.smoke.report=$taskReport",
    "-Dpoptool.smoke.python=$((Get-Command python -ErrorAction Stop).Source)",
    '-Dpoptool.smoke.bash=C:/Program Files/Git/bin/bash.exe',
    '-Didea.initially.ask.config=false',
    '-Ddisable.android.first.run=true',
    '-Djb.consents.confirmation.enabled=false',
    '-Djb.privacy.policy.text=<!--999.999-->',
    '-Didea.trust.all.projects=true',
    '-Dide.show.tips.on.startup.default.value=false'
)
[IO.File]::WriteAllLines($taskOptions,$taskJvm,[Text.UTF8Encoding]::new($false))
[IO.File]::WriteAllText((Join-Path $taskProject 'README.txt'),'Isolated PopTool plugin integration smoke project.')
$taskPrevious=$env:STUDIO_VM_OPTIONS
try {
    $env:STUDIO_VM_OPTIONS=$taskOptions
    $taskProcess=Start-Process -FilePath "$taskIde/bin/studio64.exe" -ArgumentList ('"'+$taskProject+'"') -WindowStyle Hidden -PassThru
    Write-Output "Smoke process: $($taskProcess.Id)"
    Write-Output "Smoke directory: $taskSmoke"
    Write-Output "Report: $taskReport"
} finally {
    $env:STUDIO_VM_OPTIONS=$taskPrevious
}
