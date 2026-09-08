param([ValidateSet('Release','Diagnostic','DeepDebug')][string]$Profile='Diagnostic')
$ErrorActionPreference='Stop';. "$PSScriptRoot/../tools/toolchain.ps1";$distro=Get-PhantomWslDistro
$wslBuild="/tmp/phantom-ev3-test-$($Profile.ToLower())";$source=Get-PhantomWslPath ev3;$diagnostic=if($Profile-eq'Release'){'OFF'}else{'ON'};$deep=if($Profile-eq'DeepDebug'){'ON'}else{'OFF'}
wsl.exe -d $distro -- bash -lc "rm -rf '$wslBuild' && cmake -S '$source' -B '$wslBuild' -G Ninja -DCMAKE_BUILD_TYPE=Debug -DPHANTOM_DIAGNOSTIC=$diagnostic -DPHANTOM_DEEP_DEBUG=$deep && cmake --build '$wslBuild' && ctest --test-dir '$wslBuild' --output-on-failure"
if($LASTEXITCODE-ne 0){throw "EV3 TEST failed: $Profile"}
