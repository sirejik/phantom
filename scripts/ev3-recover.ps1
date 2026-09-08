param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$FailedBuildId,
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$TransferEvidence='results/ev3/transfer',
    [string]$Destination='results/ev3/recovery'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$transferPath=Join-Path ([System.IO.Path]::GetFullPath($TransferEvidence)) "$FailedBuildId/transfer.json"
if(!(Test-Path -LiteralPath $transferPath -PathType Leaf)){throw "Matching EV3 TRANSFER report is missing: $transferPath"}
$transfer=Get-Content -LiteralPath $transferPath -Encoding UTF8 -Raw|ConvertFrom-Json
if($transfer.phase-ne'TRANSFER' -or $transfer.status-ne'PASS' -or $transfer.build_id-ne$FailedBuildId){throw 'Matching EV3 TRANSFER PASS is required before RECOVERY'}
$remote="/tmp/phantom-transfer-$FailedBuildId"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$FailedBuildId/recovery.json"
$result=Invoke-PhantomEv3ReportedPhase $Address $User $KeyPath "timeout $TimeoutSeconds '$remote/rollback-release'" '/var/lib/phantom/recovery-result.json' $report '' 'RECOVERY'
Write-Output "EV3 RECOVERY: PASS restored_build_id=$($result.build_id) report=$report; runtime remains stopped"
