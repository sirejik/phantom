param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedBuildId,
    [string]$Package='dev.phantom.questprototype',[ValidateRange(1,60)][int]$ReportTimeoutSeconds=35,
    [string]$Destination='results/quest/device-integration'
)
$ErrorActionPreference='Stop';$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$reportPath=$null
trap
{
    if(!$phaseComplete)
    {
        $runDirectory=Join-Path ([IO.Path]::GetFullPath($Destination)) $ExpectedBuildId;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
        $reportPath=Join-Path $runDirectory 'quest-device-integration-test.json';$failed=[ordered]@{schema_version=2;gate='QUEST DEVICE INTEGRATION TEST';status='FAIL';build_id=$ExpectedBuildId;detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=(Get-Date).ToUniversalTime().ToString('o');terminal_state='APP_FORCE_STOP_REQUESTED'}
        [IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("QUEST DEVICE INTEGRATION TEST: FAIL report=$reportPath; $($_.Exception.Message)");exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1";$adb=Get-PhantomAdb
$devices=@(& $adb devices|Select-Object -Skip 1|Where-Object {$_-match'\sdevice$'});if($devices.Count-ne 1){throw "Exactly one authorized ADB device is required; found $($devices.Count)"}
$serial=($devices[0]-split'\s+')[0];$model=(@(& $adb -s $serial shell getprop ro.product.model)-join'').Trim();$device=(@(& $adb -s $serial shell getprop ro.product.device)-join'').Trim();if($model-ne'Quest 3' -or $device-ne'eureka'){throw "Physical Quest 3 required; found model=$model device=$device"}
$activity=(@(& $adb -s $serial shell cmd package resolve-activity --brief $Package|Select-Object -Last 1)-join'').Trim();if(!$activity-or$activity-match'No activity'){throw "Installed package was not found: $Package"}
$remoteReport="/sdcard/Android/data/$Package/files/quest-device-integration-test.json";$runDirectory=Join-Path ([IO.Path]::GetFullPath($Destination)) $ExpectedBuildId;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
function Start-And-Wait([string]$label,[bool]$WaitForReport)
{
    & $adb -s $serial shell input keyevent KEYCODE_WAKEUP|Out-Null
    $launch=@(& $adb -s $serial shell am start -n $activity);if($LASTEXITCODE-ne 0-or($launch-join"`n")-match'Error:'){throw "$label launch failed"}
    $deadline=(Get-Date).AddSeconds($ReportTimeoutSeconds);$appPid=''
    while((Get-Date)-lt$deadline)
    {
        $appPid=(@(& $adb -s $serial shell "pidof '$Package' 2>/dev/null || true")-join'').Trim()
        $present=(!$WaitForReport)-or((@(& $adb -s $serial shell "test ! -f '$remoteReport' || echo present")-join'').Trim()-eq'present')
        if($appPid-and$present){return $appPid};Start-Sleep -Milliseconds 250
    }
    throw "$label did not become ready within $ReportTimeoutSeconds seconds"
}
& $adb -s $serial shell am force-stop $Package|Out-Null;& $adb -s $serial shell rm -f $remoteReport|Out-Null;& $adb -s $serial logcat -c|Out-Null
$firstPid=Start-And-Wait 'first' $true;& $adb -s $serial pull $remoteReport (Join-Path $runDirectory 'app-report.json')|Out-Null;$firstLog=@(& $adb -s $serial logcat -d)
& $adb -s $serial shell am force-stop $Package|Out-Null;& $adb -s $serial logcat -c|Out-Null;$secondPid=Start-And-Wait 'relaunch' $false;Start-Sleep -Seconds 2;$secondLog=@(& $adb -s $serial logcat -d);& $adb -s $serial shell am force-stop $Package|Out-Null
$appReport=Get-Content -LiteralPath (Join-Path $runDirectory 'app-report.json') -Raw -Encoding UTF8|ConvertFrom-Json
$crashPattern='FATAL EXCEPTION|Fatal signal|CRASH:|ANR in dev\.phantom\.questprototype';$checks=@(
    [ordered]@{test_id='installed-build-id';status=if($appReport.build_id-eq$ExpectedBuildId){'PASS'}else{'FAIL'};detail="expected=$ExpectedBuildId actual=$($appReport.build_id)"},
    [ordered]@{test_id='first-launch';status=if($firstPid-and!(($firstLog-join"`n")-match$crashPattern)){'PASS'}else{'FAIL'}},
    [ordered]@{test_id='force-stop-relaunch';status=if($secondPid-and!(($secondLog-join"`n")-match$crashPattern)){'PASS'}else{'FAIL'}})
$failed=@($checks|Where-Object status -eq'FAIL').Count-gt 0;$status=if(!$failed-and$appReport.status-eq'PASS'){'PASS'}else{'FAIL'};$finished=(Get-Date).ToUniversalTime()
$report=[ordered]@{schema_version=2;gate='QUEST DEVICE INTEGRATION TEST';status=$status;build_id=$ExpectedBuildId;device=[ordered]@{model=$model;device=$device};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;app_report=$appReport;host_checks=$checks;terminal_state='APP_FORCE_STOPPED'}
$reportPath=Join-Path $runDirectory 'quest-device-integration-test.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 12)+"`n",[Text.UTF8Encoding]::new($false));$phaseComplete=$true
Write-Output "QUEST DEVICE INTEGRATION TEST: $status report=$reportPath";if($status-ne'PASS'){exit 1}
