$ErrorActionPreference='Stop'
$repository=Split-Path -Parent $PSScriptRoot
. "$repository/scripts/pair-state.ps1"
. "$repository/scripts/ev3-deploy-common.ps1"
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('phantom-pair-test-'+[Guid]::NewGuid().ToString('N'))
$failures=New-Object 'System.Collections.Generic.List[string]'
$savedEnvironment=@{}
foreach($name in @('PATH','PHANTOM_ADB','PHANTOM_TEST_PULL_RECORD','PHANTOM_TEST_PULL_EXIT','PHANTOM_TEST_ANALYZER_RECORD','PHANTOM_TEST_ANALYZER_EXIT','PHANTOM_TEST_LAUNCH_STATE','PHANTOM_TEST_LAUNCH_MODE','PHANTOM_TEST_BUILD_ID'))
{$savedEnvironment[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
function Assert-True([bool]$Condition,[string]$Message){if(!$Condition){$failures.Add($Message)}}
function Assert-Throws([scriptblock]$Action,[string]$Code)
{
    try{& $Action; $failures.Add("expected $Code")}
    catch{Assert-True ($_.Exception.Message.StartsWith($Code+':')) "expected $Code, got $($_.Exception.Message)"}
}
try
{
    $paths=Get-PhantomPairPaths $temporary
    Assert-Throws {Read-PhantomPairState $temporary} 'PROVISION_REQUIRED'
    New-Item -ItemType Directory -Force -Path $paths.SshDirectory,$paths.SecretDirectory|Out-Null

    $generatedKey=Join-Path $temporary 'generated/id_ed25519'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $generatedKey)|Out-Null
    New-PhantomDeploymentKey $generatedKey
    Assert-True ((Test-Path -LiteralPath $generatedKey -PathType Leaf)-and(Test-Path -LiteralPath ($generatedKey+'.pub') -PathType Leaf)) 'empty-passphrase deployment key generation failed'

    foreach($file in @($paths.SshKey,$paths.SshConfig,$paths.KnownHosts,$paths.ControlSecret)){[IO.File]::WriteAllText($file,'test')}
    $record=[ordered]@{provision_schema_version=1;provision_status='complete';quest_adb_serial='QUEST-EXACT-001';ev3_hostname='ev3dev.local';ev3_host_key_fingerprint='SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';robot_id='phantom01';control_key_id='phantom01-control'}
    Write-PhantomPairState $record $temporary
    $loaded=Read-PhantomPairState $temporary -RequirePrivateFiles
    Assert-True ($loaded.State.quest_adb_serial-eq'QUEST-EXACT-001') 'pair record round trip failed'

    $fake=Join-Path $temporary 'adb.cmd'
    [IO.File]::WriteAllText($fake,"@echo off`r`necho List of devices attached`r`necho %PHANTOM_TEST_ADB_LINE%`r`n",[Text.Encoding]::ASCII)
    $env:PHANTOM_TEST_ADB_LINE="QUEST-EXACT-001`tdevice"
    Assert-True ((Get-PhantomQuestDevice $fake $temporary)-eq'QUEST-EXACT-001') 'exact designated Quest was not selected'
    $env:PHANTOM_TEST_ADB_LINE="OTHER-DEVICE`tdevice"
    Assert-Throws {Get-PhantomQuestDevice $fake $temporary} 'QUEST_IDENTITY_MISMATCH'
    $env:PHANTOM_TEST_ADB_LINE=''
    Assert-Throws {Get-PhantomQuestDevice $fake $temporary} 'QUEST_NOT_FOUND'

    $run=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/provision-fixed-pair.ps1" -StateRoot $temporary -Destination (Join-Path $temporary 'result') 2>&1
    Assert-True ($LASTEXITCODE-eq 0) "idempotent PROVISION failed: $($run-join' ')"
    Assert-True (($run-join' ') -match'ALREADY_PROVISIONED') 'idempotent PROVISION did not report ALREADY_PROVISIONED'
    $savedPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
    try{$rotation=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/provision-fixed-pair.ps1" -StateRoot $temporary -Destination (Join-Path $temporary 'result') -RotateControlSecret 2>&1;$rotationExit=$LASTEXITCODE}
    finally{$ErrorActionPreference=$savedPreference}
    Assert-True ($rotationExit-ne 0) 'credential rotation without explicit repair was accepted'
    Assert-True (($rotation-join' ') -match'rotation/repin requires explicit -Repair') 'rotation admission did not fail with the canonical repair requirement'

    $fakeSsh=Join-Path $temporary 'fake-ssh.cmd'
    [IO.File]::WriteAllText($fakeSsh,"@echo off`r`necho REPORT_CHANNEL`r`necho DIAGNOSTIC_CHANNEL 1>&2`r`nexit /b 7`r`n",[Text.Encoding]::ASCII)
    $transport=Invoke-PhantomNative $fakeSsh @() 3 'DEVICE_NOT_FOUND'
    Assert-True ($transport.ExitCode-eq 7) 'mocked SSH exit code was not preserved'
    Assert-True (($transport.Stdout.Count-eq 1)-and($transport.Stdout[0]-eq'REPORT_CHANNEL')) 'mocked SSH stdout was not isolated'
    Assert-True (($transport.Stderr.Count-eq 1)-and($transport.Stderr[0].Trim()-eq'DIAGNOSTIC_CHANNEL')) 'mocked SSH stderr was not isolated'

    # Exercise the actual provisioning command against a failing temporary bootstrap.
    $parseTokens=$null;$parseErrors=$null
    $provisionAst=[Management.Automation.Language.Parser]::ParseFile("$repository/scripts/ev3-provision-maintenance.ps1",[ref]$parseTokens,[ref]$parseErrors)
    $commandAst=$provisionAst.Find({param($node) $node -is [Management.Automation.Language.ExpandableStringExpressionAst] -and $node.Value.Contains('provision_status=')},$true)
    Assert-True ($null-ne$commandAst) 'provisioning failure-preserving command is missing'
    $bootstrapDirectory=Join-Path $temporary 'bootstrap-failure';New-Item -ItemType Directory -Path $bootstrapDirectory|Out-Null
    [IO.File]::WriteAllText((Join-Path $bootstrapDirectory 'bootstrap'),"#!/bin/sh`nexit 7`n",[Text.Encoding]::ASCII)
    $remoteDirectory=$bootstrapDirectory.Replace('\','/');$wifiArgs=''
    $remoteCommand=& ([scriptblock]::Create($commandAst.Extent.Text))
    $gitDirectory=Split-Path -Parent (Get-Command git).Source
    $shell=Join-Path $gitDirectory 'sh.exe'
    if(!(Test-Path -LiteralPath $shell)){$shell=Join-Path (Split-Path -Parent $gitDirectory) 'bin/sh.exe'}
    $bootstrapResult=Invoke-PhantomProcess $shell @('-c',$remoteCommand) 5 'OPERATION_TIMEOUT'
    Assert-True ($bootstrapResult.ExitCode-eq 7) 'cleanup masked failed provisioning'
    Assert-True (!(Test-Path -LiteralPath $bootstrapDirectory)) 'failed provisioning did not clean its temporary payload'

    $originalNative=${function:Invoke-PhantomNative}
    try
    {
        function Invoke-PhantomNative([string]$File,[string[]]$Arguments,[int]$TimeoutSeconds,[string]$TimeoutCode)
        {$script:observedTimeout=$TimeoutSeconds;return [pscustomobject]@{ExitCode=0;Output=@();Stdout=@();Stderr=@()}}
        foreach($budget in @(368,908))
        {
            Invoke-PhantomEv3Command 'true' $temporary $budget|Out-Null
            Assert-True ($script:observedTimeout-eq$budget) "integration SSH deadline $budget rejected or changed"
        }
    }
    finally{${function:Invoke-PhantomNative}=$originalNative}

    # Execute the log collector with fake executables, including failure propagation.
    $fakeBin=Join-Path $temporary 'bin';New-Item -ItemType Directory -Force -Path $fakeBin|Out-Null
    $pullAdb=Join-Path $fakeBin 'adb.cmd'
    $pullFixture=@'
@echo off
chcp 65001 >nul
if "%~1"=="devices" (
  echo List of devices attached
  echo QUEST-EXACT-001 device
  exit /b 0
)
echo %* > "%PHANTOM_TEST_PULL_RECORD%"
exit /b %PHANTOM_TEST_PULL_EXIT%
'@
    [IO.File]::WriteAllText($pullAdb,($pullFixture.Replace("`n","`r`n")+"`r`n"),[Text.Encoding]::ASCII)
    $analyzerFixture="@echo off`r`nchcp 65001 >nul`r`necho %* > `"%PHANTOM_TEST_ANALYZER_RECORD%`"`r`nexit /b %PHANTOM_TEST_ANALYZER_EXIT%`r`n"
    [IO.File]::WriteAllText((Join-Path $fakeBin 'python.cmd'),$analyzerFixture,[Text.Encoding]::ASCII)
    $env:PHANTOM_ADB=$pullAdb;$env:PATH=$fakeBin+';'+$env:PATH
    $env:PHANTOM_TEST_PULL_RECORD=Join-Path $temporary 'pull-args.txt'
    $env:PHANTOM_TEST_ANALYZER_RECORD=Join-Path $temporary 'analyzer-args.txt'
    $env:PHANTOM_TEST_PULL_EXIT='0';$env:PHANTOM_TEST_ANALYZER_EXIT='0'
    $captures=Join-Path $temporary 'log captures'
    function Invoke-LogCollector
    {
        $previousPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        try
        {
            $output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/quest-pull-logs.ps1" -StateRoot $temporary -Destination $captures 2>&1
            return [pscustomobject]@{ExitCode=$LASTEXITCODE;Output=$output}
        }
        finally{$ErrorActionPreference=$previousPreference}
    }
    $collected=Invoke-LogCollector
    Assert-True ($collected.ExitCode-eq 0) "mocked log collection failed: $($collected.Output-join' ')"
    $pullArguments=Get-Content -LiteralPath $env:PHANTOM_TEST_PULL_RECORD -Encoding UTF8 -Raw
    Assert-True ($pullArguments.Contains('QUEST-EXACT-001')-and$pullArguments.Contains('pull')) 'log collector did not target the designated Quest'
    $analyzerArguments=Get-Content -LiteralPath $env:PHANTOM_TEST_ANALYZER_RECORD -Encoding UTF8 -Raw
    Assert-True ($analyzerArguments.Contains($captures)) "analyzer did not receive the capture directory with spaces: $analyzerArguments"
    Remove-Item -LiteralPath $env:PHANTOM_TEST_ANALYZER_RECORD
    $env:PHANTOM_TEST_PULL_EXIT='7'
    $pullFailed=Invoke-LogCollector
    Assert-True ($pullFailed.ExitCode-ne 0) 'failed adb pull was accepted'
    Assert-True (!(Test-Path -LiteralPath $env:PHANTOM_TEST_ANALYZER_RECORD)) 'analyzer ran after failed adb pull'
    $env:PHANTOM_TEST_PULL_EXIT='0';$env:PHANTOM_TEST_ANALYZER_EXIT='9'
    $analysisFailed=Invoke-LogCollector
    Assert-True ($analysisFailed.ExitCode-ne 0) 'failed analyzer was accepted'

    $integrationFixture=@'
@echo off
setlocal EnableDelayedExpansion
if "%~1"=="devices" (
  echo List of devices attached
  echo QUEST-EXACT-001 device
  exit /b 0
)
if "%~4"=="getprop" (
  if "%~5"=="ro.product.model" echo Quest 3
  if "%~5"=="ro.product.device" echo eureka
  exit /b 0
)
if "%~6"=="resolve-activity" (
  echo dev.phantom.questprototype/MainActivity
  exit /b 0
)
set count=0
if exist "%PHANTOM_TEST_LAUNCH_STATE%" set /p count=<"%PHANTOM_TEST_LAUNCH_STATE%"
if "%~4"=="am" if "%~5"=="start" (
  set /a count+=1
  echo !count! > "%PHANTOM_TEST_LAUNCH_STATE%"
  exit /b 0
)
if "%~3"=="pull" (
  set status=PASS
  if !count! GEQ 2 if "%PHANTOM_TEST_LAUNCH_MODE%"=="bad-report" set status=FAIL
  echo {"schema_version":2,"build_id":"%PHANTOM_TEST_BUILD_ID%","build_profile":"Diagnostic","status":"!status!"} > "%~5"
  exit /b 0
)
set "request=%~4"
if not "!request:pidof=!"=="!request!" (
  if not "%PHANTOM_TEST_LAUNCH_MODE%"=="exit" echo 1234
  exit /b 0
)
if not "!request:-f=!"=="!request!" (
  if !count! LSS 2 echo present
  if !count! GEQ 2 if not "%PHANTOM_TEST_LAUNCH_MODE%"=="missing-report" echo present
  exit /b 0
)
exit /b 0
'@
    [IO.File]::WriteAllText($pullAdb,($integrationFixture.Replace("`n","`r`n")+"`r`n"),[Text.Encoding]::ASCII)
    $env:PHANTOM_TEST_LAUNCH_STATE=Join-Path $temporary 'launch-count.txt'
    $env:PHANTOM_TEST_BUILD_ID='a'*64
    foreach($edge in @(9,10,13,32))
    {
        $keyPath=Join-Path $temporary 'binary.psk';$material=[byte[]](0..31);$material[31]=[byte]$edge
        [IO.File]::WriteAllBytes($keyPath,$material)
        $output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/quest-provision-credential.ps1" -StateRoot $temporary -KeyFile $keyPath -KeyId phantom01-control -Destination (Join-Path $temporary 'credential-report') 2>&1
        Assert-True ($LASTEXITCODE-eq 0) "binary credential ending in $edge rejected: $($output-join' ')"
    }
    foreach($mode in @('normal','bad-report','missing-report'))
    {
        $env:PHANTOM_TEST_LAUNCH_MODE=$mode
        if(Test-Path -LiteralPath $env:PHANTOM_TEST_LAUNCH_STATE){Remove-Item -LiteralPath $env:PHANTOM_TEST_LAUNCH_STATE}
        $previousPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        try{$output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/quest-device-integration-test.ps1" -ExpectedBuildId $env:PHANTOM_TEST_BUILD_ID -ReportTimeoutSeconds 1 -StateRoot $temporary -Destination (Join-Path $temporary $mode) 2>&1;$integrationExit=$LASTEXITCODE}
        finally{$ErrorActionPreference=$previousPreference}
        Assert-True (($integrationExit-eq 0)-eq($mode-eq'normal')) "relaunch mode $mode returned $integrationExit : $($output-join' ')"
    }
}
finally
{
    foreach($name in $savedEnvironment.Keys){[Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process')}
    Remove-Item Env:PHANTOM_TEST_ADB_LINE -ErrorAction SilentlyContinue
    if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary -Recurse -Force}
}
if($failures.Count){$failures|ForEach-Object{[Console]::Error.WriteLine($_)};exit 1}
Write-Output 'pair-state mocked SSH/ADB contract: PASS'
