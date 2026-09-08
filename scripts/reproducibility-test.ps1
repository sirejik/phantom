<# Explicit TEST: build one selected component twice from the same semantic inputs. #>
param(
    [Parameter(Mandatory=$true)][ValidateSet('EV3','QUEST')][string]$Component,
    [ValidateSet('Diagnostic','DeepDebug','Release')][string]$Profile='Diagnostic',
    [string]$Workspace='build/reproducibility'
)
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($Workspace)
New-Item -ItemType Directory -Force -Path $root|Out-Null

function Invoke-One([string]$label)
{
    if($Component-eq'EV3')
    {
        $out=Join-Path $root "$label-ev3";$packages=Join-Path $root "$label-packages"
        & "$PSScriptRoot/ev3-build.ps1" -Profile $Profile -OutputRoot $out -PackageRoot $packages | Out-Host
        if($LASTEXITCODE-ne 0){throw "EV3 reproducibility BUILD $label failed"}
        $manifest=Get-Content -LiteralPath (Join-Path $out "$($Profile.ToLowerInvariant())/build-manifest.json") -Raw -Encoding UTF8|ConvertFrom-Json
        $artifact=Join-Path $packages "phantom-$($manifest.build_id).tar.gz"
    }
    else
    {
        $artifact=Join-Path $root "$label-quest.apk"
        & "$PSScriptRoot/quest-build.ps1" -Profile $Profile -Output $artifact | Out-Host
        if($LASTEXITCODE-ne 0){throw "Quest reproducibility BUILD $label failed"}
        $manifest=Get-Content -LiteralPath ($artifact+'.build-manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
    }
    return [pscustomobject]@{BuildId=$manifest.build_id;ArtifactSha256=(Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLowerInvariant();Artifact=$artifact}
}

$a=Invoke-One 'a';$b=Invoke-One 'b'
if($a.BuildId-ne$b.BuildId){throw "Reproducibility FAIL: build_id differs: $($a.BuildId) / $($b.BuildId)"}
$byteReproducible=$a.ArtifactSha256-eq$b.ArtifactSha256
$questDifference=$null
if($Component-eq'QUEST' -and !$byteReproducible)
{
    $differenceJson=& python "$PSScriptRoot/../tools/apk_repro_diff.py" $a.Artifact $b.Artifact
    if($LASTEXITCODE-ne 0){throw 'Quest APK reproducibility difference analysis failed'}
    $questDifference=$differenceJson|ConvertFrom-Json
}
$report=[ordered]@{schema_version=1;phase='TEST';test_id='build-reproducibility';status=if($Component-eq'EV3' -and !$byteReproducible){'FAIL'}else{'PASS'};component=$Component;profile=$Profile;build_id=$a.BuildId;artifact_a_sha256=$a.ArtifactSha256;artifact_b_sha256=$b.ArtifactSha256;byte_reproducible=$byteReproducible;quest_nondeterminism_requires_review=($Component-eq'QUEST' -and !$byteReproducible);quest_difference=$questDifference}
$path=Join-Path $root "$($Component.ToLowerInvariant())-$($Profile.ToLowerInvariant())-report.json"
[IO.File]::WriteAllText($path,($report|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
if($report.status-ne'PASS'){throw "Reproducibility FAIL: EV3 package SHA-256 differs; report=$path"}
Write-Output "Reproducibility: PASS component=$Component build_id=$($a.BuildId) byte_reproducible=$byteReproducible report=$path"
