param(
    [string]$Apk="build/quest/PhantomQuest-diagnostic.apk",
    [string]$Package="dev.phantom.questprototype",
    [string]$PreInstallReport="results/pre-install/report.json",
    [string]$Destination="results/quest/device-auto",
    [string]$InstallEvidence="results/quest/install",
    [string]$StartEvidence="results/quest/start",
    [int]$ReportTimeoutSeconds=35
)
$ErrorActionPreference="Stop"
$startedAt=(Get-Date).ToUniversalTime().ToString('o')
$phaseComplete=$false
$phaseTerminal="PREVIOUS_APP_STATE_UNCHANGED"
$manifest=$null
$runDirectory=$null
$reportPath=$null
$adb=$null
$serial=$null
trap
{
    if(!$phaseComplete)
    {
        if($adb -and $serial)
        {
            try{& $adb -s $serial shell am force-stop $Package|Out-Null;$phaseTerminal="APP_FORCE_STOP_REQUESTED"}catch{}
        }
        $failedId=if($manifest -and $manifest.build_id){$manifest.build_id}else{"failed-"+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        if(!$runDirectory){$runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $failedId;New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null}
        $reportPath=Join-Path $runDirectory "quest-device-auto.json"
        $failed=[ordered]@{schema_version=2;gate="QUEST DEVICE AUTO";status="FAIL";build_id=$(if($manifest){$manifest.build_id}else{$null});detail=$_.Exception.Message;started_at=$startedAt;finished_at=(Get-Date).ToUniversalTime().ToString('o');terminal_state=$phaseTerminal}
        [System.IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("QUEST DEVICE AUTO: FAIL report=$reportPath; $($_.Exception.Message)")
    exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1"
$adb=Get-PhantomAdb
$apkPath=[System.IO.Path]::GetFullPath($Apk)
$manifestPath=$apkPath+".build-manifest.json"
if(!(Test-Path -LiteralPath $apkPath) -or !(Test-Path -LiteralPath $manifestPath)){throw "APK or build manifest is missing: $apkPath"}
$manifest=Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw|ConvertFrom-Json
$actualApkHash=(Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($actualApkHash-ne$manifest.apk_sha256){throw "APK hash does not match build manifest"}
$preInstallPath=[System.IO.Path]::GetFullPath($PreInstallReport)
if(!(Test-Path -LiteralPath $preInstallPath)){throw "PRE-INSTALL report is missing"}
$preInstall=Get-Content -LiteralPath $preInstallPath -Encoding UTF8 -Raw|ConvertFrom-Json
$artifactMatches=@($preInstall.artifacts|Where-Object {$_.sha256-eq$actualApkHash})
$preInstallMatch=$preInstall.gate-eq"PRE-INSTALL AUTO" -and $preInstall.status-eq"PASS" -and
    $preInstall.install_authorized-eq$true -and $preInstall.worktree_dirty-eq$false -and
    $preInstall.build_ids-contains$manifest.build_id -and $preInstall.git_commit-eq$manifest.git_commit -and
    $preInstall.specification_sha256-eq$manifest.specification_sha256 -and
    $preInstall.protocol_schema_hash-eq$manifest.protocol_schema_hash -and $artifactMatches.Count-eq 1
if(!$preInstallMatch){throw "A matching clean Quest PRE-INSTALL PASS with exact artifact and contract identity is required before DEVICE AUTO"}

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

$installPath=Join-Path ([System.IO.Path]::GetFullPath($InstallEvidence)) "$($manifest.build_id)/quest-install.json"
$startPath=Join-Path ([System.IO.Path]::GetFullPath($StartEvidence)) "$($manifest.build_id)/quest-start.json"
if(!(Test-Path -LiteralPath $installPath -PathType Leaf)){throw "Matching Quest INSTALL report is missing: $installPath"}
if(!(Test-Path -LiteralPath $startPath -PathType Leaf)){throw "Matching Quest START report is missing: $startPath"}
$install=Get-Content -LiteralPath $installPath -Encoding UTF8 -Raw|ConvertFrom-Json
$start=Get-Content -LiteralPath $startPath -Encoding UTF8 -Raw|ConvertFrom-Json
$installMatch=$install.phase-eq"INSTALL" -and $install.status-eq"PASS" -and $install.build_id-eq$manifest.build_id -and $install.apk_sha256-eq$actualApkHash -and $install.package-eq$Package -and $install.device.anonymized_id-eq$deviceIdHash
$startMatch=$start.phase-eq"START" -and $start.status-eq"PASS" -and $start.build_id-eq$manifest.build_id -and $start.apk_sha256-eq$actualApkHash -and $start.package-eq$Package -and $start.device.anonymized_id-eq$deviceIdHash
if(!$installMatch -or !$startMatch){throw "Matching Quest INSTALL and START PASS are required before DEVICE AUTO"}

New-Item -ItemType Directory -Force -Path $Destination|Out-Null
$safeBuildId=$manifest.build_id-replace'[^A-Za-z0-9._-]','_'
$runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $safeBuildId
New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
$remoteReport="/sdcard/Android/data/$Package/files/quest-device-auto.json"

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
    & $adb -s $serial shell input keyevent KEYCODE_WAKEUP|Out-Null
    & $adb -s $serial shell input keyevent 82|Out-Null
    $start=@(& $adb -s $serial shell am start -n $activity)
    if($LASTEXITCODE-ne 0 -or ($start-join"`n")-match"Error:"){throw "$phase launch failed: $($start-join' ')"}
    $script:phaseTerminal="APP_RUNNING_DEVICE_CASE"
    $pidDeadline=(Get-Date).AddSeconds(15)
    $pidValue=""
    while((Get-Date)-lt$pidDeadline)
    {
        $pidValue=(@(& $adb -s $serial shell "pidof '$Package' 2>/dev/null || true")-join'').Trim()
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

$firstCaseStarted=(Get-Date).ToUniversalTime()
$firstLaunch=Start-QuestApp "first"
$deadline=(Get-Date).AddSeconds($ReportTimeoutSeconds)
while((Get-Date)-lt$deadline)
{
    $remoteListing=(@(& $adb -s $serial shell "if [ -f '$remoteReport' ]; then echo present; fi")-join'').Trim()
    if($remoteListing-eq'present') {break}
    Start-Sleep -Milliseconds 500
}
if((Get-Date)-ge$deadline)
{
    & $adb -s $serial logcat -d|Set-Content (Join-Path $runDirectory "first-launch.logcat.txt") -Encoding UTF8
    $powerState=(@(& $adb -s $serial shell dumpsys power|Select-String -Pattern 'mWakefulness=')-join'; ').Trim()
    throw "Quest DEVICE AUTO report timeout after $ReportTimeoutSeconds seconds; $powerState. The zero-interaction table-mode gate cannot continue."
}
& $adb -s $serial pull $remoteReport (Join-Path $runDirectory "app-report.json")|Out-Null
$firstLogcat=& $adb -s $serial logcat -d
$firstLogcat|Set-Content (Join-Path $runDirectory "first-launch.logcat.txt") -Encoding UTF8
$firstPid=(@(& $adb -s $serial shell "pidof '$Package' 2>/dev/null || true")-join'').Trim()
$firstDurationMs=[long]((Get-Date).ToUniversalTime()-$firstCaseStarted).TotalMilliseconds

& $adb -s $serial shell am force-stop $Package
$phaseTerminal="APP_FORCE_STOPPED"
& $adb -s $serial logcat -c
$secondCaseStarted=(Get-Date).ToUniversalTime()
$secondLaunch=Start-QuestApp "relaunch"
Start-Sleep -Seconds 8
$secondPid=(@(& $adb -s $serial shell "pidof '$Package' 2>/dev/null || true")-join'').Trim()
$secondLogcat=& $adb -s $serial logcat -d
$secondDurationMs=[long]((Get-Date).ToUniversalTime()-$secondCaseStarted).TotalMilliseconds
$secondLogcat|Set-Content (Join-Path $runDirectory "relaunch.logcat.txt") -Encoding UTF8
& $adb -s $serial shell am force-stop $Package

$appReport=Get-Content (Join-Path $runDirectory "app-report.json") -Encoding UTF8 -Raw|ConvertFrom-Json
$crashPattern='FATAL EXCEPTION|Fatal signal|CRASH:|ANR in dev\.phantom\.questprototype'
$firstCrash=($firstLogcat-join"`n")-match$crashPattern
$secondCrash=($secondLogcat-join"`n")-match$crashPattern
$identityMatch=$appReport.build_id-eq$manifest.build_id
$hostChecks=@(
    [ordered]@{test_id="pre-install-admission";status="PASS";detail="matching Quest PRE-INSTALL PASS";duration_ms=0},
    [ordered]@{test_id="install-admission";status="PASS";detail="matching Quest INSTALL PASS; sha256=$actualApkHash";duration_ms=0},
    [ordered]@{test_id="start-admission";status="PASS";detail="matching Quest START PASS";duration_ms=0},
    [ordered]@{test_id="build-id";status=$(if($identityMatch){"PASS"}else{"FAIL"});detail="expected=$($manifest.build_id); actual=$($appReport.build_id)";duration_ms=0},
    [ordered]@{test_id="first-launch";status=$(if($firstPid-and!$firstCrash){"PASS"}else{"FAIL"});detail="pid_present=$([bool]$firstPid); crash=$firstCrash";duration_ms=$firstDurationMs},
    [ordered]@{test_id="force-stop-relaunch";status=$(if($secondPid-and!$secondCrash){"PASS"}else{"FAIL"});detail="pid_present=$([bool]$secondPid); crash=$secondCrash";duration_ms=$secondDurationMs}
)
$hostFailed=@($hostChecks|Where-Object {$_.status -eq "FAIL"}).Count -gt 0
$status=if($appReport.status-eq"PASS"-and!$hostFailed){"PASS"}else{"FAIL"}
$finishedAt=(Get-Date).ToUniversalTime()
$report=[ordered]@{
    schema_version=2;gate="QUEST DEVICE AUTO";status=$status;execution_mode="ZERO_INTERACTION_TABLE_SAFE";test_case_limit_seconds=60
    build_id=$manifest.build_id;apk_sha256=$actualApkHash;build_manifest=$manifest
    device=[ordered]@{model=$model;device=$device;anonymized_id=$deviceIdHash;horizon_display_build=$displayBuild;runtime_incremental=$runtimeVersion;fingerprint=$fingerprint}
    started_at=$startedAt;finished_at=$finishedAt.ToString('o');duration_ms=[long]($finishedAt-[datetime]$startedAt).TotalMilliseconds;app_report=$appReport;host_checks=$hostChecks
    log_files=@("first-launch.logcat.txt","relaunch.logcat.txt")
}
$reportPath=Join-Path $runDirectory "quest-device-auto.json"
[System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 12)+"`n",[System.Text.UTF8Encoding]::new($false))
$appChecks=@{};foreach($check in $appReport.checks){$appChecks[$check.test_id]=$check}
$p0CapabilityIds=@(
    "embedded-build-identity","config-load-and-hash","local-floor",
    "permission-hand-tracking","permission-body-tracking","permission-scene","permission-anchor",
    "passthrough-configuration","mruk-qr-configuration","multimodal-configuration",
    "hand-adapter","controller-adapter","grasp-adapter","haptic-command-path",
    "provider-presence","provider-configuration","body-multimodal-compatibility",
    "motor-authority-disabled","runtime-error-log"
)
if($manifest.build_profile-eq"Diagnostic"){$p0CapabilityIds+="diagnostic-synthetic-suite"}else{$p0CapabilityIds+="release-engineering-disabled"}
$p0ObservationIds=@("xr-session-active","xr-focus-active","live-right-wrist-observed","live-grasp-ready-observed","live-right-shoulder-observed","live-left-touch-observed","live-qr-observed")
$p0Checks=@()
foreach($id in $p0CapabilityIds+$p0ObservationIds)
{
    if($appChecks.ContainsKey($id)){$p0Checks+=[ordered]@{test_id=$id;status=$appChecks[$id].status;detail=$appChecks[$id].detail}}
    else{$p0Checks+=[ordered]@{test_id=$id;status="NOT_RUN";detail="check missing from app report"}}
}
$p0PrerequisiteFailed=$status-ne"PASS" -or @($p0Checks|Where-Object {$_.test_id -in $p0CapabilityIds -and $_.status -ne "PASS"}).Count -gt 0
$p0Status=if($p0PrerequisiteFailed){"FAIL"}else{"PASS"}
$p0Report=[ordered]@{
    schema_version=2;gate="P0 QUEST PLATFORM COMPATIBILITY AUTO";status=$p0Status;execution_mode="ZERO_INTERACTION_TABLE_SAFE"
    build_id=$manifest.build_id;apk_sha256=$actualApkHash
    device=$report.device
    platform_matrix=[ordered]@{
        unity=$manifest.unity_version;meta_xr_core=$manifest.meta_xr_core_version
        movement_sdk=$manifest.movement_sdk_version;body_tracking_provider=$manifest.body_tracking_provider
        body_provider_joint_set=$manifest.body_provider_joint_set;body_right_shoulder_api=$manifest.body_right_shoulder_api
        body_multimodal_compatibility=$manifest.body_multimodal_compatibility
        mruk=$manifest.mruk_version;openxr_plugin=$manifest.openxr_plugin_version
        meta_openxr=$manifest.meta_openxr_version;xr_hands=$manifest.xr_hands_version
    }
    feature_flags=[ordered]@{iobt="off";fbs="off";fmm="off";wmm="off";multimodal="required";passthrough="required"}
    device_auto_report="quest-device-auto.json";test_case_limit_seconds=60;duration_seconds=[math]::Round($appReport.duration_ms/1000,3)
    live_environment_evidence=[ordered]@{xr_session_active=$appReport.xr_session_active;xr_focus_active=$appReport.xr_focus_active;live_observation_available=$appReport.live_observation_available;blocking=$false}
    checks=$p0Checks
}
$p0Path=Join-Path $runDirectory "quest-p0-report.json"
$p0Report|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $p0Path -Encoding UTF8
$phaseComplete=$true
Write-Output "QUEST DEVICE AUTO: $status"
Write-Output "report=$reportPath"
Write-Output "P0 QUEST PLATFORM COMPATIBILITY AUTO: $p0Status"
Write-Output "p0_report=$p0Path"
foreach($check in $appReport.checks){Write-Output "$($check.status) app/$($check.test_id): $($check.detail)"}
foreach($check in $hostChecks){Write-Output "$($check.status) host/$($check.test_id): $($check.detail)"}
if($status-ne"PASS"){exit 1}
