param(
    [Parameter(Mandatory=$true)][string]$Package,
    [ValidateRange(1,120)][int]$TimeoutSeconds=45,
    [string]$Destination='results/ev3/transfer',[string]$StateRoot=''
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$started=(Get-Date).ToUniversalTime();$phaseComplete=$false;$manifest=$null;$reportPath=$null
$steps=New-Object 'System.Collections.Generic.List[object]';$outcome=$null;$bytesTransferred=0
trap
{
    if(!$phaseComplete)
    {
        $id=if($manifest-and$manifest.build_id){$manifest.build_id}else{'failed-'+(Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')}
        $dir=Join-Path ([IO.Path]::GetFullPath($Destination)) $id;New-Item -ItemType Directory -Force -Path $dir|Out-Null
        $reportPath=Join-Path $dir 'transfer.json';$finished=(Get-Date).ToUniversalTime()
        $reason=if($_.Exception.Message-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'TRANSFER_FAILED'}
        $report=[ordered]@{schema_version=1;phase='TRANSFER';component='EV3';profile=if($manifest){$manifest.build_profile}else{'N_A'};status='FAIL';reason=$reason;
            build_id=if($manifest){$manifest.build_id}else{$null};artifact_sha256=$null;detail=$_.Exception.Message;started_at=$started.ToString('o');finished_at=$finished.ToString('o');
            duration_ms=[long]($finished-$started).TotalMilliseconds;steps=$steps;bytes_transferred=$bytesTransferred;terminal_state='REMOTE_STAGING_UNVERIFIED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
        [IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false))
    }
    [Console]::Error.WriteLine("EV3 TRANSFER: FAIL report=$reportPath; $($_.Exception.Message)");exit 1
}
function Add-Step([string]$Name,[datetime]$From,[string]$Status='PASS')
{$steps.Add([ordered]@{step=$Name;status=$Status;duration_ms=[long]((Get-Date).ToUniversalTime()-$From).TotalMilliseconds})}

$step=(Get-Date).ToUniversalTime();$packagePath=[IO.Path]::GetFullPath($Package)
if(!(Test-Path -LiteralPath $packagePath -PathType Leaf)){throw "ARTIFACT_MISMATCH: EV3 package is missing: $packagePath"}
$sidecar=$packagePath+'.build-manifest.json'
if(!(Test-Path -LiteralPath $sidecar -PathType Leaf)){throw "ARTIFACT_MISMATCH: EV3 package sidecar is missing: $sidecar"}
$manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
$actualHash=(Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.schema_version-ne 2 -or $manifest.component-ne'EV3' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw 'ARTIFACT_MISMATCH: invalid EV3 package sidecar'}
if($manifest.artifact_sha256-ne$actualHash){throw 'ARTIFACT_MISMATCH: EV3 package hash does not match its sidecar'}
$length=(Get-Item -LiteralPath $packagePath).Length;Add-Step 'artifact-validation' $step

$context=Get-PhantomEv3Context $StateRoot
$remote="/var/lib/phantom/staging/phantom-$($manifest.build_id).tar.gz";$partial=$remote+'.partial'
$step=(Get-Date).ToUniversalTime()
$probe=Invoke-PhantomEv3Command "if test -f '$remote'; then sha256sum '$remote' | sed 's/[[:space:]].*`$//'; else echo ABSENT; fi" $StateRoot 15
if($probe.ExitCode-ne 0){throw 'DEVICE_NOT_FOUND: EV3 remote staging probe failed'}
$remoteIdentity=(@($probe.Output|Select-Object -First 1)-join'').Trim();Add-Step 'resolve-connect-auth-and-probe' $step
if($remoteIdentity-eq$actualHash)
{
    $outcome='SKIPPED_ALREADY_PRESENT'
}
elseif($remoteIdentity-ne'ABSENT')
{throw 'ARTIFACT_MISMATCH: build_id staging path exists with different artifact SHA-256'}
else
{
    $cleanup=Invoke-PhantomEv3Command "rm -f '$partial'" $StateRoot 15
    if($cleanup.ExitCode-ne 0){throw 'TRANSFER_FAILED: stale partial upload could not be removed'}
    $step=(Get-Date).ToUniversalTime();$scp=(Get-Command scp -ErrorAction Stop).Source
    $run=Invoke-PhantomNative $scp @('-q','-O','-F',$context.SshConfig,'-o','BatchMode=yes',$packagePath,"$($context.Target):$partial") $TimeoutSeconds 'DEVICE_NOT_FOUND'
    if($run.ExitCode-ne 0){throw "TRANSFER_FAILED: scp exited with code $($run.ExitCode)"}
    $bytesTransferred=$length;Add-Step 'transfer' $step
    $step=(Get-Date).ToUniversalTime()
    $finalize=Invoke-PhantomEv3Command "test `$(sha256sum '$partial' | sed 's/[[:space:]].*`$//') = '$actualHash' && mv -f '$partial' '$remote'" $StateRoot 15
    if($finalize.ExitCode-ne 0){throw 'ARTIFACT_MISMATCH: uploaded bytes failed remote SHA-256 validation'}
    Add-Step 'remote-sha256-and-atomic-finalize' $step;$outcome='TRANSFERRED'
}

$finished=(Get-Date).ToUniversalTime();$transferStep=@($steps|Where-Object step -eq'transfer'|Select-Object -First 1)
$throughput=if($transferStep-and$transferStep.duration_ms-gt 0){[long]($bytesTransferred*1000/$transferStep.duration_ms)}else{0}
$report=[ordered]@{schema_version=1;phase='TRANSFER';component='EV3';profile=$manifest.build_profile;status='PASS';reason=$outcome;build_id=$manifest.build_id;
    artifact_sha256=$actualHash;remote_staging=$remote;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;
    steps=$steps;bytes_transferred=$bytesTransferred;throughput_bytes_per_second=$throughput;terminal_state='EXACT_ARTIFACT_STAGED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
$reportDir=Join-Path ([IO.Path]::GetFullPath($Destination)) $manifest.build_id;New-Item -ItemType Directory -Force -Path $reportDir|Out-Null
$reportPath=Join-Path $reportDir 'transfer.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 8)+"`n",[Text.UTF8Encoding]::new($false));$phaseComplete=$true
Write-Output "EV3 TRANSFER: PASS reason=$outcome build_id=$($manifest.build_id) report=$reportPath"
