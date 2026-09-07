<#
.SYNOPSIS
Prune stale artifacts from build/ without touching the current candidate.

.DESCRIPTION
`build/` accumulates every package, audit snapshot and profile directory ever
produced. Nothing deletes them, and `tools/artifact_check.py` selects packages by
name pattern, so an old tarball can sit next to the current one indefinitely.

This script keeps only what the current source tree can still be held to:
artifacts whose build_id appears in the current `build/ev3-armel/*/build-manifest.json`,
plus the newest `-Keep` of everything else. It never deletes anything by default;
run with `-Apply` once the listed plan looks right.

Audit snapshots (`phantom-audit-snapshot-*`) are never produced from a clean
worktree and are always prunable.
#>
param(
    [int]$Keep=3,
    [switch]$Apply,
    [switch]$IncludeAuditSnapshots=$true
)
$ErrorActionPreference="Stop"
$root=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$build=Join-Path $root "build"
if(!(Test-Path -LiteralPath $build)){Write-Output "nothing to clean: $build does not exist";exit 0}

$currentBuildIds=@()
Get-ChildItem (Join-Path $build "ev3-armel/*/build-manifest.json") -File -ErrorAction SilentlyContinue|ForEach-Object{
    $currentBuildIds+=(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id
}
Get-ChildItem (Join-Path $build "ev3-host-*/build-manifest.json") -File -ErrorAction SilentlyContinue|ForEach-Object{
    $currentBuildIds+=(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id
}
$currentBuildIds=@($currentBuildIds|Where-Object {$_}|Sort-Object -Unique)
Write-Output ("current build ids: " + ($(if($currentBuildIds){$currentBuildIds -join ', '}else{'(none)'})))

$packages=@(Get-ChildItem (Join-Path $build "ev3-packages") -File -ErrorAction SilentlyContinue|Sort-Object LastWriteTime -Descending)
$doomed=New-Object System.Collections.Generic.List[System.IO.FileInfo]
$keptRecent=0
foreach($file in $packages)
{
    $isCurrent=$false
    foreach($id in $currentBuildIds){if($file.Name.Contains($id)){$isCurrent=$true;break}}
    $isSnapshot=$file.Name.StartsWith("phantom-audit-snapshot")
    if($isCurrent){continue}
    if($isSnapshot -and $IncludeAuditSnapshots){$doomed.Add($file);continue}
    if($keptRecent -lt $Keep){$keptRecent++;continue}
    $doomed.Add($file)
}

$diffs=@(Get-ChildItem (Join-Path $build "diffs") -File -ErrorAction SilentlyContinue|Sort-Object LastWriteTime -Descending|Select-Object -Skip $Keep)
foreach($file in $diffs){$doomed.Add($file)}

$total=0
foreach($file in $doomed){$total+=$file.Length}
if($doomed.Count -eq 0){Write-Output "build/ is already within policy (keep=$Keep + current build ids)";exit 0}

Write-Output ("prunable: {0} files, {1:N1} MB" -f $doomed.Count,($total/1MB))
foreach($file in $doomed){Write-Output ("  " + $file.FullName.Substring($root.Length+1))}
if(!$Apply){Write-Output "";Write-Output "dry run. Re-run with -Apply to delete.";exit 0}
foreach($file in $doomed){Remove-Item -LiteralPath $file.FullName -Force}
Write-Output ("removed {0} files" -f $doomed.Count)
