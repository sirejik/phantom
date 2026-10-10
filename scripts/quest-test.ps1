param(
    [string]$Results="results/quest/unity-test-results.xml",
    [string]$Filter="Phantom.Tests",
    [ValidateSet("All","Host","Unity")][string]$Suite="All",
    [ValidateSet("All","Unit","Functional")][string]$Category="All",
    [ValidateRange(1,600)][int]$TimeoutSeconds=600
)
$ErrorActionPreference="Stop"
. "$PSScriptRoot/../tools/toolchain.ps1"
. "$PSScriptRoot/pair-state.ps1"
if($Suite -ne 'Unity')
{
    $dotnet=Get-PhantomDotnetExe
    $project=[IO.Path]::GetFullPath('PhantomQuest/Tests/Host/Phantom.HostTests.csproj')
    $env:PHANTOM_REPO_ROOT=Get-PhantomRepositoryRoot
    $categories=if($Category -eq 'All'){@('Unit','Functional')}else{@($Category)}
    $previous=Get-Location
    try {
        Set-Location (Split-Path -Parent $project)
        foreach($selection in $categories){
            $run=Invoke-PhantomProcess $dotnet @('test',$project,'--configuration','Debug','-p:RestoreLockedMode=true','--filter',"TestCategory=$selection",'--logger',"trx;LogFileName=host-$selection.trx",'--results-directory',"$env:PHANTOM_REPO_ROOT/results/quest") $TimeoutSeconds 'QUEST_HOST_TEST_TIMEOUT'
            $run.Output|Write-Output
            if($run.ExitCode-ne 0){throw "Quest host tests failed: $selection"}
        }
    } finally {Set-Location $previous}
}
if($Suite -eq 'Host'){return}
$unity=Get-PhantomUnityExe
$resultPath=[System.IO.Path]::GetFullPath($Results)
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $resultPath),"results/quest" | Out-Null
if(Test-Path -LiteralPath $resultPath){Remove-Item -LiteralPath $resultPath -Force}
$arguments=@(
    "-batchmode","-nographics",
    "-buildTarget","Android",
    "-projectPath",[System.IO.Path]::GetFullPath("PhantomQuest"),
    "-runTests","-testPlatform","EditMode",
    "-testFilter",$Filter,
    "-testResults",$resultPath,
    "-logFile",[System.IO.Path]::GetFullPath("results/quest/unity-tests.log")
)
$process=Invoke-PhantomProcess $unity $arguments $TimeoutSeconds 'UNITY_TEST_TIMEOUT'
if($process.ExitCode -ne 0){throw "Unity tests failed with exit code $($process.ExitCode); see results/quest/unity-tests.log"}
if(!(Test-Path -LiteralPath $resultPath -PathType Leaf)){throw 'Unity did not produce a test report'}
[xml]$testResults=Get-Content -LiteralPath $resultPath -Raw
$run=$testResults.'test-run'
if(!$run -or $run.total -notmatch '^\d+$' -or [int]$run.total -le 0 -or
   $run.result -ne 'Passed' -or $run.failed -ne '0' -or
   $run.passed -notmatch '^\d+$' -or [int]$run.passed -le 0)
{throw 'Unity test report is empty, unsuccessful or malformed'}
Write-Output "Unity EditMode: $($run.passed)/$($run.total) passed, $($run.failed) failed"
