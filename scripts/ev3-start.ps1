param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [string]$Target='phantom-ev3',[string]$SshConfig='.ev3-ssh/config',
    [ValidateRange(1,60)][int]$StepTimeoutSeconds=15,
    [ValidateRange(1,300)][int]$TimeoutSeconds=90,[switch]$Debug,
    [string]$Destination=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$destinationRoot=if($Destination){$Destination}elseif($Debug){'results/ev3/debug'}else{'results/ev3/start'}
$report=Join-Path ([System.IO.Path]::GetFullPath($destinationRoot)) "$BuildId/start.json"
$verbosity=if($Debug){'debug'}else{'normal'}
$command="timeout $TimeoutSeconds env PHANTOM_START_STEP_TIMEOUT_SECONDS=$StepTimeoutSeconds PHANTOM_START_VERBOSITY=$verbosity /usr/local/libexec/phantom-maintenance/start-release"
$result=Invoke-PhantomEv3ReportedPhase $command '/var/lib/phantom/start-result.json' $report $BuildId $(if($Debug){'DEBUG'}else{'START'}) $SshConfig $Target
Write-Output "EV3 START: PASS build_id=$($result.build_id) report=$report"
