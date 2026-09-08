param(
    [Parameter(Mandatory=$true)][string]$Package,
    [string]$Target='phantom-ev3',[string]$SshConfig='.ev3-ssh/config',
    [ValidateRange(1,900)][int]$TimeoutSeconds=180,
    [string]$Destination='results/ev3/transfer'
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/ev3-deploy-common.ps1"
$packagePath=[System.IO.Path]::GetFullPath($Package)
if(!(Test-Path -LiteralPath $packagePath -PathType Leaf)){throw "EV3 package is missing: $packagePath"}
$sidecar=$packagePath+'.build-manifest.json'
if(!(Test-Path -LiteralPath $sidecar -PathType Leaf)){throw "EV3 package sidecar is missing: $sidecar"}
$manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
$actualHash=(Get-FileHash -LiteralPath $packagePath -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.schema_version-ne 2 -or $manifest.component-ne'EV3' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw 'Invalid EV3 package sidecar'}
if($manifest.artifact_sha256-ne$actualHash){throw 'EV3 package hash does not match its sidecar'}

$started=(Get-Date).ToUniversalTime();$config=Get-PhantomEv3SshConfig $SshConfig
$remote="/var/lib/phantom/staging/phantom-$($manifest.build_id).tar.gz"
$scp=(Get-Command scp -ErrorAction Stop).Source
$arguments=@('-F',$config,'-o','BatchMode=yes',$packagePath,"${Target}:$remote")
$info=[System.Diagnostics.ProcessStartInfo]::new();$info.FileName=$scp
$info.Arguments=(@($arguments|ForEach-Object{'"'+$_.Replace('"','\"')+'"'})-join' ');$info.UseShellExecute=$false
$process=[System.Diagnostics.Process]::Start($info)
if(!$process.WaitForExit($TimeoutSeconds*1000)){$process.Kill();$process.WaitForExit();throw "EV3 TRANSFER exceeded ${TimeoutSeconds}s deadline"}
if($process.ExitCode-ne 0){throw "EV3 TRANSFER failed with exit $($process.ExitCode)"}
$verify=Invoke-PhantomEv3Command "test -f '$remote' && test `$(sha256sum '$remote' | sed 's/[[:space:]].*`$//') = '$actualHash'" $config $Target
if($verify.ExitCode-ne 0){throw 'EV3 TRANSFER remote SHA-256 mismatch'}
$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase='TRANSFER';status='PASS';build_id=$manifest.build_id;artifact_sha256=$actualHash;remote_staging=$remote;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds}
$reportDir=Join-Path ([System.IO.Path]::GetFullPath($Destination)) $manifest.build_id;New-Item -ItemType Directory -Force -Path $reportDir|Out-Null
$reportPath=Join-Path $reportDir 'transfer.json';[IO.File]::WriteAllText($reportPath,($report|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "EV3 TRANSFER: PASS build_id=$($manifest.build_id) report=$reportPath"
