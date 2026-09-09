param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [ValidateRange(1,900)][int]$TimeoutSeconds=360,
    [string]$Destination='results/ev3/device-integration',[string]$StateRoot=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/device-integration-test.json"
$command="/usr/local/libexec/phantom-maintenance/run-device-integration-test '$BuildId' '$TimeoutSeconds'"
$result=Invoke-PhantomEv3ReportedPhase $command '/var/lib/phantom/device-integration-test.json' $report $BuildId 'DEVICE INTEGRATION TEST' $StateRoot ($TimeoutSeconds+8)
Write-Output "EV3 DEVICE INTEGRATION TEST: PASS build_id=$($result.build_id) report=$report"
