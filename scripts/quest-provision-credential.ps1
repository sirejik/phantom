<#
.SYNOPSIS
Provision the CONTROL PSK onto a Quest 3, outside the runtime UDP protocol.

.DESCRIPTION
ENGINEERING 8.11 requires the control PSK to reach the Quest out of band and to
live only in the app-private credential store. This script is that path.

The key is written once into the app-specific provisioning directory. On its
next start the Diagnostic build imports it into the Keystore-wrapped store and
shreds the plaintext drop. Nothing about the key is printed, passed as a command
line argument, embedded in the APK, written to a build manifest or stored in the
repository.

Diagnostic profile only. A Release build never imports a provisioning drop.

.PARAMETER KeyFile
File holding the PSK: 32+ raw bytes, or exactly 64 ASCII hex characters. Keep it
outside the repository (the ignored .secrets/ directory is the usual place).
#>
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
    exit 0
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
