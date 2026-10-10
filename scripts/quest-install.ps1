param(
    [string]$Apk='build/quest/PhantomQuest-diagnostic.apk',
    [string]$Package='dev.phantom.questprototype',
    [string]$HostFingerprint='', [string]$QuestSerial='',
    [string]$RobotId='', [string]$ControlKeyId='',
    [switch]$Repair,
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$Destination='results/quest/install',[string]$StateRoot=''
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
        $finished=(Get-Date).ToUniversalTime();$reason=if($_.Exception.Message-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'INSTALL_FAILED'}
        $failed=[ordered]@{schema_version=1;phase='INSTALL';component='QUEST';profile=if($manifest){$manifest.build_profile}else{'N_A'};status='FAIL';reason=$reason;build_id=if($manifest){$manifest.build_id}else{$null};detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state=$phaseTerminal;hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
        [System.IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("QUEST INSTALL: FAIL report=$reportPath; $($_.Exception.Message)")
    exit 1
}
. "$PSScriptRoot/../tools/toolchain.ps1"
. "$PSScriptRoot/pair-state.ps1"
. "$PSScriptRoot/install-common.ps1"
. "$PSScriptRoot/install-device.ps1"
$adb=Get-PhantomAdb
$apkPath=[System.IO.Path]::GetFullPath($Apk)
$manifestPath=$apkPath+'.build-manifest.json'
if(!(Test-Path -LiteralPath $apkPath -PathType Leaf) -or !(Test-Path -LiteralPath $manifestPath -PathType Leaf)){throw "APK or build manifest is missing: $apkPath"}
$manifest=Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw|ConvertFrom-Json
$apkHash=(Get-FileHash -LiteralPath $apkPath -Algorithm SHA256).Hash.ToLowerInvariant()
if($apkHash-ne$manifest.apk_sha256){throw 'APK hash does not match build manifest'}
if($manifest.schema_version-ne 8 -or $manifest.build_identity_schema-ne'PHANTOM-BUILD-V4' -or $manifest.component-ne'QUEST' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw 'Invalid Quest build manifest'}
$pair=Initialize-PhantomInstallPair -StateRoot $StateRoot -HostFingerprint $HostFingerprint -QuestSerial $QuestSerial -RobotId $RobotId -ControlKeyId $ControlKeyId -Repair:$Repair
$setupCredential=$Repair -or ($pair.State.PSObject.Properties.Name-contains'quest_credential_staged' -and !$pair.State.quest_credential_staged)
if($setupCredential -and $manifest.build_profile-ne'Diagnostic'){throw 'PROVISION_REQUIRED: first credential setup requires a Diagnostic APK'}
$serial=Get-PhantomQuestDevice $adb $StateRoot
$model=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.model') 8)-join'').Trim()
$device=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.device') 8)-join'').Trim()
if($model-ne'Quest 3' -or $device-ne'eureka'){throw "Physical Quest 3 required; found model=$model device=$device"}
$installStarted=(Get-Date).ToUniversalTime()
$phaseTerminal='APK_INSTALL_STARTED_RESULT_UNKNOWN'
$installResult=Invoke-PhantomProcess $adb @('-s',$serial,'install','-r','-g',$apkPath) $TimeoutSeconds 'INSTALL_TIMEOUT'
$installExitCode=$installResult.ExitCode
if($installExitCode-ne 0){throw "adb install failed with exit $installExitCode"}
$phaseTerminal='APK_INSTALLED_IDENTITY_UNVERIFIED'
$installDurationMs=[long]((Get-Date).ToUniversalTime()-$installStarted).TotalMilliseconds
$verifyStarted=(Get-Date).ToUniversalTime();$installedPath='';$visibilityDeadline=(Get-Date).AddSeconds(30)
while((Get-Date)-lt$visibilityDeadline)
{
    $candidate=(@(Invoke-PhantomAdb $adb $serial @('shell','pm','path',$Package) 3|Where-Object {$_-match'^package:'}|Select-Object -First 1)-join'').Trim()
    if($candidate-match'^package:'){$installedPath=$candidate;break}
    Start-Sleep -Milliseconds 250
}
if($installedPath-notmatch'^package:'){throw "Installed package was not found after 30 seconds: $Package"}
$installedApk=$installedPath.Substring(8)
$installedHash=(@(Invoke-PhantomAdb $adb $serial @('shell','toybox','sha256sum',$installedApk) 15)-join'').Trim().Split()[0].ToLowerInvariant()
if($installedHash-ne$apkHash){throw "Installed APK hash mismatch: expected=$apkHash actual=$installedHash"}
if($setupCredential){
    Invoke-PhantomQuestCredentialSetup -KeyFile $pair.Paths.ControlSecret -KeyId $pair.State.control_key_id -Package $Package -Serial $serial -StateRoot $StateRoot -Destination (Join-Path $Destination 'credential')
    $pair.State|Add-Member -NotePropertyName quest_credential_staged -NotePropertyValue $true -Force
    Write-PhantomPairState $pair.State $StateRoot
}
$verifyDurationMs=[long]((Get-Date).ToUniversalTime()-$verifyStarted).TotalMilliseconds
$phaseTerminal='APK_INSTALLED_EXACT_BYTES_APP_NOT_STARTED'
$finished=(Get-Date).ToUniversalTime()
$report=[ordered]@{schema_version=1;phase='INSTALL';component='QUEST';profile=$manifest.build_profile;status='PASS';reason='INSTALLED';build_id=$manifest.build_id;artifact_sha256=$apkHash;installed_artifact_sha256=$installedHash;package=$Package;device_class=[ordered]@{model=$model;device=$device};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;steps=@([ordered]@{step='adb-install';status='PASS';duration_ms=$installDurationMs},[ordered]@{step='package-visibility-and-installed-apk-hash';status='PASS';duration_ms=$verifyDurationMs});terminal_state='APK_INSTALLED_EXACT_BYTES_APP_NOT_STARTED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
$runDirectory=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $manifest.build_id
New-Item -ItemType Directory -Force -Path $runDirectory|Out-Null
$reportPath=Join-Path $runDirectory 'quest-install.json'
[System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 8)+"`n",[System.Text.UTF8Encoding]::new($false))
$phaseComplete=$true
Write-Output "QUEST INSTALL: PASS build_id=$($manifest.build_id) report=$reportPath"
