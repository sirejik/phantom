param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [ValidateRange(1,60)][int]$StepTimeoutSeconds=8,
    [ValidateRange(1,300)][int]$TimeoutSeconds=30,[switch]$CaptureDebug,
    [string]$Destination='',[string]$StateRoot=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$destinationRoot=if($Destination){$Destination}elseif($CaptureDebug){'results/ev3/debug'}else{'results/ev3/start'}
$report=Join-Path ([System.IO.Path]::GetFullPath($destinationRoot)) "$BuildId/start.json"
$verbosity=if($CaptureDebug){'debug'}else{'normal'}
$command="timeout -k $StepTimeoutSeconds $TimeoutSeconds env PHANTOM_START_STEP_TIMEOUT_SECONDS=$StepTimeoutSeconds PHANTOM_START_VERBOSITY=$verbosity /usr/local/libexec/phantom-maintenance/start-release"
$result=Invoke-PhantomEv3ReportedPhase $command '/var/lib/phantom/start-result.json' $report $BuildId $(if($CaptureDebug){'DEBUG'}else{'START'}) $StateRoot ($TimeoutSeconds+$StepTimeoutSeconds+8)
Write-Output "EV3 START: PASS build_id=$($result.build_id) report=$report"
