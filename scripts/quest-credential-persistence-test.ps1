<# Explicit hardware regression for PROVISION persistence across an in-place APK update. #>
param(
    [Parameter(Mandatory=$true)][string]$ApkA,
    [Parameter(Mandatory=$true)][string]$ApkB,
    [Parameter(Mandatory=$true)][string]$KeyFile,
    [string]$Package='dev.phantom.questprototype',
    [string]$Destination='results/quest/credential-persistence'
)
$ErrorActionPreference='Stop'

function Read-BuildId([string]$Apk)
{
    $resolved=[IO.Path]::GetFullPath($Apk)
    $sidecar=$resolved+'.build-manifest.json'
    if(!(Test-Path -LiteralPath $resolved -PathType Leaf) -or !(Test-Path -LiteralPath $sidecar -PathType Leaf))
    {throw "APK or sidecar is missing: $resolved"}
    $manifest=Get-Content -LiteralPath $sidecar -Raw -Encoding UTF8|ConvertFrom-Json
    if($manifest.component-ne'QUEST' -or $manifest.build_id-notmatch'^[0-9a-f]{64}$'){throw "Invalid Quest manifest: $sidecar"}
    return $manifest.build_id
}

$started=(Get-Date).ToUniversalTime();$buildA=Read-BuildId $ApkA;$buildB=Read-BuildId $ApkB
if($buildA-eq$buildB){throw 'Persistence regression requires two distinct Quest builds'}

& "$PSScriptRoot/quest-provision-credential.ps1" -KeyFile $KeyFile -Package $Package
if($LASTEXITCODE-ne 0){throw 'PROVISION failed'}
& "$PSScriptRoot/quest-install.ps1" -Apk $ApkA -Package $Package
if($LASTEXITCODE-ne 0){throw 'Build A INSTALL failed'}
& "$PSScriptRoot/quest-start.ps1" -Package $Package -ExpectedBuildId $buildA
if($LASTEXITCODE-ne 0){throw 'Build A did not authenticate with provisioned credential'}
& "$PSScriptRoot/quest-install.ps1" -Apk $ApkB -Package $Package
if($LASTEXITCODE-ne 0){throw 'Build B in-place INSTALL failed'}
& "$PSScriptRoot/quest-start.ps1" -Package $Package -ExpectedBuildId $buildB
if($LASTEXITCODE-ne 0){throw 'Credential did not survive the in-place update to build B'}

$finished=(Get-Date).ToUniversalTime();$report=[ordered]@{schema_version=1;phase='DEVICE INTEGRATION TEST';test_id='quest-control-credential-persistence';status='PASS';build_a=$buildA;build_b=$buildB;install_mode='adb install -r -g';credential_contents_recorded=$false;started_at=$started.ToString('o');finished_at=$finished.ToString('o');duration_ms=[long]($finished-$started).TotalMilliseconds}
New-Item -ItemType Directory -Force -Path $Destination|Out-Null
$path=Join-Path ([IO.Path]::GetFullPath($Destination)) 'report.json'
[IO.File]::WriteAllText($path,($report|ConvertTo-Json -Depth 6)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "QUEST credential persistence: PASS build_a=$buildA build_b=$buildB report=$path"
