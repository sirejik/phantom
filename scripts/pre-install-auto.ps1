param([switch]$SkipUnity,[switch]$SkipArmel,[ValidateRange(1,7)][int]$Stage=2)
$ErrorActionPreference="Stop"
$started=(Get-Date).ToUniversalTime()
$checks=@()
$quotedEv3Source="'"+(Resolve-Path ev3).Path+"'"
$wslEv3Source=(wsl.exe -d Ubuntu -- wslpath -a $quotedEv3Source).Trim()
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
Run-Check "protocol-schema-generated" 1 {python tools/protocolgen.py --check}
Run-Check "config-json-schema-generated" 1 {python tools/configgen.py --check}
Run-Check "protocol-exact-hmac-fuzz" 1 {python tools/test_protocol.py}
Run-Check "simulator-regressions" 1 {python sim/ev3-simulator/test_simulator.py}
Run-Check "ev3-stage3-network-security" 3 {python ev3/network/test_phantom_network.py}
Run-Check "tracking-replay-regressions" 1 {python sim/tracking-replay/test_tracking_replay.py}
Run-Check "artifact-gate-regressions" 1 {python tools/test_artifact_check.py}
Run-Check "secret-scan" 1 {python tools/security_scan.py}
Run-Check "quest-pure-core" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File tools/quest_validation/compile_and_smoke.ps1}
Run-Check "quest-simulator-integration" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File tools/quest_validation/run_udp_integration.ps1}
Run-Check "ev3-host-release" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-host-build.ps1 -Profile Release}
Run-Check "ev3-host-diagnostic" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-host-build.ps1 -Profile Diagnostic}
Run-Check "ev3-host-asan-ubsan" 1 {wsl.exe -d Ubuntu -- bash -lc "rm -rf /tmp/phantom-ev3-sanitize && cmake -S '$wslEv3Source' -B /tmp/phantom-ev3-sanitize -G Ninja -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS='-fsanitize=address,undefined -fno-omit-frame-pointer' && cmake --build /tmp/phantom-ev3-sanitize && ASAN_OPTIONS=detect_leaks=1 ctest --test-dir /tmp/phantom-ev3-sanitize --output-on-failure"}
if($SkipUnity){$checks+=@{test_id="unity-editmode";introduced_at_stage=2;applicable_to_stage=$Stage;status="NOT_RUN";runner="scripts/quest-test.ps1";detail="explicit -SkipUnity"}}else{Run-Check "unity-editmode" 2 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/quest-test.ps1}}
if($SkipArmel){$checks+=@{test_id="ev3-armel-release-diagnostic";introduced_at_stage=1;applicable_to_stage=$Stage;status="NOT_RUN";runner="scripts/ev3-armel-docker.ps1";detail="explicit -SkipArmel"}}else{Run-Check "ev3-armel-release-diagnostic" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ev3-armel-docker.ps1}}
Run-Check "post-build-artifacts" 2 {python tools/artifact_check.py}
$mandatoryIncomplete=$checks|Where-Object status -ne "PASS"
$status=if($mandatoryIncomplete){"INCOMPLETE"}else{"PASS"}
$commit=(git rev-parse HEAD).Trim()
$dirty=((git status --porcelain).Count -gt 0)
$sourceTreeHash=(python tools/source_hash.py PhantomQuest/Assets/Phantom PhantomQuest/Assets/Plugins PhantomQuest/Packages PhantomQuest/ProjectSettings ev3 protocol config tools scripts sim deploy).Trim()
$specificationHash=(Get-FileHash docs/PHANTOM_SPECIFICATION.md -Algorithm SHA256).Hash.ToLower()
$protocolHash=(Get-Content protocol/generated/schema.sha256).Split()[0]
if($dirty){$status="INCOMPLETE";$checks+=@{test_id="clean-worktree";introduced_at_stage=1;applicable_to_stage=$Stage;status="FAIL";runner="git status --porcelain";detail="PRE-INSTALL PASS requires a clean committed source tree"}}
$artifacts=@()
$artifactFiles=@(
  Get-Item build\quest\PhantomQuest-release.apk,build\quest\PhantomQuest-release.apk.build-manifest.json,build\quest\PhantomQuest-diagnostic.apk,build\quest\PhantomQuest-diagnostic.apk.build-manifest.json -ErrorAction SilentlyContinue
  Get-ChildItem build\ev3-host-*\build-manifest.json,build\ev3-host-*\SHA256SUMS -File -ErrorAction SilentlyContinue
  Get-ChildItem build\ev3-armel\*\bin\phantom-controller,build\ev3-armel\*\bin\phantom-safety,build\ev3-armel\*\build-manifest.json,build\ev3-armel\*\SHA256SUMS -File -ErrorAction SilentlyContinue
)
$artifactFiles|Sort-Object FullName -Unique|ForEach-Object{$artifacts+=@{path=$_.FullName.Substring((Resolve-Path .).Path.Length+1);sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()}}
$buildIds=@();$artifactFiles|Where-Object Name -eq "build-manifest.json"|ForEach-Object{$buildIds+=(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id};$artifactFiles|Where-Object Name -like "*.build-manifest.json"|ForEach-Object{$buildIds+=(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id};$buildIds=@($buildIds|Sort-Object -Unique)
$report=[ordered]@{schema_version=2;gate="PRE-INSTALL AUTO";stage=$Stage;status=$status;git_commit=$commit;build_ids=$buildIds;source_tree_hash=$sourceTreeHash;worktree_dirty=$dirty;specification_sha256=$specificationHash;protocol_schema_hash=$protocolHash;started_at=$started.ToString('o');finished_at=(Get-Date).ToUniversalTime().ToString('o');checks=$checks;artifacts=$artifacts}
New-Item -ItemType Directory -Force results\pre-install|Out-Null
$report|ConvertTo-Json -Depth 8|Set-Content results\pre-install\report.json -Encoding UTF8
Write-Output "PRE-INSTALL AUTO: $status"
if($status -ne "PASS"){exit 2}
