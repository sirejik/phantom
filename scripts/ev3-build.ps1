param(
    [ValidateSet('Release','Diagnostic','DeepDebug')][string]$Profile='Diagnostic',
    [string]$OutputRoot='build/ev3-armel',
    [string]$PackageRoot='build/ev3-packages'
)
$ErrorActionPreference='Stop'
foreach($check in @(
    @('tools/protocolgen.py','--check'),
    @('tools/configgen.py','--check')))
{
    & python $check[0] $check[1]
    if($LASTEXITCODE-ne 0){throw "EV3 BUILD prerequisite consistency check failed: $($check[0])"}
}
& "$PSScriptRoot/ev3-armel-docker.ps1" -Profile $Profile -Output $OutputRoot
if($LASTEXITCODE-ne 0){throw "EV3 BUILD compile failed: $Profile"}
& "$PSScriptRoot/ev3-package.ps1" -Profile $Profile -InputRoot $OutputRoot -OutputRoot $PackageRoot
if($LASTEXITCODE-ne 0){throw "EV3 BUILD package validation failed: $Profile"}
$manifest=Get-Content -LiteralPath (Join-Path ([IO.Path]::GetFullPath($OutputRoot)) "$($Profile.ToLowerInvariant())/build-manifest.json") -Raw -Encoding UTF8|ConvertFrom-Json
$package=Join-Path ([IO.Path]::GetFullPath($PackageRoot)) "phantom-$($manifest.build_id).tar.gz"
python tools/artifact_check.py --component EV3 --profile $Profile --artifact $package --ev3-directory (Join-Path ([IO.Path]::GetFullPath($OutputRoot)) $($Profile.ToLowerInvariant()))
if($LASTEXITCODE-ne 0){throw "EV3 BUILD artifact validation failed: $Profile"}
