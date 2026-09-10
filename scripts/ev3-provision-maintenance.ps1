<# Explicit EV3 half of fixed-pair PROVISION. Never called by routine phases. #>
param(
    [Parameter(Mandatory=$true)][ValidatePattern('^SHA256:[A-Za-z0-9+/]{43}$')][string]$HostFingerprint,
    [string]$User='root',[string]$BootstrapUser='robot',
    [Parameter(Mandatory=$true)][string]$KeyPath,
    [Parameter(Mandatory=$true)][string]$SshDirectory,
    [Parameter(Mandatory=$true)][string]$ControlKeyFile,
    [ValidateSet('any','inet','inet6')][string]$AddressFamily='any',
    [ValidateRange(5,30)][int]$ScanTimeoutSeconds=8,
    [string]$WifiSettingsFile='',[string]$WifiServiceId='',
    [string]$Destination='results/ev3/provision',[switch]$RepinHost,[switch]$Repair
)
$ErrorActionPreference='Stop'
$started=(Get-Date).ToUniversalTime()
$target='ev3dev.local'
$repository=Split-Path -Parent $PSScriptRoot
$sshDirectoryPath=[IO.Path]::GetFullPath($SshDirectory)
$keyPathFull=[IO.Path]::GetFullPath($KeyPath)
$controlPath=[IO.Path]::GetFullPath($ControlKeyFile)
$knownHostsPath=Join-Path $sshDirectoryPath 'known_hosts'
$configPath=Join-Path $sshDirectoryPath 'config'

foreach($required in @($keyPathFull,($keyPathFull+'.pub'),$controlPath))
{if(!(Test-Path -LiteralPath $required -PathType Leaf)){throw "PROVISION_CORRUPT: private provisioning input is missing: $required"}}
$controlBytes=[IO.File]::ReadAllBytes($controlPath)
try
{
    $trimmed=$controlBytes
    while($trimmed.Length-gt 0 -and @(9,10,13,32)-contains$trimmed[$trimmed.Length-1]){$trimmed=$trimmed[0..($trimmed.Length-2)]}
    $isHex=$trimmed.Length-eq 64 -and -not @($trimmed|Where-Object{-not(('0123456789abcdefABCDEF').ToCharArray()-contains[char]$_)}).Count
    if(!$isHex -and $trimmed.Length-lt 32){throw 'PROVISION_CORRUPT: CONTROL PSK does not satisfy minimum entropy length'}
}
finally{if($controlBytes){[Array]::Clear($controlBytes,0,$controlBytes.Length)}}
if($WifiSettingsFile)
{
    if($WifiServiceId-notmatch'^wifi_[A-Za-z0-9_]+$'){throw 'PROVISION_CORRUPT: unsafe ConnMan Wi-Fi service id'}
    $wifiPath=[IO.Path]::GetFullPath($WifiSettingsFile)
    if(!(Test-Path -LiteralPath $wifiPath -PathType Leaf)){throw 'PROVISION_CORRUPT: Wi-Fi settings file is missing'}
}
elseif($WifiServiceId){throw 'PROVISION_CORRUPT: WifiServiceId requires WifiSettingsFile'}

New-Item -ItemType Directory -Force -Path $sshDirectoryPath|Out-Null
function Get-Fingerprint([string]$Line)
{
    $parts=$Line.Trim()-split'\s+'
    if($parts.Count-lt 3 -or $parts[1]-ne'ssh-ed25519'){return $null}
    try{$blob=[Convert]::FromBase64String($parts[2])}catch{return $null}
    $sha=[Security.Cryptography.SHA256]::Create()
    try{return 'SHA256:'+([Convert]::ToBase64String($sha.ComputeHash($blob)).TrimEnd('='))}finally{$sha.Dispose()}
}

$existing=@()
if(Test-Path -LiteralPath $knownHostsPath -PathType Leaf)
{$existing=@(Get-Content -LiteralPath $knownHostsPath -Encoding UTF8|Where-Object{$_-match'^ev3dev\.local\s+ssh-ed25519\s+'})}
if($existing.Count -and !$RepinHost)
{
    $approved=@($existing|Where-Object{(Get-Fingerprint $_)-eq$HostFingerprint})
    if($approved.Count-ne$existing.Count){throw 'HOST_KEY_MISMATCH: stored EV3 host key differs from the trusted fingerprint'}
}
else
{
    $scanArgs=@('-T',$ScanTimeoutSeconds,'-t','ed25519')
    if($AddressFamily-eq'inet'){$scanArgs=@('-4')+$scanArgs}elseif($AddressFamily-eq'inet6'){$scanArgs=@('-6')+$scanArgs}
    $sshKeyscan=(Get-Command ssh-keyscan -ErrorAction Stop).Source
    $scanRun=Invoke-PhantomProcess $sshKeyscan (@($scanArgs)+$target) ($ScanTimeoutSeconds+3) 'DEVICE_NOT_FOUND'
    if($scanRun.ExitCode-ne 0){throw "DEVICE_NOT_FOUND: ssh-keyscan exited with code $($scanRun.ExitCode)"}
    $scan=@($scanRun.Output)
    $matching=@($scan|Where-Object{(Get-Fingerprint $_)-eq$HostFingerprint})
    $distinct=@($matching|ForEach-Object{($_-split'\s+')[2]}|Sort-Object -Unique)
    if($distinct.Count-eq 0){throw 'HOST_KEY_MISMATCH: discovered EV3 key does not match the trusted fingerprint'}
    if($distinct.Count-ne 1){throw 'AMBIGUOUS_DEVICE: ev3dev.local resolved to multiple trusted host keys'}
    $parts=$matching[0]-split'\s+'
    $approved=@("ev3dev.local $($parts[1]) $($parts[2])")
    [IO.File]::WriteAllLines($knownHostsPath,[string[]]$approved,[Text.UTF8Encoding]::new($false))
}

