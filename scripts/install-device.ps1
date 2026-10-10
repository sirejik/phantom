# Internal device operations called by INSTALL; no standalone setup/transfer commands.

function Invoke-PhantomEv3Setup {
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^SHA256:[A-Za-z0-9+/]{43}$')][string]$HostFingerprint,
    [string]$User='root',[string]$BootstrapUser='robot',
    [Parameter(Mandatory=$true)][string]$KeyPath,
    [Parameter(Mandatory=$true)][string]$SshDirectory,
    [Parameter(Mandatory=$true)][string]$ControlKeyFile,
    [ValidateSet('any','inet','inet6')][string]$AddressFamily='any',
    [ValidateRange(5,30)][int]$ScanTimeoutSeconds=8,
    [string]$WifiSettingsFile='',[string]$WifiServiceId='',
    [string]$Destination='results/ev3/provision',[switch]$RepinHost,[switch]$Repair
)
$ErrorActionPreference='Stop'
$started=(Get-Date).ToUniversalTime()
$target='ev3dev.local'
$repository=Split-Path -Parent $PSScriptRoot
$sshDirectoryPath=[IO.Path]::GetFullPath($SshDirectory)
$keyPathFull=[IO.Path]::GetFullPath($KeyPath)
$controlPath=[IO.Path]::GetFullPath($ControlKeyFile)
$knownHostsPath=Join-Path $sshDirectoryPath 'known_hosts'
$configPath=Join-Path $sshDirectoryPath 'config'

foreach($required in @($keyPathFull,($keyPathFull+'.pub'),$controlPath))
{if(!(Test-Path -LiteralPath $required -PathType Leaf)){throw "PROVISION_CORRUPT: private provisioning input is missing: $required"}}
$controlBytes=[IO.File]::ReadAllBytes($controlPath)
try
{
    $trimmed=$controlBytes
    $isHex=$trimmed.Length-eq 64 -and -not @($trimmed|Where-Object{-not(('0123456789abcdefABCDEF').ToCharArray()-contains[char]$_)}).Count
    if(!$isHex -and $trimmed.Length-lt 32){throw 'PROVISION_CORRUPT: CONTROL PSK does not satisfy minimum entropy length'}
}
finally{if($controlBytes){[Array]::Clear($controlBytes,0,$controlBytes.Length)}}
if($WifiSettingsFile)
{
    if($WifiServiceId-notmatch'^wifi_[A-Za-z0-9_]+$'){throw 'PROVISION_CORRUPT: unsafe ConnMan Wi-Fi service id'}
    $wifiPath=[IO.Path]::GetFullPath($WifiSettingsFile)
    if(!(Test-Path -LiteralPath $wifiPath -PathType Leaf)){throw 'PROVISION_CORRUPT: Wi-Fi settings file is missing'}
}
elseif($WifiServiceId){throw 'PROVISION_CORRUPT: WifiServiceId requires WifiSettingsFile'}

New-Item -ItemType Directory -Force -Path $sshDirectoryPath|Out-Null
function Get-Fingerprint([string]$Line)
{
    $parts=$Line.Trim()-split'\s+'
    if($parts.Count-lt 3 -or $parts[1]-ne'ssh-ed25519'){return $null}
    try{$blob=[Convert]::FromBase64String($parts[2])}catch{return $null}
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return 'SHA256:'+([Convert]::ToBase64String($sha.ComputeHash($blob)).TrimEnd('='))}finally{$sha.Dispose()}
}

