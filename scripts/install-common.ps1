# Internal setup for INSTALL. Pair designation is local; each installer changes only its device.
. "$PSScriptRoot/pair-state.ps1"
. "$PSScriptRoot/../tools/toolchain.ps1"
function Initialize-PhantomInstallPair
{
    param([string]$StateRoot='', [string]$HostFingerprint='', [string]$QuestSerial='',
        [string]$RobotId='', [string]$ControlKeyId='',
        [switch]$Repair, [switch]$RotateSshKey, [switch]$RotateControlSecret, [switch]$RepinHost)
    if(($RotateSshKey -or $RotateControlSecret -or $RepinHost) -and !$Repair){throw 'PROVISION_CORRUPT: rotation/repin requires explicit -Repair'}
    $paths=Get-PhantomPairPaths $StateRoot
    $existing=Test-Path -LiteralPath $paths.Record -PathType Leaf
    if($existing){
        $pair=Read-PhantomPairState $StateRoot
        if(($RobotId -and $RobotId-ne$pair.State.robot_id) -or ($ControlKeyId -and $ControlKeyId-ne$pair.State.control_key_id)){throw 'PROVISION_CORRUPT: installation cannot silently replace the pair identity'}
        $RobotId=$pair.State.robot_id;$ControlKeyId=$pair.State.control_key_id
        if($QuestSerial -and $QuestSerial-ne$pair.State.quest_adb_serial){throw 'QUEST_IDENTITY_MISMATCH: supplied serial differs from designated Quest'}
        if($HostFingerprint -and $HostFingerprint-ne$pair.State.ev3_host_key_fingerprint -and !$RepinHost){throw 'HOST_KEY_MISMATCH: supplied fingerprint differs from designated EV3'}
        $QuestSerial=$pair.State.quest_adb_serial
        if(!$RepinHost){$HostFingerprint=$pair.State.ev3_host_key_fingerprint}
    }else{
        if(!$RobotId){$RobotId='phantom01'}
        if(!$ControlKeyId){$ControlKeyId='phantom01-control'}
        if((Test-Path -LiteralPath $paths.Root) -and @(Get-ChildItem -LiteralPath $paths.Root -Force).Count -gt 0){throw 'PROVISION_CORRUPT: partial local pair state requires inspection; INSTALL will not overwrite it'}
        if(!$QuestSerial){
            $adb=Get-PhantomAdb
            $devices=@(Invoke-PhantomAdb $adb '' @('devices') 8|Select-Object -Skip 1|Where-Object{$_-match'\sdevice$'})
            if($devices.Count-ne 1){throw 'AMBIGUOUS_DEVICE: supply -QuestSerial or connect exactly one authorized Quest'}
            $QuestSerial=($devices[0]-split'\s+')[0]
            $model=(@(Invoke-PhantomAdb $adb $QuestSerial @('shell','getprop','ro.product.model') 8)-join'').Trim()
            $device=(@(Invoke-PhantomAdb $adb $QuestSerial @('shell','getprop','ro.product.device') 8)-join'').Trim()
            if($model-ne'Quest 3' -or $device-ne'eureka'){throw 'QUEST_IDENTITY_MISMATCH: designated device is not Quest 3'}
        }
    }
    if($HostFingerprint-notmatch'^SHA256:[A-Za-z0-9+/]{43}$'){throw 'PROVISION_REQUIRED: trusted -HostFingerprint is required for first INSTALL or explicit repin'}
    if($QuestSerial-notmatch'^[A-Za-z0-9._:-]{1,128}$' -or $RobotId-notmatch'^[A-Za-z0-9._-]{1,32}$' -or $ControlKeyId-notmatch'^[A-Za-z0-9._-]{1,64}$'){throw 'PROVISION_CORRUPT: invalid pair identity'}
    if($existing){
        if(!(Test-Path -LiteralPath $paths.SshKey -PathType Leaf) -and !$RotateSshKey){throw 'PROVISION_CORRUPT: deployment key missing; explicit repair required'}
        if(!(Test-Path -LiteralPath $paths.ControlSecret -PathType Leaf) -and !$RotateControlSecret){throw 'PROVISION_CORRUPT: CONTROL secret missing; explicit repair required'}
    }
    New-Item -ItemType Directory -Force -Path $paths.SshDirectory,$paths.SecretDirectory|Out-Null
    if($RotateSshKey){Remove-Item -LiteralPath $paths.SshKey,($paths.SshKey+'.pub') -Force -ErrorAction SilentlyContinue}
    if(!(Test-Path -LiteralPath $paths.SshKey -PathType Leaf)){New-PhantomDeploymentKey $paths.SshKey}
    if($RotateControlSecret){Remove-Item -LiteralPath $paths.ControlSecret -Force -ErrorAction SilentlyContinue}
    if(!(Test-Path -LiteralPath $paths.ControlSecret -PathType Leaf)){
        $bytes=New-Object byte[] 32;$rng=[Security.Cryptography.RandomNumberGenerator]::Create()
        try{$rng.GetBytes($bytes);[IO.File]::WriteAllBytes($paths.ControlSecret,$bytes)}finally{$rng.Dispose();[Array]::Clear($bytes,0,$bytes.Length)}
    }
    Set-PhantomPrivateAcl $paths.SshKey;Set-PhantomPrivateAcl $paths.ControlSecret
    $record=if($existing){$pair.State}else{[pscustomobject]@{provision_schema_version=1;provision_status='complete';quest_adb_serial=$QuestSerial;ev3_hostname='ev3dev.local';ev3_host_key_fingerprint=$HostFingerprint;robot_id=$RobotId;control_key_id=$ControlKeyId;quest_credential_staged=$false}}
    $record.ev3_host_key_fingerprint=$HostFingerprint
    if($RotateControlSecret){$record|Add-Member -NotePropertyName quest_credential_staged -NotePropertyValue $false -Force}
    Write-PhantomPairState $record $StateRoot
    return Read-PhantomPairState $StateRoot
}