$familyLine=if($AddressFamily-eq'any'){''}else{"    AddressFamily $AddressFamily`n"}
$config="Host ev3dev.local`n${familyLine}    User $User`n    IdentityFile $keyPathFull`n    IdentitiesOnly yes`n    BatchMode yes`n    ConnectTimeout 8`n    ServerAliveInterval 5`n    ServerAliveCountMax 6`n    StrictHostKeyChecking yes`n    UserKnownHostsFile $knownHostsPath`n"
if(Test-Path -LiteralPath $configPath -PathType Leaf)
{
    if((Get-Content -LiteralPath $configPath -Raw -Encoding UTF8)-ne$config)
    {
        if(!$Repair){throw 'PROVISION_CORRUPT: existing EV3 SSH config differs; use explicit pair repair'}
        [IO.File]::WriteAllText($configPath,$config,[Text.UTF8Encoding]::new($false))
    }
}
else{[IO.File]::WriteAllText($configPath,$config,[Text.UTF8Encoding]::new($false))}

$ssh=(Get-Command ssh -ErrorAction Stop).Source
$scp=(Get-Command scp -ErrorAction Stop).Source
$deploymentProbe=Invoke-PhantomProcess $ssh @('-F',$configPath,'-o','BatchMode=yes',$target,'--','true') 45 'DEVICE_NOT_FOUND'
if($deploymentProbe.ExitCode-ne 0)
{
    if($BootstrapUser-notmatch'^[A-Za-z0-9._-]+$'){throw 'PROVISION_REQUIRED: a trusted bootstrap user is required to install the deployment key'}
    $bootstrapTarget="$BootstrapUser@$target"
    $bootstrapArgs=@('-o','StrictHostKeyChecking=yes','-o',"UserKnownHostsFile=$knownHostsPath",'-o','ConnectTimeout=8')
    & $scp -O @bootstrapArgs ($keyPathFull+'.pub') (Join-Path $repository 'provision/ev3/install-deployment-key') "${bootstrapTarget}:/tmp/"
    if($LASTEXITCODE-ne 0){throw 'PROVISION_REQUIRED: trusted EV3 bootstrap transfer failed'}
    & $ssh -t @bootstrapArgs $bootstrapTarget -- "sudo sh /tmp/install-deployment-key /tmp/$([IO.Path]::GetFileName($keyPathFull)).pub"
    if($LASTEXITCODE-ne 0){throw 'PROVISION_REQUIRED: trusted EV3 deployment-key installation failed'}
    & $ssh -F $configPath -o BatchMode=yes $target -- true
    if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: deployment key authentication did not become ready'}
}

$payload=@(
    (Join-Path $repository 'provision/ev3/bootstrap'),(Join-Path $repository 'provision/ev3/wifi-autoconnect'),
    (Join-Path $repository 'provision/ev3/phantom-wifi-autoconnect.service'),
    (Join-Path $repository 'deploy/scripts/install-release'),(Join-Path $repository 'deploy/scripts/start-release'),
    (Join-Path $repository 'deploy/scripts/run-device-integration-test'),(Join-Path $repository 'deploy/scripts/rollback-release')
)
foreach($source in $payload){if(!(Test-Path -LiteralPath $source -PathType Leaf)){throw "PROVISION_CORRUPT: provisioning payload is missing: $source"}}
$remoteDirectory='/tmp/phantom-maintenance-provision'
& $ssh -F $configPath $target -- "rm -rf '$remoteDirectory'; install -d -m 0700 '$remoteDirectory'"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 provisioning directory creation failed'}
& $scp -q -O -F $configPath @payload "${target}:$remoteDirectory/"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 maintenance payload transfer failed'}
& $scp -q -O -F $configPath $controlPath "${target}:$remoteDirectory/control.psk"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 CONTROL credential transfer failed'}
$wifiArgs=''
if($WifiSettingsFile)
{
    & $scp -q -O -F $configPath $wifiPath "${target}:$remoteDirectory/wifi.settings"
    if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 Wi-Fi profile transfer failed'}
    $wifiArgs=" '$WifiServiceId' 'wifi.settings'"
}
& $ssh -F $configPath $target -- "sh '$remoteDirectory/bootstrap' '$remoteDirectory' 'control.psk'$wifiArgs; rm -rf '$remoteDirectory'"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 platform provisioning failed'}
& $ssh -F $configPath $target -- "test -s /var/lib/phantom/secrets/control.psk && test -x /usr/local/libexec/phantom-maintenance/start-release"
if($LASTEXITCODE-ne 0){throw 'PROVISION_CORRUPT: EV3 provisioning verification failed'}

$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase='PROVISION';component='EV3';profile='N_A';status='PASS';reason='PROVISIONED';build_id=$null;artifact_sha256=$null;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds;terminal_state='RUNTIME_NOT_STARTED';hardware_evidence_state='NOT_QUALIFICATION_EVIDENCE';secret_material_logged=$false}
New-Item -ItemType Directory -Force -Path $Destination|Out-Null
[IO.File]::WriteAllText((Join-Path ([IO.Path]::GetFullPath($Destination)) 'provision.json'),($report|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output 'EV3 PROVISION: PASS maintenance, CONTROL credential and provisioned Wi-Fi state verified; runtime not started'