$existing=@()
if(Test-Path -LiteralPath $knownHostsPath -PathType Leaf)
{$existing=@(Get-Content -LiteralPath $knownHostsPath -Encoding UTF8|Where-Object{$_-match'^ev3dev\.local\s+ssh-ed25519\s+'})}
if($existing.Count -and !$RepinHost)
{
    $approved=@($existing|Where-Object{(Get-Fingerprint $_)-eq$HostFingerprint})
    if($approved.Count-ne$existing.Count){throw 'HOST_KEY_MISMATCH: stored EV3 host key differs from the trusted fingerprint'}
}
else
{
    $scanArgs=@('-T',$ScanTimeoutSeconds,'-t','ed25519')
    if($AddressFamily-eq'inet'){$scanArgs=@('-4')+$scanArgs}elseif($AddressFamily-eq'inet6'){$scanArgs=@('-6')+$scanArgs}
    $sshKeyscan=(Get-Command ssh-keyscan -ErrorAction Stop).Source
    $scanRun=Invoke-PhantomProcess $sshKeyscan (@($scanArgs)+$target) ($ScanTimeoutSeconds+3) 'DEVICE_NOT_FOUND'
    if($scanRun.ExitCode-ne 0){throw "DEVICE_NOT_FOUND: ssh-keyscan exited with code $($scanRun.ExitCode)"}
    $scan=@($scanRun.Output)
    $matching=@($scan|Where-Object{(Get-Fingerprint $_)-eq$HostFingerprint})
    $distinct=@($matching|ForEach-Object{($_-split'\s+')[2]}|Sort-Object -Unique)
    if($distinct.Count-eq 0){throw 'HOST_KEY_MISMATCH: discovered EV3 key does not match the trusted fingerprint'}
    if($distinct.Count-ne 1){throw 'AMBIGUOUS_DEVICE: ev3dev.local resolved to multiple trusted host keys'}
    $parts=$matching[0]-split'\s+'
    $approved=@("ev3dev.local $($parts[1]) $($parts[2])")
    [IO.File]::WriteAllLines($knownHostsPath,[string[]]$approved,[Text.UTF8Encoding]::new($false))
}

$familyLine=if($AddressFamily-eq'any'){''}else{"    AddressFamily $AddressFamily`n"}
$config="Host ev3dev.local`n${familyLine}    User $User`n    IdentityFile $keyPathFull`n    IdentitiesOnly yes`n    BatchMode yes`n    ConnectTimeout 8`n    ServerAliveInterval 5`n    ServerAliveCountMax 6`n    StrictHostKeyChecking yes`n    UserKnownHostsFile $knownHostsPath`n"
if(Test-Path -LiteralPath $configPath -PathType Leaf)
{
    if((Get-Content -LiteralPath $configPath -Raw -Encoding UTF8)-ne$config)
    {
        if(!$Repair){throw 'PROVISION_CORRUPT: existing EV3 SSH config differs; use explicit pair repair'}
        [IO.File]::WriteAllText($configPath,$config,[Text.UTF8Encoding]::new($false))
    }
}
else{[IO.File]::WriteAllText($configPath,$config,[Text.UTF8Encoding]::new($false))}

