param(
    [string]$Apk='build/quest/PhantomQuest-diagnostic.apk',
    [string]$Package='dev.phantom.questprototype',
    [ValidateRange(1,60)][int]$TimeoutSeconds=15,
    [string]$InstallEvidence='results/quest/install',
    [string]$Destination='results/quest/start'
)
$ErrorActionPreference='Stop'
$started=(Get-Date).ToUniversalTime()
$phaseComplete=$false
$phaseTerminal='PREVIOUS_APP_STATE_UNCHANGED'
$manifest=$null
$reportPath=$null
trap
{
    if(!$phaseComplete)
    {
        $failedId=if($manifest -and $manifest.build_id){$manifest.build_id}else{'failed-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        $runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $failedId
        New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
        $reportPath=Join-Path $runDirectory 'quest-start.json'
        $failed=[ordered]@{schema_version=1;phase='START';status='FAIL';build_id=if($manifest){$manifest.build_id}else{$null};detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=(Get-Date).ToUniversalTime().ToString('o');terminal_state=$phaseTerminal}
        [System.IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("QUEST START: FAIL report=$reportPath; $($_.Exception.Message)")
    exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1"
$adb=Get-PhantomAdb
$apkPath=[System.IO.Path]::GetFullPath($Apk)
$manifest=Get-Content -LiteralPath ($apkPath+'.build-manifest.json') -Encoding UTF8 -Raw|ConvertFrom-Json
$apkHash=(Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($apkHash-ne$manifest.apk_sha256){throw 'APK hash does not match build manifest'}
$installPath=Join-Path ([System.IO.Path]::GetFullPath($InstallEvidence)) "$($manifest.build_id)/quest-install.json"
if(!(Test-Path -LiteralPath $installPath -PathType Leaf)){throw "Matching Quest INSTALL report is missing: $installPath"}
$install=Get-Content -LiteralPath $installPath -Encoding UTF8 -Raw|ConvertFrom-Json
if($install.phase-ne'INSTALL' -or $install.status-ne'PASS' -or $install.build_id-ne$manifest.build_id -or $install.apk_sha256-ne$manifest.apk_sha256 -or $install.package-ne$Package){throw 'Matching Quest INSTALL PASS is required'}
$devices=@(& $adb devices|Select-Object -Skip 1|Where-Object {$_-match'\sdevice$'})
if($devices.Count-ne 1){throw "Exactly one authorized ADB device is required; found $($devices.Count)"}
$serial=($devices[0]-split'\s+')[0]
$model=(@(& $adb -s $serial shell getprop ro.product.model)-join'').Trim()
$device=(@(& $adb -s $serial shell getprop ro.product.device)-join'').Trim()
if($model-ne'Quest 3' -or $device-ne'eureka'){throw "Physical Quest 3 required; found model=$model device=$device"}
$sha=[System.Security.Cryptography.SHA256]::Create()
try{$deviceIdHash=([BitConverter]::ToString($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($serial)))).Replace('-','').ToLowerInvariant().Substring(0,16)}finally{$sha.Dispose()}
if($install.device.anonymized_id-ne$deviceIdHash){throw 'Quest START device does not match INSTALL evidence'}
$activity=(@(& $adb -s $serial shell cmd package resolve-activity --brief $Package)|Select-Object -Last 1)-join''
$activity=$activity.Trim()
if(!$activity -or $activity-match'No activity'){throw "Launch activity was not resolved for $Package"}
$launchStarted=(Get-Date).ToUniversalTime()
& $adb -s $serial shell input keyevent KEYCODE_WAKEUP|Out-Null
& $adb -s $serial shell input keyevent 82|Out-Null
$phaseTerminal='APP_LAUNCH_REQUESTED_READINESS_UNVERIFIED'
$launch=@(& $adb -s $serial shell am start -n $activity)
if($LASTEXITCODE-ne 0 -or ($launch-join"`n")-match'Error:'){throw "Quest START failed: $($launch-join' ')"}
$deadline=(Get-Date).AddSeconds($TimeoutSeconds)
$pid=''
while((Get-Date)-lt$deadline)
{
    $pid=(@(& $adb -s $serial shell "pidof '$Package' 2>/dev/null || true")-join'').Trim()
    if($pid){break}
    Start-Sleep -Milliseconds 250
}
if(!$pid){throw "Quest START did not create a process within $TimeoutSeconds seconds"}
$finished=(Get-Date).ToUniversalTime()
$report=[ordered]@{schema_version=1;phase='START';status='PASS';build_id=$manifest.build_id;apk_sha256=$manifest.apk_sha256;package=$Package;device=[ordered]@{model=$model;device=$device;anonymized_id=$deviceIdHash};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;steps=@([ordered]@{step='app-process-readiness';status='PASS';duration_ms=[long]($finished-$launchStarted).TotalMilliseconds;deadline_seconds=$TimeoutSeconds});terminal_state='APP_PROCESS_RUNNING'}
$runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $manifest.build_id
New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
$reportPath=Join-Path $runDirectory 'quest-start.json'
[System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 6)+"`n",[System.Text.UTF8Encoding]::new($false))
$phaseComplete=$true
Write-Output "QUEST START: PASS build_id=$($manifest.build_id) report=$reportPath"
