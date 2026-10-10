# Shared fixed-pair transport helpers for explicit EV3 lifecycle phases.
. "$PSScriptRoot/pair-state.ps1"

function Get-PhantomEv3Context([string]$StateRoot='')
{
    $pair=Read-PhantomPairState $StateRoot -RequirePrivateFiles
    return [pscustomobject]@{Target=$pair.State.ev3_hostname;SshConfig=$pair.Paths.SshConfig;Pair=$pair.State}
}

function Join-PhantomNativeArguments([string[]]$Arguments)
{
    return (@($Arguments|ForEach-Object{'"'+$_.Replace('"','\"')+'"'})-join' ')
}

function Invoke-PhantomNative([string]$File,[string[]]$Arguments,[int]$TimeoutSeconds,[string]$TimeoutCode)
{
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$File;$info.Arguments=Join-PhantomNativeArguments $Arguments
    $info.UseShellExecute=$false;$info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true;$info.RedirectStandardError=$true
    $process=[Diagnostics.Process]::new();$process.StartInfo=$info
    if(!$process.Start()){throw "${TimeoutCode}: process could not be started"}
    $stdout=$process.StandardOutput.ReadToEndAsync();$stderr=$process.StandardError.ReadToEndAsync()
    if(!$process.WaitForExit($TimeoutSeconds*1000))
    {
        try{$process.Kill()}catch{};$process.WaitForExit()
        throw "${TimeoutCode}: operation exceeded ${TimeoutSeconds}s hard deadline"
    }
    $stdoutLines=@($stdout.Result-split"`r?`n"|Where-Object{$_})
    $stderrLines=@($stderr.Result-split"`r?`n"|Where-Object{$_})
    return [pscustomobject]@{ExitCode=$process.ExitCode;Stdout=$stdoutLines;Stderr=$stderrLines;Output=@($stdoutLines+$stderrLines)}
}

function Invoke-PhantomEv3Command([string]$RemoteCommand,[string]$StateRoot='',[ValidateRange(1,960)][int]$TimeoutSeconds=15)
{
    $context=Get-PhantomEv3Context $StateRoot
    $ssh=(Get-Command ssh -ErrorAction Stop).Source
    $arguments=@('-F',$context.SshConfig,'-o','BatchMode=yes',$context.Target,'--',$RemoteCommand)
    $run=Invoke-PhantomNative $ssh $arguments $TimeoutSeconds 'DEVICE_NOT_FOUND'
    $joined=$run.Output-join"`n"
    if($run.ExitCode-ne 0)
    {
        if($joined-match'REMOTE HOST IDENTIFICATION HAS CHANGED|Host key verification failed|No .* host key is known')
        {throw 'HOST_KEY_MISMATCH: pinned EV3 host identity was rejected'}
        if($joined-match'Permission denied \(publickey')
        {throw 'PROVISION_CORRUPT: EV3 deployment credential was rejected'}
        if($joined-match'Connection timed out|No route to host|Connection refused|Could not resolve hostname')
        {throw "DEVICE_NOT_FOUND: designated EV3 '$($context.Target)' is unavailable"}
    }
    return $run
}

function Invoke-PhantomEv3ReportedPhase(
    [string]$RemoteCommand,[string]$RemoteReport,[string]$LocalReport,
    [string]$ExpectedBuildId='',[string]$Phase='DEVICE',[string]$StateRoot='',
    [ValidateRange(1,960)][int]$TimeoutSeconds=60)
{
    if($RemoteReport-notmatch'^/[A-Za-z0-9._/-]+$'){throw "Unsafe remote report path: $RemoteReport"}
    $local=[IO.Path]::GetFullPath($LocalReport)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $local)|Out-Null
    function Write-HostPhaseFailure([string]$Reason,[string]$Detail,[int]$ExitCode)
    {
        $failed=[ordered]@{schema_version=1;phase=$Phase;component='EV3';profile='N_A';status='FAIL';reason=$Reason;
            build_id=if($ExpectedBuildId){$ExpectedBuildId}else{$null};artifact_sha256=$null;detail=$Detail;ssh_exit_code=$ExitCode;
            duration_ms=0;terminal_state='REMOTE_STATE_UNKNOWN';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE'}
        [IO.File]::WriteAllText($local,($failed|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
    }
    $marker='__PHANTOM_PHASE_REPORT__'
    $command="rm -f '$RemoteReport'; set +e; $RemoteCommand; rc=`$?; echo $marker; test ! -f '$RemoteReport' || cat '$RemoteReport'; exit `$rc"
    try{$run=Invoke-PhantomEv3Command $command $StateRoot $TimeoutSeconds}
    catch
    {
        $reason=if($_.Exception.Message-match'^([A-Z][A-Z0-9_]+):'){$Matches[1]}else{'DEVICE_NOT_FOUND'}
        Write-HostPhaseFailure $reason $_.Exception.Message 255;throw
    }
    $markerIndex=[Array]::IndexOf($run.Stdout,$marker)
    if($markerIndex-lt 0){Write-HostPhaseFailure 'MALFORMED_PHASE_RESULT' 'EV3 phase did not return a machine-readable report' $run.ExitCode;throw "EV3 phase did not return a machine-readable report; exit=$($run.ExitCode); report=$local"}
    $jsonLines=@($run.Stdout|Select-Object -Skip ($markerIndex+1))
    if($jsonLines.Count-eq 0){Write-HostPhaseFailure 'MALFORMED_PHASE_RESULT' 'EV3 phase report is empty' $run.ExitCode;throw "EV3 phase report is empty; exit=$($run.ExitCode); report=$local"}
    try{$parsed=($jsonLines-join"`n")|ConvertFrom-Json}catch{Write-HostPhaseFailure 'MALFORMED_PHASE_RESULT' "EV3 phase report is malformed: $($_.Exception.Message)" $run.ExitCode;throw}
    if($ExpectedBuildId -and $parsed.build_id-ne$ExpectedBuildId){$parsed.status='FAIL';$parsed.reason='DEVICE_IDENTITY_MISMATCH';$parsed|Add-Member host_admission_failure "build mismatch: expected=$ExpectedBuildId actual=$($parsed.build_id)" -Force}
    if($run.ExitCode-ne 0 -and $parsed.status-eq'PASS'){$parsed.status='FAIL';$parsed.reason='REMOTE_PHASE_FAILED';$parsed|Add-Member host_transport_failure "remote command exit=$($run.ExitCode)" -Force}
    [IO.File]::WriteAllText($local,($parsed|ConvertTo-Json -Depth 12)+"`n",[Text.UTF8Encoding]::new($false))
    foreach($line in @($run.Stdout|Select-Object -First $markerIndex)){Write-Output $line}
    foreach($line in @($run.Stderr)){[Console]::Error.WriteLine($line)}
    if($run.ExitCode-ne 0 -or $parsed.status-ne'PASS'){throw "EV3 phase failed; report=$local"}
    return $parsed
}
