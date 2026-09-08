param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$Destination='results/ev3/install'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$remote="/tmp/phantom-transfer-$BuildId"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/install.json"
$result=Invoke-PhantomEv3ReportedPhase $Address $User $KeyPath "timeout $TimeoutSeconds '$remote/install-release' '$remote/package.tar.gz' '$remote/package.build-manifest.json'" '/var/lib/phantom/install-result.json' $report $BuildId 'INSTALL'
Write-Output "EV3 INSTALL: PASS build_id=$($result.build_id) report=$report; runtime remains stopped"
