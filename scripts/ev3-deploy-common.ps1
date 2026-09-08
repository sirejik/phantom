# Shared transport helpers for explicit EV3 lifecycle phases.

function Get-PhantomEv3SshConfig([string]$SshConfig='.ev3-ssh/config')
{
    $resolved=[System.IO.Path]::GetFullPath($SshConfig)
    if(!(Test-Path -LiteralPath $resolved -PathType Leaf))
    {throw "PROVISION_REQUIRED: EV3 maintenance SSH config is missing: $resolved"}
    return $resolved
}

function Get-PhantomEv3SshArguments([string]$SshConfig,[string]$Target='phantom-ev3')
{
    if($Target-notmatch'^[A-Za-z0-9._-]+$'){throw "Unsafe EV3 maintenance target: $Target"}
    return @('-F',(Get-PhantomEv3SshConfig $SshConfig),'-o','BatchMode=yes',$Target)
}

function Invoke-PhantomEv3Command([string]$RemoteCommand,[string]$SshConfig='.ev3-ssh/config',[string]$Target='phantom-ev3')
{
    $ssh=(Get-Command ssh -ErrorAction Stop).Source
    $arguments=@(Get-PhantomEv3SshArguments $SshConfig $Target)+@('--',$RemoteCommand)
    $output=@(& $ssh @arguments 2>&1);$code=$LASTEXITCODE;$joined=$output-join"`n"
    if($code-ne 0)
    {
        if($joined-match'REMOTE HOST IDENTIFICATION HAS CHANGED|Host key verification failed')
        {throw "HOST_IDENTITY_CHANGED: pinned EV3 host identity was rejected"}
        if($joined-match'Connection timed out|No route to host|Connection refused|Could not resolve hostname')
        {throw "EV3_UNREACHABLE: maintenance target '$Target' is unavailable"}
    }
    return [pscustomobject]@{ExitCode=$code;Output=$output}
}

function Invoke-PhantomEv3ReportedPhase(
    [string]$RemoteCommand,[string]$RemoteReport,[string]$LocalReport,
    [string]$ExpectedBuildId='',[string]$Phase='DEVICE',
    [string]$SshConfig='.ev3-ssh/config',[string]$Target='phantom-ev3')
{
    if($RemoteReport-notmatch'^/[A-Za-z0-9._/-]+$'){throw "Unsafe remote report path: $RemoteReport"}
    $local=[System.IO.Path]::GetFullPath($LocalReport)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $local)|Out-Null
    function Write-HostPhaseFailure([string]$Detail,[int]$ExitCode)
    {
        $failed=[ordered]@{schema_version=1;phase=$Phase;status='FAIL';build_id=if($ExpectedBuildId){$ExpectedBuildId}else{$null};detail=$Detail;ssh_exit_code=$ExitCode;terminal_state='REMOTE_STATE_UNKNOWN'}
        [System.IO.File]::WriteAllText($local,($failed|ConvertTo-Json -Depth 6)+"`n",[System.Text.UTF8Encoding]::new($false))
    }
    $marker='__PHANTOM_PHASE_REPORT__'
    $command="rm -f '$RemoteReport'; set +e; $RemoteCommand; rc=`$?; echo $marker; test ! -f '$RemoteReport' || cat '$RemoteReport'; exit `$rc"
    try{$run=Invoke-PhantomEv3Command $command $SshConfig $Target}catch{Write-HostPhaseFailure $_.Exception.Message 255;throw}
    $markerIndex=[Array]::IndexOf($run.Output,$marker)
    if($markerIndex-lt 0){Write-HostPhaseFailure "EV3 phase did not return a machine-readable report" $run.ExitCode;throw "EV3 phase did not return a machine-readable report; exit=$($run.ExitCode); report=$local"}
    $jsonLines=@($run.Output|Select-Object -Skip ($markerIndex+1))
    if($jsonLines.Count-eq 0){Write-HostPhaseFailure "EV3 phase report is empty" $run.ExitCode;throw "EV3 phase report is empty; exit=$($run.ExitCode); report=$local"}
    try{$parsed=($jsonLines-join"`n")|ConvertFrom-Json}catch{Write-HostPhaseFailure "EV3 phase report is malformed: $($_.Exception.Message)" $run.ExitCode;throw}
    if($ExpectedBuildId -and $parsed.build_id-ne$ExpectedBuildId){$parsed.status='FAIL';$parsed|Add-Member host_admission_failure "build mismatch: expected=$ExpectedBuildId actual=$($parsed.build_id)" -Force}
    if($run.ExitCode-ne 0 -and $parsed.status-eq'PASS'){$parsed.status='FAIL';$parsed|Add-Member host_transport_failure "remote command exit=$($run.ExitCode)" -Force}
    [System.IO.File]::WriteAllText($local,($parsed|ConvertTo-Json -Depth 12)+"`n",[System.Text.UTF8Encoding]::new($false))
    foreach($line in @($run.Output|Select-Object -First $markerIndex)){Write-Output $line}
    if($run.ExitCode-ne 0 -or $parsed.status-ne'PASS'){throw "EV3 phase failed; report=$local"}
    return $parsed
}