$ssh=(Get-Command ssh -ErrorAction Stop).Source
$scp=(Get-Command scp -ErrorAction Stop).Source
$deploymentProbe=Invoke-PhantomProcess $ssh @('-F',$configPath,'-o','BatchMode=yes',$target,'--','true') 45 'DEVICE_NOT_FOUND'
if($deploymentProbe.ExitCode-ne 0)
{
    if($BootstrapUser-notmatch'^[A-Za-z0-9._-]+$'){throw 'PROVISION_REQUIRED: a trusted bootstrap user is required to install the deployment key'}
    $bootstrapTarget="$BootstrapUser@$target"
    $bootstrapArgs=@('-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$knownHostsPath",'-o','ConnectTimeout=8')
    & $scp -O @bootstrapArgs ($keyPathFull+'.pub') (Join-Path $repository 'provision/ev3/install-deployment-key') "${bootstrapTarget}:/tmp/"
    if($LASTEXITCODE-ne 0){throw 'PROVISION_REQUIRED: trusted EV3 bootstrap transfer failed'}
    & $ssh -t @bootstrapArgs $bootstrapTarget -- "sudo sh /tmp/install-deployment-key /tmp/$([IO.Path]::GetFileName($keyPathFull)).pub"
    if($LASTEXITCODE-ne 0){throw 'PROVISION_REQUIRED: trusted EV3 deployment-key installation failed'}
    & $ssh -F $configPath -o BatchMode=yes $target -- true
    if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: deployment key authentication did not become ready'}
}

$payload=@(
    (Join-Path $repository 'provision/ev3/bootstrap'),(Join-Path $repository 'provision/ev3/wifi-autoconnect'),
    (Join-Path $repository 'provision/ev3/phantom-wifi-autoconnect.service'),
    (Join-Path $repository 'deploy/scripts/install-release'),(Join-Path $repository 'deploy/scripts/start-release'),
    (Join-Path $repository 'deploy/scripts/run-device-integration-test')
)
    # Setup may replace credentials and maintenance files: never do it while runtime is active.
    $idle=Invoke-PhantomProcess $ssh @('-F',$configPath,$target,'--','systemctl show -p Version >/dev/null || exit 1; if systemctl is-active --quiet phantom-controller.service || systemctl is-active --quiet phantom-safety.service || systemctl is-active --quiet phantom-network.service; then echo ACTIVE; else echo STOPPED; fi') 15 'DEVICE_NOT_FOUND'
    if($idle.ExitCode-ne 0 -or (@($idle.Output)-join'').Trim()-ne'STOPPED'){throw 'INSTALL_REQUIRES_STOPPED_RUNTIME: safely stop EV3 runtime before setup'}
foreach($source in $payload){if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw "PROVISION_CORRUPT: provisioning payload is missing: $source"}}
$remoteDirectory='/tmp/phantom-maintenance-provision'
& $ssh -F $configPath $target -- "rm -rf '$remoteDirectory'; install -d -m 0700 '$remoteDirectory'"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 provisioning directory creation failed'}
& $scp -q -O -F $configPath @payload "${target}:$remoteDirectory/"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 maintenance payload transfer failed'}
& $scp -q -O -F $configPath $controlPath "${target}:$remoteDirectory/control.psk"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 CONTROL credential transfer failed'}
$wifiArgs=''
if($WifiSettingsFile)
{
    & $scp -q -O -F $configPath $wifiPath "${target}:$remoteDirectory/wifi.settings"
    if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 Wi-Fi profile transfer failed'}
    $wifiArgs=" '$WifiServiceId' 'wifi.settings'"
}
& $ssh -F $configPath $target -- "sh '$remoteDirectory/bootstrap' '$remoteDirectory' 'control.psk'$wifiArgs; provision_status=`$?; rm -rf '$remoteDirectory'; exit `$provision_status"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 platform provisioning failed'}
& $ssh -F $configPath $target -- "test -s /var/lib/phantom/secrets/control.psk && test -x /usr/local/libexec/phantom-maintenance/start-release"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 provisioning verification failed'}

