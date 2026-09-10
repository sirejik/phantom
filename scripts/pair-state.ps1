# Private workstation state for the single designated Quest 3 + EV3 pair.
# The default lives outside the repository, build outputs, and results/evidence.

function Get-PhantomPairStateRoot([string]$StateRoot='')
{
    if($StateRoot){return [IO.Path]::GetFullPath($StateRoot)}
    if($env:PHANTOM_PAIR_STATE_ROOT){return [IO.Path]::GetFullPath($env:PHANTOM_PAIR_STATE_ROOT)}
    $local=[Environment]::GetFolderPath([Environment+SpecialFolder]::LocalApplicationData)
    if(!$local){throw 'PROVISION_CORRUPT: LocalApplicationData is unavailable'}
    return Join-Path $local 'PHANTOM'
}

function Get-PhantomPairPaths([string]$StateRoot='')
{
    $root=Get-PhantomPairStateRoot $StateRoot
    return [pscustomobject]@{
        Root=$root
        Record=(Join-Path $root 'pair.json')
        SshDirectory=(Join-Path $root 'ssh')
        SshKey=(Join-Path $root 'ssh/id_ed25519')
        SshConfig=(Join-Path $root 'ssh/config')
        KnownHosts=(Join-Path $root 'ssh/known_hosts')
        SecretDirectory=(Join-Path $root 'secrets')
        ControlSecret=(Join-Path $root 'secrets/control.psk')
    }
}

function Set-PhantomPrivateAcl([string]$Path)
{
    if($env:OS-ne'Windows_NT'){return}
    $account=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    & (Get-Command icacls.exe -ErrorAction Stop).Source $Path '/inheritance:r' '/grant:r' "${account}:(F)"|Out-Null
    if($LASTEXITCODE-ne 0){throw "PROVISION_CORRUPT: private ACL could not be applied: $Path"}
}

function Read-PhantomPairState([string]$StateRoot='',[switch]$RequirePrivateFiles)
{
    $paths=Get-PhantomPairPaths $StateRoot
    if(!(Test-Path -LiteralPath $paths.Record -PathType Leaf))
    {throw "PROVISION_REQUIRED: fixed-pair record is missing: $($paths.Record)"}
    try{$state=Get-Content -LiteralPath $paths.Record -Raw -Encoding UTF8|ConvertFrom-Json}
    catch{throw "PROVISION_CORRUPT: fixed-pair record is malformed: $($_.Exception.Message)"}
    $valid=$state.provision_schema_version-eq 1 -and
        $state.provision_status-eq'complete' -and
        $state.quest_adb_serial -is [string] -and $state.quest_adb_serial-match'^[A-Za-z0-9._:-]{1,128}$' -and
        $state.ev3_hostname-eq'ev3dev.local' -and
        $state.ev3_host_key_fingerprint -is [string] -and $state.ev3_host_key_fingerprint-match'^SHA256:[A-Za-z0-9+/]{43}$' -and
        $state.robot_id -is [string] -and $state.robot_id-match'^[A-Za-z0-9._-]{1,32}$' -and
        $state.control_key_id -is [string] -and $state.control_key_id-match'^[A-Za-z0-9._-]{1,64}$'
    if(!$valid){throw 'PROVISION_CORRUPT: fixed-pair record has invalid or incomplete fields'}
    if($RequirePrivateFiles)
    {
        foreach($required in @($paths.SshKey,$paths.SshConfig,$paths.KnownHosts,$paths.ControlSecret))
        {if(!(Test-Path -LiteralPath $required -PathType Leaf)){throw "PROVISION_CORRUPT: private pair file is missing: $required"}}
    }
    return [pscustomobject]@{State=$state;Paths=$paths}
}

function Write-PhantomPairState([object]$State,[string]$StateRoot='')
{
    $paths=Get-PhantomPairPaths $StateRoot
    New-Item -ItemType Directory -Force -Path $paths.Root|Out-Null
    $temporary=$paths.Record+'.tmp'
    [IO.File]::WriteAllText($temporary,($State|ConvertTo-Json -Depth 5 -Compress)+"`n",[Text.UTF8Encoding]::new($false))
    Set-PhantomPrivateAcl $temporary
    Move-Item -LiteralPath $temporary -Destination $paths.Record -Force
    Set-PhantomPrivateAcl $paths.Record
}

function Join-PhantomProcessArguments([string[]]$Arguments)
{
    return (@($Arguments|ForEach-Object{'"'+$_.Replace('"','\"')+'"'})-join' ')
}

function Invoke-PhantomProcess([string]$File,[string[]]$Arguments,[ValidateRange(1,600)][int]$TimeoutSeconds=15,[string]$TimeoutCode='OPERATION_TIMEOUT')
{
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName=$File;$info.Arguments=Join-PhantomProcessArguments $Arguments
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
    return [pscustomobject]@{ExitCode=$process.ExitCode;Output=@(($stdout.Result+"`n"+$stderr.Result)-split"`r?`n"|Where-Object{$_})}
}

function New-PhantomDeploymentKey([string]$Path)
{
    $sshKeygen=(Get-Command ssh-keygen -ErrorAction Stop).Source
    # Windows PowerShell drops a directly supplied empty native argument. The
    # bounded process helper quotes every argument and preserves -N "".
    $run=Invoke-PhantomProcess $sshKeygen @('-q','-t','ed25519','-N','','-C','PHANTOM deployment key','-f',$Path) 15 'PROVISION_CORRUPT'
    if($run.ExitCode-ne 0){throw "PROVISION_CORRUPT: deployment SSH key generation failed (exit=$($run.ExitCode))"}
}

function Invoke-PhantomAdb([string]$Adb,[string]$Serial,[string[]]$Arguments,[ValidateRange(1,300)][int]$TimeoutSeconds=15)
{
    $all=if($Serial){@('-s',$Serial)+$Arguments}else{$Arguments}
    $run=Invoke-PhantomProcess $Adb $all $TimeoutSeconds 'DEVICE_NOT_FOUND'
    if($run.ExitCode-ne 0){throw "DEVICE_NOT_FOUND: adb exited with code $($run.ExitCode): $($run.Output-join' ')"}
    return $run.Output
}

function Get-PhantomQuestDevice([string]$Adb,[string]$StateRoot='')
{
    $pair=Read-PhantomPairState $StateRoot
    $expected=$pair.State.quest_adb_serial
    $connected=@(Invoke-PhantomAdb $Adb '' @('devices') 8|Select-Object -Skip 1|Where-Object{$_-match'\sdevice$'}|ForEach-Object{($_-split'\s+')[0]})
    if($connected -contains $expected){return $expected}
    if($connected.Count-eq 0){throw 'QUEST_NOT_FOUND: designated Quest is not connected or not authorized'}
    throw 'QUEST_IDENTITY_MISMATCH: connected ADB device is not the designated Quest'
}
