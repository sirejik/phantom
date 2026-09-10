<# Explicit one-time, idempotent provisioning of the designated Quest 3 + EV3 pair. #>
param(
    [ValidatePattern('^SHA256:[A-Za-z0-9+/]{43}$')][string]$HostFingerprint='',
    [ValidatePattern('^[A-Za-z0-9._-]{1,32}$')][string]$RobotId='phantom01',
    [ValidatePattern('^[A-Za-z0-9._-]{1,64}$')][string]$ControlKeyId='phantom01-control',
    [string]$BootstrapUser='robot',[string]$WifiSettingsFile='',[string]$WifiServiceId='',
    [string]$StateRoot='',[string]$Destination='results/pair/provision',[switch]$Repair,
    [switch]$RotateSshKey,[switch]$RotateControlSecret,[switch]$RepinHost
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/pair-state.ps1"
$paths=Get-PhantomPairPaths $StateRoot
$recordExisted=Test-Path -LiteralPath $paths.Record -PathType Leaf
$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$reportPath=Join-Path ([IO.Path]::GetFullPath($Destination)) 'provision.json'
function Write-PairProvisionResult([string]$Status,[string]$Reason,[string]$TerminalState,[string]$Detail='')
{
    $finished=(Get-Date).ToUniversalTime();New-Item -ItemType Directory -Force -Path (Split-Path -Parent $reportPath)|Out-Null
    $report=[ordered]@{schema_version=1;phase='PROVISION';component='PAIR';profile='N_A';status=$Status;reason=$Reason;build_id=$null;artifact_sha256=$null;detail=if($Detail){$Detail}else{$null};started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state=$TerminalState;hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
    [IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
}
trap
{
    if(!$phaseComplete){$reason=if($_.Exception.Message-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'PROVISION_FAILED'};Write-PairProvisionResult 'FAIL' $reason 'PAIR_STATE_UNCHANGED_OR_PARTIAL' $_.Exception.Message}
    [Console]::Error.WriteLine("PAIR PROVISION: FAIL report=$reportPath; $($_.Exception.Message)");exit 1
}

if(($RotateSshKey -or $RotateControlSecret -or $RepinHost) -and !$Repair){throw 'PROVISION_CORRUPT: rotation/repin requires explicit -Repair'}
if($recordExisted)
{
    if(!$Repair)
    {
        $existing=Read-PhantomPairState $StateRoot -RequirePrivateFiles
        if($HostFingerprint -and $HostFingerprint-ne$existing.State.ev3_host_key_fingerprint){throw 'HOST_KEY_MISMATCH: supplied EV3 fingerprint differs from the provisioned pair'}
        if($RobotId-ne$existing.State.robot_id -or $ControlKeyId-ne$existing.State.control_key_id){throw 'PROVISION_CORRUPT: supplied pair identity differs; use explicit -Repair'}
        if($WifiSettingsFile -or $WifiServiceId){throw 'PROVISION_CORRUPT: Wi-Fi provisioning changes require explicit -Repair'}
        Write-PairProvisionResult 'PASS' 'ALREADY_PROVISIONED' 'PAIR_READY_RUNTIME_NOT_STARTED';$phaseComplete=$true
        Write-Output "PROVISION: ALREADY_PROVISIONED robot_id=$($existing.State.robot_id) report=$reportPath"
        exit 0
    }
}
elseif((Test-Path -LiteralPath $paths.Root) -and @(Get-ChildItem -LiteralPath $paths.Root -Force -ErrorAction SilentlyContinue).Count -gt 0 -and !$Repair)
{throw 'PROVISION_CORRUPT: partial fixed-pair state exists; use explicit -Repair after inspection'}

if(!$HostFingerprint){throw 'PROVISION_REQUIRED: trusted EV3 host fingerprint is required for first provisioning/repair'}
New-Item -ItemType Directory -Force -Path $paths.SshDirectory,$paths.SecretDirectory|Out-Null

if($recordExisted -and !(Test-Path -LiteralPath $paths.SshKey -PathType Leaf) -and !$RotateSshKey){throw 'PROVISION_CORRUPT: deployment key is missing; explicit -Repair -RotateSshKey is required'}
if($RotateSshKey){Remove-Item -LiteralPath $paths.SshKey,($paths.SshKey+'.pub') -Force -ErrorAction SilentlyContinue}
if(!(Test-Path -LiteralPath $paths.SshKey -PathType Leaf))
{
    New-PhantomDeploymentKey $paths.SshKey
}
Set-PhantomPrivateAcl $paths.SshKey

if($recordExisted -and !(Test-Path -LiteralPath $paths.ControlSecret -PathType Leaf) -and !$RotateControlSecret){throw 'PROVISION_CORRUPT: CONTROL secret is missing; explicit -Repair -RotateControlSecret is required'}
if($RotateControlSecret){Remove-Item -LiteralPath $paths.ControlSecret -Force -ErrorAction SilentlyContinue}
if(!(Test-Path -LiteralPath $paths.ControlSecret -PathType Leaf))
{
    $bytes=New-Object byte[] 32
    $rng=[Security.Cryptography.RandomNumberGenerator]::Create()
    try{$rng.GetBytes($bytes);[IO.File]::WriteAllBytes($paths.ControlSecret,$bytes)}finally{$rng.Dispose();[Array]::Clear($bytes,0,$bytes.Length)}
}
Set-PhantomPrivateAcl $paths.ControlSecret

. "$PSScriptRoot/../tools/toolchain.ps1"
$adb=Get-PhantomAdb
$devices=@(Invoke-PhantomAdb $adb '' @('devices') 8|Select-Object -Skip 1|Where-Object{$_-match'\sdevice$'})
if($devices.Count-eq 0){throw 'QUEST_NOT_FOUND: no authorized Quest is connected'}
if($devices.Count-ne 1){throw 'AMBIGUOUS_DEVICE: first provisioning requires exactly one authorized ADB device'}
$serial=($devices[0]-split'\s+')[0]
$model=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.model') 8)-join'').Trim()
$device=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.device') 8)-join'').Trim()
if($model-ne'Quest 3' -or $device-ne'eureka'){throw 'QUEST_IDENTITY_MISMATCH: connected device is not the designated Quest 3 class'}

& "$PSScriptRoot/ev3-provision-maintenance.ps1" -HostFingerprint $HostFingerprint `
    -KeyPath $paths.SshKey -SshDirectory $paths.SshDirectory `
    -ControlKeyFile $paths.ControlSecret -BootstrapUser $BootstrapUser `
    -WifiSettingsFile $WifiSettingsFile -WifiServiceId $WifiServiceId `
    -RepinHost:$RepinHost -Repair:$Repair
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 provisioning failed'}
& "$PSScriptRoot/quest-provision-credential.ps1" -KeyFile $paths.ControlSecret -KeyId $ControlKeyId -Serial $serial
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: Quest credential provisioning failed'}

$record=[ordered]@{provision_schema_version=1;provision_status='complete';quest_adb_serial=$serial;
    ev3_hostname='ev3dev.local';ev3_host_key_fingerprint=$HostFingerprint;robot_id=$RobotId;control_key_id=$ControlKeyId}
Write-PhantomPairState $record $StateRoot
Write-PairProvisionResult 'PASS' 'PROVISIONED' 'PAIR_READY_RUNTIME_NOT_STARTED';$phaseComplete=$true
Write-Output "PROVISION: PASS component=PAIR robot_id=$RobotId; private identity stored outside repository; report=$reportPath"
