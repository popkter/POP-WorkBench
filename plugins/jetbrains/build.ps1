param(
    [Parameter(Mandatory=$true)][string]$IdePath,
    [switch]$Test,
    [string]$CompatibilityFixture
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskIde = (Resolve-Path -LiteralPath $IdePath).Path
$taskInfo = Get-Content -LiteralPath "$taskIde/product-info.json" -Raw | ConvertFrom-Json
if ($taskInfo.productCode -ne 'AI' -or $taskInfo.buildNumber -notmatch '^([0-9]+)\.' -or [int]$Matches[1] -lt 261) {
    throw 'Build against Android Studio AI-261 or newer, not another IDE or an older platform.'
}
$taskJdk = Join-Path $taskIde 'jbr/bin'
$taskCp = "$taskIde/lib/*;$taskIde/plugins/terminal/lib/*;$taskIde/plugins/terminal/lib/modules/*;$taskIde/plugins/android/lib/*"
$taskClasses = Join-Path $taskRoot 'build/classes'
$taskLib = Join-Path $taskRoot 'build/package/poptool-scripts/lib'
New-Item -ItemType Directory -Force -Path $taskClasses,$taskLib | Out-Null
$taskSources = @(Get-ChildItem "$taskRoot/src/main/java" -Filter *.java -Recurse | ForEach-Object FullName)
& "$taskJdk/javac.exe" --release 21 -proc:none -encoding UTF-8 -cp $taskCp -d $taskClasses @taskSources
if ($LASTEXITCODE -ne 0) { throw 'Plugin compilation failed.' }
Copy-Item "$taskRoot/src/main/resources/*" $taskClasses -Recurse -Force
Copy-Item "$taskRoot/LICENSE" "$taskClasses/META-INF/LICENSE" -Force
Copy-Item "$taskRoot/THIRD_PARTY_NOTICES.md" "$taskClasses/META-INF/THIRD_PARTY_NOTICES.md" -Force
Copy-Item "$taskRoot/LICENSE" "$taskRoot/build/package/poptool-scripts/LICENSE" -Force
Copy-Item "$taskRoot/THIRD_PARTY_NOTICES.md" "$taskRoot/build/package/poptool-scripts/THIRD_PARTY_NOTICES.md" -Force
& "$taskJdk/jar.exe" --create --file "$taskLib/poptool-scripts.jar" -C $taskClasses .
if ($LASTEXITCODE -ne 0) { throw 'JAR packaging failed.' }
if ($Test) {
    $taskTestClasses = Join-Path $taskRoot 'build/test-classes'
    New-Item -ItemType Directory -Force -Path $taskTestClasses | Out-Null
    $taskTests = @(Get-ChildItem "$taskRoot/src/test/java" -Filter *.java -Recurse | ForEach-Object FullName)
    & "$taskJdk/javac.exe" --release 21 -proc:none -encoding UTF-8 -cp "$taskClasses;$taskCp" -d $taskTestClasses @taskTests
    if ($LASTEXITCODE -ne 0) { throw 'Test compilation failed.' }
    $taskTestArgs=@()
    if($CompatibilityFixture){$taskTestArgs+= (Resolve-Path -LiteralPath $CompatibilityFixture).Path}
    & "$taskJdk/java.exe" -ea -cp "$taskTestClasses;$taskClasses;$taskCp" com.poptools.scripts.CoreTests @taskTestArgs
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
}
$taskZip = Join-Path $taskRoot 'build/nicotools-0.1.0.zip'
Compress-Archive -Path "$taskRoot/build/package/poptool-scripts" -DestinationPath $taskZip -Force
Write-Output "Built $taskZip against AI-$($taskInfo.buildNumber)"
