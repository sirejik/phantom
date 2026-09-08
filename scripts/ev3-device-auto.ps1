param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,900)][int]$TimeoutSeconds=360,
    [string]$Destination='results/ev3/device-auto'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$remote="/tmp/phantom-transfer-$BuildId"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/device-auto.json"
$result=Invoke-PhantomEv3ReportedPhase $Address $User $KeyPath "'$remote/run-device-auto' '$BuildId' '$TimeoutSeconds'" '/var/lib/phantom/device-auto.json' $report $BuildId 'DEVICE AUTO'
Write-Output "EV3 DEVICE AUTO: PASS build_id=$($result.build_id) report=$report"
