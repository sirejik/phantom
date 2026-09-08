<#
.SYNOPSIS
Preview or apply cleanup of disposable build output.

.DESCRIPTION
Default mode removes caches/intermediates/backups and stale deploy packages while retaining
current final APK/EV3 packages. `-All` selects every child of build/. Dry-run is the default;
add `-Apply` to delete. Provisioning and `.secrets/**` are never in scope.
#>
param([int]$Keep=2,[switch]$All,[switch]$Apply,[string]$BuildRoot='')
$ErrorActionPreference='Stop';$repo=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$repositoryBuild=[IO.Path]::GetFullPath((Join-Path $repo 'build')).TrimEnd('\')
$build=if($BuildRoot){[IO.Path]::GetFullPath($BuildRoot).TrimEnd('\')}else{$repositoryBuild}
if($build.TrimEnd('\')-eq$repo.TrimEnd('\')-or$build-match'(?i)(^|[\\/])\.secrets([\\/]|$)'){throw "Unsafe build cleanup root: $build"}
if($build-ne$repositoryBuild-and!$build.StartsWith($repositoryBuild+'\',[StringComparison]::OrdinalIgnoreCase)){throw "Build root escaped repository build directory: $build"}
if(!(Test-Path -LiteralPath $build -PathType Container)){Write-Output "nothing to clean: $build does not exist";exit 0}

$targets=New-Object 'System.Collections.Generic.List[System.IO.FileSystemInfo]'
if($All)
{
    Get-ChildItem -LiteralPath $build -Force|ForEach-Object{$targets.Add($_)}
}
else
{
    Get-ChildItem -LiteralPath $build -Directory -Recurse -Force -ErrorAction SilentlyContinue|Where-Object{
        $_.Name-like'*_BackUpThisFolder_ButDontShipItWithYourGame'-or
        $_.Name-in @('Temp','tmp','intermediates','.gradle','diffs')-or
        $_.Name-like'ev3-host-*'
    }|ForEach-Object{$targets.Add($_)}
    $packages=@(Get-ChildItem -LiteralPath (Join-Path $build 'ev3-packages') -File -ErrorAction SilentlyContinue|Sort-Object LastWriteTime -Descending)
    $groups=$packages|Group-Object {if($_.Name-like'*.tar.gz'){'archive'}elseif($_.Name-like'*.build-manifest.json'){'manifest'}elseif($_.Name-like'*.build-result.json'){'result'}else{'other'}}
    foreach($group in $groups){$group.Group|Select-Object -Skip $Keep|ForEach-Object{$targets.Add($_)}}
}
$targets=@($targets|Sort-Object FullName -Unique|Where-Object{
    $candidate=[IO.Path]::GetFullPath($_.FullName);$candidate.StartsWith($build.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)
})
if(!$targets){Write-Output 'build cleanup: nothing selected';exit 0}
$bytes=0;foreach($target in $targets){if(!$target.PSIsContainer){$bytes+=$target.Length}}
Write-Output ("selected: {0} entries, at least {1:N1} MB" -f $targets.Count,($bytes/1MB));$targets|ForEach-Object{Write-Output ('  '+$_.FullName)}
if(!$Apply){Write-Output 'dry run; add -Apply to delete';exit 0}
foreach($target in ($targets|Sort-Object {$_.FullName.Length} -Descending)){Remove-Item -LiteralPath $target.FullName -Recurse -Force}
Write-Output ("removed {0} entries" -f $targets.Count)