$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase='PROVISION';component='EV3';profile='N_A';status='PASS';reason='PROVISIONED';build_id=$null;artifact_sha256=$null;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state='RUNTIME_NOT_STARTED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE';secret_material_logged=$false}
New-Item -ItemType Directory -Force -Path $Destination|Out-Null
[IO.File]::WriteAllText((Join-Path ([IO.Path]::GetFullPath($Destination)) 'provision.json'),($report|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'EV3 PROVISION: PASS maintenance, CONTROL credential and provisioned Wi-Fi state verified; runtime not started'

}

function Invoke-PhantomQuestCredentialSetup {
param(
    [string]$KeyFile,
    [string]$KeyId="phantom01-control",
    [string]$Package="dev.phantom.questprototype",[string]$Destination='results/quest/provision',
    [string]$Serial='',[string]$StateRoot='',
    [switch]$VerifyOnly
)
$ErrorActionPreference="Stop"
$started=(Get-Date).ToUniversalTime()
. "$PSScriptRoot/../tools/toolchain.ps1"
. "$PSScriptRoot/pair-state.ps1"

if($KeyId -notmatch '^[A-Za-z0-9._-]{1,64}$'){throw "Unsafe key id: $KeyId"}
$adb=Get-PhantomAdb

$connected=@(Invoke-PhantomAdb $adb '' @('devices') 8|Select-Object -Skip 1|Where-Object {$_-match "\sdevice$"}|ForEach-Object{($_-split'\s+')[0]})
if($Serial)
{
    if($connected -notcontains $Serial){throw 'QUEST_NOT_FOUND: explicitly designated Quest is not connected'}
    $serial=$Serial
}
else{$serial=Get-PhantomQuestDevice $adb $StateRoot}
$model=(@(Invoke-PhantomAdb $adb $serial @('shell','getprop','ro.product.model') 8)-join'').Trim()
if($model-ne"Quest 3"){throw "Physical Quest 3 required; found model=$model"}

$remoteDirectory="/sdcard/Android/data/$Package/files/phantom-provisioning"
$remotePath="$remoteDirectory/$KeyId.psk"

if($VerifyOnly)
{
    $listing=(@(Invoke-PhantomAdb $adb $serial @('shell',"if [ -f '$remotePath' ]; then echo pending; else echo none; fi") 8)-join'').Trim()
    Write-Output "provisioning drop: $listing"
    Write-Output "Run the Diagnostic app once; START will report ready, PROVISION_REQUIRED or PROVISION_CORRUPT without exposing the key."
    return
}

if(!$KeyFile){throw 'PROVISION_REQUIRED: CONTROL key file is required'}
if(!(Test-Path -LiteralPath $KeyFile)){throw "Key file not found: $KeyFile"}
$keyBytes=[System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $KeyFile).Path)
# Validate locally so a malformed key is caught before it ever leaves the host.
$trimmed=$keyBytes
$isHex=$trimmed.Length -eq 64 -and -not (@($trimmed|Where-Object {-not (('0123456789abcdefABCDEF').ToCharArray() -contains [char]$_)}).Count)
if(-not $isHex -and $trimmed.Length -lt 32){throw "PSK must be at least 32 random bytes or exactly 64 hex characters (NFR-SEC-02)"}

Invoke-PhantomAdb $adb $serial @('shell','mkdir','-p',$remoteDirectory) 8|Out-Null
Invoke-PhantomAdb $adb $serial @('push','--sync',$KeyFile,$remotePath) 30|Out-Null

$listing=(@(Invoke-PhantomAdb $adb $serial @('shell',"if [ -f '$remotePath' ]; then echo present; else echo missing; fi") 8)-join'').Trim()
if($listing-ne'present'){throw "Provisioning drop was not created on the device"}

Write-Output "CONTROL credential staged for key_id=$KeyId (contents not shown)."
Write-Output "Next: run scripts/quest-start.ps1. The app imports the key into the Android Keystore-wrapped"
Write-Output "store, shreds the plaintext drop, and START verifies the resulting readiness state."
$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase='PROVISION';component='QUEST';profile='Diagnostic';status='PASS';reason='CONTROL_CREDENTIAL_STAGED';build_id=$null;artifact_sha256=$null;key_id=$KeyId;secret_material_logged=$false;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state='CREDENTIAL_DROP_STAGED_RUNTIME_NOT_STARTED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
New-Item -ItemType Directory -Force -Path $Destination|Out-Null
[IO.File]::WriteAllText((Join-Path ([IO.Path]::GetFullPath($Destination)) 'control-credential.json'),($report|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))

}

