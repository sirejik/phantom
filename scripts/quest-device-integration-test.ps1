param(
    [ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedBuildId,
    [string]$Package='dev.phantom.questprototype',[ValidateRange(1,60)][int]$ReportTimeoutSeconds=35,
    [string]$Destination='results/quest/device-integration',[string]$StateRoot='',
    [string]$ApkA='',[string]$ApkB=''
)
$ErrorActionPreference='Stop'
$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$reportPath=$null

# Optional update-persistence scenario; all device checks share this entry point.
if($ApkA -or $ApkB)
{
    if(!$ApkA -or !$ApkB -or $ExpectedBuildId){throw 'Specify both -ApkA and -ApkB, without -ExpectedBuildId'}
    function Read-BuildId([string]$Apk)
    {
        $resolved=[IO.Path]::GetFullPath($Apk)
        $sidecar=$resolved+'.build-manifest.json'
        if(!(Test-Path -LiteralPath $resolved -PathType Leaf) -or !(Test-Path -LiteralPath $sidecar -PathType Leaf))
        {throw "APK or sidecar is missing: $resolved"}
        $manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
        if($manifest.component-ne'QUEST' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw "Invalid Quest manifest: $sidecar"}
        return $manifest.build_id
    }

    $started=(Get-Date).ToUniversalTime();$buildA=Read-BuildId $ApkA;$buildB=Read-BuildId $ApkB
    if($buildA-eq$buildB){throw 'Persistence regression requires two distinct Quest builds'}

    . "$PSScriptRoot/pair-state.ps1"
    Read-PhantomPairState $StateRoot -RequirePrivateFiles|Out-Null
    . "$PSScriptRoot/../tools/toolchain.ps1"
    $adb=Get-PhantomAdb;$serial=Get-PhantomQuestDevice $adb $StateRoot

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot/quest-install.ps1" -Apk $ApkA -Package $Package -StateRoot $StateRoot -Repair
    if($LASTEXITCODE-ne 0){throw 'Build A INSTALL failed'}
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot/quest-start.ps1" -Package $Package -ExpectedBuildId $buildA -StateRoot $StateRoot
    if($LASTEXITCODE-ne 0){throw 'Build A credential was not ready'}
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot/quest-install.ps1" -Apk $ApkB -Package $Package -StateRoot $StateRoot
    if($LASTEXITCODE-ne 0){throw 'Build B in-place INSTALL failed'}
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$PSScriptRoot/quest-start.ps1" -Package $Package -ExpectedBuildId $buildB -StateRoot $StateRoot
    if($LASTEXITCODE-ne 0){throw 'Credential did not survive the in-place update to build B'}

    $finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase='DEVICE INTEGRATION TEST';test_id='quest-control-credential-persistence';status='PASS';build_a=$buildA;build_b=$buildB;install_mode='adb install -r -g';credential_contents_recorded=$false;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds}
    New-Item -ItemType Directory -Force -Path $Destination|Out-Null
    $path=Join-Path ([IO.Path]::GetFullPath($Destination)) 'report.json'
    Invoke-PhantomAdb $adb $serial @('shell','am','force-stop',$Package) 8|Out-Null
    [IO.File]::WriteAllText($path,($report|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
    $phaseComplete=$true
    Write-Output "QUEST credential persistence: PASS build_a=$buildA build_b=$buildB report=$path"

    exit 0
}
if(!$ExpectedBuildId){throw '-ExpectedBuildId is required for installed-build checks'}

trap
{
    $failureMessage=$_.Exception.Message
    if(!$phaseComplete)
    {
        $terminalState='APP_STATE_UNVERIFIED'
        if($adb -and $serial)
        {
            try{Invoke-PhantomAdb $adb $serial @('shell','am','force-stop',$Package) 8|Out-Null;$terminalState='APP_FORCE_STOP_REQUESTED'}catch{}
        }
        $reportIdentity=if($ExpectedBuildId){$ExpectedBuildId}else{'credential-persistence'}
        $runDirectory=Join-Path ([IO.Path]::GetFullPath($Destination)) $reportIdentity;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
        $reportPath=Join-Path $runDirectory 'quest-device-integration-test.json';$finished=(Get-Date).ToUniversalTime();$reason=if($failureMessage-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'DEVICE_CHECK_FAILED'};$failed=[ordered]@{schema_version=2;phase='DEVICE INTEGRATION TEST';gate='QUEST DEVICE INTEGRATION TEST';component='QUEST';profile='UNKNOWN';status='FAIL';reason=$reason;build_id=$ExpectedBuildId;artifact_sha256=$null;detail=$failureMessage;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state=$terminalState;hardware_evidence_state='DEVICE'}
        [IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("QUEST DEVICE INTEGRATION TEST: FAIL report=$reportPath; $failureMessage");exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1";. "$PSScriptRoot/pair-state.ps1";$adb=Get-PhantomAdb
$serial=Get-PhantomQuestDevice $adb $StateRoot;$model=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.model') 8)-join'').Trim();$device=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.device') 8)-join'').Trim();if($model-ne'Quest 3' -or $device-ne'eureka'){throw 'QUEST_IDENTITY_MISMATCH: designated device is not Quest 3/eureka'}
$activity=(@(Invoke-PhantomAdb $adb $serial @('shell','cmd','package','resolve-activity','--brief',$Package) 8|Select-Object -Last 1)-join'').Trim();if(!$activity-or$activity-match'No activity'){throw "Installed package was not found: $Package"}
$remoteReport="/sdcard/Android/data/$Package/files/quest-device-integration-test.json";$runDirectory=Join-Path ([IO.Path]::GetFullPath($Destination)) $ExpectedBuildId;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
function Start-And-Wait([string]$label,[bool]$WaitForReport)
{
    Invoke-PhantomAdb $adb $serial @('shell','input','keyevent','KEYCODE_WAKEUP') 8|Out-Null
    $launch=@(Invoke-PhantomAdb $adb $serial @('shell','am','start','-n',$activity) 10);if(($launch-join"`n")-match'Error:'){throw "$label launch failed"}
    $deadline=(Get-Date).AddSeconds($ReportTimeoutSeconds);$appPid=''
    while((Get-Date)-lt$deadline)
    {
        $appPid=(@(Invoke-PhantomAdb $adb $serial @('shell',"pidof '$Package' 2>/dev/null || true") 3)-join'').Trim()
        $present=(!$WaitForReport)-or((@(Invoke-PhantomAdb $adb $serial @('shell',"test ! -f '$remoteReport' || echo present") 3)-join'').Trim()-eq'present')
        if($appPid-and$present){return $appPid};Start-Sleep -Milliseconds 250
    }
    throw "$label did not become ready within $ReportTimeoutSeconds seconds"
}
Invoke-PhantomAdb $adb $serial @('shell','am','force-stop',$Package) 8|Out-Null;Invoke-PhantomAdb $adb $serial @('shell','rm','-f',$remoteReport) 8|Out-Null;Invoke-PhantomAdb $adb $serial @('logcat','-c') 8|Out-Null
$firstPid=Start-And-Wait 'first' $true;Invoke-PhantomAdb $adb $serial @('pull',$remoteReport,(Join-Path $runDirectory 'app-report.json')) 15|Out-Null;$firstLog=@(Invoke-PhantomAdb $adb $serial @('logcat','-d') 10)
Invoke-PhantomAdb $adb $serial @('shell','am','force-stop',$Package) 8|Out-Null
Invoke-PhantomAdb $adb $serial @('shell','rm','-f',$remoteReport) 8|Out-Null
Invoke-PhantomAdb $adb $serial @('logcat','-c') 8|Out-Null
$secondPid=Start-And-Wait 'relaunch' $true
Invoke-PhantomAdb $adb $serial @('pull',$remoteReport,(Join-Path $runDirectory 'relaunch-report.json')) 15|Out-Null
Start-Sleep -Seconds 2
$secondLivePid=(@(Invoke-PhantomAdb $adb $serial @('shell',"pidof '$Package' 2>/dev/null || true") 3)-join'').Trim()
$secondLog=@(Invoke-PhantomAdb $adb $serial @('logcat','-d') 10)
Invoke-PhantomAdb $adb $serial @('shell','am','force-stop',$Package) 8|Out-Null
$appReport=Get-Content -LiteralPath (Join-Path $runDirectory 'app-report.json') -Raw -Encoding UTF8|ConvertFrom-Json
$relaunchReport=Get-Content -LiteralPath (Join-Path $runDirectory 'relaunch-report.json') -Raw -Encoding UTF8|ConvertFrom-Json
if($appReport.schema_version-ne 2 -or $relaunchReport.schema_version-ne 2 -or $appReport.build_profile-notin @('Diagnostic','Release')){throw 'MALFORMED_PHASE_RESULT: invalid Quest integration report schema or profile'}
$crashPattern='FATAL EXCEPTION|Fatal signal|CRASH:|ANR in dev\.phantom\.questprototype';$checks=@(
    [ordered]@{test_id='installed-build-id';status=if($appReport.build_id-eq$ExpectedBuildId){'PASS'}else{'FAIL'};detail="expected=$ExpectedBuildId actual=$($appReport.build_id)"},
    [ordered]@{test_id='first-launch';status=if($firstPid-and!(($firstLog-join"`n")-match$crashPattern)){'PASS'}else{'FAIL'}},
    [ordered]@{test_id='force-stop-relaunch';status=if($secondPid-and$secondLivePid-eq$secondPid-and$relaunchReport.build_id-eq$ExpectedBuildId-and$relaunchReport.status-eq'PASS'-and$relaunchReport.build_profile-eq$appReport.build_profile-and!(($secondLog-join"`n")-match$crashPattern)){'PASS'}else{'FAIL'}})
$failed=@($checks|Where-Object {$_.status -eq 'FAIL'}).Count-gt 0;$status=if(!$failed-and$appReport.status-eq'PASS'){'PASS'}else{'FAIL'};$finished=(Get-Date).ToUniversalTime()
$report=[ordered]@{schema_version=2;phase='DEVICE INTEGRATION TEST';component='QUEST';profile=$appReport.build_profile;status=$status;reason=if($status-eq'PASS'){'COMPLETED'}else{'DEVICE_CHECK_FAILED'};build_id=$ExpectedBuildId;device_class=[ordered]@{model=$model;device=$device};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;app_report=$appReport;relaunch_report=$relaunchReport;host_checks=$checks;terminal_state='APP_FORCE_STOPPED';hardware_evidence_state='DEVICE'}
$reportPath=Join-Path $runDirectory 'quest-device-integration-test.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 12)+"`n",[Text.UTF8Encoding]::new($false));$phaseComplete=$true
Write-Output "QUEST DEVICE INTEGRATION TEST: $status report=$reportPath";if($status-ne'PASS'){exit 1}
