$ErrorActionPreference="Stop"
$editorData="C:\Program Files\Unity\Hub\Editor\6000.3.22f1\Editor\Data"
$dotnet=Join-Path $editorData "NetCoreRuntime\dotnet.exe"
$csc=Join-Path $editorData "DotNetSdkRoslyn\csc.dll"
$api=Join-Path $editorData "MonoBleedingEdge\lib\mono\4.7.1-api"
$outDir=[System.IO.Path]::GetFullPath("results/quest/smoke")
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
powershell -NoProfile -ExecutionPolicy Bypass -File "tools/quest_validation/compile_and_smoke.ps1"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
& $dotnet $csc -nologo -langversion:9 -noconfig -nostdlib -target:exe -out:"$outDir/UdpIntegration.exe" -r:"$api/mscorlib.dll" -r:"$api/System.dll" -r:"$api/System.Core.dll" -r:"$outDir/Phantom.Core.dll" "tools/quest_validation/UdpIntegration.cs"
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
$stdout=Join-Path $outDir "simulator-integration.stdout.jsonl"
$stderr=Join-Path $outDir "simulator-integration.stderr.txt"
$sim=Start-Process -FilePath "python" -ArgumentList @("sim/ev3-simulator/phantom_simulator.py","--bind","127.0.0.1","--port","31339","--scenario","normal") -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
try
{
    Start-Sleep -Milliseconds 300
    & "$outDir/UdpIntegration.exe"
    if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
}
finally
{
    if(!$sim.HasExited){Stop-Process -Id $sim.Id}
}