function Invoke-PhantomEv3Transfer {
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [ValidateRange(1,120)][int]$TimeoutSeconds=45,
    [string]$Destination='results/ev3/transfer',[string]$StateRoot=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$manifest=$null;$reportPath=$null
$steps=New-Object 'System.Collections.Generic.List[object]';$outcome=$null;$bytesTransferred=0
trap
{
    if(!$phaseComplete)
    {
        $id=if($manifest-and$manifest.build_id){$manifest.build_id}else{'failed-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        $dir=Join-Path ([IO.Path]::GetFullPath($Destination)) $id;New-Item -ItemType Directory -Force -Path $dir|Out-Null
        $reportPath=Join-Path $dir 'transfer.json';$finished=(Get-Date).ToUniversalTime()
        $reason=if($_.Exception.Message-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'TRANSFER_FAILED'}
        $report=[ordered]@{schema_version=1;phase='TRANSFER';component='EV3';profile=if($manifest){$manifest.build_profile}else{'N_A'};status='FAIL';reason=$reason;
            build_id=if($manifest){$manifest.build_id}else{$null};artifact_sha256=$null;detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=$finished.ToString('o');
            duration_ms=[long]($finished-$started).TotalMilliseconds;steps=$steps;bytes_transferred=$bytesTransferred;terminal_state='REMOTE_STAGING_UNVERIFIED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
        [IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("EV3 TRANSFER: FAIL report=$reportPath; $($_.Exception.Message)");throw
}
function Add-Step([string]$Name,[datetime]$From,[string]$Status='PASS')
{$steps.Add([ordered]@{step=$Name;status=$Status;duration_ms=[long]((Get-Date).ToUniversalTime()-$From).TotalMilliseconds})}

$step=(Get-Date).ToUniversalTime();$packagePath=[IO.Path]::GetFullPath($Package)
if(!(Test-Path -LiteralPath $packagePath -PathType Leaf)){throw "ARTIFACT_MISMATCH: EV3 package is missing: $packagePath"}
$sidecar=$packagePath+'.build-manifest.json'
if(!(Test-Path -LiteralPath $sidecar -PathType Leaf)){throw "ARTIFACT_MISMATCH: EV3 package sidecar is missing: $sidecar"}
$manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
$actualHash=(Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.schema_version-ne 2 -or $manifest.component-ne'EV3' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw 'ARTIFACT_MISMATCH: invalid EV3 package sidecar'}
if($manifest.artifact_sha256-ne$actualHash){throw 'ARTIFACT_MISMATCH: EV3 package hash does not match its sidecar'}
$length=(Get-Item -LiteralPath $packagePath).Length;Add-Step 'artifact-validation' $step

$context=Get-PhantomEv3Context $StateRoot
$remote="/var/lib/phantom/staging/phantom-$($manifest.build_id).tar.gz";$partial=$remote+'.partial'
$step=(Get-Date).ToUniversalTime()
$probe=Invoke-PhantomEv3Command "if test -f '$remote'; then sha256sum '$remote' | sed 's/[[:space:]].*`$//'; else echo ABSENT; fi" $StateRoot 15
if($probe.ExitCode-ne 0){throw 'DEVICE_NOT_FOUND: EV3 remote staging probe failed'}
$remoteIdentity=(@($probe.Output|Select-Object -First 1)-join'').Trim();Add-Step 'resolve-connect-auth-and-probe' $step
if($remoteIdentity-eq$actualHash)
{
    $outcome='SKIPPED_ALREADY_PRESENT'
}
elseif($remoteIdentity-ne'ABSENT')
{throw 'ARTIFACT_MISMATCH: build_id staging path exists with different artifact SHA-256'}
else
{
    $cleanup=Invoke-PhantomEv3Command "rm -f '$partial'" $StateRoot 15
    if($cleanup.ExitCode-ne 0){throw 'TRANSFER_FAILED: stale partial upload could not be removed'}
    $step=(Get-Date).ToUniversalTime();$scp=(Get-Command scp -ErrorAction Stop).Source
    $run=Invoke-PhantomNative $scp @('-q','-O','-F',$context.SshConfig,'-o','BatchMode=yes',$packagePath,"$($context.Target):$partial") $TimeoutSeconds 'DEVICE_NOT_FOUND'
    if($run.ExitCode-ne 0){throw "TRANSFER_FAILED: scp exited with code $($run.ExitCode)"}
    $bytesTransferred=$length;Add-Step 'transfer' $step
    $step=(Get-Date).ToUniversalTime()
    $finalize=Invoke-PhantomEv3Command "test `$(sha256sum '$partial' | sed 's/[[:space:]].*`$//') = '$actualHash' && mv -f '$partial' '$remote'" $StateRoot 15
    if($finalize.ExitCode-ne 0){throw 'ARTIFACT_MISMATCH: uploaded bytes failed remote SHA-256 validation'}
    Add-Step 'remote-sha256-and-atomic-finalize' $step;$outcome='TRANSFERRED'
}

$finished=(Get-Date).ToUniversalTime();$transferStep=@($steps|Where-Object {$_.step -eq 'transfer'}|Select-Object -First 1)
$throughput=if($transferStep-and$transferStep.duration_ms-gt 0){[long]($bytesTransferred*1000/$transferStep.duration_ms)}else{0}
$report=[ordered]@{schema_version=1;phase='TRANSFER';component='EV3';profile=$manifest.build_profile;status='PASS';reason=$outcome;build_id=$manifest.build_id;
    artifact_sha256=$actualHash;remote_staging=$remote;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;
    steps=$steps;bytes_transferred=$bytesTransferred;throughput_bytes_per_second=$throughput;terminal_state='EXACT_ARTIFACT_STAGED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
$reportDir=Join-Path ([IO.Path]::GetFullPath($Destination)) $manifest.build_id;New-Item -ItemType Directory -Force -Path $reportDir|Out-Null
$reportPath=Join-Path $reportDir 'transfer.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false));$phaseComplete=$true
Write-Output "EV3 TRANSFER: PASS reason=$outcome build_id=$($manifest.build_id) report=$reportPath"

}
