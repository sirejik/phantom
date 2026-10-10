$ErrorActionPreference='Stop'
$repository=Split-Path -Parent $PSScriptRoot
. "$repository/scripts/pair-state.ps1"
. "$repository/scripts/ev3-deploy-common.ps1"
. "$repository/scripts/install-common.ps1"
. "$repository/scripts/install-device.ps1"
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('phantom-pair-test-'+[Guid]::NewGuid().ToString('N'))
$failures=New-Object 'System.Collections.Generic.List[string]'
$savedEnvironment=@{}
foreach($name in @('PHANTOM_UNITY_ROOT','PHANTOM_TEST_UNITY_MODE','PHANTOM_TEST_INSTALL_HASH','PHANTOM_TEST_INSTALL_RECORD','PHANTOM_TEST_INSTALL_FAIL'))
{$savedEnvironment[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
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
    # Run the real Unity test entry point with a fake executable. Process success
    # must not accept stale, missing, empty or failed NUnit reports.
    $env:PHANTOM_UNITY_ROOT=Join-Path $temporary 'unity'
    New-Item -ItemType Directory -Force -Path (Join-Path $env:PHANTOM_UNITY_ROOT 'Editor/Data') | Out-Null
    Add-Type -OutputAssembly (Join-Path $env:PHANTOM_UNITY_ROOT 'Editor/Unity.exe') -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.IO;
public class FakeUnity {
    public static int Main(string[] args) {
        int target=Array.IndexOf(args,"-buildTarget");
        if(target<0 || target+1>=args.Length || args[target+1]!="Android") return 8;
        string mode=Environment.GetEnvironmentVariable("PHANTOM_TEST_UNITY_MODE");
        if(mode=="timeout") { System.Threading.Thread.Sleep(10000); return 0; }
        string path=args[Array.IndexOf(args,"-testResults")+1];
        if(mode=="missing") return 0;
        string report=mode=="empty" ? "<test-run result='Passed' total='0' passed='0' failed='0'/>" :
            mode=="failed" ? "<test-run result='Failed' total='1' passed='0' failed='1'/>" :
            mode=="malformed" ? "<test-run" : "<test-run result='Passed' total='1' passed='1' failed='0'/>";
        File.WriteAllText(path,report);
        return mode=="exit" ? 7 : 0;
    }
}
'@
    foreach($mode in @('passed','failed','empty','missing','malformed','timeout','exit'))
    {
        $env:PHANTOM_TEST_UNITY_MODE=$mode
        $report=Join-Path $temporary 'unity-report.xml'
        [IO.File]::WriteAllText($report,"<test-run result='Passed' total='1' passed='1' failed='0'/>")
        $previousPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        try{$output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/quest-test.ps1" -Suite Unity -Results $report -TimeoutSeconds 1 2>&1;$unityExit=$LASTEXITCODE}
        finally{$ErrorActionPreference=$previousPreference}
        Assert-True (($unityExit-eq 0)-eq($mode-eq'passed')) "Unity mode $mode returned $unityExit : $($output-join' ')"
    }
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

    $secretBefore=(Get-FileHash $paths.ControlSecret).Hash
    $run=Initialize-PhantomInstallPair -StateRoot $temporary
    Assert-True ($run.State.quest_adb_serial-eq'QUEST-EXACT-001') 'idempotent INSTALL setup changed the designated Quest'
    Assert-True ((Get-FileHash $paths.ControlSecret).Hash-eq$secretBefore) 'routine INSTALL rotated the credential'
    Assert-Throws {Initialize-PhantomInstallPair -StateRoot $temporary -RotateControlSecret} 'PROVISION_CORRUPT'
    Assert-Throws {Initialize-PhantomInstallPair -StateRoot $temporary -QuestSerial OTHER} 'QUEST_IDENTITY_MISMATCH'
    Assert-Throws {Initialize-PhantomInstallPair -StateRoot $temporary -HostFingerprint ('SHA256:'+('B'*43))} 'HOST_KEY_MISMATCH'
    $firstRoot=Join-Path $temporary 'first-install'
    Assert-Throws {Initialize-PhantomInstallPair -StateRoot $firstRoot -QuestSerial QUEST-EXACT-001} 'PROVISION_REQUIRED'
    $first=Initialize-PhantomInstallPair -StateRoot $firstRoot -QuestSerial QUEST-EXACT-001 -HostFingerprint ('SHA256:'+('A'*43))
    Assert-True ((Get-Item $first.Paths.ControlSecret).Length-eq 32) 'first INSTALL did not create a 32-byte CONTROL credential'
    Assert-True (!$first.State.quest_credential_staged) 'first INSTALL prematurely marked the Quest credential as staged'
    $custom=Initialize-PhantomInstallPair -StateRoot (Join-Path $temporary 'custom-pair') -QuestSerial QUEST-EXACT-001 -HostFingerprint ('SHA256:'+('A'*43)) -RobotId custom-robot -ControlKeyId custom-key
    $customUpdate=Initialize-PhantomInstallPair -StateRoot $custom.Paths.Root
    Assert-True ($customUpdate.State.robot_id-eq'custom-robot'-and$customUpdate.State.control_key_id-eq'custom-key') 'routine INSTALL did not preserve custom pair identities'

    $fakeSsh=Join-Path $temporary 'fake-ssh.cmd'
    [IO.File]::WriteAllText($fakeSsh,"@echo off`r`necho REPORT_CHANNEL`r`necho DIAGNOSTIC_CHANNEL 1>&2`r`nexit /b 7`r`n",[Text.Encoding]::ASCII)
    $transport=Invoke-PhantomNative $fakeSsh @() 3 'DEVICE_NOT_FOUND'
    Assert-True ($transport.ExitCode-eq 7) 'mocked SSH exit code was not preserved'
    Assert-True (($transport.Stdout.Count-eq 1)-and($transport.Stdout[0]-eq'REPORT_CHANNEL')) 'mocked SSH stdout was not isolated'
    Assert-True (($transport.Stderr.Count-eq 1)-and($transport.Stderr[0].Trim()-eq'DIAGNOSTIC_CHANNEL')) 'mocked SSH stderr was not isolated'

    # Exercise the actual provisioning command against a failing temporary bootstrap.
    $parseTokens=$null;$parseErrors=$null
    $provisionAst=[Management.Automation.Language.Parser]::ParseFile("$repository/scripts/install-device.ps1",[ref]$parseTokens,[ref]$parseErrors)
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
        try{Invoke-PhantomQuestCredentialSetup -StateRoot $temporary -KeyFile $keyPath -KeyId phantom01-control -Destination (Join-Path $temporary 'credential-report')|Out-Null}
        catch{$failures.Add("binary credential ending in $edge rejected: $($_.Exception.Message)")}
    }
    # Run the complete Quest installer: first setup happens after APK install,
    # an update preserves credentials, and a failed install must not stage a key.
    $installAdb=Join-Path $temporary 'install-adb.exe'
    Add-Type -OutputAssembly $installAdb -OutputType ConsoleApplication -TypeDefinition @'
using System;
using System.IO;
public class FakeInstallAdb {
    public static int Main(string[] args) {
        File.AppendAllText(Environment.GetEnvironmentVariable("PHANTOM_TEST_INSTALL_RECORD"),string.Join(" ",args)+"\n");
        if(args.Length==1 && args[0]=="devices") { Console.WriteLine("List of devices attached\nQUEST-EXACT-001 device"); return 0; }
        if(args.Length>3 && args[2]=="shell" && args[3]=="getprop") { Console.WriteLine(args[4]=="ro.product.model"?"Quest 3":"eureka"); return 0; }
        if(args.Length>2 && args[2]=="install") return Environment.GetEnvironmentVariable("PHANTOM_TEST_INSTALL_FAIL")=="1"?7:0;
        if(args.Length>3 && args[3]=="pm") Console.WriteLine("package:/data/app/phantom/base.apk");
        if(args.Length>3 && args[3]=="toybox") Console.WriteLine(Environment.GetEnvironmentVariable("PHANTOM_TEST_INSTALL_HASH")+" /data/app/phantom/base.apk");
        if(args.Length>3 && args[3].Contains("-f")) Console.WriteLine("present");
        return 0;
    }
}
'@
    $env:PHANTOM_ADB=$installAdb
    $env:PHANTOM_TEST_INSTALL_RECORD=Join-Path $temporary 'install-calls.txt'
    $apk=Join-Path $temporary 'candidate.apk';[IO.File]::WriteAllBytes($apk,[byte[]](1,2,3))
    $env:PHANTOM_TEST_INSTALL_HASH=(Get-FileHash $apk).Hash.ToLowerInvariant()
    $installManifest=[ordered]@{schema_version=8;build_identity_schema='PHANTOM-BUILD-V4';component='QUEST';build_id=('a'*64);build_profile='Diagnostic';apk_sha256=$env:PHANTOM_TEST_INSTALL_HASH}
    [IO.File]::WriteAllText($apk+'.build-manifest.json',($installManifest|ConvertTo-Json))
    $installState=Join-Path $temporary 'quest-install-state'
    function Invoke-InstallFixture([string]$Root){
        $oldPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
        try{$output=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/quest-install.ps1" -Apk $apk -StateRoot $Root -QuestSerial QUEST-EXACT-001 -HostFingerprint ('SHA256:'+('A'*43)) -Destination (Join-Path $temporary 'install-results') 2>&1;return [pscustomobject]@{Code=$LASTEXITCODE;Output=($output-join' ')}}
        finally{$ErrorActionPreference=$oldPreference}
    }
    $installed=Invoke-InstallFixture $installState
    Assert-True ($installed.Code-eq 0) "first Quest INSTALL failed: $($installed.Output)"
    $calls=Get-Content $env:PHANTOM_TEST_INSTALL_RECORD
    $installLine=@($calls|Where-Object{$_-match'"?install"? "?-r"? "?-g"?'})[0]
    $pushLine=@($calls|Where-Object{$_-match'"?push"? "?--sync"?'})[0]
    Assert-True ($installLine -and $pushLine -and [Array]::IndexOf($calls,$pushLine)-gt[Array]::IndexOf($calls,$installLine)) "credential ordering failed: $($calls-join' ; ')"
    Assert-True ((Read-PhantomPairState $installState).State.quest_credential_staged) 'successful first INSTALL did not save credential staging state'
    Remove-Item -LiteralPath $env:PHANTOM_TEST_INSTALL_RECORD
    $installManifest.build_profile='Release';[IO.File]::WriteAllText($apk+'.build-manifest.json',($installManifest|ConvertTo-Json))
    $updated=Invoke-InstallFixture $installState
    Assert-True ($updated.Code-eq 0) "Quest update failed: $($updated.Output)"
    Assert-True (!((Get-Content $env:PHANTOM_TEST_INSTALL_RECORD)-match'"?push"? "?--sync"?')) 'Quest update restaged the CONTROL credential'
    $installManifest.build_profile='Diagnostic';[IO.File]::WriteAllText($apk+'.build-manifest.json',($installManifest|ConvertTo-Json))
    Remove-Item -LiteralPath $env:PHANTOM_TEST_INSTALL_RECORD;$env:PHANTOM_TEST_INSTALL_FAIL='1'
    $failedInstall=Invoke-InstallFixture (Join-Path $temporary 'failed-install-state')
    Assert-True ($failedInstall.Code-ne 0) "failed adb install was accepted: $($failedInstall.Output); calls=$((Get-Content $env:PHANTOM_TEST_INSTALL_RECORD)-join' ; ')"
    Assert-True (!((Get-Content $env:PHANTOM_TEST_INSTALL_RECORD)-match'"?push"? "?--sync"?')) 'failed install staged a credential'
    $env:PHANTOM_TEST_INSTALL_FAIL='';$env:PHANTOM_ADB=$pullAdb
    # Exercise EV3 orchestration without a device; substitute transport, not decisions.
    $ev3Package=Join-Path $temporary 'ev3.tar.gz'
    [IO.File]::WriteAllBytes($ev3Package,[byte[]]@(4,5,6))
    $ev3Manifest=[ordered]@{component='EV3';build_id=('b'*64);artifact_sha256=(Get-FileHash $ev3Package).Hash.ToLowerInvariant()}
    [IO.File]::WriteAllText($ev3Package+'.build-manifest.json',($ev3Manifest|ConvertTo-Json))
    $installBody=(Get-Content "$repository/scripts/ev3-install.ps1" -Raw -Encoding UTF8)-replace '(?m)^\. "[^\r\n]+"\r?\n',''
    $installBlock=[scriptblock]::Create($installBody)
    & {
        $steps=New-Object 'System.Collections.Generic.List[string]'
        $rejectSetup=$false
        function Initialize-PhantomInstallPair {return [pscustomobject]@{State=@{ev3_host_key_fingerprint='test'};Paths=@{SshKey='key';SshDirectory='ssh';ControlSecret='secret';SshConfig='missing'}}}
        function Invoke-PhantomEv3Setup {$steps.Add('setup');if($rejectSetup){throw 'fixture setup failed'}}
        function Invoke-PhantomEv3Transfer {$steps.Add('transfer')}
        function Invoke-PhantomEv3ReportedPhase {$steps.Add('install');return [pscustomobject]@{build_id=('b'*64)}}
        & $installBlock -Package $ev3Package -Destination $temporary|Out-Null
        Assert-True (($steps-join',')-eq'setup,transfer,install') 'EV3 INSTALL did not perform setup, transfer and installation in order'
        $steps.Clear();$rejectSetup=$true
        try{& $installBlock -Package $ev3Package -Destination $temporary|Out-Null;$failures.Add('EV3 INSTALL accepted failed setup')}catch{}
        Assert-True (($steps-join',')-eq'setup') 'EV3 INSTALL continued after setup failure'
        $steps.Clear();$ev3Manifest.artifact_sha256=('0'*64)
        [IO.File]::WriteAllText($ev3Package+'.build-manifest.json',($ev3Manifest|ConvertTo-Json))
        try{& $installBlock -Package $ev3Package -Destination $temporary|Out-Null;$failures.Add('EV3 INSTALL accepted mismatched package')}catch{}
        Assert-True ($steps.Count-eq 0) 'EV3 INSTALL contacted device before package validation'
    }
    $collectorBody=(Get-Content "$repository/scripts/ev3-pull-logs.ps1" -Raw -Encoding UTF8)-replace '(?m)^\. "[^\r\n]+"\r?\n',''
    & {
        $rejectJournal=$false
        function Invoke-PhantomEv3Command {
            param($RemoteCommand,$StateRoot,$TimeoutSeconds)
            Assert-True ($RemoteCommand.Contains('journalctl')-and$RemoteCommand.Contains('-n 5')) 'EV3 collector did not bound journal collection'
            return [pscustomobject]@{ExitCode=if($rejectJournal){7}else{0};Stdout=@('{"PRIORITY":"3"}')}
        }
        $collector=[scriptblock]::Create($collectorBody)
        & $collector -Destination (Join-Path $temporary 'ev3-logs') -Lines 5 -SkipAnalysis|Out-Null
        Assert-True (Test-Path (Join-Path $temporary 'ev3-logs/journal.jsonl')) 'EV3 collector did not write the journal'
        $rejectJournal=$true
        try{& $collector -Destination (Join-Path $temporary 'failed-ev3-logs') -Lines 5 -SkipAnalysis|Out-Null;$failures.Add('EV3 collector accepted failed SSH')}catch{}
        Assert-True (!(Test-Path (Join-Path $temporary 'failed-ev3-logs/journal.jsonl'))) 'failed EV3 collection wrote a success artifact'
    }
    # The update scenario uses the same Quest DEVICE entry, without a separate runner.
    $deviceSource=Get-Content "$repository/scripts/quest-device-integration-test.ps1" -Raw -Encoding UTF8
    $scenarioStart=$deviceSource.IndexOf('    function Read-BuildId')
    $scenarioEnd=$deviceSource.IndexOf('    exit 0',$scenarioStart)
    $scenarioBody=$deviceSource.Substring($scenarioStart,$scenarioEnd-$scenarioStart)-replace '(?m)^\s*\. "[^\r\n]+"\r?\n',''
    & {
        $calls=New-Object 'System.Collections.Generic.List[string]'
        $rejectSecondStart=$false;$StateRoot=$temporary;$Package='dev.phantom.questprototype'
        $ApkA=$apk;$ApkB=Join-Path $temporary 'update.apk'
        [IO.File]::WriteAllBytes($ApkB,[byte[]]@(7,8,9))
        $updateManifest=@{component='QUEST';build_id=('c'*64)}
        [IO.File]::WriteAllText($ApkB+'.build-manifest.json',($updateManifest|ConvertTo-Json))
        function Get-PhantomAdb {return 'fixture-adb'}
        function Get-PhantomQuestDevice {return 'QUEST-EXACT-001'}
        function Invoke-PhantomAdb {$calls.Add('force-stop')}
        function powershell.exe {
            $calls.Add($args-join' ')
            $code=if($rejectSecondStart -and ($args-join' ').Contains(('c'*64))){7}else{0}
            Set-Variable LASTEXITCODE $code -Scope 1
        }
        $scenario=[scriptblock]::Create($scenarioBody)
        $Destination=Join-Path $temporary 'persistence-pass'
        & $scenario|Out-Null
        Assert-True ($calls.Count-eq 5 -and $calls[0].Contains('-Repair') -and !$calls[2].Contains('-Repair') -and $calls[4]-eq'force-stop') 'persistence scenario restaged the updated credential or failed to stop the app'
        Assert-True (Test-Path (Join-Path $Destination 'report.json')) 'persistence success report missing'
        $Destination=Join-Path $temporary 'persistence-fail';$rejectSecondStart=$true
        try{& $scenario|Out-Null;$failures.Add('persistence scenario accepted failed second START')}catch{}
        Assert-True (!(Test-Path (Join-Path $Destination 'report.json'))) 'failed persistence wrote a PASS report'
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
