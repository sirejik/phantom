param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [ValidatePattern('^$|^[0-9a-f]{64}$')][string]$ToolBuildId='',
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,300)][int]$StepTimeoutSeconds=95,
    [ValidateRange(1,1200)][int]$TimeoutSeconds=600,
    [string]$Destination='results/ev3/start'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
if(!$ToolBuildId){$ToolBuildId=$BuildId}
$remote="/tmp/phantom-transfer-$ToolBuildId"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/start.json"
$command="timeout $TimeoutSeconds env PHANTOM_START_STEP_TIMEOUT_SECONDS=$StepTimeoutSeconds '$remote/start-release'"
$result=Invoke-PhantomEv3ReportedPhase $Address $User $KeyPath $command '/var/lib/phantom/start-result.json' $report $BuildId 'START'
Write-Output "EV3 START: PASS build_id=$($result.build_id) report=$report"
