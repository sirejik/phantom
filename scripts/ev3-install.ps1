param(
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$HostFingerprint='', [string]$QuestSerial='',
    [string]$BootstrapUser='robot', [string]$WifiSettingsFile='', [string]$WifiServiceId='',
    [string]$RobotId='', [string]$ControlKeyId='',
    [switch]$Repair, [switch]$RotateSshKey, [switch]$RotateControlSecret, [switch]$RepinHost,
    [ValidateRange(1,600)][int]$TimeoutSeconds=30,
    [string]$Destination='results/ev3/install',[string]$StateRoot=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
. "$PSScriptRoot/install-common.ps1"
. "$PSScriptRoot/install-device.ps1"
$packagePath=[IO.Path]::GetFullPath($Package)
if(!(Test-Path -LiteralPath $packagePath -PathType Leaf) -or !(Test-Path -LiteralPath ($packagePath+'.build-manifest.json') -PathType Leaf)){throw 'ARTIFACT_MISMATCH: EV3 package or sidecar is missing'}
$manifest=Get-Content -LiteralPath ($packagePath+'.build-manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
$PackageSha256=(Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.component-ne'EV3' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$' -or $manifest.artifact_sha256-ne$PackageSha256){throw 'ARTIFACT_MISMATCH: invalid EV3 package identity'}
$BuildId=$manifest.build_id
$pair=Initialize-PhantomInstallPair -StateRoot $StateRoot -HostFingerprint $HostFingerprint -QuestSerial $QuestSerial -RobotId $RobotId -ControlKeyId $ControlKeyId -Repair:$Repair -RotateSshKey:$RotateSshKey -RotateControlSecret:$RotateControlSecret -RepinHost:$RepinHost
if(($WifiSettingsFile -or $WifiServiceId) -and !$Repair -and (Test-Path -LiteralPath $pair.Paths.SshConfig)){throw 'PROVISION_CORRUPT: changing Wi-Fi requires explicit -Repair'}
Invoke-PhantomEv3Setup -HostFingerprint $pair.State.ev3_host_key_fingerprint -KeyPath $pair.Paths.SshKey -SshDirectory $pair.Paths.SshDirectory -ControlKeyFile $pair.Paths.ControlSecret -BootstrapUser $BootstrapUser -WifiSettingsFile $WifiSettingsFile -WifiServiceId $WifiServiceId -Repair:$Repair -RepinHost:$RepinHost
Invoke-PhantomEv3Transfer -Package $packagePath -TimeoutSeconds ([Math]::Min($TimeoutSeconds,120)) -StateRoot $StateRoot -Destination (Join-Path $Destination 'transfer')
$remote="/var/lib/phantom/staging/phantom-$BuildId.tar.gz"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/install.json"
$command="timeout $TimeoutSeconds /usr/local/libexec/phantom-maintenance/install-release '$remote' '$BuildId' '$PackageSha256'"
$result=Invoke-PhantomEv3ReportedPhase $command '/var/lib/phantom/install-result.json' $report $BuildId 'INSTALL' $StateRoot ($TimeoutSeconds+8)
Write-Output "EV3 INSTALL: PASS build_id=$($result.build_id) report=$report; runtime remains stopped"
