param(
    [string]$Package='dev.phantom.questprototype',
    [ValidatePattern('^$|^[0-9a-f]{64}$')][string]$ExpectedBuildId='',
    [ValidateRange(1,60)][int]$TimeoutSeconds=15,[switch]$CaptureDebug,
    [string]$Destination='',[string]$StateRoot=''
)
$ErrorActionPreference='Stop';$destinationRoot=if($Destination){$Destination}elseif($CaptureDebug){'results/quest/debug'}else{'results/quest/start'};$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$reportPath=$null;$adb=$null;$serial=$null;$remoteStatus=$null
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
        $failedId=if($ExpectedBuildId){$ExpectedBuildId}else{'failed-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        $runDirectory=Join-Path ([IO.Path]::GetFullPath($destinationRoot)) $failedId;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
        $reportPath=Join-Path $runDirectory 'quest-start.json';$finished=(Get-Date).ToUniversalTime();$reason=if($failureMessage-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'START_FAILED'};$failed=[ordered]@{schema_version=1;phase=if($CaptureDebug){'DEBUG'}else{'START'};component='QUEST';profile='Diagnostic';status='FAIL';reason=$reason;build_id=if($ExpectedBuildId){$ExpectedBuildId}else{$null};detail=$failureMessage;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state=$terminalState;hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
        [IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
        if($CaptureDebug -and $adb -and $serial)
        {
            try{Invoke-PhantomAdb $adb $serial @('logcat','-d') 10|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.logcat.txt') -Encoding UTF8}catch{}
            try{Invoke-PhantomAdb $adb $serial @('shell','dumpsys','activity','top') 10|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.activity.txt') -Encoding UTF8}catch{}
            try{Invoke-PhantomAdb $adb $serial @('shell','dumpsys','package',$Package) 10|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.package.txt') -Encoding UTF8}catch{}
            if($remoteStatus){try{Invoke-PhantomAdb $adb $serial @('shell',"test ! -f '$remoteStatus' || cat '$remoteStatus'") 5|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.startup-status.json') -Encoding UTF8}catch{}}
        }
    }
    [Console]::Error.WriteLine("QUEST START: FAIL report=$reportPath; $failureMessage");exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1";. "$PSScriptRoot/pair-state.ps1";$adb=Get-PhantomAdb
$serial=Get-PhantomQuestDevice $adb $StateRoot;$model=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.model') 8)-join'').Trim();$device=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.device') 8)-join'').Trim()
if($model-ne'Quest 3' -or $device-ne'eureka'){throw "Physical Quest 3 required; found model=$model device=$device"}
$installedPath=(@(Invoke-PhantomAdb $adb $serial @('shell','pm','path',$Package) 8|Where-Object {$_-match'^package:'}|Select-Object -First 1)-join'').Trim()
if($installedPath-notmatch'^package:'){throw "Installed package was not found: $Package"}
$activity=(@(Invoke-PhantomAdb $adb $serial @('shell','cmd','package','resolve-activity','--brief',$Package) 8|Select-Object -Last 1)-join'').Trim()
if(!$activity -or $activity-match'No activity'){throw "Launch activity was not resolved for $Package"}
$stopOutput=@(Invoke-PhantomAdb $adb $serial @('shell','am','force-stop',$Package) 8)
$remoteStatus="/sdcard/Android/data/$Package/files/phantom-status/startup.json";Invoke-PhantomAdb $adb $serial @('shell','rm','-f',$remoteStatus) 8|Out-Null
if($CaptureDebug){Invoke-PhantomAdb $adb $serial @('logcat','-c') 8|Out-Null}
Invoke-PhantomAdb $adb $serial @('shell','input','keyevent','KEYCODE_WAKEUP') 8|Out-Null
$launch=@(Invoke-PhantomAdb $adb $serial @('shell','am','start','-n',$activity) 10);if(($launch-join"`n")-match'Error:'){throw "Quest START launch failed: $($launch-join' ')"}
$deadline=(Get-Date).AddSeconds($TimeoutSeconds);$appPid='';$statusJson=''
while((Get-Date)-lt$deadline)
{
    $appPid=(@(Invoke-PhantomAdb $adb $serial @('shell',"pidof '$Package' 2>/dev/null || true") 3)-join'').Trim()
    $statusJson=(@(Invoke-PhantomAdb $adb $serial @('shell',"test ! -f '$remoteStatus' || cat '$remoteStatus'") 3)-join"`n").Trim()
    if($appPid-and$statusJson){break};Start-Sleep -Milliseconds 250
}
if(!$appPid){throw "Quest START did not create a process within $TimeoutSeconds seconds"}
if(!$statusJson){throw "Quest START did not produce bounded startup status within $TimeoutSeconds seconds"}
try{$status=$statusJson|ConvertFrom-Json}catch{throw 'Quest START returned malformed startup status'}
if($status.schema_version-ne 1 -or $status.build_id-notmatch'^[0-9a-f]{64}$'){throw 'Quest START returned invalid installed build identity'}
if($ExpectedBuildId-and$status.build_id-ne$ExpectedBuildId){throw "Installed Quest build mismatch: expected=$ExpectedBuildId actual=$($status.build_id)"}
if($status.runtime_status-ne'ready'){throw "QUEST_RUNTIME_NOT_READY: runtime_status=$($status.runtime_status)"}
if($status.control_credential-eq'absent'){throw 'PROVISION_REQUIRED: Quest CONTROL credential is absent'}
if($status.control_credential-ne'ready'){throw "PROVISION_CORRUPT: Quest CONTROL credential status=$($status.control_credential)"}
$runDirectory=Join-Path ([IO.Path]::GetFullPath($destinationRoot)) $status.build_id;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
if($CaptureDebug)
{
    Invoke-PhantomAdb $adb $serial @('logcat','-d') 10|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.logcat.txt') -Encoding UTF8
    Invoke-PhantomAdb $adb $serial @('shell','dumpsys','activity','top') 10|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.activity.txt') -Encoding UTF8
    Invoke-PhantomAdb $adb $serial @('shell','dumpsys','package',$Package) 10|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.package.txt') -Encoding UTF8
    [IO.File]::WriteAllText((Join-Path $runDirectory 'quest-debug.startup-status.json'),$statusJson+"`n",[Text.UTF8Encoding]::new($false))
}
$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase=if($CaptureDebug){'DEBUG'}else{'START'};component='QUEST';profile='Diagnostic';status='PASS';reason='STARTED';build_id=$status.build_id;package=$Package;control_credential='ready';device_class=[ordered]@{model=$model;device=$device};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state='APP_PROCESS_RUNNING';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
$reportPath=Join-Path $runDirectory 'quest-start.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false));$phaseComplete=$true
Write-Output "QUEST START: PASS build_id=$($status.build_id) report=$reportPath"
