param(
    [string]$Output="",
    [string]$SigningDirectory=".secrets/quest-release",
    [ValidateSet("Release","Diagnostic")][string]$Profile="Diagnostic",
    [switch]$VerifyReproducibility,
    [string]$ReproducibilityWorkspace='build/reproducibility',
    [ValidateRange(1,3600)][int]$TimeoutSeconds=1800
)
$ErrorActionPreference='Stop'
. "$PSScriptRoot/build-environment.ps1"
if($VerifyReproducibility){Invoke-PhantomBuildReproducibility QUEST $Profile $ReproducibilityWorkspace;return}
$ErrorActionPreference="Stop"
foreach($check in @(
    @('tools/protocolgen.py','--check'),
    @('tools/configgen.py','--check')))
{
    & python $check[0] $check[1]
    if($LASTEXITCODE-ne 0){throw "Quest BUILD prerequisite consistency check failed: $($check[0])"}
}
$unity=Assert-PhantomQuestBuildEnvironment
if(!$Output){$Output="build/quest/PhantomQuest-$($Profile.ToLowerInvariant()).apk"}
$signingRoot=[System.IO.Path]::GetFullPath($SigningDirectory)
$keystore=Join-Path $signingRoot "phantom-quest-release.keystore"
$passwordFile=Join-Path $signingRoot "keystore.pass"
if(!(Test-Path -LiteralPath $keystore)){throw "Release keystore not found: $keystore"}
if(!(Test-Path -LiteralPath $passwordFile)){throw "Release keystore password file not found: $passwordFile"}
$env:PHANTOM_APK_PATH=[System.IO.Path]::GetFullPath($Output)
$env:PHANTOM_KEYSTORE_PATH=$keystore
$env:PHANTOM_KEYSTORE_PASSWORD_FILE=$passwordFile
$env:PHANTOM_KEY_ALIAS="phantom-quest-release"
$env:PHANTOM_META_APP_ID="1405011949353501"
$env:PHANTOM_BUILD_PROFILE=$Profile
$env:PHANTOM_GIT_COMMIT=(git rev-parse HEAD).Trim()
$env:PHANTOM_WORKTREE_DIRTY=if((git status --porcelain).Count -gt 0){"true"}else{"false"}
$env:PHANTOM_PROTOCOL_SCHEMA_HASH=(Get-Content protocol\generated\schema.sha256).Split()[0]
$env:PHANTOM_PROTOCOL_SEMANTICS_HASH=(Get-Content protocol\generated\semantics.sha256).Split()[0]
$env:PHANTOM_PROTOCOL_CONTRACT_HASH=(Get-Content protocol\generated\contract.sha256).Split()[0]
$questConfig=if($Profile -in @("Diagnostic")){"config\generated\quest-network-only.generated.json"}else{"config\generated\quest.generated.json"}
$env:PHANTOM_QUEST_CONFIG_PATH=[System.IO.Path]::GetFullPath($questConfig)
$env:PHANTOM_CONFIG_HASH=(Get-FileHash $questConfig -Algorithm SHA256).Hash.ToLower()
$configManifest=Get-Content config\generated\config-manifest.json -Raw|ConvertFrom-Json
$env:PHANTOM_BUNDLE_HASH=if($Profile -in @("Diagnostic")){$configManifest.artifact_hashes.'commissioning_bundle-network-only'}else{$configManifest.artifact_hashes.commissioning_bundle}
$env:PHANTOM_PACKAGE_LOCK_SHA256=(Get-FileHash PhantomQuest\Packages\packages-lock.json -Algorithm SHA256).Hash.ToLower()
$env:PHANTOM_SOURCE_TREE_HASH=(python tools\source_hash.py PhantomQuest\Assets\Phantom PhantomQuest\Assets\Plugins PhantomQuest\Packages PhantomQuest\ProjectSettings).Trim()
$env:PHANTOM_BUILD_ID=(python tools\build_identity.py --component QUEST --profile $Profile --source-tree-hash $env:PHANTOM_SOURCE_TREE_HASH --protocol-contract-hash $env:PHANTOM_PROTOCOL_CONTRACT_HASH --component-config-hash $env:PHANTOM_CONFIG_HASH --toolchain-or-package-lock-hash $env:PHANTOM_PACKAGE_LOCK_SHA256).Trim()
# Android Gradle Prefab corrupts non-ASCII Windows profile paths in generated
# batch files. Keep its cache in the ASCII-only workspace path.
$env:GRADLE_USER_HOME=[System.IO.Path]::GetFullPath(".gradle-quest")
$arguments=@(
    "-batchmode","-nographics",
    "-buildTarget","Android",
    "-projectPath",[System.IO.Path]::GetFullPath("PhantomQuest"),
    "-executeMethod","Phantom.Editor.PhantomBuild.BuildAndroid",
    "-logFile",[System.IO.Path]::GetFullPath("results/quest/android-build.log"),
    "-quit"
)
$process=Start-Process -FilePath $unity -ArgumentList $arguments -WindowStyle Hidden -PassThru
# Start-Process -Wait waits for the complete descendant process tree on Windows.
# Unity may leave Gradle helpers alive after the editor has already returned, so
# wait for the editor process itself and use its real exit code.
if(!$process.WaitForExit($TimeoutSeconds*1000)){
    try{$process.Kill()}catch{}
    throw "Unity Android BUILD timeout after ${TimeoutSeconds}s; see results/quest/android-build.log"
}
$unityExitCode=$process.ExitCode
# A surviving Gradle daemon can retain a Windows file handle in the generated
# launcher and make the immediately following profile build nondeterministic.
$gradleWrapper=[System.IO.Path]::GetFullPath("PhantomQuest/Library/Bee/Android/Prj/IL2CPP/Gradle/gradlew.bat")
if(Test-Path -LiteralPath $gradleWrapper)
{
    $previousLocation=Get-Location
    try
    {
        Set-Location ([System.IO.Path]::GetDirectoryName($gradleWrapper))
        & $gradleWrapper --stop | Out-Null
    }
    finally { Set-Location $previousLocation }
}
if($unityExitCode -ne 0){throw "Unity Android build failed with exit code $unityExitCode; see results/quest/android-build.log"}
$manifest=Get-Content -LiteralPath ($env:PHANTOM_APK_PATH+'.build-manifest.json') -Raw -Encoding UTF8|ConvertFrom-Json
$actualHash=(Get-FileHash -LiteralPath $env:PHANTOM_APK_PATH -Algorithm SHA256).Hash.ToLowerInvariant()
if($manifest.build_id-ne$env:PHANTOM_BUILD_ID-or$manifest.apk_sha256-ne$actualHash){throw 'Quest BUILD artifact validation failed'}
$apkSigner=Get-PhantomApkSigner
$signatureOutput=& $apkSigner verify --verbose --print-certs $env:PHANTOM_APK_PATH 2>&1
if($LASTEXITCODE-ne 0){throw "Quest APK signature verification failed: $($signatureOutput -join [Environment]::NewLine)"}
$certificateLine=$signatureOutput|Where-Object{$_-match 'Signer #1 certificate SHA-256 digest:\s*([0-9a-fA-F:]{64,95})'}|Select-Object -First 1
if(!$certificateLine){throw 'Quest APK signing certificate SHA-256 was not reported by apksigner'}
$certificateSha256=([regex]::Match([string]$certificateLine,'([0-9a-fA-F:]{64,95})\s*$').Groups[1].Value-replace':','').ToLowerInvariant()
if($certificateSha256-notmatch'^[0-9a-f]{64}$'){throw 'Quest APK signing certificate SHA-256 is malformed'}
$manifest|Add-Member -NotePropertyName apk_signing_certificate_sha256 -NotePropertyValue $certificateSha256 -Force
[IO.File]::WriteAllText($env:PHANTOM_APK_PATH+'.build-manifest.json',($manifest|ConvertTo-Json -Depth 20 -Compress)+"`n",[Text.UTF8Encoding]::new($false))
python tools/artifact_check.py --component QUEST --profile $Profile --artifact $env:PHANTOM_APK_PATH
if($LASTEXITCODE-ne 0){throw 'Quest BUILD artifact structure/metadata validation failed'}
$buildResult=[ordered]@{schema_version=1;phase='BUILD';status='PASS';component='QUEST';profile=$Profile;qualification_eligible=$true;build_id=$manifest.build_id;artifact_path=$env:PHANTOM_APK_PATH;artifact_sha256=$actualHash;config_hash=$manifest.config_hash;protocol_schema_hash=$manifest.protocol_schema_hash;protocol_semantics_hash=$manifest.protocol_semantics_hash;protocol_contract_hash=$manifest.protocol_contract_hash;apk_signing_certificate_sha256=$certificateSha256}
[IO.File]::WriteAllText($env:PHANTOM_APK_PATH+'.build-result.json',($buildResult|ConvertTo-Json -Depth 5)+"`n",[Text.UTF8Encoding]::new($false))
Write-Output "QUEST BUILD: PASS profile=$Profile build_id=$($manifest.build_id)"
