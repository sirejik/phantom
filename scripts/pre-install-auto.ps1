param(
  [switch]$SkipUnity,
  [ValidateRange(1,7)][int]$Stage=3
)
$ErrorActionPreference="Stop"
. "$PSScriptRoot/../tools/toolchain.ps1"
$started=(Get-Date).ToUniversalTime()
$checks=@()
$wslDistro=Get-PhantomWslDistro
$wslEv3Source=Get-PhantomWslPath ev3
$wslRepository=Get-PhantomWslPath .
function Run-Check([string]$Name,[int]$IntroducedAtStage,[scriptblock]$Body){
    try{
        $global:LASTEXITCODE=0
        & $Body
        if($LASTEXITCODE -ne 0){throw "exit $LASTEXITCODE"}
        $script:checks+=@{test_id=$Name;introduced_at_stage=$IntroducedAtStage;applicable_to_stage=$Stage;status="PASS";runner=$Name}
    }catch{
        $script:checks+=@{test_id=$Name;introduced_at_stage=$IntroducedAtStage;applicable_to_stage=$Stage;status="FAIL";runner=$Name;detail=$_.Exception.Message}
        Write-Warning "$Name FAIL: $($_.Exception.Message)"
    }
}
Run-Check "specification-manifest-generated" 1 {python tools/specgen.py --check}
Run-Check "section-index-generated" 1 {python tools/docindex.py --check}
Run-Check "documentation-lint" 1 {python tools/doclint.py}
Run-Check "implementation-map" 1 {python tools/implementation_map_check.py}
Run-Check "protocol-schema-generated" 1 {python tools/protocolgen.py --check}
Run-Check "canonicalization-rfc8785" 1 {python tools/test_jcs.py}
Run-Check "ipc-contract-cross-implementation" 3 {python tools/test_ipc_contract.py}
Run-Check "config-validation-boundaries" 1 {python tools/test_configgen.py}
Run-Check "spec-wire-contract" 1 {python tools/spec_contract_check.py}
Run-Check "config-json-schema-generated" 1 {python tools/configgen.py --check}
Run-Check "protocol-exact-hmac-fuzz" 1 {python tools/test_protocol.py}
Run-Check "simulator-regressions" 1 {python sim/ev3-simulator/test_simulator.py}
Run-Check "ev3-stage3-network-security" 3 {python ev3/network/test_phantom_network.py}
Run-Check "ev3-device-auto-regressions" 3 {python tools/test_ev3_device_auto.py}
Run-Check "ev3-deployment-shell-syntax" 2 {wsl.exe -d $wslDistro -- bash -lc "cd '$wslRepository' && sh -n deploy/scripts/install-release deploy/scripts/start-release deploy/scripts/run-device-auto deploy/scripts/rollback-release deploy/scripts/wifi-autoconnect"}
Run-Check "deployment-powershell-syntax" 2 {
  $parseFailures=@()
  foreach($path in @('scripts/quest-install.ps1','scripts/quest-start.ps1','scripts/quest-device-auto.ps1','scripts/ev3-transfer.ps1','scripts/ev3-install.ps1','scripts/ev3-start.ps1','scripts/ev3-device-auto.ps1','scripts/ev3-recover.ps1')){
    $tokens=$null;$errors=$null
    [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path $path),[ref]$tokens,[ref]$errors)|Out-Null
    if($errors.Count){$parseFailures+="$path`: $($errors.Message -join '; ')"}
  }
  if($parseFailures.Count){throw ($parseFailures -join "`n")}
}
Run-Check "tracking-replay-regressions" 1 {python sim/tracking-replay/test_tracking_replay.py}
Run-Check "artifact-gate-regressions" 1 {python tools/test_artifact_check.py}
Run-Check "build-identity-golden" 1 {python tools/test_build_identity.py}
Run-Check "secret-scan" 1 {python tools/security_scan.py --include-artifacts}
Run-Check "secret-scan-regressions" 1 {python tools/test_security_scan.py}
Run-Check "quest-pure-core" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File tools/quest_validation/compile_and_smoke.ps1}
Run-Check "quest-simulator-integration" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File tools/quest_validation/run_udp_integration.ps1}
Run-Check "quest-android-nsd-contract" 3 {python tools/quest_android_nsd_check.py}
Run-Check "quest-androidlib-compile" 3 {& "$PSScriptRoot/../tools/quest_validation/compile_androidlib.ps1"}
Run-Check "quest-provider-compatibility" 2 {python tools/quest_provider_compatibility_check.py}
Run-Check "spec-test-duration-contract" 2 {python tools/spec_test_duration_check.py}
Run-Check "quest-analyzer-regressions" 2 {python tools/quest_validation/test_analyze.py}
Run-Check "ev3-analyzer-regressions" 2 {python tools/ev3_validation/test_analyze.py}
Run-Check "ev3-host-release" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-host-build.ps1 -Profile Release}
Run-Check "ev3-host-diagnostic" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-host-build.ps1 -Profile Diagnostic}
Run-Check "ev3-host-asan-ubsan" 1 {wsl.exe -d $wslDistro -- bash -lc "rm -rf /tmp/phantom-ev3-sanitize && cmake -S '$wslEv3Source' -B /tmp/phantom-ev3-sanitize -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' && cmake --build /tmp/phantom-ev3-sanitize && ASAN_OPTIONS=detect_leaks=1 ctest --test-dir /tmp/phantom-ev3-sanitize --output-on-failure"}
if($SkipUnity){$checks+=@{test_id="unity-editmode";introduced_at_stage=2;applicable_to_stage=$Stage;status="NOT_RUN";runner="scripts/quest-test.ps1";detail="explicit -SkipUnity"}}else{Run-Check "unity-editmode" 2 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/quest-test.ps1}}
Run-Check "post-build-artifacts" 2 {
  python tools/artifact_check.py
}
$mandatoryIncomplete=$checks|Where-Object status -ne "PASS"
$status=if($mandatoryIncomplete){"INCOMPLETE"}else{"PASS"}
$commit=(git rev-parse HEAD).Trim()
$dirty=((git status --porcelain).Count -gt 0)
$sourceTreeHash=(python tools/source_hash.py PhantomQuest/Assets/Phantom PhantomQuest/Assets/Plugins PhantomQuest/Packages PhantomQuest/ProjectSettings ev3 protocol config tools scripts sim deploy).Trim()
$specificationHash=(Get-FileHash docs/PHANTOM_SPECIFICATION.md -Algorithm SHA256).Hash.ToLower()
$protocolHash=(Get-Content protocol/generated/schema.sha256).Split()[0]
$artifacts=@()
$currentEv3BuildIds=@(Get-ChildItem build\ev3-armel\*\build-manifest.json -File -ErrorAction SilentlyContinue|ForEach-Object{(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id})
$artifactFiles=@(
  Get-Item build\quest\PhantomQuest-release.apk,build\quest\PhantomQuest-release.apk.build-manifest.json,build\quest\PhantomQuest-diagnostic.apk,build\quest\PhantomQuest-diagnostic.apk.build-manifest.json -ErrorAction SilentlyContinue
  Get-ChildItem build\ev3-host-*\build-manifest.json,build\ev3-host-*\SHA256SUMS -File -ErrorAction SilentlyContinue
  Get-ChildItem build\ev3-armel\*\bin\phantom-controller,build\ev3-armel\*\bin\phantom-safety,build\ev3-armel\*\build-manifest.json,build\ev3-armel\*\SHA256SUMS -File -ErrorAction SilentlyContinue
  Get-ChildItem build\ev3-packages\phantom-*.tar.gz,build\ev3-packages\phantom-*.tar.gz.build-manifest.json -File -ErrorAction SilentlyContinue|Where-Object{$path=$_.Name;$currentEv3BuildIds|Where-Object{$path.Contains($_)}}
  Get-Item deploy\scripts\install-release,deploy\scripts\start-release,deploy\scripts\run-device-auto,deploy\scripts\rollback-release -ErrorAction SilentlyContinue
)
$artifactFiles|Sort-Object FullName -Unique|ForEach-Object{$artifacts+=@{path=$_.FullName.Substring((Resolve-Path .).Path.Length+1);sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()}}
$buildIds=@();$artifactFiles|Where-Object Name -eq "build-manifest.json"|ForEach-Object{$buildIds+=(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id};$artifactFiles|Where-Object Name -like "*.build-manifest.json"|ForEach-Object{$buildIds+=(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id};$buildIds=@($buildIds|Sort-Object -Unique)
$report=[ordered]@{schema_version=3;gate="PRE-INSTALL AUTO";stage=$Stage;status=$status;git_commit=$commit;build_ids=$buildIds;source_tree_hash=$sourceTreeHash;worktree_dirty=$dirty;specification_sha256=$specificationHash;protocol_schema_hash=$protocolHash;started_at=$started.ToString('o');finished_at=(Get-Date).ToUniversalTime().ToString('o');checks=$checks;artifacts=$artifacts}
New-Item -ItemType Directory -Force results\pre-install|Out-Null
$report|ConvertTo-Json -Depth 8|Set-Content results\pre-install\report.json -Encoding UTF8
Write-Output "PRE-INSTALL AUTO: $status"
if($status -ne "PASS"){exit 2}
