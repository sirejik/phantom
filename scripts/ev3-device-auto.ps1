param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,900)][int]$TimeoutSeconds=360,
    [string]$PreInstallReport='results/pre-install/report.json',
    [string]$Destination='results/ev3/device-auto'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$preInstallPath=[System.IO.Path]::GetFullPath($PreInstallReport)
if(!(Test-Path -LiteralPath $preInstallPath -PathType Leaf)){throw "PRE-INSTALL report is missing: $preInstallPath"}
$preInstall=Get-Content -LiteralPath $preInstallPath -Encoding UTF8 -Raw|ConvertFrom-Json
if($preInstall.gate-ne'PRE-INSTALL AUTO' -or $preInstall.status-ne'PASS' -or $preInstall.build_ids-notcontains$BuildId){throw 'Matching EV3 PRE-INSTALL PASS is required before DEVICE AUTO'}
$remote="/tmp/phantom-transfer-$BuildId"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/device-auto.json"
$result=Invoke-PhantomEv3ReportedPhase $Address $User $KeyPath "'$remote/run-device-auto' '$BuildId' '$TimeoutSeconds'" '/var/lib/phantom/device-auto.json' $report $BuildId 'DEVICE AUTO'
Write-Output "EV3 DEVICE AUTO: PASS build_id=$($result.build_id) report=$report"
