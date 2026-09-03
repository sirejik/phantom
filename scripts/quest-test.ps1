param(
    [string]$Results="results/quest/unity-test-results.xml",
    [string]$Filter="Phantom.Tests"
)
$ErrorActionPreference="Stop"
$unity="C:\Program Files\Unity\Hub\Editor\6000.3.22f1\Editor\Unity.exe"
$arguments=@(
    "-batchmode","-nographics",
    "-projectPath",[System.IO.Path]::GetFullPath("PhantomQuest"),
    "-runTests","-testPlatform","EditMode",
    "-testFilter",$Filter,
    "-testResults",[System.IO.Path]::GetFullPath($Results),
    "-logFile",[System.IO.Path]::GetFullPath("results/quest/unity-tests.log")
)
$process=Start-Process -FilePath $unity -ArgumentList $arguments -WindowStyle Hidden -PassThru
$process.WaitForExit()
if($process.ExitCode -ne 0){throw "Unity tests failed with exit code $($process.ExitCode); see results/quest/unity-tests.log"}
[xml]$testResults=Get-Content -Raw $Results
$run=$testResults.'test-run'
Write-Output "Unity EditMode: $($run.passed)/$($run.total) passed, $($run.failed) failed"
