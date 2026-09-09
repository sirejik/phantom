param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$FailedBuildId,
    [ValidateRange(1,600)][int]$TimeoutSeconds=30,
    [string]$Destination='results/ev3/recovery',[string]$StateRoot=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$FailedBuildId/recovery.json"
$result=Invoke-PhantomEv3ReportedPhase "timeout $TimeoutSeconds /usr/local/libexec/phantom-maintenance/rollback-release" '/var/lib/phantom/recovery-result.json' $report '' 'RECOVERY' $StateRoot ($TimeoutSeconds+8)
Write-Output "EV3 RECOVERY: PASS restored_build_id=$($result.build_id) report=$report; runtime remains stopped"
