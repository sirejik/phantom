<# Explicit one-time PROVISION of the EV3 maintenance target and platform helpers. #>
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9.:%-]+$')][string]$Address,
    [Parameter(Mandatory=$true)][ValidatePattern('^SHA256:[A-Za-z0-9+/=]+$')][string]$HostFingerprint,
    [string]$User='root',[string]$KeyPath='.ev3-ssh/id_ed25519',
    [string]$Target='phantom-ev3',[string]$SshDirectory='.ev3-ssh'
)
$ErrorActionPreference='Stop'
if($User-notmatch'^[A-Za-z0-9._-]+$' -or $Target-notmatch'^[A-Za-z0-9._-]+$'){throw 'Unsafe EV3 SSH identity input'}
$key=[System.IO.Path]::GetFullPath($KeyPath)
if(!(Test-Path -LiteralPath $key -PathType Leaf)){throw "EV3 SSH identity is missing: $key"}
$sshRoot=[System.IO.Path]::GetFullPath($SshDirectory);New-Item -ItemType Directory -Force -Path $sshRoot|Out-Null
$knownHosts=Join-Path $sshRoot 'known_hosts';$config=Join-Path $sshRoot 'config'
$scan=@(& (Get-Command ssh-keyscan -ErrorAction Stop).Source -T 8 $Address 2>$null)
if(!$scan){throw "EV3_UNREACHABLE: could not read host key from $Address"}
$temp=Join-Path $sshRoot ('hostkey-'+[guid]::NewGuid().ToString('N'))
try
{
    $approved=New-Object 'System.Collections.Generic.List[string]'
    foreach($line in $scan)
    {
        [System.IO.File]::WriteAllText($temp,$line+"`n",[System.Text.UTF8Encoding]::new($false))
        $fact=(@(& (Get-Command ssh-keygen -ErrorAction Stop).Source -lf $temp -E sha256)|Select-Object -First 1)
        if($fact-match'\s(SHA256:[A-Za-z0-9+/=]+)\s' -and $Matches[1]-eq$HostFingerprint){$approved.Add($line)}
    }
    if($approved.Count-eq 0){throw "HOST_IDENTITY_CHANGED: expected fingerprint was not observed"}
    $aliased=$approved|ForEach-Object{$_ -replace ('^'+[regex]::Escape($Address)),$Target}
    [System.IO.File]::WriteAllLines($knownHosts,$aliased,[System.Text.UTF8Encoding]::new($false))
}
finally{if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Force}}
$configText=@"
Host $Target
    HostName $Address
    User $User
    IdentityFile $key
    IdentitiesOnly yes
    BatchMode yes
    ConnectTimeout 8
    ServerAliveInterval 5
    ServerAliveCountMax 2
    StrictHostKeyChecking yes
    UserKnownHostsFile $knownHosts
    HostKeyAlias $Target
"@
[System.IO.File]::WriteAllText($config,$configText.Replace("`r`n","`n"),[System.Text.UTF8Encoding]::new($false))

$stage=Join-Path ([System.IO.Path]::GetTempPath()) ('phantom-provision-'+[guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $stage|Out-Null
try
{
    foreach($pair in @(
        @('provision/ev3/bootstrap','bootstrap'),@('provision/ev3/wifi-autoconnect','wifi-autoconnect'),
        @('provision/ev3/phantom-wifi-autoconnect.service','phantom-wifi-autoconnect.service'),
        @('deploy/scripts/install-release','install-release'),@('deploy/scripts/start-release','start-release'),
        @('deploy/scripts/run-device-integration-test','run-device-integration-test'),@('deploy/scripts/rollback-release','rollback-release')))
    {Copy-Item -LiteralPath $pair[0] -Destination (Join-Path $stage $pair[1])}
    $scp=(Get-Command scp -ErrorAction Stop).Source
    & $scp -F $config -r $stage "${Target}:/tmp/phantom-maintenance-provision"
    if($LASTEXITCODE-ne 0){throw 'EV3 PROVISION payload transfer failed'}
    & (Get-Command ssh -ErrorAction Stop).Source -F $config $Target -- "chmod 0755 /tmp/phantom-maintenance-provision/bootstrap && /tmp/phantom-maintenance-provision/bootstrap /tmp/phantom-maintenance-provision"
    if($LASTEXITCODE-ne 0){throw 'EV3 PROVISION bootstrap failed'}
}
finally{if(Test-Path -LiteralPath $stage){Remove-Item -LiteralPath $stage -Recurse -Force}}
Write-Output "EV3 PROVISION: PASS target=$Target; Wi-Fi profile and credentials were not changed"
