<# Preview or remove all disposable local lifecycle reports under repository results/. #>
param([switch]$Apply)
$ErrorActionPreference='Stop'
$repository=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$expected=[IO.Path]::GetFullPath((Join-Path $repository 'results')).TrimEnd('\')
if(!(Test-Path -LiteralPath $expected -PathType Container)){Write-Output "nothing to clean: $expected does not exist";exit 0}
$resolved=(Resolve-Path -LiteralPath $expected).Path.TrimEnd('\')
if($resolved-ne$expected-or!$resolved.StartsWith($repository.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)){throw "Unsafe results cleanup root: $resolved"}
$targets=@(Get-ChildItem -LiteralPath $resolved -Force)
if(!$targets){Write-Output 'results cleanup: nothing selected';exit 0}
Write-Output ("selected: {0} result roots" -f $targets.Count)
$targets|ForEach-Object{Write-Output ('  '+$_.FullName)}
if(!$Apply){Write-Output 'dry run; add -Apply to delete';exit 0}
foreach($target in $targets){Remove-Item -LiteralPath $target.FullName -Recurse -Force}
Write-Output ("removed {0} result roots" -f $targets.Count)
