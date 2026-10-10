# Internal environment preparation and optional build reproducibility operation.
# Compilation and packaging belong to the two BUILD entry points.
. "$PSScriptRoot/../tools/toolchain.ps1"
function Get-PhantomEv3ToolchainLockPath
{
    return Join-Path (Get-PhantomRepositoryRoot) (Get-PhantomHostToolsManifest).docker.ev3_toolchain_lock
}
function Get-PhantomEv3ToolchainLock
{
    return Get-Content -LiteralPath (Get-PhantomEv3ToolchainLockPath) -Raw -Encoding UTF8 | ConvertFrom-Json
}
function Get-PhantomEv3CrossImage
{
    $lock=Get-PhantomEv3ToolchainLock
    if($lock.cross_image_digest -notmatch '^sha256:[0-9a-f]{64}$'){throw 'EV3 cross image must be pinned by SHA-256'}
    return "$($lock.cross_image)@$($lock.cross_image_digest)"
}
function Get-PhantomEv3BuildCommand([ValidateSet('Diagnostic','Release')][string]$Profile)
{
    $buildType=if($Profile-eq'Release'){'Release'}else{'RelWithDebInfo'}
    $diagnostic=if($Profile-eq'Release'){'OFF'}else{'ON'}
    # Keep compiler facts tied to the compiler actually selected by CMake.
    $command="cmake -H/workspace/ev3 -B/tmp/phantom-cross -DCMAKE_BUILD_TYPE=__TYPE__ -DPHANTOM_DIAGNOSTIC=__DIAGNOSTIC__ -DPHANTOM_BUILD_TESTS=OFF -DCMAKE_TOOLCHAIN_FILE=/workspace/ev3/toolchains/armel.cmake && cmake --build /tmp/phantom-cross -- -j2 && cmake -DCMAKE_INSTALL_PREFIX=/out -P /tmp/phantom-cross/cmake_install.cmake && cp /tmp/phantom-cross/toolchain-facts.txt /out/toolchain-facts.txt"
    return $command.Replace('__TYPE__',$buildType).Replace('__DIAGNOSTIC__',$diagnostic)
}
function Assert-PhantomEv3BuildEnvironment
{
    $image=Get-PhantomEv3CrossImage
    $kind=& docker info --format '{{.OSType}}'
    if($LASTEXITCODE-ne 0){throw 'Docker daemon is unavailable; start Docker Desktop before EV3 BUILD'}
    if($kind-ne 'linux'){throw 'EV3 BUILD requires the Docker Linux container engine'}
    & docker image inspect $image --format '{{.Id}}' | Out-Null
    if($LASTEXITCODE-ne 0){throw "Pinned EV3 image is unavailable; pull $image"}
    return $image
}
function Assert-PhantomQuestBuildEnvironment
{
    $unity=Get-PhantomUnityExe
    $data=Get-PhantomUnityEditorData
    foreach($relative in @('PlaybackEngines/AndroidPlayer/OpenJDK/bin/javac.exe','PlaybackEngines/AndroidPlayer/SDK'))
    {if(!(Test-Path -LiteralPath (Join-Path $data $relative))){throw "Unity Android build support is missing: $relative"}}
    return $unity
}

function Invoke-PhantomBuildReproducibility([string]$Component,[string]$Profile,[string]$Workspace)
{
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
$differenceClass=if($byteReproducible){'BYTE_IDENTICAL'}elseif($Component-eq'QUEST'){'BYTE_DIFFERENCE_REVIEW_REQUIRED'}else{'UNEXPECTED_BYTE_DIFFERENCE'}
$questDifference=$null
if($Component-eq'QUEST' -and !$byteReproducible)
{
    Write-Output 'APK hashes differ; compare packages with a ZIP comparison tool'
}
$report=[ordered]@{schema_version=2;phase='TEST';test_id='build-reproducibility';status=if($Component-eq'EV3' -and !$byteReproducible){'FAIL'}else{'PASS'};component=$Component;profile=$Profile;build_id=$a.BuildId;build_identity_stable=$true;artifact_a_sha256=$a.ArtifactSha256;artifact_b_sha256=$b.ArtifactSha256;artifact_byte_reproducible=$byteReproducible;difference_class=$differenceClass;difference_requires_review=($Component-eq'QUEST' -and !$byteReproducible);quest_difference=$questDifference}
$path=Join-Path $root "$($Component.ToLowerInvariant())-$($Profile.ToLowerInvariant())-report.json"
[IO.File]::WriteAllText($path,($report|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
if($report.status-ne'PASS'){throw "Reproducibility FAIL: EV3 package SHA-256 differs; report=$path"}
Write-Output "Reproducibility: PASS component=$Component build_identity_stable=true artifact_byte_reproducible=$byteReproducible difference_class=$differenceClass report=$path"

}
