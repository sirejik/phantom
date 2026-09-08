param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$BuildId,
    [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-f]{64}$')][string]$PackageSha256,
    [string]$Target='phantom-ev3',[string]$SshConfig='.ev3-ssh/config',
    [ValidateRange(1,600)][int]$TimeoutSeconds=180,
    [string]$Destination='results/ev3/install'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$remote="/var/lib/phantom/staging/phantom-$BuildId.tar.gz"
$report=Join-Path ([System.IO.Path]::GetFullPath($Destination)) "$BuildId/install.json"
$command="timeout $TimeoutSeconds /usr/local/libexec/phantom-maintenance/install-release '$remote' '$BuildId' '$PackageSha256'"
$result=Invoke-PhantomEv3ReportedPhase $command '/var/lib/phantom/install-result.json' $report $BuildId 'INSTALL' $SshConfig $Target
Write-Output "EV3 INSTALL: PASS build_id=$($result.build_id) report=$report; runtime remains stopped"
