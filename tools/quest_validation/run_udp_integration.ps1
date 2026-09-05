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
$bundle=(Get-Content config/generated/config-manifest.json -Raw|ConvertFrom-Json).artifact_hashes.'commissioning_bundle-network-only'

function Invoke-UdpScenario([string]$Scenario,[int]$Port)
{
    $stdout=Join-Path $outDir "simulator-$Scenario.stdout.jsonl"
    $stderr=Join-Path $outDir "simulator-$Scenario.stderr.txt"
    Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    $sim=Start-Process -FilePath "python" -ArgumentList @("sim/ev3-simulator/phantom_simulator.py","--bind","127.0.0.1","--port",$Port,"--scenario",$Scenario,"--network-only") -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    try
    {
        $deadline=(Get-Date).AddSeconds(3);$record=$null
        while((Get-Date)-lt $deadline -and !$record){Start-Sleep -Milliseconds 50;if(Test-Path -LiteralPath $stdout){$first=Get-Content -LiteralPath $stdout -First 1 -ErrorAction SilentlyContinue;if($first){$record=$first|ConvertFrom-Json}}}
        if(!$record){throw "simulator discovery record timeout: $Scenario"}
        & "$outDir/UdpIntegration.exe" $record.controller_boot_id $record.port $bundle $Scenario
        if($LASTEXITCODE -ne 0){throw "UDP scenario failed: $Scenario"}
    }
    finally { if(!$sim.HasExited){Stop-Process -Id $sim.Id} }
}

Invoke-UdpScenario "normal" 31339
Invoke-UdpScenario "hello_ack_lost" 31340
Invoke-UdpScenario "bad_hmac" 31341
Invoke-UdpScenario "telemetry_stop_resume" 31342
Invoke-UdpScenario "busy" 31343
Invoke-UdpScenario "wrong_robot" 31344
Invoke-UdpScenario "wrong_protocol" 31345
Invoke-UdpScenario "wrong_schema_hash" 31346
Invoke-UdpScenario "wrong_bundle_hash" 31347
