param(
    [string]$Package='dev.phantom.questprototype',
    [ValidatePattern('^$|^[0-9a-f]{64}$')][string]$ExpectedBuildId='',
    [ValidateRange(1,60)][int]$TimeoutSeconds=15,[switch]$Debug,
    [string]$Destination=''
)
$ErrorActionPreference='Stop';$destinationRoot=if($Destination){$Destination}elseif($Debug){'results/quest/debug'}else{'results/quest/start'};$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$reportPath=$null;$adb=$null;$serial=$null;$remoteStatus=$null
trap
{
    if(!$phaseComplete)
    {
        $failedId=if($ExpectedBuildId){$ExpectedBuildId}else{'failed-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        $runDirectory=Join-Path ([IO.Path]::GetFullPath($destinationRoot)) $failedId;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
        $reportPath=Join-Path $runDirectory 'quest-start.json';$failed=[ordered]@{schema_version=1;phase=if($Debug){'DEBUG'}else{'START'};status='FAIL';build_id=if($ExpectedBuildId){$ExpectedBuildId}else{$null};detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=(Get-Date).ToUniversalTime().ToString('o');terminal_state='APP_STATE_UNVERIFIED'}
        [IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
        if($Debug -and $adb -and $serial)
        {
            @(& $adb -s $serial logcat -d 2>&1)|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.logcat.txt') -Encoding UTF8
            @(& $adb -s $serial shell dumpsys activity top 2>&1)|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.activity.txt') -Encoding UTF8
            @(& $adb -s $serial shell dumpsys package $Package 2>&1)|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.package.txt') -Encoding UTF8
            if($remoteStatus){@(& $adb -s $serial shell "test ! -f '$remoteStatus' || cat '$remoteStatus'" 2>&1)|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.startup-status.json') -Encoding UTF8}
        }
    }
    [Console]::Error.WriteLine("QUEST START: FAIL report=$reportPath; $($_.Exception.Message)");exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1";$adb=Get-PhantomAdb
$devices=@(& $adb devices|Select-Object -Skip 1|Where-Object {$_-match'\sdevice$'})
if($devices.Count-ne 1){throw "Exactly one authorized ADB device is required; found $($devices.Count)"}
$serial=($devices[0]-split'\s+')[0];$model=(@(& $adb -s $serial shell getprop ro.product.model)-join'').Trim();$device=(@(& $adb -s $serial shell getprop ro.product.device)-join'').Trim()
if($model-ne'Quest 3' -or $device-ne'eureka'){throw "Physical Quest 3 required; found model=$model device=$device"}
$installedPath=(@(& $adb -s $serial shell pm path $Package|Where-Object {$_-match'^package:'}|Select-Object -First 1)-join'').Trim()
if($installedPath-notmatch'^package:'){throw "Installed package was not found: $Package"}
$activity=(@(& $adb -s $serial shell cmd package resolve-activity --brief $Package|Select-Object -Last 1)-join'').Trim()
if(!$activity -or $activity-match'No activity'){throw "Launch activity was not resolved for $Package"}
$remoteStatus="/sdcard/Android/data/$Package/files/phantom-status/startup.json";& $adb -s $serial shell rm -f $remoteStatus|Out-Null
if($Debug){& $adb -s $serial logcat -c|Out-Null}
& $adb -s $serial shell input keyevent KEYCODE_WAKEUP|Out-Null
$launch=@(& $adb -s $serial shell am start -n $activity);if($LASTEXITCODE-ne 0 -or ($launch-join"`n")-match'Error:'){throw "Quest START launch failed: $($launch-join' ')"}
$deadline=(Get-Date).AddSeconds($TimeoutSeconds);$appPid='';$statusJson=''
while((Get-Date)-lt$deadline)
{
    $appPid=(@(& $adb -s $serial shell "pidof '$Package' 2>/dev/null || true")-join'').Trim()
    $statusJson=(@(& $adb -s $serial shell "test ! -f '$remoteStatus' || cat '$remoteStatus'")-join"`n").Trim()
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
if($Debug)
{
    & $adb -s $serial logcat -d|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.logcat.txt') -Encoding UTF8
    & $adb -s $serial shell dumpsys activity top|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.activity.txt') -Encoding UTF8
    & $adb -s $serial shell dumpsys package $Package|Set-Content -LiteralPath (Join-Path $runDirectory 'quest-debug.package.txt') -Encoding UTF8
    [IO.File]::WriteAllText((Join-Path $runDirectory 'quest-debug.startup-status.json'),$statusJson+"`n",[Text.UTF8Encoding]::new($false))
}
$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase=if($Debug){'DEBUG'}else{'START'};status='PASS';build_id=$status.build_id;package=$Package;control_credential='ready';device=[ordered]@{model=$model;device=$device};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state='APP_PROCESS_RUNNING'}
$reportPath=Join-Path $runDirectory 'quest-start.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false));$phaseComplete=$true
Write-Output "QUEST START: PASS build_id=$($status.build_id) report=$reportPath"
