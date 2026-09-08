param(
    [string]$Apk='build/quest/PhantomQuest-diagnostic.apk',
    [string]$Package='dev.phantom.questprototype',
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$Destination='results/quest/install'
)
$ErrorActionPreference='Stop'
$started=(Get-Date).ToUniversalTime()
$phaseComplete=$false
$phaseTerminal='PREVIOUS_INSTALLATION_UNCHANGED'
$manifest=$null
$reportPath=$null
trap
{
    if(!$phaseComplete)
    {
        $failedId=if($manifest -and $manifest.build_id){$manifest.build_id}else{'failed-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        $runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $failedId
        New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
        $reportPath=Join-Path $runDirectory 'quest-install.json'
        $failed=[ordered]@{schema_version=1;phase='INSTALL';status='FAIL';build_id=if($manifest){$manifest.build_id}else{$null};detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=(Get-Date).ToUniversalTime().ToString('o');terminal_state=$phaseTerminal}
        [System.IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("QUEST INSTALL: FAIL report=$reportPath; $($_.Exception.Message)")
    exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1"
$adb=Get-PhantomAdb
$apkPath=[System.IO.Path]::GetFullPath($Apk)
$manifestPath=$apkPath+'.build-manifest.json'
if(!(Test-Path -LiteralPath $apkPath -PathType Leaf) -or !(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw "APK or build manifest is missing: $apkPath"}
$manifest=Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw|ConvertFrom-Json
$apkHash=(Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($apkHash-ne$manifest.apk_sha256){throw 'APK hash does not match build manifest'}
if($manifest.schema_version-ne 6 -or $manifest.build_identity_schema-ne'PHANTOM-BUILD-V2' -or $manifest.component-ne'QUEST' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw 'Invalid Quest build manifest'}
$devices=@(& $adb devices|Select-Object -Skip 1|Where-Object {$_-match'\sdevice$'})
if($devices.Count-ne 1){throw "Exactly one authorized ADB device is required; found $($devices.Count)"}
$serial=($devices[0]-split'\s+')[0]
$model=(@(& $adb -s $serial shell getprop ro.product.model)-join'').Trim()
$device=(@(& $adb -s $serial shell getprop ro.product.device)-join'').Trim()
if($model-ne'Quest 3' -or $device-ne'eureka'){throw "Physical Quest 3 required; found model=$model device=$device"}
$sha=[System.Security.Cryptography.SHA256]::Create()
try{$deviceIdHash=([BitConverter]::ToString($sha.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($serial)))).Replace('-','').ToLowerInvariant().Substring(0,16)}finally{$sha.Dispose()}
$installStarted=(Get-Date).ToUniversalTime()
$phaseTerminal='APK_INSTALL_STARTED_RESULT_UNKNOWN'
$installInfo=[System.Diagnostics.ProcessStartInfo]::new()
$installInfo.FileName=$adb
$installInfo.Arguments='-s "{0}" install -r -g "{1}"' -f $serial,$apkPath
$installInfo.UseShellExecute=$false
$installProcess=[System.Diagnostics.Process]::Start($installInfo)
$completed=$installProcess.WaitForExit($TimeoutSeconds*1000)
if(!$completed)
{
    $installProcess.Kill()
    $installProcess.WaitForExit()
    throw "adb install exceeded ${TimeoutSeconds}s deadline"
}
$installProcess.WaitForExit()
$installExitCode=$installProcess.ExitCode
if($installExitCode-ne 0){throw "adb install failed with exit $installExitCode"}
$phaseTerminal='APK_INSTALLED_IDENTITY_UNVERIFIED'
$installDurationMs=[long]((Get-Date).ToUniversalTime()-$installStarted).TotalMilliseconds
$installedPath=(@(& $adb -s $serial shell pm path $Package|Where-Object {$_-match'^package:'}|Select-Object -First 1)-join'').Trim()
if($LASTEXITCODE-ne 0 -or $installedPath-notmatch'^package:'){throw "Installed package was not found: $Package"}
$installedApk=$installedPath.Substring(8)
$installedHash=(@(& $adb -s $serial shell toybox sha256sum $installedApk)-join'').Trim().Split()[0].ToLowerInvariant()
if($LASTEXITCODE-ne 0 -or $installedHash-ne$apkHash){throw "Installed APK hash mismatch: expected=$apkHash actual=$installedHash"}
$phaseTerminal='APK_INSTALLED_EXACT_BYTES_APP_NOT_STARTED'
$finished=(Get-Date).ToUniversalTime()
$report=[ordered]@{schema_version=1;phase='INSTALL';status='PASS';build_id=$manifest.build_id;apk_sha256=$apkHash;installed_apk_sha256=$installedHash;package=$Package;device=[ordered]@{model=$model;device=$device;anonymized_id=$deviceIdHash};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;steps=@([ordered]@{step='adb-install';status='PASS';duration_ms=$installDurationMs},[ordered]@{step='installed-apk-hash';status='PASS';duration_ms=0});terminal_state='APK_INSTALLED_EXACT_BYTES_APP_NOT_STARTED'}
$runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $manifest.build_id
New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
$reportPath=Join-Path $runDirectory 'quest-install.json'
[System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
$phaseComplete=$true
Write-Output "QUEST INSTALL: PASS build_id=$($manifest.build_id) report=$reportPath"
