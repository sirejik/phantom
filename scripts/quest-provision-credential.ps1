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
    [Parameter(Mandatory=$true)][string]$KeyFile,
    [string]$KeyId="phantom01-control",
    [string]$Package="dev.phantom.questprototype",
    [switch]$VerifyOnly
)
$ErrorActionPreference="Stop"
. "$PSScriptRoot/../tools/toolchain.ps1"

if($KeyId -notmatch '^[A-Za-z0-9._-]{1,64}$'){throw "Unsafe key id: $KeyId"}
$adb=Get-PhantomAdb

$devices=@(& $adb devices|Select-Object -Skip 1|Where-Object {$_-match "\sdevice$"})
if($devices.Count-ne 1){throw "Exactly one authorized ADB device is required; found $($devices.Count)"}
$serial=($devices[0]-split "\s+")[0]
$model=(@(& $adb -s $serial shell getprop ro.product.model)-join'').Trim()
if($model-ne"Quest 3"){throw "Physical Quest 3 required; found model=$model"}

$remoteDirectory="/sdcard/Android/data/$Package/files/phantom-provisioning"
$remotePath="$remoteDirectory/$KeyId.psk"

if($VerifyOnly)
{
    $listing=(@(& $adb -s $serial shell "if [ -f '$remotePath' ]; then echo pending; else echo none; fi")-join'').Trim()
    Write-Output "provisioning drop: $listing"
    Write-Output "Run the Diagnostic app once, then confirm 'quest-control-credential-present' in the DEVICE AUTO report."
    exit 0
}

if(!(Test-Path -LiteralPath $KeyFile)){throw "Key file not found: $KeyFile"}
$keyBytes=[System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $KeyFile).Path)
# Validate locally so a malformed key is caught before it ever leaves the host.
$trimmed=$keyBytes
while($trimmed.Length -gt 0 -and @(10,13,32,9) -contains $trimmed[$trimmed.Length-1]){$trimmed=$trimmed[0..($trimmed.Length-2)]}
$isHex=$trimmed.Length -eq 64 -and -not (@($trimmed|Where-Object {-not (('0123456789abcdefABCDEF').ToCharArray() -contains [char]$_)}).Count)
if(-not $isHex -and $trimmed.Length -lt 32){throw "PSK must be at least 32 random bytes or exactly 64 hex characters (NFR-SEC-02)"}

& $adb -s $serial shell mkdir -p $remoteDirectory | Out-Null
& $adb -s $serial push --sync $KeyFile $remotePath | Out-Null
if($LASTEXITCODE-ne 0){throw "adb push of the provisioning drop failed"}

$listing=(@(& $adb -s $serial shell "if [ -f '$remotePath' ]; then echo present; else echo missing; fi")-join'').Trim()
if($listing-ne'present'){throw "Provisioning drop was not created on the device"}

Write-Output "CONTROL credential staged for key_id=$KeyId (contents not shown)."
Write-Output "Next: run scripts/quest-start.ps1 once. The app imports the key into the Android Keystore-wrapped"
Write-Output "store and shreds the plaintext drop. Then run scripts/quest-device-auto.ps1 and confirm"
Write-Output "'quest-control-credential-present' is PASS."
