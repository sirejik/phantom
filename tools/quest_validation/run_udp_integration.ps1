$ErrorActionPreference="Stop"
. "$PSScriptRoot/../toolchain.ps1"
$editorData=Get-PhantomUnityEditorData
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

function Wait-DiscoveryRecord([string]$Path,[int]$TimeoutSeconds=8)
{
    $deadline=(Get-Date).AddSeconds($TimeoutSeconds)
    while((Get-Date)-lt $deadline)
    {
        Start-Sleep -Milliseconds 50
        if(Test-Path -LiteralPath $Path)
        {
            foreach($line in (Get-Content -LiteralPath $Path -ErrorAction SilentlyContinue))
            {
                if(!$line){continue}
                $record=$null
                try{$record=$line|ConvertFrom-Json}catch{continue}
                if($record.event -eq 'listening'){return $record}
            }
        }
    }
    return $null
}

# Scenario coverage against the PC simulator: fault injection and transport
# behaviour that the production worker cannot be asked to produce on demand.
function Invoke-SimulatorScenario([string]$Scenario,[int]$Port)
{
    $stdout=Join-Path $outDir "simulator-$Scenario.stdout.jsonl"
    $stderr=Join-Path $outDir "simulator-$Scenario.stderr.txt"
    Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    $sim=Start-Process -FilePath "python" -ArgumentList @("sim/ev3-simulator/phantom_simulator.py","--bind","127.0.0.1","--port",$Port,"--scenario",$Scenario,"--network-only") -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    try
    {
        $record=Wait-DiscoveryRecord $stdout 3
        if(!$record){throw "simulator discovery record timeout: $Scenario"}
        & "$outDir/UdpIntegration.exe" $record.controller_boot_id $record.port $bundle $Scenario
        if($LASTEXITCODE-ne 0){throw "UDP scenario failed: $Scenario"}
    }
    # The child may already have exited; cleanup must never fail the scenario.
    finally { Stop-Process -Id $sim.Id -Force -ErrorAction SilentlyContinue }
}

# Interoperability against the *production* worker. The simulator is a second
# implementation; only this proves the shipped client and the shipped server
# agree on HELLO/HMAC/session/telemetry.
function Invoke-ProductionWorkerScenario([string]$Scenario)
{
    $stdout=Join-Path $outDir "production-worker-$Scenario.stdout.jsonl"
    $stderr=Join-Path $outDir "production-worker-$Scenario.stderr.txt"
    Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
    $server=Start-Process -FilePath "python" -ArgumentList @("tools/quest_validation/real_server_harness.py","--bind","127.0.0.1") -PassThru -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    try
    {
        $record=Wait-DiscoveryRecord $stdout 12
        if(!$record){throw "production worker discovery record timeout: $Scenario"}
        & "$outDir/UdpIntegration.exe" $record.controller_boot_id $record.port $record.bundle_hash $Scenario $record.build_id
        if($LASTEXITCODE-ne 0){throw "production worker UDP scenario failed: $Scenario"}
        Write-Output "PASS: real UDP Stage-3 production-worker scenario=$Scenario (shipped client <-> shipped server)"
    }
    finally { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
}

Invoke-SimulatorScenario "normal" 31339
Invoke-SimulatorScenario "hello_ack_lost" 31340
Invoke-SimulatorScenario "bad_hmac" 31341
Invoke-SimulatorScenario "telemetry_stop_resume" 31342
Invoke-SimulatorScenario "busy" 31343
Invoke-SimulatorScenario "wrong_robot" 31344
Invoke-SimulatorScenario "wrong_protocol" 31345
Invoke-SimulatorScenario "wrong_schema_hash" 31346
Invoke-SimulatorScenario "wrong_bundle_hash" 31347
Invoke-ProductionWorkerScenario "normal"
