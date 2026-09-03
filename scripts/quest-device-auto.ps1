param(
    [string]$Apk="build/quest/PhantomQuest-diagnostic.apk",
    [string]$Package="dev.phantom.questprototype",
    [string]$Destination="results/quest/device-auto",
    [int]$ReportTimeoutSeconds=35
)
$ErrorActionPreference="Stop"
$startedAt=(Get-Date).ToUniversalTime().ToString('o')
$adb="C:\Program Files\Unity\Hub\Editor\6000.3.22f1\Editor\Data\PlaybackEngines\AndroidPlayer\SDK\platform-tools\adb.exe"
if(!(Test-Path -LiteralPath $adb)){throw "Bundled adb not found: $adb"}
$apkPath=[System.IO.Path]::GetFullPath($Apk)
$manifestPath=$apkPath+".build-manifest.json"
if(!(Test-Path -LiteralPath $apkPath) -or !(Test-Path -LiteralPath $manifestPath)){throw "APK or build manifest is missing: $apkPath"}
$manifest=Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw|ConvertFrom-Json
$actualApkHash=(Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($actualApkHash-ne$manifest.apk_sha256){throw "APK hash does not match build manifest"}
$preInstallPath=[System.IO.Path]::GetFullPath("results/pre-install/report.json")
if(!(Test-Path -LiteralPath $preInstallPath)){throw "PRE-INSTALL report is missing"}
$preInstall=Get-Content -LiteralPath $preInstallPath -Encoding UTF8 -Raw|ConvertFrom-Json
if($preInstall.status-ne"PASS" -or $preInstall.build_ids-notcontains$manifest.build_id){throw "A matching PRE-INSTALL PASS is required before installation"}

$devices=@(& $adb devices|Select-Object -Skip 1|Where-Object {$_-match "\sdevice$"})
if($devices.Count-ne 1){throw "Exactly one authorized ADB device is required; found $($devices.Count)"}
$serial=($devices[0]-split "\s+")[0]
$model=(@(& $adb -s $serial shell getprop ro.product.model)-join'').Trim()
$device=(@(& $adb -s $serial shell getprop ro.product.device)-join'').Trim()
if($model-ne"Quest 3" -or $device-ne"eureka"){throw "Physical Quest 3 required; found model=$model device=$device"}
$fingerprint=(@(& $adb -s $serial shell getprop ro.build.fingerprint)-join'').Trim()
$displayBuild=(@(& $adb -s $serial shell getprop ro.build.display.id)-join'').Trim()
$runtimeVersion=(@(& $adb -s $serial shell getprop ro.build.version.incremental)-join'').Trim()
$serialBytes=[System.Text.Encoding]::UTF8.GetBytes($serial)
$sha=[System.Security.Cryptography.SHA256]::Create()
try{$deviceIdHash=([BitConverter]::ToString($sha.ComputeHash($serialBytes))).Replace("-","").ToLowerInvariant().Substring(0,16)}finally{$sha.Dispose()}

New-Item -ItemType Directory -Force -Path $Destination|Out-Null
$safeBuildId=$manifest.build_id-replace'[^A-Za-z0-9._-]','_'
$runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $safeBuildId
New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
$remoteReport="/sdcard/Android/data/$Package/files/quest-device-auto.json"

& $adb -s $serial install -r $apkPath
if($LASTEXITCODE-ne 0){throw "adb install failed"}
& $adb -s $serial shell am force-stop $Package
& $adb -s $serial shell rm -f $remoteReport
& $adb -s $serial logcat -c
$activity=(@(& $adb -s $serial shell cmd package resolve-activity --brief $Package)|Select-Object -Last 1)
$activity=(@($activity)-join'').Trim()
if(!$activity -or $activity-match"No activity"){throw "Launch activity was not resolved for $Package"}

function Start-QuestApp([string]$phase)
{
    # `am start -W` can wait indefinitely for a volumetric window while an
    # unattended HMD is asleep. Wake is harmless and output-free; readiness is
    # established by a separately bounded PID poll and by the in-app report.
    & $adb -s $serial shell input keyevent 224|Out-Null
    $start=@(& $adb -s $serial shell am start -n $activity)
    if($LASTEXITCODE-ne 0 -or ($start-join"`n")-match"Error:"){throw "$phase launch failed: $($start-join' ')"}
    $pidDeadline=(Get-Date).AddSeconds(15)
    $pidValue=""
    while((Get-Date)-lt$pidDeadline)
    {
        $pidValue=(@(& $adb -s $serial shell pidof $Package 2>$null)-join'').Trim()
        if($pidValue){break}
        Start-Sleep -Milliseconds 250
    }
    if(!$pidValue)
    {
        $powerState=(@(& $adb -s $serial shell dumpsys power|Select-String -Pattern 'mWakefulness=')-join'; ').Trim()
        throw "$phase launch did not create a process within 15 seconds; $powerState"
    }
    return $start
}

$firstLaunch=Start-QuestApp "first"
$deadline=(Get-Date).AddSeconds($ReportTimeoutSeconds)
while((Get-Date)-lt$deadline)
{
    $remoteListing=@(& $adb -s $serial shell ls $remoteReport 2>$null)
    if($LASTEXITCODE-eq 0 -and (@($remoteListing)-join'').Trim()) {break}
    Start-Sleep -Milliseconds 500
}
if((Get-Date)-ge$deadline)
{
    & $adb -s $serial logcat -d|Set-Content (Join-Path $runDirectory "first-launch.logcat.txt") -Encoding UTF8
    $powerState=(@(& $adb -s $serial shell dumpsys power|Select-String -Pattern 'mWakefulness=')-join'; ').Trim()
    throw "Quest DEVICE AUTO report timeout after $ReportTimeoutSeconds seconds; $powerState. Put on/wake the HMD and retry."
}
& $adb -s $serial pull $remoteReport (Join-Path $runDirectory "app-report.json")|Out-Null
$firstLogcat=& $adb -s $serial logcat -d
$firstLogcat|Set-Content (Join-Path $runDirectory "first-launch.logcat.txt") -Encoding UTF8
$firstPid=(@(& $adb -s $serial shell pidof $Package 2>$null)-join'').Trim()

& $adb -s $serial shell am force-stop $Package
& $adb -s $serial logcat -c
$secondLaunch=Start-QuestApp "relaunch"
Start-Sleep -Seconds 8
$secondPid=(@(& $adb -s $serial shell pidof $Package 2>$null)-join'').Trim()
$secondLogcat=& $adb -s $serial logcat -d
$secondLogcat|Set-Content (Join-Path $runDirectory "relaunch.logcat.txt") -Encoding UTF8
& $adb -s $serial shell am force-stop $Package

$appReport=Get-Content (Join-Path $runDirectory "app-report.json") -Encoding UTF8 -Raw|ConvertFrom-Json
$crashPattern='FATAL EXCEPTION|Fatal signal|CRASH:|ANR in dev\.phantom\.questprototype'
$firstCrash=($firstLogcat-join"`n")-match$crashPattern
$secondCrash=($secondLogcat-join"`n")-match$crashPattern
$identityMatch=$appReport.build_id-eq$manifest.build_id
$hostChecks=@(
    [ordered]@{test_id="pre-install-admission";status="PASS";detail="matching PRE-INSTALL PASS"},
    [ordered]@{test_id="apk-install";status="PASS";detail="adb install -r succeeded; sha256=$actualApkHash"},
    [ordered]@{test_id="build-id";status=$(if($identityMatch){"PASS"}else{"FAIL"});detail="expected=$($manifest.build_id); actual=$($appReport.build_id)"},
    [ordered]@{test_id="first-launch";status=$(if($firstPid-and!$firstCrash){"PASS"}else{"FAIL"});detail="pid_present=$([bool]$firstPid); crash=$firstCrash"},
    [ordered]@{test_id="force-stop-relaunch";status=$(if($secondPid-and!$secondCrash){"PASS"}else{"FAIL"});detail="pid_present=$([bool]$secondPid); crash=$secondCrash"}
)
$hostFailed=@($hostChecks|Where-Object status -eq"FAIL").Count-gt 0
$status=if($appReport.status-eq"PASS"-and!$hostFailed){"PASS"}else{"FAIL"}
$report=[ordered]@{
    schema_version=1;gate="QUEST DEVICE AUTO";status=$status
    build_id=$manifest.build_id;apk_sha256=$actualApkHash;build_manifest=$manifest
    device=[ordered]@{model=$model;device=$device;anonymized_id=$deviceIdHash;horizon_display_build=$displayBuild;runtime_incremental=$runtimeVersion;fingerprint=$fingerprint}
    started_at=$startedAt;finished_at=(Get-Date).ToUniversalTime().ToString('o');app_report=$appReport;host_checks=$hostChecks
    log_files=@("first-launch.logcat.txt","relaunch.logcat.txt")
}
$reportPath=Join-Path $runDirectory "quest-device-auto.json"
$report|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $reportPath -Encoding UTF8
$appChecks=@{};foreach($check in $appReport.checks){$appChecks[$check.test_id]=$check}
$p0CapabilityIds=@("passthrough-capability","mruk-qr-capability","multimodal-capability","body-provider-capability")
$p0ObservationIds=@("p0-right-wrist-observed","p0-grasp-ready-observed","p0-right-shoulder-observed","p0-left-touch-observed","p0-qr-observed")
$p0Checks=@()
foreach($id in $p0CapabilityIds+$p0ObservationIds)
{
    if($appChecks.ContainsKey($id)){$p0Checks+=[ordered]@{test_id=$id;status=$appChecks[$id].status;detail=$appChecks[$id].detail}}
    else{$p0Checks+=[ordered]@{test_id=$id;status="NOT_RUN";detail="check missing from app report"}}
}
$p0Checks+=@(
    [ordered]@{test_id="left-touch-haptics-confirmed";status="NOT_RUN";detail="requires confirmation in headset"},
    [ordered]@{test_id="pause-resume-hmd-multimodal";status="NOT_RUN";detail="requires guided headset interaction"},
    [ordered]@{test_id="continuous-simultaneous-30-min";status="NOT_RUN";detail="not started unless all prerequisite capabilities pass"}
)
$p0PrerequisiteFailed=@($p0Checks|Where-Object {$_.test_id-in$p0CapabilityIds -and $_.status-eq"FAIL"}).Count-gt 0
$p0Status=if($p0PrerequisiteFailed){"FAIL"}else{"NOT_RUN"}
$p0Report=[ordered]@{
    schema_version=1;gate="P0 QUEST PLATFORM FEASIBILITY";status=$p0Status
    build_id=$manifest.build_id;apk_sha256=$actualApkHash
    device=$report.device
    platform_matrix=[ordered]@{
        unity=$manifest.unity_version;meta_xr_core=$manifest.meta_xr_core_version
        movement_sdk=$manifest.movement_sdk_version;body_tracking_provider=$manifest.body_tracking_provider
        mruk=$manifest.mruk_version;openxr_plugin=$manifest.openxr_plugin_version
        meta_openxr=$manifest.meta_openxr_version;xr_hands=$manifest.xr_hands_version
    }
    feature_flags=[ordered]@{iobt="off";fbs="off";fmm="off";wmm="off";multimodal="required";passthrough="required"}
    device_auto_report="quest-device-auto.json";duration_seconds=[math]::Round($appReport.duration_ms/1000,3);checks=$p0Checks
}
$p0Path=Join-Path $runDirectory "quest-p0-report.json"
$p0Report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $p0Path -Encoding UTF8
Write-Output "QUEST DEVICE AUTO: $status"
Write-Output "report=$reportPath"
Write-Output "P0 QUEST PLATFORM FEASIBILITY: $p0Status"
Write-Output "p0_report=$p0Path"
foreach($check in $appReport.checks){Write-Output "$($check.status) app/$($check.test_id): $($check.detail)"}
foreach($check in $hostChecks){Write-Output "$($check.status) host/$($check.test_id): $($check.detail)"}
if($status-ne"PASS"){exit 1}
