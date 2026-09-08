param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$FailedBuildId,
    [string]$Target='phantom-ev3',[string]$SshConfig='.ev3-ssh/config',
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$Destination='results/ev3/recovery'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$FailedBuildId/recovery.json"
$result=Invoke-PhantomEv3ReportedPhase "timeout $TimeoutSeconds /usr/local/libexec/phantom-maintenance/rollback-release" '/var/lib/phantom/recovery-result.json' $report '' 'RECOVERY' $SshConfig $Target
Write-Output "EV3 RECOVERY: PASS restored_build_id=$($result.build_id) report=$report; runtime remains stopped"
