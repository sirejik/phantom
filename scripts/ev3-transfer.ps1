param(
    [Parameter(Mandatory=$true)][string]$Address,
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$PreInstallReport='results/pre-install/report.json',
    [string]$User='root',
    [string]$KeyPath='.ev3-ssh/id_ed25519',
    [ValidateRange(1,900)][int]$TimeoutSeconds=180,
    [string]$Destination='results/ev3/transfer'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
Assert-PhantomEv3ConnectionInput $Address $User
$key=Get-PhantomEv3Key $KeyPath
$packagePath=[System.IO.Path]::GetFullPath($Package)
$gatePath=[System.IO.Path]::GetFullPath($PreInstallReport)
if(!(Test-Path -LiteralPath $packagePath -PathType Leaf)){throw "EV3 package is missing: $packagePath"}
if(!(Test-Path -LiteralPath $gatePath -PathType Leaf)){throw "PRE-INSTALL report is missing: $gatePath"}
$sidecar=$packagePath+'.build-manifest.json'
if(!(Test-Path -LiteralPath $sidecar -PathType Leaf)){throw "EV3 package sidecar is missing: $sidecar"}
$manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
$gate=Get-Content -LiteralPath $gatePath -Raw -Encoding UTF8|ConvertFrom-Json
$actualHash=(Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw "Invalid EV3 build_id"}
if($manifest.artifact_sha256-ne$actualHash){throw "EV3 package hash does not match its sidecar"}
if($gate.gate-ne'PRE-INSTALL AUTO' -or $gate.status-ne'PASS' -or $gate.build_ids-notcontains$manifest.build_id){throw "Matching PRE-INSTALL PASS is required"}
if(@($gate.artifacts|Where-Object sha256 -eq $actualHash).Count-ne 1){throw "EV3 package hash is absent or ambiguous in PRE-INSTALL evidence"}
foreach($name in @('install-release','start-release','run-device-auto','rollback-release'))
{
    $tool=Join-Path $PSScriptRoot "../deploy/scripts/$name"
    $toolHash=(Get-FileHash -LiteralPath $tool -Algorithm SHA256).Hash.ToLowerInvariant()
    if(@($gate.artifacts|Where-Object sha256 -eq $toolHash).Count-ne 1){throw "Deployment tool $name is absent or ambiguous in PRE-INSTALL evidence"}
}

$started=(Get-Date).ToUniversalTime()
$tempRoot=[System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')+'\'
$stage=Join-Path $tempRoot ('phantom-transfer-'+[guid]::NewGuid().ToString('N'))
if(!$stage.StartsWith($tempRoot,[System.StringComparison]::OrdinalIgnoreCase)){throw "Unsafe transfer staging path"}
New-Item -ItemType Directory -Path $stage|Out-Null
try
{
    Copy-Item -LiteralPath $packagePath -Destination (Join-Path $stage 'package.tar.gz')
    Copy-Item -LiteralPath $gatePath -Destination (Join-Path $stage 'pre-install-report.json')
    foreach($name in @('install-release','start-release','run-device-auto','rollback-release'))
    {
        Copy-Item -LiteralPath (Join-Path $PSScriptRoot "../deploy/scripts/$name") -Destination (Join-Path $stage $name)
    }
    $hashLines=Get-ChildItem -LiteralPath $stage -File|Sort-Object Name|ForEach-Object{"$((Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant())  $($_.Name)"}
    [System.IO.File]::WriteAllText((Join-Path $stage 'SHA256SUMS'),(($hashLines-join"`n")+"`n"),[System.Text.Encoding]::ASCII)
    $remote="/tmp/phantom-transfer-$($manifest.build_id)"
    $remoteUpload="/tmp/phantom-upload-$($manifest.build_id)-$([guid]::NewGuid().ToString('N'))"
    $scp=(Get-Command scp -ErrorAction Stop).Source
    $options=Get-PhantomEv3SshOptions $key
    $arguments=@($options)+@('-r',$stage,"$User@${Address}:$remoteUpload")
    $process=Start-Process -FilePath $scp -ArgumentList $arguments -NoNewWindow -PassThru
    $completed=$process.WaitForExit($TimeoutSeconds*1000)
    if(!$completed)
    {
        $process.Kill()
        $process.WaitForExit()
        throw "EV3 transfer exceeded ${TimeoutSeconds}s deadline"
    }
    $process.WaitForExit()
    $process.Refresh()
    $transferExitCode=$process.ExitCode
    if($null-eq$transferExitCode){throw 'EV3 transfer completed but did not expose an exit code'}
    if($transferExitCode-ne 0){throw "EV3 transfer failed with exit $transferExitCode"}
    $verify=Invoke-PhantomEv3Command $Address $User $key "cd '$remoteUpload' && timeout 30 sha256sum -c SHA256SUMS && chmod 0755 install-release start-release run-device-auto rollback-release && cd / && rm -rf -- '$remote' && mv '$remoteUpload' '$remote'"
    if($verify.ExitCode-ne 0){throw "EV3 transfer verification failed: $($verify.Output-join' ')"}
    $finished=(Get-Date).ToUniversalTime()
    $report=[ordered]@{schema_version=1;phase='TRANSFER';status='PASS';build_id=$manifest.build_id;artifact_sha256=$actualHash;remote_staging=$remote;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;steps=@([ordered]@{step='copy-and-remote-sha256';status='PASS';duration_ms=[long]($finished-$started).TotalMilliseconds})}
    $reportDir=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $manifest.build_id
    New-Item -ItemType Directory -Force -Path $reportDir|Out-Null
    $reportPath=Join-Path $reportDir 'transfer.json'
    [System.IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 6)+"`n",[System.Text.UTF8Encoding]::new($false))
    Write-Output "EV3 TRANSFER: PASS build_id=$($manifest.build_id) report=$reportPath"
}
catch
{
    $finished=(Get-Date).ToUniversalTime()
    $failed=[ordered]@{schema_version=1;phase='TRANSFER';status='FAIL';build_id=$manifest.build_id;artifact_sha256=$actualHash;detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state='REMOTE_STAGING_PARTIAL_OR_UNKNOWN'}
    $reportDir=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $manifest.build_id
    New-Item -ItemType Directory -Force -Path $reportDir|Out-Null
    $reportPath=Join-Path $reportDir 'transfer.json'
    [System.IO.File]::WriteAllText($reportPath,($failed|ConvertTo-Json -Depth 6)+"`n",[System.Text.UTF8Encoding]::new($false))
    throw "EV3 TRANSFER failed; report=$reportPath; $($_.Exception.Message)"
}
finally
{
    $resolvedStage=[System.IO.Path]::GetFullPath($stage)
    if($resolvedStage.StartsWith($tempRoot,[System.StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $resolvedStage)){Remove-Item -LiteralPath $resolvedStage -Recurse -Force}
}
