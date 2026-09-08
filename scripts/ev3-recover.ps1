param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$FailedBuildId,
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$Destination='results/ev3/recovery'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$remote="/tmp/phantom-transfer-$FailedBuildId"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$FailedBuildId/recovery.json"
$result=Invoke-PhantomEv3ReportedPhase $Address $User $KeyPath "timeout $TimeoutSeconds '$remote/rollback-release'" '/var/lib/phantom/recovery-result.json' $report '' 'RECOVERY'
Write-Output "EV3 RECOVERY: PASS restored_build_id=$($result.build_id) report=$report; runtime remains stopped"
