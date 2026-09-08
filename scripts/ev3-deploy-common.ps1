# Shared transport helpers for explicit EV3 deployment phases.

function Assert-PhantomEv3ConnectionInput([string]$Address,[string]$User)
{
    if($Address-notmatch'^[A-Za-z0-9.:%-]+$'){throw "Unsafe EV3 address: $Address"}
    if($User-notmatch'^[A-Za-z0-9._-]+$'){throw "Unsafe EV3 SSH user: $User"}
}

function Get-PhantomEv3Key([string]$KeyPath)
{
    $resolved=[System.IO.Path]::GetFullPath($KeyPath)
    if(!(Test-Path -LiteralPath $resolved -PathType Leaf)){throw "EV3 SSH key is missing: $resolved"}
    return $resolved
}

function Get-PhantomEv3SshOptions([string]$KeyPath)
{
    return @('-i',$KeyPath,'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=8','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2')
}

function Invoke-PhantomEv3Command([string]$Address,[string]$User,[string]$KeyPath,[string]$RemoteCommand)
{
    Assert-PhantomEv3ConnectionInput $Address $User
    $ssh=(Get-Command ssh -ErrorAction Stop).Source
    $options=Get-PhantomEv3SshOptions (Get-PhantomEv3Key $KeyPath)
    $output=@(& $ssh @options "$User@$Address" $RemoteCommand 2>&1)
    return [pscustomobject]@{ExitCode=$LASTEXITCODE;Output=$output}
}

function Invoke-PhantomEv3ReportedPhase(
    [string]$Address,[string]$User,[string]$KeyPath,[string]$RemoteCommand,
    [string]$RemoteReport,[string]$LocalReport,[string]$ExpectedBuildId='',[string]$Phase='DEVICE')
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
    $run=Invoke-PhantomEv3Command $Address $User $KeyPath $command
    $markerIndex=[Array]::IndexOf($run.Output,$marker)
    if($markerIndex-lt 0){Write-HostPhaseFailure "EV3 phase did not return a machine-readable report" $run.ExitCode;throw "EV3 phase did not return a machine-readable report; exit=$($run.ExitCode); report=$local"}
    $jsonLines=@($run.Output|Select-Object -Skip ($markerIndex+1))
    if($jsonLines.Count-eq 0){Write-HostPhaseFailure "EV3 phase report is empty" $run.ExitCode;throw "EV3 phase report is empty; exit=$($run.ExitCode); report=$local"}
    $json=$jsonLines-join"`n"
    try{$parsed=$json|ConvertFrom-Json}catch{Write-HostPhaseFailure "EV3 phase report is malformed: $($_.Exception.Message)" $run.ExitCode;throw}
    if($ExpectedBuildId -and $parsed.build_id-ne$ExpectedBuildId)
    {
        $parsed.status='FAIL'
        $parsed|Add-Member -NotePropertyName host_admission_failure -NotePropertyValue "build mismatch: expected=$ExpectedBuildId actual=$($parsed.build_id)" -Force
    }
    if($run.ExitCode-ne 0 -and $parsed.status-eq'PASS')
    {
        $parsed.status='FAIL'
        $parsed|Add-Member -NotePropertyName host_transport_failure -NotePropertyValue "remote command exit=$($run.ExitCode)" -Force
    }
    [System.IO.File]::WriteAllText($local,($parsed|ConvertTo-Json -Depth 12)+"`n",[System.Text.UTF8Encoding]::new($false))
    foreach($line in @($run.Output|Select-Object -First $markerIndex)){Write-Output $line}
    if($run.ExitCode-ne 0 -or $parsed.status-ne'PASS'){throw "EV3 phase failed; report=$local"}
    return $parsed
}
