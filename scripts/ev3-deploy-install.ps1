<# User-intent wrapper: explicitly executes TRANSFER, then INSTALL, and never START. #>
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$Target='phantom-ev3',[string]$SshConfig='.ev3-ssh/config'
)
$ErrorActionPreference='Stop'
$resolved=[IO.Path]::GetFullPath($Package);$sidecar=$resolved+'.build-manifest.json'
if(!(Test-Path -LiteralPath $resolved -PathType Leaf) -or !(Test-Path -LiteralPath $sidecar -PathType Leaf)){throw "EV3 package or sidecar is missing: $resolved"}
$manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
$hash=(Get-FileHash -LiteralPath $resolved -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.build_id-notmatch'^[0-9a-f]{64}$' -or $manifest.artifact_sha256-ne$hash){throw 'EV3 package sidecar/hash is invalid'}
Write-Output '=== PHASE TRANSFER ==='
& "$PSScriptRoot/ev3-transfer.ps1" -Package $resolved -Target $Target -SshConfig $SshConfig
if($LASTEXITCODE-ne 0){throw 'EV3 TRANSFER failed; INSTALL was not started'}
Write-Output '=== PHASE INSTALL ==='
& "$PSScriptRoot/ev3-install.ps1" -BuildId $manifest.build_id -PackageSha256 $hash -Target $Target -SshConfig $SshConfig
if($LASTEXITCODE-ne 0){throw 'EV3 INSTALL failed'}
Write-Output "EV3 install intent: PASS build_id=$($manifest.build_id); runtime remains stopped"
