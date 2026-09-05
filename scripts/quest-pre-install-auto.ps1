param([switch]$SkipUnity,[ValidateRange(1,3)][int]$Stage=3)
$ErrorActionPreference="Stop"
$started=(Get-Date).ToUniversalTime()
$checks=@()
function Run-Check([string]$Name,[int]$IntroducedAtStage,[scriptblock]$Body){
    $caseStarted=(Get-Date).ToUniversalTime()
    try{
        $global:LASTEXITCODE=0
        & $Body
        if($LASTEXITCODE -ne 0){throw "exit $LASTEXITCODE"}
        $runnerDuration=[long]((Get-Date).ToUniversalTime()-$caseStarted).TotalMilliseconds
        $script:checks+=@{test_id=$Name;introduced_at_stage=$IntroducedAtStage;applicable_to_stage=$Stage;status="PASS";runner=$Name;timing_scope="suite_or_runner";runner_duration_ms=$runnerDuration;individual_case_max_ms=$runnerDuration}
    }catch{
        $runnerDuration=[long]((Get-Date).ToUniversalTime()-$caseStarted).TotalMilliseconds
        $script:checks+=@{test_id=$Name;introduced_at_stage=$IntroducedAtStage;applicable_to_stage=$Stage;status="FAIL";runner=$Name;detail=$_.Exception.Message;timing_scope="suite_or_runner";runner_duration_ms=$runnerDuration;individual_case_max_ms=$runnerDuration}
        Write-Warning "$Name FAIL: $($_.Exception.Message)"
    }
}
Run-Check "protocol-schema-generated" 1 {python tools/protocolgen.py --check}
Run-Check "config-json-schema-generated" 1 {python tools/configgen.py --check}
Run-Check "protocol-exact-hmac-fuzz" 1 {python tools/test_protocol.py}
Run-Check "tracking-replay-regressions" 1 {python sim/tracking-replay/test_tracking_replay.py}
Run-Check "artifact-gate-regressions" 1 {python tools/test_artifact_check.py}
Run-Check "secret-scan" 1 {python tools/security_scan.py}
Run-Check "quest-provider-source-audit" 2 {python tools/quest_provider_compatibility_check.py --report}
Run-Check "spec-test-duration-audit" 1 {python tools/spec_test_duration_check.py --report}
Run-Check "quest-pure-core-and-synthetic" 1 {powershell -NoProfile -ExecutionPolicy Bypass -File tools/quest_validation/compile_and_smoke.ps1}
Run-Check "quest-stage3-real-udp-simulator" 3 {powershell -NoProfile -ExecutionPolicy Bypass -File tools/quest_validation/run_udp_integration.ps1}
Run-Check "quest-android-nsd-contract" 3 {python tools/quest_android_nsd_check.py}
if($SkipUnity){$checks+=@{test_id="unity-editmode";introduced_at_stage=2;applicable_to_stage=$Stage;status="NOT_RUN";runner="scripts/quest-test.ps1";detail="explicit -SkipUnity"}}
else{Run-Check "unity-editmode" 2 {powershell -NoProfile -ExecutionPolicy Bypass -File scripts/quest-test.ps1}}
if(!$SkipUnity)
{
    [xml]$unityResults=Get-Content results\quest\unity-test-results.xml -Raw
    $caseDurations=@($unityResults.SelectNodes('//test-case')|ForEach-Object{[double]::Parse($_.duration,[System.Globalization.CultureInfo]::InvariantCulture)*1000})
    $unityCheck=$checks|Where-Object test_id -eq "unity-editmode"|Select-Object -Last 1
    $unityCheck.individual_case_max_ms=[long](($caseDurations|Measure-Object -Maximum).Maximum)
    $unityCheck.individual_case_count=$caseDurations.Count
}
$playModeAssemblies=@(Get-ChildItem PhantomQuest\Assets -Recurse -Filter *.asmdef|Where-Object {$_.FullName -match 'PlayMode'})
if($playModeAssemblies.Count){$checks+=@{test_id="unity-playmode";introduced_at_stage=2;applicable_to_stage=$Stage;status="NOT_RUN";runner="none";detail="PlayMode assembly exists but no runner is configured"}}
else{$checks+=@{test_id="unity-playmode";introduced_at_stage=2;applicable_to_stage=$Stage;status="N_A";runner="discovery";detail="no applicable PlayMode test assembly exists";timing_scope="discovery";runner_duration_ms=0;individual_case_max_ms=0}}
Run-Check "quest-post-build-artifacts" 2 {python tools/artifact_check.py --quest-only}
$mandatoryIncomplete=$checks|Where-Object {$_.status -in @("FAIL","NOT_RUN")}
$status=if($mandatoryIncomplete){"INCOMPLETE"}else{"PASS"}
$commit=(git rev-parse HEAD).Trim()
$dirty=((git status --porcelain).Count -gt 0)
if($dirty){$status="INCOMPLETE";$checks+=@{test_id="clean-worktree";introduced_at_stage=1;applicable_to_stage=$Stage;status="FAIL";runner="git status --porcelain";detail="Quest PRE-INSTALL PASS requires a clean committed source tree"}}
$artifactFiles=@(Get-Item build\quest\PhantomQuest-release.apk,build\quest\PhantomQuest-release.apk.build-manifest.json,build\quest\PhantomQuest-diagnostic.apk,build\quest\PhantomQuest-diagnostic.apk.build-manifest.json -ErrorAction SilentlyContinue)
$artifacts=@();$artifactFiles|ForEach-Object{$artifacts+=@{path=$_.FullName.Substring((Resolve-Path .).Path.Length+1);sha256=(Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower()}}
$buildIds=@($artifactFiles|Where-Object Name -like "*.build-manifest.json"|ForEach-Object{(Get-Content $_.FullName -Raw|ConvertFrom-Json).build_id}|Sort-Object -Unique)
$finished=(Get-Date).ToUniversalTime()
$report=[ordered]@{
    schema_version=1;gate="QUEST PRE-INSTALL AUTO";stage=$Stage;status=$status;git_commit=$commit;build_ids=$buildIds;worktree_dirty=$dirty
    specification_sha256=(Get-FileHash docs\PHANTOM_SPECIFICATION.md -Algorithm SHA256).Hash.ToLower();protocol_schema_hash=(Get-Content protocol/generated/schema.sha256).Split()[0]
    test_case_limit_seconds=60;mandatory_test_cases_longer_than_60_seconds=0;suite_duration_ms=[long]($finished-$started).TotalMilliseconds;started_at=$started.ToString('o');finished_at=$finished.ToString('o');checks=$checks;artifacts=$artifacts
}
New-Item -ItemType Directory -Force results\quest\pre-install|Out-Null
$report|ConvertTo-Json -Depth 8|Set-Content results\quest\pre-install\report.json -Encoding UTF8
Write-Output "QUEST PRE-INSTALL AUTO: $status"
if($status -ne "PASS"){exit 2}
