$ErrorActionPreference='Stop'
$repository=Split-Path -Parent $PSScriptRoot
. "$repository/scripts/pair-state.ps1"
. "$repository/scripts/ev3-deploy-common.ps1"
$temporary=Join-Path ([IO.Path]::GetTempPath()) ('phantom-pair-test-'+[Guid]::NewGuid().ToString('N'))
$failures=New-Object 'System.Collections.Generic.List[string]'
function Assert-True([bool]$Condition,[string]$Message){if(!$Condition){$failures.Add($Message)}}
function Assert-Throws([scriptblock]$Action,[string]$Code)
{
    try{& $Action; $failures.Add("expected $Code")}
    catch{Assert-True ($_.Exception.Message.StartsWith($Code+':')) "expected $Code, got $($_.Exception.Message)"}
}
try
{
    $paths=Get-PhantomPairPaths $temporary
    Assert-Throws {Read-PhantomPairState $temporary} 'PROVISION_REQUIRED'
    New-Item -ItemType Directory -Force -Path $paths.SshDirectory,$paths.SecretDirectory|Out-Null

    $generatedKey=Join-Path $temporary 'generated/id_ed25519'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $generatedKey)|Out-Null
    New-PhantomDeploymentKey $generatedKey
    Assert-True ((Test-Path -LiteralPath $generatedKey -PathType Leaf)-and(Test-Path -LiteralPath ($generatedKey+'.pub') -PathType Leaf)) 'empty-passphrase deployment key generation failed'

    foreach($file in @($paths.SshKey,$paths.SshConfig,$paths.KnownHosts,$paths.ControlSecret)){[IO.File]::WriteAllText($file,'test')}
    $record=[ordered]@{provision_schema_version=1;provision_status='complete';quest_adb_serial='QUEST-EXACT-001';ev3_hostname='ev3dev.local';ev3_host_key_fingerprint='SHA256:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA';robot_id='phantom01';control_key_id='phantom01-control'}
    Write-PhantomPairState $record $temporary
    $loaded=Read-PhantomPairState $temporary -RequirePrivateFiles
    Assert-True ($loaded.State.quest_adb_serial-eq'QUEST-EXACT-001') 'pair record round trip failed'

    $fake=Join-Path $temporary 'adb.cmd'
    [IO.File]::WriteAllText($fake,"@echo off`r`necho List of devices attached`r`necho %PHANTOM_TEST_ADB_LINE%`r`n",[Text.Encoding]::ASCII)
    $env:PHANTOM_TEST_ADB_LINE="QUEST-EXACT-001`tdevice"
    Assert-True ((Get-PhantomQuestDevice $fake $temporary)-eq'QUEST-EXACT-001') 'exact designated Quest was not selected'
    $env:PHANTOM_TEST_ADB_LINE="OTHER-DEVICE`tdevice"
    Assert-Throws {Get-PhantomQuestDevice $fake $temporary} 'QUEST_IDENTITY_MISMATCH'
    $env:PHANTOM_TEST_ADB_LINE=''
    Assert-Throws {Get-PhantomQuestDevice $fake $temporary} 'QUEST_NOT_FOUND'

    $run=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/provision-fixed-pair.ps1" -StateRoot $temporary -Destination (Join-Path $temporary 'result') 2>&1
    Assert-True ($LASTEXITCODE-eq 0) "idempotent PROVISION failed: $($run-join' ')"
    Assert-True (($run-join' ') -match'ALREADY_PROVISIONED') 'idempotent PROVISION did not report ALREADY_PROVISIONED'
    $savedPreference=$ErrorActionPreference;$ErrorActionPreference='Continue'
    try{$rotation=& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$repository/scripts/provision-fixed-pair.ps1" -StateRoot $temporary -Destination (Join-Path $temporary 'result') -RotateControlSecret 2>&1;$rotationExit=$LASTEXITCODE}
    finally{$ErrorActionPreference=$savedPreference}
    Assert-True ($rotationExit-ne 0) 'credential rotation without explicit repair was accepted'
    Assert-True (($rotation-join' ') -match'rotation/repin requires explicit -Repair') 'rotation admission did not fail with the canonical repair requirement'

    $fakeSsh=Join-Path $temporary 'fake-ssh.cmd'
    [IO.File]::WriteAllText($fakeSsh,"@echo off`r`necho REPORT_CHANNEL`r`necho DIAGNOSTIC_CHANNEL 1>&2`r`nexit /b 7`r`n",[Text.Encoding]::ASCII)
    $transport=Invoke-PhantomNative $fakeSsh @() 3 'DEVICE_NOT_FOUND'
    Assert-True ($transport.ExitCode-eq 7) 'mocked SSH exit code was not preserved'
    Assert-True (($transport.Stdout.Count-eq 1)-and($transport.Stdout[0]-eq'REPORT_CHANNEL')) 'mocked SSH stdout was not isolated'
    Assert-True (($transport.Stderr.Count-eq 1)-and($transport.Stderr[0].Trim()-eq'DIAGNOSTIC_CHANNEL')) 'mocked SSH stderr was not isolated'
}
finally
{
    Remove-Item Env:PHANTOM_TEST_ADB_LINE -ErrorAction SilentlyContinue
    if(Test-Path -LiteralPath $temporary){Remove-Item -LiteralPath $temporary -Recurse -Force}
}
if($failures.Count){$failures|ForEach-Object{[Console]::Error.WriteLine($_)};exit 1}
Write-Output 'pair-state mocked SSH/ADB contract: PASS'
