param(
    [ValidateSet('Release','Diagnostic')][string]$Profile='Diagnostic',
    [ValidatePattern('^[a-zA-Z0-9_.|^$()+*?\\-]+$')][string]$Filter='.*',
    [ValidateRange(1,600)][int]$TimeoutSeconds=600
)
$ErrorActionPreference='Stop';. "$PSScriptRoot/../tools/toolchain.ps1";$distro=Get-PhantomWslDistro
$wslBuild="/tmp/phantom-ev3-test-$($Profile.ToLower())";$source=Get-PhantomWslPath ev3;$diagnostic=if($Profile-eq'Release'){'OFF'}else{'ON'}
wsl.exe -d $distro -- timeout $TimeoutSeconds bash -lc "rm -rf '$wslBuild' && cmake -S '$source' -B '$wslBuild' -G Ninja -DCMAKE_BUILD_TYPE=Debug -DPHANTOM_DIAGNOSTIC=$diagnostic -DPHANTOM_BUILD_TESTS=ON && cmake --build '$wslBuild' && ctest --test-dir '$wslBuild' --output-on-failure --no-tests=error --timeout 30 -R '$Filter'"
if($LASTEXITCODE-ne 0){throw "EV3 TEST failed: $Profile"}
